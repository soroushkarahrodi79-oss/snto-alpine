"""Unit tests for the real OAPN trail geometries (Sierra Nevada, issue #6)."""
from __future__ import annotations

from pathlib import Path

from src.platform.alpine_trail_geoms import (
    TRAILS_GEOJSON,
    load_sierra_nevada_trail_geoms,
)
from src.territorial.alpine_fixtures import build_sierra_nevada_territory

_GEOMS = load_sierra_nevada_trail_geoms("sn")
_ASSET_IDS = {a.asset_id for a in build_sierra_nevada_territory()}


def _all_vertices(geom: dict) -> list[list[float]]:
    coords = geom["coordinates"]
    if geom["type"] == "LineString":
        return list(coords)
    if geom["type"] == "MultiLineString":
        return [pt for line in coords for pt in line]
    return []


def test_geojson_ships_with_the_repo() -> None:
    assert TRAILS_GEOJSON.exists()


def test_every_asset_has_a_real_trace() -> None:
    """Stable 1:1 correspondence between the 53 asset_ids and their traces."""
    assert set(_GEOMS) == _ASSET_IDS
    assert len(_GEOMS) == 53


def test_each_entry_is_a_list_of_geometry_dicts() -> None:
    for asset_id, geoms in _GEOMS.items():
        assert isinstance(geoms, list) and geoms, asset_id
        for g in geoms:
            assert g["type"] in ("LineString", "MultiLineString")
            assert g["coordinates"]


def test_coordinates_are_epsg4326_within_sierra_nevada() -> None:
    for asset_id, geoms in _GEOMS.items():
        for g in geoms:
            for lon, lat in _all_vertices(g):
                assert -3.7 < lon < -2.7, (asset_id, lon)
                assert 36.8 < lat < 37.35, (asset_id, lat)


def test_provenance_is_recorded_per_feature() -> None:
    import json

    fc = json.loads(TRAILS_GEOJSON.read_text(encoding="utf-8"))
    for feature in fc["features"]:
        props = feature["properties"]
        assert props.get("source")
        assert props.get("licence")


def test_non_sierra_nevada_territory_gets_no_geoms() -> None:
    assert load_sierra_nevada_trail_geoms("pnsg") == {}


def test_missing_file_returns_empty(tmp_path: Path) -> None:
    assert load_sierra_nevada_trail_geoms("sn", path=tmp_path / "none.geojson") == {}
