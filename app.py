"""
SNTO — Smart Natural Tourism Observatory
Executive Destination Intelligence Dashboard  (Phase 7)

Levanta el servidor con:
    streamlit run app.py
"""
from __future__ import annotations

import streamlit as st
from streamlit_autorefresh import st_autorefresh

from src._version import __version__
from src.platform.map_layers import LEGEND_ITEMS
from src.platform.telemetry import record_view, telemetry_enabled
from src.platform.views import ViewMode, get_view, view_modes
from src.socioeconomic.indicators import (
    aggregate_asset_risk,
    compute_svi,
)
from src.socioeconomic.indicators import (
    jobs_at_risk as compute_jobs_at_risk,
)
from src.socioeconomic.loader import load_municipalities, snapshot_exists
from src.ui.asset_detail import render_asset_page
from src.ui.asset_navigation import (
    clear_asset_selection,
    find_asset,
    selected_asset_id,
)
from src.ui.layout import (
    _TERRITORY_CONFIG,
    _VISIBLE_TERRITORIES,
    configure_page,
    inject_base_styles,
    load_dashboard,
)
from src.ui.navigation import (
    layer_tab_labels,
    module_tab_labels,
    navigation_layers,
)
from src.ui.render_widgets import (
    _compute_exec_kpis,
    _render_banner,
    _render_exec_kpis,
    _render_live_alerts,
)
from src.ui.tabs.tab_alpine import render_tab_alpine
from src.ui.tabs.tab_assets import render_tab_assets
from src.ui.tabs.tab_confidence import render_tab_confidence
from src.ui.tabs.tab_config import render_tab_config
from src.ui.tabs.tab_diagnostic import render_tab_diagnostic
from src.ui.tabs.tab_forecast import render_tab_forecast
from src.ui.tabs.tab_kpis import render_tab_kpis
from src.ui.tabs.tab_method import render_tab_method
from src.ui.tabs.tab_portfolio import render_tab_portfolio
from src.ui.tabs.tab_provenance import render_tab_provenance
from src.ui.tabs.tab_reports import render_tab_reports
from src.ui.tabs.tab_simulator import render_tab_simulator
from src.ui.tabs.tab_socioeco import render_tab_socioeco
from src.ui.tabs.tab_timeseries import render_tab_timeseries
from src.ui.tabs.tab_urgent_actions import render_tab_urgent_actions

# ── Configuración de página ───────────────────────────────────────────────────
configure_page()

# ── Estilo institucional ──────────────────────────────────────────────────────
inject_base_styles()


# ── Selector de territorio (primer bloque de barra lateral) ──────────────────
with st.sidebar:
    st.markdown("## 🏔 SNTO")
    st.markdown("**Inteligencia para la decisión  \nen espacios naturales protegidos**")
    st.divider()
    st.markdown("**Espacio protegido activo**")
    if len(_VISIBLE_TERRITORIES) > 1:
        selected_key = st.radio(
            "Territorio activo",
            options=_VISIBLE_TERRITORIES,
            format_func=lambda k: _TERRITORY_CONFIG[k]["short"],
            label_visibility="collapsed",
        )
    else:
        # Un solo territorio visible: mostrarlo como etiqueta, sin selector.
        selected_key = _VISIBLE_TERRITORIES[0]
        st.markdown(
            f'<div class="snto-side-row"><span class="snto-side-icon">🏔</span>'
            f'<span><strong>{_TERRITORY_CONFIG[selected_key]["short"]}</strong></span></div>',
            unsafe_allow_html=True,
        )
    st.divider()
    st.markdown("**Vista / audiencia**")
    _modes = view_modes()
    # Por defecto, vista Auditoría: es la que expone procedencia, fórmulas y límites,
    # la adecuada para revisión metodológica / defensa académica.
    _default_view_idx = _modes.index(ViewMode.TRIBUNAL)
    _view_mode = st.radio(
        "Vista",
        options=_modes,
        format_func=lambda m: f"{get_view(m).icon} {get_view(m).label}",
        index=_default_view_idx,
        label_visibility="collapsed",
        key="view_mode",
    )
    _view = get_view(_view_mode)
    st.caption(_view.audience)
    st.caption(f"Personas agrupadas: {' · '.join(_view.personas)}")
    st.caption(f"🏠 Inicio: {_view.home_path}")
    if _view.shows:
        st.caption(f"🔁 {_view.shows}")
    # F10 Fase 5: telemetría de uso de vistas — local y opt-in (SNTO_TELEMETRY=1).
    # Se registra una vez por CAMBIO de vista en la sesión, no en cada autorefresh,
    # para medir selecciones reales sin inflar el conteo.
    if (
        telemetry_enabled()
        and st.session_state.get("_telemetry_last") != _view.mode.value
    ):
        record_view(_view.mode.value)
        st.session_state["_telemetry_last"] = _view.mode.value
    st.divider()

# ── Cargar datos ──────────────────────────────────────────────────────────────
dashboard, ranked_assets, base_comps, assets_by_id, base_budget, _terr_cfg, calibration = load_dashboard(selected_key)
BUDGET_EUR = _terr_cfg["budget"]

n_red = sum(1 for k in dashboard.kpis if k.status == "RED")
n_amb = sum(1 for k in dashboard.kpis if k.status == "AMBER")
n_ok  = sum(1 for k in dashboard.kpis if k.status in ("GREEN", "BLUE"))

# ── Resto de la barra lateral ─────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        f'<div class="snto-side-row"><span class="snto-side-icon">🏛️</span>'
        f'<span><strong>Territorio</strong><br/>{dashboard.territory_name}</span></div>'
        f'<div class="snto-side-row"><span class="snto-side-icon">📅</span>'
        f'<span><strong>Fecha de informe</strong><br/>{dashboard.report_date}</span></div>'
        f'<div class="snto-side-row"><span class="snto-side-icon">🗂️</span>'
        f'<span><strong>Activos monitorizados</strong><br/>{dashboard.n_assets} '
        f'sendas y enclaves</span></div>',
        unsafe_allow_html=True,
    )
    st.divider()
    st.markdown("**Panel de alertas**")
    if n_red:
        st.markdown(f"🔴 **{n_red}** indicador(es) crítico(s)")
    if n_amb:
        st.markdown(f"🟡 **{n_amb}** indicador(es) en atención")
    if n_ok:
        st.markdown(f"🟢 **{n_ok}** indicador(es) normal / óptimo")
    st.divider()
    # ── Map legend ────────────────────────────────────────────────────────────
    st.markdown("**Leyenda del mapa**")
    for item in LEGEND_ITEMS:
        st.markdown(
            f'<span class="legend-chip" style="background:{item["hex"]}"></span>'
            f'<small>{item["label"]}</small>',
            unsafe_allow_html=True,
        )
    st.divider()
    st.caption(f"SNTO v{__version__} · Sentinel-2 real + INE/ALMUDENA + calibración")
    st.caption(f"Territorio principal: {_terr_cfg['short']} (Madrid · Segovia)")


# ── TAREA 1: Banner dinámico con contextual badging ──────────────────────────
_render_banner(selected_key, _terr_cfg, dashboard, n_red, n_amb)

# ── F7: Banner de vista / audiencia ───────────────────────────────────────────
st.markdown(
    f'<div style="padding:7px 14px;border-radius:6px;margin:4px 0 2px;'
    f'background:#eef3f8;border-left:4px solid #33485c;font-size:0.82rem;color:#33485c">'
    f'{_view.icon} <b>{_view.label}</b> — {_view.banner} '
    f'<br><span style="font-size:0.76rem"><b>Inicio:</b> {_view.home_path} · '
    f'<b>Perfiles:</b> {" · ".join(_view.personas)}</span> '
    f'<span style="color:#7a8899">Énfasis: {_view.emphasis}</span></div>',
    unsafe_allow_html=True,
)

# ── Autorefresh: recarga la app cada 60 s (simula polling de datos en vivo) ───
_refresh_count = st_autorefresh(interval=60_000, limit=None, key=f"live_{selected_key}")

# ── Barra de alertas en vivo ──────────────────────────────────────────────────
_alerts_placeholder = st.empty()
with _alerts_placeholder.container():
    _render_live_alerts(ranked_assets, _refresh_count)

# ── F9: Capa socioeconómica real (ALMUDENA / INE) ────────────────────────────
# Solo el PNSG tiene snapshot socioeconómico curado. Para otros territorios el
# overlay es None y el dashboard usa el modelo proxy heredado.
_socio = None
if selected_key == "pnsg" and snapshot_exists():
    _socio_snapshot = load_municipalities()
    _socio_risk = aggregate_asset_risk(
        ranked_assets, name_to_ine=_socio_snapshot.name_to_ine()
    )
    if _socio_risk:  # hay activos que cruzan con municipios del PNSG
        _socio = {
            "snapshot": _socio_snapshot,
            "risk": _socio_risk,
            "svi": compute_svi(_socio_snapshot, _socio_risk),
            "jobs": compute_jobs_at_risk(_socio_snapshot, _socio_risk),
        }

# ── Fase 6.5: el activo como página central ──────────────────────────────────
# Con la opción de navegación 2.1-A no hay URL multipágina. El id seleccionado
# en session_state actúa como ruta y sustituye la suite de módulos hasta volver.
_asset_route_id = selected_asset_id(st.session_state)
_selected_asset = find_asset(ranked_assets, _asset_route_id)
if _asset_route_id is not None and _selected_asset is None:
    clear_asset_selection(st.session_state)
    st.warning(
        "La ficha seleccionada ya no pertenece al territorio activo. "
        "Se ha vuelto a la arquitectura general."
    )
elif _selected_asset is not None:
    _comparison_by_asset = {item.asset_id: item for item in base_comps}
    render_asset_page(
        _selected_asset,
        _comparison_by_asset.get(_selected_asset.asset_id),
        calibration.get(_selected_asset.asset_id),
    )
    st.stop()

# ── TAREA 2: Tira de 4 KPIs ejecutivos ───────────────────────────────────────
# Fase 6.6: el encabezado de decisión pertenece al home Gestor. Técnica y
# Auditoría abren directamente su capa sin cifras ejecutivas por delante.
if _view.home_layer == "decidir":
    _exec_kpis = _compute_exec_kpis(ranked_assets, base_budget, assets_by_id)
    if _socio:  # KPI "Empleos locales en riesgo" respaldado por datos reales
        _exec_kpis["jobs_risk"] = _socio["jobs"].total
    _render_exec_kpis(_exec_kpis, selected_key)
    if _socio:
        st.caption(
            "ℹ️ *Empleos locales en riesgo* calculado con datos reales "
            "**ALMUDENA / INE** (afiliados a hostelería del municipio × "
            "exposición ambiental de sus activos), no con el proxy de "
            "visitantes. Detalle en **Decidir → Impacto socioeconómico**."
        )

st.divider()

# FASE 1: el mapa espacial "above the fold" se ha retirado para liberar espacio
# cognitivo. El mapa vive en «Diagnosticar → Diagnóstico espacial» y las fichas
# de activos críticos en «Decidir → Panorama ejecutivo».

# ── TAREA 4: Suite de módulos analíticos ──────────────────────────────────────
st.markdown(
    '<div style="font-size:0.70rem;font-weight:600;color:#7a8899;'
    'text-transform:uppercase;letter-spacing:0.07em;margin-bottom:6px">'
    'Arquitectura de decisión y evidencia</div>',
    unsafe_allow_html=True,
)
# Opciones 2.1-A + 2.2-A: se conservan las cuatro capas en st.tabs(), pero la
# capa home de la audiencia se coloca primero y queda seleccionada al cargar.
_layer_order = navigation_layers(_view.home_layer)
_layer_tabs = st.tabs(layer_tab_labels(_view.home_layer))
for _layer, _layer_container in zip(_layer_order, _layer_tabs, strict=True):
    with _layer_container:
        st.caption(f"**{_layer.label}** · {_layer.question}")
        _module_tabs = st.tabs(module_tab_labels(_layer.key))
        for _module, _module_container in zip(
            _layer.modules, _module_tabs, strict=True
        ):
            with _module_container:
                if _module.key == "panorama":
                    render_tab_kpis(
                        dashboard, ranked_assets, base_comps, calibration, _view
                    )
                elif _module.key == "urgent_actions":
                    render_tab_urgent_actions()
                elif _module.key == "budget":
                    render_tab_simulator(
                        base_comps,
                        assets_by_id,
                        base_budget,
                        ranked_assets,
                        _view,
                    )
                elif _module.key == "socioeconomic":
                    render_tab_socioeco(
                        _socio, base_comps, ranked_assets, base_budget, _view
                    )
                elif _module.key == "spatial":
                    render_tab_diagnostic(
                        selected_key,
                        _terr_cfg,
                        ranked_assets,
                        _view,
                        dashboard,
                        base_comps,
                    )
                elif _module.key == "alpine":
                    render_tab_alpine(
                        ranked_assets,
                        base_comps,
                        assets_by_id,
                        _view,
                    )
                elif _module.key == "assets":
                    render_tab_assets(calibration, ranked_assets, _view)
                elif _module.key == "pressure":
                    render_tab_portfolio(ranked_assets, base_comps, _view)
                elif _module.key == "forecast":
                    render_tab_forecast(ranked_assets, _view)
                elif _module.key == "satellite":
                    render_tab_timeseries(ranked_assets, _view)
                elif _module.key == "confidence":
                    render_tab_confidence(ranked_assets, _view)
                elif _module.key == "provenance":
                    render_tab_provenance(
                        ranked_assets,
                        calibration,
                        selected_key,
                        dashboard.report_date,
                        _view,
                    )
                elif _module.key == "methodology":
                    render_tab_method(_view, ranked_assets)
                elif _module.key == "reports":
                    render_tab_reports(
                        ranked_assets,
                        selected_key,
                        dashboard.territory_name,
                        dashboard.report_date,
                        _view,
                    )
                elif _module.key == "configuration":
                    render_tab_config(_view)
                else:  # pragma: no cover - guarded by navigation contract tests
                    raise ValueError(f"Unknown navigation module: {_module.key}")


# ── Pie de página ─────────────────────────────────────────────────────────────
st.divider()
st.markdown(
    f'<div style="font-size:0.72rem;color:#9aa4af;text-align:center;padding:4px 0 2px;">'
    f'Smart Natural Tourism Observatory (SNTO) v{__version__} · '
    f'Capa de inteligencia para la decisión en espacios naturales protegidos · '
    f'{dashboard.territory_name} · Madrid (España) · '
    f'Sentinel-2 real (PNSG) + capa socioeconómica INE/ALMUDENA + activos de calibración'
    f'</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div style="font-size:0.66rem;color:#9aa4af;text-align:center;padding:0 0 8px;">'
    'Fuentes de datos: Contiene datos Copernicus Sentinel-2 modificados (ESA) · '
    'cartografía © OpenStreetMap (ODbL) y OAPN (Red de Parques Nacionales) · '
    'INE (Padrón, EOATR) · ALMUDENA, Comunidad de Madrid · '
    'Procedencia y licencias en «Gobernar → Metodología y auditoría».'
    '</div>',
    unsafe_allow_html=True,
)
