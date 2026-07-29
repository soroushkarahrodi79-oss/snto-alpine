from __future__ import annotations

import logging
import math
from typing import Optional

import numpy as np
from pyproj import Transformer
from shapely.geometry import MultiLineString, Polygon, mapping, shape
from shapely.ops import substring, unary_union

from src.assets.models import GeometryType, TourismAsset

logger = logging.getLogger(__name__)

_M_PER_DEG_LAT = 111_320.0  # metres per degree of latitude (near-constant globally)

# ── DEM STAC settings ─────────────────────────────────────────────────────────
_DEM_STAC_URL  = "https://earth-search.aws.element84.com/v1"
_DEM_COLLECTION_CANDIDATES = ("cop-dem-glo-30", "copernicus-dem-glo-30")
_DEM_ASSET_CANDIDATES      = ("data", "elevation")

# Asymmetric buffer defaults (metres)
# Science rationale: runoff and sediment transport follow slopes, so the
# downslope corridor needs to be 4× wider to capture the erosion plume.
_DEFAULT_UPSLOPE_M   = 15.0
_DEFAULT_DOWNSLOPE_M = 60.0
_DEFAULT_BUFFER_CRS  = "EPSG:25830"   # UTM 30N — covers mainland Spain

# Number of equidistant sample points used to characterise trail aspect
_N_ASPECT_SAMPLES = 12

# Minimum number of valid DEM pixels required (guard against empty windows)
_MIN_DEM_PIXELS = 4

# GDAL hints for COG HTTP streaming.
# AWS_NO_SIGN_REQUEST is required because the Copernicus DEM GLO-30 asset on
# Earth Search resolves to an anonymous S3 object (s3://…). Without it, GDAL's
# /vsis3/ handler demands AWS credentials and fetch_dem_window() fails with
# "InvalidCredentials" on any machine that has none. The DEM bucket is public,
# so unsigned access is correct.
_GDAL_COG_ENV: dict[str, str] = {
    "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES",
    "GDAL_HTTP_MULTIPLEX":               "YES",
    "GDAL_HTTP_VERSION":                 "2",
    "GDAL_DISABLE_READDIR_ON_OPEN":      "EMPTY_DIR",
    "AWS_NO_SIGN_REQUEST":               "YES",
}


# ── Existing helpers (unchanged) ──────────────────────────────────────────────

def _to_shapely(asset: TourismAsset):
    geojson = {"type": asset.geometry.type.value, "coordinates": asset.geometry.coordinates}
    return shape(geojson)


def _centroid_lat_rad(asset: TourismAsset) -> float:
    geom = _to_shapely(asset)
    return math.radians(geom.centroid.y)


def get_centroid(asset: TourismAsset) -> tuple[float, float]:
    """Return (longitude, latitude) of asset centroid."""
    geom = _to_shapely(asset)
    c = geom.centroid
    return (c.x, c.y)


def get_area_ha(asset: TourismAsset) -> Optional[float]:
    """
    Return area in hectares for polygon assets using the asset's own centroid
    latitude for the degree-to-metre conversion. Accurate to < 1% for sites
    up to ~100 km². For production, reproject to a metric CRS (UTM).
    Returns None for non-polygon assets.
    """
    if asset.geometry.type != GeometryType.POLYGON:
        return None
    geom = _to_shapely(asset)
    lat_rad = _centroid_lat_rad(asset)
    m_per_deg_lon = _M_PER_DEG_LAT * math.cos(lat_rad)
    area_m2 = abs(geom.area) * _M_PER_DEG_LAT * m_per_deg_lon
    return area_m2 / 10_000.0


def get_length_km(asset: TourismAsset) -> Optional[float]:
    """
    Return approximate length in km for linear (trail) assets.
    Returns None for non-LineString assets.
    """
    if asset.geometry.type != GeometryType.LINESTRING:
        return None
    geom = _to_shapely(asset)
    lat_rad = _centroid_lat_rad(asset)
    m_per_deg_lon = _M_PER_DEG_LAT * math.cos(lat_rad)
    coords = list(geom.coords)
    total = 0.0
    for (x1, y1), (x2, y2) in zip(coords, coords[1:]):
        dx = (x2 - x1) * m_per_deg_lon
        dy = (y2 - y1) * _M_PER_DEG_LAT
        total += math.sqrt(dx**2 + dy**2)
    return total / 1_000.0


def enrich_asset_geometry(asset: TourismAsset) -> TourismAsset:
    """Return a copy of the asset with area_ha and metadata enriched."""
    centroid  = get_centroid(asset)
    area_ha   = get_area_ha(asset)
    length_km = get_length_km(asset)

    extra: dict = {"centroid_lon": centroid[0], "centroid_lat": centroid[1]}
    if area_ha is not None:
        extra["area_ha"] = area_ha
    if length_km is not None:
        extra["length_km"] = length_km

    updated_metadata = {**asset.metadata, **extra}
    return asset.model_copy(update={"area_ha": area_ha, "metadata": updated_metadata})


# ── DEM retrieval via STAC / COG ──────────────────────────────────────────────

def fetch_dem_window(
    bbox_4326: tuple[float, float, float, float],
    stac_url: str = _DEM_STAC_URL,
    collection_candidates: tuple[str, ...] = _DEM_COLLECTION_CANDIDATES,
    asset_candidates: tuple[str, ...] = _DEM_ASSET_CANDIDATES,
) -> tuple[np.ndarray, object, object]:
    """Stream a Copernicus DEM-30 window for *bbox_4326* via STAC / COG.

    Uses the same windowed-read strategy as etl_raster_processor.py: only the
    HTTP byte ranges covering the study window are fetched — the full DEM tile
    (~300 MB each) is never downloaded.

    Tries each collection name in *collection_candidates* so the function works
    whether the Earth Search catalogue uses the hyphenated or non-hyphenated
    form of the Copernicus DEM collection.

    Args:
        bbox_4326:             Study area (W, S, E, N) in EPSG:4326.
        stac_url:              STAC API root URL.
        collection_candidates: Ordered collection names to try.
        asset_candidates:      Ordered asset keys to try within the STAC item.

    Returns:
        (dem_array[H, W] float32, affine_transform, rasterio.CRS)

    Raises:
        RuntimeError if pystac-client is not installed or no DEM tile is found.
        ImportError if rasterio is not installed.
    """
    try:
        from pystac_client import Client
    except ImportError as exc:
        raise RuntimeError(
            "pystac-client is required for DEM fetch: pip install pystac-client"
        ) from exc

    import rasterio
    from rasterio.transform import from_bounds as transform_from_bounds
    from rasterio.windows import bounds as window_bounds
    from rasterio.windows import from_bounds as window_from_bounds

    catalog = Client.open(stac_url)
    item = None

    for collection in collection_candidates:
        search = catalog.search(
            collections=[collection],
            bbox=list(bbox_4326),
            max_items=5,
        )
        items = list(search.items())
        if items:
            item = items[0]
            logger.debug("DEM: found item '%s' in collection '%s'", item.id, collection)
            break

    if item is None:
        raise RuntimeError(
            f"No Copernicus DEM tile found for bbox={bbox_4326}. "
            f"Tried collections: {collection_candidates}."
        )

    href = None
    for key in asset_candidates:
        asset_obj = item.assets.get(key)
        if asset_obj is not None:
            href = asset_obj.href
            break

    if href is None:
        raise RuntimeError(
            f"DEM item '{item.id}' has none of the expected asset keys "
            f"{asset_candidates}. Available: {list(item.assets.keys())}"
        )

    with rasterio.Env(**_GDAL_COG_ENV):
        with rasterio.open(href) as ds:
            t = Transformer.from_crs(4326, ds.crs, always_xy=True)
            xmin, ymin = t.transform(bbox_4326[0], bbox_4326[1])
            xmax, ymax = t.transform(bbox_4326[2], bbox_4326[3])
            win = window_from_bounds(xmin, ymin, xmax, ymax, ds.transform)
            dem = ds.read(1, window=win).astype(np.float32)
            geo_bounds = window_bounds(win, ds.transform)
            h, w = dem.shape
            out_transform = transform_from_bounds(*geo_bounds, w, h)
            crs = ds.crs

    if dem.size < _MIN_DEM_PIXELS:
        raise RuntimeError(
            f"DEM window for bbox={bbox_4326} contains only {dem.size} pixel(s) "
            "— too small for reliable slope/aspect calculation."
        )

    return dem, out_transform, crs


# ── Slope and aspect ──────────────────────────────────────────────────────────

_M_PER_DEG = _M_PER_DEG_LAT  # 111_320.0


def metric_slope_transform(transform: object, crs: object, mean_lat_deg: float):
    """Return a transform whose pixel size is in METRES, for slope magnitude.

    ``compute_slope_aspect`` reads pixel size straight from the transform. When
    the DEM is geographic (EPSG:4326) that size is in DEGREES, so rise/run
    explodes and every slope saturates near 90°. *Aspect* is an angle and stays
    correct (scale-invariant), which is why the asymmetric buffer — which only
    uses aspect — never hit this; *slope magnitude* does not.

    For a geographic transform this returns a copy with the ``a``/``e`` pixel
    steps rescaled to metres (longitude scaled by ``cos(lat)``). For an already
    projected transform it is returned unchanged.

    Args:
        transform: affine transform of the DEM window.
        crs: CRS of the DEM.
        mean_lat_deg: representative latitude, for the longitude metre-scaling.

    Returns:
        An ``affine.Affine`` suitable as the ``transform`` arg of
        :func:`compute_slope_aspect` for correct slope magnitudes.
    """
    import math

    from affine import Affine
    from pyproj import CRS as ProjCRS

    t: Affine = transform  # type: ignore[assignment]
    if not ProjCRS.from_user_input(crs).is_geographic:
        return t
    m_per_deg_lon = _M_PER_DEG * math.cos(math.radians(mean_lat_deg))
    return Affine(t.a * m_per_deg_lon, t.b, t.c, t.d, t.e * _M_PER_DEG, t.f)


def compute_slope_aspect(
    dem_array: np.ndarray,
    transform: object,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute terrain slope and aspect from a DEM window.

    Uses numpy.gradient to estimate the local partial derivatives, then
    converts to slope (degrees, 0=flat, 90=vertical cliff) and aspect
    (degrees, 0/360=North, 90=East, 180=South, 270=West — clockwise from N).

    Pixel size is read from the affine ``transform`` and assumed to be in
    METRES. Aspect is scale-invariant, but for correct **slope magnitude** on a
    geographic (EPSG:4326) DEM, first convert the transform with
    :func:`metric_slope_transform`.

    Args:
        dem_array:  2-D float32 elevation array [H, W].
        transform:  rasterio / affine Affine transform for the array.

    Returns:
        (slope_deg[H, W], aspect_deg[H, W]) — both float32.
    """
    from affine import Affine

    t: Affine = transform  # type: ignore[assignment]

    # Pixel size in map units (may be degrees or metres depending on CRS)
    px_size_x = abs(t.a)   # column step → x
    px_size_y = abs(t.e)   # row step    → y

    # np.gradient returns (grad_along_rows, grad_along_cols)
    # rows correspond to Y (latitude/northing), cols to X (lon/easting)
    grad_y_raw, grad_x_raw = np.gradient(dem_array.astype(np.float64))

    # Convert from rise/pixel to rise/metre
    dz_dy = grad_y_raw / px_size_y   # ∂z/∂y  (positive = uphill to north)
    dz_dx = grad_x_raw / px_size_x   # ∂z/∂x  (positive = uphill to east)

    # Slope in degrees
    slope_deg = np.degrees(np.arctan(np.sqrt(dz_dx**2 + dz_dy**2)))

    # Aspect: measured clockwise from North (0°/360° = N, 90° = E)
    # arctan2(dz_dx, -dz_dy):  East is positive X, South is negative Y
    # Adding 360 and taking modulo ensures [0, 360) range
    aspect_rad = np.arctan2(dz_dx, -dz_dy)
    aspect_deg = (np.degrees(aspect_rad) + 360.0) % 360.0

    return slope_deg.astype(np.float32), aspect_deg.astype(np.float32)


# ── Asymmetric trail buffer ───────────────────────────────────────────────────

def _mean_aspect_along_trail(
    trail_geom,
    dem_array: np.ndarray,
    aspect_deg: np.ndarray,
    dem_transform: object,
    dem_crs: object,
    trail_crs: str,
    n_samples: int = _N_ASPECT_SAMPLES,
) -> float:
    """Estimate mean terrain aspect (°) at equidistant points along the trail.

    Samples the pre-computed aspect raster at *n_samples* positions distributed
    evenly along the trail.  The mean is computed as a circular mean to handle
    the 0°/360° discontinuity correctly.

    Returns the mean aspect in degrees [0, 360), clockwise from North.
    """
    if trail_geom.length == 0:
        return 0.0

    from pyproj import CRS as ProjCRS
    from shapely.ops import transform as shapely_transform

    trail_proj_crs = ProjCRS.from_user_input(trail_crs)
    dem_proj_crs   = ProjCRS.from_user_input(dem_crs)

    if not trail_proj_crs.equals(dem_proj_crs):
        t = Transformer.from_crs(trail_proj_crs, dem_proj_crs, always_xy=True)
        trail_in_dem_crs = shapely_transform(t.transform, trail_geom)
    else:
        trail_in_dem_crs = trail_geom

    from affine import Affine
    tx: Affine = dem_transform  # type: ignore[assignment]
    h, w = dem_array.shape

    sin_sum = cos_sum = 0.0
    n_valid = 0

    for i in range(n_samples):
        # .interpolate() always returns a Point; avoids degenerate geometry when
        # start_dist == end_dist in shapely.ops.substring (Shapely 2 behaviour)
        fraction = i / max(n_samples - 1, 1)
        pt = trail_in_dem_crs.interpolate(fraction, normalized=True)

        # Convert geographic/projected coords → pixel indices (row, col)
        col_f = (pt.x - tx.c) / tx.a
        row_f = (pt.y - tx.f) / tx.e
        col = int(round(col_f))
        row = int(round(row_f))

        if 0 <= row < h and 0 <= col < w:
            angle_rad = math.radians(float(aspect_deg[row, col]))
            sin_sum  += math.sin(angle_rad)
            cos_sum  += math.cos(angle_rad)
            n_valid  += 1

    if n_valid == 0:
        return 0.0  # fallback: assume north-facing

    # Circular mean
    mean_angle_rad = math.atan2(sin_sum / n_valid, cos_sum / n_valid)
    return (math.degrees(mean_angle_rad) + 360.0) % 360.0


def _is_left_side_downslope(trail_utm, mean_aspect_deg: float) -> bool:
    """Return True if the left side of the trail (w.r.t. its direction) faces downslope.

    Compares the trail's main perpendicular left-side direction with the terrain
    downslope direction derived from the mean aspect.

    Aspect 0°=N means elevation increases to the north → downslope faces south.
    The downslope unit vector is the opposite of the aspect vector.
    """
    coords = list(trail_utm.coords)
    if len(coords) < 2:
        return True  # arbitrary default

    # Trail direction vector (from first to last vertex)
    dx = coords[-1][0] - coords[0][0]
    dy = coords[-1][1] - coords[0][1]
    length = math.hypot(dx, dy)
    if length == 0:
        return True
    dx /= length
    dy /= length

    # Left perpendicular (rotate 90° anti-clockwise)
    left_x = -dy
    left_y =  dx

    # Downslope direction: opposite of the upslope direction (aspect)
    # Aspect is "direction of steepest ascent" → downslope = aspect + 180°
    downslope_deg = (mean_aspect_deg + 180.0) % 360.0
    downslope_rad = math.radians(downslope_deg)
    # In UTM: East = +X, North = +Y
    down_x = math.sin(downslope_rad)   # East component
    down_y = math.cos(downslope_rad)   # North component

    # Dot product: positive → left side is downslope
    return (left_x * down_x + left_y * down_y) > 0.0


def asymmetric_trail_buffer(
    trail_geom,
    dem_array: np.ndarray,
    dem_transform: object,
    dem_crs: object,
    upslope_m: float = _DEFAULT_UPSLOPE_M,
    downslope_m: float = _DEFAULT_DOWNSLOPE_M,
    target_crs: str = _DEFAULT_BUFFER_CRS,
) -> Polygon:
    """Create a topographically informed asymmetric corridor buffer for a trail.

    Replaces the naive ``LineString.buffer(50)`` with an asymmetric polygon:
    *upslope_m* metres on the uphill side (erosion source limited by slope) and
    *downslope_m* metres on the downhill side (where runoff and sediment land).
    Scientific rationale: Wemple et al. (2001) show sediment deposition zones
    are 3–5× wider downslope of hiking trails on steep terrain.

    Algorithm:
      1. Reproject trail to *target_crs* (metric CRS).
      2. Sample terrain aspect from *dem_array* at equidistant trail points.
      3. Determine which side of the trail is downslope via dot-product test.
      4. Use Shapely offset_curve() to create two parallel offset lines.
      5. Build the corridor polygon from the two offset lines and end caps.

    Args:
        trail_geom:   Shapely LineString or MultiLineString in EPSG:4326.
        dem_array:    2-D float32 elevation array from fetch_dem_window().
        dem_transform:Affine transform matching *dem_array*.
        dem_crs:      CRS of *dem_array*.
        upslope_m:    Buffer distance on the uphill side (default 15 m).
        downslope_m:  Buffer distance on the downhill side (default 60 m).
        target_crs:   Metric CRS for buffering (default EPSG:25830 UTM 30N).

    Returns:
        Shapely Polygon in *target_crs*.  Falls back to a symmetric buffer of
        ``(upslope_m + downslope_m) / 2`` m if offset_curve fails (e.g. for
        degenerate geometry).
    """
    from pyproj import CRS as ProjCRS
    from shapely.ops import transform as shapely_transform

    # 1. Reproject trail from WGS84 to target_crs (metric)
    wgs84      = ProjCRS.from_epsg(4326)
    metric_crs = ProjCRS.from_user_input(target_crs)
    t_to_utm   = Transformer.from_crs(wgs84, metric_crs, always_xy=True)

    # Handle MultiLineString by merging into the longest component
    if trail_geom.geom_type == "MultiLineString":
        trail_geom = max(trail_geom.geoms, key=lambda g: g.length)

    trail_utm: object = shapely_transform(t_to_utm.transform, trail_geom)

    # 2. Compute aspect (already available from caller or compute inline)
    _, aspect_deg = compute_slope_aspect(dem_array, dem_transform)

    # 3. Determine which offset side is downslope
    mean_asp = _mean_aspect_along_trail(
        trail_utm, dem_array, aspect_deg, dem_transform, dem_crs,
        trail_crs=target_crs,
    )
    left_is_down = _is_left_side_downslope(trail_utm, mean_asp)

    dist_left  = downslope_m if left_is_down else upslope_m
    dist_right = upslope_m   if left_is_down else downslope_m

    # 4. Create two parallel offset curves using Shapely
    # offset_curve(distance): positive = left, negative = right
    try:
        left_curve  = trail_utm.offset_curve( dist_left,  join_style="round", quad_segs=8)
        right_curve = trail_utm.offset_curve(-dist_right, join_style="round", quad_segs=8)
    except Exception as exc:
        logger.warning("offset_curve failed (%s); falling back to symmetric buffer.", exc)
        sym_dist = (upslope_m + downslope_m) / 2.0
        return trail_utm.buffer(sym_dist, cap_style="round", join_style="round")

    # 5. Build corridor polygon: left curve → right curve reversed → closed ring
    try:
        left_coords  = list(left_curve.coords)
        right_coords = list(reversed(list(right_curve.coords)))
        ring = left_coords + right_coords + [left_coords[0]]
        corridor = Polygon(ring)
        if not corridor.is_valid:
            corridor = corridor.buffer(0)  # auto-repair self-intersections
        if corridor.is_empty:
            raise ValueError("Empty corridor polygon after construction")
        return corridor
    except Exception as exc:
        logger.warning(
            "Corridor polygon construction failed (%s); falling back to symmetric buffer.", exc
        )
        sym_dist = (upslope_m + downslope_m) / 2.0
        return trail_utm.buffer(sym_dist, cap_style="round", join_style="round")


def build_trail_buffer(
    trail_geom_4326,
    dem_array: np.ndarray | None,
    dem_transform: object | None,
    dem_crs: object | None,
    upslope_m: float = _DEFAULT_UPSLOPE_M,
    downslope_m: float = _DEFAULT_DOWNSLOPE_M,
    symmetric_fallback_m: float = 50.0,
    target_crs: str = _DEFAULT_BUFFER_CRS,
) -> Polygon:
    """Top-level buffer builder with graceful symmetric fallback.

    When DEM data is available, delegates to asymmetric_trail_buffer().
    When *dem_array* is None (DEM fetch failed or skipped), creates a simple
    symmetric buffer of *symmetric_fallback_m* metres — preserving backward
    compatibility with the original ETL pipeline.

    Args:
        trail_geom_4326:       Shapely LineString/MultiLineString in EPSG:4326.
        dem_array:             DEM array from fetch_dem_window(); None → fallback.
        dem_transform:         Affine transform for dem_array; None → fallback.
        dem_crs:               CRS for dem_array; None → fallback.
        upslope_m:             Upslope buffer distance (default 15 m).
        downslope_m:           Downslope buffer distance (default 60 m).
        symmetric_fallback_m:  Symmetric buffer radius when DEM is unavailable.
        target_crs:            Metric CRS for buffering.

    Returns:
        Shapely Polygon in *target_crs*.
    """
    if dem_array is None or dem_transform is None or dem_crs is None:
        logger.info("DEM unavailable — using symmetric buffer (%.0f m).", symmetric_fallback_m)
        from pyproj import CRS as ProjCRS
        from shapely.ops import transform as shapely_transform

        wgs84      = ProjCRS.from_epsg(4326)
        metric_crs = ProjCRS.from_user_input(target_crs)
        t_to_utm   = Transformer.from_crs(wgs84, metric_crs, always_xy=True)
        geom = trail_geom_4326
        if geom.geom_type == "MultiLineString":
            geom = max(geom.geoms, key=lambda g: g.length)
        trail_utm = shapely_transform(t_to_utm.transform, geom)
        return trail_utm.buffer(symmetric_fallback_m, cap_style="round", join_style="round")

    return asymmetric_trail_buffer(
        trail_geom_4326, dem_array, dem_transform, dem_crs,
        upslope_m=upslope_m, downslope_m=downslope_m, target_crs=target_crs,
    )
