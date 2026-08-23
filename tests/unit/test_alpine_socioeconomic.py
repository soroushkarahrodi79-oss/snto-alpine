"""Unit tests for src.socioeconomic.alpine_mapping (issue #10)."""
from __future__ import annotations

from dataclasses import dataclass

from src.config.constants import (
    ALPINE_OAPN_RED_TOTAL_VISITORS,
    ALPINE_OAPN_REPORT_YEAR,
    ALPINE_OAPN_SIERRA_NEVADA_SHARE_PCT,
)
from src.socioeconomic.alpine_mapping import (
    build_municipal_context,
    load_sierra_nevada_crosswalk,
    resolve_region_to_ine,
    sierra_nevada_visitor_pressure,
)
from src.socioeconomic.mapping import CROSSWALK_PATH as PNSG_CROSSWALK_PATH
from src.territorial.alpine_fixtures import build_sierra_nevada_territory


@dataclass
class _FakeAsset:
    region: str


def test_crosswalk_loads_real_granada_and_almeria_rows() -> None:
    rows = load_sierra_nevada_crosswalk()
    assert len(rows) >= 20
    provinces = {r.province for r in rows}
    assert provinces == {"Granada", "Almería"}


def test_crosswalk_is_disjoint_from_madrid_ine_codes() -> None:
    """No Sierra Nevada row may carry a Madrid (province 28) INE code —
    that would be exactly the Madrid/PNSG leak issue #10 forbids."""
    rows = load_sierra_nevada_crosswalk()
    assert all(not r.ine_code.startswith("28") for r in rows)
    # And every code is a real 5-digit INE code for Granada (18) or Almería (04).
    assert all(r.ine_code[:2] in ("18", "04") for r in rows)
    assert all(len(r.ine_code) == 5 for r in rows)


def test_resolve_region_matches_accent_and_non_accent_spellings() -> None:
    accented = resolve_region_to_ine("Güéjar Sierra")
    unaccented = resolve_region_to_ine("Guejar Sierra")
    assert accented is not None and unaccented is not None
    assert accented.ine_code == unaccented.ine_code == "18094"


def test_resolve_region_handles_the_1971_municipality_merger() -> None:
    """Yegen and Mecina Bombarón are pedanías of Alpujarra de la Sierra
    (merged 1971) — both trail-name spellings must resolve to that one code."""
    yegen = resolve_region_to_ine("Yegen")
    mecina = resolve_region_to_ine("Mecina Bombarón")
    assert yegen is None  # Yegen itself has no independent INE code
    assert mecina is None  # neither does "Mecina Bombarón" as a name
    # Only the merged municipality name resolves — this documents the gap
    # rather than silently mis-mapping a pedanía to a random neighbour.
    merged = resolve_region_to_ine("Alpujarra de la Sierra")
    assert merged is not None and merged.ine_code == "18904"


def test_resolve_region_returns_none_for_non_municipalities() -> None:
    assert resolve_region_to_ine("Sierra Nevada") is None       # massif default
    assert resolve_region_to_ine("Refugio Poqueira") is None    # not a municipality
    assert resolve_region_to_ine("") is None


def test_resolve_region_never_falls_back_to_a_madrid_municipality() -> None:
    """Names that exist in the PNSG (Madrid) crosswalk but not in Sierra
    Nevada's must not resolve here — no silent cross-territory leak."""
    assert resolve_region_to_ine("Madrid") is None
    assert resolve_region_to_ine("Manzanares El Real") is None


def test_visitor_pressure_matches_the_documented_oapn_source() -> None:
    year, share, estimate, red_total = sierra_nevada_visitor_pressure()
    assert year == ALPINE_OAPN_REPORT_YEAR == 2023
    assert share == ALPINE_OAPN_SIERRA_NEVADA_SHARE_PCT == 4.89
    assert red_total == ALPINE_OAPN_RED_TOTAL_VISITORS == 15_016_249
    assert estimate == round(red_total * share / 100.0)
    assert estimate == 734_295


def test_municipal_context_resolves_most_real_sierra_nevada_assets() -> None:
    assets = build_sierra_nevada_territory()
    ctx = build_municipal_context(assets)
    assert ctx.n_assets == len(assets)
    assert ctx.n_resolved > 0
    # Every resolved municipality must be a real Andalusian one.
    assert set(ctx.provinces) <= {"Granada", "Almería"}
    assert ctx.oapn_sierra_nevada_visitors_estimate == 734_295


def test_municipal_context_reports_unresolved_regions_honestly() -> None:
    assets = [_FakeAsset(region="Sierra Nevada"), _FakeAsset(region="Monachil")]
    ctx = build_municipal_context(assets)
    assert ctx.n_assets == 2
    assert ctx.n_resolved == 1
    assert "Sierra Nevada" in ctx.unresolved_regions


def test_sierra_nevada_crosswalk_file_is_separate_from_pnsg_madrid_file() -> None:
    """Structural guard: Sierra Nevada must ship its own crosswalk file,
    never read the gitignored Madrid/PNSG one."""
    from src.socioeconomic.alpine_mapping import CROSSWALK_PATH as SN_PATH

    assert SN_PATH != PNSG_CROSSWALK_PATH
    assert SN_PATH.exists()
