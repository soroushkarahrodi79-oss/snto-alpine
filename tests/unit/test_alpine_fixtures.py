"""Unit tests for src/territorial/alpine_fixtures.py.

Guards the Sierra Nevada dashboard fixture built from the real GEE time series.
The load-bearing regression here is the map-placement contract: every asset's
``region`` must resolve to a centroid in ``map_layers._REGION_CENTROIDS``, or the
asset silently plots at the base reserve's default centroid (Madrid) instead of
on the massif.
"""
from __future__ import annotations

from src.platform.map_layers import _REGION_CENTROIDS
from src.territorial.alpine_fixtures import (
    build_sierra_nevada_territory,
    sierra_nevada_region_centroids,
)
from src.territorial.models import AssetType
from src.territorial.tpi import rank_assets

_ASSETS = build_sierra_nevada_territory()


def test_builds_the_53_oapn_assets() -> None:
    assert len(_ASSETS) == 53


def test_asset_ids_are_unique() -> None:
    ids = [a.asset_id for a in _ASSETS]
    assert len(set(ids)) == len(ids)


def test_only_trail_and_cycling_route_types() -> None:
    types = {a.asset_type for a in _ASSETS}
    assert types <= {AssetType.TRAIL, AssetType.CYCLING_ROUTE}
    # Both categories must be present (senderismo + ciclismo).
    assert AssetType.CYCLING_ROUTE in types and AssetType.TRAIL in types


def test_scores_are_in_range() -> None:
    for a in _ASSETS:
        assert 20.0 <= a.ehs <= 98.0, a.ehs
        assert 0.0 <= a.risk_score <= 1.0, a.risk_score
        assert 0.0 <= a.dcs <= 95.0, a.dcs
        assert 0.0 <= a.economic_importance <= 1.0
        assert 0.0 <= a.accessibility_score <= 1.0
        assert a.visitor_capacity_annual > 0
        assert 0.0 <= a.mk_p_value <= 1.0


def test_trend_directions_are_valid() -> None:
    valid = {"increasing", "decreasing", "no_trend"}
    assert {a.trend_direction for a in _ASSETS} <= valid


def test_alert_levels_are_valid() -> None:
    valid = {
        "CRITICAL_INTERVENTION",
        "URGENT_MONITORING",
        "PREVENTIVE_ACTION",
        "ROUTINE_MONITORING",
    }
    assert {a.alert_level for a in _ASSETS} <= valid


def test_every_region_resolves_to_a_map_centroid() -> None:
    """The map-placement contract: no asset may fall back to the Madrid default."""
    for a in _ASSETS:
        assert a.region in _REGION_CENTROIDS, (
            f"region '{a.region}' (asset {a.asset_id}) has no centroid; "
            "it would plot at the base reserve default instead of Sierra Nevada."
        )


def test_region_centroids_all_sit_on_the_massif() -> None:
    """Every Sierra Nevada centroid is within the massif bounding box."""
    for region, (lat, lon) in sierra_nevada_region_centroids().items():
        assert 36.8 < lat < 37.3, (region, lat)
        assert -3.7 < lon < -2.7, (region, lon)


def test_build_is_deterministic() -> None:
    """Proxy attributes are hash-derived, so two builds must be identical."""
    again = build_sierra_nevada_territory()
    assert [a.asset_id for a in again] == [a.asset_id for a in _ASSETS]
    assert [a.ehs for a in again] == [a.ehs for a in _ASSETS]
    assert [a.visitor_capacity_annual for a in again] == [
        a.visitor_capacity_annual for a in _ASSETS
    ]


def test_ranks_into_tiers_without_error() -> None:
    ranked = rank_assets(_ASSETS)
    assert len(ranked) == 53
    assert all(a.tier in (1, 2, 3, 4) for a in ranked)
    assert all(a.tpi is not None for a in ranked)


def test_registered_and_visible_in_the_dashboard() -> None:
    from src.ui.layout import _BUILD_FN, _TERRITORY_CONFIG, _VISIBLE_TERRITORIES

    assert "sn" in _TERRITORY_CONFIG
    assert "sn" in _BUILD_FN
    assert "sn" in _VISIBLE_TERRITORIES
    lat, lon, _zoom = _TERRITORY_CONFIG["sn"]["map_center"]
    assert 36.8 < lat < 37.3 and -3.7 < lon < -2.7
