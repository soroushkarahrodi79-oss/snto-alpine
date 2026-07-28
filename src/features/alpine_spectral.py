"""
SNTO Alpine Edition — Alpine spectral & snow indices (Sierra Nevada pilot)
=========================================================================
Dual-season feature extraction for high-mountain protected areas.

Sierra Nevada poses two spectrally opposite problems in the same territory:

* **Winter** — snowpack retreat.  Snow is the *signal*, and the index of record
  is NDSI (Hall et al. 1995).
* **Summer** — erosion of the *borreguiles* (wet alpine pastures above the
  treeline) under MTB and hiking pressure.  Here snow is *noise*, and the
  indices of record are EVI and NDMI.

This module deliberately does **not** redefine EVI or NDMI — it imports them
from :mod:`src.features.spectral`, which already implements EVI with the
blue-band aerosol correction that avoids NDVI saturation.  What is genuinely
new here is NDSI, a snow-permissive scene mask, and the two alpine metrics
derived from them (snowline elevation, snowpack duration).

The masking asymmetry is the reason this module exists.  The rest of SNTO
treats Sentinel-2 SCL class 11 (snow/ice) as contamination and discards it —
see ``_SCL_BAD_VALUES`` in :mod:`src.ingestion.gee_adapter`.  For a snow index
that is exactly backwards, so the winter mask retains class 11 while the summer
mask drops it.  Using the wrong one silently produces an empty scene in winter
or a snow-inflated pasture signal in summer.

Scalar index functions follow the conventions of :mod:`src.features.spectral`:
surface reflectances in [0, 1], a zero-denominator guard returning 0.0, never
raising and never emitting NaN.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import numpy as np

from src.assets.models import AssetObservation
from src.config.constants import (
    ALPINE_EVI_HEALTHY_BASELINE,
    ALPINE_MIN_SNOW_PIXELS,
    ALPINE_NDMI_HEALTHY_BASELINE,
    ALPINE_SNOWLINE_PERCENTILE,
    ALPINE_W_EVI,
    ALPINE_W_NDMI,
    NDSI_NIR_WATER_FLOOR,
    NDSI_SNOW_THRESHOLD,
)
from src.features.spectral import compute_evi, compute_ndmi
from src.temporal.series_spec import SEASON_MONTHS

__all__ = [
    "AlpineFeatures",
    "AlpineSeason",
    "alpine_valid_mask",
    "compute_ndsi",
    "compute_snowline_elevation",
    "compute_snowpack_duration",
    "compute_soil_degradation",
    "extract_alpine_features",
    "is_snow_pixel",
    "scl_exclusion_set",
    "snow_mask",
    "compute_evi",
    "compute_ndmi",
]


# ── Season switch ────────────────────────────────────────────────────────────


class AlpineSeason(str, Enum):
    """The two operational modes of the Alpine Edition.

    Month membership is resolved against ``SEASON_MONTHS`` in
    :mod:`src.temporal.series_spec` rather than redefined here, so the alpine
    pipeline cannot drift from the rest of the temporal layer (note in
    particular that December belongs to the *following* year's winter).
    """

    WINTER = "winter"
    SUMMER = "summer"

    @property
    def months(self) -> tuple[int, ...]:
        """Calendar months aggregated by this season."""
        return SEASON_MONTHS[self.value]


# ── Scene masking ────────────────────────────────────────────────────────────
#
# Sentinel-2 Scene Classification Layer (SCL) codes:
#   0 no_data          1 saturated/defective   2 dark_area_pixels
#   3 cloud_shadow     4 vegetation            5 bare_soil / rock
#   6 water            7 unclassified          8 cloud_medium_probability
#   9 cloud_high_probability                  10 thin_cirrus
#  11 snow / ice
#
# Both alpine sets retain class 5 (bare soil / rock), which is ubiquitous above
# the treeline and would otherwise erase most of the study area, and class 7
# (unclassified), matching the deliberate choice in calculate_delta_ehs.py.

_ALPINE_SCL_EXCLUDE_WINTER: frozenset[int] = frozenset({0, 1, 3, 6, 8, 9, 10})
"""Winter exclusions — snow (11) is RETAINED because it is the signal.

Water (6) is excluded because it mimics snow in NDSI; cloud, cirrus and shadow
are excluded as usual.
"""

_ALPINE_SCL_EXCLUDE_SUMMER: frozenset[int] = frozenset({0, 1, 3, 6, 8, 9, 10, 11})
"""Summer exclusions — snow (11) is DROPPED because residual snow and firn
patches would inflate the vegetation signal of the borreguiles."""


def scl_exclusion_set(season: AlpineSeason) -> frozenset[int]:
    """Return the SCL classes to exclude for the given season.

    Args:
        season: WINTER (snow is signal) or SUMMER (snow is noise).

    Returns:
        Frozen set of SCL class codes to treat as invalid.
    """
    if season is AlpineSeason.WINTER:
        return _ALPINE_SCL_EXCLUDE_WINTER
    return _ALPINE_SCL_EXCLUDE_SUMMER


def alpine_valid_mask(
    scl_array: np.ndarray,
    season: AlpineSeason,
    nodata_mask: Optional[np.ndarray] = None,
) -> np.ndarray:
    """Build a boolean validity mask for one alpine scene.

    Mirrors the staged exclusion pipeline used by ``calculate_delta_ehs.py``:
    nodata first, then SCL classes.  Callers layering a geometry mask (e.g.
    trail buffers) should AND it onto the result.

    The SCL band is 20 m while the reference grid is usually 10 m; resample it
    with ``Resampling.nearest`` *before* calling this — class codes must never
    be interpolated.

    Args:
        scl_array: SCL class codes, already aligned to the target grid.
        season: selects the snow-permissive or snow-excluding rule set.
        nodata_mask: optional boolean array, True where the reflectance bands
            carry nodata.  Those pixels are invalidated regardless of SCL.

    Returns:
        Boolean array, True where the pixel is usable for this season.
    """
    excluded = np.isin(scl_array, list(scl_exclusion_set(season)))
    valid = ~excluded
    if nodata_mask is not None:
        valid &= ~nodata_mask
    return valid


# ── Index formulas ───────────────────────────────────────────────────────────


def compute_ndsi(green: float, swir: float) -> float:
    """Normalized Difference Snow Index (Hall et al. 1995).

    NDSI = (GREEN – SWIR1) / (GREEN + SWIR1)

    Snow reflects strongly in the visible green and absorbs almost completely in
    the shortwave infrared, giving values well above 0.4, while rock, soil and
    vegetation stay low.  Liquid water shares this signature, so NDSI alone is
    not a snow test — see :func:`is_snow_pixel`.

    All inputs are surface reflectances in [0, 1].

    Args:
        green: Green reflectance (Sentinel-2 B03, 10 m).
        swir:  SWIR1 reflectance (Sentinel-2 B11, 20 m — resample to 10 m).

    Returns:
        NDSI in [-1, 1]; fresh snow is typically > 0.7.  Returns 0.0 when the
        denominator is zero.
    """
    denom = green + swir
    return (green - swir) / denom if denom != 0.0 else 0.0


def is_snow_pixel(
    ndsi: float,
    nir: float,
    threshold: float = NDSI_SNOW_THRESHOLD,
    nir_floor: float = NDSI_NIR_WATER_FLOOR,
) -> bool:
    """Classify a single pixel as snow.

    A high NDSI is necessary but not sufficient: open water and wet rock also
    score high.  The NIR floor is what separates them — snow remains reflective
    in the near infrared, whereas liquid water absorbs it almost entirely.  This
    matters in Sierra Nevada, where the glacial lagunas sit at exactly the
    elevations the snowline calculation cares about.

    Args:
        ndsi: NDSI value for the pixel.
        nir:  NIR reflectance (Sentinel-2 B08), in [0, 1].
        threshold: minimum NDSI for a snow candidate.
        nir_floor: minimum NIR reflectance; below this the pixel is water.

    Returns:
        True when the pixel is snow under both criteria.
    """
    return ndsi >= threshold and nir > nir_floor


def compute_soil_degradation(
    mean_evi: float,
    mean_ndmi: float,
    evi_baseline: float = ALPINE_EVI_HEALTHY_BASELINE,
    ndmi_baseline: float = ALPINE_NDMI_HEALTHY_BASELINE,
    w_evi: float = ALPINE_W_EVI,
    w_ndmi: float = ALPINE_W_NDMI,
) -> float:
    """Summer soil-degradation index for borreguiles, in [0, 1].

    A weighted deficit of greenness and moisture against healthy alpine-pasture
    baselines, following the same deficit-against-baseline shape as the
    operational EHS in ``calculate_delta_ehs.py``.  Higher means more degraded.

    This is a *relative* stress indicator, not a measured soil-loss quantity.
    Attributing it to trampling rather than to drought is the job of
    :mod:`src.spatial_causality.alpine_causality`, not of this function.

    Args:
        mean_evi: observed mean EVI over the summer window.
        mean_ndmi: observed mean NDMI over the summer window.
        evi_baseline: healthy borreguil EVI reference (must be > 0).
        ndmi_baseline: healthy borreguil NDMI reference (must be > 0).
        w_evi: weight of the EVI deficit.
        w_ndmi: weight of the NDMI deficit.

    Returns:
        Degradation index in [0, 1]; 0.0 when both baselines are non-positive.
    """
    total_weight = w_evi + w_ndmi
    if total_weight <= 0.0:
        return 0.0

    evi_deficit = (
        _clamp_unit((evi_baseline - mean_evi) / evi_baseline)
        if evi_baseline > 0.0
        else 0.0
    )
    ndmi_deficit = (
        _clamp_unit((ndmi_baseline - mean_ndmi) / ndmi_baseline)
        if ndmi_baseline > 0.0
        else 0.0
    )
    return (w_evi * evi_deficit + w_ndmi * ndmi_deficit) / total_weight


def _clamp_unit(value: float) -> float:
    """Clamp to [0, 1]."""
    return max(0.0, min(1.0, value))


# ── Raster-level snow metrics ────────────────────────────────────────────────


def snow_mask(
    ndsi_array: np.ndarray,
    nir_array: Optional[np.ndarray] = None,
    valid_mask: Optional[np.ndarray] = None,
    threshold: float = NDSI_SNOW_THRESHOLD,
    nir_floor: float = NDSI_NIR_WATER_FLOOR,
) -> np.ndarray:
    """Array counterpart of :func:`is_snow_pixel`.

    Args:
        ndsi_array: NDSI raster.
        nir_array: optional NIR raster for water rejection.  When omitted the
            result is an NDSI-only candidate mask and *will* include water.
        valid_mask: optional boolean scene mask from :func:`alpine_valid_mask`.
        threshold: minimum NDSI.
        nir_floor: minimum NIR reflectance.

    Returns:
        Boolean array, True where the pixel is classified as snow.
    """
    with np.errstate(invalid="ignore"):
        mask = np.asarray(ndsi_array) >= threshold
    mask &= np.isfinite(ndsi_array)

    if nir_array is not None:
        with np.errstate(invalid="ignore"):
            mask &= np.asarray(nir_array) > nir_floor

    if valid_mask is not None:
        mask &= valid_mask

    return mask


def compute_snowline_elevation(
    ndsi_array: np.ndarray,
    dem_array: np.ndarray,
    nir_array: Optional[np.ndarray] = None,
    valid_mask: Optional[np.ndarray] = None,
    percentile: float = ALPINE_SNOWLINE_PERCENTILE,
    min_snow_pixels: int = ALPINE_MIN_SNOW_PIXELS,
    threshold: float = NDSI_SNOW_THRESHOLD,
) -> Optional[float]:
    """Estimate the regional snowline in metres above sea level.

    The snowline is reported as a low percentile of the elevation distribution
    of snow pixels rather than the strict minimum, which in practice is set by
    a handful of shaded pixels in north-facing ravines and is not a defensible
    regional figure.

    ``dem_array`` must already be co-registered with ``ndsi_array`` on the same
    grid — the Copernicus DEM-30 window returned by
    ``src.geospatial.geometry.fetch_dem_window`` needs resampling to the
    Sentinel-2 10 m grid before it is passed here.

    Args:
        ndsi_array: NDSI raster.
        dem_array: elevation raster (m.a.s.l.), same shape as ``ndsi_array``.
        nir_array: optional NIR raster for water rejection.
        valid_mask: optional boolean scene mask.
        percentile: percentile of snow-pixel elevations to report.
        min_snow_pixels: below this count the estimate is suppressed.
        threshold: minimum NDSI for a snow candidate.

    Returns:
        Snowline elevation in metres, or ``None`` when too few snow pixels
        survive masking to support an estimate.

    Raises:
        ValueError: if ``dem_array`` and ``ndsi_array`` have different shapes.
    """
    ndsi = np.asarray(ndsi_array)
    dem = np.asarray(dem_array)
    if ndsi.shape != dem.shape:
        raise ValueError(
            f"ndsi_array shape {ndsi.shape} does not match "
            f"dem_array shape {dem.shape}"
        )

    mask = snow_mask(
        ndsi,
        nir_array=nir_array,
        valid_mask=valid_mask,
        threshold=threshold,
    )
    mask &= np.isfinite(dem)

    elevations = dem[mask]
    if elevations.size < min_snow_pixels:
        return None

    return float(np.percentile(elevations, percentile))


def compute_snowpack_duration(
    ndsi_series: list[float],
    threshold: float = NDSI_SNOW_THRESHOLD,
) -> int:
    """Count the periods in a series whose composite NDSI indicates snow cover.

    Expressed in *periods*, not days: with the monthly cadence of ``SeriesSpec``
    a return value of 4 means four snow-covered months.  ``NaN`` entries are
    gaps (masked-out composites) and are not counted as snow-free — they are
    simply not counted at all, so callers comparing seasons across years should
    also check how many periods were observed.

    Args:
        ndsi_series: NDSI values ordered chronologically; may contain NaN.
        threshold: minimum NDSI for a period to count as snow-covered.

    Returns:
        Number of periods at or above the threshold.
    """
    return sum(
        1
        for value in ndsi_series
        if value is not None and np.isfinite(value) and value >= threshold
    )


# ── Dual-season feature extraction ───────────────────────────────────────────


@dataclass(frozen=True)
class AlpineFeatures:
    """Per-asset, per-season alpine feature vector.

    Follows the optional-index convention of
    :class:`src.features.spectral.SpectralFeatures`: an index that has no
    observations reports ``None`` for its mean and an empty series, rather than
    a zero that would read as a measurement.  Fields belonging to the other
    season are always ``None``.
    """

    asset_id: str
    season: AlpineSeason
    n_observations: int

    # Winter mode
    mean_ndsi: Optional[float] = None
    ndsi_series: list[float] = field(default_factory=list)
    snowpack_duration_periods: Optional[int] = None
    snowline_elevation_m: Optional[float] = None

    # Summer mode
    mean_evi: Optional[float] = None
    evi_series: list[float] = field(default_factory=list)
    mean_ndmi: Optional[float] = None
    ndmi_series: list[float] = field(default_factory=list)
    soil_degradation_index: Optional[float] = None


def extract_alpine_features(
    observations: list[AssetObservation],
    season: AlpineSeason,
    snowline_elevation_m: Optional[float] = None,
) -> AlpineFeatures:
    """Aggregate observations into a season-specific alpine feature vector.

    The season switch is the point of this function: winter reports snow
    metrics and summer reports pasture-condition metrics, from the same
    observation stream, with no overlap in the fields populated.

    Observations outside the requested season's months are ignored.  Snowline
    is a raster-derived quantity that cannot be recovered from per-asset scalar
    observations, so it is passed in by the caller (see
    :func:`compute_snowline_elevation`) rather than computed here.

    Args:
        observations: monthly observations for a single asset.
        season: WINTER or SUMMER.
        snowline_elevation_m: optional snowline for the winter vector.

    Returns:
        Populated :class:`AlpineFeatures`.

    Raises:
        ValueError: if ``observations`` is empty, or if none of them fall in
            the requested season.
    """
    if not observations:
        raise ValueError("Cannot extract features from an empty observation list.")

    months = season.months
    seasonal = [o for o in observations if o.month in months]
    if not seasonal:
        raise ValueError(
            f"No observations fall in season '{season.value}' "
            f"(months {months}); cannot extract alpine features."
        )

    asset_id = seasonal[0].asset_id

    if season is AlpineSeason.WINTER:
        ndsi_values = [o.ndsi for o in seasonal if o.ndsi is not None]
        if ndsi_values:
            mean_ndsi: Optional[float] = sum(ndsi_values) / len(ndsi_values)
            ndsi_series = [
                o.ndsi if o.ndsi is not None else float("nan") for o in seasonal
            ]
            duration: Optional[int] = compute_snowpack_duration(ndsi_series)
        else:
            mean_ndsi = None
            ndsi_series = []
            duration = None

        return AlpineFeatures(
            asset_id=asset_id,
            season=season,
            n_observations=len(seasonal),
            mean_ndsi=mean_ndsi,
            ndsi_series=ndsi_series,
            snowpack_duration_periods=duration,
            snowline_elevation_m=snowline_elevation_m,
        )

    evi_values = [o.evi for o in seasonal if o.evi is not None]
    if evi_values:
        mean_evi: Optional[float] = sum(evi_values) / len(evi_values)
        evi_series = [o.evi if o.evi is not None else float("nan") for o in seasonal]
    else:
        mean_evi = None
        evi_series = []

    ndmi_series = [o.ndmi for o in seasonal]
    mean_ndmi = sum(ndmi_series) / len(ndmi_series)

    degradation = (
        compute_soil_degradation(mean_evi, mean_ndmi) if mean_evi is not None else None
    )

    return AlpineFeatures(
        asset_id=asset_id,
        season=season,
        n_observations=len(seasonal),
        mean_evi=mean_evi,
        evi_series=evi_series,
        mean_ndmi=mean_ndmi,
        ndmi_series=ndmi_series,
        soil_degradation_index=degradation,
    )
