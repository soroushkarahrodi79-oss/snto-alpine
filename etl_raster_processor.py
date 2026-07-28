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

def search_best_item(
    bbox: tuple[float, float, float, float],
    date_range: str,
    max_cloud_pct: float,
    stac_url: str = STAC_URL,
    collection: str = COLLECTION,
) -> object:
    """Return the least-cloudy S2 L2A STAC item intersecting *bbox*.

    Items are filtered server-side by cloud cover then sorted client-side to
    avoid catalogue-specific *sortby* syntax differences.
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
    if not items:
        raise RuntimeError(
            f"No S2 L2A scene found for bbox={bbox}, dates={date_range}, "
            f"cloud < {max_cloud_pct}%. "
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

    if args.territory:
        from src.config.territories import get as get_territory

        territory = get_territory(args.territory)
        bbox = territory.bbox_wgs84
        label = f"{territory.display_name} ({territory.region})"
        if args.territory == "sierra_nevada":
            alpine = True

    print(SEP)
    print("  SNTO ETL -- Sentinel-2 Raster Processor  [STAC / COG Edition]")
    print(f"  Pilot: {label}")
    print(f"  Bbox (WGS84) : {bbox}")
    print(f"  STAC URL     : {STAC_URL}")
    print(f"  Date range   : {args.date_range}  (cloud < {MAX_CLOUD_PCT} %)")
    print(f"  Output       : {CLEAN_DIR}")
    print(f"  Mode         : {'ALPINE (NDSI + SCL)' if alpine else 'standard'}")
    print(SEP)
    print()
    run(bbox=bbox, date_range=args.date_range, alpine=alpine)
    print(SEP)


if __name__ == "__main__":
    main()
