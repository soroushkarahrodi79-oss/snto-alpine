"""F5 — Field-validation schema and satellite↔terrain agreement metrics."""
from __future__ import annotations

import pytest

from src.validation import (
    ErosionClass,
    FieldObservation,
    cliffs_delta,
    control_impact_contrast,
    spearman_correlation,
    split_impact_control,
    validate_satellite_vs_field,
)
from src.validation.agreement import bootstrap_spearman_ci


def _obs(plot_id, is_control, **kw):
    base = dict(plot_id=plot_id, lat=40.8, lon=-3.9, distance_to_trail_m=0.0,
                is_control=is_control)
    base.update(kw)
    return FieldObservation(**base)


# ── Field schema ────────────────────────────────────────────────────────────

def test_degradation_index_combines_available_components():
    o = _obs("p1", False, soil_compaction_mpa=3.0, veg_cover_pct=0.0,
             erosion_class=ErosionClass.SEVERE)
    assert o.degradation_index() == 100.0   # all components maxed
    pristine = _obs("p2", True, soil_compaction_mpa=0.0, veg_cover_pct=100.0,
                    erosion_class=ErosionClass.NONE)
    assert pristine.degradation_index() == 0.0


def test_degradation_index_none_when_no_components():
    assert _obs("p3", False).degradation_index() is None


def test_split_impact_control():
    obs = [_obs("a", False), _obs("b", True), _obs("c", False)]
    impact, control = split_impact_control(obs)
    assert [o.plot_id for o in impact] == ["a", "c"]
    assert [o.plot_id for o in control] == ["b"]


# ── Correlation ───────────────────────────────────────────────────────────────

def test_spearman_perfect_monotonic():
    assert spearman_correlation([1, 2, 3, 4], [10, 20, 30, 40]) == 1.0
    assert spearman_correlation([1, 2, 3, 4], [40, 30, 20, 10]) == -1.0


def test_spearman_guards_small_or_constant():
    assert spearman_correlation([1, 2], [3, 4]) == 0.0
    assert spearman_correlation([5, 5, 5], [1, 2, 3]) == 0.0
    with pytest.raises(ValueError):
        spearman_correlation([1, 2, 3], [1, 2])


def test_validate_satellite_vs_field_strong_positive():
    pairs = [(10, 12), (30, 28), (55, 60), (80, 75), (95, 90)]
    rep = validate_satellite_vs_field(pairs)
    assert rep.n == 5
    assert rep.spearman >= 0.6 and rep.direction_ok
    assert "fuerte" in rep.verdict


def test_validate_flags_insufficient_sample():
    rep = validate_satellite_vs_field([(10, 12), (20, 25)])
    assert "insuficiente" in rep.verdict


# ── Control–Impact contrast (BACI) ────────────────────────────────────────────

def test_cliffs_delta_direction():
    assert cliffs_delta([5, 6, 7], [1, 2, 3]) == 1.0    # a wholly above b
    assert cliffs_delta([1, 2, 3], [5, 6, 7]) == -1.0


def test_control_impact_contrast_detects_large_effect():
    impact = [70, 75, 80, 65]    # degraded trail corridor
    control = [20, 25, 15, 30]   # pristine control plots
    res = control_impact_contrast(impact, control)
    assert res.impact_more_degraded is True
    assert res.delta > 0 and res.cliffs_delta == 1.0
    assert "efecto grande" in res.verdict


def test_control_impact_contrast_no_gradient():
    res = control_impact_contrast([30, 32, 28], [31, 29, 33])
    assert "sin gradiente" in res.verdict or res.impact_more_degraded is False


def test_control_impact_requires_both_groups():
    with pytest.raises(ValueError):
        control_impact_contrast([1, 2], [])


# ── Bootstrap CI for the Spearman agreement (issue #11) ──────────────────────


def test_bootstrap_spearman_ci_brackets_the_point_estimate():
    pairs = [(10, 12), (20, 22), (30, 28), (40, 45), (50, 48), (60, 65)]
    ci = bootstrap_spearman_ci(pairs, seed=0)
    assert ci.lower <= ci.point <= ci.upper


def test_bootstrap_spearman_ci_matches_the_point_spearman():
    pairs = [(10, 12), (20, 22), (30, 28), (40, 45), (50, 48), (60, 65)]
    ci = bootstrap_spearman_ci(pairs, seed=0)
    sat = [p[0] for p in pairs]
    field = [p[1] for p in pairs]
    assert ci.point == spearman_correlation(sat, field)


def test_bootstrap_spearman_ci_is_reproducible_for_a_fixed_seed():
    pairs = [(10, 12), (20, 22), (30, 28), (40, 45), (50, 48), (60, 65)]
    a = bootstrap_spearman_ci(pairs, seed=42)
    b = bootstrap_spearman_ci(pairs, seed=42)
    assert (a.lower, a.upper) == (b.lower, b.upper)


def test_bootstrap_spearman_ci_degenerates_below_four_plots():
    pairs = [(10, 12), (20, 22), (30, 28)]
    ci = bootstrap_spearman_ci(pairs)
    assert ci.lower == ci.upper == ci.point
