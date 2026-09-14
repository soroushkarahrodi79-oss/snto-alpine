# Estado del proyecto — SNTO Alpine Edition

> Documento canónico de estado. Generado por auditoría el **2026-09-14**. Sustituye
> a cualquier lectura de "estado actual" que se infiera de otros documentos
> (README, `CLAUDE.md`, `docs/roadmap/*`) si entran en contradicción con lo
> aquí registrado — este archivo es la fuente de verdad y debe actualizarse en
> cada cambio de estado real.

## 1. Estado a fecha de hoy (2026-09-14)

**`PAUSED_PENDING_EVIDENCE`**

La release `v0.1.0` está cortada, con CI verde y el milestone `Alpine 0.1.0`
prácticamente cerrado (8/9 issues). El único trabajo pendiente —la campaña de
validación de campo (issue [#11](https://github.com/soroushkarahrodi79-oss/snto-alpine/issues/11))—
es trabajo físico de terreno (parcelas, penetrómetro, transecto de nieve) que
**no puede ejecutarse desde este entorno**. El desarrollo de software está
efectivamente en pausa hasta que esa evidencia exista: no hay más issues
abiertas que dependan de código, y la propia issue #11 es explícitamente la
puerta de bloqueo para cualquier claim de "piloto validado" y para la release
`1.0.0`. Esto no es `MAINTENANCE_ONLY` (no hay una cola de mantenimiento
activa distinta de #11) ni `RELEASE_LOCKED` (no hay una razón editorial o de
congelación de release — el bloqueo es de evidencia), y no es `ACTIVE_BOUNDED`
(no hay desarrollo de producto en curso).

## 2. Referencia de release exacta

- **Tag de release:** [`v0.1.0`](https://github.com/soroushkarahrodi79-oss/snto-alpine/releases/tag/v0.1.0) — commit `46a50932bda19048c66dd7da76a3cbf4a82a7c19`, publicado 2026-08-23.
- **`main` actual:** commit `090d7db9bb4d408fa167fc056a27cb0081e504f7`, **5 commits por delante** del tag `v0.1.0` (`git log v0.1.0..origin/main`). Los 5 commits son exclusivamente correcciones de documentación (wording de licencia, `CITATION.cff`, cierre de QA de la issue #12) — **sin cambios funcionales, de datos ni de pipeline** respecto al código etiquetado. CI verde en ambos puntos (run [#39](https://github.com/soroushkarahrodi79-oss/snto-alpine/actions/runs/33535835782) sobre `main` actual).
- **Referencia canónica recomendada:** citar/instalar desde el tag `v0.1.0`. Tratar `main` como equivalente funcional con documentación más al día.
- No existe DOI propio (Zenodo) para esta edición — ver §4 y §7 de este documento sobre el ceiling de citación.

## 3. Qué está demostrado frente a qué es simulado, derivado, provisional o sin validar

| Clase | Contenido |
|---|---|
| **Real / demostrado** | 53/53 trazas de sendero OAPN reales (#6); mosaico NDSI multitesela real 52/53 activos (#7); serie de innivación real dic 2023–mar 2024 con CI bootstrap (#8); 52/53 zonas SCM con `evidence_class=REAL` (#9); crosswalk INE Granada/Almería real + cifra real de visitantes OAPN 2023 (#10); indicadores municipales IECA/SIMA reales para 24/24 municipios (#22, #27); AEMET OpenData y Cetursa (Umbraco API) cableados y verificados en vivo, sin autenticación falsa ni datos simulados (#21). |
| **Provisional / con supuestos declarados** | Factor de pendiente TRAGSA ×1,0→×1,8 (supuesto de planificación, no tarifa oficial publicada); buffer de erosión escalado por pendiente (implementado y testeado, requiere DEM Copernicus vía STAC en ejecución real para producción). |
| **Derivado / proxy, nunca observación directa** | Empleos dependientes e ingresos hostelería de `public_roi.py` (parámetros de literatura — 22,50 €/visitante, 2.500 visitantes/empleo — marcados `EvidenceClass=SIMULATED`, visiblemente separados de las cifras reales IECA/SIMA). |
| **Sin validar (crítico)** | **Ningún resultado de esta edición está contrastado sobre el terreno.** El protocolo BACI de validación existe (`docs/alpine_field_validation_protocol.md`) pero la campaña física **no se ha ejecutado** (#11). La verificación cruzada de invierno satélite↔AEMET/Cetursa tampoco se ha realizado (prevista invierno 2026–2027, sin archivo histórico posible retroactivamente). |
| **Motor heredado (fuera del alcance de esta auditoría)** | El motor EHS/SCM/DCS/persistencia/UI de 4 capas se heredó íntegro del observatorio base (`snto-smart-tourism-observatory`). Su historial de validación, DOI y estado de despliegue **no transfieren** a este repositorio y no se auditan aquí — ver README §10. |

## 4. Techo de reclamación (claim ceiling)

Esta edición puede describirse como: *"prototipo reproducible de la Edición
Alpina de SNTO sobre Sierra Nevada, con datos reales comprometidos para
geometría de sendero, cobertura de nieve, series temporales y contexto
socioeconómico municipal, y dos fuentes independientes de nieve cableadas y
verificadas en vivo."*

**No puede** describirse como: un "piloto validado", un sistema con
validación de campo, una release con paridad de madurez respecto al
observatorio base (ese motor tiene su propio historial v1.0→v2.0 y DOI, que
no aplican aquí), ni un despliegue en producción (no existe instancia Alpine
desplegada; el workflow de Azure es manual, deshabilitado por defecto, y
requiere doble confirmación — ver §5 de deployment safety en `CLAUDE.md`).

Cualquier redacción (README, CITATION.cff, comunicación externa) que sugiera
validación de campo, DOI propio, o estado de producción antes de que la
issue #11 publique resultados **sobreclama** respecto a la evidencia
registrada aquí.

## 5. Cambios de mantenimiento permitidos

Sin reabrir desarrollo, son admisibles:

- Correcciones de documentación, wording de licencia/citación, enlaces rotos.
- Parcheo de dependencias y CI (sin cambiar el comportamiento de los pipelines de datos).
- Arreglos de bugs que no alteren `evidence_class` ni introduzcan nuevas fuentes de datos.
- Actualización de este documento (`PROJECT_STATUS.md`) cuando cambie el estado real.
- Preparación (no ejecución) de instrumentos, protocolos o scripts para la campaña de campo de la issue #11.

**No** son mantenimiento: nuevas fuentes de datos, nuevos indicadores, cambios de UI/producto, cualquier claim nuevo de validación, o despliegue en producción.

## 6. Evidencia o necesidad para reabrir desarrollo

El desarrollo se reabre cuando ocurra cualquiera de:

1. **La campaña de campo de la issue #11 se ejecuta y publica resultados** (positivos o negativos, sin sobreafirmar) — desbloquea el trabajo de QA/release hacia `1.0.0` y cualquier claim de "piloto validado".
2. **Una necesidad de usuario concreta** (p. ej. la administración del Parque Nacional, Cetursa, o un caso de uso del TFM) solicita una funcionalidad o integración nueva con alcance definido — se abriría como issue nueva, nunca como extensión silenciosa del alcance actual.
3. **Un cambio en la disponibilidad de datos** (nuevo archivo histórico de AEMET/Cetursa, nueva escena STAC que cubra el activo sin huella) que permita cerrar una limitación ya documentada en §8 del README.

## 7. Disposición de issues y PRs abiertos

### Issues abiertos (1 de 9 en el milestone `Alpine 0.1.0`)

| # | Título | Disposición |
|---|---|---|
| [#11](https://github.com/soroushkarahrodi79-oss/snto-alpine/issues/11) | Diseñar y ejecutar la campaña de validación de campo de Sierra Nevada | **Se mantiene abierta.** El diseño (protocolo BACI) está completo; la ejecución es trabajo físico de campo que no puede realizarse desde este entorno de agente. Es la puerta de bloqueo explícita para "piloto validado" y para `1.0.0`. No requiere acción de código hasta que exista un titular humano que ejecute la campaña. |

Las 8 issues restantes del milestone (#6, #7, #8, #9, #10, #12, #21, #22, #27 — nota: son 9 títulos porque el milestone lista 9 issues totales, 8 cerradas) están **cerradas** con evidencia real comprometida; ver README §1 y `RELEASE_NOTES.md` para el detalle por issue. `CLAUDE.md` describe #12, #21 y #27 como abiertas a fecha 2026-08-23 — **eso está desactualizado**: las tres se cerraron entre el 23 y 24 de agosto de 2026. Se recomienda actualizar `CLAUDE.md` en un PR de documentación aparte (fuera del alcance de este cambio, que es mínimo y auditable).

### Pull requests abiertos

**Ninguno.** `soroushkarahrodi79-oss/snto-alpine` no tiene PRs abiertas a fecha de esta auditoría. La PR #30 (release gate de v0.1.0) y la PR #31 (curación de portfolio) están mergeadas en `main`.

## 8. Ambigüedades detectadas (reportadas, no corregidas en este cambio)

- **Contradicción de wording en `CITATION.cff`:** el campo `abstract` describe el software como *"Observatorio de inteligencia territorial de código abierto para uso académico"* ("open source... for academic use"). `LICENSE` y el badge del README son explícitos en que esto es **source-available / uso académico no comercial**, no código abierto en el sentido OSI. Esta frase del abstract debería corregirse a algo como *"de código disponible para uso académico"* — no se ha modificado aquí porque implica editar `CITATION.cff`, fuera del alcance mínimo de esta auditoría de estado.
- **`LICENSE` §2 (Datos)** enumera como fuente "ALMUDENA — Instituto de Estadística de la Comunidad de Madrid", que es la fuente del observatorio **base** (PNSG/Madrid), no de esta edición Alpina (que usa IECA/SIMA de Andalucía, según README §10 y §11 y `CLAUDE.md`). El bloque de fuentes de `LICENSE` parece no haberse actualizado tras el fork. Se reporta como inconsistencia de licencia/atribución de datos a resolver por el autor; no se ha tocado `LICENSE` en este cambio.

---

*Este archivo se genera y mantiene manualmente. Actualícese en cada cambio de
estado (nueva release, cierre de #11, apertura de una nueva issue de alcance).*
