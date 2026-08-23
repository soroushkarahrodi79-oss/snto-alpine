# Release Notes — Alpine Edition v0.1.0

**Fecha:** 2026-08-23
**Hito:** `Alpine 0.1.0` — Prototipo reproducible

---

## Qué es esta release

`v0.1.0` cierra el hito *Alpine 0.1.0: prototipo reproducible*. No es un sistema validado en campo ni un producto en producción — es la primera versión con datos reales comprometidos y pipeline reproducible sobre el **Parque Nacional de Sierra Nevada**.

Esta edición **no** hereda el linaje de versiones (v1.0→v2.0), el DOI de Zenodo ni el despliegue en Azure del observatorio base del que deriva.

---

## Qué está real y comprometido

| Issue | Resultado |
|---|---|
| #6 — Geometrías reales de sendero | 53/53 trazas OAPN reales en `clean_assets/sierra_nevada_trails.geojson` |
| #7 — Mosaico NDSI multitesela | 52/53 activos cubiertos (30SVF/30SWF/30SVG/30SWG); 1 activo documentado como fuera de toda huella STAC |
| #8 — Serie de innivación multitemporal | Serie mensual dic 2023–mar 2024 con CI bootstrap en `sierra_nevada_snow_series.{csv,json}` |
| #9 — Zonas SCM reales | 52/53 activos con `evidence_class=REAL`; 1 con `NO_VALID_CONTROL` explícito |
| #10 — Cruce INE andaluz + visitantes OAPN | Cruce Granada/Almería real para 25 municipios; ≈734.295 visitantes OAPN 2023 (cifra real, no proxy) |
| #21 — Fuentes de nieve independientes | AEMET OpenData `nev1` y Cetursa parte de nieve (Umbraco JSON) ambos cableados y verificados en vivo (2026-08-23) |
| #22 — Indicadores IECA/SIMA | Población, economía y estadística real para 24/24 municipios; secreto estadístico (`*`) → `None`, no a cero |
| #27 — Indicadores IECA/SIMA enriquecidos | Más campos reales de la misma ficha SIMA: establecimientos, transacciones inmobiliarias, consumo eléctrico, ingresos/gastos per cápita, hostales |

---

## Qué NO está en esta release

- **Validación de campo (issue #11):** el protocolo BACI está diseñado pero la campaña física (parcelas, penetrómetro, transecto de nieve) **no se ha ejecutado**. Ningún resultado de esta edición está contrastado sobre el terreno.
- **Despliegue en producción:** no existe instancia Alpine en Azure ni en ningún otro proveedor. El workflow de despliegue es manual y está deshabilitado por defecto.
- **Verificación cruzada de invierno (issue #21):** AEMET y Cetursa no sirven archivo histórico — la correlación con la serie #8 (dic 2023–mar 2024) no es retroactivamente posible; está prevista durante el invierno 2026–2027.
- **DOI propio:** no se ha depositado en Zenodo. Citar por URL + tag `v0.1.0`.

---

## Tests

1.150+ tests superados, 1 omitido, 0 regresiones. Suite completa incluyendo los módulos alpinos nuevos.

---

## Cómo citar

> Karahrodi, S. (2026). *SNTO — Alpine Edition v0.1.0* [software]. GitHub. https://github.com/soroushkarahrodi79-oss/snto-alpine · tag `v0.1.0`
