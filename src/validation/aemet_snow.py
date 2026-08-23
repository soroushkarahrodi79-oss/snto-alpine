"""
SNTO Alpine Edition — AEMET OpenData mountain/snow client (issue #21)
=========================================================================
Wires the first of the two independent snow-verification sources issue #11's
protocol (``docs/alpine_field_validation_protocol.md``, §4) named but did not
integrate: AEMET's official REST API, queried for the "Sierra Nevada" mountain
zone (AEMET's own area code ``nev1``).

Two endpoints, verified against AEMET OpenData's published Swagger
documentation AND against live responses from a real API key:

* ``GET /api/prediccion/especifica/montaña/pasada/area/{area}/dia/{dia}`` —
  mountain weather forecast, day 0 (today) to day 3. **Works for Sierra
  Nevada** (``nev1``) and is this module's primary function for the pilot.
* ``GET /api/prediccion/especifica/nivologica/{area}`` — avalanche-danger
  bulletin. Verified live to accept **only** ``area="0"`` (Pirineo Catalán)
  or ``area="1"`` (Pirineo Navarro y Aragonés) — ``nev1`` returns a 404
  ("el valor del parametro solo puede ser 0,1"). AEMET's official
  avalanche-bulletin network does **not** cover Sierra Nevada at all; this
  endpoint is kept here (mirroring the documented API shape faithfully) but
  is not usable for this pilot's independent snow cross-check. Use
  :func:`fetch_mountain_forecast` instead.

Both follow AEMET OpenData's standard two-step pattern: the authenticated
call (``api_key`` header) returns a small envelope naming a ``datos`` URL;
the actual payload is a second, unauthenticated GET to that URL. Both need a
free AEMET OpenData API key (register at
https://opendata.aemet.es/centrodedescargas/altaUsuario), supplied via the
``AEMET_API_KEY`` environment variable — never hardcoded, following the same
credential-gate convention as the rest of the pipeline
(:func:`src.spatial_causality.zone_loader.real_zones_exist`-style honest
absence).

:func:`parse_mountain_forecast` extracts the real structured fields verified
against a live Sierra Nevada (``nev1``) response: the free-air 0°C/-10°C
isotherm altitudes (a freezing-level reading is a meteorologically
independent proxy for whether snow could be accumulating, distinct from
Sentinel-2's spectral signal), wind aloft, and per-station min/max
temperatures at named altitudes (e.g. Pradollano 2,165 m, Borreguiles
2,665 m). It does **not** report snow depth in centimetres — this forecast
endpoint is a weather forecast, not a snowpack survey; AEMET does not
publish a numeric snow-depth product for Sierra Nevada through this API
family. Present the isotherm/temperature figures as meteorological context
alongside the satellite snowline, never as a replacement measurement of it.

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
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

__all__ = [
    "AEMET_BASE_URL",
    "SIERRA_NEVADA_AREA_CODE",
    "API_KEY_ENV_VAR",
    "AemetCredentialsMissing",
    "AemetResponse",
    "MountainPlaceReading",
    "MountainForecastSummary",
    "has_credentials",
    "fetch_mountain_forecast",
    "fetch_nivological_info",
    "parse_mountain_forecast",
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
    """A fetched AEMET OpenData payload, with enough provenance to cite it."""

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
    as JSON under either encoding AEMET is known to use, otherwise the
    decoded text — AEMET does not guarantee JSON on every endpoint (the
    nivológica bulletin, e.g., is plain prose), and guessing wrong would
    raise rather than degrade.

    AEMET's data URLs are inconsistently encoded (some UTF-8, some
    ISO-8859-15/latin-1) independently of whether the body is JSON, so both
    encodings are tried before falling back to plain text.
    """
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        raw_bytes = resp.read()

    decoded = raw_bytes.decode("utf-8", errors="replace")
    for encoding in ("utf-8", "latin-1"):
        try:
            decoded = raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
        try:
            return json.loads(decoded)
        except json.JSONDecodeError:
            pass  # not JSON under this encoding either; keep the decoded text
    return decoded


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

    Verified live for Sierra Nevada (``area="nev1"``) — this is the endpoint
    to use for this pilot. Pass the result's ``.raw`` to
    :func:`parse_mountain_forecast` for the structured fields.

    Raises:
        AemetCredentialsMissing: if ``AEMET_API_KEY`` is unset.
        RuntimeError: if AEMET's envelope carries no data URL.
    """
    path = _MONTANA_PATH.format(area=area, dia=dia)
    return _fetch_two_step(path, area, timeout)


def fetch_nivological_info(area: str, timeout: int = 20) -> AemetResponse:
    """Avalanche-danger bulletin for ``area`` — ``"0"`` (Pirineo Catalán) or
    ``"1"`` (Pirineo Navarro y Aragonés) **only**, verified live. AEMET's
    avalanche-bulletin network does not cover Sierra Nevada through this
    endpoint — do not pass ``nev1`` here; use
    :func:`fetch_mountain_forecast` for Sierra Nevada instead. No default
    ``area`` is provided, precisely so a caller cannot accidentally assume
    Sierra Nevada coverage that does not exist.

    Raises:
        AemetCredentialsMissing: if ``AEMET_API_KEY`` is unset.
        RuntimeError: if AEMET's envelope carries no data URL (includes the
            404 AEMET returns for any ``area`` outside ``{"0", "1"}``).
    """
    path = _NIVOLOGICA_PATH.format(area=area)
    return _fetch_two_step(path, area, timeout)


# ── Structured parsing (verified against a live nev1 response) ──────────────


@dataclass(frozen=True)
class MountainPlaceReading:
    """One named place's forecast min/max temperature, from the
    ``sensacion_termica`` section (e.g. Pradollano, Borreguiles)."""

    name: str
    altitude_m: Optional[float]
    min_temp_c: Optional[float]
    max_temp_c: Optional[float]


@dataclass(frozen=True)
class MountainForecastSummary:
    """Structured extract of a mountain-forecast response.

    Free-text categories (``cloud``, ``precipitation``, ``storms``,
    ``temperature_trend``, ``wind``) are kept as AEMET's own prose — they are
    forecaster judgement, not a number to reduce further. The numeric fields
    (isotherm altitudes, wind aloft, per-place temperatures) are the parts
    genuinely comparable, as context, against a satellite snowline estimate.
    """

    area: str
    forecast_name: str
    cloud: Optional[str] = None
    precipitation: Optional[str] = None
    storms: Optional[str] = None
    temperature_trend: Optional[str] = None
    wind: Optional[str] = None
    isotherm_0c_m: Optional[float] = None
    isotherm_minus10c_m: Optional[float] = None
    wind_1500m: Optional[str] = None
    wind_3000m: Optional[str] = None
    places: list[MountainPlaceReading] = field(default_factory=list)


def _first_number(text: Optional[str]) -> Optional[float]:
    """Pull the leading number out of a text field like '4600 m' -> 4600.0."""
    if not text:
        return None
    digits = "".join(c for c in text.split()[0] if c.isdigit() or c == ".")
    return float(digits) if digits else None


def parse_mountain_forecast(raw: Any) -> MountainForecastSummary:
    """Parse a :func:`fetch_mountain_forecast` payload's ``.raw`` into
    :class:`MountainForecastSummary`.

    Tolerant of missing sections/apartados — a field AEMET didn't include
    for this call is ``None``, never a fabricated placeholder. Raises only
    when ``raw`` isn't the expected list-of-one-dict shape at all (a
    genuinely different/unexpected AEMET response, worth surfacing rather
    than silently returning an empty summary).

    Args:
        raw: the parsed JSON from ``AemetResponse.raw`` — a one-element list
            containing the forecast object, per the verified live response
            shape.

    Returns:
        :class:`MountainForecastSummary`.

    Raises:
        ValueError: if ``raw`` is not a non-empty list of dicts.
    """
    if not isinstance(raw, list) or not raw or not isinstance(raw[0], dict):
        raise ValueError(
            "Expected a non-empty list of forecast objects from AEMET; "
            f"got {type(raw).__name__}"
        )
    doc = raw[0]

    sections = {s.get("nombre"): s for s in doc.get("seccion", [])}
    apartados_by_section = {
        name: {a.get("nombre"): a.get("texto") for a in sec.get("apartado", [])}
        for name, sec in sections.items()
    }

    prediccion = apartados_by_section.get("prediccion", {})
    atmosfera = apartados_by_section.get("atmosferalibre", {})

    places: list[MountainPlaceReading] = []
    for lugar in sections.get("sensacion_termica", {}).get("lugar", []):
        places.append(
            MountainPlaceReading(
                name=lugar.get("nombre", ""),
                altitude_m=_first_number(lugar.get("altitud")),
                min_temp_c=lugar.get("minima"),
                max_temp_c=lugar.get("maxima"),
            )
        )

    return MountainForecastSummary(
        area=doc.get("id", ""),
        forecast_name=doc.get("nombre", ""),
        cloud=prediccion.get("nubosidad"),
        precipitation=prediccion.get("pcp"),
        storms=prediccion.get("tormentas"),
        temperature_trend=prediccion.get("temperatura"),
        wind=prediccion.get("viento"),
        isotherm_0c_m=_first_number(atmosfera.get("isocero")),
        isotherm_minus10c_m=_first_number(atmosfera.get("iso10")),
        wind_1500m=atmosfera.get("v1500"),
        wind_3000m=atmosfera.get("v3000"),
        places=places,
    )
