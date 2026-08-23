# Claude Code Context: SNTO — Alpine Edition

SNTO means Smart Natural Tourism Observatory. **This repository (`snto-alpine`, GitHub: `soroushkarahrodi79-oss/snto-alpine`) is the Alpine Edition**, forked with full history from `snto-smart-tourism-observatory` (kept as remote `upstream`, a local path in this environment). Its pilot is **Parque Nacional de Sierra Nevada** (Andalucía). The base PNSG pipeline is preserved intact and must keep working — Sierra Nevada is added alongside it, never in place of it. Sierra del Rincon is archived. The project is a Python 3.12+ / Streamlit scientific-product prototype with research and SaaS ambitions. The base PNSG engine's releases, DOI, cloud resources and validation state do not transfer to this repository.

**Read this before trusting anything about "current status" below**: `main`'s git history (262+ commits) is dominated by *inherited* upstream work — the base observatory's v1.0→v2.0→v3.0-prep lineage (Fase 4/5/6, persistence layer, role-based UI, Azure Postgres cutover, etc.) all happened in `upstream` and arrived here as baked-in history at fork time. That work is real and the code is present, but it is **not** this fork's active backlog — nobody is doing Fase 6 / v2.0 work *in this repo*. The actual work items for `snto-alpine` live in **this repo's own GitHub issue tracker**, not in `docs/roadmap/*.md` (those docs are inherited upstream artifacts and describe upstream's v2.0/v3.0 narrative, not Alpine's). Canonical Alpine-specific roadmap notes: `docs/roadmap/alpine-v0.1.md`.

## Where the real backlog lives

GitHub milestone **`Alpine 0.1.0`** (`soroushkarahrodi79-oss/snto-alpine`, milestone #1): *"Prototipo reproducible: aislamiento operativo, backlog trazable, QA visual y release honesta sin validación de campo."* As of 2026-08-23: 3 open issues, 7 closed.

| Issue | Title | Status |
|---|---|---|
| #6 | Ingest real Sierra Nevada trail geometries (OAPN/OSM) | Closed — 53/53 real OAPN traces |
| #7 | Complete multi-tile winter NDSI coverage for the 53 assets | Closed — 52/53 real NDSI (1 documented residual outside every scene's swath) |
| #8 | Build multi-date snowpack and snowline series | Closed — Dec 2023–Mar 2024 monthly series |
| #9 | Execute altitude-matched observed SCM zones | Closed — 52/53 assets, real evidence class |
| #10 | Replace Madrid socioeconomic fallback with Andalusian sources | Closed — real INE crosswalk + real OAPN visitor figure |
| #11 | Design and execute the Sierra Nevada field validation campaign | **Open — design done, campaign NOT executed** |
| #12 | Release: visual QA and cut Alpine 0.1.0 | Open — finish line, blocked on #11's campaign actually running |
| #21 | Wire real independent snow-verification sources (AEMET + Cetursa) | **Open — both wired and live-verified: AEMET (`nev1`) and Cetursa (Umbraco backend API, plain unauthenticated JSON)** |
| #22 | Source real IECA/REDIAM municipal population and economy figures | Closed — real IECA/SIMA data for all 24 municipalities, cross-verified against IECA's own bulk export |

`snto-alpine`'s own PR history is separate from upstream's numbering: #1–#24 so far (edition bootstrap, DEM anonymous-S3 fix, dashboard wiring, season colouring, roadmap/backlog docs, then the #6–#11 stack, then #21/#22), all merged. Don't confuse these with the PR numbers referenced inside inherited `docs/` content (those are upstream PRs, e.g. #61–#92, and don't exist in this repo).

**Stacked-PR workflow note**: #6–#11 were built as a stack of branches (each based on the previous one's branch, not on `main`) so each issue got its own reviewable PR. Merging a PR whose base is a feature branch (not `main`) lands the commits on that base branch, **not on `main`** — the top-of-stack branch still needs its own PR against `main` to actually land the work. Verify with `git log origin/main..origin/<top-of-stack-branch>` before assuming a stack is fully landed.

## Current status (2026-08-23)

- Dashboard: Sierra Nevada is selectable and exposes 53 OAPN assets, all with real trail geometry.
- Winter: real multi-tile NDSI mosaic (52/53 assets) and a real Dec 2023–Mar 2024 monthly snow series with bootstrap-CI snowline uncertainty.
- Summer: real altitude-matched SCM zone attribution (52/53 assets, `evidence_class=REAL`) — corridor vs. control, elevation-band matched, slope gate preserved.
- Socioeconomic: real Granada/Almería INE municipal crosswalk (25 municipalities), real IECA/SIMA population + economy figures for all 24 real municipalities (population, % over 65, 10-year population change, unemployment, hostelería establishments, hotel capacity — each with its own sourced vintage), and one real (non-proxy) visitor-pressure figure (OAPN 2023 Sierra Nevada share, ≈734,295 visitors). IECA figures were cross-verified against IECA's own official bulk export ("Andalucía pueblo a pueblo" full dataset) — 24/24 exact match.
- Field validation: protocol **designed** (`docs/alpine_field_validation_protocol.md`) — dual-season BACI plan reusing the real SCM zones, candidate-plot generator, bootstrap CI for satellite↔field agreement. Both independent snow-verification sources are now wired and live-verified: AEMET OpenData mountain forecast for `nev1`, and Cetursa's ski-resort parte via its Umbraco backend API (plain unauthenticated JSON — the SPA is client-rendered but its backend is not, so no headless browser was needed) — see issue #21. The campaign itself has **not run**; no field data exists yet.
- Evidence caveat: nothing in this edition is field-validated. Any "piloto validado" claim is premature until issue #11's campaign actually executes and its results (positive or negative) are published.
- Deployment: there is no Alpine production deployment. The Azure workflow is manual-only, disabled by default and targets dedicated Alpine resource names.

## Alpine-specific modules

- `src/features/alpine_spectral.py` — NDSI, **seasonal SCL masking** (winter KEEPS class 11, summer DROPS it), snow-vs-water NIR floor, snowline, snowpack duration, borreguil degradation index. Imports `compute_evi`/`compute_ndmi` from `spectral.py` rather than redefining them.
- `src/geospatial/alpine_dem.py` — slope-**magnitude** scaling of the corridor (the base `asymmetric_trail_buffer` computes slope then discards it). 15 m upslope fixed; 60→80 m downslope between 20° and 30°.
- `src/spatial_causality/alpine_causality.py` — control zone narrowed to 200–500 m **and intersected with the trail's DEM elevation band ±50 m**, removing the elevation confound. Rutting requires both excess degradation *and* a slope gate.
- `src/spatial_causality/alpine_scm_zones.py` (issue #9) — wires the above to real monthly EVI/NDMI zone observations, with an explicit `NO_VALID_CONTROL` fallback (distinguishable from a real `MIXED` result) when a zone never had enough valid pixels.
- `src/geospatial/zonal_stats.py` (issue #9) — polygon zonal-mean raster stats (reprojects a zone polygon onto the raster grid, rasterises, means the valid pixels).
- `src/risk_engine/public_roi.py` — TRAGSA €15.50/m × slope factor (1.0→1.8), plus dependent jobs/revenue. `TRAGSA_BASE_RATE_EUR_PER_M` lives in `src/config/constants.py`; `tis_engine.py` and `run_pipeline_a_filemode.py` import it.
- `src/platform/alpine_dashboard.py` (pure, no Streamlit) + `src/ui/tabs/tab_alpine.py` (render) + `NavigationModule("alpine", …)` in `src/ui/navigation.py` + the `app.py` dispatch branch. All four are required together or `tests/ui/test_app_shell.py` fails.
- `src/platform/alpine_trail_geoms.py` (issue #6) — loads the 53 real OAPN trail traces from `clean_assets/sierra_nevada_trails.geojson` (extracted once by `scripts/extract_oapn_trail_geoms.py` from the GEE template) into the `real_geoms` shape `map_layers.assets_to_geojson` expects, replacing the centroid+jitter approximation on the map.
- `src/socioeconomic/alpine_mapping.py` (issue #10) — real Granada/Almería INE crosswalk (`clean_assets/sierra_nevada_municipios_ine.csv`), separate from and never falling back to the Madrid/PNSG crosswalk; carries the real OAPN visitor-pressure figure.
- `src/socioeconomic/alpine_indicators.py` (issue #22) — parses IECA/SIMA's "Andalucía pueblo a pueblo" municipal fact sheets into real population/economy figures, one committed snapshot per municipality (`src/socioeconomic/snapshot/sierra_nevada_municipal_indicators.json`, built by `scripts/build_alpine_municipal_indicators.py`). IECA's own suppression marks (`*`/`-`, small-municipality statistical secrecy) parse to `None` with an explicit caveat, never a fabricated number.
- `src/validation/alpine_plots.py` (issue #11) — deterministic candidate BACI plot coordinates sampled inside an asset's real local/control SCM zones, for the not-yet-executed field campaign.
- `src/validation/aemet_snow.py` (issue #21) — real AEMET OpenData client for Sierra Nevada's mountain-zone forecast (`nev1`); requires `AEMET_API_KEY` (free registration). `fetch_nivological_info()` exists but is verified to **not** cover Sierra Nevada (AEMET's avalanche bulletin only serves the Pyrenees) — no default `area`, so it can't be called assuming coverage that doesn't exist.
- `src/validation/cetursa_snow.py` (issue #21) — real Cetursa "parte de nieve" client, the second independent snow source. The public page is a client-rendered Next.js SPA, but it fetches its data from Cetursa's Umbraco backend (`umb.sierranevada.es/umbraco/api/parte/previsiones?culture=es`), which returns **plain unauthenticated JSON** — verified live via a bare `urllib` GET, no headless browser and no API key (the earlier "needs headless / dead end" verdict was pointing at the SPA page, not this backend). `fetch_snow_report()` + `parse_snow_report()` extract per-sector skiable-domain snow depths, quality, per-station temps and avalanche-risk index. Honest-fallback: closed-season sentinels (`espesorminimo "9999"`, empty fields, `min 9999 / max 0` pair) collapse to `None`, never a fabricated 0 cm; `has_snow_data()` gates presentation (verified `False` live on 2026-08-23, station closed). `superficieinnivada` is a year-round domain descriptor, **not** a live snow-area measurement — do not cross-check it against satellite area. Only the skiable domain (vertiente norte ~2,100–3,300 m), open season only; no historical archive, so useful prospectively (like AEMET).
- `etl_raster_processor.py` — `run_alpine_multitile()` (winter B03/B08/B11/SCL) and `run_alpine_multitile_summer()` (summer B02/B04/B08/B11/SCL, real vectorised EVI) mosaic across all 4 MGRS tiles (30SVF/30SWF/30SVG/30SWG) independently, then merge in cloud-ascending order.
- `scripts/build_alpine_snow_series.py`, `scripts/build_alpine_scm_zones.py` — orchestrate the live-STAC runs behind #8 and #9's committed `clean_assets/sierra_nevada_*.{json,csv}` outputs.
- Tests: `tests/unit/test_alpine_*.py`, `tests/unit/test_zonal_stats.py`, `tests/unit/test_alpine_plots.py`, `tests/unit/test_alpine_socioeconomic.py`, `tests/unit/test_alpine_indicators.py`, `tests/unit/test_aemet_snow.py`, `tests/unit/test_cetursa_snow.py`, `tests/unit/test_validation.py`.

## Alpine non-negotiables

- **Never reuse the base SCL exclusion list for winter.** `gee_adapter._SCL_BAD_VALUES` drops class 11; for NDSI that empties the scene.
- **NDSI alone is not a snow test.** Water shares the signature; always apply the NIR floor (`is_snow_pixel`).
- **Do not label flat-terrain degradation as rutting.** The slope gate is what separates compaction from channelised erosion.
- Never present centroid+jitter sampling as trail-level topographic precision where a real trace exists.
- Socioeconomic jobs/revenue are proxy estimates, not INE/ALMUDENA/IECA observations, except the one real OAPN visitor-pressure figure (issue #10) — keep the two visibly distinct.
- Keep real, calibrated, synthetic and simulated evidence visibly separated; an `evidence_class` must never be upgraded past what its `data_source` actually supports.
- Do not claim field validation until issue #11's campaign has actually run and its results are published — design existing is not validation.
- Do not reuse the base observatory's Azure app, DOI, release numbering or production-state claims.

## Development contracts

- Python ≥3.12.
- `app.py` is composition/navigation; UI modules live under `src/ui/`.
- The Alpine navigation entry, render branch, territory builder and map layers must move together; shell and navigation tests enforce the contract.
- Heavy raster/STAC work stays offline; the dashboard consumes versioned light assets and must fail soft when they are absent.
- Work through feature branches and PRs; do not modify `main` directly.
- Preserve the base PNSG path and its tests when extending Alpine behavior.
- When stacking PRs (issue A's branch built on issue B's branch), the top-of-stack branch still needs its own PR against `main` once the whole stack is reviewed — see the workflow note above.

## Deployment safety

`.github/workflows/deploy-azure-container-apps.yml` must remain manual-only until dedicated Alpine infrastructure exists. It requires both:

1. repository variable `SNTO_ALPINE_DEPLOY_ENABLED=true`; and
2. typed workflow confirmation `alpine-production`.

Expected resource names are `rg-snto-alpine-app`, `snto-alpine` and image `snto-alpine`. See `DEPLOY.md`. A normal merge must run CI only.

## Product Direction

SNTO should become a decision-intelligence layer for protected natural tourism destinations — not a replacement for ArcGIS, Google Earth Engine, Sentinel Hub, Tableau, or Power BI, but something that integrates with or sits above GIS, Earth observation, and BI tools. For the Alpine edition specifically: the near-term goal is a reproducible, honestly-labelled 0.1.0 prototype (milestone above), not feature parity with the base observatory's v2.0/v3.0 track.

## Non-Negotiables

- Do not modify `main` directly.
- Do not merge PRs without explicit human approval.
- Do not mix documentation PRs with functional changes.
- Do not blur real, calibrated, synthetic, or simulated evidence.
- Do not overclaim scientific validity before validation — nothing in this edition is field-validated until issue #11's campaign actually runs.
- Preserve scientific transparency and methodological caveats.
- Don't confuse inherited `docs/roadmap/*.md` (upstream's v2.0/v3.0 narrative) with this fork's actual backlog (GitHub issues #6–#12, #21, #22 under milestone `Alpine 0.1.0`).

## Next Recommended Actions

1. Run the Sierra Nevada field validation campaign designed in `docs/alpine_field_validation_protocol.md` (issue #11) — this is physical fieldwork (plots, penetrometer, snow transect), not something to execute from this environment. Publish the agreement results (`bootstrap_spearman_ci`, `control_impact_contrast`) honestly, whatever they show.
2. Once #11 closes with published results, do the visual QA + release pass for #12 — the milestone's finish line.
3. Issue #21: both snow sources (AEMET + Cetursa) are now wired and live-verified — Cetursa via its Umbraco backend API (`umb.sierranevada.es/umbraco/api/parte/previsiones`), plain unauthenticated JSON, no headless browser needed. The remaining open item on #21 is prospective, not code: run a live winter cross-check (satellite snowline/NDSI vs. Cetursa per-sector espesores in the skiable band, and AEMET isotherm) during a future winter — neither backend serves a historical archive, so the retroactive check against #8's closed Dec 2023–Mar 2024 series is not possible. Consider whether #21 can close as "sources wired" with the winter cross-check tracked under #11's campaign, or stays open until that run.
4. Optional, not filed as an issue: the IECA bulk export used to verify #22's data (`Andalucía pueblo a pueblo`, full-Andalucía spreadsheet) carries more real indicators than what's wired — elections, agriculture, real-estate transactions, top-5 business sectors per municipality. File an issue first if pursuing this rather than freelancing in-branch.
