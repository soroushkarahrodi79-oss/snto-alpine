"""
SNTO Alpine Edition — Alpine spatial causality (Sierra Nevada pilot)
====================================================================
Distinguishing MTB/hiking rutting from macro-climate drying in high mountain.

The base Spatial Causality Module (:mod:`src.spatial_causality.analyzer`)
compares a 0–50 m trail core against a 200–1000 m landscape annulus and asks
whether degradation is localized or landscape-wide.  That comparison rests on
an assumption that quietly fails above the treeline: that the control annulus
is ecologically equivalent to the corridor.

In Sierra Nevada a 1 km annulus around a trail at 2,600 m can span from 2,200 m
pine forest to 3,000 m periglacial rock.  Vegetation vigour there is governed by
elevation far more strongly than by trampling, so a naive annulus comparison
attributes an *elevation gradient* to mountain bikers — or, just as bad, masks
real rutting behind an annulus that happens to sit lower and greener.

This module fixes the confound with two changes:

* **A tighter control zone** — 200–500 m rather than 200–1000 m.
* **Altitude matching** — the annulus is intersected with the DEM elevation
  band of the trail itself, so the control really is *untrampled alpine
  baseline at the same altitude*.

The attribution then answers the question a park manager actually has: is this
particular corridor losing vegetation faster than identical terrain 300 m away
that nobody rides on?  If yes, and the terrain is steep enough for runoff to
concentrate, it is rutting and a restoration budget is justified.  If the
control is degrading just as fast, the driver is regional drought and local
spending will not fix it.

Evidence provenance follows the base module exactly: a result derived from
simulated zones stays SIMULATED and therefore, per
:mod:`src.platform.evidence`, supports no decision on its own.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np
from shapely.geometry import Polygon

from src.features.alpine_spectral import AlpineFeatures, AlpineSeason
from src.geospatial.alpine_dem import ALPINE_STEEP_SLOPE_DEG
from src.geospatial.geometry import _DEFAULT_BUFFER_CRS
from src.platform.evidence import EvidenceClass
from src.spatial_causality.analyzer import (
    _SIG_LANDSCAPE,
    _SIG_LOCALIZED,
    CORE_OUTER_M,
    evidence_class_for_source,
)

logger = logging.getLogger(__name__)

__all__ = [
    "ALPINE_CONTROL_INNER_M",
    "ALPINE_CONTROL_OUTER_M",
    "ALPINE_ELEVATION_BAND_M",
    "ALPINE_LOCAL_OUTER_M",
    "AlpineAttribution",
    "altitude_matched_control_zone",
    "compute_attribution_index",
    "compute_mtb_attribution",
]

# ── Zone geometry (metres) ───────────────────────────────────────────────────

ALPINE_LOCAL_OUTER_M: int = CORE_OUTER_M   # 50 m — inherited trail corridor
ALPINE_CONTROL_INNER_M: int = 200
ALPINE_CONTROL_OUTER_M: int = 500
ALPINE_ELEVATION_BAND_M: float = 50.0
"""Half-width of the elevation band the control zone is restricted to.

±50 m around the trail's mean elevation.  Wide enough to retain usable pixel
counts on steep terrain where a narrow band would empty the control zone;
narrow enough that the vegetation belt does not change within it.
"""

# ── Classification thresholds ────────────────────────────────────────────────
# Numerically aligned with the base SCM (_SIG_LOCALIZED 0.15 / _SIG_LANDSCAPE
# 0.07) so both modules stay on one calibration surface, even though the
# quantity differs — see compute_attribution_index for why this is a difference
# of degradation indices rather than the base module's ratio.
_ATTRIBUTION_RUTTING: float = _SIG_LOCALIZED    # 0.15 — excess → anthropogenic
_ATTRIBUTION_CLIMATE: float = _SIG_LANDSCAPE    # 0.07 — below → macro-climate
_ATTRIBUTION_HIGH_CONFIDENCE: float = 0.25

CLASSIFICATION_RUTTING = "ANTHROPOGENIC_RUTTING"
CLASSIFICATION_CLIMATE = "MACROCLIMATE_DRIVEN"
CLASSIFICATION_MIXED = "MIXED"


@dataclass(frozen=True)
class AlpineAttribution:
    """Outcome of an alpine MTB-vs-climate attribution.

    Mirrors the shape of :class:`~src.spatial_causality.analyzer.SpatialCausalityResult`
    (classification / confidence / rationale / plain language / evidence class)
    so downstream consumers can treat the two interchangeably.
    """

    asset_id: str
    classification: str          # ANTHROPOGENIC_RUTTING | MACROCLIMATE_DRIVEN | MIXED
    confidence: str              # HIGH | MODERATE | LOW
    attribution_index: float
    local_degradation: float
    control_degradation: float
    mean_slope_deg: float
    slope_gate_passed: bool
    technical_rationale: str
    plain_language: str
    management_implication: str
    n_observations: int
    data_source: str
    evidence_class: EvidenceClass = EvidenceClass.SIMULATED


def compute_attribution_index(
    local_degradation: float,
    control_degradation: float,
) -> float:
    """Excess degradation in the trail corridor over the altitude-matched control.

    Returned as a plain **difference**, not the ratio the base module's SIG uses.
    Both inputs are already normalised deficits in [0, 1]
    (:func:`src.features.alpine_spectral.compute_soil_degradation`), so a
    difference is directly interpretable, bounded in [-1, 1], and — critically —
    numerically stable.  A ratio would divide by the control's degradation, which
    in a healthy untrampled borreguil is legitimately near zero and would turn
    ordinary noise into an unbounded attribution score.

    Args:
        local_degradation: degradation index of the 0–50 m corridor.
        control_degradation: degradation index of the altitude-matched control.

    Returns:
        Excess degradation in [-1, 1]; positive means the corridor is worse.
    """
    return local_degradation - control_degradation


def altitude_matched_control_zone(
    trail_geom_metric,
    dem_array: Optional[np.ndarray] = None,
    dem_transform: Optional[object] = None,
    dem_crs: Optional[object] = None,
    inner_m: int = ALPINE_CONTROL_INNER_M,
    outer_m: int = ALPINE_CONTROL_OUTER_M,
    band_m: float = ALPINE_ELEVATION_BAND_M,
    target_crs: str = _DEFAULT_BUFFER_CRS,
) -> Polygon:
    """Build the untrampled control zone at the trail's own altitude.

    Two stages:

    1. An annulus between ``inner_m`` and ``outer_m`` around the trail — far
       enough out to be untrampled, close enough to share aspect, geology and
       weather with the corridor.
    2. Intersection with the DEM elevation band ``trail_mean_elev ± band_m``,
       which is what removes the elevation confound.

    Degrades gracefully in the house style: without a DEM, or when the elevation
    band does not intersect the annulus (a trail on a narrow ridge, where no
    nearby terrain shares its elevation), it returns the plain annulus and logs.
    The caller can detect that case by the absence of an elevation restriction
    in the returned area.

    Args:
        trail_geom_metric: Shapely LineString in ``target_crs`` (metric).
        dem_array: elevation window from ``fetch_dem_window``, or None.
        dem_transform: affine transform matching ``dem_array``.
        dem_crs: CRS of ``dem_array``.
        inner_m: inner radius of the control annulus.
        outer_m: outer radius of the control annulus.
        band_m: half-width of the elevation band.
        target_crs: metric CRS of the trail and of the returned polygon.

    Returns:
        Shapely Polygon (possibly a MultiPolygon-backed union) in ``target_crs``.

    Raises:
        ValueError: if ``inner_m`` is not smaller than ``outer_m``.
    """
    if inner_m >= outer_m:
        raise ValueError(
            f"inner_m ({inner_m}) must be smaller than outer_m ({outer_m})."
        )

    annulus = trail_geom_metric.buffer(outer_m).difference(
        trail_geom_metric.buffer(inner_m)
    )

    if dem_array is None or dem_transform is None or dem_crs is None:
        logger.info(
            "No DEM supplied; control zone is a plain %d–%d m annulus "
            "and is NOT altitude-matched.",
            inner_m,
            outer_m,
        )
        return annulus

    try:
        band_geom = _elevation_band_geometry(
            trail_geom_metric,
            dem_array,
            dem_transform,
            dem_crs,
            band_m,
            target_crs,
        )
    except Exception as exc:  # pragma: no cover - defensive, mirrors house style
        logger.warning(
            "Elevation-band construction failed (%s); "
            "returning un-matched annulus.",
            exc,
        )
        return annulus

    if band_geom is None or band_geom.is_empty:
        logger.warning(
            "Elevation band ±%.0f m is empty; returning un-matched annulus.",
            band_m,
        )
        return annulus

    matched = annulus.intersection(band_geom)
    if matched.is_empty:
        logger.warning(
            "Elevation band ±%.0f m does not intersect the %d–%d m annulus "
            "(ridge trail?); returning un-matched annulus.",
            band_m,
            inner_m,
            outer_m,
        )
        return annulus

    return matched


def _elevation_band_geometry(
    trail_geom_metric,
    dem_array: np.ndarray,
    dem_transform: object,
    dem_crs: object,
    band_m: float,
    target_crs: str,
):
    """Polygonise the DEM cells within ±``band_m`` of the trail's mean elevation."""
    import rasterio.features
    from pyproj import CRS as ProjCRS
    from pyproj import Transformer
    from shapely.geometry import shape as shapely_shape
    from shapely.ops import transform as shapely_transform
    from shapely.ops import unary_union

    trail_crs_obj = ProjCRS.from_user_input(target_crs)
    dem_crs_obj = ProjCRS.from_user_input(dem_crs)

    if not trail_crs_obj.equals(dem_crs_obj):
        to_dem = Transformer.from_crs(trail_crs_obj, dem_crs_obj, always_xy=True)
        trail_in_dem = shapely_transform(to_dem.transform, trail_geom_metric)
    else:
        trail_in_dem = trail_geom_metric

    mean_elev = _mean_elevation_along_trail(trail_in_dem, dem_array, dem_transform)
    if mean_elev is None:
        return None

    lo, hi = mean_elev - band_m, mean_elev + band_m
    band_mask = np.isfinite(dem_array) & (dem_array >= lo) & (dem_array <= hi)
    if not band_mask.any():
        return None

    polys = [
        shapely_shape(geom)
        for geom, value in rasterio.features.shapes(
            band_mask.astype(np.uint8),
            mask=band_mask,
            transform=dem_transform,
        )
        if value == 1
    ]
    if not polys:
        return None

    band_geom = unary_union(polys)

    if not trail_crs_obj.equals(dem_crs_obj):
        to_target = Transformer.from_crs(dem_crs_obj, trail_crs_obj, always_xy=True)
        band_geom = shapely_transform(to_target.transform, band_geom)

    return band_geom


def _mean_elevation_along_trail(
    trail_in_dem_crs,
    dem_array: np.ndarray,
    dem_transform: object,
    n_samples: int = 12,
) -> Optional[float]:
    """Mean elevation (m.a.s.l.) sampled at equidistant points along a trail."""
    from affine import Affine

    tx: Affine = dem_transform  # type: ignore[assignment]
    h, w = dem_array.shape

    total = 0.0
    n_valid = 0
    for i in range(n_samples):
        fraction = i / max(n_samples - 1, 1)
        pt = trail_in_dem_crs.interpolate(fraction, normalized=True)
        col = int(round((pt.x - tx.c) / tx.a))
        row = int(round((pt.y - tx.f) / tx.e))
        if 0 <= row < h and 0 <= col < w:
            value = float(dem_array[row, col])
            if np.isfinite(value):
                total += value
                n_valid += 1

    return total / n_valid if n_valid else None


def compute_mtb_attribution(
    local: AlpineFeatures,
    control: AlpineFeatures,
    mean_slope_deg: float,
    data_source: str = "scm_simulated:alpine",
    steep_slope_deg: float = ALPINE_STEEP_SLOPE_DEG,
) -> AlpineAttribution:
    """Attribute summer degradation to trail use or to macro-climate.

    Two criteria, mirroring the two-criterion structure of
    ``SpatialCausalityAnalyzer._classify``:

    * **Excess degradation** — the corridor must be measurably worse than the
      altitude-matched control (:func:`compute_attribution_index`).
    * **Slope gate** — the terrain must be steep enough for concentrated runoff
      to cut ruts.  On a flat borreguil, MTB traffic compacts but does not
      channel, so excess degradation there is not *rutting* and should not be
      sold to a budget holder as such.

    Both must hold for ``ANTHROPOGENIC_RUTTING``.  When the corridor and its
    control degrade alike, the driver is regional and local restoration money
    will not change the outcome — that is ``MACROCLIMATE_DRIVEN``.

    Args:
        local: summer features for the 0–50 m corridor.
        control: summer features for the altitude-matched control zone.
        mean_slope_deg: mean trail slope from
            :func:`src.geospatial.alpine_dem.sample_slope_along_trail`.
        data_source: provenance tag; decides the evidence class exactly as in
            the base SCM (anything containing "simulat" stays SIMULATED).
        steep_slope_deg: slope above which runoff is assumed to concentrate.

    Returns:
        Populated :class:`AlpineAttribution`.

    Raises:
        ValueError: if either feature vector is not a SUMMER vector, or if
            either lacks a soil degradation index.
    """
    for label, features in (("local", local), ("control", control)):
        if features.season is not AlpineSeason.SUMMER:
            raise ValueError(
                f"{label} features must be SUMMER "
                f"(got '{features.season.value}'); alpine attribution is a "
                "growing-season analysis."
            )
        if features.soil_degradation_index is None:
            raise ValueError(
                f"{label} features carry no soil_degradation_index "
                "(EVI missing); cannot attribute degradation."
            )

    local_deg = local.soil_degradation_index
    control_deg = control.soil_degradation_index
    index = compute_attribution_index(local_deg, control_deg)
    slope_ok = bool(np.isfinite(mean_slope_deg) and mean_slope_deg >= steep_slope_deg)

    classification, confidence = _classify_alpine(index, slope_ok)

    technical = (
        f"Local degradation {local_deg:.3f} vs altitude-matched control "
        f"{control_deg:.3f} (±{ALPINE_ELEVATION_BAND_M:.0f} m band, "
        f"{ALPINE_CONTROL_INNER_M}–{ALPINE_CONTROL_OUTER_M} m annulus); "
        f"attribution index {index:+.3f}; mean slope {mean_slope_deg:.1f}° "
        f"({'above' if slope_ok else 'below'} the {steep_slope_deg:.0f}° "
        f"runoff-concentration threshold)."
    )

    if classification == CLASSIFICATION_RUTTING:
        plain = (
            "El corredor del sendero se degrada notablemente más que el terreno "
            "equivalente a la misma altitud, y la pendiente es suficiente para "
            "que la escorrentía abra roderas. El uso recreativo es el factor "
            "dominante."
        )
        implication = (
            "Intervención local justificada: estabilización del firme y drenaje "
            "transversal en los tramos de mayor pendiente."
        )
    elif classification == CLASSIFICATION_CLIMATE:
        plain = (
            "El corredor y el terreno de control se degradan a un ritmo similar. "
            "El patrón apunta a sequía regional, no al uso del sendero."
        )
        implication = (
            "La restauración local no corregiría la causa. Priorizar seguimiento "
            "y medidas a escala de macizo."
        )
    else:
        plain = (
            "Hay indicios de exceso de degradación en el corredor, pero no "
            "concluyentes: o la señal es débil o la pendiente no basta para "
            "atribuirla a roderas."
        )
        implication = (
            "Mantener seguimiento y reforzar la evidencia antes de comprometer "
            "presupuesto de restauración."
        )

    return AlpineAttribution(
        asset_id=local.asset_id,
        classification=classification,
        confidence=confidence,
        attribution_index=round(index, 5),
        local_degradation=round(local_deg, 5),
        control_degradation=round(control_deg, 5),
        mean_slope_deg=round(float(mean_slope_deg), 2)
        if np.isfinite(mean_slope_deg)
        else 0.0,
        slope_gate_passed=slope_ok,
        technical_rationale=technical,
        plain_language=plain,
        management_implication=implication,
        n_observations=min(local.n_observations, control.n_observations),
        data_source=data_source,
        evidence_class=evidence_class_for_source(data_source),
    )


def _classify_alpine(index: float, slope_gate_passed: bool) -> tuple[str, str]:
    """Two-criterion classification: excess degradation × slope gate."""
    if index >= _ATTRIBUTION_RUTTING and slope_gate_passed:
        confidence = "HIGH" if index >= _ATTRIBUTION_HIGH_CONFIDENCE else "MODERATE"
        return CLASSIFICATION_RUTTING, confidence

    if index < _ATTRIBUTION_CLIMATE:
        confidence = "HIGH" if index <= 0.0 else "MODERATE"
        return CLASSIFICATION_CLIMATE, confidence

    return CLASSIFICATION_MIXED, "LOW"
