from __future__ import annotations

# Risk model weights (must sum to 1.0)
WEIGHT_ECOLOGICAL: float = 0.4
WEIGHT_HUMAN_PRESSURE: float = 0.3
WEIGHT_VULNERABILITY: float = 0.3

# Alert score thresholds
ALERT_CRITICAL: float = 0.85
ALERT_URGENT: float = 0.70
ALERT_PREVENTIVE: float = 0.50

# NDVI rising trend threshold (units/month)
TREND_RISING_SLOPE: float = 0.002

# NDVI baselines for Iberian Mediterranean scrubland
NDVI_HEALTHY_BASELINE: float = 0.55
NDVI_DEGRADED_THRESHOLD: float = 0.30

# NDMI healthy baseline
NDMI_HEALTHY_BASELINE: float = 0.20

# Anomaly detection
ANOMALY_Z_THRESHOLD: float = 2.0

# Mock data parameters
MOCK_MONTHS: int = 12
MOCK_SPRING_PEAK_MONTH: int = 4  # April — Mediterranean phenology peak

# Human pressure proxy — geo-based thresholds
HP_ROAD_DECAY: float = 1.5          # α for road accessibility exponential decay
HP_SETTLEMENT_DECAY: float = 0.4    # α for settlement proximity decay
HP_POI_SATURATION: int = 15         # POI count that saturates poi_density factor
HP_TRAIL_SATURATION_KM: float = 8.0 # trail network km that saturates connectivity
HP_SLOPE_MAX_DEG: float = 30.0      # slope (degrees) above which access is zero

# Spectral fallback disturbance threshold (deseasonalized NDVI std)
HP_MAX_DISTURBANCE_STD: float = 0.05

# ── Operational EHS — per-scene percentile anchoring ─────────────────────────
# Governs calculate_delta_ehs.py. All five values are intentionally exposed
# here (not hardcoded in the logic) so they can be calibrated and defended.
#
# P_BASE / P_FLOOR are computed from the actual pixel distribution of each
# Sentinel-2 scene, per season, after excluding SCL-masked and trail-buffer
# pixels.  Adjust to match the ecological dynamics of the target territory.
#
# EHS_SEASON_FOR_BUDGET must be "summer" or "spring"; it selects which
# seasonal EHS column tis_engine.py reads for priority and budget.
EHS_P_BASE: int = 90              # percentile → baseline_sano (healthy reference)
EHS_P_FLOOR: int = 10             # percentile → suelo (degraded floor)
EHS_W_NDVI: float = 0.5           # weight of NDVI deficit in composite EHS
EHS_W_NDMI: float = 0.5           # weight of NDMI deficit in composite EHS
EHS_SEASON_FOR_BUDGET: str = "summer"  # season driving priority_score & tis_budget

# ── Operational SCM — raster-based SIG thresholds & causal factors ────────────
# Governs run_scm_operational.py and tis_engine.py.
#
# SIG = (NDVI_landscape − NDVI_core) / max(NDVI_landscape, 0.01)
# Thresholds match src/spatial_causality/analyzer.py for cross-module consistency.
#
# Causal factors apply the polluter-pays principle to the restoration budget:
# investment should be proportional to the fraction of degradation attributable
# to human pressure rather than to climate forcing beyond local control.
# These are starting values; adjust after field validation.
SCM_SIG_LOCALIZED_THRESHOLD: float = 0.15  # SIG above this → LOCALIZED_IMPACT
SCM_SIG_LANDSCAPE_THRESHOLD: float = 0.07  # SIG below this → LANDSCAPE_DRIVEN

SCM_LOCALIZED_FACTOR: float = 1.0   # trail use is the driver — full budget
SCM_MIXED_FACTOR: float = 0.5       # ambiguous cause — half budget
SCM_LANDSCAPE_FACTOR: float = 0.0   # climate is the driver — no local budget

# ── Dense-canopy NDVI saturation guard (Task 2) ──────────────────────────────
# Above this mean NDVI, the index saturates in closed forest canopies (e.g.
# beech groves – Hayedos) and loses sensitivity to sub-canopy stress.
# EHS weight is dynamically shifted toward NDMI, which continues to track
# water-content gradients even when the canopy is spectrally opaque in NIR.
EHS_DENSE_CANOPY_NDVI_THRESHOLD: float = 0.80  # saturation onset
EHS_W_NDVI_DENSE: float = 0.20  # NDVI weight in dense-canopy mode
EHS_W_NDMI_DENSE: float = 0.80  # NDMI weight in dense-canopy mode

# ── TRAGSA restoration unit rate ─────────────────────────────────────────────
# Order-of-magnitude linear rate for trail-surface restoration, TRAGSA 2023
# tariff. Previously duplicated as a literal in tis_engine.py and
# run_pipeline_a_filemode.py; centralised here so a tariff update lands in one
# place. Both consumers import it and keep their own module-level alias for
# backward compatibility.
TRAGSA_BASE_RATE_EUR_PER_M: float = 15.50

# ── Alpine Edition — high-mountain intervention cost ─────────────────────────
# Working above 2,000 m costs more than the tariff assumes: shorter weather
# windows, helicopter or pack-animal haulage instead of vehicles, and manual
# placement on ground no machine can reach. The multiplier ramps from 1.0 at
# ALPINE_COST_SLOPE_MIN_DEG to ALPINE_COST_MAX_FACTOR at HP_SLOPE_MAX_DEG.
#
# These are planning assumptions for the Sierra Nevada pilot, NOT a published
# TRAGSA high-mountain schedule. Any figure derived from them is a budget
# estimate for comparison between trails, not a tendered price.
ALPINE_COST_SLOPE_MIN_DEG: float = 10.0  # below this, the flat-terrain rate holds
ALPINE_COST_MAX_FACTOR: float = 1.80     # cost multiplier at HP_SLOPE_MAX_DEG

# ── Alpine Edition — regional tourism economy proxies ────────────────────────
# Lifted out of src/ui/tabs/tab_socioeco.py so the public ROI model is testable
# outside Streamlit. Both are proxy estimates, not INE/ALMUDENA observations —
# the socioeconomic snapshot in src/socioeconomic/ carries the real municipal
# indicators, and ROI statements must be badged accordingly.
ALPINE_SPEND_PER_VISITOR_EUR: float = 22.50  # daily local hospitality spend
ALPINE_VISITORS_PER_JOB: int = 2_500         # annual visitors sustaining one job

# ── Alpine Edition — snow detection (NDSI) ───────────────────────────────────
# Governs src/features/alpine_spectral.py for the Sierra Nevada pilot.
#
# NDSI = (B03_green − B11_swir1) / (B03_green + B11_swir1).  Snow is bright in
# green and strongly absorbing in SWIR, so it separates cleanly from rock and
# vegetation.  It does NOT separate cleanly from water, which is also bright in
# green and dark in SWIR — hence the NIR floor, which exploits the fact that
# snow stays reflective in NIR while liquid water does not (Hall et al. 1995).
#
# These are the standard MODIS/Landsat snow-mapping values; they are starting
# points for the Sierra Nevada pilot and must be recalibrated against ground
# observation before any operational snowline claim.
NDSI_SNOW_THRESHOLD: float = 0.40    # NDSI at/above which a pixel may be snow
NDSI_NIR_WATER_FLOOR: float = 0.11   # NIR reflectance below this → water, not snow

# ── Alpine Edition — snowline & snowpack ─────────────────────────────────────
# The snowline is reported as a low percentile of the elevation distribution of
# snow pixels rather than the strict minimum, which would be driven by single
# shaded outliers in ravines.  ALPINE_MIN_SNOW_PIXELS mirrors the small-sample
# guard in src/geospatial/aggregation.py: below it, report None rather than a
# number that looks authoritative but is noise.
ALPINE_SNOWLINE_PERCENTILE: float = 5.0  # percentile of snow-pixel elevations
ALPINE_MIN_SNOW_PIXELS: int = 25         # below this, snowline is not reported

# ── Alpine Edition — borreguiles (high-altitude pasture) baselines ───────────
# Borreguiles are wet alpine grasslands above the treeline.  Their EVI is
# structurally lower than closed forest, so NDVI-era baselines overstate
# degradation.  EVI is used instead of NDVI to avoid saturation and to stay
# comparable with the dense-canopy guard above.
# Unvalidated until the Sierra Nevada field campaign; do not present as truth.
ALPINE_EVI_HEALTHY_BASELINE: float = 0.35   # healthy borreguil growing-season EVI
ALPINE_NDMI_HEALTHY_BASELINE: float = 0.20  # healthy borreguil moisture
ALPINE_W_EVI: float = 0.5    # weight of EVI deficit in soil degradation index
ALPINE_W_NDMI: float = 0.5   # weight of NDMI deficit in soil degradation index

# ── Alpine Edition — observed SCM zones (issue #9) ───────────────────────────
# A zonal mean over too few pixels is dominated by rasterisation edge noise
# rather than the zone's actual condition — mirrors the ALPINE_MIN_SNOW_PIXELS
# small-sample guard above, at 10 m resolution over a 200-500 m annulus.
ALPINE_MIN_ZONE_PIXELS: int = 8

# ── Decision Confidence Score — minimum quality gates for can_act ─────────────
# Prevents issuing an actionable recommendation when foundational data quality
# or time-series robustness falls below minimum thresholds, even if the total
# DCS score reaches the HIGH band through strong spatial or signal scores.
# These are starting values; adjust after operational calibration.
DCS_MIN_DQ_FOR_ACTION: int = 10   # minimum DQ score (out of 25) to enable can_act
DCS_MIN_TR_FOR_ACTION: int = 12   # minimum TR score (out of 25) to enable can_act
