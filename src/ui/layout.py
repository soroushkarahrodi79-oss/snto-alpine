"""
Dashboard shell layout — page config + institutional CSS (Fase 4, paso 11).

Extracted from app.py (issue #27, modularización). ``configure_page`` wraps the
one-time ``st.set_page_config`` (must run before any other st command) and
``inject_base_styles`` injects the institutional stylesheet. The CSS string is
verbatim from app.py.
"""
from __future__ import annotations

import streamlit as st

from src._version import __version__
from src.intervention import allocate_tis_budget, compare_scenarios
from src.platform import compute_executive_dashboard
from src.platform.enrichment import enrich_assets_with_satellite
from src.territorial.alpine_fixtures import build_sierra_nevada_territory
from src.territorial.fixtures import build_pnsg_territory, build_territory
from src.territorial.tpi import rank_assets


def configure_page() -> None:
    """Set Streamlit page config (title, icon, layout, About menu)."""
    st.set_page_config(
        page_title="SNTO — Inteligencia para la decisión en espacios protegidos",
        page_icon="🏔",
        layout="wide",
        initial_sidebar_state="expanded",
        menu_items={
            "About": (
                f"Smart Natural Tourism Observatory (SNTO) v{__version__} · "
                "Capa de inteligencia para la decisión en espacios naturales "
                "protegidos — se apoya en GIS y observación de la Tierra, no los "
                "sustituye · Caso activo: Parque Nacional Sierra de Guadarrama "
                "(Madrid · Segovia, España)"
            ),
        },
    )


_BASE_CSS = """
<style>
:root {
    --snto-space-1: 4px;
    --snto-space-2: 8px;
    --snto-space-3: 12px;
    --snto-space-4: 16px;
    --snto-space-6: 24px;
    --snto-space-8: 32px;
    --snto-border-hairline: #d9e0e7;
    --snto-text-primary: #0d1b2a;
    --snto-text-secondary: #4b5b6b;
}

[data-testid="stAppViewContainer"] > .main { background: #f4f5f7; }

[data-testid="stSidebar"] { background: #1b2d42; }
[data-testid="stSidebar"] .stMarkdown,
[data-testid="stSidebar"] .stCaption,
[data-testid="stSidebar"] hr {
    color: #c8d6e5 !important;
    border-color: #2e4560 !important;
}

/* ── TAREA 1: Contraste accesible en el selector de observatorio ──────── */
/* Opciones del st.radio — texto claro AA sobre fondo #1b2d42 */
[data-testid="stSidebar"] label[data-baseweb="radio"] p {
    color: #E0E6EE !important;
    font-size: 0.86rem !important;
}
[data-testid="stSidebar"] label[data-baseweb="radio"] {
    padding: 5px 8px;
    border-radius: 6px;
    transition: background 0.15s ease;
}
[data-testid="stSidebar"] label[data-baseweb="radio"]:hover {
    background: rgba(255,255,255,0.07);
}
/* Etiquetas de widgets, encabezados y negritas del sidebar */
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p,
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3,
[data-testid="stSidebar"] strong {
    color: #F2F6FA !important;
}
/* Selectbox y multiselect (futuras ampliaciones del sidebar) */
[data-testid="stSidebar"] [data-baseweb="select"] * {
    color: #E0E6EE !important;
}

/* Fila informativa institucional del sidebar */
.snto-side-row {
    display: flex; align-items: center; gap: 8px;
    padding: 4px 0; font-size: 0.82rem; color: #c8d6e5;
}
.snto-side-row .snto-side-icon { width: 18px; text-align: center; flex-shrink: 0; }
.snto-side-row strong { color: #F2F6FA; }

.kpi-card {
    background: #ffffff;
    border-radius: 6px;
    padding: 1rem 1.1rem 0.9rem;
    margin-bottom: 0.2rem;
    box-shadow: 0 1px 4px rgba(0,0,0,.08);
}
.kpi-meta  { font-size: 0.65rem; color: #9aa4af; text-transform: uppercase; letter-spacing: 0.08em; }
.kpi-name  { font-size: 0.875rem; color: #3d4a5c; font-weight: 600; margin: 0.15rem 0 0.45rem; }
.kpi-value { font-size: 1.45rem; font-weight: 700; color: #0d1b2a; line-height: 1.2; }
.kpi-badge {
    display: inline-block;
    font-size: 0.65rem; font-weight: 700; letter-spacing: 0.07em;
    padding: 0.2rem 0.6rem; border-radius: 3px; margin-top: 0.45rem;
}

/* Map legend chip */
.legend-chip {
    display: inline-block;
    width: 12px; height: 12px;
    border-radius: 50%;
    margin-right: 6px;
    vertical-align: middle;
}

/* Live alert chips */
.snto-alert-chip {
    display: flex; align-items: flex-start; gap: 8px;
    padding: 9px 12px; border-radius: 7px; border: 1px solid;
    min-width: 180px; max-width: 270px; flex-shrink: 0;
}
.snto-alert-name { font-size: 0.80rem; font-weight: 700; color: #0d1b2a; line-height: 1.2; }
.snto-alert-sub  { font-size: 0.68rem; color: #7a8899; margin-top: 1px; }
.snto-alert-bar  {
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 7px;
}
.snto-alert-title {
    font-size: 0.72rem; font-weight: 700; color: #7a8899;
    text-transform: uppercase; letter-spacing: 0.08em;
}
.snto-refresh-ts { font-size: 0.68rem; color: #9aa4af; }
.snto-pulse {
    display: inline-block; width: 7px; height: 7px;
    background: #22c55e; border-radius: 50%;
    margin-right: 5px; vertical-align: middle;
    animation: snto-pulse 1.8s infinite;
}
@keyframes snto-pulse {
    0%,100% { opacity:1; transform:scale(1); }
    50%      { opacity:0.35; transform:scale(0.8); }
}

/* Tier stat row in map hero */
.snto-tier-row {
    display: flex; align-items: center; justify-content: space-between;
    padding: 6px 10px; border-radius: 5px; background: #ffffff;
    border-left: 4px solid; margin-bottom: 5px;
    box-shadow: 0 1px 3px rgba(0,0,0,.06);
}

/* ── TAREA 1: Dynamic territory banner ──────────────────────────── */
.snto-banner {
    border-radius: 10px;
    padding: 18px 22px 14px;
    margin-bottom: 12px;
}
.snto-banner-badge {
    display: inline-flex; align-items: center; gap: 5px;
    padding: 4px 12px; border-radius: 20px;
    font-size: 0.70rem; font-weight: 600; letter-spacing: 0.05em;
    margin-right: 6px; margin-bottom: 4px;
}
.snto-banner-title {
    font-size: 1.30rem; font-weight: 600; margin: 8px 0 3px; line-height: 1.25;
}
.snto-banner-sub { font-size: 0.76rem; }

/* ── TAREA 2: Executive KPI strip ───────────────────────────────── */
.exec-kpi {
    background: #ffffff;
    border-radius: 8px;
    padding: 12px 14px 10px;
    border-top: 3px solid;
    box-shadow: 0 1px 4px rgba(0,0,0,.07);
    height: 100%;
}
.exec-kpi-label {
    font-size: 0.66rem; color: #7a8899;
    text-transform: uppercase; letter-spacing: 0.07em; margin-bottom: 4px;
}
.exec-kpi-value { font-size: 1.45rem; font-weight: 700; line-height: 1.15; }
.exec-kpi-delta { font-size: 0.69rem; margin-top: 4px; }

/* ── TAREA 3: Fichas de alerta rápida ───────────────────────────── */
.snto-ficha {
    background: #ffffff;
    border-radius: 7px;
    padding: 9px 12px;
    border-left: 4px solid;
    margin-bottom: 7px;
    box-shadow: 0 1px 3px rgba(0,0,0,.06);
}
.snto-ficha-name {
    font-size: 0.875rem; font-weight: 600; color: #0d1b2a;
    line-height: 1.3; clear: right;
}
.snto-ficha-meta { font-size: 0.67rem; color: #7a8899; margin-top: 1px; }
.snto-ficha-ehs {
    display: inline-block; font-size: 0.67rem; font-weight: 700;
    padding: 2px 6px; border-radius: 4px; float: right; margin-left: 8px;
}
.snto-ehs-bar {
    height: 3px; border-radius: 2px; background: #e8ecf0;
    margin-top: 5px; overflow: hidden;
}
.snto-ehs-fill { height: 100%; border-radius: 2px; }
.snto-panel-title {
    font-size: 0.67rem; font-weight: 600; color: #7a8899;
    text-transform: uppercase; letter-spacing: 0.07em; margin-bottom: 8px;
}

/* FASE 6.1: semantic hierarchy from the v2 design-system rules. */
.snto-decision-card {
    background: #ffffff;
    border-radius: 8px;
    border-top: 3px solid #33485c;
    padding: var(--snto-space-4);
    margin-bottom: var(--snto-space-6);
    box-shadow: 0 1px 4px rgba(0,0,0,.07);
}
.snto-asset-card {
    background: #ffffff;
    border-radius: 7px;
    border-left: 4px solid #607d8b;
    padding: var(--snto-space-3) var(--snto-space-4);
    margin-bottom: var(--snto-space-2);
}
.snto-evidence-card {
    background: #ffffff;
    border: 1px solid var(--snto-border-hairline);
    border-radius: 8px;
    padding: var(--snto-space-3) var(--snto-space-4);
    margin-bottom: var(--snto-space-3);
    box-shadow: none;
}
.snto-decision-value {
    color: var(--snto-text-primary);
    font-size: 1.45rem;
    font-weight: 700;
    line-height: 1.2;
}
.snto-context-value {
    color: var(--snto-text-primary);
    font-size: 1.05rem;
    font-weight: 600;
    line-height: 1.3;
}
.snto-micro-label {
    color: #68798a;
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.07em;
    text-transform: uppercase;
}
.snto-body-copy {
    color: var(--snto-text-secondary);
    font-size: 0.875rem;
    line-height: 1.5;
}
.snto-evidence-badge {
    display: inline-block;
    border: 1px solid #aebbc8;
    border-radius: 3px;
    color: #33485c;
    font-size: 0.65rem;
    font-weight: 700;
    letter-spacing: 0.07em;
    padding: 2px 6px;
    text-transform: uppercase;
    vertical-align: middle;
}

/* ── FASE 3: TIER (estrategia, neutro) vs ALERTA (táctica, semáforo) ─────── */
/* Chip de TIER: nomenclatura estructural [TIER N], paleta índigo→pizarra,
   deliberadamente NO semafórica (no es riesgo, es prioridad de inversión). */
.snto-tier-chip {
    display: inline-block; font-size: 0.62rem; font-weight: 700;
    letter-spacing: 0.07em; padding: 2px 8px; border-radius: 3px;
    vertical-align: middle; text-transform: uppercase;
}
/* Chip de ALERTA: semáforo táctico (🔴🟡🔵🟢), forma de píldora. */
.snto-status-chip {
    display: inline-block; font-size: 0.62rem; font-weight: 600;
    padding: 2px 8px; border-radius: 11px; vertical-align: middle;
    margin-left: 4px;
}
</style>
"""


def inject_base_styles() -> None:
    """Inject the institutional stylesheet (verbatim from app.py)."""
    st.markdown(_BASE_CSS, unsafe_allow_html=True)


# ── Fecha global de informe ───────────────────────────────────────────────────
REPORT_DATE = "2026-06-12"


# ── Registro de territorios ───────────────────────────────────────────────────
_TERRITORY_CONFIG: dict[str, dict] = {
    "snr": {
        "name":       "Reserva de la Biosfera Sierra del Rincón",
        "short":      "Sierra del Rincón",
        "budget":     100_000,
        "report_date": REPORT_DATE,
        "map_center": (41.130, -3.490, 11),
    },
    "pnsg": {
        "name":       "Parque Nacional Sierra de Guadarrama",
        "short":      "PN Sierra de Guadarrama",
        "budget":     150_000,
        "report_date": REPORT_DATE,
        "map_center": (40.820, -3.960, 10),
    },
    # Alpine Edition — Sierra Nevada. EHS y tendencia derivados de la serie
    # Sentinel-2 real (GEE); atributos socioeconómicos y SCM son proxy (ver
    # src.territorial.alpine_fixtures). Presupuesto regional de mayor escala.
    "sn": {
        "name":       "Parque Nacional de Sierra Nevada",
        "short":      "PN Sierra Nevada",
        "budget":     400_000,
        "report_date": REPORT_DATE,
        "map_center": (37.055, -3.310, 10),
    },
}

_BUILD_FN = {
    "snr":  build_territory,
    "pnsg": build_pnsg_territory,
    "sn":   build_sierra_nevada_territory,
}

# Territorios VISIBLES en el selector de la UI. El PNSG es el territorio
# principal del observatorio; Sierra del Rincón se conserva en el código, los
# datos y los scripts del pipeline (raíz del proyecto), pero ya no se ofrece en
# la vista. Para volver a mostrarlo, añade "snr" a esta lista.
_VISIBLE_TERRITORIES = ["pnsg", "sn"]


# ── Pipeline con caché ────────────────────────────────────────────────────────

@st.cache_data(show_spinner="Calculando inteligencia territorial…")
def load_dashboard(territory_key: str):
    """Return (dashboard, assets, comps, assets_by_id, base_budget, cfg, cal) — cached per territory.

    Fase 2 — inyección satelital: antes de rankear, el EHS satelital real del
    Pipeline A sobreescribe (conservadoramente) el EHS curado donde el satélite
    observa MÁS degradación. Como rank_assets recalcula TPI/tier a partir de
    ehs, el dato real se propaga a TPI, tiers, presupuesto y los 10 KPIs.
    """
    cfg    = _TERRITORY_CONFIG[territory_key]
    raw    = _BUILD_FN[territory_key]()
    raw, cal = enrich_assets_with_satellite(territory_key, raw)
    assets = rank_assets(raw)
    by_id  = {a.asset_id: a for a in assets}
    max_v  = max(a.visitor_capacity_annual for a in assets)
    comps  = [compare_scenarios(a, max_v) for a in assets]
    budget = allocate_tis_budget(comps, by_id, cfg["budget"])
    dash   = compute_executive_dashboard(
        territory_name=cfg["name"],
        report_date=cfg["report_date"],
        assets=assets,
        budget_result=budget,
        comparisons=comps,
    )
    return dash, assets, comps, by_id, budget, cfg, cal
