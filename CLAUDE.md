# Claude Code Context: SNTO — Alpine Edition

SNTO means Smart Natural Tourism Observatory. **This repository (`snto-alpine`, GitHub: `soroushkarahrodi79-oss/snto-alpine`) is the Alpine Edition**, forked with full history from `snto-smart-tourism-observatory` (kept as remote `upstream`, a local path in this environment). Its pilot is **Parque Nacional de Sierra Nevada** (Andalucía). The base PNSG pipeline is preserved intact and must keep working — Sierra Nevada is added alongside it, never in place of it. Sierra del Rincon is archived. The project is a Python 3.12+ / Streamlit scientific-product prototype with research and SaaS ambitions.

**Read this before trusting anything about "current status" below**: `main`'s git history (262+ commits) is dominated by *inherited* upstream work — the base observatory's v1.0→v2.0→v3.0-prep lineage (Fase 4/5/6, persistence layer, role-based UI, Azure Postgres cutover, etc.) all happened in `upstream` and arrived here as baked-in history at fork time. That work is real and the code is present, but it is **not** this fork's active backlog — nobody is doing Fase 6 / v2.0 work *in this repo*. The actual work items for `snto-alpine` live in **this repo's own GitHub issue tracker**, not in `docs/roadmap/*.md` (those docs are inherited upstream artifacts and describe upstream's v2.0/v3.0 narrative, not Alpine's).

## Where the real backlog lives

GitHub milestone **`Alpine 0.1.0`** (`soroushkarahrodi79-oss/snto-alpine`, milestone #1): *"Prototipo reproducible: aislamiento operativo, backlog trazable, QA visual y release honesta sin validación de campo."* As of 2026-08-23: 7 open issues, 0 closed.

| Issue | Title | Notes |
|---|---|---|
| #6 | Ingest real Sierra Nevada trail geometries (OAPN/OSM) | Replace centroid+jitter with real traces |
| #7 | Complete multi-tile winter NDSI coverage for the 53 assets | |
| #8 | Build multi-date snowpack and snowline series | |
| #9 | Execute altitude-matched observed SCM zones | |
| #10 | Replace Madrid socioeconomic fallback with Andalusian sources | |
| #11 | Design and execute the Sierra Nevada field validation campaign | |
| #12 | Release: visual QA and cut Alpine 0.1.0 | Finish line for the milestone |

`snto-alpine`'s own PR history is separate from upstream's numbering and currently small: #1–#13 (edition bootstrap, DEM anonymous-S3 fix, dashboard wiring, season colouring, roadmap/backlog docs), all merged. Don't confuse these with the PR numbers referenced inside inherited `docs/` content (those are upstream PRs, e.g. #61–#92, and don't exist in this repo).

## Alpine Edition — what is different

The edition exists because Sierra Nevada poses two spectrally opposite problems in one territory: winter snowpack retreat (snow is the *signal*) and summer borreguil erosion from MTB/hiking (snow is *noise*).

- `src/features/alpine_spectral.py` — NDSI, **seasonal SCL masking** (winter KEEPS class 11, summer DROPS it), snow-vs-water NIR floor, snowline, snowpack duration, borreguil degradation index. Imports `compute_evi`/`compute_ndmi` from `spectral.py` rather than redefining them.
- `src/geospatial/alpine_dem.py` — slope-**magnitude** scaling of the corridor (the base `asymmetric_trail_buffer` computes slope then discards it). 15 m upslope fixed; 60→80 m downslope between 20° and 30°.
- `src/spatial_causality/alpine_causality.py` — control zone narrowed to 200–500 m **and intersected with the trail's DEM elevation band ±50 m**, removing the elevation confound. Rutting requires both excess degradation *and* a slope gate.
- `src/risk_engine/public_roi.py` — TRAGSA €15.50/m × slope factor (1.0→1.8), plus dependent jobs/revenue. `TRAGSA_BASE_RATE_EUR_PER_M` lives in `src/config/constants.py`; `tis_engine.py` and `run_pipeline_a_filemode.py` import it.
- `src/platform/alpine_dashboard.py` (pure, no Streamlit) + `src/ui/tabs/tab_alpine.py` (render) + `NavigationModule("alpine", …)` in `src/ui/navigation.py` + the `app.py` dispatch branch. All four are required together or `tests/ui/test_app_shell.py` fails.
- `src/platform/alpine_trail_geoms.py` (new, issue #6) — loads the 53 real OAPN trail traces from `clean_assets/sierra_nevada_trails.geojson` (extracted once by `scripts/extract_oapn_trail_geoms.py` from the GEE template) into the `real_geoms` shape `map_layers.assets_to_geojson` expects, replacing the centroid+jitter approximation on the map. `build_alpine_asset_layers.py` samples NDSI/slope along the real trace when available.
- `etl_raster_processor.py --territory sierra_nevada` streams B03 + SCL and writes `clean_S2_NDSI.tif`. `etl_raster_intersection.py` switches on `SNTO_TERRITORY=sierra_nevada`.
- Tests: `tests/unit/test_alpine_pipeline.py`, `tests/unit/test_alpine_dashboard.py`, `tests/unit/test_alpine_trail_geoms.py`.

Alpine-specific non-negotiables, on top of the general ones below:

- **Never reuse the base SCL exclusion list for winter.** `gee_adapter._SCL_BAD_VALUES` drops class 11; for NDSI that empties the scene.
- **NDSI alone is not a snow test.** Water shares the signature; always apply the NIR floor (`is_snow_pixel`).
- **Do not label flat-terrain degradation as rutting.** The slope gate is what separates compaction from channelised erosion.
- Socioeconomic jobs/revenue are proxy estimates, not INE/ALMUDENA observations. Nothing in this edition is field-validated (that's the point of issue #11).

## Current work-in-progress (this environment, as of 2026-08-23)

- Branch `feat/oapn-trail-geometries`, commit `dfd7b24` (local, not pushed): closes out issue #6. Extraction script + loader module + 7 unit tests + wiring through `app.py`/`tab_alpine.py`/`build_alpine_asset_layers.py`. Code-reviewed and looks complete against the issue's acceptance criteria; pending a local test run (Python wasn't installed in this environment until now — see below) before pushing and opening a PR.
- A scratch script `scripts/_cap.py` (Playwright screenshot capture, undeclared dependency) exists locally, untracked, deliberately excluded from the #6 commit — useful later for issue #12's visual QA, but not part of #6's deliverable.
- Local dev environment now has a real Python at `C:\Users\Dell\AppData\Local\Python\bin\python.exe` (3.14) with a project `.venv`; the previous blocker (only the Microsoft Store execution-alias stub was on PATH) is resolved.

## Product Direction

SNTO should become a decision-intelligence layer for protected natural tourism destinations — not a replacement for ArcGIS, Google Earth Engine, Sentinel Hub, Tableau, or Power BI, but something that integrates with or sits above GIS, Earth observation, and BI tools. For the Alpine edition specifically: the near-term goal is a reproducible, honestly-labelled 0.1.0 prototype (milestone above), not feature parity with the base observatory's v2.0/v3.0 track.

## Non-Negotiables

- Do not modify `main` directly.
- Do not merge PRs without explicit human approval.
- Do not mix documentation PRs with functional changes.
- Do not blur real, calibrated, synthetic, or simulated evidence.
- Do not overclaim scientific validity before validation — nothing in this edition is field-validated until issue #11 happens.
- Preserve scientific transparency and methodological caveats.
- Don't confuse inherited `docs/roadmap/*.md` (upstream's v2.0/v3.0 narrative) with this fork's actual backlog (GitHub issues #6–#12 under milestone `Alpine 0.1.0`).

## Next Recommended Actions

1. Run `tests/unit/test_alpine_trail_geoms.py` (and the full suite) locally to confirm issue #6's WIP is green, then push `feat/oapn-trail-geometries` and open a PR against `main` — only with explicit owner go-ahead.
2. Pick the next issue from the `Alpine 0.1.0` milestone (#7–#12) — #7/#8/#9 are science/data groundwork that #6 partially unblocks (real traces enable precise on-trail sampling); #10 and #11 are more standalone; #12 is the release gate and comes last.
3. Once #6–#11 are closed, do the visual QA + release pass for #12 (this is where `scripts/_cap.py`'s intent — automated screenshot capture — could become a real dev tool if formalized with a declared Playwright dependency).
