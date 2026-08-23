# Despliegue de SNTO Alpine

La Edición Alpina **no tiene un despliegue propio activo**. El workflow
`.github/workflows/deploy-azure-container-apps.yml` se conserva como plantilla,
pero es manual y queda deshabilitado por defecto.

Esta separación es deliberada: el repositorio deriva del observatorio base,
pero no debe desplegarse sobre sus recursos, su dominio ni su imagen.

## Estado seguro por defecto

- Los merges a `main` ejecutan únicamente CI.
- El workflow de Azure solo admite `workflow_dispatch`.
- El job se omite salvo que la variable de repositorio
  `SNTO_ALPINE_DEPLOY_ENABLED` valga exactamente `true`.
- La ejecución manual exige escribir `alpine-production`.
- Los nombres esperados son exclusivos de Alpine:
  `rg-snto-alpine-app`, `snto-alpine` y la imagen `snto-alpine`.

No copies en este repositorio los secretos del observatorio base sin haber
provisionado primero un destino Alpine independiente.

## Requisitos para habilitarlo

1. Crear un Resource Group dedicado: `rg-snto-alpine-app`.
2. Crear un Azure Container App dedicado: `snto-alpine`, con puerto 8501.
3. Crear o seleccionar un ACR y conceder acceso exclusivamente al flujo Alpine.
4. Crear una identidad administrada y una credencial federada cuyo `subject`
   sea:

   ```text
   repo:soroushkarahrodi79-oss/snto-alpine:ref:refs/heads/main
   ```

5. Configurar estos secretos del repositorio:

   - `ACR_LOGIN_SERVER`
   - `ACR_USERNAME`
   - `ACR_PASSWORD`
   - `AZURE_CLIENT_ID`
   - `AZURE_TENANT_ID`
   - `AZURE_SUBSCRIPTION_ID`

6. Añadir la variable `SNTO_ALPINE_DEPLOY_ENABLED=true` solo después de revisar
   que todos los identificadores pertenecen al entorno Alpine.
7. Ejecutar CI sobre el commit que se desea publicar y confirmar que está verde.
8. Lanzar manualmente **Deploy Alpine to Azure Container Apps** e introducir
   `alpine-production`.

## Verificación

El workflow crea una imagen inmutable etiquetada con los primeros ocho
caracteres del SHA y comprueba:

```text
https://<fqdn-alpine>/_stcore/health
```

La respuesta esperada es HTTP 200. Además debe hacerse una revisión visual de:

- selector de territorio Sierra Nevada;
- pestaña «Observatorio alpino»;
- conmutación Invierno/Verano;
- 53 activos en el mapa;
- rampa NDSI parcial y rampa de pendiente;
- mensajes de procedencia y limitaciones.

## Rollback

Cada despliegue genera una revisión nueva con una etiqueta de imagen por SHA.
Para volver a una versión anterior, selecciona la última imagen Alpine conocida
como correcta y crea una revisión nueva de `snto-alpine`. No reutilices una
imagen o revisión de `snto-observatory`.

## Datos y backend

El primer despliegue Alpine debe tratarse como demo académica. Los rásteres
pesados se generan offline y no se incluyen en la imagen; el dashboard consume
las capas ligeras versionadas en `clean_assets/`. PostgreSQL, `/api/v2` y los
recursos productivos del observatorio base no se consideran desplegados para
esta edición hasta que exista una decisión y una infraestructura propias.

La secuencia y sus puertas de salida se mantienen en
[`docs/roadmap/alpine-v0.1.md`](docs/roadmap/alpine-v0.1.md).
