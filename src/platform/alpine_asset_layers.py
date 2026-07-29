"""
SNTO Alpine Edition — per-asset seasonal map layers (Sierra Nevada pilot)
========================================================================
Loads the precomputed per-asset NDSI and slope values that colour the alpine
map by season, from ``clean_assets/sierra_nevada_asset_layers.csv``.

The dashboard must stay light: it reads a small CSV here, with **no rasterio /
STAC dependency at runtime**. The heavy work — sampling the winter NDSI raster
and the Copernicus DEM at each asset's mapped position — is done offline by
``scripts/build_alpine_asset_layers.py``, which writes that CSV.

When the CSV is absent (the sampler has not been run) the loader returns empty
mappings, and the alpine tab falls back to tier colouring with its honest
"NDSI/slope not loaded" caption — never a fabricated colour.

Provenance: NDSI is real (Sentinel-2 scene, water-masked by the NIR floor);
slope is real (Copernicus DEM-30). Both are sampled at the asset's **approximate
mapped position** (municipality centroid + jitter), not its true trace, so they
are indicative, not survey-grade. Coverage is partial: an asset outside the NDSI
scene footprint simply has no NDSI value.
"""
from __future__ import annotations

import csv
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_LAYERS_CSV = _ROOT / "clean_assets" / "sierra_nevada_asset_layers.csv"

# Only the Sierra Nevada dashboard key carries alpine layers.
_ALPINE_DASHBOARD_KEY = "sn"

__all__ = ["LAYERS_CSV", "load_alpine_asset_layers"]

LAYERS_CSV = _LAYERS_CSV


def _to_float(raw: str | None) -> float | None:
    if raw in (None, "", "null", "nan", "NaN"):
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def load_alpine_asset_layers(
    dashboard_key: str,
    path: Path | None = None,
) -> tuple[dict[str, float], dict[str, float]]:
    """Return ``(ndsi_by_asset, slope_by_asset)`` for the season-coloured map.

    Args:
        dashboard_key: dashboard territory key; only ``"sn"`` has alpine layers.
        path: override CSV path (for tests). Defaults to the shipped file.

    Returns:
        Two dicts ``asset_id -> value``. Either is empty when the territory is
        not Sierra Nevada, the CSV is missing, or that column has no value —
        the alpine tab treats an empty mapping as "not loaded".
    """
    if dashboard_key != _ALPINE_DASHBOARD_KEY:
        return {}, {}

    csv_path = path or _LAYERS_CSV
    if not csv_path.exists():
        return {}, {}

    ndsi_by_asset: dict[str, float] = {}
    slope_by_asset: dict[str, float] = {}
    with open(csv_path, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            asset_id = row.get("asset_id")
            if not asset_id:
                continue
            ndsi = _to_float(row.get("ndsi"))
            slope = _to_float(row.get("slope_deg"))
            if ndsi is not None:
                ndsi_by_asset[asset_id] = ndsi
            if slope is not None:
                slope_by_asset[asset_id] = slope

    return ndsi_by_asset, slope_by_asset
