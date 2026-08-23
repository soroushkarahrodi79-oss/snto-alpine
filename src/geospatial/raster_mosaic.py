"""
Pure raster-mosaic helpers for the Alpine Edition multi-tile winter pipeline
(issue #7 — Sierra Nevada's massif spans 4 Sentinel-2 MGRS tiles: 30SVF,
30SWF, 30SVG, 30SWG; a single STAC item only covers part of the 53 assets).

Kept free of rasterio/STAC I/O so the merge and manifest logic is testable
without network access or real COGs — ``etl_raster_processor.py`` supplies
the per-tile arrays already windowed to a shared grid.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, fields
from pathlib import Path

import numpy as np


def merge_first_valid(
    arrays: list[np.ndarray],
    nodata: float,
) -> np.ndarray:
    """Mosaic same-shaped tile arrays, taking the first non-nodata value per pixel.

    ``arrays`` should be ordered by preference (e.g. ascending cloud cover) —
    once a pixel is filled by an earlier array it is never overwritten by a
    later one, so tile priority is caller-controlled. A pixel stays ``nodata``
    only if every array is ``nodata`` there (no tile covers it).

    Args:
        arrays: same-shape 2-D arrays, one per tile, already clipped/resampled
            to the same grid.
        nodata: sentinel value marking "this tile has no data at this pixel"
            (e.g. 0 for reflectance/SCL bands, out of the tile's real extent
            or its own no-data classification).

    Returns:
        A single 2-D array of the same shape and dtype as the inputs.
    """
    if not arrays:
        raise ValueError("merge_first_valid requires at least one array")
    shape = arrays[0].shape
    for a in arrays[1:]:
        if a.shape != shape:
            raise ValueError(f"shape mismatch: {a.shape} != {shape}")

    out = np.full(shape, nodata, dtype=arrays[0].dtype)
    filled = np.zeros(shape, dtype=bool)
    for a in arrays:
        take = (~filled) & (a != nodata)
        out[take] = a[take]
        filled |= take
    return out


def coverage_fraction(array: np.ndarray, nodata: float) -> float:
    """Fraction of pixels in *array* that are not *nodata*, in [0, 1]."""
    if array.size == 0:
        return 0.0
    return float(np.count_nonzero(array != nodata)) / array.size


@dataclass(frozen=True)
class TileManifestEntry:
    """One source scene contributing to a mosaic — the provenance record
    issue #7 asks for ("manifiesto de tesela, escena, fecha y cobertura")."""

    tile: str
    scene_id: str
    date: str
    cloud_pct: float
    coverage_pct: float


_MANIFEST_FIELDS = [f.name for f in fields(TileManifestEntry)]


def write_manifest_csv(entries: list[TileManifestEntry], out_path: Path) -> None:
    """Write the tile/scene/date/coverage manifest as a committed CSV."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_MANIFEST_FIELDS)
        writer.writeheader()
        for e in entries:
            writer.writerow(
                {
                    "tile": e.tile,
                    "scene_id": e.scene_id,
                    "date": e.date,
                    "cloud_pct": round(e.cloud_pct, 2),
                    "coverage_pct": round(e.coverage_pct, 2),
                }
            )


def read_manifest_csv(path: Path) -> list[TileManifestEntry]:
    """Inverse of :func:`write_manifest_csv`, mainly for tests."""
    with path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [
            TileManifestEntry(
                tile=row["tile"],
                scene_id=row["scene_id"],
                date=row["date"],
                cloud_pct=float(row["cloud_pct"]),
                coverage_pct=float(row["coverage_pct"]),
            )
            for row in reader
        ]
