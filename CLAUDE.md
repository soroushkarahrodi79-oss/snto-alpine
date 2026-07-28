# Claude Code Context: SNTO — Alpine Edition

SNTO means Smart Natural Tourism Observatory. **This repository is the Alpine Edition**, forked with full history from `snto-smart-tourism-observatory` (kept as remote `upstream`). Its pilot is **Parque Nacional de Sierra Nevada** (Andalucía). The base PNSG pipeline is preserved intact and must keep working — Sierra Nevada is added alongside it, never in place of it. Sierra del Rincon is archived. The project is a Python 3.12 / Streamlit scientific-product prototype with research and SaaS ambitions.

## Alpine Edition — what is different

The edition exists because Sierra Nevada poses two spectrally opposite problems in one territory: winter snowpack retreat (snow is the *signal*) and summer borreguil erosion from MTB/hiking (snow is *noise*).

- `src/features/alpine_spectral.py` — NDSI, **seasonal SCL masking** (winter KEEPS class 11, summer DROPS it), snow-vs-water NIR floor, snowline, snowpack duration, borreguil degradation index. Imports `compute_evi`/`compute_ndmi` from `spectral.py` rather than redefining them.
- `src/geospatial/alpine_dem.py` — slope-**magnitude** scaling of the corridor (the base `asymmetric_trail_buffer` computes slope then discards it). 15 m upslope fixed; 60→80 m downslope between 20° and 30°.
- `src/spatial_causality/alpine_causality.py` — control zone narrowed to 200–500 m **and intersected with the trail's DEM elevation band ±50 m**, removing the elevation confound. Rutting requires both excess degradation *and* a slope gate.
- `src/risk_engine/public_roi.py` — TRAGSA €15.50/m × slope factor (1.0→1.8), plus dependent jobs/revenue. `TRAGSA_BASE_RATE_EUR_PER_M` now lives in `src/config/constants.py`; `tis_engine.py` and `run_pipeline_a_filemode.py` import it.
- `src/platform/alpine_dashboard.py` (pure, no Streamlit) + `src/ui/tabs/tab_alpine.py` (render) + `NavigationModule("alpine", …)` in `src/ui/navigation.py` + the `app.py` dispatch branch. All four are required together or `tests/ui/test_app_shell.py` fails.
- `etl_raster_processor.py --territory sierra_nevada` streams B03 + SCL and writes `clean_S2_NDSI.tif`. `etl_raster_intersection.py` switches on `SNTO_TERRITORY=sierra_nevada`.
- Tests: `tests/unit/test_alpine_pipeline.py` and `tests/unit/test_alpine_dashboard.py`.

Alpine-specific non-negotiables, on top of the general ones below:

- **Never reuse the base SCL exclusion list for winter.** `gee_adapter._SCL_BAD_VALUES` drops class 11; for NDSI that empties the scene.
- **NDSI alone is not a snow test.** Water shares the signature; always apply the NIR floor (`is_snow_pixel`).
- **Do not label flat-terrain degradation as rutting.** The slope gate is what separates compaction from channelised erosion.
- Socioeconomic jobs/revenue are proxy estimates, not INE/ALMUDENA observations. Nothing in this edition is field-validated.

## Current Status

- v1.0.0 → v1.5.0 are all released and tagged. **`main` is on `2.0.0` — the v2.0 release is PREPARED but the `v2.0.0` tag + GitHub Release are still pending the owner** (tag pushes are blocked from the agent environment; the owner tags after the visual pass + image rebuild). pyproject.toml / `src/_version` / CITATION.cff all read `2.0.0`; the last *pushed* stable tag is still `v1.5.0` (2026-07-18) until the owner tags `v2.0.0`. v2.0.0 consummates the roadmap's v2.0 milestone: modular architecture (Fase 4, shipped in v1.5.0) + persistent backend (Fase 5, shipped in v1.5.0) + role-based UI evolution (Fase 6, new). After the owner tags, bump the dev marker (e.g. `2.1.0.dev0`) in a follow-up, mirroring the v1.5.0→1.6.0.dev0 flow.
- v1.2.0 (OAPN multi-park expansion), v1.3.0 (statistical rigor), and v1.4.0 (decision integration: risk brief #12, GIS export #25, evidence separation #10, positioning #9, field-validation tooling #26) are merged. Only the manual GEE field-validation campaign for the pilot parks remains open work, not a code blocker.
- **v1.5.0 consolidates Fase 4, #28, and Fase 5** (see below) into one tagged, published release (GitHub Release live at the `v1.5.0` tag).
- **Fase 4 (`app.py` modularization, #27) is COMPLETE.** `app.py` went from ~3,170 lines to ~285 (composition/navigation only); the UI was extracted to `src/ui/`.
- **Audience-views rescue (#28) is COMPLETE.** The `claude/tourism-observatory-views-audit-jyl38k` branch was rescued (re-implemented, not cherry-picked) onto the modular structure.
- **Fase 5 (v2.0 persistent-backend foundations, ADR-011 / `docs/roadmap/plan_fase5_v2_foundations.md`) is COMPLETE in code and in production.** All 10 steps 5.0–5.9 are merged (PR #61 design; #62–#70 implementation): SQLAlchemy models + Alembic, typed repositories, a read+write `/api/v2` surface, lifecycle state machines with validated transitions, the alert & field-verification persistence bridges, an audit trail on every write, minimal API-key write-auth (reads open), and the first UI consumer ("Acciones urgentes" tab). **The production Postgres cutover (ADR-011 §4bis) was executed by the owner on 2026-07-18** — see "Next Recommended Actions" #2 for the live-infra facts. No cloud resource was provisioned by any Fase 5 code PR.
- **Fase 6 (v2.0 role-based UI evolution, `docs/roadmap/plan_fase6_v2_ui_evolution.md` implementing `docs/ux/ui-evolution-v2-spec.md`) is COMPLETE in code.** All steps 6.0–6.7f are merged (PRs #75–#89). The three §2 product decisions were resolved by their conservative recommendations and implemented: 2.1-A layer-grouped `st.tabs()` (`src/ui/navigation.py`, 4 IA layers Decidir/Diagnosticar/Evidenciar/Gobernar), 2.2-A the 3 existing views absorb the spec's 6 personas (extended `ViewProfile` with `home_layer`), 2.3 asset-as-a-page via `st.session_state` routing (`src/ui/asset_detail.py`). **Two-agent history:** steps 6.1/6.3–6.6/6.7a–d were implemented by the owner's Codex agent (`codex/*` branches, PRs #78–#87) on this session's design; 6.2a/b, 6.7e and 6.7f by Claude Code. Codex's off-remote 6.7e draft (local commit `47837b1`, never pushed) was superseded by PR #89.
- The operational roadmap is `docs/roadmap/plan_fases_post_v1.2.md`. With Fase 6 shipped, the remaining tracks are operational (field-validation campaign #26, ADR-012 API-deploy trigger watch) — see "Next Recommended Actions".

## Pull Requests

- No SNTO release PRs are currently pending. Fase 3 (#33–#37), Fase 4 modularization (#38–#53), the #28 audience-views rescue (#54–#59), Fase 5 v2.0 foundations (#61–#70), ADR-012 (#72), the v1.5.0 release (#73–#74), and Fase 6 UI evolution (#75–#89) are all merged. PR #85 (an earlier partial docs sync) was superseded by the Fase 6 closure sync and closed unmerged.
- Historical note: PR #1 (v1.1.0) merged; the statistical-rigor work formerly on `research/statistical-rigor` reached `main` via the v1.3.0 rescue.

## Architecture Facts

- `app.py` is composition/navigation only: page setup + sidebar assembly + the Fase 6 shell — an asset-as-a-page route check (`selected_asset_id` in `st.session_state` → `render_asset_page` + `st.stop()`), then nested `st.tabs()`: 4 IA layers (Decidir/Diagnosticar/Evidenciar/Gobernar, audience home layer first per `ViewProfile.home_layer`) × 13 modules dispatched by `NavigationModule.key` to their `render_tab_x(...)` — + footer. The layer/module contract lives in `src/ui/navigation.py` and is enforced by `tests/ui/test_navigation.py`.
- Gobernar-layer surfaces added late in Fase 6: `tab_reports.py` (6.7e — downloadable executive brief over the decision portfolio via `src/reporting/territorial_brief.py` + real-trend GIS GeoJSON via `src/reporting/gis_export.py`; the two asset sets are distinct and labelled) and `tab_config.py` (6.7f — read-only territory registry, `src/platform/territory_registry.py`; nothing is marked field-validated).
- The UI lives in `src/ui/`: `layout.py` (page config, institutional CSS, territory registry, cached `load_dashboard`), `render_helpers.py` (presentation primitives), `render_widgets.py` (`st.`-rendering widgets), `src/ui/tabs/` (one module per tab), and `src/ui/services/` (persistence-backed query services, e.g. `urgent_actions.py`).
- Audience views: `src/platform/views.py` (`ViewProfile.section()` is the single layered-disclosure contract), `src/platform/telemetry.py` (local opt-in usage telemetry, `SNTO_TELEMETRY=1`). Financial figures are invariant across views (verified by `tests/integration/test_view_modulation.py`).
- **Persistence layer (Fase 5, ADR-011):** `src/persistence/` — SQLAlchemy 2.0 models (`models/`), typed repositories (`repositories/`), services (`services/`: the alert & field-verification bridges, lifecycle state machines, and the single audit choke-point), `session.py` (engine/session reading `settings.database_url`), and Alembic migrations (`migrations/`). `src/api/v2/` is the read+write surface over it; write endpoints are gated by `require_write_auth` (API key, `SNTO_API_KEY`), reads are open. Built against SQLite by default; Postgres is env-gated (`SNTO_DB_*`) and never auto-provisioned by code — production now runs against Azure Postgres (`snto-db`) since the 2026-07-18 owner cutover. **The FastAPI app itself is not deployed**; the deployed Streamlit Container App consumes persistence in-process (`src/ui/services/`), so `/api/v2` currently exists as code + tests only.
- The analytical core under `src/` is well separated. The v2 API (`src/api/v2/`) is now the persistence-backed integration surface; the older stateless routers (`/evaluate_asset`, `/ranking`, `/alerts`) remain unchanged.
- The Streamlit dashboard is feature-rich; the audience-view modulation (#28) reduces cognitive density per role.

## Product Direction

SNTO has the intellectual core of a reference product but the body of an advanced academic prototype. It should become a decision-intelligence layer for protected natural tourism destinations. It should not try to replace ArcGIS, Google Earth Engine, Sentinel Hub, Tableau, or Power BI. It should integrate with or sit above GIS, Earth observation, and BI tools.

## Roadmap Discipline

- v1.1: integration, stabilization, real temporal evidence, evidence clarity.
- v1.2: controlled expansion and pilot readiness.
- v2.0: modular architecture, UI evolution, backend/platform foundations.
- v3.0: enterprise/institutional maturity and multi-park scaling.

## Non-Negotiables

- Do not modify `main` directly.
- Do not merge PRs without explicit human approval.
- Do not mix documentation PRs with functional changes.
- Do not begin major UI evolution before modularizing `app.py`.
- Do not blur real, calibrated, synthetic, or simulated evidence.
- Do not overclaim scientific validity before validation.
- Preserve scientific transparency and methodological caveats.

## Next Recommended Actions

v1.5.0 is released (Fases 0–4, the #28 rescue, and Fase 5 all shipped in it). Remaining / next:

1. **Owner cleanup:** issue #28 is closed. Old merged branches (`feature/v1.5.0-*`, `release/v1.4.0`) can be deleted whenever convenient — none are referenced by anything live.
2. **Production DB cutover (ADR-011 §4bis): ✅ EXECUTED by the owner on 2026-07-18.** Azure Postgres Flexible Server `snto-db` (v16, Burstable B1ms, PostGIS, Sweden Central, same RG as the Container App), narrow firewall (Azure services + owner IP), Alembic created all 9 tables, and the five `SNTO_DB_*` secrets are wired into the `snto-observatory` Container App. Verified live: the "Acciones Urgentes" tab shows the connected-but-empty state. `SNTO_API_KEY` intentionally left unset (writes open) for now. Rollback: unset the 5 `SNTO_DB_*` Container App vars → automatic fallback to local SQLite. Ops gotcha: Container Apps in Single-revision mode do NOT pick up updated secret values without an explicit `az containerapp revision restart`.
3. **Field-validation campaign (#26):** the tooling/protocol are merged (and Fase 5.6 added persistent `FieldVerification` records); the real ground-truth campaign (penetrometer/cover/erosion on PNSG priority assets) is manual field work, still pending — do not claim validation until collected.
4. **Deploy the `/api/v2` HTTP surface:** scoped in **ADR-012** (`docs/decisions/ADR-012.md`) — status quo (not deployed) until a named external consumer appears, then a second scale-to-zero Container App (`snto-api`) from the same image with `SNTO_API_KEY` set before first exposure. Awaiting owner go/no-go on the trigger; no resource provisioned by the ADR.
5. **Fase 6: ✅ COMPLETE in code (PRs #75–#89).** All 4 IA layers, persona home layers, asset-as-a-page, alert triage, and the six 6.7x module deep-dives (simulator v2, pressure/capacity, confidence, provenance, reports/exports, territorial config) are merged. Remaining before calling v2.0 UI "released": an owner visual pass of the deployed app (`streamlit run app.py` or the Container App) across the 4 layers and the 3 views, then cut the next release when satisfied.
6. **Deployed-app freshness:** the `snto-observatory` Container App serves whatever image was last built — after merging Fase 6, rebuild/redeploy the image to see the new 4-layer shell in production (and remember the Single-revision secret-restart gotcha from #2).

When cutting the next release, bump `pyproject.toml` from `1.6.0.dev0`, run `scripts/sync_readme.py`, and tag.

