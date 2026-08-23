"""Unit tests for src.validation.alpine_plots (issue #11)."""
from __future__ import annotations

from shapely.geometry import box

from src.validation.alpine_plots import propose_baci_plots

_CRS = "EPSG:25830"


def test_proposes_the_requested_number_of_plots_per_zone() -> None:
    local = box(500_000, 4_100_000, 500_100, 4_100_100)
    control = box(500_300, 4_100_300, 500_600, 4_100_600)
    plots = propose_baci_plots(
        "sn-01", local, control, _CRS, "2400-2600m", n_per_zone=5
    )
    impact = [p for p in plots if not p.is_control]
    control_plots = [p for p in plots if p.is_control]
    assert len(impact) == 5
    assert len(control_plots) == 5


def test_impact_plots_precede_control_plots() -> None:
    local = box(500_000, 4_100_000, 500_100, 4_100_100)
    control = box(500_300, 4_100_300, 500_600, 4_100_600)
    plots = propose_baci_plots("sn-01", local, control, _CRS, "stratum", n_per_zone=3)
    flags = [p.is_control for p in plots]
    assert flags == sorted(flags)  # False (impact) before True (control)


def test_plots_carry_the_asset_id_and_stratum() -> None:
    local = box(500_000, 4_100_000, 500_050, 4_100_050)
    control = box(500_300, 4_100_300, 500_350, 4_100_350)
    plots = propose_baci_plots(
        "sn-42", local, control, _CRS, "borreguil-alto", n_per_zone=2
    )
    assert all(p.asset_id == "sn-42" for p in plots)
    assert all(p.stratum == "borreguil-alto" for p in plots)


def test_plot_coordinates_land_inside_their_source_zone() -> None:
    """Reprojecting a Sierra Nevada-scale UTM box should keep points in a
    sane Granada-ish lat/lon envelope, not silently mis-project."""
    local = box(460_000, 4_100_000, 460_500, 4_100_500)  # near Sierra Nevada, UTM 30N
    plots = propose_baci_plots("sn-01", local, None, _CRS, "stratum", n_per_zone=3)
    assert plots
    for p in plots:
        assert 35.0 < p.lat < 39.0
        assert -5.0 < p.lon < -2.0


def test_missing_control_zone_yields_no_control_plots_but_keeps_impact() -> None:
    local = box(500_000, 4_100_000, 500_100, 4_100_100)
    plots = propose_baci_plots("sn-01", local, None, _CRS, "stratum", n_per_zone=4)
    assert all(not p.is_control for p in plots)
    assert len(plots) == 4


def test_both_zones_missing_yields_no_plots() -> None:
    plots = propose_baci_plots("sn-01", None, None, _CRS, "stratum", n_per_zone=4)
    assert plots == []


def test_deterministic_for_the_same_seed() -> None:
    local = box(500_000, 4_100_000, 500_200, 4_100_200)
    control = box(500_400, 4_100_400, 500_700, 4_100_700)
    a = propose_baci_plots(
        "sn-01", local, control, _CRS, "stratum", n_per_zone=4, seed=7
    )
    b = propose_baci_plots(
        "sn-01", local, control, _CRS, "stratum", n_per_zone=4, seed=7
    )
    assert [(p.lat, p.lon) for p in a] == [(p.lat, p.lon) for p in b]


def test_different_seeds_usually_propose_different_coordinates() -> None:
    local = box(500_000, 4_100_000, 500_200, 4_100_200)
    a = propose_baci_plots("sn-01", local, None, _CRS, "stratum", n_per_zone=4, seed=1)
    b = propose_baci_plots("sn-01", local, None, _CRS, "stratum", n_per_zone=4, seed=2)
    assert [(p.lat, p.lon) for p in a] != [(p.lat, p.lon) for p in b]


def test_plot_ids_are_unique_and_prefixed_by_role() -> None:
    local = box(500_000, 4_100_000, 500_100, 4_100_100)
    control = box(500_300, 4_100_300, 500_400, 4_100_400)
    plots = propose_baci_plots("sn-07", local, control, _CRS, "stratum", n_per_zone=3)
    ids = [p.plot_id for p in plots]
    assert len(ids) == len(set(ids))
    assert all(
        pid.startswith("sn-07:impact:") or pid.startswith("sn-07:control:")
        for pid in ids
    )
