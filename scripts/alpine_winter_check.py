"""Validate the winter NDSI product end-to-end and render a snow map.

Reads the GeoTIFFs written by
    etl_raster_processor.py --territory sierra_nevada
co-registers the Copernicus DEM to the NDSI grid, applies the winter SCL mask
and the NIR water floor, and reports the snowline. Then renders a PNG.

Not part of the test suite — a one-off verification / visualization helper.

Running::

    PYTHONPATH=. python scripts/alpine_winter_check.py

The anonymous-S3 access needed for the Copernicus DEM is handled in code
(``_GDAL_COG_ENV["AWS_NO_SIGN_REQUEST"]``). On a machine whose ``PROJ_LIB`` /
``PROJ_DATA`` points at a *different* PROJ install (e.g. one bundled with
PostgreSQL), rasterio.warp here will raise a PROJ database-version error; export
``PROJ_DATA`` to rasterio's own ``proj_data`` directory first, as
``tests/integration/conftest.py`` does for the test suite.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import Resampling as WarpResampling
from rasterio.warp import reproject, transform_bounds

from src.features.alpine_spectral import (
    AlpineSeason,
    alpine_valid_mask,
    compute_snowline_elevation,
    snow_mask,
)
from src.geospatial.geometry import fetch_dem_window

CLEAN = Path("data/clean_assets")
OUT_PNG = Path("data/outputs/sierra_nevada_winter_ndsi.png")


def _read(path: Path):
    with rasterio.open(path) as ds:
        return ds.read(1), ds.transform, ds.crs, ds.nodata


def main() -> None:
    ndsi, transform, crs, ndsi_nodata = _read(CLEAN / "clean_S2_NDSI.tif")
    nir_dn, _, _, _ = _read(CLEAN / "clean_S2_B08_nir.tif")
    scl, _, _, _ = _read(CLEAN / "clean_S2_SCL.tif")
    h, w = ndsi.shape
    print(f"NDSI grid: {w}x{h} px  crs={crs.to_string()}")

    # Stored B08 is Sentinel-2 DN (reflectance x 10000); the NIR water floor is
    # defined in [0,1] reflectance, so scale before use.
    nir = nir_dn.astype(np.float32) / 10000.0

    # Reference-band nodata came through NDSI as -9999.0
    ndsi = np.where(ndsi == (ndsi_nodata if ndsi_nodata is not None else -9999.0),
                    np.nan, ndsi)

    # ── Co-register the Copernicus DEM to the NDSI grid ──────────────────────
    bounds = rasterio.transform.array_bounds(h, w, transform)  # (l, b, r, t)
    bbox_4326 = transform_bounds(crs, "EPSG:4326", *bounds)
    print(f"AOI (4326): {tuple(round(v, 4) for v in bbox_4326)}")
    dem_arr, dem_transform, dem_crs = fetch_dem_window(bbox_4326)
    print(f"DEM window: {dem_arr.shape[1]}x{dem_arr.shape[0]} px  "
          f"elev {np.nanmin(dem_arr):.0f}–{np.nanmax(dem_arr):.0f} m")

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

    # ── Winter mask + snow classification ────────────────────────────────────
    valid = alpine_valid_mask(scl, AlpineSeason.WINTER)
    snow = snow_mask(ndsi, nir_array=nir, valid_mask=valid)
    snow_no_floor = snow_mask(ndsi, valid_mask=valid)  # NDSI-only, includes water

    n_valid = int(valid.sum())
    print("\n── Winter snow classification ──")
    print(f"valid pixels (winter SCL mask):     {n_valid:,} "
          f"({n_valid / (h * w):.1%} of grid)")
    print(f"snow candidates (NDSI>=0.40, +mask): {int(snow_no_floor.sum()):,}")
    print(f"snow after NIR water floor:          {int(snow.sum()):,} "
          f"(rejected {int(snow_no_floor.sum() - snow.sum()):,} water/dark px)")

    snow_elev = dem_on_grid[snow & np.isfinite(dem_on_grid)]
    if snow_elev.size:
        print("\n── Snow elevation distribution (m.a.s.l.) ──")
        for p in (5, 25, 50, 75, 95):
            print(f"  p{p:02d}: {np.percentile(snow_elev, p):6.0f} m")
        print(f"  min {snow_elev.min():.0f} · max {snow_elev.max():.0f} · "
              f"mean {snow_elev.mean():.0f}")

    snowline = compute_snowline_elevation(ndsi, dem_on_grid, nir_array=nir,
                                          valid_mask=valid)
    print(f"\nSNOWLINE (p5 of snow-pixel elevations): "
          f"{snowline:.0f} m.a.s.l." if snowline is not None else "SNOWLINE: None")

    # ── Render ───────────────────────────────────────────────────────────────
    _render(ndsi, snow, dem_on_grid, snowline)


def _render(ndsi, snow, dem, snowline) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap

    # Downsample for a light PNG
    step = max(1, min(ndsi.shape) // 900)
    nd = ndsi[::step, ::step]
    sn = snow[::step, ::step]
    dm = dem[::step, ::step]

    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(15, 6), constrained_layout=True)

    im0 = axes[0].imshow(nd, cmap="RdBu", vmin=-1, vmax=1)
    axes[0].set_title("NDSI — Sierra Nevada · 2024-02-02 (30SVG)")
    axes[0].axis("off")
    fig.colorbar(im0, ax=axes[0], shrink=0.7, label="NDSI")

    # Hillshade-ish elevation backdrop + snow overlay
    axes[1].imshow(dm, cmap="terrain")
    snow_cmap = ListedColormap([(0, 0, 0, 0), (0.10, 0.45, 0.95, 0.9)])
    axes[1].imshow(sn.astype(int), cmap=snow_cmap, vmin=0, vmax=1)
    title = "Nieve clasificada (NDSI≥0.40 + suelo NIR) sobre elevación"
    if snowline is not None:
        title += f"\ncota de nieve ≈ {snowline:.0f} m s.n.m."
    axes[1].set_title(title)
    axes[1].axis("off")

    fig.suptitle("SNTO Alpine Edition — modo invierno (innivación)",
                 fontsize=14, fontweight="bold")
    fig.savefig(OUT_PNG, dpi=110)
    print(f"\nPNG escrito: {OUT_PNG}")


if __name__ == "__main__":
    main()
