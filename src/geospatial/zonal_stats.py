"""
SNTO Alpine Edition — polygon zonal statistics (Sierra Nevada pilot, issue #9)
================================================================================
Mean raster value inside an arbitrary polygon (a trail corridor, an
altitude-matched control annulus), as opposed to the point-sampling helpers in
:mod:`src.geospatial.asset_sampling` (which read a small patch around
individual trace vertices). The Spatial Causality Module's local/control zones
are areas, not points, so they need a real polygon rasterisation rather than a
scatter of point samples.

Kept separate from ``asset_sampling`` because the two answer different
questions: "what is the value at this vertex" vs. "what is the mean value
inside this shape". Both eventually feed the same kind of per-asset raster
value, but conflating them would make the point-sampling path pay for a
polygon rasterisation it does not need.
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from src.config.constants import ALPINE_MIN_ZONE_PIXELS

__all__ = ["reproject_polygon", "zonal_mean"]


def reproject_polygon(polygon, src_crs: object, dst_crs: object):
    """Reproject a Shapely polygon from *src_crs* to *dst_crs*.

    A no-op (returns *polygon* unchanged) when the two CRSs are equal, so
    callers can pass this through unconditionally without an extra branch.
    """
    from pyproj import CRS as ProjCRS
    from pyproj import Transformer
    from shapely.ops import transform as shapely_transform

    src = ProjCRS.from_user_input(src_crs)
    dst = ProjCRS.from_user_input(dst_crs)
    if src.equals(dst):
        return polygon

    transformer = Transformer.from_crs(src, dst, always_xy=True)
    return shapely_transform(transformer.transform, polygon)


def zonal_mean(
    arr: np.ndarray,
    transform: object,
    polygon,
    polygon_crs: object,
    raster_crs: object,
    valid_mask: Optional[np.ndarray] = None,
    min_pixels: int = ALPINE_MIN_ZONE_PIXELS,
) -> tuple[Optional[float], int]:
    """Mean of *arr* over the pixels whose centre falls inside *polygon*.

    Reprojects *polygon* into *raster_crs* first (a no-op when they already
    match), then rasterises it against *arr*'s grid with
    ``rasterio.features.geometry_mask``. An additional *valid_mask* (e.g. a
    season-appropriate SCL exclusion mask) is ANDed in, matching the layered
    masking convention used across the alpine pipeline (nodata, then scene
    classification, then geometry).

    Args:
        arr: raster band, already on the grid described by *transform*.
        transform: affine transform for *arr*.
        polygon: Shapely polygon (or MultiPolygon) defining the zone.
        polygon_crs: CRS of *polygon*.
        raster_crs: CRS of *arr* / *transform*.
        valid_mask: optional boolean array, True where the pixel is usable.
        min_pixels: below this count, the mean is not reported — a handful of
            edge pixels is rasterisation noise, not a zone measurement.

    Returns:
        ``(mean, n_valid_pixels)``. ``mean`` is ``None`` when the polygon does
        not intersect the grid, or when fewer than *min_pixels* survive
        masking.
    """
    import rasterio.features
    from shapely.geometry import mapping

    poly_on_grid = reproject_polygon(polygon, polygon_crs, raster_crs)
    if poly_on_grid.is_empty:
        return None, 0

    try:
        geom_mask = rasterio.features.geometry_mask(
            [mapping(poly_on_grid)],
            out_shape=arr.shape,
            transform=transform,
            invert=True,
        )
    except ValueError:
        # geometry_mask raises when the polygon's bounds do not overlap the
        # raster's transform/shape at all — an empty zone, not an error.
        return None, 0

    mask = geom_mask & np.isfinite(arr)
    if valid_mask is not None:
        mask &= valid_mask

    n_valid = int(mask.sum())
    if n_valid < min_pixels:
        return None, n_valid

    return float(arr[mask].mean()), n_valid
