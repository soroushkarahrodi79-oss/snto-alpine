"""
SNTO Alpine Edition — Public administration ROI & budget engine
===============================================================
Translating ecological evidence into the two numbers a public budget holder
actually decides on: what restoration costs, and what is lost by not doing it.

The base platform already prices interventions — ``tis_engine.py`` applies the
TRAGSA linear rate of €15.50/m, scaled by priority and by the SCM causal factor.
That rate, however, is a lowland tariff. It assumes vehicle access, a full
working season and machine placement, none of which hold above 2,000 m in
Sierra Nevada, where the restoration window is short, haulage may be by
helicopter or pack animal, and steep ground is worked by hand.

This module therefore adds a slope-dependent multiplier, and pairs the cost with
the regional economy the trail supports: the hospitality jobs and summer
tourism revenue that depend on the sector staying open. The output is a single
sentence a director can put in front of a budget committee.

**Provenance discipline.** The jobs and revenue figures here are proxy
estimates, not INE/ALMUDENA observations — real municipal indicators live in
:mod:`src.socioeconomic`. Every statement therefore carries an
:class:`~src.platform.evidence.EvidenceClass`, and per the project's evidence
doctrine a SIMULATED statement supports no decision on its own. Nothing in this
module may be presented as a tendered price or a validated employment figure.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.config.constants import (
    ALPINE_COST_MAX_FACTOR,
    ALPINE_COST_SLOPE_MIN_DEG,
    ALPINE_SPEND_PER_VISITOR_EUR,
    ALPINE_VISITORS_PER_JOB,
    HP_SLOPE_MAX_DEG,
    TRAGSA_BASE_RATE_EUR_PER_M,
)
from src.platform.evidence import EvidenceClass

__all__ = [
    "PublicROIStatement",
    "RestorationCost",
    "build_public_roi_statement",
    "compute_restoration_cost",
    "estimate_dependent_jobs",
    "estimate_tourism_revenue",
    "slope_cost_factor",
]


@dataclass(frozen=True)
class RestorationCost:
    """Cost of restoring one trail, with its derivation exposed."""

    asset_id: str
    length_m: float
    mean_slope_deg: float
    base_rate_eur_per_m: float
    slope_factor: float
    total_eur: float

    @property
    def effective_rate_eur_per_m(self) -> float:
        """Slope-adjusted unit rate actually applied."""
        return self.base_rate_eur_per_m * self.slope_factor


@dataclass(frozen=True)
class PublicROIStatement:
    """A decision-ready ROI statement for one trail."""

    asset_id: str
    asset_name: str
    restoration_cost: RestorationCost
    dependent_jobs: float
    tourism_revenue_eur: float
    evidence_class: EvidenceClass

    @property
    def statement(self) -> str:
        """The institutional one-liner, in English."""
        return (
            f"Intervening on {self.asset_name} prevents "
            f"€{self.restoration_cost.total_eur:,.0f} in structural soil loss "
            f"while safeguarding {self.dependent_jobs:,.1f} local jobs and "
            f"€{self.tourism_revenue_eur:,.0f} in Sierra Nevada summer "
            f"tourism revenue."
        )

    @property
    def statement_es(self) -> str:
        """Spanish rendering, for the dashboard (which has no i18n layer)."""
        return (
            f"Intervenir en {self.asset_name} evita "
            f"{self.restoration_cost.total_eur:,.0f} € de pérdida estructural "
            f"de suelo y protege {self.dependent_jobs:,.1f} empleos locales y "
            f"{self.tourism_revenue_eur:,.0f} € de ingresos por turismo estival "
            f"en Sierra Nevada."
        )

    @property
    def is_decision_grade(self) -> bool:
        """Whether this statement may stand alone in a funding decision.

        False for SIMULATED/SYNTHETIC evidence, which the project's evidence
        gating matrix admits for no decision use.
        """
        return self.evidence_class in (EvidenceClass.REAL, EvidenceClass.CALIBRATED)


def slope_cost_factor(
    mean_slope_deg: float,
    min_slope_deg: float = ALPINE_COST_SLOPE_MIN_DEG,
    max_slope_deg: float = HP_SLOPE_MAX_DEG,
    max_factor: float = ALPINE_COST_MAX_FACTOR,
) -> float:
    """Multiplier on the TRAGSA base rate for high-mountain terrain.

    Piecewise-linear and monotonic: 1.0 up to ``min_slope_deg``, ramping to
    ``max_factor`` at ``max_slope_deg`` and flat above it. Capping rather than
    extrapolating past 30° is deliberate — beyond that slope the intervention
    type changes entirely (anchored structures, not surface restoration) and a
    linear €/m model no longer describes the work.

    Args:
        mean_slope_deg: mean trail slope in degrees.
        min_slope_deg: slope below which the flat-terrain rate applies.
        max_slope_deg: slope at which the multiplier saturates.
        max_factor: multiplier at and above ``max_slope_deg``.

    Returns:
        Multiplier >= 1.0. Non-finite or negative slope yields 1.0.
    """
    if not _is_finite(mean_slope_deg) or mean_slope_deg <= min_slope_deg:
        return 1.0
    if mean_slope_deg >= max_slope_deg:
        return max_factor

    span = max_slope_deg - min_slope_deg
    if span <= 0.0:
        return max_factor

    ratio = (mean_slope_deg - min_slope_deg) / span
    return 1.0 + ratio * (max_factor - 1.0)


def compute_restoration_cost(
    asset_id: str,
    length_m: float,
    mean_slope_deg: float = 0.0,
    base_rate_eur_per_m: float = TRAGSA_BASE_RATE_EUR_PER_M,
) -> RestorationCost:
    """Price the restoration of one alpine trail.

    ``cost = length_m × base_rate × slope_factor(mean_slope_deg)``

    Deliberately *not* scaled by priority score or SCM causal factor — those
    belong to budget allocation (``tis_engine.py``), which decides how much of a
    known cost to fund. Mixing them here would make the engineering cost of a
    trail depend on how urgent it is, which it does not.

    Args:
        asset_id: trail identifier.
        length_m: trail length in metres (must be >= 0).
        mean_slope_deg: mean slope from
            :func:`src.geospatial.alpine_dem.sample_slope_along_trail`.
        base_rate_eur_per_m: TRAGSA linear rate.

    Returns:
        Populated :class:`RestorationCost`.

    Raises:
        ValueError: if ``length_m`` is negative.
    """
    if length_m < 0.0:
        raise ValueError(f"length_m must be non-negative, got {length_m}.")

    factor = slope_cost_factor(mean_slope_deg)
    total = length_m * base_rate_eur_per_m * factor

    return RestorationCost(
        asset_id=asset_id,
        length_m=float(length_m),
        mean_slope_deg=float(mean_slope_deg) if _is_finite(mean_slope_deg) else 0.0,
        base_rate_eur_per_m=base_rate_eur_per_m,
        slope_factor=round(factor, 4),
        total_eur=round(total, 2),
    )


def estimate_dependent_jobs(
    visitor_capacity_annual: int,
    visitors_per_job: int = ALPINE_VISITORS_PER_JOB,
    exposure: float = 1.0,
) -> float:
    """Hospitality jobs sustained by one trail's visitor flow.

    A proxy: annual visitors divided by the visitors needed to sustain one job,
    optionally scaled by an exposure fraction. ``exposure`` is where a real
    socioeconomic signal enters — pass
    ``src.socioeconomic.indicators.AssetRiskAgg.exposure()`` to weight the
    estimate by the municipality's actual dependence on tourism rather than
    assuming full exposure.

    Args:
        visitor_capacity_annual: annual visitors attributed to the trail.
        visitors_per_job: visitors sustaining one full-time job.
        exposure: fraction of that employment actually at stake, in [0, 1].

    Returns:
        Estimated jobs; 0.0 for non-positive inputs.
    """
    if visitor_capacity_annual <= 0 or visitors_per_job <= 0:
        return 0.0
    return (visitor_capacity_annual / visitors_per_job) * _clamp_unit(exposure)


def estimate_tourism_revenue(
    visitor_capacity_annual: int,
    spend_per_visitor_eur: float = ALPINE_SPEND_PER_VISITOR_EUR,
    exposure: float = 1.0,
) -> float:
    """Local hospitality revenue dependent on one trail.

    Args:
        visitor_capacity_annual: annual visitors attributed to the trail.
        spend_per_visitor_eur: average local spend per visitor.
        exposure: fraction of that revenue actually at stake, in [0, 1].

    Returns:
        Estimated revenue in euros; 0.0 for non-positive inputs.
    """
    if visitor_capacity_annual <= 0 or spend_per_visitor_eur <= 0.0:
        return 0.0
    return visitor_capacity_annual * spend_per_visitor_eur * _clamp_unit(exposure)


def build_public_roi_statement(
    asset_id: str,
    asset_name: str,
    length_m: float,
    visitor_capacity_annual: int,
    mean_slope_deg: float = 0.0,
    exposure: float = 1.0,
    evidence_class: EvidenceClass = EvidenceClass.SIMULATED,
    base_rate_eur_per_m: float = TRAGSA_BASE_RATE_EUR_PER_M,
    restoration_cost: Optional[RestorationCost] = None,
) -> PublicROIStatement:
    """Assemble the public ROI statement for one trail.

    Args:
        asset_id: trail identifier.
        asset_name: display name used in the statement.
        length_m: trail length in metres.
        visitor_capacity_annual: annual visitors attributed to the trail.
        mean_slope_deg: mean trail slope, driving the cost multiplier.
        exposure: fraction of dependent jobs and revenue at stake, in [0, 1].
        evidence_class: provenance of the underlying degradation evidence.
            Defaults to SIMULATED, the conservative assumption.
        base_rate_eur_per_m: TRAGSA linear rate.
        restoration_cost: pre-computed cost; when omitted it is derived from
            ``length_m`` and ``mean_slope_deg``.

    Returns:
        Populated :class:`PublicROIStatement`.
    """
    cost = restoration_cost or compute_restoration_cost(
        asset_id=asset_id,
        length_m=length_m,
        mean_slope_deg=mean_slope_deg,
        base_rate_eur_per_m=base_rate_eur_per_m,
    )

    return PublicROIStatement(
        asset_id=asset_id,
        asset_name=asset_name,
        restoration_cost=cost,
        dependent_jobs=round(
            estimate_dependent_jobs(visitor_capacity_annual, exposure=exposure), 2
        ),
        tourism_revenue_eur=round(
            estimate_tourism_revenue(visitor_capacity_annual, exposure=exposure), 2
        ),
        evidence_class=evidence_class,
    )


def _clamp_unit(value: float) -> float:
    """Clamp to [0, 1]."""
    return max(0.0, min(1.0, value))


def _is_finite(value: float) -> bool:
    """True when ``value`` is a finite real number."""
    return value == value and value not in (float("inf"), float("-inf"))
