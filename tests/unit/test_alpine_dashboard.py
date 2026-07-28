"""Unit tests for src/platform/alpine_dashboard.py (Alpine Edition UI logic).

``src/platform/`` must never import Streamlit, so every builder here is
exercised headless: GeoJSON dicts, Plotly figures and PyDeck decks are
inspected directly.

Deck assertions are deliberately duck-typed. ``tests/unit/test_map_layers.py``
installs a fake ``pydeck`` into ``sys.modules`` and reloads ``map_layers``, so
depending on test order the layer object here may be either a real
``pydeck.Layer`` (which exposes ``.type``) or that stub (which exposes
``.kind``). Asserting on one of them would make this file order-dependent.
"""
from __future__ import annotations

import pytest

from src.features.alpine_spectral import AlpineSeason
from src.platform.alpine_dashboard import (
    ALPINE_SEASON_VIEWS,
    SIERRA_NEVADA_VIEW,
    alert_badge_counts,
    alpine_assets_to_geojson,
    build_alpine_deck,
    build_alpine_matrix,
    season_view,
    slope_to_rgba,
    snow_to_rgba,
)
from src.platform.map_layers import TIER_COLORS


class _FakeAsset:
    """Minimal stand-in carrying every attribute the base builders read."""

    def __init__(self, asset_id: str, tier: int, alert_level: str | None) -> None:
        self.asset_id = asset_id
        self.name = f"Sendero {asset_id}"
        self.asset_type = "TRAIL"
        self.region = "Monachil"
        self.ehs = 45.0 + tier
        self.tier = tier
        self.tier_label = "IMMEDIATE ATTENTION"
        self.tpi = 70.0
        self.dcs = 65.0
        self.alert_level = alert_level
        self.scm_classification = "LOCALIZED_IMPACT"
        self.trend_direction = "decreasing"
        self.length_km = 4.2
        self.elevation_m = 2_400.0
        self.area_ha = None
        self.visitor_capacity_annual = 10_000 * tier
        self.economic_importance = 0.5
        self.description = "Sendero de alta montaña"


def _assets() -> list[_FakeAsset]:
    return [
        _FakeAsset("sn-0", 1, "CRITICAL_INTERVENTION"),
        _FakeAsset("sn-1", 2, "URGENT_MONITORING"),
        _FakeAsset("sn-2", 3, None),
        _FakeAsset("sn-3", 4, None),
    ]


def _layer_kind(layer) -> str:
    """Read the layer type from either the real pydeck Layer or the test stub."""
    return getattr(layer, "type", None) or getattr(layer, "kind", "")


def _layer_data(layer):
    """Read layer data from either the real pydeck Layer or the test stub."""
    if hasattr(layer, "kwargs"):
        return layer.kwargs.get("data")
    return getattr(layer, "data", None)


# ── Season descriptors ───────────────────────────────────────────────────────


def test_both_seasons_are_described() -> None:
    assert set(ALPINE_SEASON_VIEWS) == {AlpineSeason.WINTER, AlpineSeason.SUMMER}


def test_winter_view_is_driven_by_ndsi() -> None:
    view = season_view(AlpineSeason.WINTER)
    assert view.primary_indices == ("NDSI",)
    assert view.colour_variable == "ndsi"


def test_summer_view_is_driven_by_slope_with_evi_and_ndmi() -> None:
    view = season_view(AlpineSeason.SUMMER)
    assert view.primary_indices == ("EVI", "NDMI")
    assert view.colour_variable == "slope_deg"


def test_each_season_states_the_question_it_answers() -> None:
    assert all(v.question.endswith("?") for v in ALPINE_SEASON_VIEWS.values())


# ── Colour ramps ─────────────────────────────────────────────────────────────


def test_snow_ramp_runs_from_dark_rock_to_white() -> None:
    assert snow_to_rgba(-1.0)[:3] == [74, 85, 104]
    assert snow_to_rgba(1.0)[:3] == [255, 255, 255]


def test_snow_ramp_brightness_increases_with_ndsi() -> None:
    brightness = [sum(snow_to_rgba(v / 10.0)[:3]) for v in range(-10, 11)]
    assert all(b >= a for a, b in zip(brightness, brightness[1:]))


def test_slope_ramp_runs_from_green_to_red() -> None:
    assert slope_to_rgba(0.0)[:3] == [46, 125, 50]
    assert slope_to_rgba(45.0)[:3] == [198, 40, 40]


def test_slope_ramp_hue_shifts_monotonically_from_green_to_red() -> None:
    """The ramp passes through amber, so the red channel alone is NOT monotonic
    (it peaks at ~230 in amber, then darkens to 198 at the red end). What must
    hold is that the hue keeps moving away from green — measured as the
    green-minus-red balance decreasing all the way up the slope range."""
    balance = [
        slope_to_rgba(float(s))[1] - slope_to_rgba(float(s))[0]
        for s in range(0, 46)
    ]
    assert all(b <= a for a, b in zip(balance, balance[1:]))
    assert balance[0] > 0 > balance[-1]


def test_ramps_respect_the_requested_alpha() -> None:
    assert snow_to_rgba(0.5, alpha=128)[3] == 128
    assert slope_to_rgba(25.0, alpha=200)[3] == 200


# ── Seasonal GeoJSON colouring ───────────────────────────────────────────────


def test_seasons_colour_the_same_trail_differently() -> None:
    winter = alpine_assets_to_geojson(
        _assets(), AlpineSeason.WINTER, ndsi_by_asset={"sn-0": 0.85}
    )
    summer = alpine_assets_to_geojson(
        _assets(), AlpineSeason.SUMMER, slope_by_asset={"sn-0": 28.0}
    )
    assert (
        winter["features"][0]["properties"]["fill_color"]
        != summer["features"][0]["properties"]["fill_color"]
    )


def test_winter_features_report_the_ndsi_readout() -> None:
    geojson = alpine_assets_to_geojson(
        _assets(), AlpineSeason.WINTER, ndsi_by_asset={"sn-0": 0.85}
    )
    props = geojson["features"][0]["properties"]
    assert props["season_metric"] == "NDSI"
    assert props["season_value"] == "+0.85"


def test_summer_features_report_the_slope_readout() -> None:
    geojson = alpine_assets_to_geojson(
        _assets(), AlpineSeason.SUMMER, slope_by_asset={"sn-0": 28.0}
    )
    props = geojson["features"][0]["properties"]
    assert props["season_metric"] == "Pendiente media"
    assert props["season_value"] == "28.0°"


def test_unmeasured_trail_keeps_its_tier_colour() -> None:
    """A missing NDSI must read as 'not measured', never as bare ground."""
    geojson = alpine_assets_to_geojson(
        _assets(), AlpineSeason.WINTER, ndsi_by_asset={"sn-0": 0.85}
    )
    props = geojson["features"][1]["properties"]
    assert props["season_value"] == "sin dato"
    assert props["fill_color"] == TIER_COLORS[props["tier"]]


def test_geojson_is_a_feature_collection_with_one_feature_per_asset() -> None:
    assets = _assets()
    geojson = alpine_assets_to_geojson(assets, AlpineSeason.SUMMER)
    assert geojson["type"] == "FeatureCollection"
    assert len(geojson["features"]) == len(assets)


# ── PyDeck deck ──────────────────────────────────────────────────────────────


def test_deck_uses_a_single_geojson_layer() -> None:
    deck = build_alpine_deck(_assets(), AlpineSeason.SUMMER)
    assert len(deck.layers) == 1
    assert _layer_kind(deck.layers[0]) == "GeoJsonLayer"


def test_deck_carries_the_season_coloured_features() -> None:
    deck = build_alpine_deck(
        _assets(), AlpineSeason.SUMMER, slope_by_asset={"sn-0": 28.0}
    )
    data = _layer_data(deck.layers[0])
    assert data is not None
    assert data["type"] == "FeatureCollection"


def test_deck_is_centred_on_sierra_nevada() -> None:
    deck = build_alpine_deck(_assets(), AlpineSeason.WINTER)
    view_state = deck.initial_view_state
    assert 36.8 < view_state.latitude < 37.3
    assert -3.7 < view_state.longitude < -3.0


def test_sierra_nevada_viewport_covers_the_high_massif() -> None:
    assert 36.8 < SIERRA_NEVADA_VIEW["latitude"] < 37.3
    assert -3.7 < SIERRA_NEVADA_VIEW["longitude"] < -3.0


# ── TPI portfolio matrix ─────────────────────────────────────────────────────


def test_matrix_uses_roman_numeral_tiers() -> None:
    fig = build_alpine_matrix(_assets())
    names = [trace.name for trace in fig.data]
    assert any("TIER I " in n for n in names)
    assert any("TIER IV" in n for n in names)


def test_matrix_draws_one_trace_per_populated_tier() -> None:
    fig = build_alpine_matrix(_assets())
    assert len(fig.data) == 4


def test_matrix_annotates_critical_and_urgent_alert_badges() -> None:
    texts = [a.text for a in build_alpine_matrix(_assets()).layout.annotations]
    assert any("crítico" in t for t in texts)
    assert any("urgente" in t for t in texts)


def test_matrix_omits_badges_when_there_are_no_alerts() -> None:
    quiet = [_FakeAsset("sn-9", 4, None)]
    texts = [a.text for a in build_alpine_matrix(quiet).layout.annotations]
    assert not any("crítico" in t or "urgente" in t for t in texts)


def test_matrix_handles_an_empty_portfolio() -> None:
    assert build_alpine_matrix([]).layout.title.text == "Sin activos para mostrar"


def test_matrix_accepts_a_title_override() -> None:
    fig = build_alpine_matrix(_assets(), title="Cartera Sierra Nevada")
    assert fig.layout.title.text == "Cartera Sierra Nevada"


# ── Alert badge counting ─────────────────────────────────────────────────────


def test_alert_badges_count_critical_and_urgent_separately() -> None:
    assert alert_badge_counts(_assets()) == {"critical": 1, "urgent": 1}


def test_alert_badges_are_zero_for_a_quiet_portfolio() -> None:
    assert alert_badge_counts([]) == {"critical": 0, "urgent": 0}


@pytest.mark.parametrize("season", [AlpineSeason.WINTER, AlpineSeason.SUMMER])
def test_every_season_produces_a_renderable_deck(season) -> None:
    deck = build_alpine_deck(_assets(), season)
    assert len(deck.layers) == 1
