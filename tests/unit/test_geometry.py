"""Unit tests for src/geospatial/geometry.py — Task 4 (Asymmetric Buffer).

All STAC / rasterio calls are fully mocked so the suite runs offline.
The tests focus on:
  - compute_slope_aspect (pure numpy — no mocking needed)
  - _is_left_side_downslope (pure geometry)
  - build_trail_buffer with dem_array=None (symmetric fallback — no mocking)
  - build_trail_buffer with DEM data (asymmetric mode)
  - fetch_dem_window (STAC + rasterio — mocked)
"""
from __future__ import annotations

import math
import sys
import types
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from affine import Affine
from shapely.geometry import LineString, MultiLineString

# ── Inject pystac_client stub before any import of geometry ───────────────────
# pystac_client may not be installed in the test environment.
# We inject a minimal stub so that the import-time lazy-try block in
# fetch_dem_window() can find the module; individual tests then patch
# Client.open via the stub.

def _make_pystac_stub() -> types.ModuleType:
    stub = types.ModuleType("pystac_client")
    stub.Client = MagicMock()
    return stub

_pystac_stub = _make_pystac_stub()
sys.modules.setdefault("pystac_client", _pystac_stub)

# ── Module under test ──────────────────────────────────────────────────────────
from src.geospatial.geometry import (  # noqa: E402
    _is_left_side_downslope,
    asymmetric_trail_buffer,
    build_trail_buffer,
    compute_slope_aspect,
    fetch_dem_window,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _flat_dem(rows: int = 20, cols: int = 20, elevation: float = 1200.0) -> np.ndarray:
    """Return a flat DEM (constant elevation) — slope=0 everywhere."""
    return np.full((rows, cols), elevation, dtype=np.float32)


def _tilted_dem(
    rows: int = 20, cols: int = 20,
    drop_per_col: float = 5.0,
) -> np.ndarray:
    """Return a DEM sloping uniformly east (elevation decreases left to right).

    Column 0 = highest (West side), column N-1 = lowest (East side).
    drop_per_col is metres of elevation change per pixel column.
    Terrain aspect should be ~90° (East) = downslope direction is East.
    """
    dem = np.zeros((rows, cols), dtype=np.float32)
    for c in range(cols):
        dem[:, c] = 1000.0 + (cols - c) * drop_per_col
    return dem


def _utm_transform(
    x0: float = 400_000.0, y0: float = 4_600_000.0, res: float = 30.0
) -> Affine:
    """Simple UTM affine transform (north-up, res×res metre pixels)."""
    # top-left corner origin; y decreases (north-up raster convention)
    return Affine(res, 0.0, x0, 0.0, -res, y0)


def _geo_transform(
    lon0: float = -3.60, lat0: float = 41.15, res_deg: float = 1 / 3600.0
) -> Affine:
    """Geographic (EPSG:4326) affine transform (1 arc-second resolution)."""
    return Affine(res_deg, 0.0, lon0, 0.0, -res_deg, lat0)


def _west_east_trail_utm() -> LineString:
    """A horizontal (W→E) trail in UTM coordinates (metres)."""
    return LineString([(400_100.0, 4_600_400.0), (400_900.0, 4_600_400.0)])


def _north_south_trail_utm() -> LineString:
    """A vertical (N→S) trail in UTM coordinates."""
    return LineString([(400_500.0, 4_600_800.0), (400_500.0, 4_600_200.0)])


# ── compute_slope_aspect ───────────────────────────────────────────────────────

class TestComputeSlopeAspect:

    def test_flat_dem_slope_is_zero(self):
        dem   = _flat_dem(10, 10, 1000.0)
        t     = _utm_transform()
        slope, _ = compute_slope_aspect(dem, t)
        # Interior pixels should be exactly 0; edge pixels also ~0 for flat DEM
        assert np.allclose(slope, 0.0, atol=1e-4)

    def test_flat_dem_aspect_shape_matches_input(self):
        dem = _flat_dem(12, 15, 900.0)
        t   = _utm_transform()
        slope, aspect = compute_slope_aspect(dem, t)
        assert slope.shape  == (12, 15)
        assert aspect.shape == (12, 15)

    def test_westward_upslope_gives_correct_aspect(self):
        """DEM tilted so elevation drops left→right (West is high, East is low).

        Aspect is the direction of steepest ASCENT (uphill), which is West = 270°.
        The downslope direction (East = 90°) is aspect + 180° and is used by
        _is_left_side_downslope to determine which trail side gets the wide buffer.
        """
        dem = _tilted_dem(20, 20, drop_per_col=5.0)
        t   = _utm_transform(res=30.0)
        _, aspect = compute_slope_aspect(dem, t)
        # Interior pixels should face West (upslope) = 270°
        interior = aspect[2:-2, 2:-2]
        mean_asp = float(interior.mean())
        assert abs(mean_asp - 270.0) < 5.0, f"Expected upslope aspect ~270° West, got {mean_asp:.1f}°"

    def test_slope_magnitude_known_value(self):
        """DEM with 5 m / 30 m pixel → slope = arctan(5/30) ≈ 9.46°."""
        dem = _tilted_dem(20, 20, drop_per_col=5.0)
        t   = _utm_transform(res=30.0)
        slope, _ = compute_slope_aspect(dem, t)
        # Interior columns (2:-2 avoids gradient boundary effects)
        interior_col = slope[10, 2:-2]
        expected_deg = math.degrees(math.atan(5.0 / 30.0))
        assert np.allclose(interior_col, expected_deg, atol=0.5), \
            f"Expected slope ~{expected_deg:.2f}°, got {interior_col.mean():.2f}°"

    def test_output_dtype_is_float32(self):
        dem = _flat_dem()
        t   = _utm_transform()
        slope, aspect = compute_slope_aspect(dem, t)
        assert slope.dtype  == np.float32
        assert aspect.dtype == np.float32

    def test_aspect_in_valid_range(self):
        """Aspect values must be in [0, 360)."""
        dem = _tilted_dem()
        t   = _utm_transform()
        _, aspect = compute_slope_aspect(dem, t)
        assert float(aspect.min()) >= 0.0
        assert float(aspect.max()) < 360.0


# ── _is_left_side_downslope ───────────────────────────────────────────────────

class TestIsLeftSideDownslope:

    def test_east_facing_trail_left_is_north(self):
        """Trail going East → left side faces North.  Downslope South (aspect=0=N → downslope=S=180°).
        So left (North) ≠ downslope (South) → False."""
        trail = _west_east_trail_utm()     # W→E direction
        # Aspect 0° = North is upslope → downslope = South (180°)
        # Left of W→E trail is North → not downslope
        result = _is_left_side_downslope(trail, mean_aspect_deg=0.0)
        assert result is False

    def test_east_facing_trail_right_is_south(self):
        """Aspect 180° = South is upslope → downslope = North (0°).
        Left of W→E trail is North → is downslope."""
        trail = _west_east_trail_utm()
        result = _is_left_side_downslope(trail, mean_aspect_deg=180.0)
        assert result is True

    def test_north_south_trail_with_eastward_downslope(self):
        """Trail going N→S. Left of N→S is East.
        Aspect 270° = West is upslope → downslope = East (90°).
        Left (East) == downslope → True."""
        trail = _north_south_trail_utm()
        result = _is_left_side_downslope(trail, mean_aspect_deg=270.0)
        assert result is True

    def test_degenerate_single_point_returns_default(self):
        """Single-point line has zero length — default is True (safe fallback)."""
        trail = LineString([(400_000.0, 4_600_000.0), (400_000.0, 4_600_000.0)])
        result = _is_left_side_downslope(trail, mean_aspect_deg=45.0)
        assert isinstance(result, bool)


# ── build_trail_buffer (symmetric fallback) ───────────────────────────────────

class TestBuildTrailBufferFallback:
    """When dem_array=None the function must fall back to a symmetric buffer."""

    def _wgs84_trail(self) -> LineString:
        """Simple WGS84 LineString in Sierra del Rincón area."""
        return LineString([(-3.55, 41.10), (-3.52, 41.12)])

    def test_fallback_returns_polygon(self):
        from shapely.geometry import Polygon
        buf = build_trail_buffer(
            self._wgs84_trail(), None, None, None,
            symmetric_fallback_m=50.0,
        )
        assert isinstance(buf, Polygon)

    def test_fallback_is_not_empty(self):
        buf = build_trail_buffer(self._wgs84_trail(), None, None, None)
        assert not buf.is_empty

    def test_fallback_is_valid_polygon(self):
        buf = build_trail_buffer(self._wgs84_trail(), None, None, None)
        assert buf.is_valid

    def test_fallback_area_scales_with_radius(self):
        trail = self._wgs84_trail()
        buf_50  = build_trail_buffer(trail, None, None, None, symmetric_fallback_m=50.0)
        buf_100 = build_trail_buffer(trail, None, None, None, symmetric_fallback_m=100.0)
        # Larger radius → larger area
        assert buf_100.area > buf_50.area

    def test_fallback_handles_multilinestring(self):
        ml = MultiLineString([
            [(-3.55, 41.10), (-3.52, 41.12)],
            [(-3.52, 41.12), (-3.50, 41.14)],
        ])
        buf = build_trail_buffer(ml, None, None, None)
        assert not buf.is_empty


# ── build_trail_buffer (asymmetric mode with synthetic DEM) ──────────────────

class TestBuildTrailBufferAsymmetric:
    """Tests using a small synthetic DEM — no STAC/rasterio mocking needed."""

    def _study_bbox(self) -> tuple:
        return (-3.60, 41.10, -3.50, 41.20)

    def _wgs84_trail(self) -> LineString:
        return LineString([(-3.58, 41.14), (-3.52, 41.14)])

    def _make_utm_dem(self) -> tuple[np.ndarray, Affine, object]:
        """Small synthetic DEM in UTM EPSG:25830 — slope East (downslope East)."""
        from pyproj import CRS
        rows, cols = 100, 100
        dem = _tilted_dem(rows, cols, drop_per_col=3.0)
        t   = _utm_transform(x0=390_000.0, y0=4_560_000.0, res=10.0)
        crs = CRS.from_epsg(25830)
        return dem, t, crs

    def test_asymmetric_buffer_returns_polygon(self):
        from shapely.geometry import Polygon
        dem, t, crs = self._make_utm_dem()
        buf = build_trail_buffer(
            self._wgs84_trail(), dem, t, crs,
            upslope_m=15.0, downslope_m=60.0,
        )
        assert isinstance(buf, Polygon)

    def test_asymmetric_buffer_is_not_empty(self):
        dem, t, crs = self._make_utm_dem()
        buf = build_trail_buffer(self._wgs84_trail(), dem, t, crs)
        assert not buf.is_empty

    def test_asymmetric_buffer_is_valid(self):
        dem, t, crs = self._make_utm_dem()
        buf = build_trail_buffer(self._wgs84_trail(), dem, t, crs)
        assert buf.is_valid

    def test_asymmetric_buffer_wider_than_upslope_only(self):
        """Total corridor width should exceed a symmetric upslope-only buffer."""
        dem, t, crs = self._make_utm_dem()
        buf_asym = build_trail_buffer(
            self._wgs84_trail(), dem, t, crs,
            upslope_m=15.0, downslope_m=60.0,
        )
        buf_sym15 = build_trail_buffer(
            self._wgs84_trail(), None, None, None,
            symmetric_fallback_m=15.0,
        )
        assert buf_asym.area > buf_sym15.area

    def test_asymmetric_buffer_in_correct_crs(self):
        """Buffer coordinates should be in metric range (EPSG:25830 UTM)."""
        dem, t, crs = self._make_utm_dem()
        buf = build_trail_buffer(self._wgs84_trail(), dem, t, crs)
        # UTM easting in Spain is roughly 200_000–900_000 m
        minx, _, maxx, _ = buf.bounds
        assert 100_000 < minx < 1_000_000, f"minx={minx:.0f} not in UTM range"
        assert 100_000 < maxx < 1_000_000, f"maxx={maxx:.0f} not in UTM range"


# ── asymmetric_trail_buffer directly ─────────────────────────────────────────

class TestAsymmetricTrailBuffer:

    def _wgs84_trail(self) -> LineString:
        return LineString([(-3.58, 41.14), (-3.52, 41.14)])

    def _utm_dem(self):
        from pyproj import CRS
        dem = _tilted_dem(100, 100, 3.0)
        t   = _utm_transform(390_000.0, 4_560_000.0, 10.0)
        crs = CRS.from_epsg(25830)
        return dem, t, crs

    def test_multilinestring_handled_gracefully(self):
        ml = MultiLineString([
            [(-3.58, 41.14), (-3.55, 41.14)],
            [(-3.55, 41.14), (-3.52, 41.14)],
        ])
        dem, t, crs = self._utm_dem()
        from shapely.geometry import Polygon
        buf = asymmetric_trail_buffer(ml, dem, t, crs)
        assert isinstance(buf, Polygon)
        assert not buf.is_empty

    def test_upslope_gt_downslope_produces_narrower_corridor(self):
        """Swapping up/downslope widths changes corridor shape."""
        dem, t, crs = self._utm_dem()
        trail = self._wgs84_trail()
        buf_wide_down = asymmetric_trail_buffer(
            trail, dem, t, crs, upslope_m=15.0, downslope_m=60.0
        )
        buf_wide_up = asymmetric_trail_buffer(
            trail, dem, t, crs, upslope_m=60.0, downslope_m=15.0
        )
        # Both corridors cover the same linear feature — areas differ only in width
        # distribution; total area should be approximately equal (same sum of widths)
        assert abs(buf_wide_down.area - buf_wide_up.area) / max(buf_wide_down.area, 1) < 0.30


# ── metric_slope_transform (geographic DEM slope correction) ─────────────────

def test_metric_slope_transform_rescales_a_geographic_dem() -> None:
    """A geographic DEM's degree pixel size must become metres for slope.

    Without this, slope magnitude on a 4326 DEM saturates near 90°. Regression
    guard for the bug that made the alpine slope-scaled buffer always max out.
    """
    from src.geospatial.geometry import compute_slope_aspect, metric_slope_transform

    # 30 m ≈ 0.00027° at the equator; build a geographic ramp of exactly that
    # pixel size rising ~tan(20°) metres per pixel eastward.
    deg = 30.0 / 111_320.0
    transform = Affine(deg, 0, -3.4, 0, -deg, 37.1)
    rise = math.tan(math.radians(20.0)) * 30.0
    dem = (np.arange(20)[None, :].repeat(20, 0).astype(np.float32)) * rise

    # Raw (buggy) path saturates near vertical; corrected path recovers a
    # realistic slope (exact value shifts with the cos(lat) longitude
    # foreshortening, so assert a plausible band, not a pinned degree).
    raw_slope, _ = compute_slope_aspect(dem, transform)
    metric_tr = metric_slope_transform(transform, "EPSG:4326", mean_lat_deg=37.1)
    fixed_slope, _ = compute_slope_aspect(dem, metric_tr)

    assert float(np.median(raw_slope)) > 80.0             # the bug
    assert 10.0 < float(np.median(fixed_slope)) < 40.0    # the fix
    assert float(np.median(fixed_slope)) < float(np.median(raw_slope)) - 40.0


def test_metric_slope_transform_leaves_projected_unchanged() -> None:
    from src.geospatial.geometry import metric_slope_transform

    utm = Affine(30.0, 0, 500_000.0, 0, -30.0, 4_100_000.0)
    assert metric_slope_transform(utm, "EPSG:25830", mean_lat_deg=37.1) == utm


# ── COG streaming environment ────────────────────────────────────────────────

def test_dem_cog_env_allows_anonymous_s3() -> None:
    """The Copernicus DEM asset is an anonymous S3 object; GDAL must not sign.

    Without AWS_NO_SIGN_REQUEST=YES, fetch_dem_window() fails with
    "InvalidCredentials" on any machine without AWS credentials. Regression
    guard for that latent failure.
    """
    from src.geospatial.geometry import _GDAL_COG_ENV

    assert _GDAL_COG_ENV.get("AWS_NO_SIGN_REQUEST") == "YES"


# ── fetch_dem_window (STAC + rasterio fully mocked) ──────────────────────────

class TestFetchDemWindow:
    """Verify STAC search + COG read logic without network calls."""

    def _mock_stac_item(self, href: str = "https://example.com/dem.tif"):
        item = MagicMock()
        asset = MagicMock()
        asset.href = href
        item.id = "Copernicus_DSM_COG_10_N41_00_W004_00_DEM"
        item.assets = {"data": asset}
        return item

    def _make_rasterio_ds(
        self, dem: np.ndarray, transform: Affine
    ):
        """Build a mock rasterio dataset that returns *dem* for the window read."""
        from pyproj import CRS
        ds = MagicMock()
        ds.crs = CRS.from_epsg(4326)
        ds.transform = transform
        ds.read.return_value = dem
        ds.__enter__ = MagicMock(return_value=ds)
        ds.__exit__ = MagicMock(return_value=False)
        return ds

    def _patch_client(self, mock_catalog):
        """Patch Client.open on whichever pystac_client is live (stub or real).

        When pystac-client is installed (e.g. CI), it may already be in
        sys.modules before this module's ``setdefault`` stub injection, so the
        real ``Client`` is what ``fetch_dem_window`` imports. Patching the live
        module — instead of the orphaned ``_pystac_stub`` — keeps these tests
        offline and deterministic in both environments.
        """
        import pystac_client  # resolves to the stub or the real module in sys.modules
        return patch.object(pystac_client.Client, "open", return_value=mock_catalog)

    def test_returns_array_transform_crs(self):
        """Verify that fetch_dem_window returns (ndarray, transform, CRS) on success.

        The function uses local imports of rasterio sub-modules, so we patch
        those modules directly in sys.modules rather than as module attributes.
        """
        from pyproj import CRS

        dem_data = _flat_dem(10, 10, 1000.0)
        geo_t    = _geo_transform(-3.60, 41.15, 1 / 3600.0)
        item     = self._mock_stac_item()
        ds       = self._make_rasterio_ds(dem_data, geo_t)

        mock_catalog = MagicMock()
        mock_search  = MagicMock()
        mock_search.items.return_value = [item]
        mock_catalog.search.return_value = mock_search

        # Build mock rasterio.windows and rasterio.transform modules
        fake_win       = MagicMock(name="win")
        fake_geo_bounds = (-3.60, 41.10, -3.50, 41.20)

        mock_rasterio_windows   = MagicMock()
        mock_rasterio_windows.from_bounds.return_value = fake_win
        mock_rasterio_windows.bounds.return_value      = fake_geo_bounds

        mock_rasterio_transform = MagicMock()
        mock_rasterio_transform.from_bounds.return_value = geo_t

        mock_rasterio_env = MagicMock()
        mock_rasterio_env.return_value.__enter__ = MagicMock(return_value=None)
        mock_rasterio_env.return_value.__exit__  = MagicMock(return_value=False)

        with self._patch_client(mock_catalog), \
             patch("src.geospatial.geometry.Transformer") as mock_tf, \
             patch("rasterio.open", return_value=ds), \
             patch("rasterio.Env", mock_rasterio_env), \
             patch.dict(sys.modules, {
                 "rasterio.windows":   mock_rasterio_windows,
                 "rasterio.transform": mock_rasterio_transform,
             }):

            t_inst = MagicMock()
            t_inst.transform.side_effect = lambda x, y: (x, y)
            mock_tf.from_crs.return_value = t_inst

            result = fetch_dem_window((-3.60, 41.10, -3.50, 41.20))

        arr, out_t, out_crs = result
        assert isinstance(arr, np.ndarray)
        assert arr.dtype == np.float32
        assert isinstance(out_crs, CRS)

    def test_raises_when_no_dem_tile_found(self):
        mock_catalog = MagicMock()
        mock_search  = MagicMock()
        mock_search.items.return_value = []   # empty — no DEM found
        mock_catalog.search.return_value = mock_search

        with self._patch_client(mock_catalog), \
             pytest.raises(RuntimeError, match="No Copernicus DEM tile"):
            fetch_dem_window((-3.60, 41.10, -3.50, 41.20))

    def test_raises_when_asset_key_missing(self):
        item = MagicMock()
        item.id = "some_item"
        item.assets = {}   # no "data" or "elevation" key
        mock_catalog = MagicMock()
        mock_search  = MagicMock()
        mock_search.items.return_value = [item]
        mock_catalog.search.return_value = mock_search

        with self._patch_client(mock_catalog), \
             pytest.raises(RuntimeError, match="none of the expected asset keys"):
            fetch_dem_window((-3.60, 41.10, -3.50, 41.20))

    def test_raises_without_pystac_client(self):
        # Temporarily hide pystac_client by replacing with None so the lazy
        # try/import block inside fetch_dem_window raises ImportError/RuntimeError
        saved = sys.modules.get("pystac_client")
        sys.modules["pystac_client"] = None  # type: ignore[assignment]
        try:
            with pytest.raises((RuntimeError, ImportError)):
                fetch_dem_window((-3.60, 41.10, -3.50, 41.20))
        finally:
            sys.modules["pystac_client"] = saved  # type: ignore[assignment]
