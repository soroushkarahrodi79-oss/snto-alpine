"""
Shared raster-sampling helpers for Sierra Nevada per-asset values.

Extracted from ``scripts/build_alpine_asset_layers.py`` so the winter
snow-series builder (issue #8) can reuse the exact same "sample along the
real OAPN trace, falling back to centroid+jitter" logic instead of
duplicating it — one asset should get the same sample points regardless of
which script is pulling values for it.
"""
from __future__ import annotations

import numpy as np

from src.platform.map_layers import _flatten_coords, _jitter, _region_centroid

_MAX_TRACE_PTS = 24  # cap the vertices sampled along a real trace
_WIN = 3          # sampling half-window (pixels) -> 7x7 patch at 10 m
_MIN_VALID = 4    # minimum valid pixels to accept a sample


def sample_points_for_asset(
    asset, geoms: dict[str, list[dict]]
) -> list[tuple[float, float]]:
    """Points (lat, lon) to sample for this asset.

    Along the REAL OAPN trace when available (evenly subsampled vertices), so
    sampled indices are the trail's own values; otherwise a single
    centroid+jitter point — the same approximation the map falls back to.
    """
    trace = geoms.get(asset.asset_id)
    if trace:
        verts: list[list[float]] = []
        for g in trace:
            verts.extend(_flatten_coords(g))
        if verts:
            step = max(1, len(verts) // _MAX_TRACE_PTS)
            return [(v[1], v[0]) for v in verts[::step]]  # geojson is (lon, lat)
    lat, lon = _region_centroid(asset.region)
    return [_jitter(asset.asset_id, lat, lon)]


def sample_raster_mean(ds, arr, x, y, *, mask=None) -> float | None:
    """Mean of a small patch around map coords (x, y), honouring nodata/mask."""
    row, col = ds.index(x, y)
    h, w = arr.shape
    if not (0 <= row < h and 0 <= col < w):
        return None
    r0, r1 = max(0, row - _WIN), min(h, row + _WIN + 1)
    c0, c1 = max(0, col - _WIN), min(w, col + _WIN + 1)
    patch = arr[r0:r1, c0:c1]
    valid = np.isfinite(patch)
    if ds.nodata is not None:
        valid &= patch != ds.nodata
    if mask is not None:
        valid &= mask[r0:r1, c0:c1]
    if int(valid.sum()) < _MIN_VALID:
        return None
    return float(patch[valid].mean())


def mean_over_points(ds, arr, transformer, pts, *, mask=None) -> float | None:
    """Average raster value over all sample points that fall on valid pixels."""
    vals: list[float] = []
    for lat, lon in pts:
        x, y = transformer.transform(lon, lat)
        v = sample_raster_mean(ds, arr, x, y, mask=mask)
        if v is not None:
            vals.append(v)
    return sum(vals) / len(vals) if vals else None
