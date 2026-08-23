"""
Observatorio Alpino — Sierra Nevada (SNTO Alpine Edition).

Superficie Streamlit del módulo alpino. Toda la lógica de figuras y capas vive
en ``src/platform/alpine_dashboard.py`` (sin Streamlit, testeable headless);
aquí sólo se compone la vista, siguiendo el patrón de ``tab_simulator.py``.

Estructura:
  1. Conmutador de temporada (Invierno / Verano).
  2. Mapa PyDeck WebGL con gradiente estacional.
  3. Simulador presupuestario What-If (50.000 € – 1.000.000 €).
  4. Matriz de cartera TPI con TIER I–IV y distintivos de alerta.
  5. Contexto municipal (INE andaluz real, issue #10) + presión de
     visitantes real (OAPN).
"""
from __future__ import annotations

import streamlit as st

from src.features.alpine_spectral import AlpineSeason
from src.intervention import BudgetScenarioAssumptions, build_budget_envelopes
from src.platform import methodology as method
from src.platform.alpine_dashboard import (
    alert_badge_counts,
    build_alpine_deck,
    build_alpine_matrix,
    season_view,
)
from src.socioeconomic.alpine_indicators import load_sierra_nevada_indicators
from src.socioeconomic.alpine_mapping import build_municipal_context

# El presupuesto regional anual se mueve en un rango mucho mayor que el del
# simulador PNSG (20K–300K): Sierra Nevada combina parque nacional y estación
# de esquí, con programas de la Junta de Andalucía de otro orden de magnitud.
ALPINE_BUDGET_MIN_EUR: int = 50_000
ALPINE_BUDGET_MAX_EUR: int = 1_000_000
ALPINE_BUDGET_DEFAULT_EUR: int = 250_000
ALPINE_BUDGET_STEP_EUR: int = 50_000


def render_tab_alpine(
    ranked_assets,
    base_comps,
    assets_by_id,
    _view,
    slope_by_asset: dict[str, float] | None = None,
    ndsi_by_asset: dict[str, float] | None = None,
    real_geoms: dict[str, list[dict]] | None = None,
) -> None:
    """Renderiza el observatorio alpino de Sierra Nevada.

    Args:
        ranked_assets: activos territoriales rankeados (tier y tpi asignados).
        base_comps: comparaciones de escenarios de intervención.
        assets_by_id: índice de activos por identificador.
        _view: perfil de audiencia activo (divulgación por capas).
        slope_by_asset: pendiente media por activo (°), colorea el mapa estival.
        ndsi_by_asset: NDSI medio por activo, colorea el mapa invernal.
        real_geoms: trazas cartográficas reales OAPN por activo; el mapa las
            dibuja en lugar de la posición aproximada por centroide.
    """
    st.subheader("Observatorio Alpino — Sierra Nevada")

    if not ranked_assets:
        st.info(
            "No hay activos cargados para Sierra Nevada. Ejecuta el pipeline "
            "territorial antes de usar este módulo."
        )
        return

    # ── 1. Conmutador de temporada ────────────────────────────────────────────
    season = _season_switcher(_view)
    view = season_view(season)

    st.caption(f"**{view.label}** · {view.question}")

    # ── 2. Mapa PyDeck ────────────────────────────────────────────────────────
    st.markdown(f"##### Mapa territorial · {view.legend_caption}")
    try:
        deck = build_alpine_deck(
            ranked_assets,
            season,
            real_geoms=real_geoms,
            slope_by_asset=slope_by_asset,
            ndsi_by_asset=ndsi_by_asset,
        )
        st.pydeck_chart(deck, use_container_width=True, height=540)
    except ImportError:
        st.error(
            "**pydeck no instalado.** Ejecuta `pip install pydeck` para "
            "habilitar el mapa WebGL.",
            icon="⚠️",
        )

    if season is AlpineSeason.WINTER and not ndsi_by_asset:
        st.caption(
            "Sin NDSI cargado: las sendas conservan el color de su tier. "
            "Ejecuta `etl_raster_processor.py` sobre una ventana invernal para "
            "generar `clean_S2_NDSI.tif`."
        )
    elif season is AlpineSeason.SUMMER and not slope_by_asset:
        st.caption(
            "Sin pendientes calculadas: las sendas conservan el color de su "
            "tier. Ejecuta `etl_raster_intersection.py` con "
            "`SNTO_TERRITORY=sierra_nevada`."
        )

    st.divider()

    # ── 3. Simulador presupuestario What-If ───────────────────────────────────
    _render_budget_simulator(base_comps, assets_by_id)

    st.divider()

    # ── 4. Matriz de cartera TPI ──────────────────────────────────────────────
    _render_portfolio_matrix(ranked_assets)

    st.divider()

    # ── 5. Contexto municipal ─────────────────────────────────────────────────
    _render_municipal_context(ranked_assets)


def _season_switcher(_view) -> AlpineSeason:
    """Conmutador Invierno/Verano.

    La clave de estado incluye el modo de vista para que cada audiencia recuerde
    su propia selección, igual que el conmutador de mapa de ``tab_diagnostic``.
    """
    options = (AlpineSeason.WINTER, AlpineSeason.SUMMER)
    return st.radio(
        "Temporada",
        options=options,
        format_func=lambda s: season_view(s).label,
        horizontal=True,
        key=f"alpine_season_{_view.mode.value}",
    )


def _render_budget_simulator(base_comps, assets_by_id) -> None:
    """Simulador What-If de presupuesto regional anual."""
    st.markdown("##### Simulador presupuestario What-If")
    st.markdown(
        method.scenario_badge(
            "ESCENARIO SIMULADO",
            "reasignación modelada por TIS con verificación DCS",
        ),
        unsafe_allow_html=True,
    )

    if not base_comps:
        st.info(
            "No hay comparaciones de escenarios disponibles; el simulador "
            "necesita el motor de intervención ejecutado."
        )
        return

    budget = st.slider(
        "Asignación presupuestaria regional anual (€)",
        min_value=ALPINE_BUDGET_MIN_EUR,
        max_value=ALPINE_BUDGET_MAX_EUR,
        value=ALPINE_BUDGET_DEFAULT_EUR,
        step=ALPINE_BUDGET_STEP_EUR,
        format="€%d",
        key="alpine_budget_eur",
    )

    envelopes = build_budget_envelopes(
        base_comps,
        assets_by_id,
        budget,
        BudgetScenarioAssumptions(),
    )

    cols = st.columns(len(envelopes))
    for col, envelope in zip(cols, envelopes, strict=True):
        with col:
            st.metric(
                envelope.label,
                f"{envelope.funded_count} sendas",
                help=(
                    f"Presupuesto {envelope.budget_eur:,.0f} € · "
                    f"asignado {envelope.result.total_allocated_eur:,.0f} € · "
                    f"remanente {envelope.result.remaining_eur:,.0f} €"
                ),
            )

    annual = next(
        (e for e in envelopes if e.code == "annual"),
        envelopes[0] if envelopes else None,
    )
    if annual is not None:
        st.caption(
            f"Plan anual a {annual.budget_eur:,.0f} €: "
            f"{annual.funded_count} sendas financiadas, "
            f"{len(annual.result.deferred_items)} aplazadas. "
            "La priorización es por TIS y respeta la puerta de evidencia (DCS)."
        )


def _render_portfolio_matrix(ranked_assets) -> None:
    """Matriz de cartera TPI de 4 cuadrantes con distintivos de alerta."""
    st.markdown("##### Matriz de cartera TPI")

    badges = alert_badge_counts(ranked_assets)
    if badges["critical"] or badges["urgent"]:
        st.markdown(
            f"🔴 **{badges['critical']}** en intervención crítica &nbsp;·&nbsp; "
            f"🟠 **{badges['urgent']}** en seguimiento urgente"
        )

    st.plotly_chart(
        build_alpine_matrix(
            ranked_assets,
            title="Cartera Sierra Nevada — Presión turística vs riesgo ecológico",
        ),
        use_container_width=True,
    )
    st.caption(
        "Eje X: presión turística (volumen anual normalizado). "
        "Eje Y: riesgo ecológico (100 − EHS). "
        "El TIER es prioridad de inversión, no gravedad táctica."
    )


def _render_municipal_context(ranked_assets) -> None:
    """Cobertura municipal andaluza real + presión de visitantes real (OAPN)."""
    st.markdown("##### Contexto municipal")
    st.caption(
        "Sierra Nevada no tiene datos ALMUDENA (solo cubre la Comunidad de "
        "Madrid). Esta sección usa únicamente fuentes propias de Andalucía: "
        "el callejero municipal oficial del INE y la encuesta de visitantes "
        "de OAPN — nunca cifras del PNSG/Madrid."
    )

    ctx = build_municipal_context(ranked_assets)

    m_col1, m_col2, m_col3 = st.columns(3)
    with m_col1:
        st.metric(
            "Activos con municipio andaluz real (INE)",
            f"{ctx.n_resolved}/{ctx.n_assets}",
        )
    with m_col2:
        st.metric(
            "Municipios reales representados",
            f"{ctx.n_municipios}",
            help=f"Provincias: {', '.join(ctx.provinces) or '—'}",
        )
    with m_col3:
        st.metric(
            f"Visitantes P.N. Sierra Nevada · {ctx.oapn_report_year} (real, OAPN)",
            f"{ctx.oapn_sierra_nevada_visitors_estimate:,.0f}".replace(",", "."),
            help=(
                f"{ctx.oapn_sierra_nevada_share_pct:.2f}% de los "
                f"{ctx.oapn_red_total_visitors:,.0f}".replace(",", ".")
                + " visitantes de toda la Red de Parques Nacionales en "
                f"{ctx.oapn_report_year} (Encuesta SIR, OAPN). Cifra del "
                "parque completo — no desagregable por sendero ni municipio."
            ),
        )

    if ctx.unresolved_regions:
        with st.expander(
            f"ℹ️ {len(ctx.unresolved_regions)} región(es) sin municipio real "
            "vinculado",
            expanded=False,
        ):
            st.markdown(
                "No son municipios andaluces (el macizo por defecto, refugios "
                "o parajes) o su topónimo aún no está en el callejero:\n\n"
                + "\n".join(f"- {r}" for r in ctx.unresolved_regions)
            )

    _render_municipal_indicators_table(ctx.municipios)

    st.caption(
        "Fuentes: INE — Relación de municipios y sus códigos (Granada/Almería). "
        "OAPN — *Visitantes en la Red de Parques Nacionales, Anualidad "
        f"{ctx.oapn_report_year}* (Mayo 2024). IECA — *Andalucía pueblo a "
        "pueblo* (SIMA), población y economía municipal, fecha por indicador "
        "en la tabla anterior. Nunca se muestra ninguna cifra de Madrid/PNSG "
        "en su lugar."
    )


def _render_municipal_indicators_table(municipios) -> None:
    """Real IECA/SIMA population + economy indicators (issue #22)."""
    if not municipios:
        return

    indicators = load_sierra_nevada_indicators()
    if not indicators:
        st.caption(
            "⚠️ Snapshot IECA/SIMA no generado todavía — ejecuta "
            "`scripts/build_alpine_municipal_indicators.py` para poblar "
            "población y economía municipal real."
        )
        return

    import pandas as pd

    rows = []
    for m in municipios:
        ind = indicators.get(m.ine_code)
        rows.append({
            "Municipio": m.name,
            "Provincia": m.province,
            "Población": ind.population if ind else None,
            "% ≥65 años": ind.pct_over_65 if ind else None,
            "Var. población 10a (%)": ind.pop_change_10y_pct if ind else None,
            "Paro (%)": ind.unemployment_rate_pct if ind else None,
            "Establ. hostelería": ind.hosteleria_establishments if ind else None,
            "Plazas hoteleras": ind.hotel_beds if ind else None,
        })
    df = pd.DataFrame(rows)

    st.markdown("**Población y economía municipal real (IECA/SIMA)**")
    st.dataframe(
        df, use_container_width=True, hide_index=True,
        column_config={
            "Población": st.column_config.NumberColumn(format="%d"),
            "% ≥65 años": st.column_config.NumberColumn(format="%.1f"),
            "Var. población 10a (%)": st.column_config.NumberColumn(format="%+.1f"),
            "Paro (%)": st.column_config.NumberColumn(format="%.1f"),
            "Establ. hostelería": st.column_config.NumberColumn(format="%d"),
            "Plazas hoteleras": st.column_config.NumberColumn(format="%d"),
        },
    )
    n_missing = sum(1 for m in municipios if m.ine_code not in indicators)
    if n_missing:
        st.caption(
            f"⚠️ {n_missing} municipio(s) sin ficha IECA/SIMA descargada — "
            "casillas vacías, no ceros."
        )
    all_caveats = [
        (m.name, c)
        for m in municipios
        if (ind := indicators.get(m.ine_code)) is not None
        for c in ind.caveats
    ]
    if all_caveats:
        with st.expander(
            f"ℹ️ {len(all_caveats)} dato(s) no publicado(s) por IECA (secreto "
            "estadístico / no disponible)",
            expanded=False,
        ):
            st.markdown("\n".join(f"- *{nm}*: {c}" for nm, c in all_caveats))
