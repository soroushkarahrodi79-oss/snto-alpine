# Protocolo de validación de campo — Sierra Nevada (issue #11)

> **Propósito.** Ninguna cifra de este piloto está validada en campo. Este
> documento es la mitad de "diseñar antes de medir, ejecutar después" que
> corresponde a diseño: protocolo, muestreo, controles, época, instrumentos y
> el análisis de concordancia que se aplicará a los datos una vez recogidos.
> **No es una campaña ya realizada.** Hasta que se ejecute y se publiquen sus
> resultados — sean positivos o negativos — ninguna vista de `snto-alpine`
> puede afirmar "piloto validado" y la release `1.0.0` queda bloqueada
> (issue #11, sección "Puerta").

Sierra Nevada añade dos cosas que el protocolo base (`docs/field_validation_protocol.md`,
territorio PNSG) no tenía que resolver:

1. **Doble estacionalidad.** El borreguil estival (BTT/senderismo) y la nieve
   invernal son dos fenómenos espectralmente opuestos en el mismo terreno
   (`CLAUDE.md`), así que necesitan dos sub-protocolos, no uno.
2. **Zonas SCM ya georreferenciadas.** El issue #9 ya construye, por activo,
   un corredor local (0–50 m) y un control altitud-emparejado (200–500 m,
   banda de elevación ±50 m) reales — no hay que inventar dónde emparejar
   impacto/control, hay que **muestrear dentro de esas mismas zonas**.

Reutiliza sin modificar `src/validation/field.py` y `src/validation/agreement.py`
(ver §4) y solo añade lo que faltaba: `src/validation/alpine_plots.py`
(propuesta de parcelas dentro de las zonas SCM) y
`bootstrap_spearman_ci()` en `agreement.py` (intervalo de confianza).

---

## 1. Qué se mide en campo

### 1.1 Sub-protocolo estival (borreguiles / erosión BTT)

Idéntico al protocolo base — reutiliza `FieldObservation` sin cambios:

| Variable | Instrumento / método | Campo |
|---|---|---|
| Compactación del suelo | Penetrómetro de bolsillo (MPa) | `soil_compaction_mpa` |
| Cobertura vegetal | Estimación visual en cuadrante (%) | `veg_cover_pct` |
| Erosión visible | Clase 0–3 (ninguna→severa) | `erosion_class` |
| Anchura real del sendero | Cinta métrica (m) | `trail_width_m` |
| Afluencia | Conteo / contador automático | `visitor_count` |
| Foto georreferenciada | Móvil con GPS | `photo_ref` |
| Estrato | Banda de altitud (p.ej. "2400–2600m") | `stratum` |

`degradation_index()` (0–100, convenio de estrés) es el mismo compuesto que en
PNSG. Se contrasta contra `soil_degradation_index` de
`src.features.alpine_spectral.compute_soil_degradation` (EVI+NDMI, issue #9).

### 1.2 Sub-protocolo invernal (nieve)

Nuevo — no existía en el protocolo base porque PNSG no tiene innivación
significativa. Dos variables, ambas comparables contra NDSI:

| Variable | Instrumento / método | Uso |
|---|---|---|
| Profundidad de nieve | Sonda/estaca graduada, transecto de 10 puntos por parcela | Contraste directo con NDSI (`is_snow_pixel`) |
| Presencia/ausencia de nieve | Observación binaria + foto | Validación del umbral `NDSI_SNOW_THRESHOLD=0.40` |

Las parcelas de nieve **no** siguen el diseño control-impacto de §2 — el
control-impacto de MTB no aplica a un fenómeno climático de escala regional.
En su lugar, se distribuyen a lo largo de un **transecto altitudinal** (cada
100 m de cota, desde 1.900 m hasta 3.300 m) para contrastar contra la cota de
nieve calculada por satélite (`compute_snowline_elevation`, issue #7/#8), no
contra un activo concreto.

## 2. Diseño control-impacto (BACI) — sub-protocolo estival

Igual que el protocolo base, pero las zonas ya existen en vez de tener que
definirse en campo:

- **Parcelas de impacto** — dentro del corredor local del activo (0–50 m,
  `ALPINE_LOCAL_OUTER_M`), `is_control=False`.
- **Parcelas de control** — dentro de la zona de control altitud-emparejada
  del mismo activo (200–500 m, banda ±50 m, `ALPINE_CONTROL_INNER_M`/
  `ALPINE_CONTROL_OUTER_M`), `is_control=True`. El emparejamiento por
  altitud ya está resuelto por `altitude_matched_control_zone` — el campo
  solo tiene que ir a las coordenadas propuestas.

`src/validation/alpine_plots.py::propose_baci_plots(asset_id, local_zone,
control_zone, zone_crs, stratum, n_per_zone)` toma esas dos geometrías
(las mismas que ya construye `scripts/build_alpine_scm_zones.py`) y devuelve
una lista determinista de coordenadas GPS candidatas, por zona — "parcelas
con coordenadas... definidas" sin que el equipo de campo tenga que inventar
dónde plantar el penetrómetro. Un activo cuya zona de control cayó en
`NO_VALID_CONTROL` (issue #9) simplemente no propone parcelas de control ahí
— señal honesta de que ese activo necesita geometría revisada antes de
poder emparejarse, no un error silencioso.

**Generar la lista real de parcelas** (próximo paso, no ejecutado aquí — requiere
las zonas ya calculadas por `scripts/build_alpine_scm_zones.py`):

```python
from src.validation.alpine_plots import propose_baci_plots
from src.validation.io import write_template

rows = [
    {"plot_id": p.plot_id, "asset_id": p.asset_id, "lat": p.lat, "lon": p.lon,
     "is_control": p.is_control, "stratum": p.stratum}
    for p in propose_baci_plots(asset_id, local_zone, control_zone,
                                 "EPSG:25830", stratum, n_per_zone=4)
]
write_template("clean_assets/sierra_nevada_field_plots_template.csv", rows)
```

## 3. Época e instrumentos

| Sub-protocolo | Ventana | Justificación |
|---|---|---|
| Estival (borreguil) | Julio–agosto | Coincide con el pico de EVI/NDMI usado por issue #9 y con el pico de visitas BTT (OAPN: julio+agosto = mayor afluencia estacional en Sierra Nevada, ver `sierra_nevada_visitor_pressure()`, issue #10) |
| Invernal (nieve) | Enero–febrero | Coincide con las escenas de mayor cobertura de nieve usadas en issue #7/#8 (diciembre-marzo, con enero/febrero como núcleo de manto estable) |

Instrumentos: penetrómetro de bolsillo, cinta métrica, sonda de nieve
graduada, GPS (móvil con precisión ≤5 m es suficiente dado que las zonas SCM
tienen escala de decenas de metros), cámara con geoetiquetado.

## 4. Fuente independiente para contraste de nieve/cota

Criterio de aceptación explícito de #11. Dos fuentes reales, verificables,
distintas de Sentinel-2/NDSI:

1. **AEMET OpenData** (`opendata.aemet.es`) — API REST oficial y gratuita
   (registro con API key). Publica predicción y boletín de montaña para la
   zona "Sierra Nevada" (`nev1`), incluyendo temperatura y precipitación en
   altura — sirve para corroborar si hubo o no precipitación en forma de
   nieve en la ventana de la escena satelital, y como fuente climatológica
   independiente para la cota de nieve regional. **No** es del mismo sensor
   que Sentinel-2, por lo que un acuerdo entre ambos no es circular.
2. **Boletín de nieve de Cetursa** (estación de esquí Sierra Nevada) —
   publica a diario, en temporada, el espesor de nieve en base y cota
   máxima/mínima de la estación. Es un dato de terreno real (varillas de
   nieve, no satelital) pero **cubre solo el dominio esquiable** (vertiente
   norte, ~2.100–3.300 m) — no vale como control de todo el macizo, solo
   como contraste puntual en esa franja.

Ninguna de las dos está todavía integrada en `snto-alpine` (ambas requieren
credenciales/scraping que no forman parte de este pase) — se documentan como
la fuente a usar, no como un dato ya cargado. Wiring real queda para cuando
se ejecute la campaña, siguiendo el mismo patrón `real_zones_exist()` /
`load_real_zones()` que ya usa `src/spatial_causality/zone_loader.py`: un
gate honesto que degrada a "sin contraste independiente" en vez de fingir
uno.

## 5. Métricas de concordancia (`src/validation/agreement.py`)

Las mismas dos que en PNSG, sin modificar, más el intervalo de confianza que
pedía la AC de #11:

1. **Correlación satélite↔terreno** — `validate_satellite_vs_field(pairs)`,
   Spearman entre `soil_degradation_index` satelital y `degradation_index()`
   de campo en parcelas co-localizadas. ρ ≥ 0,6 ⇒ concordancia fuerte.
2. **Intervalo de confianza** — `bootstrap_spearman_ci(pairs)` (nuevo,
   issue #11): bootstrap i.i.d. (reutiliza `block_bootstrap_ci` con
   `block_len=1` — las parcelas son una muestra transversal, no una serie
   temporal, así que un bootstrap por bloques de longitud 1 es exactamente
   el bootstrap i.i.d. correcto, sin añadir una segunda implementación).
   Degenera honestamente a un intervalo puntual por debajo de 4 parcelas,
   igual que el resto de intervalos de confianza del proyecto
   (`snowline_series_ci`, issue #8).
3. **Contraste control-impacto** — `control_impact_contrast(impact, control)`,
   delta de Cliff. δ ≥ 0,474 ⇒ efecto grande.

## 6. Tamaño muestral mínimo y límites

- Mínimo **3 parcelas co-localizadas** por régimen (estival/invernal) para
  que Spearman tenga sentido — igual que el protocolo base.
- Campaña piloto mínima defendible: **≥ 8 parcelas impacto + ≥ 8 control**
  por cada uno de 3–5 activos representativos (uno por franja altitudinal:
  ~2.000 m, ~2.400 m, ~2.800 m), más **≥ 10 puntos** en el transecto de
  nieve. Esto es un piso para un primer ciclo, no la campaña completa.
- Campaña completa (recomendada antes de cualquier claim "validado a nivel
  de macizo"): ≥ 15–20 parcelas impacto + control por activo, cubriendo
  ambas vertientes (Granada y Almería) y los tres tipos de terreno del
  slope gate (`ALPINE_STEEP_SLOPE_DEG=20°` como corte).
- Un solo ciclo Control-Impact **no** sostiene afirmaciones de tendencia
  temporal — confirma la *relación* satélite↔degradación en un momento dado,
  no la evolución.

## 7. Publicación honesta (sin sobreafirmar)

Por mandato de la AC y de los no-negociables de `CLAUDE.md`:

- El resultado se publica **exista o no** concordancia — un ρ bajo o un
  efecto pequeño es un hallazgo válido (posiblemente indica que el índice
  necesita recalibración, no que el campo "falló").
- Cada figura publicada debe llevar su intervalo (`bootstrap_spearman_ci`)
  y su `n` — nunca un punto suelto.
- Mientras issue #11 no se cierre, cualquier mención a "piloto validado" en
  documentación, dashboard o comunicación externa es una sobreafirmación y
  debe eliminarse o matizarse como "no validado en campo" (redacción ya
  usada en `territories.py`'s `notes` para `sierra_nevada`).

---

*Documento de protocolo · SNTO Alpine Edition · issue #11 · territorio Sierra
Nevada. Diseño únicamente — la ejecución de la campaña y la publicación de
resultados quedan pendientes.*
