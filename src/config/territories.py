"""
SNTO — Territory Registry
=========================
Central definition of all observatory territories. Each entry carries the
study-area bounding box (WGS 84, W S E N), the Sentinel-2 tile code, and
human-readable metadata used by ETL scripts and pipeline reports.

Adding a new territory
----------------------
1. Add a TerritoryConfig entry to TERRITORIES.
2. Place raw Sentinel-2 .SAFE folders under
       data/raw_assets/raster_data/<folder_name>/
3. Run prepare_raster.py --territory <key> ... to populate
       data/clean_assets/<key>/
4. Register vector layers in etl_vector_cleaner.py if available.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TerritoryConfig:
    key: str                              # unique slug used in CLI flags and paths
    display_name: str
    bbox_wgs84: tuple[float, float, float, float]  # (W, S, E, N)
    s2_tile: str                          # Sentinel-2 MGRS tile (e.g. "T30TVL")
    raw_raster_folder: str                # sub-folder under data/raw_assets/raster_data/
    protection_category: str             # e.g. "Biosphere Reserve", "National Park"
    # Trail cartography file under data/raw_assets/vector_data/ analysed by the
    # Pipeline A (EHS / ΔEHS / SCM / budget). One GeoJSON of LineString trails.
    trails_geojson: str = "hiking_trails.geojson"
    # Dashboard discriminator used by app.py to bind the live observatory tab
    # for this territory to the per-trail pipeline output. Matches the
    # short key used by _TERRITORY_CONFIG / _BUILD_FN in app.py.
    dashboard_key: str = ""
    region: str = "Comunidad de Madrid"
    country: str = "Spain"
    notes: str = ""
    # Optional external data sources available for this territory
    external_sources: list[str] = field(default_factory=list)
    # Sentinel-2 MGRS tiles whose union covers the territory. Empty means
    # "just s2_tile" (single-tile territories keep the old single-item ETL
    # path); >1 entries routes etl_raster_processor.py through the
    # multi-tile mosaic (issue #7 — Sierra Nevada spans 4 tiles).
    mgrs_tiles: tuple[str, ...] = ()


# ── Registered territories ─────────────────────────────────────────────────────

TERRITORIES: dict[str, TerritoryConfig] = {

    "sierra_del_rincon": TerritoryConfig(
        key="sierra_del_rincon",
        display_name="Reserva de la Biosfera Sierra del Rincón",
        bbox_wgs84=(-3.65, 41.05, -3.30, 41.20),
        s2_tile="T30TVL",
        raw_raster_folder="Sierra del Rincón",
        protection_category="Biosphere Reserve (UNESCO MAB)",
        trails_geojson="hiking_trails.geojson",
        dashboard_key="snr",
        notes="Pilot territory. Small municipalities: Montejo de la Sierra, "
              "Prádena del Rincón, La Hiruela, Horcajuelo de la Sierra, Madarcos.",
        external_sources=["INE — padrón municipal", "OSM — senderos"],
    ),

    "pnsg": TerritoryConfig(
        key="pnsg",
        display_name="Parque Nacional Sierra de Guadarrama",
        # Full park boundary (Madrid + Segovia sides). For Madrid-only analysis
        # tighten to (-3.98, 40.68, -3.58, 41.05).
        bbox_wgs84=(-4.21, 40.65, -3.58, 41.08),
        s2_tile="T30TVL",
        raw_raster_folder="PNSG",
        protection_category="National Park (Red de Parques Nacionales)",
        trails_geojson="pnsg_oapn_trails.geojson",  # cartografía OFICIAL OAPN (225 sendas)
        dashboard_key="pnsg",
        notes="Larger territory with diverse municipalities: Cercedilla, "
              "Navacerrada, Guadarrama, Los Molinos, Collado Mediano, "
              "Manzanares el Real, Rascafría, Lozoya. "
              "Straddles Madrid and Castilla y León (Segovia). "
              "Richer socioeconomic data available via ALMUDENA and INE.",
        external_sources=[
            "ALMUDENA (Comunidad de Madrid IDE) — parcelas, usos del suelo, "
            "red viaria, edificios: https://www.comunidad.madrid/servicios/mapas/descarga-datos",
            "INE — Censo 2021, padrón municipal, estadística de turismo rural: "
            "https://www.ine.es/dyngs/INEbase/es/categoria.htm?c=Estadistica_P&cid=1254734710984",
            "MITERD OAPN — límite administrativo PNSG, ZEC, senderos oficiales: "
            "https://www.miteco.gob.es/es/red-parques-nacionales/nuestros-parques/guadarrama/",
            "OSM — red de senderos, miradores, aparcamientos",
        ],
    ),

    "sierra_nevada": TerritoryConfig(
        key="sierra_nevada",
        display_name="Parque Nacional de Sierra Nevada",
        # Macizo completo: vertiente norte (Granada / estación de esquí) y
        # vertiente sur (Alpujarra). Cubre Veleta (3.396 m) y Mulhacén (3.479 m),
        # el punto más alto de la península ibérica.
        # Widened past the original (-3.60, 36.90, -2.85, 37.20) after issue #7:
        # the real OAPN trail geometries (issue #6) extend to lon -2.7568 /
        # lat 37.2713, past the old E/N edges — those assets got silently
        # dropped from every STAC search. Bounds now cover the real traces
        # with a small margin.
        bbox_wgs84=(-3.61, 36.90, -2.74, 37.28),
        # Cuatro tiles MGRS cubren el macizo; 30SVF es el de la zona alta y el
        # que usan por defecto los scripts de descarga.
        s2_tile="T30SVF",
        raw_raster_folder="Sierra Nevada",
        protection_category="National Park (Red de Parques Nacionales)",
        trails_geojson="sierra_nevada_oapn_trails.geojson",
        dashboard_key="sn",
        region="Andalucía",
        mgrs_tiles=("30SVF", "30SWF", "30SVG", "30SWG"),
        notes="Alpine Edition pilot. Doble estacionalidad: innivación invernal "
              "(NDSI, cota de nieve, duración del manto) y erosión estival de "
              "borreguiles por BTT y senderismo. Municipios: Monachil, "
              "Güéjar Sierra, Capileira, Trevélez, Bubión, Pampaneira. "
              "El macizo cae en 4 teselas MGRS (ver mgrs_tiles); el mosaico "
              "invernal multi-tesela vive en etl_raster_processor.py (#7). "
              "NO validado en campo — ver campaña de validación pendiente.",
        external_sources=[
            "OAPN MITECO — límite del parque y senderos oficiales: "
            "https://www.miteco.gob.es/es/red-parques-nacionales/nuestros-parques/sierra-nevada/",
            "Junta de Andalucía REDIAM — cartografía ambiental y usos del suelo: "
            "https://www.juntadeandalucia.es/medioambiente/portal/acceso-rediam",
            "INE — padrón municipal y estadística de turismo de Andalucía: "
            "https://www.ine.es/dyngs/INEbase/es/categoria.htm?c=Estadistica_P&cid=1254734710984",
            "Copernicus DEM GLO-30 (STAC) — pendiente y orientación",
            "OSM — red de senderos y rutas BTT",
        ],
    ),
}


def get(key: str) -> TerritoryConfig:
    """Return a TerritoryConfig by key, raising KeyError with a helpful message."""
    if key not in TERRITORIES:
        available = ", ".join(sorted(TERRITORIES))
        raise KeyError(
            f"Unknown territory '{key}'. Available: {available}"
        )
    return TERRITORIES[key]


def list_keys() -> list[str]:
    return sorted(TERRITORIES)
