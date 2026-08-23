"""
Build the per-asset seasonal map layers for the Sierra Nevada dashboard.

Samples the winter NDSI raster and the Copernicus DEM at each asset's mapped
position and writes ``clean_assets/sierra_nevada_asset_layers.csv``, read at
runtime by ``src.platform.alpine_asset_layers.load_alpine_asset_layers``.

Inputs (generate the NDSI raster first)::

    python etl_raster_processor.py --territory sierra_nevada \
        --date-range "2024-02-01/2024-02-29"    # → data/clean_assets/clean_S2_NDSI.tif

Then::

    AWS_NO_SIGN_REQUEST=YES PROJ_DATA=<rasterio proj_data> \
        PYTHONPATH=. python scripts/build_alpine_asset_layers.py

NDSI is real (Sentinel-2, water-masked by the NIR floor). Slope is real
(Copernicus DEM-30). Both are sampled at the asset's APPROXIMATE mapped point
(municipality centroid + jitter), so they are indicative, not survey-grade.
Assets outside the NDSI scene footprint get no NDSI (partial coverage is honest).
"""
from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import rasterio
from pyproj import Transformer

from src.config.constants import NDSI_NIR_WATER_FLOOR
from src.geospatial.asset_sampling import mean_over_points, sample_points_for_asset
from src.geospatial.geometry import (
    compute_slope_aspect,
    fetch_dem_window,
    metric_slope_transform,
)
from src.platform.alpine_trail_geoms import load_sierra_nevada_trail_geoms
from src.territorial.alpine_fixtures import build_sierra_nevada_territory

_ROOT = Path(__file__).resolve().parents[1]
_NDSI_TIF = _ROOT / "data" / "clean_assets" / "clean_S2_NDSI.tif"
_NIR_TIF = _ROOT / "data" / "clean_assets" / "clean_S2_B08_nir.tif"
_OUT = _ROOT / "clean_assets" / "sierra_nevada_asset_layers.csv"


def main() -> None:
    assets = build_sierra_nevada_territory()
    geoms = load_sierra_nevada_trail_geoms("sn")
    n_real = sum(1 for a in assets if a.asset_id in geoms)
    print(f"Real OAPN traces available for {n_real}/{len(assets)} assets.")
    sample_pts = {a.asset_id: sample_points_for_asset(a, geoms) for a in assets}

    ndsi_by_asset: dict[str, float] = {}
    if _NDSI_TIF.exists():
        with rasterio.open(_NDSI_TIF) as nds:
            ndsi = nds.read(1)
            to_ndsi = Transformer.from_crs("EPSG:4326", nds.crs, always_xy=True)
            # Water mask from the NIR floor (snow stays reflective in NIR; water
            # does not) so lagunas do not colour as snow.
            water_ok = None
            if _NIR_TIF.exists():
                with rasterio.open(_NIR_TIF) as nir_ds:
                    nir = nir_ds.read(1).astype(np.float32) / 10000.0
                water_ok = nir > NDSI_NIR_WATER_FLOOR
            for asset_id, pts in sample_pts.items():
                val = mean_over_points(nds, ndsi, to_ndsi, pts, mask=water_ok)
                if val is not None:
                    ndsi_by_asset[asset_id] = round(val, 4)
        print(f"NDSI sampled for {len(ndsi_by_asset)}/{len(assets)} assets "
              f"(rest fall outside the scene footprint).")
    else:
        print(f"NDSI raster not found at {_NDSI_TIF}; skipping NDSI column.")

    # Slope from the Copernicus DEM over the bounding box of the sample points.
    all_pts = [p for pts in sample_pts.values() for p in pts]
    lats = [p[0] for p in all_pts]
    lons = [p[1] for p in all_pts]
    pad = 0.02
    bbox = (min(lons) - pad, min(lats) - pad, max(lons) + pad, max(lats) + pad)
    slope_by_asset: dict[str, float] = {}
    try:
        dem, dem_tr, dem_crs = fetch_dem_window(bbox)
        # DEM is geographic → metre-scale the transform for slope magnitude.
        mean_lat = 0.5 * (bbox[1] + bbox[3])
        metric_tr = metric_slope_transform(dem_tr, dem_crs, mean_lat)
        slope_deg, _ = compute_slope_aspect(dem, metric_tr)
        to_dem = Transformer.from_crs("EPSG:4326", dem_crs, always_xy=True)

        class _DemDS:  # minimal shim so sample_raster_mean can reuse .index/.nodata
            nodata = None

            @staticmethod
            def index(x, y):
                from affine import Affine
                t: Affine = dem_tr  # type: ignore[assignment]
                return int(round((y - t.f) / t.e)), int(round((x - t.c) / t.a))

        for asset_id, pts in sample_pts.items():
            val = mean_over_points(_DemDS, slope_deg, to_dem, pts)
            if val is not None:
                slope_by_asset[asset_id] = round(val, 2)
        print(f"Slope sampled for {len(slope_by_asset)}/{len(assets)} assets.")
    except Exception as exc:  # pragma: no cover - network/DEM failure
        print(f"DEM slope sampling failed ({exc}); skipping slope column.")

    _OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(_OUT, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["asset_id", "ndsi", "slope_deg", "ndsi_source", "dem_source"])
        for a in assets:
            writer.writerow([
                a.asset_id,
                ndsi_by_asset.get(a.asset_id, ""),
                slope_by_asset.get(a.asset_id, ""),
                "S2_NDSI_2024-02" if a.asset_id in ndsi_by_asset else "",
                "cop-dem-glo-30" if a.asset_id in slope_by_asset else "",
            ])
    print(f"Wrote {_OUT}")


if __name__ == "__main__":
    main()
