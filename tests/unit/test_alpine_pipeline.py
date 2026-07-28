"""Unit tests for the SNTO Alpine Edition pipeline (Sierra Nevada pilot).

Covers the four alpine modules end to end, fully offline:

  * ``src/features/alpine_spectral.py``      — NDSI, seasonal SCL masking,
                                                snowline, snowpack duration
  * ``src/geospatial/alpine_dem.py``          — slope sampling, slope-scaled
                                                corridor widths
  * ``src/spatial_causality/alpine_causality.py`` — altitude-matched control
                                                zone, MTB-vs-climate attribution
  * ``src/risk_engine/public_roi.py``         — slope-adjusted TRAGSA cost,
                                                public ROI statement

The tests concentrate on the behaviours that would silently produce a *plausible
but wrong* number, because those are the ones that survive review:

  - the winter mask must KEEP SCL class 11 while the summer mask DROPS it;
  - water must not be counted as snow (it shares the NDSI signature);
  - a flat trail must never be labelled "rutting" however degraded it is;
  - altitude matching must actually discard out-of-band control terrain.

All STAC / rasterio access is mocked, following ``tests/unit/test_geometry.py``.
"""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import numpy as np
import pytest
from affine import Affine
from shapely.geometry import LineString


# ── Inject pystac_client stub before importing any alpine geospatial module ───
def _make_pystac_stub() -> types.ModuleType:
    stub = types.ModuleType("pystac_client")
    stub.Client = MagicMock()
    return stub


sys.modules.setdefault("pystac_client", _make_pystac_stub())

from src.assets.models import AssetObservation  # noqa: E402
from src.features.alpine_spectral import (  # noqa: E402
    AlpineFeatures,
    AlpineSeason,
    alpine_valid_mask,
    compute_ndsi,
    compute_snowline_elevation,
    compute_snowpack_duration,
    compute_soil_degradation,
    is_snow_pixel,
    scl_exclusion_set,
    snow_mask,
)
from src.geospatial.alpine_dem import (  # noqa: E402
    ALPINE_MAX_DOWNSLOPE_M,
    ALPINE_STEEP_SLOPE_DEG,
    alpine_trail_buffer,
    sample_slope_along_trail,
    slope_scaled_buffer_widths,
)
from src.geospatial.geometry import compute_slope_aspect  # noqa: E402
from src.platform.evidence import EvidenceClass  # noqa: E402
from src.risk_engine.public_roi import (  # noqa: E402
    build_public_roi_statement,
    compute_restoration_cost,
    estimate_dependent_jobs,
    estimate_tourism_revenue,
    slope_cost_factor,
)
from src.spatial_causality.alpine_causality import (  # noqa: E402
    ALPINE_CONTROL_INNER_M,
    ALPINE_CONTROL_OUTER_M,
    CLASSIFICATION_CLIMATE,
    CLASSIFICATION_RUTTING,
    altitude_matched_control_zone,
    compute_attribution_index,
    compute_mtb_attribution,
)

# ── Shared fixtures / helpers ────────────────────────────────────────────────

_RES_M = 30.0
# A DEM window that genuinely contains the test trail in EPSG:25830 (a window
# that does not is silently treated as flat, which once masked a real failure).
_UTM_TRANSFORM = Affine(_RES_M, 0, 467400.0, 0, -_RES_M, 4101200.0)
_TRAIL_4326 = LineString([(-3.365, 37.055), (-3.360, 37.055)])
_TRAIL_UTM = LineString([(467900.0, 4100600.0), (468100.0, 4100600.0)])


def _ramp_dem(slope_deg: float, size: int = 60, base_m: float = 2500.0) -> np.ndarray:
    """A DEM rising west→east at exactly ``slope_deg``."""
    rise = np.tan(np.radians(slope_deg)) * _RES_M
    cols = np.arange(size)[None, :].repeat(size, 0).astype(np.float32)
    return cols * rise + base_m


def _summer(degradation: float, asset_id: str = "sn-01") -> AlpineFeatures:
    return AlpineFeatures(
        asset_id=asset_id,
        season=AlpineSeason.SUMMER,
        n_observations=3,
        mean_evi=0.30,
        mean_ndmi=0.20,
        soil_degradation_index=degradation,
    )


# ── TAREA 1 · NDSI ───────────────────────────────────────────────────────────


def test_compute_ndsi_known_value() -> None:
    assert abs(compute_ndsi(green=0.8, swir=0.2) - 0.6) < 1e-10


def test_compute_ndsi_zero_denominator_returns_zero() -> None:
    assert compute_ndsi(green=0.0, swir=0.0) == 0.0


def test_compute_ndsi_fresh_snow_is_high_and_rock_is_low() -> None:
    # Fresh snow: bright green, near-zero SWIR. Bare rock: similar in both.
    assert compute_ndsi(green=0.85, swir=0.08) > 0.7
    assert abs(compute_ndsi(green=0.22, swir=0.25)) < 0.15


# ── TAREA 1 · snow vs water discrimination ───────────────────────────────────


def test_snow_requires_both_high_ndsi_and_nir_floor() -> None:
    assert is_snow_pixel(ndsi=0.75, nir=0.30) is True


def test_water_is_rejected_despite_high_ndsi() -> None:
    """Glacial lagunas share snow's NDSI signature but absorb NIR.

    Without the NIR floor they would be counted as snow at exactly the
    elevations the snowline estimate depends on.
    """
    assert is_snow_pixel(ndsi=0.80, nir=0.02) is False


def test_low_ndsi_is_not_snow_however_bright_in_nir() -> None:
    assert is_snow_pixel(ndsi=0.10, nir=0.40) is False


# ── TAREA 1 · seasonal SCL masking (the core asymmetry) ──────────────────────


def test_winter_mask_keeps_snow_class_11() -> None:
    """Snow is the winter signal — excluding it would empty the scene."""
    assert 11 not in scl_exclusion_set(AlpineSeason.WINTER)
    valid = alpine_valid_mask(np.array([[11]]), AlpineSeason.WINTER)
    assert bool(valid[0, 0]) is True


def test_summer_mask_drops_snow_class_11() -> None:
    """In summer, residual snow and firn would inflate the pasture signal."""
    assert 11 in scl_exclusion_set(AlpineSeason.SUMMER)
    valid = alpine_valid_mask(np.array([[11]]), AlpineSeason.SUMMER)
    assert bool(valid[0, 0]) is False


@pytest.mark.parametrize("season", [AlpineSeason.WINTER, AlpineSeason.SUMMER])
@pytest.mark.parametrize("bad_class", [0, 1, 3, 6, 8, 9, 10])
def test_clouds_shadow_and_water_excluded_in_both_seasons(season, bad_class) -> None:
    valid = alpine_valid_mask(np.array([[bad_class]]), season)
    assert bool(valid[0, 0]) is False


@pytest.mark.parametrize("season", [AlpineSeason.WINTER, AlpineSeason.SUMMER])
def test_bare_rock_class_5_retained_above_treeline(season) -> None:
    """Class 5 is ubiquitous above the treeline; excluding it erases the massif."""
    valid = alpine_valid_mask(np.array([[5]]), season)
    assert bool(valid[0, 0]) is True


def test_nodata_mask_invalidates_regardless_of_scl() -> None:
    scl = np.array([[4, 4]])
    nodata = np.array([[True, False]])
    valid = alpine_valid_mask(scl, AlpineSeason.SUMMER, nodata_mask=nodata)
    assert bool(valid[0, 0]) is False
    assert bool(valid[0, 1]) is True


def test_snow_mask_honours_scene_validity_mask() -> None:
    ndsi = np.array([[0.9, 0.9]])
    nir = np.array([[0.3, 0.3]])
    valid = np.array([[True, False]])
    mask = snow_mask(ndsi, nir_array=nir, valid_mask=valid)
    assert bool(mask[0, 0]) is True
    assert bool(mask[0, 1]) is False


# ── TAREA 1 · snowline elevation ─────────────────────────────────────────────


def _snow_above(threshold_m: float, size: int = 10):
    dem = np.linspace(2000, 3000, size * size).reshape(size, size).astype(np.float32)
    ndsi = np.where(dem > threshold_m, 0.8, 0.1).astype(np.float32)
    nir = np.full((size, size), 0.30, dtype=np.float32)
    return ndsi, dem, nir


def test_snowline_tracks_the_snow_covered_elevation_band() -> None:
    ndsi, dem, nir = _snow_above(2500.0)
    snowline = compute_snowline_elevation(ndsi, dem, nir_array=nir)
    assert snowline is not None
    assert 2500.0 <= snowline <= 2600.0


def test_snowline_is_not_dragged_down_by_high_altitude_water() -> None:
    """Lagunas at altitude must not lower the reported snowline."""
    ndsi, dem, nir = _snow_above(2500.0)
    baseline = compute_snowline_elevation(ndsi, dem, nir_array=nir)

    ndsi_w, nir_w = ndsi.copy(), nir.copy()
    ndsi_w[0, :] = 0.8   # water: high NDSI …
    nir_w[0, :] = 0.02   # … but NIR-absorbing

    assert compute_snowline_elevation(ndsi_w, dem, nir_array=nir_w) == baseline


def test_snowline_returns_none_below_minimum_pixel_count() -> None:
    """Better no number than an authoritative-looking one built from noise."""
    ndsi = np.full((5, 5), 0.05, dtype=np.float32)
    dem = np.full((5, 5), 2400.0, dtype=np.float32)
    assert compute_snowline_elevation(ndsi, dem) is None


def test_snowline_raises_on_shape_mismatch() -> None:
    with pytest.raises(ValueError, match="does not match"):
        compute_snowline_elevation(np.zeros((4, 4)), np.zeros((5, 5)))


# ── TAREA 1 · snowpack duration & degradation ────────────────────────────────


def test_snowpack_duration_counts_only_snow_covered_periods() -> None:
    assert compute_snowpack_duration([0.8, 0.6, 0.1, 0.9]) == 3


def test_snowpack_duration_ignores_nan_gaps() -> None:
    """NaN is a masked-out composite, not a snow-free month."""
    assert compute_snowpack_duration([0.8, float("nan"), 0.9]) == 2


def test_soil_degradation_is_bounded_and_rises_as_condition_falls() -> None:
    healthy = compute_soil_degradation(mean_evi=0.35, mean_ndmi=0.20)
    degraded = compute_soil_degradation(mean_evi=0.05, mean_ndmi=0.02)
    assert 0.0 <= healthy <= 1.0 and 0.0 <= degraded <= 1.0
    assert degraded > healthy


# ── TAREA 1 · dual-season extractor ──────────────────────────────────────────


def _year_of_observations() -> list[AssetObservation]:
    return [
        AssetObservation(
            asset_id="sn-01",
            year=2024,
            month=m,
            ndvi=0.40,
            ndmi=0.20,
            evi=0.30,
            ndsi=0.70 if m in (1, 2, 12) else -0.10,
        )
        for m in range(1, 13)
    ]


def test_winter_mode_reports_snow_metrics_only() -> None:
    from src.features.alpine_spectral import extract_alpine_features

    features = extract_alpine_features(
        _year_of_observations(), AlpineSeason.WINTER, snowline_elevation_m=2550.0
    )
    assert features.n_observations == 3                # Jan, Feb, Dec
    assert features.snowpack_duration_periods == 3
    assert features.snowline_elevation_m == 2550.0
    assert features.mean_evi is None
    assert features.soil_degradation_index is None


def test_summer_mode_reports_pasture_metrics_only() -> None:
    from src.features.alpine_spectral import extract_alpine_features

    features = extract_alpine_features(_year_of_observations(), AlpineSeason.SUMMER)
    assert features.n_observations == 3                # Jun, Jul, Aug
    assert features.mean_evi is not None
    assert features.soil_degradation_index is not None
    assert features.mean_ndsi is None
    assert features.snowline_elevation_m is None


def test_december_belongs_to_winter_per_canonical_season_table() -> None:
    assert AlpineSeason.WINTER.months == (1, 2, 12)
    assert AlpineSeason.SUMMER.months == (6, 7, 8)


def test_extractor_rejects_empty_observations() -> None:
    from src.features.alpine_spectral import extract_alpine_features

    with pytest.raises(ValueError, match="empty"):
        extract_alpine_features([], AlpineSeason.WINTER)


def test_extractor_rejects_a_season_with_no_observations() -> None:
    from src.features.alpine_spectral import extract_alpine_features

    july_only = [
        AssetObservation(asset_id="sn-01", year=2024, month=7, ndvi=0.4, ndmi=0.2)
    ]
    with pytest.raises(ValueError, match="No observations fall in season"):
        extract_alpine_features(july_only, AlpineSeason.WINTER)


# ── TAREA 2 · slope-scaled corridor widths ───────────────────────────────────


@pytest.mark.parametrize("slope", [0.0, 5.0, 15.0, 19.9])
def test_gentle_slopes_keep_the_inherited_baseline_corridor(slope) -> None:
    assert slope_scaled_buffer_widths(slope) == (15.0, 60.0)


@pytest.mark.parametrize("slope", [30.0, 35.0, 60.0])
def test_corridor_saturates_at_the_maximum_downslope_width(slope) -> None:
    assert slope_scaled_buffer_widths(slope) == (15.0, ALPINE_MAX_DOWNSLOPE_M)


def test_corridor_ramps_linearly_between_20_and_30_degrees() -> None:
    _, downslope = slope_scaled_buffer_widths(25.0)
    assert abs(downslope - 70.0) < 1e-9


def test_uphill_side_never_widens_with_slope() -> None:
    """Trail runoff does not travel uphill; the source zone is slope-invariant."""
    assert all(
        slope_scaled_buffer_widths(float(s))[0] == 15.0 for s in range(0, 61)
    )


def test_downslope_width_is_monotonic_in_slope() -> None:
    widths = [slope_scaled_buffer_widths(s / 4.0)[1] for s in range(0, 200)]
    assert all(b >= a for a, b in zip(widths, widths[1:]))


def test_non_finite_slope_falls_back_to_the_narrow_baseline() -> None:
    assert slope_scaled_buffer_widths(float("nan")) == (15.0, 60.0)


def test_steep_threshold_is_the_documented_20_degrees() -> None:
    assert ALPINE_STEEP_SLOPE_DEG == 20.0


# ── TAREA 2 · slope sampling & buffer construction ───────────────────────────


@pytest.mark.parametrize("built_slope", [2.0, 12.0, 25.0])
def test_slope_sampling_recovers_the_dem_gradient(built_slope) -> None:
    slope_deg, _ = compute_slope_aspect(_ramp_dem(built_slope), _UTM_TRANSFORM)
    sampled = sample_slope_along_trail(
        _TRAIL_UTM, slope_deg, _UTM_TRANSFORM, "EPSG:25830"
    )
    assert abs(sampled - built_slope) < 1.0


def test_slope_sampling_assumes_flat_when_trail_is_outside_the_dem() -> None:
    """Conservative: yields the narrow corridor rather than an unfounded wide one."""
    slope_deg, _ = compute_slope_aspect(_ramp_dem(25.0), _UTM_TRANSFORM)
    far_away = LineString([(100000.0, 4000000.0), (100200.0, 4000000.0)])
    assert sample_slope_along_trail(
        far_away, slope_deg, _UTM_TRANSFORM, "EPSG:25830"
    ) == 0.0


def test_steep_trail_gets_a_wider_corridor_than_a_gentle_one() -> None:
    gentle = alpine_trail_buffer(
        _TRAIL_4326, _ramp_dem(2.0), _UTM_TRANSFORM, "EPSG:25830"
    )
    steep = alpine_trail_buffer(
        _TRAIL_4326, _ramp_dem(28.0), _UTM_TRANSFORM, "EPSG:25830"
    )
    assert gentle.is_valid and steep.is_valid
    assert steep.area > gentle.area


def test_buffer_falls_back_to_symmetric_without_a_dem() -> None:
    poly = alpine_trail_buffer(_TRAIL_4326, None, None, None)
    assert poly.is_valid and not poly.is_empty


# ── TAREA 3 · altitude-matched control zone ──────────────────────────────────


def test_control_zone_radii_are_the_documented_200_to_500_m() -> None:
    assert (ALPINE_CONTROL_INNER_M, ALPINE_CONTROL_OUTER_M) == (200, 500)


def test_control_zone_without_dem_is_a_plain_annulus() -> None:
    annulus = altitude_matched_control_zone(_TRAIL_UTM, None, None, None)
    assert annulus.is_valid and not annulus.is_empty
    # A plain annulus excludes the inner corridor.
    assert not annulus.intersects(_TRAIL_UTM.buffer(100.0).centroid.buffer(1.0))


def test_altitude_matching_discards_out_of_band_control_terrain() -> None:
    """On a slope the annulus spans many vegetation belts; matching removes them."""
    plain = altitude_matched_control_zone(_TRAIL_UTM, None, None, None)
    matched = altitude_matched_control_zone(
        _TRAIL_UTM, _ramp_dem(20.0), _UTM_TRANSFORM, "EPSG:25830"
    )
    assert not matched.is_empty
    assert matched.area < plain.area


def test_flat_terrain_retains_essentially_the_whole_annulus() -> None:
    """With no elevation gradient there is no confound to remove."""
    flat = np.full((60, 60), 2500.0, dtype=np.float32)
    plain = altitude_matched_control_zone(_TRAIL_UTM, None, None, None)
    matched = altitude_matched_control_zone(
        _TRAIL_UTM, flat, _UTM_TRANSFORM, "EPSG:25830"
    )
    assert matched.area == pytest.approx(plain.area, rel=0.02)


def test_control_zone_rejects_inverted_radii() -> None:
    with pytest.raises(ValueError, match="must be smaller"):
        altitude_matched_control_zone(_TRAIL_UTM, None, None, None, inner_m=500,
                                      outer_m=200)


# ── TAREA 3 · MTB vs climate attribution ─────────────────────────────────────


def test_attribution_index_is_the_excess_over_the_control() -> None:
    assert compute_attribution_index(0.55, 0.20) == pytest.approx(0.35)


def test_steep_trail_with_excess_degradation_is_flagged_as_rutting() -> None:
    result = compute_mtb_attribution(_summer(0.55), _summer(0.20), mean_slope_deg=26.0)
    assert result.classification == CLASSIFICATION_RUTTING
    assert result.confidence == "HIGH"
    assert result.slope_gate_passed is True


def test_identical_excess_on_flat_ground_is_not_rutting() -> None:
    """Flat ground compacts but does not channel runoff — it is not rutting."""
    result = compute_mtb_attribution(_summer(0.55), _summer(0.20), mean_slope_deg=4.0)
    assert result.classification != CLASSIFICATION_RUTTING
    assert result.slope_gate_passed is False


def test_control_degrading_equally_is_attributed_to_macroclimate() -> None:
    result = compute_mtb_attribution(_summer(0.50), _summer(0.52), mean_slope_deg=30.0)
    assert result.classification == CLASSIFICATION_CLIMATE


def test_attribution_carries_management_language_and_provenance() -> None:
    result = compute_mtb_attribution(_summer(0.55), _summer(0.20), mean_slope_deg=26.0)
    assert result.plain_language and result.management_implication
    assert result.evidence_class is EvidenceClass.SIMULATED


def test_real_zone_provenance_is_preserved_from_the_data_source() -> None:
    result = compute_mtb_attribution(
        _summer(0.55), _summer(0.20), 26.0, data_source="scm_real:gee_s2"
    )
    assert result.evidence_class is EvidenceClass.REAL


def test_attribution_rejects_winter_feature_vectors() -> None:
    winter = AlpineFeatures(
        asset_id="sn-01",
        season=AlpineSeason.WINTER,
        n_observations=3,
        soil_degradation_index=0.5,
    )
    with pytest.raises(ValueError, match="must be SUMMER"):
        compute_mtb_attribution(winter, _summer(0.2), 25.0)


def test_attribution_rejects_features_without_a_degradation_index() -> None:
    no_index = AlpineFeatures(
        asset_id="sn-01", season=AlpineSeason.SUMMER, n_observations=3
    )
    with pytest.raises(ValueError, match="no soil_degradation_index"):
        compute_mtb_attribution(no_index, _summer(0.2), 25.0)


# ── TAREA 4 · slope-adjusted restoration cost ────────────────────────────────


@pytest.mark.parametrize("slope", [0.0, 5.0, 10.0])
def test_flat_terrain_uses_the_unmodified_tragsa_rate(slope) -> None:
    assert slope_cost_factor(slope) == 1.0


def test_cost_factor_saturates_at_thirty_degrees() -> None:
    assert slope_cost_factor(30.0) == 1.80
    assert slope_cost_factor(55.0) == 1.80


def test_cost_factor_is_monotonic_in_slope() -> None:
    factors = [slope_cost_factor(s / 4.0) for s in range(0, 200)]
    assert all(b >= a for a, b in zip(factors, factors[1:]))


def test_one_kilometre_flat_trail_prices_at_the_base_rate() -> None:
    cost = compute_restoration_cost("sn-01", length_m=1000.0, mean_slope_deg=5.0)
    assert cost.total_eur == pytest.approx(15_500.0)
    assert cost.effective_rate_eur_per_m == pytest.approx(15.50)


def test_high_mountain_trail_costs_more_than_the_same_length_flat() -> None:
    flat = compute_restoration_cost("sn-01", 1000.0, 5.0)
    steep = compute_restoration_cost("sn-01", 1000.0, 30.0)
    assert steep.total_eur == pytest.approx(27_900.0)
    assert steep.total_eur > flat.total_eur


def test_restoration_cost_rejects_negative_length() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        compute_restoration_cost("sn-01", length_m=-1.0)


# ── TAREA 4 · socioeconomic ROI ──────────────────────────────────────────────


def test_dependent_jobs_scale_with_visitors_and_exposure() -> None:
    assert estimate_dependent_jobs(25_000) == pytest.approx(10.0)
    assert estimate_dependent_jobs(25_000, exposure=0.5) == pytest.approx(5.0)


def test_revenue_scales_with_visitors_and_exposure() -> None:
    assert estimate_tourism_revenue(10_000) == pytest.approx(225_000.0)
    assert estimate_tourism_revenue(10_000, exposure=0.2) == pytest.approx(45_000.0)


def test_zero_visitors_yield_no_jobs_or_revenue() -> None:
    assert estimate_dependent_jobs(0) == 0.0
    assert estimate_tourism_revenue(0) == 0.0


def test_public_roi_statement_names_cost_jobs_and_revenue() -> None:
    statement = build_public_roi_statement(
        asset_id="sn-01",
        asset_name="Vereda de la Estrella",
        length_m=2_400.0,
        visitor_capacity_annual=45_000,
        mean_slope_deg=24.0,
    )
    text = statement.statement
    assert "Vereda de la Estrella" in text
    assert "structural soil loss" in text
    assert "local jobs" in text
    assert "summer tourism revenue" in text
    assert statement.restoration_cost.total_eur > 0


def test_simulated_roi_statement_is_not_decision_grade() -> None:
    """A SIMULATED statement supports no funding decision on its own."""
    statement = build_public_roi_statement("sn-01", "Trail", 100.0, 1_000)
    assert statement.evidence_class is EvidenceClass.SIMULATED
    assert statement.is_decision_grade is False


def test_real_evidence_makes_the_statement_decision_grade() -> None:
    statement = build_public_roi_statement(
        "sn-01", "Trail", 100.0, 1_000, evidence_class=EvidenceClass.REAL
    )
    assert statement.is_decision_grade is True


def test_spanish_rendering_is_available_for_the_dashboard() -> None:
    statement = build_public_roi_statement("sn-01", "Sendero", 100.0, 1_000)
    assert "Intervenir en Sendero" in statement.statement_es
