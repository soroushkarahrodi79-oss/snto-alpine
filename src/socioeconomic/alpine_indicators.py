"""
SNTO Alpine Edition — real IECA/SIMA municipal indicators (issue #22)
=======================================================================
Issue #10 shipped only municipal *identity* (name → INE code) for the 25
Sierra Nevada municipalities, deliberately leaving population/economy
unsourced rather than fabricate it. This module sources the real figures
from IECA (Instituto de Estadística y Cartografía de Andalucía)'s public
"Andalucía pueblo a pueblo" municipal fact sheets — the SIMA (Sistema de
Información Multiterritorial de Andalucía) database's public-facing summary,
one page per municipality at a stable, INE-code-keyed URL::

    https://www.juntadeandalucia.es/institutodeestadisticaycartografia/sima/ficha.htm?mun=<ine_code>

Each field on that page carries its own vintage (e.g. "Población total.
2025", "Tasa municipal de desempleo (%). 2025") — IECA updates different
indicators on different cycles, so a single "snapshot date" for the whole
record would misrepresent how current each figure actually is. This module
therefore keeps the PNSG snapshot's ``provenance: dict[field, "source year"]``
convention (:class:`src.socioeconomic.models.Municipality`) rather than a
record-wide date.

Deliberately a **new** record type, not :class:`src.socioeconomic.models.Municipality`
— issue #10 already decided that reusing the ALMUDENA-shaped model would
imply a completeness Sierra Nevada doesn't have (no ALMUDENA-equivalent
tourism-employment series exists here; IECA's public sheet reports
*hostelería establishment counts* and *hotel bed capacity*, a related but
different kind of tourism indicator). Wearing the wrong model's shape would
misrepresent what was actually sourced.

Some fields are published as ``*`` — IECA's own suppression mark for small
municipalities where publishing the true figure would identify individuals
or single businesses (statistical secrecy, same caveat the PNSG snapshot
already documents for its own tiny municipalities). Those parse to ``None``
with an explicit caveat, never to a fabricated plausible number.
"""
from __future__ import annotations

import html as html_module
import json
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Optional

__all__ = [
    "SIMA_FICHA_URL",
    "AndalusianMunicipalIndicators",
    "parse_sima_ficha_html",
    "load_sierra_nevada_indicators",
]

_SNAPSHOT_PATH = (
    Path(__file__).resolve().parent
    / "snapshot" / "sierra_nevada_municipal_indicators.json"
)

SIMA_FICHA_URL = (
    "https://www.juntadeandalucia.es/institutodeestadisticaycartografia/"
    "sima/ficha.htm?mun={ine_code}"
)
SOURCE_NAME = "IECA/SIMA — Andalucía pueblo a pueblo"

# label substring (accent/case-insensitive) -> output field name.
# Matched against the ROW LABEL with its trailing ". <year>" stripped, so the
# substring never needs to include the vintage itself.
_LABEL_FIELD_MAP: tuple[tuple[str, str], ...] = (
    ("poblacion total", "population"),
    ("porcentaje de poblacion mayor de 65 anos", "pct_over_65"),
    ("variacion relativa de la poblacion en diez anos", "pop_change_10y_pct"),
    ("tasa municipal de desempleo", "unemployment_rate_pct"),
    ("seccion i. hosteleria", "hosteleria_establishments"),
    ("plazas en hoteles", "hotel_beds"),
    ("hoteles", "hotels"),
    ("renta bruta media", "gross_income_mean_eur"),
    ("renta disponible media", "disposable_income_mean_eur"),
)

_ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
_CELL_RE = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_YEAR_SUFFIX_RE = re.compile(r"\.\s*(\d{4}(?:-\d{4})?)\s*$")


def _normalize_label(label: str) -> str:
    s = unicodedata.normalize("NFKD", label)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower().strip()


def _clean_cell(raw: str) -> str:
    text = _TAG_RE.sub("", raw)
    text = html_module.unescape(text)
    text = text.replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


_SUPPRESSED_MARKERS = {"*", "-", "..", "n.d.", "n.d"}


def _parse_number(value: str) -> Optional[float]:
    """Spanish-locale number ('8.676' or '42,3') -> float, or None if suppressed."""
    v = value.strip()
    if not v or v in _SUPPRESSED_MARKERS:
        return None
    v = v.replace(".", "").replace(",", ".")
    try:
        return float(v)
    except ValueError:
        return None


@dataclass(frozen=True)
class AndalusianMunicipalIndicators:
    """Real IECA/SIMA indicators for one Sierra Nevada municipality.

    Every populated field's vintage lives in ``provenance``, keyed by field
    name (e.g. ``provenance["population"] == "IECA/SIMA 2025"``). A field
    that IECA suppressed for statistical secrecy is ``None`` with a matching
    entry in ``caveats`` — never filled with a plausible-looking guess.
    """

    ine_code: str
    population: Optional[int] = None
    pct_over_65: Optional[float] = None
    pop_change_10y_pct: Optional[float] = None
    unemployment_rate_pct: Optional[float] = None
    hosteleria_establishments: Optional[int] = None
    hotels: Optional[int] = None
    hotel_beds: Optional[int] = None
    gross_income_mean_eur: Optional[float] = None
    disposable_income_mean_eur: Optional[float] = None
    source: str = SOURCE_NAME
    source_url: str = ""
    provenance: dict[str, str] = field(default_factory=dict)
    caveats: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ine_code": self.ine_code,
            "population": self.population,
            "pct_over_65": self.pct_over_65,
            "pop_change_10y_pct": self.pop_change_10y_pct,
            "unemployment_rate_pct": self.unemployment_rate_pct,
            "hosteleria_establishments": self.hosteleria_establishments,
            "hotels": self.hotels,
            "hotel_beds": self.hotel_beds,
            "gross_income_mean_eur": self.gross_income_mean_eur,
            "disposable_income_mean_eur": self.disposable_income_mean_eur,
            "source": self.source,
            "source_url": self.source_url,
            "provenance": self.provenance,
            "caveats": self.caveats,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "AndalusianMunicipalIndicators":
        return cls(
            ine_code=d["ine_code"],
            population=d.get("population"),
            pct_over_65=d.get("pct_over_65"),
            pop_change_10y_pct=d.get("pop_change_10y_pct"),
            unemployment_rate_pct=d.get("unemployment_rate_pct"),
            hosteleria_establishments=d.get("hosteleria_establishments"),
            hotels=d.get("hotels"),
            hotel_beds=d.get("hotel_beds"),
            gross_income_mean_eur=d.get("gross_income_mean_eur"),
            disposable_income_mean_eur=d.get("disposable_income_mean_eur"),
            source=d.get("source", SOURCE_NAME),
            source_url=d.get("source_url", ""),
            provenance=d.get("provenance", {}),
            caveats=d.get("caveats", []),
        )


def parse_sima_ficha_html(
    ine_code: str, html: str
) -> AndalusianMunicipalIndicators:
    """Parse one IECA/SIMA municipal fact-sheet page into real indicators.

    Pure string parsing — no network. Rows the page doesn't have (label not
    found) simply leave that field ``None``; rows whose value is IECA's ``*``
    suppression mark parse to ``None`` with an explicit caveat. Both are
    honest "not available", never a fabricated number.

    Args:
        ine_code: the municipality's INE code (also the ``mun=`` query param
            used to fetch this page from :data:`SIMA_FICHA_URL`).
        html: the raw fetched page.

    Returns:
        :class:`AndalusianMunicipalIndicators` for this municipality.
    """
    body = re.sub(r"<script.*?</script>", "", html, flags=re.S)
    body = re.sub(r"<style.*?</style>", "", body, flags=re.S)

    values: dict[str, Optional[float]] = {}
    provenance: dict[str, str] = {}
    caveats: list[str] = []

    for row_html in _ROW_RE.findall(body):
        cells = [_clean_cell(c) for c in _CELL_RE.findall(row_html)]
        cells = [c for c in cells if c]
        if len(cells) != 2:
            continue
        label, raw_value = cells

        year_match = _YEAR_SUFFIX_RE.search(label)
        year = year_match.group(1) if year_match else None
        label_norm = _normalize_label(_YEAR_SUFFIX_RE.sub("", label))

        for needle, field_name in _LABEL_FIELD_MAP:
            if needle in label_norm and field_name not in values:
                parsed = _parse_number(raw_value)
                values[field_name] = parsed
                if parsed is not None:
                    provenance[field_name] = (
                        f"{SOURCE_NAME} {year}" if year else SOURCE_NAME
                    )
                elif raw_value.strip() in _SUPPRESSED_MARKERS:
                    caveats.append(
                        f"{field_name}: dato no publicado por IECA/SIMA "
                        f"(secreto estadístico o no disponible"
                        f"{f', {year}' if year else ''})"
                    )
                break

    def _as_int(v: Optional[float]) -> Optional[int]:
        return int(v) if v is not None else None

    return AndalusianMunicipalIndicators(
        ine_code=ine_code,
        population=_as_int(values.get("population")),
        pct_over_65=values.get("pct_over_65"),
        pop_change_10y_pct=values.get("pop_change_10y_pct"),
        unemployment_rate_pct=values.get("unemployment_rate_pct"),
        hosteleria_establishments=_as_int(values.get("hosteleria_establishments")),
        hotels=_as_int(values.get("hotels")),
        hotel_beds=_as_int(values.get("hotel_beds")),
        gross_income_mean_eur=values.get("gross_income_mean_eur"),
        disposable_income_mean_eur=values.get("disposable_income_mean_eur"),
        source_url=SIMA_FICHA_URL.format(ine_code=ine_code),
        provenance=provenance,
        caveats=caveats,
    )


@lru_cache(maxsize=1)
def load_sierra_nevada_indicators(
    path: Path | None = None,
) -> dict[str, AndalusianMunicipalIndicators]:
    """Load the committed real IECA/SIMA snapshot: ``ine_code -> indicators``.

    Returns an empty dict — never raises — when the snapshot hasn't been
    built yet (``scripts/build_alpine_municipal_indicators.py`` not run),
    so a caller can degrade to "no economic data" honestly instead of
    crashing the dashboard.
    """
    p = path or _SNAPSHOT_PATH
    if not p.exists():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    return {
        code: AndalusianMunicipalIndicators.from_dict(rec)
        for code, rec in data.get("municipalities", {}).items()
    }
