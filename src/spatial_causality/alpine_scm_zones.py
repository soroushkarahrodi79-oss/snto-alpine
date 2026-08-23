"""
SNTO Alpine Edition — executing observed SCM zones (Sierra Nevada pilot, issue #9)
====================================================================================
Wires :mod:`src.spatial_causality.alpine_causality`'s pure attribution math to
real monthly EVI/NDMI zone observations, with an **explicit** fallback when a
usable local/control pair does not exist.

This module is pure aggregation — no rasterio, no network I/O — so it is
testable without live data. :mod:`scripts.build_alpine_scm_zones` supplies the
per-month zonal means from the real pipeline (real trail geometry, real DEM,
real Sentinel-2 summer scenes).

Why an explicit fallback matters here specifically: silently classifying an
asset as ``MIXED``/``LOW`` when the control zone never had enough valid
pixels would look identical to a real ambiguous result. Issue #9's acceptance
criteria ask for the two to stay distinguishable, so a failed execution
returns ``classification=NO_VALID_CONTROL`` with a stated reason instead of a
number that merely happens to fall in the ambiguous band.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.assets.models import AssetObservation
from src.features.alpine_spectral import AlpineSeason, extract_alpine_features
from src.spatial_causality.alpine_causality import AlpineAttribution, compute_mtb_attribution

__all__ = [
    "MIN_SUMMER_OBSERVATIONS",
    "NO_VALID_CONTROL",
    "MonthlyZoneSignal",
    "ScmZoneOutcome",
    "build_summer_observations",
    "execute_scm_attribution",
]

NO_VALID_CONTROL = "NO_VALID_CONTROL"

# Below this many valid summer months, a mean over the series is one or two
# scenes dressed up as a trend. Two is the floor for "series" rather than
# "single observation" — matches the intent of MIN_VALID_PIXEL_PCT-style
# guards elsewhere in the alpine pipeline.
MIN_SUMMER_OBSERVATIONS: int = 2


@dataclass(frozen=True)
class MonthlyZoneSignal:
    """One month's zonal-mean spectral signal for one zone (local or control)."""

    year: int
    month: int
    evi: Optional[float]
    ndmi: Optional[float]
    ndvi: Optional[float] = None
    n_pixels: int = 0


@dataclass(frozen=True)
class ScmZoneOutcome:
    """Outcome of attempting to execute one asset's observed-zone attribution."""

    asset_id: str
    attribution: Optional[AlpineAttribution]
    classification: str
    control_altitude_matched: bool
    fallback_reason: Optional[str] = None


def build_summer_observations(
    asset_id: str, monthly: list[MonthlyZoneSignal], data_source: str
) -> list[AssetObservation]:
    """Real summer :class:`AssetObservation` records from monthly zone signals.

    Months whose EVI or NDMI could not be sampled (empty zone, insufficient
    pixels) are dropped rather than filled with a placeholder — a gap should
    read as absent, not as a fabricated zero. NDVI is a required
    ``AssetObservation`` field the alpine summer path itself does not read
    (:func:`extract_alpine_features` uses EVI, not NDVI); when a real NDVI
    zonal mean is available it is carried through anyway, and otherwise EVI
    stands in for it so the field holds a real vegetation value rather than a
    fabricated 0.0.
    """
    obs: list[AssetObservation] = []
    for m in monthly:
        if m.evi is None or m.ndmi is None:
            continue
        obs.append(
            AssetObservation(
                asset_id=asset_id,
                year=m.year,
                month=m.month,
                ndvi=m.ndvi if m.ndvi is not None else m.evi,
                ndmi=m.ndmi,
                evi=m.evi,
                data_source=data_source,
            )
        )
    return obs


def execute_scm_attribution(
    asset_id: str,
    local_monthly: list[MonthlyZoneSignal],
    control_monthly: list[MonthlyZoneSignal],
    mean_slope_deg: float,
    control_altitude_matched: bool,
    min_observations: int = MIN_SUMMER_OBSERVATIONS,
) -> ScmZoneOutcome:
    """Attribute one asset's summer degradation from observed zone signals.

    Two ways this can honestly fail to produce an attribution, both reported
    as ``NO_VALID_CONTROL`` with a stated reason rather than silently falling
    back to a plausible-looking number:

    * too few valid summer months in either zone (``min_observations`` floor);
    * a zone with observations but no usable EVI (all-cloud / all-gap season).

    Args:
        asset_id: asset identifier.
        local_monthly: per-month signals for the 0-50 m corridor.
        control_monthly: per-month signals for the altitude-matched control.
        mean_slope_deg: mean trail slope, from
            :func:`src.geospatial.alpine_dem.sample_slope_along_trail`.
        control_altitude_matched: whether the control zone actually
            intersected the trail's elevation band (vs. degrading to a plain
            un-matched annulus) — decides the ``data_source`` tag, which in
            turn decides how the result reads downstream (still REAL evidence
            either way; only the elevation confound guarantee differs).
        min_observations: minimum valid summer months required per zone.

    Returns:
        :class:`ScmZoneOutcome`.
    """
    local_source = (
        "scm_real:alpine" if control_altitude_matched else "scm_real:alpine_unmatched_control"
    )
    local_obs = build_summer_observations(asset_id, local_monthly, local_source)
    control_obs = build_summer_observations(asset_id, control_monthly, local_source)

    if len(local_obs) < min_observations or len(control_obs) < min_observations:
        return ScmZoneOutcome(
            asset_id=asset_id,
            attribution=None,
            classification=NO_VALID_CONTROL,
            control_altitude_matched=control_altitude_matched,
            fallback_reason=(
                f"insufficient summer observations (local={len(local_obs)}, "
                f"control={len(control_obs)}, need >= {min_observations})"
            ),
        )

    try:
        local_features = extract_alpine_features(local_obs, AlpineSeason.SUMMER)
        control_features = extract_alpine_features(control_obs, AlpineSeason.SUMMER)
    except ValueError as exc:
        return ScmZoneOutcome(
            asset_id=asset_id,
            attribution=None,
            classification=NO_VALID_CONTROL,
            control_altitude_matched=control_altitude_matched,
            fallback_reason=str(exc),
        )

    if (
        local_features.soil_degradation_index is None
        or control_features.soil_degradation_index is None
    ):
        return ScmZoneOutcome(
            asset_id=asset_id,
            attribution=None,
            classification=NO_VALID_CONTROL,
            control_altitude_matched=control_altitude_matched,
            fallback_reason="no usable EVI signal in local and/or control zone",
        )

    attribution = compute_mtb_attribution(
        local_features,
        control_features,
        mean_slope_deg=mean_slope_deg,
        data_source=local_source,
    )
    return ScmZoneOutcome(
        asset_id=asset_id,
        attribution=attribution,
        classification=attribution.classification,
        control_altitude_matched=control_altitude_matched,
        fallback_reason=None,
    )
