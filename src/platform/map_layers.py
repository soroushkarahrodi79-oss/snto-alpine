"""
SNTO — PyDeck map layer builder for the territorial dashboard.

Replaces the Folium/Leaflet approach with Deck.gl / WebGL rendering.
All rendering happens client-side (GPU), so server RAM stays constant
regardless of how many assets are displayed — enabling scale to hundreds
of assets without Streamlit OOM errors.

Design
------
* `assets_to_geojson()` converts TerritorialAsset objects to a GeoJSON
  FeatureCollection. Geometry is approximate (municipality centroid +
  deterministic per-asset jitter) because real trail coordinates live in
  PostGIS / hiking_trails.geojson, not in the platform layer.

  For production: replace the centroid-based geometry with real coordinates
  read from geopandas::

      gdf = gpd.read_file("data/raw_assets/vector_data/hiking_trails.geojson")
      # merge with assets by name/id, then use gdf.geometry directly

* `build_pydeck_deck()` returns a pydeck.Deck with a single GeoJsonLayer
  so the browser receives one WebGL draw call per frame regardless of
  asset count (vs one Leaflet GeoJSON layer per asset in Folium).

* Tier colour encoding (matches sidebar legend):
    Tier 1 — Red     (Atención Inmediata)
    Tier 2 — Orange  (Acción Preventiva)
    Tier 3 — Blue    (Monitorización)
    Tier 4 — Green   (Promoción Activa)

Dependencies: pydeck>=0.9  (pip install pydeck)
"""
from __future__ import annotations

import math
from typing import Any

try:
    import pydeck as pdk
    _PYDECK_AVAILABLE = True
except ImportError:  # pragma: no cover
    pdk = None  # type: ignore[assignment]
    _PYDECK_AVAILABLE = False

# ── Geography: approximate centroids (WGS-84) per municipality ────────────────
# Source: IGN Nomenclátor Geográfico (municipios de la sierra norte, Madrid)
# Format: (latitude, longitude) — note GeoJSON uses [lon, lat]
_REGION_CENTROIDS: dict[str, tuple[float, float]] = {
    # ── Reserva Biosfera Sierra del Rincón ────────────────────────────────────
    "Montejo de la Sierra":    (41.1700, -3.4830),
    "La Hiruela":              (41.1200, -3.4730),
    "Horcajuelo de la Sierra": (41.1630, -3.4330),
    "Puebla de la Sierra":     (41.0830, -3.4520),
    "Prádena del Rincón":      (41.1130, -3.4970),
    "Robregordo":              (41.1750, -3.5640),
    # ── Parque Nacional Sierra de Guadarrama ─────────────────────────────────
    "Rascafría":               (40.8870, -3.8690),
    "Cercedilla":              (40.7330, -4.0730),
    "Navacerrada":             (40.7700, -4.0070),
    "Manzanares El Real":      (40.7230, -3.8600),
    "Los Molinos":             (40.7630, -4.0220),
    "Guadarrama":              (40.6690, -4.0770),
    "San Lorenzo de El Escorial": (40.5930, -4.1470),
    # ── Alpine Edition — Parque Nacional de Sierra Nevada (Andalucía) ─────────
    # Municipios que aparecen en la cartografía OAPN de sendas/rutas BTT. Deben
    # coincidir con src.territorial.alpine_fixtures._MUNICIPIOS.
    "Sierra Nevada":           (37.0550, -3.3100),
    "Monachil":                (37.1260, -3.5310),
    "Güéjar Sierra":           (37.1630, -3.4370),
    "Güejar Sierra":           (37.1630, -3.4370),
    "Dílar":                   (37.0700, -3.5770),
    "Lanjarón":                (36.9220, -3.4790),
    "Soportújar":              (36.9300, -3.4120),
    "Cáñar":                   (36.9450, -3.4270),
    "Capileira":               (37.0010, -3.3590),
    "Bubión":                  (36.9940, -3.3620),
    "Pampaneira":              (36.9630, -3.3680),
    "Trevélez":                (36.9950, -3.2690),
    "Pórtugos":                (36.9390, -3.3110),
    "Portugos":                (36.9390, -3.3110),
    "Busquístar":              (36.9380, -3.2930),
    "Bérchules":               (36.9820, -3.2080),
    "Mecina Bombarón":         (36.9800, -3.1520),
    "Mecina Bombaron":         (36.9800, -3.1520),
    "Yegen":                   (36.9920, -3.1300),
    "Válor":                   (36.9930, -3.1010),
    "Valor":                   (36.9930, -3.1010),
    "Cádiar":                  (36.9310, -3.1900),
    "Jérez del Marquesado":    (37.1900, -3.1400),
    "Postero Alto":            (37.1600, -3.1200),
    "Aldeire":                 (37.2010, -3.1000),
    "La Calahorra":            (37.1810, -3.0520),
    "Lanteira":                (37.1990, -3.0780),
    "Niguelas":                (36.9810, -3.5270),
    "Cumbres Verdes":          (37.0890, -3.5070),
    "Arenales del Trevenque":  (37.0930, -3.5030),
    "Abrucena":                (37.1320, -2.7970),
    "Bayarcal":                (37.0300, -2.8830),
    "Laujar":                  (36.9930, -2.8970),
    "Refugio Poqueira":        (37.0200, -3.3300),
}

# Fallback centroid for unknown regions (geographic centre of the reserve)
_DEFAULT_CENTROID = (41.130, -3.490)

# Default map centre and initial zoom (Sierra del Rincón)
_MAP_LATITUDE  = 41.130
_MAP_LONGITUDE = -3.490
_MAP_ZOOM      = 11

# ── Colour palette by tier (RGBA lists for Deck.gl / PyDeck) ─────────────────
# Escala NEUTRA índigo→pizarra. El tier es prioridad de inversión (estrategia),
# NO riesgo táctico: por eso no es semafórica. El semáforo (rojo/ámbar/verde) se
# reserva para el gradiente espectral de EHS y para las ALERTAS.
TIER_COLORS: dict[int, list[int]] = {
    1: [ 49,  46,  92, 225],   # índigo profundo — Tier I, prioridad máxima
    2: [ 86,  84, 138, 220],   # índigo medio    — Tier II
    3: [131, 136, 176, 215],   # pizarra media   — Tier III
    4: [179, 184, 212, 210],   # pizarra clara   — Tier IV, mínima inversión
}
_TIER_COLOR_FALLBACK = [150, 150, 150, 180]

# Line colour is a slightly darker, fully-opaque variant of the fill
_TIER_LINE_COLORS: dict[int, list[int]] = {
    1: [ 32,  30,  64, 255],
    2: [ 60,  58, 104, 255],
    3: [ 96, 101, 142, 255],
    4: [140, 146, 178, 255],
}

# Human-readable labels for the legend widget (nomenclatura estructural)
LEGEND_ITEMS: list[dict[str, Any]] = [
    {"tier": 1, "label": "TIER I — Prioridad máxima de inversión", "hex": "#312e5c"},
    {"tier": 2, "label": "TIER II — Inversión preventiva",         "hex": "#56548a"},
    {"tier": 3, "label": "TIER III — Monitorización rutinaria",    "hex": "#8388b0"},
    {"tier": 4, "label": "TIER IV — Promoción / mínima inversión", "hex": "#b3b8d4"},
]

# Asset-type emoji for tooltips
_ASSET_EMOJI: dict[str, str] = {
    "TRAIL":             "🥾",
    "VIEWPOINT":         "🔭",
    "RECREATIONAL_AREA": "🌿",
    "NATURAL_PARK":      "🌲",
    "CYCLING_ROUTE":     "🚴",
}

# Functional designation per asset type (governance terminology, shown in tooltip)
_ASSET_USAGE: dict[str, str] = {
    "TRAIL":             "Senda de senderismo · Uso peatonal preferente",
    "CYCLING_ROUTE":     "Ruta cicloturista · Uso compartido bici-peatón",
    "VIEWPOINT":         "Mirador · Punto de observación paisajística",
    "RECREATIONAL_AREA": "Área recreativa · Uso público regulado",
    "NATURAL_PARK":      "Enclave natural · Conservación prioritaria",
}

# Metres per degree of latitude (near-constant globally)
_M_PER_DEG_LAT = 111_320.0


# ── Geometry helpers ──────────────────────────────────────────────────────────

def _region_centroid(region: str) -> tuple[float, float]:
    """Return (lat, lon) for a region name, falling back to reserve centre."""
    return _REGION_CENTROIDS.get(region, _DEFAULT_CENTROID)


def _jitter(asset_id: str, lat: float, lon: float, spread: float = 0.007) -> tuple[float, float]:
    """Apply a deterministic, asset-specific offset within a region.

    Uses the asset_id hash so the same asset always appears at the same
    location across page reloads, while different assets in the same
    municipality are spread out (spread ≈ 700 m at 41 °N).
    """
    h = hash(asset_id) & 0xFFFF
    dlat = (((h >> 8) & 0xFF) / 255.0 - 0.5) * spread
    dlon = (((h      ) & 0xFF) / 255.0 - 0.5) * spread
    return lat + dlat, lon + dlon


def _trail_endpoints(
    lat: float, lon: float, length_km: float, heading_deg: float
) -> tuple[list[float], list[float]]:
    """Compute start and end [lon, lat] for a trail line.

    Positions the trail symmetrically around (lat, lon) with the given
    heading (0° = North, 90° = East) and total length *length_km*.
    """
    half_km = length_km / 2.0
    lat_rad = math.radians(lat)

    # Metres per degree of longitude at this latitude
    m_per_deg_lon = _M_PER_DEG_LAT * math.cos(lat_rad)

    heading_rad = math.radians(heading_deg)
    dlat_km =  math.cos(heading_rad) * half_km
    dlon_km =  math.sin(heading_rad) * half_km

    dlat_deg = dlat_km * 1000.0 / _M_PER_DEG_LAT
    dlon_deg = dlon_km * 1000.0 / m_per_deg_lon

    start = [lon - dlon_deg, lat - dlat_deg]   # [lon, lat] — GeoJSON order
    end   = [lon + dlon_deg, lat + dlat_deg]
    return start, end


def _heading_from_id(asset_id: str) -> float:
    """Return a deterministic compass heading (0-360°) for a trail."""
    h = (hash(asset_id) >> 16) & 0xFFFF
    return (h / 65535.0) * 360.0


def _trail_path(
    lat: float, lon: float, length_km: float, heading_deg: float, asset_id: str,
    n_points: int = 11,
) -> list[list[float]]:
    """Generate an undulating polyline approximating a mountain trail trace.

    Real trail geometry lives in PostGIS / hiking_trails.geojson; until that
    integration, a straight 2-point segment misleads the territorial analyst.
    This generator produces a deterministic curved path (same trace on every
    reload, keyed on asset_id): points along the heading axis with
    perpendicular sinusoidal offsets that mimic switchbacks and contour-following.

    Returns a list of [lon, lat] vertices (GeoJSON order).
    """
    start, end = _trail_endpoints(lat, lon, length_km, heading_deg)
    h = hash(asset_id)
    # Two deterministic phase/amplitude seeds per trail
    phase1 = ((h >> 4)  & 0xFF) / 255.0 * 2 * math.pi
    phase2 = ((h >> 12) & 0xFF) / 255.0 * 2 * math.pi
    amp_scale = 0.10 + (((h >> 20) & 0xFF) / 255.0) * 0.08   # 10-18 % of length

    # Perpendicular unit vector to the heading (in degree-space, corrected for lat)
    lat_rad = math.radians(lat)
    heading_rad = math.radians(heading_deg)
    # Axis direction in (dlon, dlat) degree-space
    perp_dlat = -math.sin(heading_rad)
    perp_dlon =  math.cos(heading_rad) / max(0.2, math.cos(lat_rad))

    length_deg = length_km * 1000.0 / _M_PER_DEG_LAT   # rough scalar for amplitude
    max_amp = length_deg * amp_scale

    path = []
    for i in range(n_points):
        t = i / (n_points - 1)
        base_lon = start[0] + (end[0] - start[0]) * t
        base_lat = start[1] + (end[1] - start[1]) * t
        # Sum of two sinusoids, pinned to zero at both endpoints
        envelope = math.sin(math.pi * t)
        offset = (
            math.sin(2 * math.pi * t * 1.5 + phase1) * 0.6
            + math.sin(2 * math.pi * t * 3.0 + phase2) * 0.4
        ) * max_amp * envelope
        path.append([
            base_lon + perp_dlon * offset,
            base_lat + perp_dlat * offset,
        ])
    return path


_POINT_RADIUS_MIN_M = 100.0   # floor so tiny areas stay clickable on the map

# Type defaults (metres) for assets without a known area_ha — sized for zoom ~11
_POINT_RADIUS_DEFAULTS: dict[str, float] = {
    "VIEWPOINT":         60.0,
    "RECREATIONAL_AREA": 80.0,
    "NATURAL_PARK":      90.0,
}


def _point_radius_m(asset) -> float:
    """Return a display radius in metres appropriate for a point asset.

    When the asset carries a footprint (``area_ha``) the radius is the
    equivalent-circle radius of that area (r = √(A/π)), so a 100 ha park
    renders ~564 m wide while a small recreational area stays compact —
    a faithful footprint beats a flat cosmetic dot.  A floor keeps even
    tiny areas clickable.  Assets with no area (viewpoints) fall back to
    a type default.
    """
    area_ha = getattr(asset, "area_ha", None)
    if area_ha and area_ha > 0:
        area_m2 = area_ha * 10_000.0
        radius = math.sqrt(area_m2 / math.pi)
        return max(_POINT_RADIUS_MIN_M, radius)
    return _POINT_RADIUS_DEFAULTS.get(asset.asset_type, 70.0)


# ── Real-geometry helpers (Pipeline A traces) ─────────────────────────────────

def _flatten_coords(geom: dict) -> list[list[float]]:
    """Flat list of [lon, lat] vertices from a LineString / MultiLineString / Point."""
    t = geom.get("type")
    c = geom.get("coordinates") or []
    if t == "LineString":
        return [pt for pt in c]
    if t == "MultiLineString":
        return [pt for line in c for pt in line]
    if t == "Point":
        return [c]
    return []


def _representative_point(geoms: list[dict]) -> "list[float] | None":
    """A vertex that lies ON the real trace (its middle vertex), to anchor a point
    asset over its real senda instead of the municipality centroid."""
    pts: list[list[float]] = []
    for g in geoms:
        pts.extend(_flatten_coords(g))
    if not pts:
        return None
    return pts[len(pts) // 2]


def _merge_linestrings(geoms: list[dict]) -> "dict | None":
    """Combine matched trail geometries into one LineString (single) or
    MultiLineString (several), ready for a GeoJsonLayer."""
    lines: list[list[list[float]]] = []
    for g in geoms:
        t = g.get("type")
        c = g.get("coordinates") or []
        if t == "LineString" and c:
            lines.append(c)
        elif t == "MultiLineString":
            lines.extend([part for part in c if part])
    if not lines:
        return None
    if len(lines) == 1:
        return {"type": "LineString", "coordinates": lines[0]}
    return {"type": "MultiLineString", "coordinates": lines}


# ── GeoJSON feature builders ──────────────────────────────────────────────────

def _build_properties(asset) -> dict[str, Any]:
    """Shared GeoJSON property payload for all asset types."""
    tier     = asset.tier or 0
    color    = TIER_COLORS.get(tier, _TIER_COLOR_FALLBACK)
    lcolor   = _TIER_LINE_COLORS.get(tier, _TIER_COLOR_FALLBACK)
    emoji    = _ASSET_EMOJI.get(asset.asset_type, "📍")
    tier_lbl = (asset.tier_label or "Sin clasificar").replace("_", " ").title()
    desc     = (asset.description or "")[:120] + ("…" if len(asset.description or "") > 120 else "")

    return {
        "asset_id":    asset.asset_id,
        "name":        asset.name,
        "asset_type":  f"{emoji} {asset.asset_type.replace('_',' ').title()}",
        "usage":       _ASSET_USAGE.get(asset.asset_type, "Activo turístico natural"),
        "region":      asset.region,
        "ehs":         round(asset.ehs, 1),
        "tier":        tier,
        "tier_label":  tier_lbl,
        "tpi":         round(asset.tpi, 1) if asset.tpi is not None else "—",
        "alert":       (asset.alert_level or "").replace("_", " "),
        "description": desc,
        # Procedencia geométrica (por defecto aproximada; los builders reales lo sobreescriben)
        "geom_source": "approx",
        "geom_note":   "≈ Posición aproximada (centroide municipal)",
        # Deck.gl / GeoJsonLayer colour accessors
        "fill_color":  color,
        "line_color":  lcolor,
    }


def _trail_feature(asset, real_geoms: "list[dict] | None" = None) -> dict[str, Any]:
    """GeoJSON Feature (LineString) for a TRAIL asset.

    When ``real_geoms`` carries the real Pipeline A trace(s) for this asset, the
    feature uses the true cartographic geometry; otherwise it falls back to a
    synthetic path near the municipality centroid.
    """
    props = _build_properties(asset)
    props["length_km"] = asset.length_km or "—"
    props["elevation"] = f"{asset.elevation_m:.0f} m" if asset.elevation_m else "—"

    real_geom = _merge_linestrings(real_geoms) if real_geoms else None
    if real_geom is not None:
        props["geom_source"] = "real"
        props["geom_note"]   = "📍 Traza cartográfica real (Sentinel-2 · Pipeline A)"
        return {"type": "Feature", "geometry": real_geom, "properties": props}

    lat, lon = _region_centroid(asset.region)
    lat, lon = _jitter(asset.asset_id, lat, lon, spread=0.006)
    length_km = asset.length_km or 2.0
    heading   = _heading_from_id(asset.asset_id)
    path = _trail_path(lat, lon, length_km, heading, asset.asset_id)

    return {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": path,
        },
        "properties": props,
    }


def _point_feature(asset, real_geoms: "list[dict] | None" = None) -> dict[str, Any]:
    """GeoJSON Feature (Point) for non-trail assets.

    When ``real_geoms`` carries the asset's real Pipeline A trace(s), the point is
    anchored on a vertex of that real trace; otherwise it falls back to the
    municipality centroid plus deterministic jitter.
    """
    props = _build_properties(asset)
    props["point_radius"] = _point_radius_m(asset)
    props["area_ha"]  = f"{asset.area_ha:.1f} ha" if asset.area_ha else "—"
    props["elevation"] = f"{asset.elevation_m:.0f} m" if asset.elevation_m else "—"

    real_pt = _representative_point(real_geoms) if real_geoms else None
    if real_pt is not None:
        lon, lat = real_pt[0], real_pt[1]
        props["geom_source"] = "real"
        props["geom_note"]   = "📍 Anclado en la traza real de su senda (Sentinel-2 · Pipeline A)"
    else:
        lat, lon = _region_centroid(asset.region)
        lat, lon = _jitter(asset.asset_id, lat, lon, spread=0.010)

    return {
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [lon, lat],   # GeoJSON: [longitude, latitude]
        },
        "properties": props,
    }


# ── Public API ────────────────────────────────────────────────────────────────

def assets_to_geojson(assets: list, real_geoms: "dict[str, list[dict]] | None" = None) -> dict[str, Any]:
    """Convert a list of TerritorialAsset objects to a GeoJSON FeatureCollection.

    Trail assets become LineString features; all other types become Point
    features. Properties include tier-coded colours ready for Deck.gl
    accessor expressions (``"properties.fill_color"``).

    When ``real_geoms`` (``asset_id → [geometry]`` from
    ``calibration.asset_trail_geometries``) is supplied, assets with a real
    Pipeline A trace are drawn on their true cartographic geometry instead of
    the municipality-centroid approximation.

    Args:
        assets: Ranked TerritorialAsset objects (tier and tpi must be set).

    Returns:
        GeoJSON FeatureCollection dict — pass directly to
        ``pydeck.Layer("GeoJsonLayer", data=...)``.
    """
    real_geoms = real_geoms or {}
    features = []
    for asset in assets:
        rg = real_geoms.get(asset.asset_id)
        if asset.asset_type in ("TRAIL", "CYCLING_ROUTE"):
            features.append(_trail_feature(asset, rg))
        else:
            features.append(_point_feature(asset, rg))
    return {"type": "FeatureCollection", "features": features}


def build_pydeck_deck(
    assets: list,
    map_lat: float = _MAP_LATITUDE,
    map_lon: float = _MAP_LONGITUDE,
    map_zoom: int = _MAP_ZOOM,
    real_geoms: "dict[str, list[dict]] | None" = None,
) -> "pdk.Deck":
    """Build a Deck.gl / PyDeck deck for the territorial asset portfolio.

    Uses a single ``GeoJsonLayer`` so the browser issues one WebGL draw
    call per frame regardless of asset count — O(1) GPU cost vs O(N)
    with one Folium layer per asset.

    Args:
        assets: Ranked TerritorialAsset objects (tier set by rank_assets()).

    Returns:
        pydeck.Deck ready for ``st.pydeck_chart()``.

    Raises:
        ImportError: if pydeck is not installed.
    """
    if not _PYDECK_AVAILABLE:
        raise ImportError(
            "pydeck is required for map rendering. "
            "Install it with: pip install pydeck"
        )

    geojson = assets_to_geojson(assets, real_geoms)

    tooltip = {
        "html": (
            "<div style='"
            "font-family:system-ui,sans-serif;"
            "padding:10px 12px;"
            "max-width:270px;"
            "line-height:1.5;"
            "'>"
            "<b style='font-size:13px'>{name}</b><br/>"
            "<span style='color:#85b7eb;font-size:11px;font-weight:600'>{usage}</span><br/>"
            "<span style='color:#a0b0c0;font-size:11px'>{asset_type} · {region}</span>"
            "<hr style='border:none;border-top:1px solid #2e4560;margin:6px 0'/>"
            "<b>EHS</b> {ehs}/100 &nbsp;·&nbsp; "
            "<b>Tier</b> {tier} — {tier_label}<br/>"
            "<span style='font-size:11px;color:#c8d6e5'>{alert}</span><br/>"
            "<span style='font-size:10px;color:#7e93a8;margin-top:3px;display:block'>{geom_note}</span>"
            "<span style='font-size:11px;color:#a0b0c0;margin-top:4px;display:block'>"
            "{description}</span>"
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
        # Point colour (fills circles, colours line rings)
        get_fill_color="properties.fill_color",
        get_line_color="properties.line_color",
        # Point-specific: radius in metres
        get_point_radius="properties.point_radius",
        point_radius_units="meters",
        point_radius_min_pixels=5,
        point_radius_max_pixels=18,
        # Line-specific: width in metres (trails)
        get_line_width=22,
        line_width_units="meters",
        line_width_min_pixels=2,
        line_width_max_pixels=6,
        # Polygon fill opacity is handled via fill_color alpha channel
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


# ── Real-trail diagnostic view (Pipeline A output) ────────────────────────────

def build_real_trails_deck(
    geojson: dict,
    map_lat: float,
    map_lon: float,
    map_zoom: int,
    boundary_geojson: dict | None = None,
) -> "pdk.Deck":
    """Build a Deck.gl deck from REAL trail geometry coloured by computed EHS.

    Unlike build_pydeck_deck (which synthesises trail shapes from municipality
    centroids), this consumes the GeoJSON produced by the Pipeline A bridge
    (src.platform.real_trails.build_real_trails_geojson) where every LineString
    is the true cartographic trace and the colour encodes the satellite-derived
    Ecological Health Score.

    Args:
        geojson: FeatureCollection with per-feature 'line_color' [R,G,B,A].
        map_lat, map_lon, map_zoom: initial view state.

    Returns:
        pydeck.Deck ready for st.pydeck_chart().

    Raises:
        ImportError: if pydeck is not installed.
    """
    if not _PYDECK_AVAILABLE:
        raise ImportError(
            "pydeck is required for map rendering. Install it with: pip install pydeck"
        )

    tooltip = {
        "html": (
            "<div style='font-family:system-ui,sans-serif;padding:10px 12px;"
            "max-width:260px;line-height:1.5;'>"
            "<b style='font-size:13px'>{name}</b><br/>"
            "<span style='color:#a0b0c0;font-size:11px'>{length_km} km · "
            "Prioridad: {priority}</span>"
            "<hr style='border:none;border-top:1px solid #2e4560;margin:6px 0'/>"
            "<b>EHS verano</b> {health_summer}/100 &nbsp;·&nbsp; <b>ΔEHS</b> {delta_health}<br/>"
            "<span style='font-size:11px;color:#c8d6e5'>Causa: {scm}</span><br/>"
            "<span style='font-size:11px;color:#f0c674'>Zona PRUG: {prug}</span><br/>"
            "<span style='font-size:11px;color:#85b7eb'>Presupuesto: {budget}</span>"
            "</div>"
        ),
        "style": {
            "background": "#1b2d42", "color": "white",
            "border-radius": "6px", "padding": "0",
            "box-shadow": "0 4px 12px rgba(0,0,0,.4)",
        },
    }

    layers = []

    # Contorno oficial del parque (debajo de las sendas), si se proporciona.
    if boundary_geojson is not None:
        layers.append(pdk.Layer(
            "GeoJsonLayer",
            data=boundary_geojson,
            pickable=False,
            stroked=True,
            filled=True,
            get_fill_color=[80, 140, 200, 28],     # azul muy tenue
            get_line_color=[120, 180, 240, 200],   # contorno azul claro
            get_line_width=60,
            line_width_units="meters",
            line_width_min_pixels=1,
            line_width_max_pixels=3,
            opacity=1.0,
        ))

    layers.append(pdk.Layer(
        "GeoJsonLayer",
        data=geojson,
        pickable=True,
        stroked=True,
        filled=False,
        get_line_color="properties.line_color",
        get_line_width=30,
        line_width_units="meters",
        line_width_min_pixels=2,
        line_width_max_pixels=7,
        opacity=1.0,
    ))

    view_state = pdk.ViewState(
        latitude=map_lat, longitude=map_lon, zoom=map_zoom, pitch=0, bearing=0,
    )

    return pdk.Deck(
        layers=layers,
        initial_view_state=view_state,
        tooltip=tooltip,
        map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
    )


# ── Spectral diagnostic view ──────────────────────────────────────────────────

# RdYlGn colour ramp anchored at EHS breakpoints (ColorBrewer 5-class diverging).
# Each entry: (ehs_threshold, [R, G, B]).  Values between stops are interpolated.
_SPECTRAL_RAMP: list[tuple[float, list[int]]] = [
    (0.0,   [165,   0,  38]),   # deep red    — critical degradation
    (30.0,  [215,  48,  39]),   # red
    (45.0,  [253, 174,  97]),   # orange
    (60.0,  [255, 255, 191]),   # pale yellow — transitional
    (75.0,  [166, 217, 106]),   # yellow-green
    (100.0, [ 26, 152,  80]),   # deep green  — excellent health
]


def _ehs_to_rgba(ehs: float, alpha: int = 220) -> list[int]:
    """Interpolate an RGBA colour from the RdYlGn spectral ramp for a given EHS.

    Args:
        ehs   : Ecological Health Score 0-100.
        alpha : Opacity byte 0-255 (default 220).

    Returns:
        [R, G, B, A] list ready for Deck.gl colour accessors.
    """
    ehs = max(0.0, min(100.0, ehs))
    # Find the two surrounding stops
    for i in range(len(_SPECTRAL_RAMP) - 1):
        lo_val, lo_rgb = _SPECTRAL_RAMP[i]
        hi_val, hi_rgb = _SPECTRAL_RAMP[i + 1]
        if lo_val <= ehs <= hi_val:
            t = (ehs - lo_val) / (hi_val - lo_val) if hi_val != lo_val else 0.0
            r = int(lo_rgb[0] + t * (hi_rgb[0] - lo_rgb[0]))
            g = int(lo_rgb[1] + t * (hi_rgb[1] - lo_rgb[1]))
            b = int(lo_rgb[2] + t * (hi_rgb[2] - lo_rgb[2]))
            return [r, g, b, alpha]
    # Fallback — should not be reached
    return [128, 128, 128, alpha]


def _assets_to_geojson_spectral(assets: list, real_geoms: "dict[str, list[dict]] | None" = None) -> dict[str, Any]:
    """GeoJSON FeatureCollection with EHS-gradient colours (spectral diagnostic view).

    Identical geometry to assets_to_geojson() but replaces tier-coded colours
    with a continuous RdYlGn gradient derived from each asset's EHS score,
    simulating the NDVI/NDMI spectral signature of corridor degradation.
    """
    real_geoms = real_geoms or {}
    features = []
    for asset in assets:
        color  = _ehs_to_rgba(asset.ehs)
        lcolor = _ehs_to_rgba(asset.ehs, alpha=255)
        rg = real_geoms.get(asset.asset_id)

        if asset.asset_type in ("TRAIL", "CYCLING_ROUTE"):
            feat = _trail_feature(asset, rg)
        else:
            feat = _point_feature(asset, rg)

        # Override tier colours with spectral colours
        feat["properties"]["fill_color"] = color
        feat["properties"]["line_color"] = lcolor
        features.append(feat)

    return {"type": "FeatureCollection", "features": features}


def build_pydeck_deck_spectral(
    assets: list,
    map_lat: float = _MAP_LATITUDE,
    map_lon: float = _MAP_LONGITUDE,
    map_zoom: int = _MAP_ZOOM,
    real_geoms: "dict[str, list[dict]] | None" = None,
) -> "pdk.Deck":
    """Build a Deck.gl deck using the EHS spectral-gradient colour scheme.

    Identical layer config to build_pydeck_deck() except colours encode
    ecological health (RdYlGn) rather than management tier.  Hover tooltip
    adds NDVI/NDMI context explaining the colour encoding.

    Args:
        assets: Ranked TerritorialAsset objects (ehs must be set).

    Returns:
        pydeck.Deck ready for st.pydeck_chart().

    Raises:
        ImportError: if pydeck is not installed.
    """
    if not _PYDECK_AVAILABLE:
        raise ImportError(
            "pydeck is required for map rendering. "
            "Install it with: pip install pydeck"
        )

    geojson = _assets_to_geojson_spectral(assets, real_geoms)

    tooltip = {
        "html": (
            "<div style='"
            "font-family:system-ui,sans-serif;"
            "padding:10px 12px;"
            "max-width:270px;"
            "line-height:1.5;"
            "'>"
            "<b style='font-size:13px'>{name}</b><br/>"
            "<span style='color:#85b7eb;font-size:11px;font-weight:600'>{usage}</span><br/>"
            "<span style='color:#a0b0c0;font-size:11px'>{asset_type} · {region}</span>"
            "<hr style='border:none;border-top:1px solid #2e4560;margin:6px 0'/>"
            "<b>EHS (Salud Ecológica)</b> {ehs}/100<br/>"
            "<span style='font-size:11px;color:#c8d6e5'>"
            "Color = gradiente espectral NDVI/NDMI · "
            "🟢 verde = saludable · 🔴 rojo = degradado"
            "</span><br/>"
            "<span style='font-size:10px;color:#7e93a8;margin-top:3px;display:block'>{geom_note}</span>"
            "<span style='font-size:11px;color:#a0b0c0;margin-top:4px;display:block'>"
            "{description}</span>"
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
        get_line_width=22,
        line_width_units="meters",
        line_width_min_pixels=2,
        line_width_max_pixels=6,
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
