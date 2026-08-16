# Claude Code Context: SNTO — Alpine Edition

SNTO means Smart Natural Tourism Observatory. This repository is the **Alpine
Edition**, derived with history from `snto-smart-tourism-observatory`. Its pilot
is Parque Nacional de Sierra Nevada (Andalucía). The base PNSG engine must keep
working, but its releases, DOI, cloud resources and validation state do not
transfer to this repository.

Canonical roadmap: `docs/roadmap/alpine-v0.1.md`.

## Current status

- Version: `0.1.0.dev0`; no Alpine release or DOI yet.
- `main`: four Alpine PRs merged (#1–#4), latest SHA `7059e39` (2026-07-29).
- Dashboard: Sierra Nevada is selectable and exposes 53 OAPN assets.
- Real data: summer GEE series for 53 assets; NDSI February 2024 for 43/53;
  Copernicus slope for 53/53.
- Geometry caveat: the seasonal layer samples municipality centroid + stable
  jitter, not the real trail trace.
- Evidence caveat: SCM and socioeconomic/visitor attributes retain simulated or
  proxy components; nothing is field-validated.
- CI: current branch reports 1,060 passing / 1 skipped. Lint, coverage,
  typecheck job and PostgreSQL integration job completed successfully.
- Deployment: there is no Alpine production deployment. The Azure workflow is
  manual-only, disabled by default and targets dedicated Alpine resource names.

## Alpine-specific modules

- `src/features/alpine_spectral.py`: NDSI, seasonal SCL masking, NIR water
  floor, snowline, snowpack duration and borreguil degradation.
- `src/geospatial/alpine_dem.py`: slope-magnitude-scaled asymmetric corridor.
- `src/spatial_causality/alpine_causality.py`: 200–500 m control constrained to
  the trail elevation band ±50 m; rutting also requires the slope gate.
- `src/risk_engine/public_roi.py`: TRAGSA base rate × slope factor plus clearly
  labelled socioeconomic scenarios.
- `src/territorial/alpine_fixtures.py`: 53 dashboard assets from the real Sierra
  Nevada GEE series; proxy fields are documented in the module.
- `src/platform/alpine_asset_layers.py`: lightweight runtime loader for the
  committed NDSI/slope CSV.
- `src/platform/alpine_dashboard.py` + `src/ui/tabs/tab_alpine.py`: pure map/TPI
  builders and Streamlit rendering.
- `scripts/build_alpine_asset_layers.py`: offline sampling pipeline.
- `scripts/alpine_winter_check.py`: winter NDSI/DEM validation helper.

## Alpine non-negotiables

- Never reuse the base SCL exclusion list for winter: class 11 (snow/ice) is
  signal in winter and noise in summer.
- NDSI alone is not a snow test; always apply the NIR water floor.
- Do not label flat-terrain degradation as rutting; keep the slope gate.
- Never present centroid+jitter sampling as trail-level topographic precision.
- Keep real, calibrated, synthetic and simulated evidence visibly separated.
- Do not claim field validation until a Sierra Nevada campaign has run.
- Do not reuse the base observatory's Azure app, DOI, release numbering or
  production-state claims.

## Development contracts

- Python ≥3.12.
- `app.py` is composition/navigation; UI modules live under `src/ui/`.
- The Alpine navigation entry, render branch, territory builder and map layers
  must move together; shell and navigation tests enforce the contract.
- Heavy raster/STAC work stays offline; the dashboard consumes versioned light
  assets and must fail soft when they are absent.
- Work through feature branches and PRs; do not modify `main` directly.
- Preserve the base PNSG path and its tests when extending Alpine behavior.

## Deployment safety

`.github/workflows/deploy-azure-container-apps.yml` must remain manual-only
until dedicated Alpine infrastructure exists. It requires both:

1. repository variable `SNTO_ALPINE_DEPLOY_ENABLED=true`; and
2. typed workflow confirmation `alpine-production`.

Expected resource names are `rg-snto-alpine-app`, `snto-alpine` and image
`snto-alpine`. See `DEPLOY.md`. A normal merge must run CI only.

## Next actions

1. Complete the `0.1.0` documentation/visual-QA gate and cut an honest prototype
   release.
2. Ingest real trail geometries and replace centroid+jitter sampling.
3. Complete multi-tile, multi-date NDSI coverage for all 53 assets.
4. Execute observed altitude-matched SCM zones.
5. Replace Madrid socioeconomic fallbacks with Andalusian sources and add a
   real visitor-pressure feed.
6. Design and execute Sierra Nevada field validation before a `1.0.0` claim.
