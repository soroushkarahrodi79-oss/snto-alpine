"""
SNTO Alpine Edition — Cetursa "parte de nieve" client (issue #21)
=================================================================
Wires the second of the two independent snow-verification sources issue #11's
protocol (``docs/alpine_field_validation_protocol.md``, §4) named but did not
integrate: Cetursa's daily ski-resort snow bulletin for the Sierra Nevada
skiable domain (vertiente norte, ~2.100-3.300 m). Unlike Sentinel-2's spectral
signal, these are ground readings (varillas de nieve) — an independent
cross-check, not a circular one — but they cover **only the skiable domain**,
not the whole massif, so they are a point contrast in that elevation band, never
a control for the entire pilot.

How this was wired (and why the earlier "not wireable" verdict was wrong)
------------------------------------------------------------------------
The public page (``sierranevada.es/.../parte-nieve/``) is a client-rendered
Next.js SPA, so a plain fetch of *that URL* returns HTML with no snow numbers —
which is what an earlier investigation observed. But the SPA does not compute
the parte itself; it fetches it from Cetursa's own Umbraco backend:

    GET https://umb.sierranevada.es/umbraco/api/parte/previsiones?culture=es

That endpoint returns clean, **unauthenticated** JSON and was verified live
(HTTP 200) from a plain ``urllib`` request with no browser, no headless
rendering, no cookies and no API key. So the honest finding is the opposite of
"needs headless rendering": the backend API is directly and cleanly consumable.
No credential gate is needed here (contrast :mod:`src.validation.aemet_snow`,
which does need ``AEMET_API_KEY``).

What it returns, and the honest-absence handling
------------------------------------------------
The payload carries two partes — ``"Hoy"`` (today) and ``"Previsión"`` — each
with a ``partenieve`` object holding ``general`` (fecha/hora/aviso),
``estadoestacion`` (``"Abierta"``/``"Cerrada"``), ``nieve`` (per-sector snow
depths and quality) and ``meteorologia`` (per-station temperatures, wind,
avalanche-risk index). Out of season the station is ``Cerrada`` and Cetursa
fills the snow fields with sentinels rather than measurements:

* ``espesorminimo == "9999"`` and empty-string sector espesores mean "no
  reading" — they parse to ``None`` here, **never** a fabricated 0 cm, matching
  the project's honest-fallback convention (:func:`has_snow_data` degrades
  cleanly, analogous to :func:`src.validation.aemet_snow.has_credentials`).
* ``superficieinnivada`` (e.g. ``"1143 km2."``) is a static description of the
  domain's snowmaking/skiable extent that is present year-round *including when
  the station is closed*. It is therefore **not** a live snow-covered-area
  measurement and must not be cross-checked against a satellite snow-area
  figure. It is parsed and exposed for completeness, but flagged by
  ``estacion_abierta`` so a consumer never mistakes a closed-season figure for a
  measurement.

The genuinely satellite-comparable ground truth is the per-sector snow depth in
centimetres (:attr:`CetursaSnowReport.stations`), available only in open season,
scoped to the skiable domain's elevation band.

Like AEMET's forecast family, this endpoint serves only the current parte plus a
short-range forecast — there is no historical archive — so a retroactive
cross-check against issue #8's already-closed Dec 2023-Mar 2024 satellite series
is not possible through it. It becomes useful prospectively, run alongside a
future winter's snow-series build.
"""
from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

__all__ = [
    "CETURSA_PARTE_URL",
    "CETURSA_PUBLIC_PAGE",
    "SNOW_SECTORS",
    "CetursaResponse",
    "StationSnowReading",
    "CetursaSnowReport",
    "fetch_snow_report",
    "parse_snow_report",
    "has_snow_data",
]

# Cetursa's Umbraco backend — the JSON the public SPA itself consumes.
CETURSA_PARTE_URL = (
    "https://umb.sierranevada.es/umbraco/api/parte/previsiones?culture=es"
)
# The human-facing page, kept for citation/provenance (not fetched).
CETURSA_PUBLIC_PAGE = (
    "https://sierranevada.es/es/invierno/la-estacion/en-directo/parte-nieve/"
)

# Per-sector snow-depth keys in the ``nieve`` object, with the resort's own
# display names for the ones that are unambiguous. Sectors without a confident
# display name fall back to a title-cased key rather than an invented label.
SNOW_SECTORS: dict[str, str] = {
    "veleta": "Veleta",
    "laguna": "Laguna de las Yeguas",
    "borreguiles": "Borreguiles",
    "lomadilar": "Loma de Dílar",
    "parador": "Parador",
    "rio": "Río",
}

# ``espesorminimo`` uses this as an out-of-service sentinel, not a measurement.
_ESPESOR_CLOSED_SENTINEL = "9999"


class CetursaUnavailable(RuntimeError):
    """Raised when Cetursa's backend returns no usable parte payload."""


@dataclass(frozen=True)
class CetursaResponse:
    """A fetched Cetursa parte payload, with enough provenance to cite it."""

    url: str
    raw: Any
    fetched_at: str


@dataclass(frozen=True)
class StationSnowReading:
    """One skiable-domain sector's snow depth and quality.

    ``espesor_cm`` is ``None`` when the sector has no reading (empty field or
    the closed-season sentinel), never a fabricated 0.
    """

    sector: str
    display_name: str
    espesor_cm: Optional[float]
    calidad: Optional[str]


@dataclass(frozen=True)
class CetursaSnowReport:
    """Structured extract of one parte (``"Hoy"`` by default).

    Free-text/categorical fields are kept as Cetursa's own strings. Numeric
    fields are parsed to floats, with sentinels/empties collapsed to ``None``.
    ``estacion_abierta`` gates whether the snow figures are live measurements at
    all — out of season they are placeholders, not readings.
    """

    parte_name: str
    fecha: Optional[str] = None
    hora: Optional[str] = None
    estado_estacion: Optional[str] = None
    estacion_abierta: bool = False
    aviso: Optional[str] = None
    espesor_min_cm: Optional[float] = None
    espesor_max_cm: Optional[float] = None
    calidad_nieve: Optional[str] = None
    # Present year-round (incl. closed) — a domain descriptor, NOT a live
    # snow-covered-area measurement. Do not cross-check against satellite area.
    superficie_innivada_km2: Optional[float] = None
    riesgo_aludes: Optional[int] = None
    temp_pradollano_c: Optional[float] = None
    temp_borreguiles_c: Optional[float] = None
    temp_veleta_c: Optional[float] = None
    stations: list[StationSnowReading] = field(default_factory=list)


def _clean(value: Any) -> Optional[str]:
    """Strip a string field; return ``None`` for empty/whitespace-only/absent."""
    if not isinstance(value, str):
        return value if value is not None else None
    stripped = value.strip()
    return stripped or None


def _leading_number(value: Any) -> Optional[float]:
    """Pull the leading number out of a field like '1143 km2.' -> 1143.0 or
    '35     ' -> 35.0. Returns ``None`` when there is no number."""
    text = _clean(value)
    if text is None:
        return None
    digits = ""
    for ch in text:
        if ch.isdigit() or (ch == "." and digits):
            digits += ch
        elif ch in "-" and not digits:
            digits += ch
        elif digits:
            break
    if digits in ("", "-", "."):
        return None
    try:
        return float(digits)
    except ValueError:
        return None


def _espesor_cm(value: Any) -> Optional[float]:
    """Parse a snow-depth field to centimetres, collapsing the closed-season
    sentinel and empty fields to ``None`` (honest absence, never a fake 0)."""
    text = _clean(value)
    if text is None or text == _ESPESOR_CLOSED_SENTINEL:
        return None
    return _leading_number(text)


def _merged_meteo(partenieve: dict) -> dict:
    """Flatten ``meteorologia.paginas.pagina`` (a list of pages with disjoint
    keys) into a single dict, so lookups don't depend on page ordering."""
    merged: dict[str, Any] = {}
    meteo = partenieve.get("meteorologia") or {}
    paginas = (meteo.get("paginas") or {}).get("pagina") or []
    if isinstance(paginas, dict):  # single-page payloads may not be a list
        paginas = [paginas]
    for page in paginas:
        if isinstance(page, dict):
            merged.update(page)
    return merged


def fetch_snow_report(timeout: int = 20) -> CetursaResponse:
    """Fetch Cetursa's parte JSON from its Umbraco backend.

    A single plain, unauthenticated GET — no API key, no browser. Pass the
    result's ``.raw`` to :func:`parse_snow_report`.

    Raises:
        CetursaUnavailable: if the response is not the expected
            ``{"Partes": [...]}`` shape.
        urllib.error.URLError / socket.timeout: on network failure (surfaced,
            not swallowed, so a caller degrades honestly to "sin contraste").
    """
    req = urllib.request.Request(
        CETURSA_PARTE_URL,
        headers={"Accept": "application/json", "User-Agent": "snto-alpine/0.1"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = json.loads(resp.read().decode("utf-8"))

    if not isinstance(raw, dict) or not isinstance(raw.get("Partes"), list):
        raise CetursaUnavailable(
            f"Cetursa backend returned an unexpected shape from {CETURSA_PARTE_URL}"
        )
    return CetursaResponse(
        url=CETURSA_PARTE_URL,
        raw=raw,
        fetched_at=datetime.now(timezone.utc).isoformat(),
    )


def parse_snow_report(
    raw: Any, parte_name: str = "Hoy"
) -> CetursaSnowReport:
    """Parse a :func:`fetch_snow_report` payload's ``.raw`` into a
    :class:`CetursaSnowReport`.

    Tolerant of missing sections — a field Cetursa didn't include is ``None``,
    never a fabricated placeholder. Snow-depth sentinels/empties collapse to
    ``None``.

    Args:
        raw: parsed JSON from :attr:`CetursaResponse.raw` — a dict with a
            ``"Partes"`` list.
        parte_name: which parte to extract (``"Hoy"`` or ``"Previsión"``).

    Returns:
        :class:`CetursaSnowReport`.

    Raises:
        ValueError: if ``raw`` isn't the expected ``{"Partes": [...]}`` shape,
            or the requested parte isn't present.
    """
    if not isinstance(raw, dict) or not isinstance(raw.get("Partes"), list):
        raise ValueError(
            "Expected a dict with a 'Partes' list from Cetursa; "
            f"got {type(raw).__name__}"
        )

    parte = next(
        (
            p
            for p in raw["Partes"]
            if isinstance(p, dict) and p.get("Name") == parte_name
        ),
        None,
    )
    if parte is None:
        available = [p.get("Name") for p in raw["Partes"] if isinstance(p, dict)]
        raise ValueError(
            f"Parte {parte_name!r} not present in Cetursa payload; got {available}"
        )

    partenieve = (parte.get("Parte") or {}).get("partenieve") or {}
    general = partenieve.get("general") or {}
    nieve = partenieve.get("nieve") or {}
    meteo = _merged_meteo(partenieve)

    estado = _clean(partenieve.get("estadoestacion"))
    abierta = bool(estado) and estado.lower() != "cerrada"

    stations: list[StationSnowReading] = []
    for sector, display in SNOW_SECTORS.items():
        espesor = nieve.get(f"espesor{sector}")
        calidad = nieve.get(f"calidad{sector}")
        # Only emit a sector Cetursa actually lists (keys present in payload).
        if f"espesor{sector}" not in nieve and f"calidad{sector}" not in nieve:
            continue
        stations.append(
            StationSnowReading(
                sector=sector,
                display_name=display,
                espesor_cm=_espesor_cm(espesor),
                calidad=_clean(calidad),
            )
        )

    riesgo = _leading_number(meteo.get("riesgoavalancha"))

    # Closed season reports the pair (espesorminimo "9999", espesormaximo "0").
    # When the minimum is the sentinel, the station is reporting no snowpack, so
    # the paired "0" maximum is a sentinel too — not a measured 0 cm.
    min_is_sentinel = (
        _clean(nieve.get("espesorminimo")) == _ESPESOR_CLOSED_SENTINEL
    )
    espesor_max = (
        None if min_is_sentinel else _espesor_cm(nieve.get("espesormaximo"))
    )

    return CetursaSnowReport(
        parte_name=parte_name,
        fecha=_clean(general.get("fecha")),
        hora=_clean(general.get("hora")),
        estado_estacion=estado,
        estacion_abierta=abierta,
        aviso=_clean(general.get("textoprevisionapertura")),
        espesor_min_cm=_espesor_cm(nieve.get("espesorminimo")),
        espesor_max_cm=espesor_max,
        calidad_nieve=_clean(nieve.get("calidadnieve")),
        superficie_innivada_km2=_leading_number(nieve.get("superficieinnivada")),
        riesgo_aludes=int(riesgo) if riesgo is not None else None,
        temp_pradollano_c=_leading_number(meteo.get("temperaturapradollano")),
        temp_borreguiles_c=_leading_number(meteo.get("temperaturaborreguiles")),
        temp_veleta_c=_leading_number(meteo.get("temperaturaveleta")),
        stations=stations,
    )


def has_snow_data(report: CetursaSnowReport) -> bool:
    """True when the parte carries at least one real snow-depth measurement.

    Callers should check this before presenting Cetursa as an active
    cross-check, and degrade honestly to "estación cerrada, sin espesores que
    contrastar" out of season — analogous to
    :func:`src.validation.aemet_snow.has_credentials`.
    """
    if report.espesor_max_cm is not None or report.espesor_min_cm is not None:
        return True
    return any(s.espesor_cm is not None for s in report.stations)
