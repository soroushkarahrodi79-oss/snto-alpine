"""
SNTO Alpine Edition — Topo-asymmetric erosion buffering (Sierra Nevada pilot)
============================================================================
Slope-magnitude-aware trail corridors for high-mountain MTB and hiking routes.

:mod:`src.geospatial.geometry` already ingests the Copernicus DEM-30 via STAC
(``fetch_dem_window``), derives slope and aspect (``compute_slope_aspect``), and
builds an asymmetric corridor that is wider on the downhill side
(``asymmetric_trail_buffer``).  This module does not duplicate any of that.

What it adds is the missing half of the topography.  ``asymmetric_trail_buffer``
discards slope magnitude — its body reads ``_, aspect_deg = compute_slope_aspect(...)``
— so the corridor knows *which way* water runs but not *how hard*.  Every trail
therefore gets the same 15 m / 60 m corridor whether it crosses a flat borreguil
or plunges down a 35° couloir.

In Sierra Nevada that distinction is the whole problem: MTB descents concentrate
on the steepest sectors, where runoff energy scales with slope and the sediment
plume travels far further downhill.  This module samples slope along the trail
and widens the downslope corridor accordingly, while holding the uphill side at
the 15 m baseline — there is no mechanism by which trail runoff travels uphill.

All geometry conventions are inherited unchanged: trails arrive in EPSG:4326,
buffering happens in EPSG:25830 (ETRS89 / UTM 30N), and the module never raises
on degenerate terrain — it degrades to a symmetric buffer and logs, matching the
contract of ``build_trail_buffer``.
"""
from __future__ import annotations

import logging

import numpy as np
from pyproj import Transformer
from shapely.geometry import Polygon

from src.config.constants import HP_SLOPE_MAX_DEG
from src.geospatial.geometry import (
    _DEFAULT_BUFFER_CRS,
    _DEFAULT_DOWNSLOPE_M,
    _DEFAULT_UPSLOPE_M,
    _N_ASPECT_SAMPLES,
    asymmetric_trail_buffer,
    compute_slope_aspect,
)

logger = logging.getLogger(__name__)

__all__ = [
    "ALPINE_STEEP_SLOPE_DEG",
    "ALPINE_MAX_DOWNSLOPE_M",
    "alpine_trail_buffer",
    "sample_slope_along_trail",
    "slope_scaled_buffer_widths",
]

# ── Slope-scaling thresholds ─────────────────────────────────────────────────
# Below ALPINE_STEEP_SLOPE_DEG the corridor keeps the inherited 15/60 m
# baseline, so gentle alpine trails behave exactly as in the PNSG pilot and
# remain comparable with it.  Above it the downslope side ramps linearly to
# ALPINE_MAX_DOWNSLOPE_M, reached at HP_SLOPE_MAX_DEG (30°) — the slope the
# risk engine already treats as the practical limit of pedestrian access.
#
# The 60→80 m range follows the field brief for Sierra Nevada MTB descents.
# It is a planning assumption, not a measured transport distance; the Wemple
# et al. (2001) 3–5× downslope ratio that motivates the base 15/60 split was
# established on forested terrain, not on alpine pasture.
ALPINE_STEEP_SLOPE_DEG: float = 20.0   # slope above which the corridor widens
ALPINE_MAX_DOWNSLOPE_M: float = 80.0   # downslope width at HP_SLOPE_MAX_DEG


def sample_slope_along_trail(
    trail_geom,
    slope_deg: np.ndarray,
    dem_transform: object,
    dem_crs: object,
    trail_crs: str = _DEFAULT_BUFFER_CRS,
    n_samples: int = _N_ASPECT_SAMPLES,
) -> float:
    """Mean terrain slope (degrees) at equidistant points along a trail.

    The linear counterpart of ``geometry._mean_aspect_along_trail``.  Aspect is
    an angle on a circle and needs a circular mean; slope is a magnitude, so a
    plain arithmetic mean is correct here and a circular mean would be wrong.

    Samples falling outside the DEM window are skipped rather than treated as
    zero, so a partially covered trail reports the slope of its covered part
    instead of an artificially flattened average.

    Args:
        trail_geom: Shapely LineString already in ``trail_crs``.
        slope_deg: slope raster from :func:`compute_slope_aspect`.
        dem_transform: affine transform matching ``slope_deg``.
        dem_crs: CRS of the slope raster.
        trail_crs: CRS of ``trail_geom`` (default EPSG:25830).
        n_samples: number of equidistant samples along the trail.

    Returns:
        Mean slope in degrees; 0.0 for a zero-length trail or when no sample
        falls inside the DEM window (flat is the conservative assumption — it
        yields the narrow baseline corridor rather than an unfounded wide one).
    """
    if trail_geom.length == 0:
        return 0.0

    from affine import Affine
    from pyproj import CRS as ProjCRS
    from shapely.ops import transform as shapely_transform

    trail_proj_crs = ProjCRS.from_user_input(trail_crs)
    dem_proj_crs = ProjCRS.from_user_input(dem_crs)

    if not trail_proj_crs.equals(dem_proj_crs):
        t = Transformer.from_crs(trail_proj_crs, dem_proj_crs, always_xy=True)
        trail_in_dem_crs = shapely_transform(t.transform, trail_geom)
    else:
        trail_in_dem_crs = trail_geom

    tx: Affine = dem_transform  # type: ignore[assignment]
    h, w = slope_deg.shape

    total = 0.0
    n_valid = 0

    for i in range(n_samples):
        fraction = i / max(n_samples - 1, 1)
        pt = trail_in_dem_crs.interpolate(fraction, normalized=True)

        col = int(round((pt.x - tx.c) / tx.a))
        row = int(round((pt.y - tx.f) / tx.e))

        if 0 <= row < h and 0 <= col < w:
            value = float(slope_deg[row, col])
            if np.isfinite(value):
                total += value
                n_valid += 1

    if n_valid == 0:
        logger.info(
            "No trail sample fell inside the DEM window; assuming flat terrain."
        )
        return 0.0

    return total / n_valid


def slope_scaled_buffer_widths(
    mean_slope_deg: float,
    upslope_m: float = _DEFAULT_UPSLOPE_M,
    baseline_downslope_m: float = _DEFAULT_DOWNSLOPE_M,
    max_downslope_m: float = ALPINE_MAX_DOWNSLOPE_M,
    steep_slope_deg: float = ALPINE_STEEP_SLOPE_DEG,
    max_slope_deg: float = HP_SLOPE_MAX_DEG,
) -> tuple[float, float]:
    """Map mean trail slope onto (upslope_m, downslope_m) corridor widths.

    Piecewise-linear and monotonic in slope:

    ==========================  ==========================================
    Mean slope                  Corridor
    ==========================  ==========================================
    ``< steep_slope_deg``       ``(15, 60)`` — inherited PNSG baseline
    ``steep … max_slope_deg``   upslope 15; downslope ramps 60 → 80
    ``>= max_slope_deg``        ``(15, 80)`` — saturated
    ==========================  ==========================================

    The uphill side never widens: trail runoff does not travel uphill, so the
    15 m baseline represents the erosion *source* zone and is slope-invariant.

    Args:
        mean_slope_deg: mean slope along the trail, from
            :func:`sample_slope_along_trail`.
        upslope_m: uphill corridor width (slope-invariant).
        baseline_downslope_m: downslope width below ``steep_slope_deg``.
        max_downslope_m: downslope width at and above ``max_slope_deg``.
        steep_slope_deg: slope at which widening begins.
        max_slope_deg: slope at which widening saturates.

    Returns:
        ``(upslope_m, downslope_m)`` in metres.
    """
    if not np.isfinite(mean_slope_deg) or mean_slope_deg < steep_slope_deg:
        return upslope_m, baseline_downslope_m

    if mean_slope_deg >= max_slope_deg:
        return upslope_m, max_downslope_m

    span = max_slope_deg - steep_slope_deg
    if span <= 0.0:
        return upslope_m, max_downslope_m

    ratio = (mean_slope_deg - steep_slope_deg) / span
    downslope = baseline_downslope_m + ratio * (max_downslope_m - baseline_downslope_m)
    return upslope_m, downslope


def alpine_trail_buffer(
    trail_geom_4326,
    dem_array: np.ndarray | None,
    dem_transform: object | None,
    dem_crs: object | None,
    symmetric_fallback_m: float = 50.0,
    target_crs: str = _DEFAULT_BUFFER_CRS,
) -> Polygon:
    """Build a slope-scaled asymmetric corridor for one alpine trail.

    Pipeline: derive slope and aspect once, sample mean slope along the trail,
    map it to corridor widths, then delegate the actual corridor construction to
    the existing :func:`asymmetric_trail_buffer` — which handles reprojection,
    the downslope-side dot-product test, offset curves and self-intersection
    repair.  This function only decides *how wide*.

    Mirrors the graceful-degradation contract of ``geometry.build_trail_buffer``:
    it never raises.  Without a DEM it returns a symmetric buffer, because a
    slope-scaled corridor without slope data would be a fabricated number
    dressed as a measurement.

    Args:
        trail_geom_4326: Shapely LineString / MultiLineString in EPSG:4326.
        dem_array: elevation window from ``fetch_dem_window``, or None.
        dem_transform: affine transform matching ``dem_array``.
        dem_crs: CRS of ``dem_array``.
        symmetric_fallback_m: radius used when no DEM is available.
        target_crs: metric CRS for buffering (default EPSG:25830).

    Returns:
        Shapely Polygon in ``target_crs``.
    """
    if dem_array is None or dem_transform is None or dem_crs is None:
        logger.info(
            "No DEM available for alpine trail buffer; "
            "falling back to symmetric %.1f m buffer.",
            symmetric_fallback_m,
        )
        return _symmetric_buffer(trail_geom_4326, symmetric_fallback_m, target_crs)

    try:
        slope_deg, _ = compute_slope_aspect(dem_array, dem_transform)
        trail_metric = _to_metric(trail_geom_4326, target_crs)
        mean_slope = sample_slope_along_trail(
            trail_metric,
            slope_deg,
            dem_transform,
            dem_crs,
            trail_crs=target_crs,
        )
    except Exception as exc:  # pragma: no cover - defensive, mirrors house style
        logger.warning(
            "Slope sampling failed (%s); falling back to symmetric buffer.", exc
        )
        return _symmetric_buffer(trail_geom_4326, symmetric_fallback_m, target_crs)

    upslope_m, downslope_m = slope_scaled_buffer_widths(mean_slope)
    logger.info(
        "Alpine corridor: mean slope %.1f° → upslope %.1f m / downslope %.1f m.",
        mean_slope,
        upslope_m,
        downslope_m,
    )

    return asymmetric_trail_buffer(
        trail_geom_4326,
        dem_array,
        dem_transform,
        dem_crs,
        upslope_m=upslope_m,
        downslope_m=downslope_m,
        target_crs=target_crs,
    )


def _to_metric(trail_geom_4326, target_crs: str):
    """Reproject a WGS84 trail to the metric buffering CRS."""
    from pyproj import CRS as ProjCRS
    from shapely.ops import transform as shapely_transform

    if trail_geom_4326.geom_type == "MultiLineString":
        trail_geom_4326 = max(trail_geom_4326.geoms, key=lambda g: g.length)

    t = Transformer.from_crs(
        ProjCRS.from_epsg(4326), ProjCRS.from_user_input(target_crs), always_xy=True
    )
    return shapely_transform(t.transform, trail_geom_4326)


def _symmetric_buffer(trail_geom_4326, radius_m: float, target_crs: str) -> Polygon:
    """Symmetric fallback corridor in the metric CRS."""
    trail_metric = _to_metric(trail_geom_4326, target_crs)
    return trail_metric.buffer(radius_m, cap_style="round", join_style="round")
