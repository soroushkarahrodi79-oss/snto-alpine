"""Unit tests for src/platform/map_layers.py — Task 5 (PyDeck migration).

All tests run offline; no network calls or browser rendering required.
pydeck is an optional dependency: tests that need it are skipped if not
installed (CI without frontend deps can still run the full suite).
"""
from __future__ import annotations

import sys
import types
from dataclasses import dataclass
from typing import Optional

import pytest

# ── Minimal pydeck stub (avoid real WebGL / browser requirement in CI) ────────

def _make_pydeck_stub() -> types.ModuleType:
    stub = types.ModuleType("pydeck")

    class _FakeLayer:
        def __init__(self, kind, **kwargs):
            self.kind   = kind
            self.kwargs = kwargs

    class _FakeViewState:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class _FakeDeck:
        def __init__(self, layers=None, initial_view_state=None,
                     tooltip=None, map_style=None):
            self.layers             = layers or []
            self.initial_view_state = initial_view_state
            self.tooltip            = tooltip
            self.map_style          = map_style

    stub.Layer     = _FakeLayer
    stub.ViewState = _FakeViewState
    stub.Deck      = _FakeDeck
    return stub

_pydeck_stub = _make_pydeck_stub()
# Force the stub regardless of import order. Another test collected earlier (or
# map_layers' own import chain via real_trails/calibration) may already have
# pulled the REAL pydeck into sys.modules; a setdefault() here would then be a
# silent no-op and bind build_pydeck_deck to real (browser/WebGL) pydeck, whose
# Deck/Layer objects lack the .tooltip/.kwargs the offline tests inspect. We
# install the stub and reload map_layers so its `import pydeck as pdk` resolves
# to the stub — keeping these tests offline and order-independent.
import importlib  # noqa: E402

sys.modules["pydeck"] = _pydeck_stub
import src.platform.map_layers as _map_layers  # noqa: E402

_map_layers = importlib.reload(_map_layers)

LEGEND_ITEMS = _map_layers.LEGEND_ITEMS
TIER_COLORS = _map_layers.TIER_COLORS
_heading_from_id = _map_layers._heading_from_id
_jitter = _map_layers._jitter
_point_radius_m = _map_layers._point_radius_m
_region_centroid = _map_layers._region_centroid


def test_jitter_is_process_stable_not_python_hash_salted() -> None:
    """The marker offset must be identical across processes.

    Built-in hash() is salted per process (PYTHONHASHSEED), which moved markers
    on every server restart and broke alignment with offline-sampled layers.
    _jitter must use a stable hash — pin an exact value so a regression to
    hash() (or any change to the scheme) fails loudly.
    """
    lat, lon = _jitter("pn_sierra_nevada_test_asset_042", 37.05, -3.31)
    assert (round(lat, 6), round(lon, 6)) == (37.048339, -3.309986)
_trail_endpoints = _map_layers._trail_endpoints
assets_to_geojson = _map_layers.assets_to_geojson
build_pydeck_deck = _map_layers.build_pydeck_deck


# ── Minimal TerritorialAsset stub ─────────────────────────────────────────────

@dataclass
class _FakeAsset:
    asset_id:               str
    name:                   str
    asset_type:             str
    region:                 str
    ehs:                    float
    tier:                   Optional[int]
    tpi:                    Optional[float]
    tier_label:             Optional[str]
    alert_level:            str
    scm_classification:     str
    trend_direction:        str
    description:            str = ""
    length_km:              Optional[float] = None
    area_ha:                Optional[float] = None
    elevation_m:            Optional[float] = None
    priority_rank:          Optional[int] = None


def _trail(
    asset_id: str = "trail-01",
    region: str = "Montejo de la Sierra",
    length_km: float = 5.0,
    tier: int = 1,
) -> _FakeAsset:
    return _FakeAsset(
        asset_id=asset_id, name="Test Trail", asset_type="TRAIL",
        region=region, ehs=40.0, tier=tier, tpi=88.0,
        tier_label="IMMEDIATE ATTENTION", alert_level="URGENT_MONITORING",
        scm_classification="LOCALIZED_IMPACT", trend_direction="decreasing",
        length_km=length_km,
    )


def _viewpoint(
    asset_id: str = "view-01",
    region: str = "La Hiruela",
    tier: int = 2,
) -> _FakeAsset:
    return _FakeAsset(
        asset_id=asset_id, name="Test Viewpoint", asset_type="VIEWPOINT",
        region=region, ehs=61.0, tier=tier, tpi=55.0,
        tier_label="PREVENTIVE ACTION", alert_level="PREVENTIVE_ACTION",
        scm_classification="LOCALIZED_IMPACT", trend_direction="no_trend",
    )


def _park(
    asset_id: str = "park-01",
    area_ha: float = 50.0,
    tier: int = 3,
) -> _FakeAsset:
    return _FakeAsset(
        asset_id=asset_id, name="Test Park", asset_type="NATURAL_PARK",
        region="Horcajuelo de la Sierra", ehs=70.0, tier=tier, tpi=33.0,
        tier_label="ROUTINE MONITORING", alert_level="NORMAL",
        scm_classification="LANDSCAPE_DRIVEN", trend_direction="no_trend",
        area_ha=area_ha,
    )


# ── TIER_COLORS ───────────────────────────────────────────────────────────────

class TestTierColors:
    def test_all_four_tiers_defined(self):
        for t in (1, 2, 3, 4):
            assert t in TIER_COLORS

    def test_colors_are_rgba_lists(self):
        for t, rgba in TIER_COLORS.items():
            assert isinstance(rgba, list)
            assert len(rgba) == 4
            assert all(0 <= v <= 255 for v in rgba)

    def test_palette_is_neutral_not_semaphore(self):
        # Fase 3: el TIER es prioridad de inversión (estrategia), NO riesgo. La
        # paleta es neutra índigo→pizarra: ningún tier debe ser rojo- ni
        # verde-dominante (eso es el semáforo, reservado a las alertas).
        for t, (r, g, b, _a) in TIER_COLORS.items():
            assert not (r > g and r > b), f"Tier {t} no debe ser rojo-dominante"
            assert not (g > r and g > b), f"Tier {t} no debe ser verde-dominante"

    def test_palette_is_sequential_dark_to_light(self):
        # Tier I = más oscuro (máxima prioridad de inversión) → Tier IV = más claro.
        brightness = {t: sum(TIER_COLORS[t][:3]) for t in (1, 2, 3, 4)}
        assert brightness[1] < brightness[2] < brightness[3] < brightness[4]


# ── LEGEND_ITEMS ──────────────────────────────────────────────────────────────

class TestLegendItems:
    def test_four_items(self):
        assert len(LEGEND_ITEMS) == 4

    def test_each_item_has_required_keys(self):
        for item in LEGEND_ITEMS:
            assert "tier" in item
            assert "label" in item
            assert "hex" in item

    def test_hex_colors_are_valid(self):
        for item in LEGEND_ITEMS:
            assert item["hex"].startswith("#")
            assert len(item["hex"]) == 7


# ── _region_centroid ──────────────────────────────────────────────────────────

class TestRegionCentroid:
    def test_known_region_returns_coords(self):
        lat, lon = _region_centroid("Montejo de la Sierra")
        assert 40.0 < lat < 42.0
        assert -4.0 < lon < -3.0

    def test_unknown_region_returns_default(self):
        lat, lon = _region_centroid("Atlantis")
        # Default is the reserve centre — still valid lat/lon for Spain
        assert 40.0 < lat < 42.0
        assert -4.0 < lon < -3.0

    def test_all_known_regions_in_spain(self):
        regions = [
            "Montejo de la Sierra", "La Hiruela", "Horcajuelo de la Sierra",
            "Puebla de la Sierra", "Prádena del Rincón", "Robregordo",
        ]
        for r in regions:
            lat, lon = _region_centroid(r)
            assert 40.0 < lat < 42.0, f"{r}: lat={lat} out of Spain range"
            assert -4.0 < lon < -3.0, f"{r}: lon={lon} out of Spain range"


# ── _jitter ───────────────────────────────────────────────────────────────────

class TestJitter:
    def test_output_is_near_input(self):
        lat, lon = _jitter("id-1", 41.17, -3.48, spread=0.007)
        assert abs(lat - 41.17) < 0.007
        assert abs(lon - (-3.48)) < 0.007

    def test_deterministic_same_id(self):
        j1 = _jitter("asset-abc", 41.0, -3.5)
        j2 = _jitter("asset-abc", 41.0, -3.5)
        assert j1 == j2

    def test_different_ids_produce_different_offsets(self):
        j1 = _jitter("id-A", 41.0, -3.5)
        j2 = _jitter("id-B", 41.0, -3.5)
        assert j1 != j2


# ── _trail_endpoints ──────────────────────────────────────────────────────────

class TestTrailEndpoints:
    def test_endpoints_have_correct_format(self):
        start, end = _trail_endpoints(41.17, -3.48, 5.0, 0.0)
        assert len(start) == 2   # [lon, lat]
        assert len(end)   == 2

    def test_north_heading_moves_lat(self):
        """Heading 0° (North) → end has higher latitude than start."""
        start, end = _trail_endpoints(41.17, -3.48, 5.0, 0.0)
        # start[1] is lat_start, end[1] is lat_end; end should be north of start
        assert end[1] > start[1]

    def test_east_heading_moves_lon(self):
        """Heading 90° (East) → end has higher longitude than start."""
        start, end = _trail_endpoints(41.17, -3.48, 5.0, 90.0)
        assert end[0] > start[0]

    def test_trail_distance_approx_correct(self):
        """5 km trail at 0° heading → lat difference ≈ 5/111.32 ≈ 0.045°."""
        import math
        start, end = _trail_endpoints(41.17, -3.48, 5.0, 0.0)
        dlat = abs(end[1] - start[1])
        expected = 5.0 / 111.320
        assert abs(dlat - expected) < 0.005

    def test_zero_length_collapses_to_point(self):
        start, end = _trail_endpoints(41.17, -3.48, 0.0, 45.0)
        assert start == end


# ── _point_radius_m ───────────────────────────────────────────────────────────

class TestPointRadiusM:
    def test_viewpoint_has_small_radius(self):
        asset = _viewpoint()
        assert _point_radius_m(asset) <= 200.0

    def test_park_with_area_ha_is_larger(self):
        asset = _park(area_ha=100.0)
        r = _point_radius_m(asset)
        # Equivalent circular radius of 100 ha ≈ 564 m
        assert r > 300.0

    def test_radius_grows_with_area(self):
        small = _park(area_ha=10.0)
        large = _park(area_ha=100.0)
        assert _point_radius_m(large) > _point_radius_m(small)

    def test_minimum_radius_respected(self):
        very_tiny = _FakeAsset(
            asset_id="tiny", name="Tiny", asset_type="RECREATIONAL_AREA",
            region="Montejo de la Sierra", ehs=80.0, tier=4, tpi=20.0,
            tier_label="PROMOTION", alert_level="NORMAL",
            scm_classification="LANDSCAPE_DRIVEN", trend_direction="increasing",
            area_ha=0.1,   # Very small area
        )
        assert _point_radius_m(very_tiny) >= 100.0


# ── assets_to_geojson ─────────────────────────────────────────────────────────

class TestAssetsToGeojson:
    def _mixed_assets(self):
        return [
            _trail("t1", tier=1),
            _trail("t2", tier=2),
            _viewpoint("v1", tier=2),
            _park("p1", tier=3),
            _viewpoint("v2", tier=4),
        ]

    def test_returns_feature_collection(self):
        fc = assets_to_geojson(self._mixed_assets())
        assert fc["type"] == "FeatureCollection"
        assert "features" in fc

    def test_feature_count_matches_asset_count(self):
        assets = self._mixed_assets()
        fc = assets_to_geojson(assets)
        assert len(fc["features"]) == len(assets)

    def test_trail_produces_linestring(self):
        fc = assets_to_geojson([_trail()])
        geom = fc["features"][0]["geometry"]
        assert geom["type"] == "LineString"
        # _trail_path() renders an undulating polyline (≥2 vertices) rather
        # than a straight start→end segment, so the trace doesn't mislead the
        # territorial analyst. Endpoints must still be distinct.
        coords = geom["coordinates"]
        assert len(coords) >= 2
        assert coords[0] != coords[-1]   # start ≠ end

    def test_viewpoint_produces_point(self):
        fc = assets_to_geojson([_viewpoint()])
        geom = fc["features"][0]["geometry"]
        assert geom["type"] == "Point"
        assert len(geom["coordinates"]) == 2   # [lon, lat]

    def test_park_produces_point(self):
        fc = assets_to_geojson([_park()])
        geom = fc["features"][0]["geometry"]
        assert geom["type"] == "Point"

    def test_geojson_lon_lat_order(self):
        """GeoJSON must use [longitude, latitude] not [latitude, longitude]."""
        fc = assets_to_geojson([_viewpoint("v-montejo", region="Montejo de la Sierra")])
        lon, lat = fc["features"][0]["geometry"]["coordinates"]
        # Montejo centroid: lat ≈ 41.17, lon ≈ -3.48
        assert lat > 40.0 and lat < 42.0, f"Expected latitude, got {lat}"
        assert lon < 0.0, f"Expected negative longitude, got {lon}"

    def test_properties_contain_required_fields(self):
        fc = assets_to_geojson([_trail("t99", tier=1)])
        props = fc["features"][0]["properties"]
        for field in ("name", "ehs", "tier", "fill_color", "line_color"):
            assert field in props, f"Missing property: {field}"

    def test_fill_color_is_rgba_list(self):
        fc = assets_to_geojson([_trail(tier=1)])
        color = fc["features"][0]["properties"]["fill_color"]
        assert isinstance(color, list)
        assert len(color) == 4
        assert all(0 <= v <= 255 for v in color)

    def test_tier1_color_is_neutral_dark(self):
        # Tier I: índigo profundo neutro (no semáforo rojo).
        fc = assets_to_geojson([_trail(tier=1)])
        r, g, b, _ = fc["features"][0]["properties"]["fill_color"]
        assert not (r > g and r > b) and not (g > r and g > b)

    def test_tier1_fill_darker_than_tier4(self):
        # La paleta neutra codifica prioridad por luminosidad: Tier I < Tier IV.
        t1 = assets_to_geojson([_trail(tier=1)])["features"][0]["properties"]["fill_color"]
        t4 = assets_to_geojson([_viewpoint(tier=4)])["features"][0]["properties"]["fill_color"]
        assert sum(t1[:3]) < sum(t4[:3])

    def test_coordinates_are_in_sierra_del_rincon(self):
        """All generated coordinates should be in the reserve area (rough bbox)."""
        assets = self._mixed_assets()
        fc = assets_to_geojson(assets)
        for feat in fc["features"]:
            geom = feat["geometry"]
            if geom["type"] == "Point":
                lon, lat = geom["coordinates"]
            else:
                lon, lat = geom["coordinates"][0]
            assert 41.0 < lat < 41.4, f"Latitude {lat:.4f} outside reserve bbox"
            assert -3.7 < lon < -3.3, f"Longitude {lon:.4f} outside reserve bbox"

    def test_empty_asset_list(self):
        fc = assets_to_geojson([])
        assert fc["type"] == "FeatureCollection"
        assert fc["features"] == []

    def test_cycling_route_produces_linestring(self):
        cycling = _FakeAsset(
            asset_id="bike-01", name="Cycling Route", asset_type="CYCLING_ROUTE",
            region="Robregordo", ehs=85.0, tier=4, tpi=30.0,
            tier_label="PROMOTION", alert_level="NORMAL",
            scm_classification="LANDSCAPE_DRIVEN", trend_direction="increasing",
            length_km=12.0,
        )
        fc = assets_to_geojson([cycling])
        assert fc["features"][0]["geometry"]["type"] == "LineString"

    def test_trail_length_affects_coordinate_spread(self):
        """Longer trail → larger distance between start and end coordinates."""
        import math
        short_fc = assets_to_geojson([_trail("t-short", length_km=2.0)])
        long_fc  = assets_to_geojson([_trail("t-long",  length_km=10.0)])

        def _dist(coords):
            s, e = coords[0], coords[1]
            return math.hypot(e[0] - s[0], e[1] - s[1])

        short_d = _dist(short_fc["features"][0]["geometry"]["coordinates"])
        long_d  = _dist(long_fc["features"][0]["geometry"]["coordinates"])
        assert long_d > short_d


# ── build_pydeck_deck ─────────────────────────────────────────────────────────

class TestBuildPydeckDeck:
    def _assets(self):
        return [_trail(tier=1), _viewpoint(tier=2), _park(tier=3)]

    def test_returns_deck_object(self):
        deck = build_pydeck_deck(self._assets())
        assert isinstance(deck, _pydeck_stub.Deck)

    def test_deck_has_one_geojson_layer(self):
        deck = build_pydeck_deck(self._assets())
        assert len(deck.layers) == 1
        layer = deck.layers[0]
        assert layer.kind == "GeoJsonLayer"

    def test_layer_data_is_feature_collection(self):
        deck  = build_pydeck_deck(self._assets())
        layer = deck.layers[0]
        data  = layer.kwargs.get("data")
        assert data is not None
        assert data["type"] == "FeatureCollection"

    def test_layer_feature_count_matches_assets(self):
        assets = self._assets()
        deck   = build_pydeck_deck(assets)
        n_feat = len(deck.layers[0].kwargs["data"]["features"])
        assert n_feat == len(assets)

    def test_view_state_centred_on_reserve(self):
        deck = build_pydeck_deck(self._assets())
        vs   = deck.initial_view_state
        assert 41.0 < vs.latitude  < 41.3
        assert -3.6 < vs.longitude < -3.3

    def test_tooltip_is_configured(self):
        deck = build_pydeck_deck(self._assets())
        assert deck.tooltip is not None
        assert "html" in deck.tooltip

    def test_tooltip_references_name_property(self):
        deck = build_pydeck_deck(self._assets())
        assert "{name}" in deck.tooltip["html"]

    def test_map_style_is_set(self):
        deck = build_pydeck_deck(self._assets())
        assert deck.map_style is not None
        assert "http" in deck.map_style

    def test_empty_asset_list_produces_empty_layer(self):
        deck = build_pydeck_deck([])
        n_feat = len(deck.layers[0].kwargs["data"]["features"])
        assert n_feat == 0


# ── Geometría real (traza Pipeline A) vs aproximada (centroide) ───────────────

_REAL_LINE = {"type": "LineString", "coordinates": [[-4.02, 40.84], [-4.01, 40.85], [-4.00, 40.86]]}


class TestRealGeometryInjection:
    def test_trail_uses_real_linestring(self):
        fc = assets_to_geojson([_trail(asset_id="t1")], {"t1": [_REAL_LINE]})
        feat = fc["features"][0]
        assert feat["geometry"]["coordinates"] == _REAL_LINE["coordinates"]
        assert feat["properties"]["geom_source"] == "real"

    def test_multiple_trails_become_multilinestring(self):
        line2 = {"type": "LineString", "coordinates": [[-3.9, 40.7], [-3.8, 40.7]]}
        fc = assets_to_geojson([_trail(asset_id="t1")], {"t1": [_REAL_LINE, line2]})
        geom = fc["features"][0]["geometry"]
        assert geom["type"] == "MultiLineString"
        assert len(geom["coordinates"]) == 2

    def test_point_asset_anchored_on_real_trace(self):
        # El viewpoint se ancla en un vértice de la traza real (vértice medio).
        fc = assets_to_geojson([_viewpoint(asset_id="v1")], {"v1": [_REAL_LINE]})
        feat = fc["features"][0]
        assert feat["geometry"]["type"] == "Point"
        assert feat["geometry"]["coordinates"] in _REAL_LINE["coordinates"]
        assert feat["properties"]["geom_source"] == "real"

    def test_no_real_geometry_falls_back_to_approx(self):
        fc = assets_to_geojson([_trail(asset_id="t1")], {"t1": []})
        assert fc["features"][0]["properties"]["geom_source"] == "approx"

    def test_missing_asset_id_falls_back_to_approx(self):
        fc = assets_to_geojson([_viewpoint(asset_id="v9")], {})
        assert fc["features"][0]["properties"]["geom_source"] == "approx"
