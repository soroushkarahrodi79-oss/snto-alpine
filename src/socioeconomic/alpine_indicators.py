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
#
# ORDER MATTERS: for each row the first needle that is a substring of the label
# wins, so a more specific needle must precede a shorter one it contains
# ("plazas en hostales" before "hostales y pensiones"; the residential-energy
# needle before the total-energy one it is a superstring of). All needles below
# were checked against a real ficha (mun=18010, fetched 2026-08-23) to confirm
# they are unique and hit the intended row.
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
    # ── issue #27: richer real fields, same source (the SIMA ficha) ──────────
    # Lodging beyond hotels (completes accommodation capacity).
    ("plazas en hostales y pensiones", "hostal_pension_beds"),
    ("hostales y pensiones", "hostales_pensiones"),
    # Real-estate market pressure (second-home / tourism proxy).
    ("transacciones inmobiliarias. vivienda nueva", "real_estate_tx_new"),
    ("transacciones inmobiliarias. vivienda segunda mano", "real_estate_tx_used"),
    # Economic density.
    ("total establecimientos", "total_establishments"),
    # Land use (plural "cultivos ..." is the surface row, not the singular
    # "principal cultivo ..." rows).
    ("superficie dedicada a cultivos herbaceos", "ag_area_herbaceous_ha"),
    ("superficie dedicada a cultivos lenosos", "ag_area_woody_ha"),
    # Electricity consumption (residential needle MUST precede the total one).
    ("consumo de energia electrica residencial", "elec_consumption_residential_mwh"),
    ("consumo de energia electrica", "elec_consumption_mwh"),
    # Municipal fiscal capacity (public-investment / TRAGSA co-financing angle).
    ("ingresos por habitante", "income_per_capita_eur"),
    ("gastos por habitante", "expense_per_capita_eur"),
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
    # ── issue #27: richer real fields from the same SIMA ficha ──────────────
    hostales_pensiones: Optional[int] = None
    hostal_pension_beds: Optional[int] = None
    real_estate_tx_new: Optional[int] = None
    real_estate_tx_used: Optional[int] = None
    total_establishments: Optional[int] = None
    ag_area_herbaceous_ha: Optional[float] = None
    ag_area_woody_ha: Optional[float] = None
    elec_consumption_mwh: Optional[float] = None
    elec_consumption_residential_mwh: Optional[float] = None
    income_per_capita_eur: Optional[float] = None
    expense_per_capita_eur: Optional[float] = None
    source: str = SOURCE_NAME
    source_url: str = ""
    provenance: dict[str, str] = field(default_factory=dict)
    caveats: list[str] = field(default_factory=list)

    # Fields serialised in insertion order below; kept as a single list so
    # to_dict / from_dict can't drift out of sync with each other.
    _SERIALISED_FIELDS = (
        "population",
        "pct_over_65",
        "pop_change_10y_pct",
        "unemployment_rate_pct",
        "hosteleria_establishments",
        "hotels",
        "hotel_beds",
        "gross_income_mean_eur",
        "disposable_income_mean_eur",
        "hostales_pensiones",
        "hostal_pension_beds",
        "real_estate_tx_new",
        "real_estate_tx_used",
        "total_establishments",
        "ag_area_herbaceous_ha",
        "ag_area_woody_ha",
        "elec_consumption_mwh",
        "elec_consumption_residential_mwh",
        "income_per_capita_eur",
        "expense_per_capita_eur",
    )

    def to_dict(self) -> dict:
        d: dict = {"ine_code": self.ine_code}
        for name in self._SERIALISED_FIELDS:
            d[name] = getattr(self, name)
        d["source"] = self.source
        d["source_url"] = self.source_url
        d["provenance"] = self.provenance
        d["caveats"] = self.caveats
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "AndalusianMunicipalIndicators":
        kwargs = {name: d.get(name) for name in cls._SERIALISED_FIELDS}
        return cls(
            ine_code=d["ine_code"],
            source=d.get("source", SOURCE_NAME),
            source_url=d.get("source_url", ""),
            provenance=d.get("provenance", {}),
            caveats=d.get("caveats", []),
            **kwargs,
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
        hostales_pensiones=_as_int(values.get("hostales_pensiones")),
        hostal_pension_beds=_as_int(values.get("hostal_pension_beds")),
        real_estate_tx_new=_as_int(values.get("real_estate_tx_new")),
        real_estate_tx_used=_as_int(values.get("real_estate_tx_used")),
        total_establishments=_as_int(values.get("total_establishments")),
        ag_area_herbaceous_ha=values.get("ag_area_herbaceous_ha"),
        ag_area_woody_ha=values.get("ag_area_woody_ha"),
        elec_consumption_mwh=values.get("elec_consumption_mwh"),
        elec_consumption_residential_mwh=values.get(
            "elec_consumption_residential_mwh"
        ),
        income_per_capita_eur=values.get("income_per_capita_eur"),
        expense_per_capita_eur=values.get("expense_per_capita_eur"),
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
