"""
SNTO Alpine Edition — AEMET OpenData mountain/snow client (issue #21)
=========================================================================
Wires the first of the two independent snow-verification sources issue #11's
protocol (``docs/alpine_field_validation_protocol.md``, §4) named but did not
integrate: AEMET's official REST API, queried for the "Sierra Nevada" mountain
zone (AEMET's own area code ``nev1``).

Two endpoints, verified against AEMET OpenData's published Swagger
documentation (``PrediccionesEspecificasApi``):

* ``GET /api/prediccion/especifica/nivologica/{area}`` — nivological
  (snow-condition) bulletin for a mountain zone.
* ``GET /api/prediccion/especifica/montaña/pasada/area/{area}/dia/{dia}`` —
  mountain weather forecast, day 0 (today) to day 3.

Both follow AEMET OpenData's standard two-step pattern: the authenticated
call (``api_key`` header) returns a small envelope naming a ``datos`` URL;
the actual payload is a second, unauthenticated GET to that URL. Both need a
free AEMET OpenData API key (register at
https://opendata.aemet.es/centrodedescargas/altaUsuario), supplied via the
``AEMET_API_KEY`` environment variable — never hardcoded, following the same
credential-gate convention as the rest of the pipeline
(:func:`src.spatial_causality.zone_loader.real_zones_exist`-style honest
absence).

**What this module deliberately does NOT do**: parse the nivological/mountain
payload into structured fields (snow depth, snowline elevation, etc.). AEMET
publishes these as free-text/bulletin-style content whose exact JSON schema
could not be verified without a live API key in the environment this was
built in — inventing a parser against an unverified schema would be worse
than not parsing at all. :func:`fetch_nivological_info` and
:func:`fetch_mountain_forecast` return the raw decoded payload; extracting
specific fields is future work once a real response has been inspected.

There is no historical-archive endpoint in this API family — only "today
+0..+3 days" forecasts and a "past 24-36h" summary. Cross-checking issue #8's
already-completed Dec 2023-Mar 2024 satellite series against AEMET is
therefore not possible retroactively through this client; it becomes useful
prospectively, run alongside a *future* winter's snow-series build.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

__all__ = [
    "AEMET_BASE_URL",
    "SIERRA_NEVADA_AREA_CODE",
    "API_KEY_ENV_VAR",
    "AemetCredentialsMissing",
    "AemetResponse",
    "has_credentials",
    "fetch_mountain_forecast",
    "fetch_nivological_info",
]

AEMET_BASE_URL = "https://opendata.aemet.es/opendata"
SIERRA_NEVADA_AREA_CODE = "nev1"  # AEMET's own mountain-zone code
API_KEY_ENV_VAR = "AEMET_API_KEY"

_MONTANA_PATH = "/api/prediccion/especifica/montaña/pasada/area/{area}/dia/{dia}"
_NIVOLOGICA_PATH = "/api/prediccion/especifica/nivologica/{area}"


class AemetCredentialsMissing(RuntimeError):
    """Raised when AEMET_API_KEY is not set — never call AEMET without one."""


@dataclass(frozen=True)
class AemetResponse:
    """A fetched AEMET OpenData payload, with enough provenance to cite it.

    ``raw`` is whatever the ``datos`` URL returned, decoded as JSON when
    possible and left as text otherwise (AEMET's older endpoints sometimes
    respond with non-JSON encodings) — see the module docstring for why this
    is not parsed further here.
    """

    endpoint: str
    area: str
    raw: Any
    fetched_at: str


def has_credentials() -> bool:
    """True when ``AEMET_API_KEY`` is set. Callers should check this before
    presenting AEMET data as available, and degrade to "sin contraste
    independiente" honestly when it isn't."""
    return bool(os.environ.get(API_KEY_ENV_VAR))


def _api_key() -> str:
    key = os.environ.get(API_KEY_ENV_VAR)
    if not key:
        raise AemetCredentialsMissing(
            f"{API_KEY_ENV_VAR} is not set. Register a free AEMET OpenData "
            "API key at https://opendata.aemet.es/centrodedescargas/altaUsuario "
            f"and export it as {API_KEY_ENV_VAR} before calling this module."
        )
    return key


def _get_envelope(url: str, api_key: str, timeout: int) -> dict:
    """Step 1: authenticated call, returns the envelope naming the data URL."""
    req = urllib.request.Request(url, headers={"api_key": api_key})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get_payload(url: str, timeout: int) -> Any:
    """Step 2: unauthenticated fetch of the actual data. JSON if it parses
    as JSON, otherwise the decoded text — AEMET does not guarantee JSON on
    every endpoint, and guessing wrong would raise rather than degrade."""
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        raw_bytes = resp.read()
    try:
        return json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return raw_bytes.decode("latin-1", errors="replace")


def _fetch_two_step(path: str, area: str, timeout: int = 20) -> AemetResponse:
    api_key = _api_key()
    url = AEMET_BASE_URL + urllib.parse.quote(path)
    envelope = _get_envelope(url, api_key, timeout)

    if envelope.get("estado") != 200 or not envelope.get("datos"):
        raise RuntimeError(
            f"AEMET OpenData did not return a data URL for {path}: {envelope}"
        )

    payload = _get_payload(envelope["datos"], timeout)
    return AemetResponse(
        endpoint=path,
        area=area,
        raw=payload,
        fetched_at=datetime.now(timezone.utc).isoformat(),
    )


def fetch_mountain_forecast(
    area: str = SIERRA_NEVADA_AREA_CODE, dia: str = "0", timeout: int = 20
) -> AemetResponse:
    """Mountain-zone weather forecast for ``area``, day ``dia`` (``"0"``-``"3"``).

    Raises:
        AemetCredentialsMissing: if ``AEMET_API_KEY`` is unset.
        RuntimeError: if AEMET's envelope carries no data URL.
    """
    path = _MONTANA_PATH.format(area=area, dia=dia)
    return _fetch_two_step(path, area, timeout)


def fetch_nivological_info(
    area: str = SIERRA_NEVADA_AREA_CODE, timeout: int = 20
) -> AemetResponse:
    """Nivological (snow-condition) bulletin for ``area``.

    Raises:
        AemetCredentialsMissing: if ``AEMET_API_KEY`` is unset.
        RuntimeError: if AEMET's envelope carries no data URL.
    """
    path = _NIVOLOGICA_PATH.format(area=area)
    return _fetch_two_step(path, area, timeout)
