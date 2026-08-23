"""Unit tests for the multi-tile mosaic helpers (issue #7)."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from src.geospatial.raster_mosaic import (
    TileManifestEntry,
    coverage_fraction,
    merge_first_valid,
    read_manifest_csv,
    write_manifest_csv,
)

NODATA = 0


def test_merge_combines_non_overlapping_tiles() -> None:
    """Two tiles covering disjoint halves of the grid mosaic into a full grid."""
    left = np.array([[1, 1, 0, 0], [1, 1, 0, 0]], dtype=np.uint16)
    right = np.array([[0, 0, 2, 2], [0, 0, 2, 2]], dtype=np.uint16)
    merged = merge_first_valid([left, right], nodata=NODATA)
    expected = np.array([[1, 1, 2, 2], [1, 1, 2, 2]], dtype=np.uint16)
    assert np.array_equal(merged, expected)


def test_merge_edge_pixel_takes_first_tile_by_priority() -> None:
    """Where tiles overlap at a shared boundary, the earlier (preferred) tile wins."""
    preferred = np.array([[5, 5], [0, 0]], dtype=np.uint16)
    fallback = np.array([[9, 9], [9, 9]], dtype=np.uint16)
    merged = merge_first_valid([preferred, fallback], nodata=NODATA)
    # top row: preferred tile had data -> its value kept, not overwritten
    assert merged[0, 0] == 5 and merged[0, 1] == 5
    # bottom row: preferred tile was nodata there -> fallback fills the gap
    assert merged[1, 0] == 9 and merged[1, 1] == 9


def test_merge_pixel_stays_nodata_when_no_tile_covers_it() -> None:
    a = np.array([[0, 1]], dtype=np.uint16)
    b = np.array([[0, 0]], dtype=np.uint16)
    merged = merge_first_valid([a, b], nodata=NODATA)
    assert merged[0, 0] == NODATA
    assert merged[0, 1] == 1


def test_merge_rejects_shape_mismatch() -> None:
    a = np.zeros((2, 2), dtype=np.uint16)
    b = np.zeros((3, 3), dtype=np.uint16)
    try:
        merge_first_valid([a, b], nodata=NODATA)
        raised = False
    except ValueError:
        raised = True
    assert raised


def test_merge_requires_at_least_one_array() -> None:
    try:
        merge_first_valid([], nodata=NODATA)
        raised = False
    except ValueError:
        raised = True
    assert raised


def test_coverage_fraction() -> None:
    arr = np.array([0, 1, 1, 0, 1], dtype=np.uint16)
    assert coverage_fraction(arr, nodata=0) == 0.6


def test_coverage_fraction_empty_array_is_zero() -> None:
    assert coverage_fraction(np.array([], dtype=np.uint16), nodata=0) == 0.0


def test_manifest_round_trips_through_csv(tmp_path: Path) -> None:
    entries = [
        TileManifestEntry("30SVF", "S2A_30SVF_20240222_0_L2A", "2024-02-22", 35.83, 92.5),
        TileManifestEntry("30SWF", "S2B_30SWF_20240224_0_L2A", "2024-02-24", 4.34, 88.1),
    ]
    out = tmp_path / "manifest.csv"
    write_manifest_csv(entries, out)
    assert out.exists()
    round_tripped = read_manifest_csv(out)
    assert round_tripped == entries
