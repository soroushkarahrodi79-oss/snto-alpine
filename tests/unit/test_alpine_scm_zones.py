"""Unit tests for src.spatial_causality.alpine_scm_zones (issue #9)."""
from __future__ import annotations

from src.platform.evidence import EvidenceClass
from src.spatial_causality.alpine_causality import (
    CLASSIFICATION_CLIMATE,
    CLASSIFICATION_RUTTING,
)
from src.spatial_causality.alpine_scm_zones import (
    MIN_SUMMER_OBSERVATIONS,
    NO_VALID_CONTROL,
    MonthlyZoneSignal,
    build_summer_observations,
    execute_scm_attribution,
)


def _months(
    evi_values: list[float | None], ndmi: float = 0.20
) -> list[MonthlyZoneSignal]:
    return [
        MonthlyZoneSignal(
            year=2024, month=6 + i, evi=v, ndmi=ndmi if v is not None else None
        )
        for i, v in enumerate(evi_values)
    ]


def test_build_summer_observations_drops_months_with_no_evi() -> None:
    monthly = _months([0.30, None, 0.28])
    obs = build_summer_observations("sn-01", monthly, "scm_real:alpine")
    assert len(obs) == 2
    assert all(o.evi is not None for o in obs)


def test_build_summer_observations_backfills_ndvi_from_evi() -> None:
    monthly = [MonthlyZoneSignal(2024, 6, evi=0.31, ndmi=0.2, ndvi=None)]
    obs = build_summer_observations("sn-01", monthly, "scm_real:alpine")
    assert obs[0].ndvi == 0.31


def test_execute_attribution_rutting_case_is_real_and_matched() -> None:
    local = _months([0.10, 0.09, 0.11])   # degraded corridor (low EVI)
    control = _months([0.34, 0.35, 0.33])  # healthy altitude-matched control
    outcome = execute_scm_attribution(
        "sn-01", local, control, mean_slope_deg=26.0, control_altitude_matched=True,
    )
    assert outcome.classification == CLASSIFICATION_RUTTING
    assert outcome.attribution is not None
    assert outcome.attribution.evidence_class is EvidenceClass.REAL
    assert outcome.attribution.data_source == "scm_real:alpine"
    assert outcome.fallback_reason is None


def test_execute_attribution_climate_case_when_zones_track_together() -> None:
    local = _months([0.20, 0.19, 0.21])
    control = _months([0.21, 0.20, 0.20])
    outcome = execute_scm_attribution(
        "sn-02", local, control, mean_slope_deg=30.0, control_altitude_matched=True,
    )
    assert outcome.classification == CLASSIFICATION_CLIMATE


def test_unmatched_control_tags_a_different_data_source() -> None:
    local = _months([0.10, 0.09, 0.11])
    control = _months([0.34, 0.35, 0.33])
    outcome = execute_scm_attribution(
        "sn-03", local, control, mean_slope_deg=26.0, control_altitude_matched=False,
    )
    assert outcome.attribution is not None
    assert outcome.attribution.data_source == "scm_real:alpine_unmatched_control"
    assert outcome.attribution.evidence_class is EvidenceClass.REAL
    assert outcome.control_altitude_matched is False


def test_fallback_when_control_zone_never_had_enough_observations() -> None:
    local = _months([0.10, 0.09, 0.11])
    control = _months([None, None, 0.33])  # only one usable month
    assert MIN_SUMMER_OBSERVATIONS == 2
    outcome = execute_scm_attribution(
        "sn-04", local, control, mean_slope_deg=26.0, control_altitude_matched=True,
    )
    assert outcome.attribution is None
    assert outcome.classification == NO_VALID_CONTROL
    assert "insufficient" in outcome.fallback_reason
    assert outcome.control_altitude_matched is True


def test_fallback_when_local_zone_is_entirely_missing() -> None:
    local: list[MonthlyZoneSignal] = _months([None, None, None])
    control = _months([0.30, 0.31, 0.29])
    outcome = execute_scm_attribution(
        "sn-05", local, control, mean_slope_deg=26.0, control_altitude_matched=True,
    )
    assert outcome.attribution is None
    assert outcome.classification == NO_VALID_CONTROL


def test_fallback_is_distinguishable_from_a_real_mixed_result() -> None:
    """A real ambiguous result and a failed execution must not look alike."""
    local_ambiguous = _months([0.24, 0.25, 0.23])
    control_ambiguous = _months([0.30, 0.29, 0.31])
    real_mixed = execute_scm_attribution(
        "sn-06", local_ambiguous, control_ambiguous,
        mean_slope_deg=26.0, control_altitude_matched=True,
    )

    local_missing = _months([None, None])
    control_present = _months([0.30, 0.29, 0.31])
    failed = execute_scm_attribution(
        "sn-07", local_missing, control_present,
        mean_slope_deg=26.0, control_altitude_matched=True,
    )

    assert real_mixed.classification != NO_VALID_CONTROL
    assert real_mixed.attribution is not None
    assert failed.classification == NO_VALID_CONTROL
    assert failed.attribution is None
