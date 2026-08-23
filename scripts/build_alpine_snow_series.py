"""
Build the Sierra Nevada winter snow series (issue #8): one winter
(Dec 2023 - Mar 2024), monthly cadence, instead of a single February 2024
scene.

For each month this re-runs the multi-tile mosaic from #7
(``etl_raster_processor.run_alpine_multitile``), co-registers the Copernicus
DEM to compute that month's regional snowline (reusing the pattern from
``scripts/alpine_winter_check.py``), and samples every asset's NDSI along its
real OAPN trace (``src.geospatial.asset_sampling``, the same helper
``build_alpine_asset_layers.py`` uses).

Writes two committed, dashboard-light outputs:
    clean_assets/sierra_nevada_snow_series.json   - regional snowline series
                                                     + bootstrap uncertainty
    clean_assets/sierra_nevada_snow_series.csv    - per-asset NDSI per month
                                                     + snowpack duration

Each period's tile/scene manifest is kept alongside the raw rasters under
clean_assets/snow_series/manifest_<period>.csv (small, committed — the
per-observation provenance issue #8 asks for).

Running (repeats the #7 multi-tile mosaic 4x — several minutes per month)::

    AWS_NO_SIGN_REQUEST=YES PYTHONPATH=. python scripts/build_alpine_snow_series.py
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.warp import Resampling as WarpResampling
from rasterio.warp import reproject, transform_bounds

from etl_raster_processor import run_alpine_multitile
from src.config.constants import NDSI_NIR_WATER_FLOOR
from src.config.territories import get as get_territory
from src.features.alpine_snow_series import (
    WinterPeriodObservation,
    asset_snowpack_duration,
    write_series_json,
)
from src.features.alpine_spectral import (
    AlpineSeason,
    alpine_valid_mask,
    compute_snowline_elevation,
    snow_mask,
)
from src.geospatial.asset_sampling import mean_over_points, sample_points_for_asset
from src.geospatial.geometry import fetch_dem_window
from src.geospatial.raster_mosaic import read_manifest_csv
from src.platform.alpine_trail_geoms import load_sierra_nevada_trail_geoms
from src.territorial.alpine_fixtures import build_sierra_nevada_territory

_ROOT = Path(__file__).resolve().parents[1]
_CLEAN = _ROOT / "data" / "clean_assets"
_COMMITTED = _ROOT / "clean_assets"
_MANIFEST_DIR = _COMMITTED / "snow_series"
_JSON_OUT = _COMMITTED / "sierra_nevada_snow_series.json"
_CSV_OUT = _COMMITTED / "sierra_nevada_snow_series.csv"

# One winter, monthly cadence (issue #8's pilot series).
WINTER_PERIODS: list[tuple[str, str]] = [
    ("2023-12", "2023-12-01/2023-12-31"),
    ("2024-01", "2024-01-01/2024-01-31"),
    ("2024-02", "2024-02-01/2024-02-29"),
    ("2024-03", "2024-03-01/2024-03-31"),
]


def _regional_snowline(clean_dir: Path) -> tuple[float | None, int, float]:
    """Co-register the DEM to the freshly-written mosaic and compute the
    snowline. Returns (snowline_m, n_snow_pixels, coverage_pct)."""
    with rasterio.open(clean_dir / "clean_S2_NDSI.tif") as ds:
        ndsi = ds.read(1)
        transform, crs, nodata = ds.transform, ds.crs, ds.nodata
    with rasterio.open(clean_dir / "clean_S2_B08_nir.tif") as ds:
        nir = ds.read(1).astype(np.float32) / 10000.0
    with rasterio.open(clean_dir / "clean_S2_SCL.tif") as ds:
        scl = ds.read(1)

    h, w = ndsi.shape
    nodata_val = nodata if nodata is not None else -9999.0
    valid_grid = ndsi != nodata_val
    coverage_pct = 100.0 * float(valid_grid.sum()) / valid_grid.size
    ndsi = np.where(valid_grid, ndsi, np.nan)

    bounds = rasterio.transform.array_bounds(h, w, transform)
    bbox_4326 = transform_bounds(crs, "EPSG:4326", *bounds)
    dem_arr, dem_transform, dem_crs = fetch_dem_window(bbox_4326)
    dem_on_grid = np.full((h, w), np.nan, dtype=np.float32)
    reproject(
        source=dem_arr,
        destination=dem_on_grid,
        src_transform=dem_transform,
        src_crs=dem_crs,
        dst_transform=transform,
        dst_crs=crs,
        resampling=WarpResampling.bilinear,
        src_nodata=None,
        dst_nodata=np.nan,
    )

    winter_valid = alpine_valid_mask(scl, AlpineSeason.WINTER)
    snow = snow_mask(ndsi, nir_array=nir, valid_mask=winter_valid)
    snowline = compute_snowline_elevation(
        ndsi, dem_on_grid, nir_array=nir, valid_mask=winter_valid
    )
    return snowline, int(snow.sum()), coverage_pct


def _sample_period_ndsi(clean_dir: Path, sample_pts: dict) -> dict[str, float]:
    ndsi_by_asset: dict[str, float] = {}
    with rasterio.open(clean_dir / "clean_S2_NDSI.tif") as nds:
        ndsi = nds.read(1)
        to_ndsi = Transformer.from_crs("EPSG:4326", nds.crs, always_xy=True)
        with rasterio.open(clean_dir / "clean_S2_B08_nir.tif") as nir_ds:
            nir = nir_ds.read(1).astype(np.float32) / 10000.0
        water_ok = nir > NDSI_NIR_WATER_FLOOR
        for asset_id, pts in sample_pts.items():
            val = mean_over_points(nds, ndsi, to_ndsi, pts, mask=water_ok)
            if val is not None:
                ndsi_by_asset[asset_id] = round(val, 4)
    return ndsi_by_asset


def main() -> None:
    territory = get_territory("sierra_nevada")
    assets = build_sierra_nevada_territory()
    geoms = load_sierra_nevada_trail_geoms("sn")
    sample_pts = {a.asset_id: sample_points_for_asset(a, geoms) for a in assets}
    _MANIFEST_DIR.mkdir(parents=True, exist_ok=True)

    observations: list[WinterPeriodObservation] = []
    ndsi_by_asset_by_period: dict[str, dict[str, float]] = {}

    for period_key, date_range in WINTER_PERIODS:
        print(f"\n===== {period_key} ({date_range}) =====")
        manifest_path = _MANIFEST_DIR / f"manifest_{period_key}.csv"
        try:
            run_alpine_multitile(
                bbox=territory.bbox_wgs84,
                mgrs_tiles=territory.mgrs_tiles,
                date_range=date_range,
                manifest_path=manifest_path,
            )
        except RuntimeError as exc:
            print(f"  No usable scene for {period_key}: {exc}")
            observations.append(
                WinterPeriodObservation(
                    period_key=period_key,
                    date_range=date_range,
                    mosaic_coverage_pct=0.0,
                    snowline_elevation_m=None,
                    n_snow_pixels=0,
                )
            )
            continue

        tiles = read_manifest_csv(manifest_path)
        snowline, n_snow, coverage_pct = _regional_snowline(_CLEAN)
        print(
            f"  snowline={snowline}  n_snow_px={n_snow}  coverage={coverage_pct:.1f}%"
        )
        observations.append(
            WinterPeriodObservation(
                period_key=period_key,
                date_range=date_range,
                mosaic_coverage_pct=coverage_pct,
                snowline_elevation_m=snowline,
                n_snow_pixels=n_snow,
                tiles=tiles,
            )
        )

        ndsi_by_asset_by_period[period_key] = _sample_period_ndsi(_CLEAN, sample_pts)
        n_sampled = len(ndsi_by_asset_by_period[period_key])
        print(f"  NDSI sampled for {n_sampled}/{len(assets)} assets")

    write_series_json(observations, _JSON_OUT)
    print(f"\nWrote {_JSON_OUT}")

    period_keys = [p for p, _ in WINTER_PERIODS]
    with open(_CSV_OUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["asset_id", *period_keys, "snowpack_duration_periods"])
        for a in assets:
            row_ndsi = [
                ndsi_by_asset_by_period.get(pk, {}).get(a.asset_id, "")
                for pk in period_keys
            ]
            ndsi_dict = {
                pk: ndsi_by_asset_by_period.get(pk, {}).get(a.asset_id)
                for pk in period_keys
            }
            duration = asset_snowpack_duration(ndsi_dict, period_keys)
            writer.writerow([a.asset_id, *row_ndsi, duration])
    print(f"Wrote {_CSV_OUT}")


if __name__ == "__main__":
    main()
