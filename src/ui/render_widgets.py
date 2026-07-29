"""
Streamlit render widgets for the SNTO dashboard shell — Fase 4, paso 2.

The composite render functions that paint the top-of-page hero: the live-alert
strip, the dynamic territory/view banners, the 4-KPI executive strip, the quick
alert cards, the per-KPI drill-down and the KPI card. Extracted verbatim from
app.py (issue #27, modularización).

Unlike the pure primitives in ``render_helpers`` these call ``st.*`` and own
their presentation constants (_BANNER_CFG, _EXEC_DELTAS, _KPI_DRILLDOWN, …), but
they still take every data input as an explicit parameter — no reads of
app-assembly globals or session state — so they move cleanly out of the shell.
Names keep their original ``_`` prefix so app.py call sites are unchanged.
"""
from __future__ import annotations

import datetime

import streamlit as st

from src.ui.asset_navigation import select_asset
from src.ui.kpi_sections import kpi_evidence_label
from src.ui.render_helpers import (
    _ALERT_META,
    _ALERT_SEVERITY,
    _BG,
    _COLOR,
    _EMOJI,
    _alert_accent,
    _alert_chip,
    _ehs_color,
    _tier_chip,
)


# ── Renderizador de alertas en vivo ──────────────────────────────────────────
def _render_live_alerts(assets: list, refresh_count: int) -> None:
    active = sorted(
        [a for a in assets if a.alert_level in _ALERT_META],
        key=lambda a: _ALERT_SEVERITY[a.alert_level],
    )
    if not active:
        st.success("✅ Sin alertas activas en este territorio.", icon="🌿")
        return

    chips = ""
    for a in active[:8]:
        icon, label, bg, border = _ALERT_META[a.alert_level]
        name = a.name.split("—")[0].strip()[:30]
        chips += (
            f'<div class="snto-alert-chip" style="background:{bg};border-color:{border};">'
            f'  <span style="font-size:15px;line-height:1.3">{icon}</span>'
            f'  <div>'
            f'    <div class="snto-alert-name">{name}</div>'
            f'    <div class="snto-alert-sub">EHS {a.ehs:.0f} · {a.region} · {label}</div>'
            f'  </div>'
            f'</div>'
        )

    ts = datetime.datetime.now().strftime("%H:%M:%S")
    st.markdown(
        f'<div class="snto-alert-bar">'
        f'  <span class="snto-alert-title">'
        f'    <span class="snto-pulse"></span>'
        f'    {len(active)} alerta{"s" if len(active) != 1 else ""} activa{"s" if len(active) != 1 else ""}'
        f'  </span>'
        f'  <span class="snto-refresh-ts">Actualizado: {ts} · ciclo #{refresh_count}</span>'
        f'</div>'
        f'<div style="display:flex;gap:8px;flex-wrap:wrap;padding-bottom:4px;">{chips}</div>',
        unsafe_allow_html=True,
    )


# ── TAREA 1: Configuración de banners dinámicos ──────────────────────────────
_BANNER_CFG: dict[str, dict] = {
    "snr": {
        "bg":          "#0d2818",
        "main_badge":  ("🌿", "Reserva de la Biosfera · UNESCO MAB", "#0F6E56", "#9FE1CB"),
        "extra_badge": None,
        "text_color":  "#E1F5EE",
        "sub_color":   "#5DCAA5",
    },
    "pnsg": {
        "bg":          "#0d1e3a",
        "main_badge":  ("⛰️", "Parque Nacional · Red de Parques Nacionales", "#185FA5", "#B5D4F4"),
        "extra_badge": ("⚠️", "Alta presión antrópica", "#EF9F27", "#412402"),
        "text_color":  "#E6F1FB",
        "sub_color":   "#85B7EB",
    },
    "sn": {
        "bg":          "#0d1e3a",
        "main_badge":  (
            "🏔", "Parque Nacional · Alta montaña mediterránea", "#185FA5", "#B5D4F4"
        ),
        "extra_badge": (
            "❄️", "Doble estacionalidad · nieve y borreguiles", "#5DA9E8", "#08243E"
        ),
        "text_color":  "#E6F1FB",
        "sub_color":   "#85B7EB",
    },
}

# Simulated cycle-over-cycle deltas — directionally realistic for demo data
_EXEC_DELTAS: dict[str, dict] = {
    "snr":  {"ehs": -3.1, "tis": -1.8, "deuda": 12_000,  "jobs": 0.6},
    "pnsg": {"ehs": -5.3, "tis": -4.1, "deuda": 68_000,  "jobs": 2.1},
    "sn":   {"ehs": -4.4, "tis": -3.0, "deuda": 45_000,  "jobs": 1.4},
}


def _render_banner(key: str, cfg: dict, dashboard, n_red: int, n_amb: int) -> None:
    bc = _BANNER_CFG[key]
    icon_m, text_m, bg_m, fg_m = bc["main_badge"]
    main_badge = (
        f'<span class="snto-banner-badge" style="background:{bg_m};color:{fg_m};">'
        f'{icon_m} {text_m}</span>'
    )
    extra_badge = ""
    if bc["extra_badge"]:
        icon_e, text_e, bg_e, fg_e = bc["extra_badge"]
        extra_badge = (
            f'<span class="snto-banner-badge" style="background:{bg_e};color:{fg_e};">'
            f'{icon_e} {text_e}</span>'
        )
    if n_red >= 1:
        status_html = (
            f'<span style="color:#ff6b6b;font-size:0.77rem;">'
            f'⚠ {n_red} alerta(s) crítica(s)</span>'
        )
    elif n_amb >= 1:
        status_html = (
            f'<span style="color:#ffd97d;font-size:0.77rem;">'
            f'◉ {n_amb} indicador(es) en atención</span>'
        )
    else:
        status_html = (
            '<span style="color:#6ee7b7;font-size:0.77rem;">✓ Sin alertas críticas</span>'
        )
    st.markdown(
        f'<div class="snto-banner" style="background:{bc["bg"]};">'
        f'<div style="display:flex;align-items:center;justify-content:space-between;'
        f'flex-wrap:wrap;gap:6px;">'
        f'<div>{main_badge}{extra_badge}</div>'
        f'<div>{status_html}</div>'
        f'</div>'
        f'<div class="snto-banner-title" style="color:{bc["text_color"]};">'
        f'{dashboard.territory_name}</div>'
        f'<div class="snto-banner-sub" style="color:{bc["sub_color"]};">'
        f'Plataforma SNTO · Informe estratégico · {dashboard.report_date} · '
        f'{dashboard.n_assets} activos monitorizados · '
        f'Presupuesto base: €{cfg["budget"]:,}'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ── TAREA 2: Executive KPI strip ─────────────────────────────────────────────
def _compute_exec_kpis(ranked_assets, base_budget, assets_by_id) -> dict:
    ehs_medio = sum(a.ehs for a in ranked_assets) / len(ranked_assets)
    tis_portfolio = base_budget.portfolio_tis
    _base_funded = {it.asset_id for it in base_budget.funded_items}

    deuda = sum(
        item.cost_eur for item in base_budget.deferred_items
        if item.asset_id in assets_by_id
        and (assets_by_id[item.asset_id].tier or 0) <= 2
    )
    for item in base_budget.funded_items:
        a = assets_by_id.get(item.asset_id)
        if a and (a.tier or 0) == 1:
            deuda += item.cost_eur * 0.15

    _spend = 22.50
    _jobs_per = 2_500
    _risk = {1: 1.00, 2: 0.40}
    total_jobs_risk = 0.0
    for a in ranked_assets:
        t = a.tier or 0
        if t not in _risk:
            continue
        rf = _risk[t] if a.asset_id not in _base_funded else _risk[t] * 0.15
        total_jobs_risk += (a.visitor_capacity_annual / _jobs_per) * rf

    return {
        "ehs_medio":    ehs_medio,
        "tis_portfolio": tis_portfolio,
        "deuda_eur":    deuda,
        "jobs_risk":    total_jobs_risk,
    }


def _render_exec_kpis(kpis_data: dict, selected_key: str) -> None:
    ehs  = kpis_data["ehs_medio"]
    tis  = kpis_data["tis_portfolio"]
    deuda = kpis_data["deuda_eur"]
    jobs  = kpis_data["jobs_risk"]
    d = _EXEC_DELTAS.get(selected_key, {"ehs": -2.0, "tis": -1.0, "deuda": 5_000, "jobs": 0.2})

    def _delta_html(val: float, *, positive_is_bad: bool) -> str:
        is_bad = (val > 0) if positive_is_bad else (val < 0)
        color  = "#A32D2D" if is_bad else "#3B6D11"
        arrow  = "▲" if val > 0 else "▼"
        sign   = "+" if val > 0 else ""
        return (
            f'<span style="color:{color}">'
            f'{arrow} {sign}{val:g} vs ciclo anterior</span>'
        )

    ehs_color = "#0F6E56" if ehs >= 65 else ("#EF9F27" if ehs >= 50 else "#A32D2D")
    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.markdown(
            f'<div class="snto-decision-card exec-kpi" '
            f'style="border-top-color:{ehs_color};">'
            f'<div class="exec-kpi-label">Salud ecológica media</div>'
            f'<div class="exec-kpi-value" style="color:{ehs_color}">'
            f'{ehs:.1f}<span style="font-size:0.85rem;color:#9aa4af">/100</span></div>'
            f'<div class="exec-kpi-delta">{_delta_html(d["ehs"], positive_is_bad=False)}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f'<div class="snto-decision-card exec-kpi" '
            f'style="border-top-color:#185FA5;">'
            f'<div class="exec-kpi-label">TIS portfolio</div>'
            f'<div class="exec-kpi-value" style="color:#185FA5">{tis:.1f}</div>'
            f'<div class="exec-kpi-delta">{_delta_html(d["tis"], positive_is_bad=False)}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            f'<div class="snto-decision-card exec-kpi" '
            f'style="border-top-color:#854F0B;">'
            f'<div class="exec-kpi-label">Deuda ecológica acumulada</div>'
            f'<div class="exec-kpi-value" style="color:#854F0B">€{deuda:,.0f}</div>'
            f'<div class="exec-kpi-delta">{_delta_html(d["deuda"], positive_is_bad=True)}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with c4:
        st.markdown(
            f'<div class="snto-decision-card exec-kpi" '
            f'style="border-top-color:#A32D2D;">'
            f'<div class="exec-kpi-label">Empleos locales en riesgo</div>'
            f'<div class="exec-kpi-value" style="color:#A32D2D">{jobs:.1f}</div>'
            f'<div class="exec-kpi-delta">{_delta_html(d["jobs"], positive_is_bad=True)}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )


# ── TAREA 3: Fichas de alerta rápida (map hero right panel) ─────────────────
def _render_fichas_rapidas(ranked_assets: list) -> None:
    top3 = [a for a in ranked_assets if (a.tier or 5) <= 2][:3]
    if not top3:
        top3 = ranked_assets[:3]

    st.markdown(
        '<div class="snto-panel-title">Priorización de Activos Turísticos Críticos</div>',
        unsafe_allow_html=True,
    )
    for a in top3:
        alert_accent = _alert_accent(a.alert_level)
        ehs_c = _ehs_color(a.ehs)
        name_short = a.name.split("—")[0].strip()
        ehs_w = max(2, int(a.ehs))
        vis   = f"{a.visitor_capacity_annual:,}"
        st.markdown(
            f'<div class="snto-asset-card snto-ficha" '
            f'style="border-left-color:{alert_accent};">'
            f'<span class="snto-ficha-ehs" style="background:{ehs_c}1a;color:{ehs_c};">'
            f'EHS {a.ehs:.0f}</span>'
            f'<div class="snto-ficha-name">{name_short}</div>'
            f'<div class="snto-ficha-meta">{a.region} · {vis} visit./año</div>'
            f'<div style="margin-top:5px">{_tier_chip(a.tier)}{_alert_chip(a.alert_level)}</div>'
            f'<div class="snto-ehs-bar">'
            f'<div class="snto-ehs-fill" style="width:{ehs_w}%;background:{ehs_c};"></div>'
            f'</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        st.button(
            "Abrir ficha",
            key=f"asset-page-critical-{a.asset_id}",
            on_click=select_asset,
            args=(st.session_state, a.asset_id),
        )
    # Visitor count summary below fichas
    _visitors_t12 = sum(
        a.visitor_capacity_annual for a in ranked_assets if (a.tier or 5) <= 2
    )
    st.markdown(
        f'<div style="margin-top:6px;padding:8px 10px;background:#fff8f0;'
        f'border-radius:6px;border-left:3px solid #EF9F27;">'
        f'<div style="font-size:0.65rem;color:#854F0B;text-transform:uppercase;'
        f'letter-spacing:0.06em">Capacidad de carga antrópica comprometida (Tier 1+2)</div>'
        f'<div style="font-size:1.25rem;font-weight:700;color:#A32D2D">'
        f'{_visitors_t12:,}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ── TAREA 2: Drill-down por KPI ──────────────────────────────────────────────
# Mapa nº de KPI → filtro sobre los activos clasificados. El motor de
# dashboard.py no se modifica: cada filtro replica el criterio documentado
# en technical_basis del propio KPI.
_KPI_DRILLDOWN = {
    2:  lambda assets: sorted(
            [a for a in assets if a.tier in (1, 2)],
            key=lambda a: (a.tier, -(a.tpi or 0))),
    3:  lambda assets: sorted(
            [a for a in assets if a.tier in (1, 2)],
            key=lambda a: -a.visitor_capacity_annual),
    4:  "backlog",   # orden por inversión de mitigación descendente (deuda ecológica)
    7:  lambda assets: sorted(
            [a for a in assets
             if a.scm_classification == "LOCALIZED_IMPACT" and a.tier in (1, 2)],
            key=lambda a: -(a.tpi or 0)),
    9:  lambda assets: sorted(
            [a for a in assets if a.trend_direction == "decreasing"],
            key=lambda a: a.ehs),
    10: lambda assets: sorted(
            [a for a in assets if a.dcs < 55],
            key=lambda a: a.dcs),
}

_KPI_DRILLDOWN_CAPTION = {
    2:  "Sendas y enclaves que requieren intervención financiera inmediata o preventiva, ordenados por prioridad territorial (TPI).",
    3:  "Capacidad de carga antrópica comprometida: activos Tier 1-2 ordenados por presión de visitantes.",
    4:  "Deuda ecológica por activo: la inversión de mitigación pendiente justifica administrativamente la priorización del presupuesto público.",
    7:  "Activos con degradación causada por presión antrópica confirmada (clasificación causal SCM: impacto localizado).",
    9:  "Activos en trayectoria de degradación activa (tendencia Mann-Kendall decreciente).",
    10: "Activos sin evidencia suficiente (DCS < 55): requieren refuerzo de monitorización antes de comprometer inversión de capital.",
}

_ALERT_LABEL_ES = {
    "CRITICAL_INTERVENTION": "🔴 Intervención crítica",
    "URGENT_MONITORING":     "🟡 Monitorización urgente",
    "PREVENTIVE_ACTION":     "🔵 Acción preventiva",
    "NORMAL":                "🟢 Normal",
}


def _render_kpi_drilldown(kpi, ranked_assets: list, cost_by_id: dict) -> None:
    """Tabla de drill-down con los activos que componen el indicador."""
    import pandas as pd

    spec = _KPI_DRILLDOWN.get(kpi.number)
    if spec is None:
        return

    if spec == "backlog":
        rows_src = sorted(
            [a for a in ranked_assets if a.tier in (1, 2)],
            key=lambda a: -cost_by_id.get(a.asset_id, 0),
        )
    else:
        rows_src = spec(ranked_assets)

    if not rows_src:
        st.caption("Sin activos afectados por este indicador en el ciclo actual.")
        return

    st.markdown("**Desglose de activos afectados**")
    st.caption(_KPI_DRILLDOWN_CAPTION.get(kpi.number, ""))
    df = pd.DataFrame([
        {
            "Senda / Activo":   a.name,
            "Municipio":        a.region,
            "EHS":              round(a.ehs, 0),
            "Estado de alerta": _ALERT_LABEL_ES.get(a.alert_level, a.alert_level),
            "Presión (visit./año)": a.visitor_capacity_annual,
            "Inversión de mitigación (€)": cost_by_id.get(a.asset_id, 0),
        }
        for a in rows_src
    ])
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "EHS": st.column_config.ProgressColumn(
                "EHS", min_value=0, max_value=100, format="%.0f"),
            "Presión (visit./año)": st.column_config.NumberColumn(format="%d"),
            "Inversión de mitigación (€)": st.column_config.NumberColumn(format="€%d"),
        },
    )


# ── Renderizador de tarjeta KPI ───────────────────────────────────────────────
def render_kpi_card(
    kpi,
    ranked_assets: list | None = None,
    cost_by_id: dict | None = None,
    *,
    context: bool = False,
) -> None:
    color = _COLOR[kpi.status]
    bg    = _BG[kpi.status]
    emoji = _EMOJI[kpi.status]
    evidence = kpi_evidence_label(kpi.number)
    card_class = "snto-evidence-card" if context else "snto-decision-card kpi-card"
    card_style = "" if context else f' style="border-top-color:{color};"'
    value_class = "snto-context-value" if context else "snto-decision-value"
    st.markdown(
        f"""<div class="{card_class}"{card_style}>
  <div class="kpi-meta">KPI {kpi.number} · <span class="snto-evidence-badge">{evidence}</span></div>
  <div class="kpi-name">{kpi.name}</div>
  <div class="{value_class}">{kpi.value}</div>
  <span class="kpi-badge" style="color:{color};background:{bg};">{emoji}&thinsp;{kpi.status_label}</span>
</div>""",
        unsafe_allow_html=True,
    )
    has_drilldown = kpi.number in _KPI_DRILLDOWN and ranked_assets is not None
    label = ("Interpretación, acción recomendada y desglose de activos"
             if has_drilldown else "Interpretación y acción recomendada")
    with st.expander(label):
        st.markdown(f"**¿Qué significa?** {kpi.what_it_means}")
        st.markdown(f"**Acción recomendada:** _{kpi.recommended_action}_")
        st.caption(f"Base técnica SNTO: {kpi.technical_basis}")
        if has_drilldown:
            st.divider()
            _render_kpi_drilldown(kpi, ranked_assets, cost_by_id or {})


def render_kpi_grid(
    kpis: list,
    ranked_assets: list,
    cost_by_id: dict,
    *,
    columns: int,
    context: bool = False,
) -> None:
    """Render a stable KPI subset in semantic decision/evidence cards."""
    for row_start in range(0, len(kpis), columns):
        row_kpis = kpis[row_start : row_start + columns]
        row_columns = st.columns(columns)
        for index, kpi in enumerate(row_kpis):
            with row_columns[index]:
                render_kpi_card(
                    kpi,
                    ranked_assets,
                    cost_by_id,
                    context=context,
                )
        st.write("")
