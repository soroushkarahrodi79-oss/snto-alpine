"""
SNTO Alpine Edition — real OAPN trail geometries (Sierra Nevada pilot)
=====================================================================
Loads the real Sierra Nevada trail traces from
``clean_assets/sierra_nevada_trails.geojson`` in the ``real_geoms`` shape the
map builders expect: ``asset_id -> [geometry_dict]``.

These are the official OAPN cartographic traces (simplified ~12 m), extracted
from the GEE template by ``scripts/extract_oapn_trail_geoms.py``. When supplied
as ``real_geoms`` to :func:`src.platform.map_layers.assets_to_geojson`, each
asset is drawn on its **true trace** instead of the municipality-centroid
approximation; an asset with no trace falls back to the synthetic path (the
honest "no real geometry" state), because ``map_layers`` already handles a
missing entry that way.

Runtime is light: this reads one GeoJSON, no rasterio / STAC. Coordinates are
EPSG:4326 (lon, lat); metric work downstream reprojects to EPSG:25830.
"""
from __future__ import annotations

import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_GEOJSON = _ROOT / "clean_assets" / "sierra_nevada_trails.geojson"
_ALPINE_DASHBOARD_KEY = "sn"

__all__ = ["TRAILS_GEOJSON", "load_sierra_nevada_trail_geoms"]

TRAILS_GEOJSON = _GEOJSON


def load_sierra_nevada_trail_geoms(
    dashboard_key: str,
    path: Path | None = None,
) -> dict[str, list[dict]]:
    """Return ``asset_id -> [geometry]`` real traces for the Sierra Nevada map.

    Args:
        dashboard_key: only ``"sn"`` carries alpine trail geometries.
        path: override GeoJSON path (for tests). Defaults to the shipped file.

    Returns:
        Mapping of asset_id to a one-element list holding its GeoJSON geometry
        dict (LineString or MultiLineString). Empty when the territory is not
        Sierra Nevada or the file is absent — callers then fall back to the
        centroid approximation.
    """
    if dashboard_key != _ALPINE_DASHBOARD_KEY:
        return {}

    geojson_path = path or _GEOJSON
    if not geojson_path.exists():
        return {}

    fc = json.loads(geojson_path.read_text(encoding="utf-8"))
    geoms: dict[str, list[dict]] = {}
    for feature in fc.get("features", []):
        props = feature.get("properties") or {}
        asset_id = props.get("asset_id")
        geometry = feature.get("geometry")
        if asset_id and geometry:
            geoms.setdefault(asset_id, []).append(geometry)
    return geoms
