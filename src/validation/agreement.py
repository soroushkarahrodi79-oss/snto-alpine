"""
SNTO — Satellite ↔ ground-truth agreement metrics (F5)
======================================================
Turns a field campaign into a defensible validation statement. Two analyses:

1. **Correlation** — Spearman rank correlation between the satellite stress
   score and the field degradation index at co-located plots. A strong positive
   rank correlation is the evidence that *"the satellite EHS tracks observed
   degradation"*.
2. **Control–Impact contrast (BACI-style)** — compares trail-corridor (impact)
   plots against control plots far from the trail in the same habitat. The
   effect size (Cliff's delta) and mean difference quantify how much more
   degraded the impacted corridor is than its control.

Pure functions, no SciPy dependency: Spearman and Cliff's delta are implemented
directly so the module runs anywhere the test suite does.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Sequence

from src.time_series.confidence import BootstrapCI, block_bootstrap_ci


def _rank(values: Sequence[float]) -> list[float]:
    """Average (fractional) ranks, handling ties."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0  # 1-based average rank for the tie group
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def _pearson(x: Sequence[float], y: Sequence[float]) -> float:
    mx, my = statistics.fmean(x), statistics.fmean(y)
    sx = sum((a - mx) ** 2 for a in x)
    sy = sum((b - my) ** 2 for b in y)
    if sx == 0 or sy == 0:
        return 0.0
    cov = sum((a - mx) * (b - my) for a, b in zip(x, y))
    return cov / (sx ** 0.5 * sy ** 0.5)


def spearman_correlation(x: Sequence[float], y: Sequence[float]) -> float:
    """Spearman rank correlation in [-1, 1]; 0.0 for <3 points or constant input."""
    if len(x) != len(y):
        raise ValueError("x and y must have equal length")
    if len(x) < 3:
        return 0.0
    return round(_pearson(_rank(x), _rank(y)), 4)


def cliffs_delta(a: Sequence[float], b: Sequence[float]) -> float:
    """Cliff's delta effect size in [-1, 1]: P(a>b) - P(a<b).

    Positive ⇒ group ``a`` tends to exceed group ``b``.
    """
    if not a or not b:
        return 0.0
    gt = sum(1 for x in a for y in b if x > y)
    lt = sum(1 for x in a for y in b if x < y)
    return round((gt - lt) / (len(a) * len(b)), 4)


@dataclass(frozen=True)
class AgreementReport:
    n: int
    spearman: float
    direction_ok: bool   # True when satellite stress rises with field degradation
    verdict: str


def validate_satellite_vs_field(
    pairs: Sequence[tuple[float, float]],
    strong: float = 0.6,
    moderate: float = 0.3,
) -> AgreementReport:
    """Spearman agreement between (satellite_stress, field_degradation) pairs.

    Both inputs follow the stress convention (high = degraded), so a positive
    correlation validates the satellite signal.
    """
    sat = [p[0] for p in pairs]
    field = [p[1] for p in pairs]
    rho = spearman_correlation(sat, field)
    if len(pairs) < 3:
        verdict = "insuficiente (se requieren >= 3 plots co-localizados)"
    elif rho >= strong:
        verdict = "concordancia fuerte: el satélite sigue la degradación observada"
    elif rho >= moderate:
        verdict = "concordancia moderada: señal consistente, ampliar muestra"
    elif rho > 0:
        verdict = "concordancia débil"
    else:
        verdict = "sin concordancia / dirección inesperada — revisar"
    return AgreementReport(
        n=len(pairs), spearman=rho, direction_ok=rho > 0, verdict=verdict,
    )


def bootstrap_spearman_ci(
    pairs: Sequence[tuple[float, float]],
    alpha: float = 0.05,
    n_boot: int = 1000,
    seed: int = 0,
) -> BootstrapCI:
    """Percentile CI for the satellite↔field Spearman ρ (issue #11's "con
    intervalos e incertidumbre" requirement).

    Field-validation plots are a cross-sectional sample, not a time series, so
    this reuses :func:`src.time_series.confidence.block_bootstrap_ci` with
    ``block_len=1`` — which degenerates the moving-block bootstrap to an
    ordinary i.i.d. resample-with-replacement, the correct bootstrap for
    independent plots, without introducing a second bootstrap implementation.

    Below 4 plots the underlying function returns a degenerate point interval
    (lower == upper == point) rather than fabricating a spread from too few
    resamples — consistent with :func:`validate_satellite_vs_field`'s own
    "insuficiente" floor at 3 plots.
    """
    return block_bootstrap_ci(
        list(pairs),
        statistic=lambda s: spearman_correlation([p[0] for p in s], [p[1] for p in s]),
        n_boot=n_boot,
        block_len=1,
        alpha=alpha,
        seed=seed,
    )


@dataclass(frozen=True)
class ContrastResult:
    n_impact: int
    n_control: int
    mean_impact: float
    mean_control: float
    delta: float            # mean_impact - mean_control
    cliffs_delta: float     # effect size, impact vs control
    impact_more_degraded: bool
    verdict: str


def control_impact_contrast(
    impact_values: Sequence[float],
    control_values: Sequence[float],
    large_effect: float = 0.474,   # Romano et al. (2006) "large" Cliff's delta
) -> ContrastResult:
    """BACI-style control–impact contrast of field degradation indices.

    Expectation under trail impact: impacted plots are more degraded than their
    controls (positive delta, positive Cliff's delta).
    """
    if not impact_values or not control_values:
        raise ValueError("both impact_values and control_values are required")
    mi = statistics.fmean(impact_values)
    mc = statistics.fmean(control_values)
    d = cliffs_delta(impact_values, control_values)
    delta = mi - mc
    if delta > 0 and abs(d) >= large_effect:
        verdict = "impacto claramente mayor que el control (efecto grande)"
    elif delta > 0:
        verdict = "impacto mayor que el control (efecto pequeño/moderado)"
    else:
        verdict = "sin gradiente de impacto frente al control"
    return ContrastResult(
        n_impact=len(impact_values),
        n_control=len(control_values),
        mean_impact=round(mi, 2),
        mean_control=round(mc, 2),
        delta=round(delta, 2),
        cliffs_delta=d,
        impact_more_degraded=delta > 0,
        verdict=verdict,
    )
