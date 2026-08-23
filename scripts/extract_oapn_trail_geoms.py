"""
Extract the real OAPN trail geometries embedded in the Sierra Nevada GEE
template into a GeoJSON the dashboard can draw.

``scripts/gee_templates_oapn/pn_sierra_nevada.js`` embeds the 53 official OAPN
trail/MTB-route traces (simplified ~12 m) as
``ee.Feature(ee.Geometry.LineString([[lon, lat], ...]), {asset_id, ...})``.
This one-off parser lifts them into
``clean_assets/sierra_nevada_trails.geojson`` (EPSG:4326), keyed by asset_id,
with source/licence provenance per feature — replacing the municipality-centroid
approximation on the map and enabling on-trace NDSI/slope sampling.

Run once; the GeoJSON is committed::

    PYTHONPATH=. python scripts/extract_oapn_trail_geoms.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_JS = _ROOT / "scripts" / "gee_templates_oapn" / "pn_sierra_nevada.js"
_OUT = _ROOT / "clean_assets" / "sierra_nevada_trails.geojson"

_SOURCE = (
    "OAPN SIGRED (cartografía oficial Red de Parques Nacionales), vía plantilla GEE"
)
_LICENCE = "Reutilización institucional con cita — OAPN · P.N. Sierra Nevada"


def _match_bracket(text: str, start: int, open_ch: str, close_ch: str) -> int:
    """Return the index just past the bracket that opens at ``start``."""
    depth = 0
    for i in range(start, len(text)):
        c = text[i]
        if c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return i + 1
    raise ValueError(f"Unbalanced {open_ch}{close_ch} from {start}")


def main() -> None:
    js = _JS.read_text(encoding="utf-8")
    features: list[dict] = []

    # Most traces are LineString; a couple of long routes are MultiLineString.
    for m in re.finditer(r"ee\.Geometry\.(MultiLineString|LineString)\(", js):
        geom_type = m.group(1)
        coords_start = js.index("[", m.end())
        coords_end = _match_bracket(js, coords_start, "[", "]")
        coords = json.loads(js[coords_start:coords_end])

        props_start = js.index("{", coords_end)
        props_end = _match_bracket(js, props_start, "{", "}")
        props = json.loads(js[props_start:props_end])

        features.append({
            "type": "Feature",
            "geometry": {"type": geom_type, "coordinates": coords},
            "properties": {
                "asset_id": props["asset_id"],
                "nombre": props.get("nombre", ""),
                "category": props.get("category", ""),
                "source": _SOURCE,
                "licence": _LICENCE,
            },
        })

    crs84 = {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}}
    fc = {
        "type": "FeatureCollection",
        "crs": crs84,
        "features": features,
    }
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(features)} trail geometries to {_OUT}")


if __name__ == "__main__":
    main()
