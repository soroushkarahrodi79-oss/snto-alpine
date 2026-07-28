"""
SNTO ETL -- Raster Intersection (Zonal Statistics)
===================================================
Pilot Territory: Sierra del Rincón Biosphere Reserve, Madrid, Spain

For each hiking trail in production_hiking_trails:
  1. Fetches the Copernicus DEM GLO-30 for the study area via STAC / COG
  2. Computes terrain slope and aspect from the DEM window
  3. Projects each trail to EPSG:25830 (UTM zone 30N)
  4. Creates an asymmetric buffer (15 m upslope / 60 m downslope) informed
     by the slope direction — capturing the runoff corridor more accurately
     than a generic 50 m symmetric buffer (Wemple et al. 2001)
  5. Reprojects buffers to match each raster's native CRS before extraction
  6. Computes mean NDVI and mean NDMI via rasterstats zonal statistics
  7. Writes avg_ndvi / avg_ndmi back to the PostGIS table

Falls back to a symmetric 50 m buffer if the DEM STAC fetch fails (e.g.
in offline environments or when the catalogue is temporarily unavailable).

Dependencies:
  pip install geopandas psycopg2-binary sqlalchemy rasterio rasterstats
  pip install pystac-client affine
"""
from __future__ import annotations

import io
import os
import sys

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from pathlib import Path

import geopandas as gpd
import psycopg2
import rasterio
from dotenv import load_dotenv
from rasterstats import zonal_stats
from sqlalchemy import create_engine

load_dotenv()  # carga .env antes de os.getenv() a nivel de módulo

SEP = "=" * 72
DIV = "-" * 72

PROJECT_ROOT = Path(__file__).parent
CLEAN_DIR    = PROJECT_ROOT / "data" / "clean_assets"

NDVI_PATH = CLEAN_DIR / "clean_S2_NDVI.tif"
NDMI_PATH = CLEAN_DIR / "clean_S2_NDMI.tif"

# Asymmetric buffer distances (Science: downslope zone is 4× wider to capture
# the runoff and sediment deposition corridor — Wemple et al. 2001)
UPSLOPE_M   = 15       # Buffer on the uphill side (metres)
DOWNSLOPE_M = 60       # Buffer on the downhill side (metres)
BUFFER_M    = 50       # Symmetric fallback radius when DEM is unavailable
BUFFER_CRS  = "EPSG:25830"  # UTM zone 30N — covers mainland Spain

# Territory switch (Alpine Edition).  When set to "sierra_nevada" the buffer
# step uses slope-magnitude-scaled corridors (src/geospatial/alpine_dem.py)
# instead of the fixed 15/60 m widths above: alpine MTB descents concentrate on
# the steepest sectors, where the sediment plume travels further downhill.
# Any other value keeps the inherited PNSG behaviour byte-for-byte.
TERRITORY = os.getenv("SNTO_TERRITORY", "pnsg")
ALPINE_TERRITORY = "sierra_nevada"

# ── Credentials (override via environment variables) ──────────────────────────
DB_HOST = os.getenv("SNTO_DB_HOST", "localhost")
DB_PORT = int(os.getenv("SNTO_DB_PORT", "5432"))
DB_NAME = os.getenv("SNTO_DB_NAME", "snto")
DB_USER = os.getenv("SNTO_DB_USER", "postgres")
DB_PASS = os.getenv("SNTO_DB_PASS", "")


# ── Connection helpers ─────────────────────────────────────────────────────────

def _connect() -> psycopg2.extensions.connection:
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASS, connect_timeout=10,
    )


def _engine():
    return create_engine(
        f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )


# ── Schema helpers ─────────────────────────────────────────────────────────────

def _ensure_columns(conn: psycopg2.extensions.connection) -> None:
    """Add avg_ndvi / avg_ndmi FLOAT columns if they do not already exist."""
    with conn.cursor() as cur:
        for col in ("avg_ndvi", "avg_ndmi"):
            cur.execute(
                """
                SELECT 1 FROM information_schema.columns
                WHERE  table_schema = 'public'
                  AND  table_name   = 'production_hiking_trails'
                  AND  column_name  = %s
                """,
                (col,),
            )
            if cur.fetchone() is None:
                print(f"    Adding column '{col}' FLOAT to production_hiking_trails ...")
                cur.execute(
                    f"ALTER TABLE production_hiking_trails ADD COLUMN {col} FLOAT"
                )
            else:
                print(f"    Column '{col}' already exists — will overwrite values.")
    conn.commit()


# ── Raster helpers ─────────────────────────────────────────────────────────────

def _inspect_raster(path: Path, label: str) -> None:
    with rasterio.open(path) as src:
        print(f"    {label}: {path.name}")
        print(f"           CRS    = {src.crs.to_string()}")
        print(f"           Size   = {src.width} px × {src.height} px")
        print(f"           Bands  = {src.count}")
        print(f"           NoData = {src.nodata}")
        print(f"           Bounds = ({src.bounds.left:.4f}, {src.bounds.bottom:.4f}, "
              f"{src.bounds.right:.4f}, {src.bounds.top:.4f})")


def _compute_zonal_stats(
    buffers_gdf: gpd.GeoDataFrame,
    raster_path: Path,
    label: str,
) -> list[float | None]:
    """
    Reproject buffers to the raster's native CRS (if mismatched), then run
    rasterstats. Returns a list of mean values positionally aligned to
    buffers_gdf.  Geometries that fall outside the raster extent return None.
    """
    from pyproj import CRS as ProjCRS

    with rasterio.open(raster_path) as src:
        raster_crs    = src.crs          # rasterio.crs.CRS object
        raster_nodata = src.nodata

    # Convert rasterio CRS to pyproj.CRS for semantic equality check.
    # Comparing .to_string() values is unreliable: pyproj returns WKT2 while
    # rasterio returns PROJ4 — the same authority produces different strings,
    # so a naive string comparison always reports a mismatch.
    raster_crs_obj = ProjCRS.from_user_input(raster_crs)
    crs_match = buffers_gdf.crs.equals(raster_crs_obj)

    buf_epsg    = buffers_gdf.crs.to_epsg() or buffers_gdf.crs.to_string()
    raster_epsg = raster_crs.to_epsg() or raster_crs.to_string()
    print(f"    Raster CRS ({label}): EPSG:{raster_epsg}")
    print(f"    Buffer CRS          : EPSG:{buf_epsg}")

    if not crs_match:
        print("    CRS mismatch — reprojecting buffers to raster CRS ...")
        aligned = buffers_gdf.to_crs(raster_crs.to_wkt())
    else:
        print("    CRS match — no reprojection needed.")
        aligned = buffers_gdf

    # rasterstats.zonal_stats accepts a GeoDataFrame directly (v0.18+)
    stats_list = zonal_stats(
        aligned,
        str(raster_path),
        stats=["mean"],
        nodata=raster_nodata,
        all_touched=False,   # only pixels whose centre falls within the buffer
    )

    return [s.get("mean") for s in stats_list]


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print(SEP)
    print("  SNTO ETL — Raster Intersection (Zonal Statistics)")
    print("  Pilot: Sierra del Rincón Biosphere Reserve, Madrid, Spain")
    print(f"  Target: postgresql://{DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}")
    print(SEP)
    print()

    # ── [1/7] Verify raster inputs ────────────────────────────────────────────
    print("  [1/7] Verifying Sentinel-2 raster files ...")
    missing = [
        (lbl, p) for lbl, p in [("NDVI", NDVI_PATH), ("NDMI", NDMI_PATH)]
        if not p.exists()
    ]
    if missing:
        for lbl, p in missing:
            print(f"  ERROR: {lbl} raster not found at: {p}")
        sys.exit(1)

    _inspect_raster(NDVI_PATH, "NDVI")
    _inspect_raster(NDMI_PATH, "NDMI")
    print()

    # ── [2/7] Connect to PostGIS ──────────────────────────────────────────────
    print("  [2/7] Connecting to PostGIS ...")
    try:
        conn = _connect()
    except (psycopg2.OperationalError, UnicodeDecodeError) as exc:
        print(f"  ERROR: Cannot connect — {type(exc).__name__}")
        print("  Ensure PostgreSQL is running and credentials are correct.")
        print("  Override via env vars: SNTO_DB_HOST / PORT / NAME / USER / PASS")
        sys.exit(1)

    major, minor = divmod(conn.server_version, 10000)
    print(f"  Connected. PostgreSQL {major}.{minor}")
    print()

    # ── [3/7] Ensure output columns exist ────────────────────────────────────
    print("  [3/7] Ensuring avg_ndvi / avg_ndmi columns exist ...")
    _ensure_columns(conn)
    print()

    # ── [4/7] Load hiking trails ──────────────────────────────────────────────
    print("  [4/7] Loading hiking trails from PostGIS ...")
    engine = _engine()
    try:
        trails_gdf = gpd.read_postgis(
            "SELECT id, name, geometry FROM production_hiking_trails ORDER BY id",
            con=engine,
            geom_col="geometry",
            crs="EPSG:4326",
        )
    finally:
        engine.dispose()
    n_total = len(trails_gdf)
    print(f"    Loaded {n_total} features from production_hiking_trails")
    print(f"    Native CRS: {trails_gdf.crs.to_string()}")

    valid_mask = trails_gdf.geometry.notna() & ~trails_gdf.geometry.is_empty
    trails_gdf = trails_gdf[valid_mask].copy()
    n_valid = len(trails_gdf)
    if n_total != n_valid:
        print(f"    Dropped {n_total - n_valid} null/empty geometries. {n_valid} remain.")
    print()

    # ── [5/7] Fetch DEM + build asymmetric trail buffers ─────────────────────
    from src.geospatial.geometry import build_trail_buffer, fetch_dem_window

    is_alpine = TERRITORY == ALPINE_TERRITORY

    # Determine overall bounding box (W, S, E, N) in EPSG:4326
    bounds = trails_gdf.total_bounds   # [minx, miny, maxx, maxy]
    dem_bbox = (float(bounds[0]), float(bounds[1]), float(bounds[2]), float(bounds[3]))

    dem_array = dem_transform = dem_crs = None
    print("  [5/7] Fetching Copernicus DEM GLO-30 for study area ...")
    try:
        dem_array, dem_transform, dem_crs = fetch_dem_window(dem_bbox)
        print(
            f"    DEM loaded: {dem_array.shape[1]}×{dem_array.shape[0]} px  "
            f"elevation range {dem_array.min():.0f}–{dem_array.max():.0f} m"
        )
        if is_alpine:
            from src.geospatial.alpine_dem import (
                ALPINE_MAX_DOWNSLOPE_M,
                ALPINE_STEEP_SLOPE_DEG,
            )
            print(
                f"    Alpine mode ({TERRITORY}): slope-scaled corridor — "
                f"{UPSLOPE_M} m upslope, downslope {DOWNSLOPE_M}→"
                f"{ALPINE_MAX_DOWNSLOPE_M:.0f} m above {ALPINE_STEEP_SLOPE_DEG:.0f}°"
            )
        else:
            print(
                f"    Asymmetric buffer: {UPSLOPE_M} m upslope / "
                f"{DOWNSLOPE_M} m downslope"
            )
    except Exception as exc:
        print(f"    DEM fetch failed ({exc})")
        print(f"    Falling back to symmetric {BUFFER_M} m buffer.")

    print(f"    Building buffers in {BUFFER_CRS} ...")
    buffer_polygons = []
    for geom in trails_gdf.geometry:
        if is_alpine:
            from src.geospatial.alpine_dem import alpine_trail_buffer

            buf = alpine_trail_buffer(
                geom, dem_array, dem_transform, dem_crs,
                symmetric_fallback_m=BUFFER_M,
                target_crs=BUFFER_CRS,
            )
        else:
            buf = build_trail_buffer(
                geom, dem_array, dem_transform, dem_crs,
                upslope_m=UPSLOPE_M,
                downslope_m=DOWNSLOPE_M,
                symmetric_fallback_m=BUFFER_M,
                target_crs=BUFFER_CRS,
            )
        buffer_polygons.append(buf)

    buffers_gdf = gpd.GeoDataFrame(
        trails_gdf.drop(columns=["geometry"]),
        geometry=buffer_polygons,
        crs=BUFFER_CRS,
    )

    n_empty = buffers_gdf.geometry.is_empty.sum()
    if n_empty:
        print(f"    WARNING: {n_empty} buffer(s) are unexpectedly empty — "
              "they will produce NULL stats.")
    print(f"    Buffer GDF CRS  : {buffers_gdf.crs.to_string()}")
    print(f"    Buffers created : {len(buffers_gdf)}")
    print()

    # ── [6/7] Compute zonal statistics ───────────────────────────────────────
    print("  [6/7] Computing zonal statistics ...")
    print()

    print("  --- NDVI ---")
    ndvi_means = _compute_zonal_stats(buffers_gdf, NDVI_PATH, "NDVI")
    n_ndvi_ok  = sum(1 for v in ndvi_means if v is not None)
    print(f"    Non-null results: {n_ndvi_ok} / {len(ndvi_means)}")
    if n_ndvi_ok > 0:
        valid = [v for v in ndvi_means if v is not None]
        print(f"    Mean NDVI : {sum(valid)/len(valid):.4f}")
        print(f"    Range     : {min(valid):.4f}  –  {max(valid):.4f}")
    print()

    print("  --- NDMI ---")
    ndmi_means = _compute_zonal_stats(buffers_gdf, NDMI_PATH, "NDMI")
    n_ndmi_ok  = sum(1 for v in ndmi_means if v is not None)
    print(f"    Non-null results: {n_ndmi_ok} / {len(ndmi_means)}")
    if n_ndmi_ok > 0:
        valid = [v for v in ndmi_means if v is not None]
        print(f"    Mean NDMI : {sum(valid)/len(valid):.4f}")
        print(f"    Range     : {min(valid):.4f}  –  {max(valid):.4f}")
    print()

    if n_ndvi_ok == 0 and n_ndmi_ok == 0:
        print("  WARNING: ALL zonal stats returned None. The trail buffers may lie")
        print("  entirely outside the raster extent. Check CRS and spatial coverage.")
        print()

    # ── [7/7] Write back to PostGIS ───────────────────────────────────────────
    print("  [7/7] Writing avg_ndvi / avg_ndmi back to PostGIS ...")
    ids     = trails_gdf["id"].tolist()
    updated = 0

    with conn.cursor() as cur:
        for trail_id, ndvi_val, ndmi_val in zip(ids, ndvi_means, ndmi_means):
            cur.execute(
                """
                UPDATE production_hiking_trails
                   SET avg_ndvi = %s,
                       avg_ndmi = %s
                 WHERE id = %s
                """,
                (ndvi_val, ndmi_val, int(trail_id)),
            )
            updated += cur.rowcount

    conn.commit()
    print(f"    Rows updated: {updated}")
    print()

    # ── Verification report ───────────────────────────────────────────────────
    print(DIV)
    print("  VERIFICATION REPORT")
    print(DIV)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                COUNT(*)                                AS total_rows,
                COUNT(avg_ndvi)                         AS ndvi_populated,
                COUNT(avg_ndmi)                         AS ndmi_populated,
                ROUND(AVG(avg_ndvi)::numeric, 6)        AS mean_ndvi,
                ROUND(MIN(avg_ndvi)::numeric, 6)        AS min_ndvi,
                ROUND(MAX(avg_ndvi)::numeric, 6)        AS max_ndvi,
                ROUND(AVG(avg_ndmi)::numeric, 6)        AS mean_ndmi,
                ROUND(MIN(avg_ndmi)::numeric, 6)        AS min_ndmi,
                ROUND(MAX(avg_ndmi)::numeric, 6)        AS max_ndmi
            FROM production_hiking_trails
            """
        )
        r = cur.fetchone()
        print(f"  Total trails         : {r[0]}")
        print(f"  avg_ndvi populated   : {r[1]}")
        print(f"  avg_ndmi populated   : {r[2]}")
        print(f"  Mean NDVI            : {r[3]}")
        print(f"  NDVI range           : {r[4]}  –  {r[5]}")
        print(f"  Mean NDMI            : {r[6]}")
        print(f"  NDMI range           : {r[7]}  –  {r[8]}")
    print()

    conn.close()

    print(SEP)
    print("  Zonal statistics ETL complete.")
    print(SEP)
    print()


if __name__ == "__main__":
    main()
