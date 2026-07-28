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
) -> None:
    """Renderiza el observatorio alpino de Sierra Nevada.

    Args:
        ranked_assets: activos territoriales rankeados (tier y tpi asignados).
        base_comps: comparaciones de escenarios de intervención.
        assets_by_id: índice de activos por identificador.
        _view: perfil de audiencia activo (divulgación por capas).
        slope_by_asset: pendiente media por activo (°), colorea el mapa estival.
        ndsi_by_asset: NDSI medio por activo, colorea el mapa invernal.
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
