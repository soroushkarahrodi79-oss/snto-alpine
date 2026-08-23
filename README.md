<div align="center">

# 🏔 Smart Natural Tourism Observatory — Alpine Edition (Sierra Nevada Pilot)

**Capa de inteligencia para la decisión en espacios naturales protegidos de alta montaña.** Código abierto, para uso académico.

De la teledetección Sentinel-2 a la decisión de inversión pública sobre el **Parque Nacional de Sierra Nevada** (Andalucía): innivación invernal, erosión estival de *borreguiles* por BTT y senderismo, atribución causal frente al clima, y traducción financiera TRAGSA para la administración pública (Junta de Andalucía, MITECO, Cetursa Sierra Nevada).

[![Tests](https://img.shields.io/badge/tests-1150%2B%20passing-brightgreen)](#7-tests)
[![Python](https://img.shields.io/badge/python-%E2%89%A53.12-blue)](https://www.python.org/)
[![CI](https://github.com/soroushkarahrodi79-oss/snto-alpine/actions/workflows/ci.yml/badge.svg)](https://github.com/soroushkarahrodi79-oss/snto-alpine/actions/workflows/ci.yml)
[![Version](https://img.shields.io/badge/versi%C3%B3n-0.1.0-blue)](#1-estado-del-proyecto)
[![Status](https://img.shields.io/badge/estado-prototipo%20·%20sin%20validar-lightgrey)](#1-estado-del-proyecto)
[![License](https://img.shields.io/badge/uso-acad%C3%A9mico-lightgrey)](LICENSE)

🏗 [Arquitectura](ARCHITECTURE.md) · 🗺 [Hoja de ruta Alpine](docs/roadmap/alpine-v0.1.md) · 🌱 [Observatorio base (del que deriva)](https://github.com/soroushkarahrodi79-oss/snto-smart-tourism-observatory)

> ℹ️ **Edición derivada, versión 0.1.0.** Este repositorio es un *fork* del [observatorio base SNTO](https://github.com/soroushkarahrodi79-oss/snto-smart-tourism-observatory) y **reutiliza su motor** (EHS, SCM, DCS, capa temporal, persistencia, UI de 4 capas). No hereda su linaje de versiones (v1.0→v2.0), su DOI de Zenodo ni su despliegue en vivo — esos pertenecen al proyecto base. Este README describe **la Edición Alpina**; la relación con el motor heredado se detalla en [§10](#10-relación-con-el-observatorio-base).

</div>

---

## 🎯 El problema en una frase

Sierra Nevada afronta **dos amenazas espectralmente opuestas en el mismo macizo**: en invierno, el retroceso del manto nivoso por el cambio climático (clave para la resiliencia de la estación de esquí y del recurso hídrico); en verano, la erosión de los *borreguiles* —pastos húmedos de alta montaña sobre el límite arbóreo— bajo la presión del *mountain bike* y el senderismo. La Edición Alpina detecta ambas desde el satélite, **distingue el uso recreativo del forzamiento climático**, y traduce el hallazgo en una prioridad de inversión con coste TRAGSA y nivel de confianza.

> SNTO **no reemplaza** a ArcGIS, Google Earth Engine, Sentinel Hub, Tableau ni Power BI: se sitúa **por encima** de las plataformas GIS, de observación de la Tierra y de BI, y traduce su señal en decisiones de conservación defendibles.

---

## 📑 Índice

1. [Estado del proyecto](#1-estado-del-proyecto)
2. [Arquitectura de doble temporada](#2-arquitectura-de-doble-temporada)
3. [Módulos de la Edición Alpina](#3-módulos-de-la-edición-alpina)
4. [Stack tecnológico](#4-stack-tecnológico)
5. [Estructura del repositorio](#5-estructura-del-repositorio)
6. [Orden de ejecución](#6-orden-de-ejecución)
7. [Tests](#7-tests)
8. [Honestidad sobre limitaciones](#8-honestidad-sobre-limitaciones)
9. [Fundamento científico](#9-fundamento-científico)
10. [Relación con el observatorio base](#10-relación-con-el-observatorio-base)
11. [Fuentes y licencias de datos](#11-fuentes-y-licencias-de-datos)
12. [Licencia / uso académico](#12-licencia--uso-académico)

---

## 1. Estado del proyecto

`0.1.0` — **primera release, prototipo reproducible sin validación de campo.** El versionado reinicia desde 0.x deliberadamente: es una línea de producto nueva. La madurez del **motor heredado** (arquitectura modular, backend persistente, UI por roles) es del observatorio base; la **adaptación alpina** es un prototipo que cierra el hito `Alpine 0.1.0`.

| Componente alpino | Estado |
|---|---|
| **Geometrías reales de sendero** — `src/platform/alpine_trail_geoms.py` | ✅ 53/53 trazas OAPN reales (`clean_assets/sierra_nevada_trails.geojson`, issue #6). El mapa dibuja la traza completa en lugar de centroide+jitter. |
| **Índices alpinos (NDSI + doble temporada)** — `src/features/alpine_spectral.py` | ✅ Verano: serie GEE real de 53 activos. Invierno: mosaico multitesela real 30SVF/30SWF/30SVG/30SWG, serie Dic 2023–Mar 2024 con CI bootstrap (52/53 activos; 1 fuera de toda huella STAC, documentado — issue #7/#8). |
| **Buffer de erosión escalado por pendiente** — `src/geospatial/alpine_dem.py` | 🟡 Implementado y con tests. Requiere DEM Copernicus vía STAC en ejecución real. |
| **SCM alpino (control emparejado por altitud)** — `src/spatial_causality/alpine_causality.py` | ✅ 52/53 activos con `evidence_class=REAL`; zonas de control emparejadas por altitud ±50 m. 1 activo sin control válido (`NO_VALID_CONTROL` explícito — issue #9). |
| **ROI público (TRAGSA × pendiente)** — `src/risk_engine/public_roi.py` | 🟡 Implementado. Tarifa base real (TRAGSA 2023); factor pendiente ×1,0→×1,8 es supuesto de planificación, no tarifa publicada. |
| **Dashboard alpino** — `src/platform/alpine_dashboard.py` + `src/ui/tabs/tab_alpine.py` | ✅ 53 activos cableados con trazas reales; conmutador Invierno/Verano; simulador 50K–1M €; matriz TPI; contexto municipal real IECA/SIMA. Sin despliegue en producción. |
| **Territorio Sierra Nevada** — `src/config/territories.py` | ✅ `TerritoryConfig` real (bbox del macizo, teselas 30SVF/30SWF/30SVG/30SWG). |
| **Crosswalk INE andaluz** — `src/socioeconomic/alpine_mapping.py` | ✅ Cruce INE Granada/Almería real para 25 municipios; figura de visitantes OAPN real (≈734.295, 2023) — issue #10. Nunca usa proxies del PNSG/Madrid. |
| **Indicadores municipales IECA/SIMA** — `src/socioeconomic/alpine_indicators.py` | ✅ Fichas reales para 24/24 municipios: población, envejecimiento, cambio demográfico, paro, hostelería, establecimientoss, transacciones inmobiliarias, superficie agrícola, consumo eléctrico, ingresos/gastos por habitante — con secreto estadístico (`*`) parseado a `None`, no a cero (issues #22, #27). |
| **Fuentes de nieve independientes** — `src/validation/aemet_snow.py` / `cetursa_snow.py` | 🟡 AEMET OpenData `nev1` y Cetursa (Umbraco JSON, sin autenticación) ambos cableados y verificados en vivo. Sin datos de invierno disponibles en temporada cerrada; verificación retroactiva imposible (sin archivo histórico) — issue #21. |
| **Validación de campo** | ⛔ **No realizada.** Protocolo BACI diseñado (`docs/alpine_field_validation_protocol.md`); la campaña no se ha ejecutado — issue #11. |

✅ = dato real observado o geometría real OAPN/INE/IECA. 🟡 = implementado y con tests, dato o cobertura aún parcial. ⛔ = no disponible.

**1.150+ tests superados, 1 omitido** — suite completa incluyendo los módulos alpinos nuevos (`test_alpine_trail_geoms`, `test_alpine_scm_zones`, `test_alpine_snow_series`, `test_alpine_indicators`, `test_aemet_snow`, `test_cetursa_snow`, `test_zonal_stats`, etc.).

---

## 2. Arquitectura de doble temporada

Sierra Nevada plantea **dos problemas espectralmente opuestos en el mismo territorio**, y esa oposición estructura toda la edición:

| | **Invierno** | **Verano** |
|---|---|---|
| Problema | Retroceso del manto nivoso | Erosión de borreguiles por BTT y senderismo |
| La nieve es… | **la señal** | **ruido** |
| Índice | NDSI = (B03 − B11) / (B03 + B11) | EVI + NDMI |
| Máscara SCL | **conserva** la clase 11 | **descarta** la clase 11 |
| Salidas | Cota de nieve (m s.n.m.), duración del manto | Índice de degradación del suelo |

**La asimetría de máscara es el núcleo de la edición.** El motor base excluye la clase SCL 11 (nieve/hielo) como contaminación — correcto para un parque de media montaña, catastrófico para un índice de nieve: vaciaría la escena justo en los meses de interés. `src/features/alpine_spectral.py` define dos conjuntos de exclusión (`alpine_valid_mask`) y el conmutador estacional que elige entre ellos.

El agua se excluye en ambas temporadas: comparte la firma NDSI de la nieve (verde alto, SWIR bajo), y las lagunas glaciares están precisamente en la cota que determina la línea de nieve. Por eso `is_snow_pixel()` exige además un **suelo de reflectancia NIR** — la nieve sigue siendo reflectante en el infrarrojo cercano; el agua líquida no.

### Flujo por capas (Ingesta → Extracción → Riesgo → UI)

```mermaid
flowchart LR
  subgraph ING["Ingesta"]
    S2["Sentinel-2 L2A vía STAC<br/>B03·B04·B08·B11·SCL"]
    DEM["Copernicus DEM-30<br/>vía STAC · EPSG:25830"]
  end
  subgraph FEAT["Extracción de rasgos"]
    MASK["Máscara SCL estacional<br/>alpine_valid_mask()"]
    WIN["Invierno: NDSI · cota de nieve<br/>· duración del manto"]
    SUM["Verano: EVI · NDMI<br/>· degradación del suelo"]
    SLOPE["Pendiente y orientación<br/>compute_slope_aspect()"]
    BUF["Buffer asimétrico escalado<br/>15 m arriba / 60→80 m abajo"]
  end
  subgraph RISK["Motor de riesgo"]
    SCM["SCM alpino: zona local 0–50 m<br/>vs control 200–500 m<br/>MISMA COTA ±50 m"]
    ATTR["Índice de atribución<br/>+ puerta de pendiente"]
    ROI["Coste TRAGSA × factor pendiente<br/>+ empleos e ingresos"]
  end
  subgraph UI["Interfaz"]
    DASH["Conmutador de temporada · mapa PyDeck<br/>· simulador 50 K–1 M € · matriz TPI"]
  end

  S2 --> MASK --> WIN & SUM
  DEM --> SLOPE --> BUF
  SUM --> SCM
  BUF --> SCM --> ATTR --> ROI
  WIN --> DASH
  ATTR --> DASH
  ROI --> DASH
```

### Convención de scores: salud vs estrés (heredada del motor)

El sistema usa dos direcciones de score 0–100 y no deben mezclarse:

- **Health Score / EHS:** 0 = crítico, 100 = saludable. Convenio del dashboard, TPI, tiers y comunicación ejecutiva.
- **Stress Score / EHS operacional:** 0 = sin estrés, 100 = máxima degradación. Convenio de las columnas legacy del pipeline geoespacial.

La conversión oficial vive en `src.metrics.semantics`: `health = 100 − stress`.

> **Disciplina de evidencia.** Toda cifra socioeconómica es una estimación *proxy*, no una observación, y `PublicROIStatement` transporta su `EvidenceClass`. Conforme a la matriz de `src/platform/evidence.py`, una afirmación `SIMULATED` **no sostiene ninguna decisión de gasto por sí sola**. Nada en esta edición está validado en campo.

---

## 3. Módulos de la Edición Alpina

| Módulo | Aportación sobre el motor base |
|---|---|
| `src/features/alpine_spectral.py` | NDSI, máscara SCL estacional, discriminación nieve/agua (suelo NIR), cota de nieve, duración del manto, índice de degradación de borreguiles. Reutiliza `compute_evi`/`compute_ndmi` del módulo base sin redefinirlos. |
| `src/geospatial/alpine_dem.py` | **Escalado del corredor por magnitud de pendiente.** El lado de aguas abajo pasa de 60 a 80 m entre 20° y 30°; el de aguas arriba se mantiene en 15 m. |
| `src/geospatial/zonal_stats.py` | Estadística zonal poligonal sobre rásteres: reprojecta la zona al grid del ráster, rasteriza y calcula la media de píxeles válidos. Usado por el pipeline de zonas SCM reales. |
| `src/spatial_causality/alpine_causality.py` | **Zona de control emparejada por altitud.** Anillo 200–500 m intersectado con la banda DEM ±50 m del sendero. La clasificación «roderas» exige exceso de degradación **y** puerta de pendiente. |
| `src/spatial_causality/alpine_scm_zones.py` | Conecta la causalidad alpina con observaciones mensuales reales EVI/NDMI por zona, con fallback explícito `NO_VALID_CONTROL` cuando una zona carece de píxeles válidos suficientes. |
| `src/risk_engine/public_roi.py` | Tarifa TRAGSA 15,50 €/m ajustada por pendiente (×1,0→×1,8) y traducida a empleos e ingresos hosteleros dependientes. Tarifa base en `src/config/constants.py`. |
| `src/platform/alpine_trail_geoms.py` | Carga las 53 trazas cartográficas reales OAPN desde `clean_assets/sierra_nevada_trails.geojson` para el mapa PyDeck, sustituyendo el centroide+jitter de la aproximación anterior. |
| `src/platform/alpine_dashboard.py` | Constructores puros (sin Streamlit) del mapa PyDeck y la matriz TPI por temporada. |
| `src/ui/tabs/tab_alpine.py` | Superficie Streamlit: conmutador Invierno/Verano, mapa con trazas reales, simulador presupuestario (50K–1M €), matriz TPI (TIER I–IV) y tabla de indicadores municipales reales IECA/SIMA. |
| `src/socioeconomic/alpine_mapping.py` | Cruce INE Granada/Almería real para 25 municipios (sin fallback al padrón de Madrid/PNSG), con la figura de visitantes OAPN Sierra Nevada 2023. |
| `src/socioeconomic/alpine_indicators.py` | Parser de fichas SIMA «Andalucía pueblo a pueblo»: extrae indicadores reales (población, economía, inmobiliario, energía) para 24 municipios, con secreto estadístico parseado a `None`. Snapshot compilado en `src/socioeconomic/snapshot/`. |
| `src/validation/aemet_snow.py` | Cliente AEMET OpenData para la zona de montaña `nev1`: previsión nivológica en tiempo real. Requiere `AEMET_API_KEY` (registro gratuito). |
| `src/validation/cetursa_snow.py` | Cliente del «parte de nieve» de Cetursa vía el backend Umbraco (`umb.sierranevada.es/umbraco/api/parte/previsiones`), JSON sin autenticación. Extrae espesores por sector, temperaturas y riesgo de alud. `has_snow_data()` detecta la temporada cerrada (sentinel `9999`). |
| `src/validation/alpine_plots.py` | Generador determinista de parcelas BACI candidatas dentro de las zonas SCM reales, para la campaña de campo no ejecutada (issue #11). |

Ingesta NDSI y regeneración de la serie por sendero:

- `etl_raster_processor.py --territory sierra_nevada` transmite B03 + SCL y escribe `clean_S2_NDSI.tif`.
- `scripts/gee_templates_oapn/pn_sierra_nevada.js` incorpora B3/NDSI y una **máscara SCL estacional permisiva con la nieve** para regenerar la serie mensual de 53 activos en el GEE Code Editor.

---

## 4. Stack tecnológico

- **Lenguaje:** Python ≥ 3.12
- **Geoespacial:** rasterio, rasterstats, shapely, geopandas; pystac-client (STAC), Copernicus DEM GLO-30
- **Datos:** Sentinel-2 SR L2A (Copernicus); Google Earth Engine (`gee_adapter.py`, credenciales no incluidas)
- **CRS:** EPSG:25830 (ETRS89 / UTM 30N) para buffers y rásteres; EPSG:4326 para almacenamiento vectorial
- **Base de datos:** PostgreSQL / PostGIS (motor heredado)
- **API / dashboard:** FastAPI, uvicorn, Streamlit, pydeck (Deck.gl)
- **Persistencia:** SQLAlchemy 2.0 + Alembic (SQLite en dev/CI)
- **Análisis:** NumPy, pydantic; forecasting propio del motor (`src/forecasting/`)
- **Test / calidad:** pytest, pytest-cov, ruff
- **Infra:** Docker · GitHub Actions (CI)

---

## 5. Estructura del repositorio

Módulos **específicamente alpinos** marcados con 🏔; el resto es motor heredado.

```
snto-alpine/
├── README.md · ARCHITECTURE.md · CITATION.cff · requirements.txt · pyproject.toml
├── app.py                              # dashboard Streamlit (pestaña 🏔 alpina cableada)
│
├── etl_raster_processor.py             # 🏔 --territory sierra_nevada → NDSI + SCL + mosaico
├── etl_raster_intersection.py          # 🏔 SNTO_TERRITORY=sierra_nevada → buffers escalados
│
├── scripts/
│   ├── gee_templates_oapn/
│   │   └── pn_sierra_nevada.js         # 🏔 plantilla GEE con NDSI + máscara estacional
│   ├── build_alpine_snow_series.py     # 🏔 genera sierra_nevada_snow_series.{csv,json}
│   ├── build_alpine_scm_zones.py       # 🏔 genera sierra_nevada_scm_zones.{csv,json}
│   └── build_alpine_municipal_indicators.py  # 🏔 scrapa fichas SIMA → snapshot JSON
│
├── src/
│   ├── features/
│   │   ├── spectral.py                 #    NDVI/NDMI/EVI (motor)
│   │   └── alpine_spectral.py          # 🏔 NDSI, máscara estacional, cota de nieve
│   ├── geospatial/
│   │   ├── geometry.py                 #    DEM STAC, slope/aspect, buffer asimétrico (motor)
│   │   ├── alpine_dem.py               # 🏔 escalado del corredor por pendiente
│   │   └── zonal_stats.py              # 🏔 estadística zonal poligonal sobre rásteres
│   ├── spatial_causality/
│   │   ├── analyzer.py                 #    SCM base
│   │   ├── alpine_causality.py         # 🏔 control emparejado por altitud
│   │   └── alpine_scm_zones.py         # 🏔 zonas SCM reales con observaciones mensuales
│   ├── risk_engine/
│   │   └── public_roi.py               # 🏔 coste TRAGSA × pendiente + ROI socioeconómico
│   ├── platform/
│   │   ├── map_layers.py · charts.py   #    PyDeck + matriz TPI (motor)
│   │   ├── alpine_dashboard.py         # 🏔 mapa y matriz por temporada
│   │   └── alpine_trail_geoms.py       # 🏔 carga trazas OAPN reales → mapa
│   ├── socioeconomic/
│   │   ├── alpine_mapping.py           # 🏔 cruce INE andaluz + visitantes OAPN reales
│   │   ├── alpine_indicators.py        # 🏔 parser fichas SIMA, 24 municipios reales
│   │   └── snapshot/
│   │       └── sierra_nevada_municipal_indicators.json  # 🏔 snapshot IECA/SIMA compilado
│   ├── validation/
│   │   ├── aemet_snow.py               # 🏔 cliente AEMET OpenData nev1 (requiere API key)
│   │   ├── cetursa_snow.py             # 🏔 cliente Cetursa parte de nieve (sin auth)
│   │   └── alpine_plots.py             # 🏔 parcelas BACI candidatas para campaña de campo
│   ├── ui/tabs/
│   │   └── tab_alpine.py               # 🏔 pestaña «Observatorio alpino»
│   ├── config/
│   │   ├── constants.py                # 🏔 constantes NDSI/ALPINE_/TRAGSA
│   │   └── territories.py              # 🏔 TerritoryConfig sierra_nevada
│   └── ...                             #    ingestion, time_series, decision_confidence,
│                                       #    territorial, intervention, socioeconomic, ... (motor)
│
├── tests/unit/
│   ├── test_alpine_pipeline.py         # 🏔 NDSI, máscara, pendiente, atribución, ROI
│   ├── test_alpine_dashboard.py        # 🏔 rampas de color, deck, matriz, badges
│   ├── test_alpine_trail_geoms.py      # 🏔 geometrías reales OAPN
│   ├── test_alpine_scm_zones.py        # 🏔 zonas SCM con control real
│   ├── test_alpine_snow_series.py      # 🏔 serie NDSI multitemporal
│   ├── test_alpine_indicators.py       # 🏔 indicadores IECA/SIMA (secreto estadístico)
│   ├── test_aemet_snow.py              # 🏔 cliente AEMET
│   ├── test_cetursa_snow.py            # 🏔 cliente Cetursa + centinelas temporada cerrada
│   ├── test_zonal_stats.py             # 🏔 estadística zonal
│   └── ...                             #    suite heredada del motor
│
└── clean_assets/
    ├── sierra_nevada_trails.geojson          # 🏔 53 trazas OAPN reales
    ├── sierra_nevada_asset_layers.csv        # 🏔 NDSI + pendiente por activo
    ├── sierra_nevada_ndsi_manifest.csv       # 🏔 manifiesto mosaico NDSI multitesela
    ├── sierra_nevada_snow_series.{csv,json}  # 🏔 serie dic 2023–mar 2024
    ├── sierra_nevada_scm_zones.{csv,json}    # 🏔 zonas SCM reales 52/53 activos
    └── sierra_nevada_municipios_ine.csv      # 🏔 cruce INE Granada/Almería
```

---

## 6. Orden de ejecución

```bash
pip install -r requirements.txt
cp .env.example .env
```

### Verano — salud del suelo de los borreguiles

```bash
# Rásteres NDVI/NDMI/EVI de una ventana estival
python etl_raster_processor.py --territory sierra_nevada --date-range "2024-07-01/2024-09-30"

# Buffers de erosión escalados por pendiente (DEM Copernicus vía STAC)
SNTO_TERRITORY=sierra_nevada python etl_raster_intersection.py
```

### Invierno — innivación

```bash
# NDSI + SCL de una ventana invernal (activa el modo alpino automáticamente)
python etl_raster_processor.py --territory sierra_nevada --date-range "2024-01-01/2024-03-31"
# → escribe clean_S2_NDSI.tif, clean_S2_SCL.tif, clean_S2_B03_green.tif
```

### Serie de innivación multitemporal (activos comprometidos)

La capa versionada `clean_assets/sierra_nevada_snow_series.{csv,json}` contiene
la serie mensual dic 2023–mar 2024 de NDSI, cota de nieve y CI bootstrap para
52/53 activos (1 activo queda fuera de toda huella STAC — documentado en el
manifiesto). Generada con:

```bash
python scripts/build_alpine_snow_series.py
```

Para regenerar `clean_assets/sierra_nevada_asset_layers.csv` (NDSI + pendiente
de resumen por activo):

```bash
python scripts/build_alpine_asset_layers.py
```

Pega `scripts/gee_templates_oapn/pn_sierra_nevada.js` en [code.earthengine.google.com](https://code.earthengine.google.com) para ampliar la serie a temporadas adicionales.

### Dashboard

```bash
streamlit run app.py   # selecciona Sierra Nevada → pestaña «Observatorio alpino»
```

---

## 7. Tests

```bash
pytest -q
```

- **1.150+ passing, 1 skipped, 0 regresiones** — incluye todos los módulos alpinos: `test_alpine_pipeline.py`, `test_alpine_dashboard.py`, `test_alpine_trail_geoms.py`, `test_alpine_scm_zones.py`, `test_alpine_snow_series.py`, `test_alpine_indicators.py`, `test_aemet_snow.py`, `test_cetursa_snow.py`, `test_zonal_stats.py`, `test_scm_real_zones.py`, `test_real_trails_semantics.py` y `test_alpine_plots.py`, más la suite heredada y los contratos de roadmap y aislamiento de despliegue.
- CI (`ci.yml`, GitHub Actions, Python 3.12 / Ubuntu): `ruff` bloqueante sobre los módulos mantenidos —**incluidos los alpinos**—, suite con cobertura ≥ 80 %, `mypy` y un job de PostgreSQL real. El despliegue Alpine es manual, tiene doble confirmación y está deshabilitado por defecto.
- Los tests corren **offline**: STAC (`pystac-client`), `rasterio` y `pydeck` se sustituyen por stubs; el DEM se simula con transforms `affine`.

---

## 8. Honestidad sobre limitaciones

La transparencia metodológica es parte del valor académico del proyecto.

- **Cobertura invernal 52/53:** 1 activo queda fuera de la huella de todas las teselas STAC disponibles; su NDSI es `NaN` en todo el dataset, no interpolado. El manifiesto (`sierra_nevada_ndsi_manifest.csv`) lo identifica explícitamente. La serie cubre dic 2023–mar 2024 (4 meses); temporadas adicionales requieren re-ejecutar `build_alpine_snow_series.py` sobre escenas STAC nuevas.
- **Coste TRAGSA de alta montaña:** la tarifa base de 15,50 €/m es de orden de magnitud (TRAGSA 2023); el **factor de pendiente ×1,0→×1,8 es un supuesto de planificación**, no una tarifa oficial de alta montaña publicada. El buffer escalado necesita el DEM Copernicus via STAC en ejecución real.
- **Empleos e ingresos = proxy:** los campos `dependent_jobs` e `hospitality_revenue_eur` de `public_roi.py` derivan de parámetros de literatura (22,50 €/visitante, 2.500 visitantes/empleo), **no** de observación INE/Andalucía. Toda salida lleva `EvidenceClass`; una `SIMULATED` no sostiene decisión de gasto por sí sola. Las cifras de población, economía y establecimientos del contexto municipal **sí** son reales (IECA/SIMA); los empleos/ingresos del ROI **no**.
- **Fuentes de nieve sin archivo histórico:** AEMET (`nev1`) y Cetursa (Umbraco API) sólo sirven datos en tiempo real — ninguna tiene archivo histórico descargable. La verificación cruzada prospectiva con el dataset de innivación (#8) se realizará durante el invierno 2026–2027 (issue #21).
- **Sin validación de campo:** nada está contrastado sobre el terreno (penetrómetro, parcelas de cobertura, erosión medida). El protocolo BACI está diseñado (`docs/alpine_field_validation_protocol.md`), pero la campaña no se ha ejecutado (issue #11). No se afirma validación hasta que esa campaña publique resultados.

---

## 9. Fundamento científico

**Innivación (invierno).** El NDSI (Normalized Difference Snow Index, Hall et al. 1995) explota que la nieve reflecta con fuerza en el verde (B03) y absorbe casi por completo en el SWIR (B11). El umbral operativo (NDSI ≥ 0,40) marca *candidatos* de nieve; el agua comparte esa firma, de ahí el suelo de reflectancia NIR para separarlas.

**Erosión estival (verano).** Cadena causal documentada: **pisoteo / rodadura recreativa → compactación del suelo → estrés hídrico → firma espectral medible** (caída de EVI y NDMI). En terreno con pendiente, la escorrentía concentra la energía erosiva y el penacho de sedimento viaja aguas abajo (Wemple et al. 2001), lo que justifica el corredor asimétrico escalado por pendiente y la **puerta de pendiente** de la atribución: en llano el uso compacta pero no abre roderas.

Referencias clave: Hall et al. (1995); Wemple et al. (2001); Roovers et al. (2004); Pickering & Mount (2010); Marion & Leung (2001); Cole & Monz (2002).

Marco regulatorio español aplicable: Ley 42/2007 (Patrimonio Natural y Biodiversidad), Ley 26/2007 (Responsabilidad Medioambiental), TRAGSA Tarifas 2023.

---

## 10. Relación con el observatorio base

La Edición Alpina **deriva** del [observatorio base SNTO](https://github.com/soroushkarahrodi79-oss/snto-smart-tourism-observatory) y **reutiliza su motor íntegro**: EHS operacional, SCM, DCS (data quality gate), TPI y tiers, capa temporal Sentinel-2, backend persistente (`src/persistence/`, `/api/v2`), y la UI de 4 capas de decisión (Decidir · Diagnosticar · Evidenciar · Gobernar). Ese motor fue desarrollado y demostrado sobre el **Parque Nacional Sierra de Guadarrama** y otros parques de la Red OAPN.

Lo que aporta esta edición es **únicamente la capa alpina** descrita en [§2](#2-arquitectura-de-doble-temporada) y [§3](#3-módulos-de-la-edición-alpina); la pestaña «Observatorio alpino» se añade como un módulo más dentro de la capa *Diagnosticar* del motor.

**No** heredan a este repositorio: el historial de releases del base (v1.0→v2.0), su DOI de Zenodo, ni su despliegue en vivo en Azure — pertenecen al proyecto base. La documentación técnica extendida del motor (whitepaper, ADRs, notas metodológicas) vive en el repositorio base.

---

## 11. Fuentes y licencias de datos

| Fuente | Proveedor | Licencia / condiciones | Atribución requerida |
|---|---|---|---|
| Sentinel-2 L2A (NDVI/NDMI/EVI/NDSI) | ESA / Copernicus | Datos abiertos Copernicus (uso libre con atribución) | *Contiene datos Copernicus Sentinel-2 modificados* |
| DEM GLO-30 (pendiente / orientación) | Copernicus | Datos abiertos Copernicus | *Copernicus DEM — producto ESA* |
| Cartografía de sendas y rutas BTT | OAPN (Red de Parques Nacionales) / OSM | Reutilización institucional con cita · ODbL | *Cartografía OAPN — P.N. Sierra Nevada* · *© OpenStreetMap contributors* |
| Fichas municipales IECA/SIMA | Junta de Andalucía — IECA | Reutilización con cita (portal datos abiertos Junta) | *IECA — «Andalucía pueblo a pueblo», SIMA* |
| Visitantes Red de Parques Nacionales | OAPN (MITECO) | Datos públicos con atribución | *OAPN — Encuesta de visitantes SIR, 2023* |
| Pronóstico nivológico Sierra Nevada | AEMET OpenData | Uso libre con atribución (API gratuita, registro requerido) | *Agencia Estatal de Meteorología (AEMET)* |
| Parte de nieve Cetursa | Cetursa Sierra Nevada | Consumo legítimo de API pública sin autenticación | *Cetursa Sierra Nevada S.A.* |
| Cartografía ambiental y usos del suelo | Junta de Andalucía — REDIAM | Reutilización con cita | *REDIAM, Junta de Andalucía* |
| Padrón municipal, estadística de turismo | INE | Datos abiertos INE (reutilización con cita) | *Instituto Nacional de Estadística (INE)* |

El **código** se distribuye para **uso académico y de investigación**. Los **datos** pertenecen a sus proveedores y conservan sus licencias; este proyecto solo los reutiliza con la atribución indicada.

---

## 12. Licencia / uso académico

Proyecto de investigación académica desarrollado en la **Universidad Complutense de Madrid (UCM)**.

El código se distribuye para uso académico y de investigación con atribución. Ver [`LICENSE`](LICENSE). Los datos pertenecen a sus respectivos proveedores y conservan sus licencias (ver §11).

### Cómo citar

> ⚠️ **La Edición Alpina no tiene DOI propio todavía** (no se ha depositado en Zenodo; esta es la primera release, v0.1.0). Los DOI `10.5281/zenodo.20818269` y `10.5281/zenodo.21472647` pertenecen al **observatorio base**, no a este repositorio; no los uses para citar la Edición Alpina. Mientras no exista depósito, cita este repositorio por su URL y *tag* `v0.1.0`.

Para citar el **marco base** del que deriva, ver el [observatorio base](https://github.com/soroushkarahrodi79-oss/snto-smart-tourism-observatory) y su DOI de Zenodo.

Fichero de cita: [`CITATION.cff`](CITATION.cff) · Contribuciones: [`CONTRIBUTING.md`](CONTRIBUTING.md)

---

<div align="center">
<sub>SNTO Alpine Edition v0.1.0 · Python ≥ 3.12 · 1150+ tests passing · agosto 2026</sub>
</div>
