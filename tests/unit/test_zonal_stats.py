"""Unit tests for src.geospatial.zonal_stats (issue #9)."""
from __future__ import annotations

import numpy as np
import pytest
from affine import Affine
from shapely.geometry import box

from src.geospatial.zonal_stats import reproject_polygon, zonal_mean

# A 20x20 raster of 10 m pixels, origin at (0, 100) — EPSG:25830-flavoured but
# the CRS math itself does not care, this is a synthetic local grid.
_TRANSFORM = Affine(10.0, 0.0, 0.0, 0.0, -10.0, 200.0)
_CRS = "EPSG:25830"


def _grid(value: float = 1.0, shape=(20, 20)) -> np.ndarray:
    return np.full(shape, value, dtype=np.float32)


def test_reproject_polygon_is_a_noop_for_matching_crs() -> None:
    poly = box(0, 0, 50, 50)
    out = reproject_polygon(poly, "EPSG:25830", "EPSG:25830")
    assert out is poly


def test_reproject_polygon_changes_coordinates_for_different_crs() -> None:
    poly = box(-3.0, 37.0, -2.99, 37.01)  # EPSG:4326 degrees
    out = reproject_polygon(poly, "EPSG:4326", "EPSG:25830")
    # UTM coordinates are on the order of 1e5-1e6, not ~-3..37.
    assert out.bounds[0] > 100_000


def test_zonal_mean_averages_only_pixels_inside_the_polygon() -> None:
    arr = _grid(1.0)
    arr[:10, :] = 5.0  # top half (higher rows→lower y) reads 5.0
    # Polygon covering only the bottom half of the grid (y in [0, 100]).
    poly = box(0, 0, 200, 100)
    mean, n = zonal_mean(arr, _TRANSFORM, poly, _CRS, _CRS, min_pixels=1)
    assert mean == pytest.approx(1.0)
    assert n > 0


def test_zonal_mean_honours_an_extra_valid_mask() -> None:
    arr = _grid(3.0)
    poly = box(0, 100, 200, 200)
    valid = np.zeros(arr.shape, dtype=bool)
    valid[:5, :5] = True  # only a small corner is "valid" (e.g. cloud-free)
    mean, n = zonal_mean(
        arr, _TRANSFORM, poly, _CRS, _CRS, valid_mask=valid, min_pixels=1
    )
    assert mean == pytest.approx(3.0)
    assert n == 25


def test_zonal_mean_is_none_below_the_min_pixel_floor() -> None:
    arr = _grid(2.0)
    # A sliver polygon that only grazes a handful of pixels.
    poly = box(0, 0, 10, 10)
    mean, n = zonal_mean(arr, _TRANSFORM, poly, _CRS, _CRS, min_pixels=1000)
    assert mean is None


def test_zonal_mean_is_none_for_a_polygon_outside_the_grid() -> None:
    arr = _grid(2.0)
    poly = box(10_000, 10_000, 10_100, 10_100)
    mean, n = zonal_mean(arr, _TRANSFORM, poly, _CRS, _CRS)
    assert mean is None
    assert n == 0


def test_zonal_mean_ignores_non_finite_pixels() -> None:
    arr = _grid(4.0)
    arr[0, 0] = np.nan
    poly = box(0, 190, 10, 200)  # covers just the top-left pixel(s)
    mean, n = zonal_mean(arr, _TRANSFORM, poly, _CRS, _CRS, min_pixels=1)
    assert mean is None or mean == pytest.approx(4.0)
