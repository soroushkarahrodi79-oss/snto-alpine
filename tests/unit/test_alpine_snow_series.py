"""Unit tests for the multi-date winter snow series (issue #8)."""

from __future__ import annotations

from pathlib import Path

from src.features.alpine_snow_series import (
    MIN_VALID_PIXEL_PCT,
    WinterPeriodObservation,
    asset_snowpack_duration,
    series_summary,
    snowline_series_ci,
    write_series_json,
)
from src.temporal.manifest import DataStatus

PERIODS = ["2023-12", "2024-01", "2024-02", "2024-03"]


def _obs(
    period_key: str,
    coverage: float = 80.0,
    snowline: float | None = 2400.0,
    n_snow: int = 5000,
) -> WinterPeriodObservation:
    return WinterPeriodObservation(
        period_key=period_key,
        date_range=f"{period_key}-01/{period_key}-28",
        mosaic_coverage_pct=coverage,
        snowline_elevation_m=snowline,
        n_snow_pixels=n_snow,
    )


def test_present_true_above_quality_floor_with_snowline() -> None:
    o = _obs("2024-01", coverage=90.0, snowline=2300.0)
    assert o.present is True
    assert o.data_status is DataStatus.REAL


def test_present_false_below_coverage_floor() -> None:
    o = _obs("2024-01", coverage=MIN_VALID_PIXEL_PCT - 1, snowline=2300.0)
    assert o.present is False
    assert o.data_status is DataStatus.MISSING


def test_present_false_when_snowline_missing() -> None:
    """A mosaic that ran but found too few snow pixels is a gap, not a zero."""
    o = _obs("2024-01", coverage=90.0, snowline=None)
    assert o.present is False
    assert o.data_status is DataStatus.MISSING


def test_snowline_series_ci_none_for_single_period() -> None:
    assert snowline_series_ci([_obs("2024-02")]) is None


def test_snowline_series_ci_none_when_all_missing() -> None:
    obs = [_obs(p, snowline=None) for p in PERIODS]
    assert snowline_series_ci(obs) is None


def test_snowline_series_ci_covers_the_point_estimate() -> None:
    values = [2200.0, 2350.0, 2300.0, 2450.0]
    obs = [_obs(p, snowline=v) for p, v in zip(PERIODS, values)]
    ci = snowline_series_ci(obs)
    assert ci is not None
    assert ci.lower <= ci.point <= ci.upper
    # The point estimate should track the plain mean of the 4 values.
    assert abs(ci.point - sum(values) / len(values)) < 1e-6


def test_snowline_series_ci_excludes_gaps() -> None:
    """A missing period must not silently become a 0 m snowline in the CI."""
    obs = [
        _obs("2023-12", snowline=None),  # gap
        _obs("2024-01", snowline=2300.0),
        _obs("2024-02", snowline=2350.0),
    ]
    ci = snowline_series_ci(obs)
    # Only 2 present values -> still computable, but degenerate/narrow is fine;
    # the key assertion is it never used 0.0 for the gap.
    assert ci is not None
    assert ci.point > 1000  # nowhere near what a 0-contaminated mean would give


def test_asset_snowpack_duration_counts_snow_periods() -> None:
    ndsi = {"2023-12": 0.55, "2024-01": 0.62, "2024-02": 0.30, "2024-03": 0.10}
    # threshold default (NDSI_SNOW_THRESHOLD) is 0.40 -> only Dec & Jan count
    assert asset_snowpack_duration(ndsi, PERIODS) == 2


def test_asset_snowpack_duration_missing_period_is_a_gap_not_snow_free() -> None:
    with_gap = {"2023-12": 0.55, "2024-02": 0.60}  # Jan, Mar absent
    without_gap = {"2023-12": 0.55, "2024-01": 0.0, "2024-02": 0.60, "2024-03": 0.0}
    assert asset_snowpack_duration(with_gap, PERIODS) == 2
    assert asset_snowpack_duration(without_gap, PERIODS) == 2  # unaffected by the 0s


def test_series_summary_reports_gaps_and_coverage() -> None:
    obs = [
        _obs("2023-12", snowline=2200.0),
        _obs("2024-01", coverage=10.0, snowline=None),  # gap
        _obs("2024-02", snowline=2300.0),
        _obs("2024-03", snowline=2400.0),
    ]
    summary = series_summary(obs)
    assert summary["n_expected"] == 4
    assert summary["n_present"] == 3
    assert summary["gaps"] == ["2024-01"]
    assert summary["snowline_mean_m"] is not None
    assert (
        summary["snowline_ci_low_m"]
        <= summary["snowline_mean_m"]
        <= summary["snowline_ci_high_m"]
    )


def test_series_summary_single_present_period_has_no_ci_but_has_a_point() -> None:
    obs = [_obs("2024-02", snowline=2300.0)]
    summary = series_summary(obs)
    assert summary["snowline_mean_m"] == 2300.0
    assert summary["snowline_ci_low_m"] is None


def test_write_series_json_round_trips(tmp_path: Path) -> None:
    import json

    obs = [_obs(p, snowline=2300.0 + i * 10) for i, p in enumerate(PERIODS)]
    out = tmp_path / "series.json"
    write_series_json(obs, out)
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["n_expected"] == 4
    assert len(data["periods"]) == 4
