# Hoja de ruta de SNTO Alpine

> **Autoridad de planificación de esta edición.** Los demás documentos de esta
> carpeta proceden del observatorio base y se conservan como referencia
> arquitectónica. Sus versiones v1.x–v3.x, despliegues y releases no describen
> el estado de SNTO Alpine.

## Punto de partida — 29 de julio de 2026

La rama `main` contiene la primera iteración funcional de la Edición Alpina:

- pipeline espectral de doble temporada;
- NDSI con máscara invernal y separación nieve/agua;
- pendiente y buffer de erosión alpino;
- causalidad emparejada por altitud y ROI público;
- 53 activos OAPN de Sierra Nevada visibles en el dashboard;
- NDSI real para 43/53 activos y pendiente Copernicus para 53/53;
- CI verde con 1.060 tests superados y 1 omitido.

La edición sigue en `0.1.0.dev0`, sin release propia, sin despliegue propio y sin
validación de campo. La posición de cada activo en la capa estacional es todavía
aproximada (centroide municipal + *jitter*), no la traza real del sendero.

## Principios de ejecución

1. Cada cifra conserva su clase de evidencia y su procedencia.
2. No se afirma validación mientras no exista contraste de campo.
3. Se completa la fidelidad geográfica antes de ampliar funciones de producto.
4. Alpine no reutiliza recursos, DOI ni numeración de releases del observatorio
   base.
5. Cada hito sale mediante PR pequeño, CI verde y revisión humana.

## Hito A — `0.1.0`: prototipo reproducible

Objetivo: convertir el estado actual en una release académica coherente y
reproducible, sin aumentar las afirmaciones científicas.

### Trabajo

- [x] Mantener el despliegue heredado deshabilitado y manual hasta que exista
  infraestructura Alpine independiente ([PR #5](https://github.com/soroushkarahrodi79-oss/snto-alpine/pull/5)).
- [x] Sincronizar README, contexto de agentes, estado de CI y limitaciones
  ([PR #5](https://github.com/soroushkarahrodi79-oss/snto-alpine/pull/5)).
- [x] Publicar este roadmap como autoridad de planificación Alpine
  ([PR #5](https://github.com/soroushkarahrodi79-oss/snto-alpine/pull/5)).
- [x] Crear el milestone
  [`Alpine 0.1.0`](https://github.com/soroushkarahrodi79-oss/snto-alpine/milestone/1)
  y convertir las tareas posteriores en issues trazables.
- [ ] Ejecutar revisión visual del dashboard en Sierra Nevada para Invierno y
  Verano ([#12](https://github.com/soroushkarahrodi79-oss/snto-alpine/issues/12)).
- [ ] Cortar la release `0.1.0` como **prototipo sin validación de campo**
  ([#12](https://github.com/soroushkarahrodi79-oss/snto-alpine/issues/12)).

### Puerta de salida

CI verde; documentación sin referencias operativas al despliegue base; cero
workflow automático de producción; limitaciones visibles en README y UI.

## Hito B — `0.2.0`: fidelidad geográfica y cobertura invernal

Objetivo: sustituir los puntos aproximados por observaciones ligadas a la
geometría real y completar el macizo.

### Trabajo

- [ ] Ingerir las trazas reales OAPN/OSM con identificador y licencia
  verificables ([#6](https://github.com/soroushkarahrodi79-oss/snto-alpine/issues/6)).
- [ ] Muestrear NDSI y pendiente sobre la traza o corredor del activo, no sobre
  centroide municipal + *jitter*.
- [ ] Componer las teselas Sentinel-2 necesarias para alcanzar cobertura NDSI
  53/53 o documentar explícitamente cualquier ausencia residual
  ([#7](https://github.com/soroushkarahrodi79-oss/snto-alpine/issues/7)).
- [ ] Incorporar varias fechas invernales y producir duración de manto, cota de
  nieve e incertidumbre, no solo una escena de febrero de 2024
  ([#8](https://github.com/soroushkarahrodi79-oss/snto-alpine/issues/8)).
- [ ] Versionar un manifiesto de procedencia por escena, tesela, fecha y método
  de agregación.

### Puerta de salida

Toda métrica cartográfica referencia una geometría real; cobertura cuantificada;
serie invernal reproducible; tests de CRS, mosaico y muestreo de corredores.

## Hito C — `0.3.0`: evidencia territorial de Sierra Nevada

Objetivo: eliminar los fallbacks territoriales y reducir los proxies que hoy
condicionan la decisión.

### Trabajo

- [ ] Ejecutar zonas SCM reales, emparejadas por altitud, para los activos que
  dispongan de geometría y cobertura suficientes ([#9](https://github.com/soroushkarahrodi79-oss/snto-alpine/issues/9)).
- [ ] Sustituir la capa socioeconómica heredada de Madrid por INE/IECA/REDIAM y
  fuentes andaluzas con fecha y licencia ([#10](https://github.com/soroushkarahrodi79-oss/snto-alpine/issues/10)).
- [ ] Incorporar al menos una fuente real de presión/aforo de visitantes.
- [ ] Recalibrar capacidad, importancia económica y accesibilidad; mantener como
  `SIMULATED` cualquier componente que siga siendo un escenario.
- [ ] Verificar que todas las pestañas degradan honestamente para Sierra Nevada
  y que ninguna muestra datos PNSG como si fueran alpinos.

### Puerta de salida

Sin datos territoriales de Madrid en vistas Alpine; SCM observado donde sea
posible; procedencia y clase de evidencia visibles de extremo a extremo.

## Hito D — `0.5.0`: puerta de validación de campo

Objetivo: medir qué relación existe realmente entre la señal remota y la
degradación/nieve observadas en Sierra Nevada.

### Trabajo

- [ ] Adaptar el protocolo de campo a borreguiles, senderos BTT y gradiente
  altitudinal de Sierra Nevada ([#11](https://github.com/soroushkarahrodi79-oss/snto-alpine/issues/11)).
- [ ] Definir parcelas co-localizadas, controles, época, instrumentos y tamaño
  mínimo de muestra antes de recoger datos.
- [ ] Registrar cobertura, compactación/erosión y evidencia fotográfica con
  coordenadas y trazabilidad.
- [ ] Contrastar EVI/NDMI/índice de degradación y SCM contra campo.
- [ ] Contrastar NDSI/cota de nieve contra una fuente independiente.
- [ ] Publicar resultados positivos o negativos con intervalos e incertidumbre.

### Puerta de salida

Dataset de campo real y auditable; métricas de concordancia publicadas; límites
y umbrales recalibrados. Hasta superar esta puerta, SNTO Alpine sigue siendo un
prototipo de apoyo a la decisión.

## Hito E — `1.0.0`: piloto validado para Sierra Nevada

Este hito solo se plantea tras la puerta de validación:

- despliegue Alpine independiente y monitorizado;
- actualización de datos reproducible;
- dossier institucional con claims limitados a la evidencia obtenida;
- release y depósito propios, sin reutilizar el DOI del observatorio base;
- plan de mantenimiento, responsables y costes operativos.

## Backlog trazable

1. ✅ Aislamiento del despliegue Alpine — [PR #5](https://github.com/soroushkarahrodi79-oss/snto-alpine/pull/5).
2. ✅ Estado, roadmap y recuento de tests — [PR #5](https://github.com/soroushkarahrodi79-oss/snto-alpine/pull/5).
3. [Geometrías reales de senderos](https://github.com/soroushkarahrodi79-oss/snto-alpine/issues/6).
4. [Cobertura NDSI multitesela 53/53](https://github.com/soroushkarahrodi79-oss/snto-alpine/issues/7).
5. [Serie multifecha de manto y cota de nieve](https://github.com/soroushkarahrodi79-oss/snto-alpine/issues/8).
6. [Zonas SCM observadas y emparejadas por altitud](https://github.com/soroushkarahrodi79-oss/snto-alpine/issues/9).
7. [Fuentes socioeconómicas andaluzas](https://github.com/soroushkarahrodi79-oss/snto-alpine/issues/10).
8. [Campaña de campo de Sierra Nevada](https://github.com/soroushkarahrodi79-oss/snto-alpine/issues/11).
9. [QA visual y release Alpine 0.1.0](https://github.com/soroushkarahrodi79-oss/snto-alpine/issues/12).

## Relación con la documentación heredada

Los planes `v1.1`, `v1.2`, `v2.0`, `v3.0` y `plan_v3_roadmap.md` explican la
evolución del motor base. Se pueden consultar para decisiones de arquitectura,
persistencia, API o gobernanza, pero **no son la secuencia de releases de esta
edición**. Cuando exista conflicto, prevalece este documento y el README Alpine.
