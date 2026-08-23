"""
Execute the Sierra Nevada altitude-matched observed SCM zones (issue #9).

Wires the pure primitives that already existed —
``src.spatial_causality.alpine_causality.altitude_matched_control_zone`` /
``compute_mtb_attribution``, and the new
``src.spatial_causality.alpine_scm_zones.execute_scm_attribution`` — to real
data for every Sierra Nevada asset with a real OAPN trace (issue #6):

  1. Build each asset's local corridor (0-50 m, ``ALPINE_LOCAL_OUTER_M``) and
     altitude-matched control zone (200-500 m annulus intersected with the
     trail's DEM elevation band ±50 m) in EPSG:25830, once, reusing a single
     Copernicus DEM window over the whole territory.
  2. For June/July/August 2024, run the new multi-tile summer mosaic
     (``etl_raster_processor.run_alpine_multitile_summer``, issue #9's
     counterpart to #7's winter mosaic) and take a zonal EVI/NDMI/NDVI mean
     inside each asset's local and control polygons
     (``src.geospatial.zonal_stats.zonal_mean``), masked by the summer SCL
     rule (snow/cloud/water dropped — snow is noise here, see
     ``alpine_spectral.alpine_valid_mask``).
  3. Feed the resulting monthly series into
     ``execute_scm_attribution``, which classifies each asset as
     ANTHROPOGENIC_RUTTING / MACROCLIMATE_DRIVEN / MIXED, or explicitly
     NO_VALID_CONTROL when a zone never had enough valid summer pixels —
     the fallback issue #9's acceptance criteria ask for, rather than a
     silently-simulated number indistinguishable from a real MIXED result.

Writes two committed, dashboard-light outputs:
    clean_assets/sierra_nevada_scm_zones.json  - per-asset attribution summary
    clean_assets/sierra_nevada_scm_zones.csv   - flat table, one row/asset

Each period's tile/scene manifest is kept alongside the raster output under
clean_assets/scm_zones/manifest_<period>.csv, mirroring issue #8's per-
observation provenance record.

Running (repeats the summer multi-tile mosaic 3x — several minutes/month)::

    AWS_NO_SIGN_REQUEST=YES PYTHONPATH=. python scripts/build_alpine_scm_zones.py
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import rasterio
from pyproj import CRS as ProjCRS
from pyproj import Transformer
from shapely.geometry import shape as shapely_shape
from shapely.ops import linemerge, transform as shapely_transform, unary_union

from etl_raster_processor import run_alpine_multitile_summer
from src.config.territories import get as get_territory
from src.features.alpine_spectral import AlpineSeason, alpine_valid_mask
from src.geospatial.alpine_dem import sample_slope_along_trail
from src.geospatial.geometry import (
    _DEFAULT_BUFFER_CRS,
    compute_slope_aspect,
    fetch_dem_window,
    metric_slope_transform,
)
from src.geospatial.zonal_stats import zonal_mean
from src.platform.alpine_trail_geoms import load_sierra_nevada_trail_geoms
from src.spatial_causality.alpine_causality import (
    ALPINE_CONTROL_INNER_M,
    ALPINE_CONTROL_OUTER_M,
    ALPINE_LOCAL_OUTER_M,
    altitude_matched_control_zone,
)
from src.spatial_causality.alpine_scm_zones import (
    MonthlyZoneSignal,
    execute_scm_attribution,
)
from src.territorial.alpine_fixtures import build_sierra_nevada_territory

_ROOT = Path(__file__).resolve().parents[1]
_CLEAN = _ROOT / "data" / "clean_assets"
_COMMITTED = _ROOT / "clean_assets"
_MANIFEST_DIR = _COMMITTED / "scm_zones"
_JSON_OUT = _COMMITTED / "sierra_nevada_scm_zones.json"
_CSV_OUT = _COMMITTED / "sierra_nevada_scm_zones.csv"

# One growing season, monthly cadence — same cadence as #8's winter series.
SUMMER_PERIODS: list[tuple[str, str, int, int]] = [
    ("2024-06", "2024-06-01/2024-06-30", 2024, 6),
    ("2024-07", "2024-07-01/2024-07-31", 2024, 7),
    ("2024-08", "2024-08-01/2024-08-31", 2024, 8),
]


def _trail_geom_4326(geom_dicts: list[dict]):
    """Merge an asset's real-trace geometry dict(s) into one Shapely line."""
    parts = [shapely_shape(g) for g in geom_dicts]
    merged = linemerge(unary_union(parts)) if len(parts) > 1 else parts[0]
    if merged.geom_type == "MultiLineString":
        # linemerge can still return disjoint pieces; the longest is the
        # trail's main trace (mirrors alpine_dem._to_metric's contract).
        merged = max(merged.geoms, key=lambda g: g.length)
    return merged


def _to_metric(geom_4326, target_crs: str = _DEFAULT_BUFFER_CRS):
    t = Transformer.from_crs(
        ProjCRS.from_epsg(4326), ProjCRS.from_user_input(target_crs), always_xy=True
    )
    return shapely_transform(t.transform, geom_4326)


def _build_zone_geometry(
    geoms: dict[str, list[dict]],
    dem_arr: np.ndarray,
    dem_transform: object,
    dem_crs: object,
    slope_deg: np.ndarray,
) -> dict[str, dict]:
    """Local corridor + altitude-matched control zone for every real-trace asset."""
    zones: dict[str, dict] = {}
    for asset_id, geom_list in geoms.items():
        trail_4326 = _trail_geom_4326(geom_list)
        trail_metric = _to_metric(trail_4326)

        local_zone = trail_metric.buffer(ALPINE_LOCAL_OUTER_M)
        annulus = trail_metric.buffer(ALPINE_CONTROL_OUTER_M).difference(
            trail_metric.buffer(ALPINE_CONTROL_INNER_M)
        )
        control_zone = altitude_matched_control_zone(
            trail_metric, dem_arr, dem_transform, dem_crs
        )
        # altitude_matched_control_zone returns the plain annulus, area-for-
        # area, whenever it could not intersect the elevation band; a
        # strictly smaller area is the signature of a real intersection.
        matched = control_zone.area < annulus.area - 1.0

        mean_slope = sample_slope_along_trail(
            trail_metric, slope_deg, dem_transform, dem_crs
        )

        zones[asset_id] = {
            "local": local_zone,
            "control": control_zone,
            "matched": matched,
            "slope": mean_slope,
        }
    return zones


def _read_period_bands(clean_dir: Path):
    with rasterio.open(clean_dir / "clean_S2_EVI.tif") as ds:
        evi = ds.read(1)
        transform, crs = ds.transform, ds.crs
    with rasterio.open(clean_dir / "clean_S2_NDMI.tif") as ds:
        ndmi = ds.read(1)
    with rasterio.open(clean_dir / "clean_S2_NDVI.tif") as ds:
        ndvi = ds.read(1)
    with rasterio.open(clean_dir / "clean_S2_SCL.tif") as ds:
        scl = ds.read(1)

    valid = alpine_valid_mask(scl, AlpineSeason.SUMMER)
    valid &= np.isfinite(evi) & (evi != -9999.0)
    return evi, ndmi, ndvi, transform, crs, valid


def main() -> None:
    territory = get_territory("sierra_nevada")
    assets = build_sierra_nevada_territory()
    geoms = load_sierra_nevada_trail_geoms("sn")
    print(f"Real OAPN traces available for {len(geoms)}/{len(assets)} assets.")

    print("Fetching Copernicus DEM window for the full territory bbox …")
    dem_arr, dem_transform, dem_crs = fetch_dem_window(territory.bbox_wgs84)
    mean_lat = 0.5 * (territory.bbox_wgs84[1] + territory.bbox_wgs84[3])
    slope_deg, _ = compute_slope_aspect(
        dem_arr, metric_slope_transform(dem_transform, dem_crs, mean_lat)
    )

    zones = _build_zone_geometry(geoms, dem_arr, dem_transform, dem_crs, slope_deg)
    n_matched = sum(1 for z in zones.values() if z["matched"])
    print(
        f"Zone geometry built for {len(zones)} assets "
        f"({n_matched} with an altitude-matched control)."
    )

    monthly_local: dict[str, list[MonthlyZoneSignal]] = {aid: [] for aid in zones}
    monthly_control: dict[str, list[MonthlyZoneSignal]] = {aid: [] for aid in zones}

    _MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    for period_key, date_range, year, month in SUMMER_PERIODS:
        print(f"\n===== {period_key} ({date_range}) =====")
        manifest_path = _MANIFEST_DIR / f"manifest_{period_key}.csv"
        try:
            run_alpine_multitile_summer(
                bbox=territory.bbox_wgs84,
                mgrs_tiles=territory.mgrs_tiles,
                date_range=date_range,
                manifest_path=manifest_path,
            )
        except RuntimeError as exc:
            print(f"  No usable scene for {period_key}: {exc}")
            for aid in zones:
                monthly_local[aid].append(MonthlyZoneSignal(year, month, None, None))
                monthly_control[aid].append(MonthlyZoneSignal(year, month, None, None))
            continue

        evi, ndmi, ndvi, raster_transform, raster_crs, valid = _read_period_bands(_CLEAN)

        n_both = 0
        for asset_id, z in zones.items():
            local_evi, local_n = zonal_mean(
                evi, raster_transform, z["local"], _DEFAULT_BUFFER_CRS, raster_crs,
                valid_mask=valid,
            )
            local_ndmi, _ = zonal_mean(
                ndmi, raster_transform, z["local"], _DEFAULT_BUFFER_CRS, raster_crs,
                valid_mask=valid,
            )
            local_ndvi, _ = zonal_mean(
                ndvi, raster_transform, z["local"], _DEFAULT_BUFFER_CRS, raster_crs,
                valid_mask=valid,
            )
            control_evi, control_n = zonal_mean(
                evi, raster_transform, z["control"], _DEFAULT_BUFFER_CRS, raster_crs,
                valid_mask=valid,
            )
            control_ndmi, _ = zonal_mean(
                ndmi, raster_transform, z["control"], _DEFAULT_BUFFER_CRS, raster_crs,
                valid_mask=valid,
            )
            control_ndvi, _ = zonal_mean(
                ndvi, raster_transform, z["control"], _DEFAULT_BUFFER_CRS, raster_crs,
                valid_mask=valid,
            )

            monthly_local[asset_id].append(
                MonthlyZoneSignal(year, month, local_evi, local_ndmi, local_ndvi, local_n)
            )
            monthly_control[asset_id].append(
                MonthlyZoneSignal(year, month, control_evi, control_ndmi, control_ndvi, control_n)
            )
            if local_evi is not None and control_evi is not None:
                n_both += 1
        print(f"  Zonal EVI sampled for {n_both}/{len(zones)} assets (both zones valid)")

    outcomes = [
        execute_scm_attribution(
            asset_id,
            monthly_local[asset_id],
            monthly_control[asset_id],
            mean_slope_deg=z["slope"],
            control_altitude_matched=z["matched"],
        )
        for asset_id, z in zones.items()
    ]

    n_attributed = sum(1 for o in outcomes if o.attribution is not None)
    n_matched_used = sum(
        1 for o in outcomes if o.attribution is not None and o.control_altitude_matched
    )
    print(
        f"\nAttribution executed for {n_attributed}/{len(outcomes)} assets "
        f"({n_matched_used} with an altitude-matched control; "
        f"{len(outcomes) - n_attributed} fell back to NO_VALID_CONTROL)."
    )

    _COMMITTED.mkdir(parents=True, exist_ok=True)
    _write_json(outcomes, _JSON_OUT)
    print(f"Wrote {_JSON_OUT}")
    _write_csv(outcomes, _CSV_OUT)
    print(f"Wrote {_CSV_OUT}")


def _write_json(outcomes, out_path: Path) -> None:
    n_attributed = sum(1 for o in outcomes if o.attribution is not None)
    payload = {
        "n_assets": len(outcomes),
        "n_attributed": n_attributed,
        "n_no_valid_control": len(outcomes) - n_attributed,
        "assets": [
            {
                "asset_id": o.asset_id,
                "classification": o.classification,
                "control_altitude_matched": o.control_altitude_matched,
                "fallback_reason": o.fallback_reason,
                "attribution": (
                    None
                    if o.attribution is None
                    else {
                        "confidence": o.attribution.confidence,
                        "attribution_index": o.attribution.attribution_index,
                        "local_degradation": o.attribution.local_degradation,
                        "control_degradation": o.attribution.control_degradation,
                        "mean_slope_deg": o.attribution.mean_slope_deg,
                        "slope_gate_passed": o.attribution.slope_gate_passed,
                        "n_observations": o.attribution.n_observations,
                        "data_source": o.attribution.data_source,
                        "evidence_class": o.attribution.evidence_class.value,
                        "technical_rationale": o.attribution.technical_rationale,
                        "plain_language": o.attribution.plain_language,
                        "management_implication": o.attribution.management_implication,
                    }
                ),
            }
            for o in outcomes
        ],
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_csv(outcomes, out_path: Path) -> None:
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "asset_id", "classification", "control_altitude_matched",
            "attribution_index", "local_degradation", "control_degradation",
            "mean_slope_deg", "slope_gate_passed", "n_observations",
            "data_source", "evidence_class", "fallback_reason",
        ])
        for o in outcomes:
            a = o.attribution
            writer.writerow([
                o.asset_id,
                o.classification,
                o.control_altitude_matched,
                a.attribution_index if a else "",
                a.local_degradation if a else "",
                a.control_degradation if a else "",
                a.mean_slope_deg if a else "",
                a.slope_gate_passed if a else "",
                a.n_observations if a else "",
                a.data_source if a else "",
                a.evidence_class.value if a else "SIMULATED",
                o.fallback_reason or "",
            ])


if __name__ == "__main__":
    main()
