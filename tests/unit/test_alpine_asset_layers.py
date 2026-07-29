"""Unit tests for src/platform/alpine_asset_layers.py (season-colour layers)."""
from __future__ import annotations

from pathlib import Path

from src.platform.alpine_asset_layers import load_alpine_asset_layers

_CSV = (
    "asset_id,ndsi,slope_deg,ndsi_source,dem_source\n"
    "a1,0.62,24.5,S2_NDSI_2024-02,cop-dem-glo-30\n"
    "a2,,12.0,,cop-dem-glo-30\n"            # no NDSI (outside scene), has slope
    "a3,-0.30,,S2_NDSI_2024-02,\n"          # has NDSI, no slope
    "a4,,,,\n"                               # neither
)


def _write(tmp_path: Path) -> Path:
    p = tmp_path / "layers.csv"
    p.write_text(_CSV, encoding="utf-8")
    return p


def test_loads_ndsi_and_slope_dicts(tmp_path: Path) -> None:
    ndsi, slope = load_alpine_asset_layers("sn", path=_write(tmp_path))
    assert ndsi == {"a1": 0.62, "a3": -0.30}
    assert slope == {"a1": 24.5, "a2": 12.0}


def test_missing_values_are_omitted_not_zeroed(tmp_path: Path) -> None:
    ndsi, slope = load_alpine_asset_layers("sn", path=_write(tmp_path))
    assert "a2" not in ndsi   # blank NDSI → absent, not 0.0
    assert "a3" not in slope
    assert "a4" not in ndsi and "a4" not in slope


def test_non_sierra_nevada_territory_gets_no_layers(tmp_path: Path) -> None:
    assert load_alpine_asset_layers("pnsg", path=_write(tmp_path)) == ({}, {})


def test_missing_file_returns_empty(tmp_path: Path) -> None:
    assert load_alpine_asset_layers("sn", path=tmp_path / "nope.csv") == ({}, {})
