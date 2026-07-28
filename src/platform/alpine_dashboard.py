"""
SNTO Alpine Edition — Sierra Nevada observatory view builders
==============================================================
Pure presentation logic for the dual-season public-sector dashboard.

Like every other module in ``src/platform/``, this file **must not import
Streamlit**. It returns PyDeck decks, Plotly figures and dataclasses; the
Streamlit surface that renders them lives in ``src/ui/tabs/tab_alpine.py``.
That separation is what lets the whole view be unit-tested headless.

The module is a thin layer over the existing builders. ``map_layers`` already
produces a single-draw-call ``GeoJsonLayer`` deck, and ``charts`` already
produces the four-quadrant TPI matrix with Roman-numeral tier labels. Neither
is reimplemented here — what is added is the *seasonal recolouring* those
builders cannot express:

* **Winter — Snowpack & Ski Resilience.** Trails are coloured by snow presence
  (NDSI), so retreat of the snowpack is legible as a map, not a table.
* **Summer — MTB & Soil Health.** Trails are coloured by terrain slope, the
  variable that drives rutting and that the erosion buffer already computes.

The tier palette is left strictly alone. It is a deliberately neutral
indigo→slate ramp because tier means *investment priority*, not danger, and two
tests in ``tests/unit/test_map_layers.py`` enforce that it never becomes a
traffic light. The seasonal ramps introduced here colour a different variable
(snow, slope) and never overwrite tier semantics on the matrix.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from src.features.alpine_spectral import AlpineSeason
from src.platform.charts import build_portfolio_matrix
from src.platform.map_layers import _PYDECK_AVAILABLE, assets_to_geojson, pdk

__all__ = [
    "ALPINE_SEASON_VIEWS",
    "SIERRA_NEVADA_VIEW",
    "AlpineSeasonView",
    "alert_badge_counts",
    "alpine_assets_to_geojson",
    "build_alpine_deck",
    "build_alpine_matrix",
    "season_view",
    "slope_to_rgba",
    "snow_to_rgba",
]

# ── Map framing: Sierra Nevada ───────────────────────────────────────────────
# Centred between the Veleta/Mulhacén high massif and the Alpujarra valleys, so
# both the ski domain and the summer trail network are in the initial viewport.
SIERRA_NEVADA_VIEW: dict[str, float] = {
    "latitude": 37.055,
    "longitude": -3.330,
    "zoom": 10.0,
}


@dataclass(frozen=True)
class AlpineSeasonView:
    """Everything the UI needs to render one season, resolved from the season."""

    season: AlpineSeason
    label: str
    question: str
    primary_indices: tuple[str, ...]
    colour_variable: str      # "ndsi" | "slope_deg"
    legend_caption: str


ALPINE_SEASON_VIEWS: dict[AlpineSeason, AlpineSeasonView] = {
    AlpineSeason.WINTER: AlpineSeasonView(
        season=AlpineSeason.WINTER,
        label="Invierno — Innivación y resiliencia de la estación",
        question="¿Hasta dónde llega la nieve y cuánto dura?",
        primary_indices=("NDSI",),
        colour_variable="ndsi",
        legend_caption="Color = cobertura de nieve (NDSI)",
    ),
    AlpineSeason.SUMMER: AlpineSeasonView(
        season=AlpineSeason.SUMMER,
        label="Verano — BTT y salud del suelo",
        question="¿Dónde erosiona el uso recreativo los borreguiles?",
        primary_indices=("EVI", "NDMI"),
        colour_variable="slope_deg",
        legend_caption="Color = pendiente media del sendero (°)",
    ),
}


def season_view(season: AlpineSeason) -> AlpineSeasonView:
    """Resolve the view descriptor for a season."""
    return ALPINE_SEASON_VIEWS[season]


# ── Seasonal colour ramps ────────────────────────────────────────────────────
# Snow: slate (bare) → white (deep snow). Deliberately monochrome-cold; using a
# red/green semaphore for snow would imply snow is good or bad rather than
# present or absent.
_SNOW_RAMP: list[tuple[float, list[int]]] = [
    (-0.20, [ 74,  85, 104]),   # bare rock / vegetation
    ( 0.20, [116, 143, 173]),   # patchy / wet snow
    ( 0.40, [168, 197, 222]),   # snow threshold
    ( 0.70, [214, 232, 246]),   # continuous snowpack
    ( 1.00, [255, 255, 255]),   # fresh deep snow
]

# Slope: green (gentle) → amber → red (steep). Semaphore is legitimate here —
# steep genuinely means higher erosion hazard, matching the project's rule that
# the traffic light is reserved for risk.
_SLOPE_RAMP: list[tuple[float, list[int]]] = [
    ( 0.0, [ 46, 125,  50]),    # flat — gentle borreguil
    (10.0, [154, 186,  70]),
    (20.0, [230, 168,  40]),    # ALPINE_STEEP_SLOPE_DEG — widening begins
    (30.0, [216, 106,  40]),    # HP_SLOPE_MAX_DEG
    (45.0, [198,  40,  40]),    # extreme descent
]


def _interpolate_ramp(
    value: float,
    ramp: list[tuple[float, list[int]]],
    alpha: int,
) -> list[int]:
    """Linearly interpolate an RGBA colour from a sorted stop ramp."""
    if value <= ramp[0][0]:
        return ramp[0][1] + [alpha]
    if value >= ramp[-1][0]:
        return ramp[-1][1] + [alpha]

    for (lo_val, lo_rgb), (hi_val, hi_rgb) in zip(ramp, ramp[1:]):
        if lo_val <= value <= hi_val:
            span = hi_val - lo_val
            ratio = (value - lo_val) / span if span else 0.0
            return [
                int(round(lo + (hi - lo) * ratio))
                for lo, hi in zip(lo_rgb, hi_rgb)
            ] + [alpha]

    return ramp[-1][1] + [alpha]  # pragma: no cover - unreachable given guards


def snow_to_rgba(ndsi: float, alpha: int = 230) -> list[int]:
    """Map an NDSI value to an RGBA colour on the snow ramp.

    Args:
        ndsi: NDSI in [-1, 1].
        alpha: opacity channel, 0-255.

    Returns:
        ``[r, g, b, a]`` suitable for a Deck.gl colour accessor.
    """
    return _interpolate_ramp(ndsi, _SNOW_RAMP, alpha)


def slope_to_rgba(slope_deg: float, alpha: int = 230) -> list[int]:
    """Map a slope in degrees to an RGBA colour on the erosion-hazard ramp.

    Args:
        slope_deg: mean trail slope in degrees.
        alpha: opacity channel, 0-255.

    Returns:
        ``[r, g, b, a]`` suitable for a Deck.gl colour accessor.
    """
    return _interpolate_ramp(slope_deg, _SLOPE_RAMP, alpha)


def alpine_assets_to_geojson(
    assets: list,
    season: AlpineSeason,
    real_geoms: Optional[dict[str, list[dict]]] = None,
    slope_by_asset: Optional[dict[str, float]] = None,
    ndsi_by_asset: Optional[dict[str, float]] = None,
) -> dict[str, Any]:
    """Build the season-coloured GeoJSON for the alpine map.

    Delegates geometry construction to
    :func:`src.platform.map_layers.assets_to_geojson` — including its real
    Pipeline A trace handling — then overrides only the colour accessors and
    adds the seasonal readout to each feature's properties.

    Assets with no measurement for the season keep their inherited tier colour,
    so a missing NDSI reads as "not measured" rather than as bare ground.

    Args:
        assets: ranked TerritorialAsset objects.
        season: WINTER or SUMMER.
        real_geoms: optional ``asset_id → [geometry]`` real traces.
        slope_by_asset: mean slope per asset, degrees (summer colouring).
        ndsi_by_asset: mean NDSI per asset (winter colouring).

    Returns:
        GeoJSON FeatureCollection dict.
    """
    geojson = assets_to_geojson(assets, real_geoms)
    slope_by_asset = slope_by_asset or {}
    ndsi_by_asset = ndsi_by_asset or {}
    view = season_view(season)

    for feature in geojson["features"]:
        props = feature["properties"]
        asset_id = props.get("asset_id")

        if season is AlpineSeason.WINTER:
            value = ndsi_by_asset.get(asset_id)
            props["season_metric"] = "NDSI"
            props["season_value"] = (
                f"{value:+.2f}" if value is not None else "sin dato"
            )
            if value is not None:
                props["fill_color"] = snow_to_rgba(value)
                props["line_color"] = snow_to_rgba(value, alpha=255)
        else:
            value = slope_by_asset.get(asset_id)
            props["season_metric"] = "Pendiente media"
            props["season_value"] = (
                f"{value:.1f}°" if value is not None else "sin dato"
            )
            if value is not None:
                props["fill_color"] = slope_to_rgba(value)
                props["line_color"] = slope_to_rgba(value, alpha=255)

        props["season_label"] = view.label

    return geojson


def build_alpine_deck(
    assets: list,
    season: AlpineSeason,
    real_geoms: Optional[dict[str, list[dict]]] = None,
    slope_by_asset: Optional[dict[str, float]] = None,
    ndsi_by_asset: Optional[dict[str, float]] = None,
    map_lat: float = SIERRA_NEVADA_VIEW["latitude"],
    map_lon: float = SIERRA_NEVADA_VIEW["longitude"],
    map_zoom: float = SIERRA_NEVADA_VIEW["zoom"],
) -> "pdk.Deck":
    """Build the season-aware Sierra Nevada PyDeck map.

    A single ``GeoJsonLayer``, matching the base map builders: one WebGL draw
    call regardless of trail count.

    Args:
        assets: ranked TerritorialAsset objects.
        season: WINTER or SUMMER.
        real_geoms: optional real Pipeline A traces.
        slope_by_asset: mean slope per asset, degrees.
        ndsi_by_asset: mean NDSI per asset.
        map_lat: initial viewport latitude.
        map_lon: initial viewport longitude.
        map_zoom: initial viewport zoom.

    Returns:
        ``pydeck.Deck`` ready for ``st.pydeck_chart()``.

    Raises:
        ImportError: if pydeck is not installed.
    """
    if not _PYDECK_AVAILABLE:
        raise ImportError(
            "pydeck is required for map rendering. "
            "Install it with: pip install pydeck"
        )

    geojson = alpine_assets_to_geojson(
        assets,
        season,
        real_geoms=real_geoms,
        slope_by_asset=slope_by_asset,
        ndsi_by_asset=ndsi_by_asset,
    )

    tooltip = {
        "html": (
            "<div style='"
            "font-family:system-ui,sans-serif;"
            "padding:10px 12px;"
            "max-width:270px;"
            "line-height:1.5;"
            "'>"
            "<b style='font-size:13px'>{name}</b><br/>"
            "<span style='color:#a0b0c0;font-size:11px'>{asset_type} · {region}</span>"
            "<hr style='border:none;border-top:1px solid #2e4560;margin:6px 0'/>"
            "<b>{season_metric}</b> {season_value}<br/>"
            "<b>EHS</b> {ehs}/100 &nbsp;·&nbsp; "
            "<b>Tier</b> {tier} — {tier_label}<br/>"
            "<span style='font-size:11px;color:#c8d6e5'>{alert}</span><br/>"
            "<span style='font-size:10px;color:#7e93a8;margin-top:3px;display:block'>"
            "{geom_note}</span>"
            "</div>"
        ),
        "style": {
            "background": "#1b2d42",
            "color": "white",
            "border-radius": "6px",
            "padding": "0",
            "box-shadow": "0 4px 12px rgba(0,0,0,.4)",
        },
    }

    layer = pdk.Layer(
        "GeoJsonLayer",
        data=geojson,
        pickable=True,
        stroked=True,
        filled=True,
        extruded=False,
        get_fill_color="properties.fill_color",
        get_line_color="properties.line_color",
        get_point_radius="properties.point_radius",
        point_radius_units="meters",
        point_radius_min_pixels=5,
        point_radius_max_pixels=18,
        get_line_width=26,
        line_width_units="meters",
        line_width_min_pixels=2,
        line_width_max_pixels=7,
        opacity=1.0,
    )

    view_state = pdk.ViewState(
        latitude=map_lat,
        longitude=map_lon,
        zoom=map_zoom,
        pitch=0,
        bearing=0,
    )

    return pdk.Deck(
        layers=[layer],
        initial_view_state=view_state,
        tooltip=tooltip,
        map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
    )


# ── TPI portfolio matrix ─────────────────────────────────────────────────────

_CRITICAL_ALERT = "CRITICAL_INTERVENTION"
_URGENT_ALERT = "URGENT_MONITORING"


def alert_badge_counts(assets: list) -> dict[str, int]:
    """Count assets carrying a critical or urgent alert.

    Args:
        assets: ranked TerritorialAsset objects.

    Returns:
        ``{"critical": n, "urgent": n}``.
    """
    critical = sum(
        1 for a in assets if getattr(a, "alert_level", None) == _CRITICAL_ALERT
    )
    urgent = sum(
        1 for a in assets if getattr(a, "alert_level", None) == _URGENT_ALERT
    )
    return {"critical": critical, "urgent": urgent}


def build_alpine_matrix(assets: list, title: Optional[str] = None):
    """Build the TPI portfolio matrix with alpine framing and alert badges.

    Delegates the four-quadrant scatter to
    :func:`src.platform.charts.build_portfolio_matrix` — which already plots one
    trace per tier with Roman-numeral labels (``TIER I``…``TIER IV``), quadrant
    dividers at x=50/y=50 and the neutral tier palette — then annotates the
    critical/urgent counts so a director sees the alert load without reading
    every marker.

    Args:
        assets: ranked TerritorialAsset objects (tier and tpi must be set).
        title: optional title override.

    Returns:
        ``plotly.graph_objects.Figure``.
    """
    fig = build_portfolio_matrix(assets)

    if not assets:
        return fig

    badges = alert_badge_counts(assets)
    parts: list[str] = []
    if badges["critical"]:
        parts.append(
            f"<span style='color:#c62828'><b>🔴 {badges['critical']} "
            f"crítico{'s' if badges['critical'] != 1 else ''}</b></span>"
        )
    if badges["urgent"]:
        parts.append(
            f"<span style='color:#e65100'><b>🟠 {badges['urgent']} "
            f"urgente{'s' if badges['urgent'] != 1 else ''}</b></span>"
        )

    if parts:
        fig.add_annotation(
            xref="paper",
            yref="paper",
            x=1.0,
            y=1.10,
            xanchor="right",
            yanchor="bottom",
            showarrow=False,
            align="right",
            text=" &nbsp;·&nbsp; ".join(parts),
            font=dict(size=12),
        )

    if title:
        fig.update_layout(title=dict(text=title))

    return fig
