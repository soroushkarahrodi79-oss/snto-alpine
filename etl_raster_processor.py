"""
SNTO ETL Phase 0 -- Sentinel-2 Raster Processor  [STAC / COG Edition]
======================================================================
Pilot Territory: Sierra del Rincón Biosphere Reserve, Madrid, Spain

Replaces the local-ZIP workflow with a fully cloud-native approach:

  1. Queries AWS Earth Search (public STAC v1, no auth) for the least-cloudy
     Sentinel-2 L2A scene covering the study bbox in the requested date window.
  2. Resolves the COG href for each required band (B04 Red 10 m, B08 NIR 10 m,
     B11 SWIR 20 m) directly from the STAC item assets.
  3. Streams ONLY the study-area window from each COG via rasterio windowed-read
     over HTTPS — no full-file download, no temporary extraction.
  4. Resamples B11 from 20 m to 10 m on-the-fly using rasterio's out_shape.
  5. Computes NDVI and NDMI, writes 5 production-ready GeoTIFFs to clean_assets/.

ENV overrides (optional):
  SNTO_S2_DATE_RANGE    e.g. "2022-06-01/2022-09-30"   default: 2023-07-01/2023-09-30
  SNTO_S2_CLOUD_PCT     e.g. "15"                       default: 20

Inputs  : STAC API — https://earth-search.aws.element84.com/v1
Outputs : data/clean_assets/clean_S2_B04_red.tif
          data/clean_assets/clean_S2_B08_nir.tif
          data/clean_assets/clean_S2_B11_swir.tif
          data/clean_assets/clean_S2_NDVI.tif
          data/clean_assets/clean_S2_NDMI.tif
"""
from __future__ import annotations

import argparse
import io
import os
import sys
from pathlib import Path

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.transform import from_bounds as transform_from_bounds
from rasterio.windows import bounds as window_bounds
from rasterio.windows import from_bounds as window_from_bounds

from src.geospatial.raster_mosaic import (
    TileManifestEntry,
    coverage_fraction,
    merge_first_valid,
    write_manifest_csv,
)

# pystac-client is a runtime dependency only needed when actually calling the
# STAC API.  The lazy import lets the module be imported in test environments
# where the package may not be installed, while still failing explicitly at
# call time if the library is missing.
try:
    from pystac_client import Client
except ImportError:  # pragma: no cover
    Client = None  # type: ignore[assignment,misc]

SEP = "=" * 72
DIV = "-" * 72

PROJECT_ROOT = Path(__file__).parent
CLEAN_DIR    = PROJECT_ROOT / "data" / "clean_assets"

# ── Study area ────────────────────────────────────────────────────────────────
BBOX_4326: tuple[float, float, float, float] = (-3.65, 41.05, -3.30, 41.20)  # W S E N

# ── STAC / scene settings (overridable via env) ───────────────────────────────
STAC_URL      = "https://earth-search.aws.element84.com/v1"
COLLECTION    = "sentinel-2-l2a"
DATE_RANGE    = os.environ.get("SNTO_S2_DATE_RANGE", "2023-07-01/2023-09-30")
MAX_CLOUD_PCT = float(os.environ.get("SNTO_S2_CLOUD_PCT", "20"))

# Asset key lookup order (AWS Earth Search keys listed first; MPC keys as fallback)
_KEYS_B04: tuple[str, ...] = ("red",   "B04")
_KEYS_B08: tuple[str, ...] = ("nir",   "nir08", "B08")   # catalogue-dependent
_KEYS_B11: tuple[str, ...] = ("swir16", "B11")
# Alpine Edition additions: green drives NDSI, SCL drives the snow-permissive mask
_KEYS_B03: tuple[str, ...] = ("green", "B03")
_KEYS_SCL: tuple[str, ...] = ("scl",   "SCL")

# GDAL environment hints that activate HTTP range-request optimisation for COGs
_GDAL_COG_ENV: dict[str, str] = {
    "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES",
    "GDAL_HTTP_MULTIPLEX":               "YES",
    "GDAL_HTTP_VERSION":                 "2",
    "GDAL_DISABLE_READDIR_ON_OPEN":      "EMPTY_DIR",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS":  ".tif,.tiff",
}


# ── STAC helpers ──────────────────────────────────────────────────────────────

def _item_mgrs_tile(item: object) -> str | None:
    """Best-effort MGRS tile code for a STAC item (e.g. ``"30SVF"``).

    AWS Earth Search's ``sentinel-2-l2a`` items carry it as ``grid:code``
    (``"MGRS-30SVF"``), not the ``s2:mgrs_tile`` property some other
    catalogues use; fall back to parsing the item id (``S2B_30SVF_...``).
    """
    props = item.properties  # type: ignore[attr-defined]
    tile = props.get("s2:mgrs_tile")
    if tile:
        return tile
    grid_code = props.get("grid:code", "")
    if grid_code.startswith("MGRS-"):
        return grid_code[len("MGRS-"):]
    parts = str(item.id).split("_")  # type: ignore[attr-defined]
    if len(parts) > 1 and len(parts[1]) == 5:
        return parts[1]
    return None


def search_best_item(
    bbox: tuple[float, float, float, float],
    date_range: str,
    max_cloud_pct: float,
    stac_url: str = STAC_URL,
    collection: str = COLLECTION,
    mgrs_tile: str | None = None,
) -> object:
    """Return the least-cloudy S2 L2A STAC item intersecting *bbox*.

    Items are filtered server-side by cloud cover then sorted client-side to
    avoid catalogue-specific *sortby* syntax differences.

    Args:
        mgrs_tile: when set (e.g. ``"30SVF"``), restrict to items from that
            single MGRS tile — needed when *bbox* spans several tiles and
            each one must be searched/mosaicked separately (issue #7).
    """
    if Client is None:  # pragma: no cover
        raise ImportError("pystac-client is required: pip install pystac-client")
    catalog = Client.open(stac_url)
    search = catalog.search(
        collections=[collection],
        bbox=list(bbox),
        datetime=date_range,
        query={"eo:cloud_cover": {"lt": max_cloud_pct}},
        max_items=50,
    )
    items = list(search.items())
    if mgrs_tile is not None:
        items = [it for it in items if _item_mgrs_tile(it) == mgrs_tile]
    if not items:
        scope = f", tile={mgrs_tile}" if mgrs_tile else ""
        raise RuntimeError(
            f"No S2 L2A scene found for bbox={bbox}, dates={date_range}, "
            f"cloud < {max_cloud_pct}%{scope}. "
            "Widen DATE_RANGE or raise SNTO_S2_CLOUD_PCT."
        )
    items.sort(key=lambda it: float(it.properties.get("eo:cloud_cover", 100)))
    return items[0]


def resolve_asset_href(item: object, *candidate_keys: str) -> str:
    """Return the href for the first matching asset key in *item*.

    Raises KeyError listing available assets when none of *candidate_keys* match.
    """
    for key in candidate_keys:
        asset = item.assets.get(key)  # type: ignore[union-attr]
        if asset is not None:
            return asset.href
    available = list(item.assets.keys())  # type: ignore[union-attr]
    raise KeyError(
        f"None of {candidate_keys!r} found in STAC item '{item.id}'. "  # type: ignore[union-attr]
        f"Available assets: {available}"
    )


# ── COG windowed-read ─────────────────────────────────────────────────────────

def bbox_to_native_crs(
    bbox_4326: tuple[float, float, float, float],
    target_crs: object,
) -> tuple[float, float, float, float]:
    """Reproject a (W, S, E, N) bbox from EPSG:4326 into *target_crs*."""
    t = Transformer.from_crs(4326, target_crs, always_xy=True)
    xmin, ymin = t.transform(bbox_4326[0], bbox_4326[1])
    xmax, ymax = t.transform(bbox_4326[2], bbox_4326[3])
    return xmin, ymin, xmax, ymax


def read_cog_window(
    href: str,
    bbox_4326: tuple[float, float, float, float],
    out_shape: tuple[int, int] | None = None,
    resampling: Resampling = Resampling.bilinear,
    boundless: bool = False,
) -> tuple[np.ndarray, object, object]:
    """Stream a windowed read from a COG without downloading the full file.

    No data is written to disk.  Only the HTTP ranges that cover the study
    window are fetched, which corresponds to a small fraction of the full tile.

    Args:
        href:       HTTPS URL pointing to a Cloud-Optimised GeoTIFF.
        bbox_4326:  Study-area bounds (W, S, E, N) in EPSG:4326.
        out_shape:  (H, W) target; rasterio resamples on-the-fly when set.
                    Pass the reference (H, W) to coerce a 20 m band to 10 m.
        resampling: Algorithm used when *out_shape* differs from native size.
        boundless:  when True, *bbox_4326* may extend beyond this dataset's
            own extent — the out-of-tile area reads as 0 (nodata) instead of
            raising/clipping. Needed to read one MGRS tile against the
            territory's full multi-tile bbox before mosaicking (issue #7).

    Returns:
        Tuple of (array[H, W] uint16, affine_transform, rasterio.CRS).
    """
    with rasterio.Env(**_GDAL_COG_ENV):
        with rasterio.open(href) as ds:
            xmin, ymin, xmax, ymax = bbox_to_native_crs(bbox_4326, ds.crs)
            win = window_from_bounds(xmin, ymin, xmax, ymax, ds.transform)

            read_kwargs: dict = {"window": win}
            if out_shape is not None:
                read_kwargs["out_shape"]   = (1, out_shape[0], out_shape[1])
                read_kwargs["resampling"]  = resampling
            if boundless:
                read_kwargs["boundless"]  = True
                read_kwargs["fill_value"] = 0

            data = ds.read(1, **read_kwargs)

            # Derive the output affine transform from the geographic window bounds
            # and the actual pixel dimensions (which may differ from the native
            # window size when out_shape is given).
            geo_bounds = window_bounds(win, ds.transform)   # left, bottom, right, top
            h, w = data.shape
            out_transform = transform_from_bounds(*geo_bounds, w, h)
            crs = ds.crs

    return data, out_transform, crs


# ── Spectral indices ──────────────────────────────────────────────────────────

def compute_normalised_index(
    band_a: np.ndarray,
    band_b: np.ndarray,
) -> np.ndarray:
    """Return (A – B) / (A + B) as float32 with zero-denominator guard.

    np.errstate suppresses the RuntimeWarning that would otherwise appear for
    zero-denominator pixels before np.where applies the mask.
    """
    a = band_a.astype(np.float32)
    b = band_b.astype(np.float32)
    denom = a + b
    with np.errstate(divide="ignore", invalid="ignore"):
        result = np.where(denom == 0.0, 0.0, (a - b) / denom)
    return result.astype(np.float32)


# ── Writer ────────────────────────────────────────────────────────────────────

def write_tif(out_path: Path, data: np.ndarray, profile: dict) -> None:
    """Write a single-band 2-D array to a GeoTIFF."""
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(data[np.newaxis])


# ── Orchestration ─────────────────────────────────────────────────────────────

def run(
    bbox: tuple[float, float, float, float] = BBOX_4326,
    date_range: str = DATE_RANGE,
    max_cloud_pct: float = MAX_CLOUD_PCT,
    clean_dir: Path = CLEAN_DIR,
    alpine: bool = False,
) -> dict[str, Path]:
    """Full ETL run.  Returns a mapping of output name → Path for callers.

    Args:
        bbox: study area (W, S, E, N) in EPSG:4326.
        date_range: STAC ``datetime`` filter, e.g. ``"2024-01-01/2024-03-31"``.
        max_cloud_pct: maximum scene cloud cover accepted.
        clean_dir: output directory for the GeoTIFFs.
        alpine: when True, additionally streams B03 (green) and SCL, computes
            NDSI and writes ``clean_S2_NDSI.tif`` / ``clean_S2_SCL.tif``.
            Required for the Alpine Edition winter mode — NDSI needs green and
            SWIR, and the snow-permissive mask needs the raw SCL class codes
            (see ``src/features/alpine_spectral.py``).  Default False keeps the
            PNSG output set unchanged.
    """
    clean_dir.mkdir(parents=True, exist_ok=True)

    # Step 1 — discover scene
    print("  Searching STAC catalogue …")
    item = search_best_item(bbox, date_range, max_cloud_pct)
    cloud_pct = item.properties.get("eo:cloud_cover", "?")
    print(f"  Selected item : {item.id}")
    print(f"  Date          : {item.datetime}")
    print(f"  Cloud cover   : {cloud_pct} %")
    print()

    # Step 2 — resolve COG hrefs
    href_b04 = resolve_asset_href(item, *_KEYS_B04)
    href_b08 = resolve_asset_href(item, *_KEYS_B08)
    href_b11 = resolve_asset_href(item, *_KEYS_B11)
    print("  COG hrefs:")
    print(f"    B04 : …{href_b04[-70:]}")
    print(f"    B08 : …{href_b08[-70:]}")
    print(f"    B11 : …{href_b11[-70:]}")
    print()

    # Step 3 — stream B04 (10 m, reference grid)
    print("  Streaming B04 (Red, 10 m) …")
    b04_arr, ref_transform, ref_crs = read_cog_window(href_b04, bbox)
    ref_h, ref_w = b04_arr.shape
    print(f"  B04 clipped shape : {ref_h} × {ref_w} px @ 10 m")

    # Step 4 — stream B08 (10 m, same native grid as B04)
    print("  Streaming B08 (NIR, 10 m) …")
    b08_arr, _, _ = read_cog_window(href_b08, bbox)
    print(f"  B08 clipped shape : {b08_arr.shape[0]} × {b08_arr.shape[1]} px")

    # Step 5 — stream B11 (20 m), resample to 10 m on-the-fly
    print("  Streaming B11 (SWIR, 20 m) → resampling to 10 m on-the-fly …")
    b11_arr, _, _ = read_cog_window(
        href_b11, bbox,
        out_shape=(ref_h, ref_w),
        resampling=Resampling.bilinear,
    )
    print(f"  B11 resampled     : {b11_arr.shape[0]} × {b11_arr.shape[1]} px")
    print()

    # Step 5b — Alpine Edition: green (10 m) + SCL (20 m) for NDSI and masking
    b03_arr = scl_arr = None
    if alpine:
        href_b03 = resolve_asset_href(item, *_KEYS_B03)
        href_scl = resolve_asset_href(item, *_KEYS_SCL)
        print("  [alpine] Streaming B03 (Green, 10 m) …")
        b03_arr, _, _ = read_cog_window(href_b03, bbox)
        print(f"  B03 clipped shape : {b03_arr.shape[0]} × {b03_arr.shape[1]} px")

        # SCL carries class CODES, not a continuous quantity — it must be
        # resampled with nearest neighbour. Bilinear would invent classes that
        # do not exist (e.g. averaging 4=vegetation and 6=water into 5=rock).
        print("  [alpine] Streaming SCL (20 m) → nearest-neighbour to 10 m …")
        scl_arr, _, _ = read_cog_window(
            href_scl, bbox,
            out_shape=(ref_h, ref_w),
            resampling=Resampling.nearest,
        )
        print(f"  SCL resampled     : {scl_arr.shape[0]} × {scl_arr.shape[1]} px")
        print()

    # Step 6 — spectral indices
    print("  Computing NDVI = (B08 – B04) / (B08 + B04) …")
    ndvi = compute_normalised_index(b08_arr, b04_arr)

    print("  Computing NDMI = (B08 – B11) / (B08 + B11) …")
    ndmi = compute_normalised_index(b08_arr, b11_arr)

    ndsi = None
    if alpine:
        print("  [alpine] Computing NDSI = (B03 – B11) / (B03 + B11) …")
        ndsi = compute_normalised_index(b03_arr, b11_arr)
    print()

    # Step 7 — write outputs
    band_profile: dict = {
        "driver":    "GTiff",
        "dtype":     "uint16",
        "width":     ref_w,
        "height":    ref_h,
        "count":     1,
        "crs":       ref_crs,
        "transform": ref_transform,
        "compress":  "lzw",
    }
    index_profile: dict = {**band_profile, "dtype": "float32", "nodata": -9999.0}

    outputs: list[tuple[str, np.ndarray, dict]] = [
        ("clean_S2_B04_red.tif",  b04_arr.astype(np.uint16),                    band_profile),
        ("clean_S2_B08_nir.tif",  b08_arr.astype(np.uint16),                    band_profile),
        # clip before uint16 cast: bilinear resampling can produce tiny negatives
        ("clean_S2_B11_swir.tif", np.clip(b11_arr, 0, 65535).astype(np.uint16), band_profile),
        ("clean_S2_NDVI.tif",     ndvi,                                           index_profile),
        ("clean_S2_NDMI.tif",     ndmi,                                           index_profile),
    ]

    if alpine:
        # SCL stays uint8: they are class codes, and writing them as float
        # would invite exactly the interpolation this pipeline avoids.
        scl_profile: dict = {**band_profile, "dtype": "uint8"}
        outputs.extend([
            ("clean_S2_B03_green.tif", b03_arr.astype(np.uint16), band_profile),
            ("clean_S2_SCL.tif",       scl_arr.astype(np.uint8),  scl_profile),
            ("clean_S2_NDSI.tif",      ndsi,                      index_profile),
        ])

    result_paths: dict[str, Path] = {}
    print("  Writing GeoTIFFs:")
    for fname, data, profile in outputs:
        out_path = clean_dir / fname
        write_tif(out_path, data, profile)
        size_mb = out_path.stat().st_size / 1_048_576
        print(f"    {fname:<30}  {size_mb:5.1f} MB")
        result_paths[fname] = out_path
    print()

    # Step 8 — summary statistics
    print(DIV)
    print("  INDEX STATISTICS")
    print(DIV)
    valid_mask = (b04_arr > 0) | (b08_arr > 0)
    valid_ndvi = ndvi[valid_mask]
    valid_ndmi = ndmi[valid_mask]
    print(
        f"  NDVI  min={ndvi.min():.4f}  max={ndvi.max():.4f}"
        f"  mean={valid_ndvi.mean():.4f}  (valid px: {len(valid_ndvi):,})"
    )
    print(
        f"  NDMI  min={ndmi.min():.4f}  max={ndmi.max():.4f}"
        f"  mean={valid_ndmi.mean():.4f}  (valid px: {len(valid_ndmi):,})"
    )
    if alpine and ndsi is not None:
        valid_ndsi = ndsi[valid_mask]
        snow_px = int((valid_ndsi >= 0.40).sum())
        print(
            f"  NDSI  min={ndsi.min():.4f}  max={ndsi.max():.4f}"
            f"  mean={valid_ndsi.mean():.4f}  (valid px: {len(valid_ndsi):,})"
        )
        print(
            f"        snow candidates (NDSI ≥ 0.40): {snow_px:,} px "
            f"({snow_px / max(len(valid_ndsi), 1):.1%})"
        )
    print()
    print("  Note: NDVI mean ~0.30–0.45 expected for summer Mediterranean landscape.")
    if alpine:
        print(
            "  Note: NDSI ≥ 0.40 marks snow CANDIDATES only. Water shares that "
            "signature —\n"
            "        apply the NIR floor via src.features.alpine_spectral."
            "is_snow_pixel()."
        )
    print()
    print(DIV)
    print(f"  Done. {len(outputs)} GeoTIFFs written to: {clean_dir}")

    return result_paths


# ── Alpine Edition: multi-tile winter mosaic (issue #7) ───────────────────────

def run_alpine_multitile(
    bbox: tuple[float, float, float, float],
    mgrs_tiles: tuple[str, ...],
    date_range: str = DATE_RANGE,
    max_cloud_pct: float = MAX_CLOUD_PCT,
    clean_dir: Path = CLEAN_DIR,
    manifest_path: Path | None = None,
) -> dict[str, Path]:
    """Winter NDSI mosaic across every MGRS tile in *mgrs_tiles*.

    A single STAC item only covers part of a multi-tile territory (Sierra
    Nevada's massif spans 30SVF/30SWF/30SVG/30SWG), which left 10/53 assets
    without real NDSI. This searches each tile independently for its own
    least-cloud winter scene, reads B03/B08/B11/SCL for every tile against
    the *shared* full-bbox grid (``boundless=True`` fills the out-of-tile
    area with 0/nodata), then mosaics tile-by-tile with
    :func:`src.geospatial.raster_mosaic.merge_first_valid` — tiles are
    merged in ascending cloud-cover order so a clearer scene wins any overlap
    at tile boundaries. Writes the same GeoTIFF set as :func:`run` (alpine
    mode) plus the tile/scene/date/coverage manifest issue #7 asks for.

    Args:
        bbox: full territory bbox (W, S, E, N) in EPSG:4326 — spans all tiles.
        mgrs_tiles: MGRS tile codes to search and mosaic, e.g.
            ``("30SVF", "30SWF", "30SVG", "30SWG")``.
        manifest_path: override for the committed manifest CSV; defaults to
            ``clean_assets/sierra_nevada_ndsi_manifest.csv`` at the repo root
            (sibling of the other committed Alpine Edition data files, not
            the gitignored raster output directory).
    """
    clean_dir.mkdir(parents=True, exist_ok=True)

    ref_h = ref_w = None
    ref_transform = ref_crs = None
    b03_tiles: list[np.ndarray] = []
    b08_tiles: list[np.ndarray] = []
    b11_tiles: list[np.ndarray] = []
    scl_tiles: list[np.ndarray] = []
    manifest: list[TileManifestEntry] = []

    print(f"  Searching {len(mgrs_tiles)} MGRS tiles: {', '.join(mgrs_tiles)}")
    for tile in mgrs_tiles:
        print(f"  [{tile}] searching STAC …")
        item = search_best_item(bbox, date_range, max_cloud_pct, mgrs_tile=tile)
        cloud_pct = float(item.properties.get("eo:cloud_cover", 100))
        print(f"  [{tile}] {item.id}  date={item.datetime}  cloud={cloud_pct:.1f}%")

        href_b03 = resolve_asset_href(item, *_KEYS_B03)
        href_b08 = resolve_asset_href(item, *_KEYS_B08)
        href_b11 = resolve_asset_href(item, *_KEYS_B11)
        href_scl = resolve_asset_href(item, *_KEYS_SCL)

        b03, tr, crs = read_cog_window(href_b03, bbox, boundless=True)
        if ref_h is None:
            ref_h, ref_w = b03.shape
            ref_transform, ref_crs = tr, crs
        elif b03.shape != (ref_h, ref_w):
            # Tiles can land on slightly different 10 m grids; snap this
            # tile's read onto the reference grid established by the first.
            b03, _, _ = read_cog_window(
                href_b03, bbox, out_shape=(ref_h, ref_w), boundless=True
            )

        b08, _, _ = read_cog_window(
            href_b08, bbox, out_shape=(ref_h, ref_w), boundless=True
        )
        b11, _, _ = read_cog_window(
            href_b11, bbox, out_shape=(ref_h, ref_w),
            resampling=Resampling.bilinear, boundless=True,
        )
        scl, _, _ = read_cog_window(
            href_scl, bbox, out_shape=(ref_h, ref_w),
            resampling=Resampling.nearest, boundless=True,
        )

        cov = coverage_fraction(b03, nodata=0)
        print(f"  [{tile}] valid coverage of the full bbox grid: {cov:.1%}")
        manifest.append(TileManifestEntry(
            tile=tile,
            scene_id=str(item.id),
            date=str(item.datetime)[:10],
            cloud_pct=cloud_pct,
            coverage_pct=cov * 100,
        ))

        b03_tiles.append(b03.astype(np.uint16))
        b08_tiles.append(b08.astype(np.uint16))
        b11_tiles.append(np.clip(b11, 0, 65535).astype(np.uint16))
        scl_tiles.append(scl.astype(np.uint8))
        print()

    # Merge in ascending cloud-cover order: a clearer scene wins any pixel two
    # tiles both claim (edge overlap), everything else fills honest gaps.
    order = sorted(range(len(mgrs_tiles)), key=lambda i: manifest[i].cloud_pct)
    b03_mosaic = merge_first_valid([b03_tiles[i] for i in order], nodata=0)
    b08_mosaic = merge_first_valid([b08_tiles[i] for i in order], nodata=0)
    b11_mosaic = merge_first_valid([b11_tiles[i] for i in order], nodata=0)
    scl_mosaic = merge_first_valid([scl_tiles[i] for i in order], nodata=0)
    mosaic_cov = coverage_fraction(b03_mosaic, nodata=0)
    print(f"  Combined mosaic coverage of the full bbox: {mosaic_cov:.1%}")

    print("  Computing NDSI = (B03 – B11) / (B03 + B11) over the mosaic …")
    ndsi = compute_normalised_index(b03_mosaic, b11_mosaic)
    # A pixel no tile covers is not a real 0.0 NDSI value — mark it nodata
    # explicitly rather than let it read as a (wrong) valid measurement.
    uncovered = b03_mosaic == 0
    ndsi[uncovered] = -9999.0
    print()

    band_profile: dict = {
        "driver": "GTiff", "dtype": "uint16", "width": ref_w, "height": ref_h,
        "count": 1, "crs": ref_crs, "transform": ref_transform, "compress": "lzw",
    }
    scl_profile: dict = {**band_profile, "dtype": "uint8"}
    index_profile: dict = {**band_profile, "dtype": "float32", "nodata": -9999.0}

    outputs: list[tuple[str, np.ndarray, dict]] = [
        ("clean_S2_B03_green.tif", b03_mosaic, band_profile),
        ("clean_S2_B08_nir.tif",   b08_mosaic, band_profile),
        ("clean_S2_B11_swir.tif",  b11_mosaic, band_profile),
        ("clean_S2_SCL.tif",       scl_mosaic, scl_profile),
        ("clean_S2_NDSI.tif",      ndsi,       index_profile),
    ]
    result_paths: dict[str, Path] = {}
    print("  Writing mosaicked GeoTIFFs:")
    for fname, data, profile in outputs:
        out_path = clean_dir / fname
        write_tif(out_path, data, profile)
        size_mb = out_path.stat().st_size / 1_048_576
        print(f"    {fname:<30}  {size_mb:5.1f} MB")
        result_paths[fname] = out_path
    print()

    manifest_out = manifest_path or (
        PROJECT_ROOT / "clean_assets" / "sierra_nevada_ndsi_manifest.csv"
    )
    write_manifest_csv(manifest, manifest_out)
    print(f"  Manifest written to {manifest_out}")
    result_paths["manifest"] = manifest_out

    print(DIV)
    print(f"  Done. {len(outputs)} GeoTIFFs + manifest written.")

    return result_paths


def main() -> None:
    # UTF-8 output for Windows terminals with non-Unicode code pages
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="SNTO Sentinel-2 STAC/COG raster processor."
    )
    parser.add_argument(
        "--territory",
        default=None,
        help=(
            "Territory key from src/config/territories.py (e.g. sierra_nevada). "
            "Overrides the default bbox."
        ),
    )
    parser.add_argument(
        "--alpine",
        action="store_true",
        help=(
            "Alpine Edition mode: also stream B03 + SCL and write NDSI. "
            "Implied by --territory sierra_nevada."
        ),
    )
    parser.add_argument(
        "--date-range",
        default=DATE_RANGE,
        help='STAC datetime filter, e.g. "2024-01-01/2024-03-31".',
    )
    args = parser.parse_args()

    bbox = BBOX_4326
    label = "Sierra del Rincón Biosphere Reserve, Madrid, Spain"
    alpine = args.alpine
    mgrs_tiles: tuple[str, ...] = ()

    if args.territory:
        from src.config.territories import get as get_territory

        territory = get_territory(args.territory)
        bbox = territory.bbox_wgs84
        label = f"{territory.display_name} ({territory.region})"
        if args.territory == "sierra_nevada":
            alpine = True
        mgrs_tiles = territory.mgrs_tiles

    print(SEP)
    print("  SNTO ETL -- Sentinel-2 Raster Processor  [STAC / COG Edition]")
    print(f"  Pilot: {label}")
    print(f"  Bbox (WGS84) : {bbox}")
    print(f"  STAC URL     : {STAC_URL}")
    print(f"  Date range   : {args.date_range}  (cloud < {MAX_CLOUD_PCT} %)")
    print(f"  Output       : {CLEAN_DIR}")
    if len(mgrs_tiles) > 1:
        print(f"  Mode         : ALPINE multi-tile mosaic ({', '.join(mgrs_tiles)})")
        print(SEP)
        print()
        run_alpine_multitile(bbox=bbox, mgrs_tiles=mgrs_tiles, date_range=args.date_range)
    else:
        print(f"  Mode         : {'ALPINE (NDSI + SCL)' if alpine else 'standard'}")
        print(SEP)
        print()
        run(bbox=bbox, date_range=args.date_range, alpine=alpine)
    print(SEP)


if __name__ == "__main__":
    main()
