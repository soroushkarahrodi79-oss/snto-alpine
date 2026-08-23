"""
SNTO Alpine Edition — Sierra Nevada municipal crosswalk (issue #10)
====================================================================
The base socioeconomic module (:mod:`src.socioeconomic.mapping` /
:mod:`src.socioeconomic.loader`) resolves ``TerritorialAsset.region`` against
ALMUDENA/INE data for the 34 municipalities of the **Comunidad de Madrid**
side of the PNSG pilot. Sierra Nevada is in Granada and Almería (Andalucía);
none of its 25 real municipalities are in that crosswalk, and ALMUDENA does
not cover them at all — Madrid's Banco de Datos Municipal is a regional
statistical office with no Andalusian mandate.

This module is the Sierra Nevada counterpart: a crosswalk from the region
names already assigned by :mod:`src.territorial.alpine_fixtures` (25 real
municipalities across Granada and Almería, plus non-municipal park features
such as "Refugio Poqueira") to their official INE municipal codes.

Unlike the PNSG snapshot, this ships **identity only** — no ALMUDENA-shaped
population/tourism/economy figures. IECA (Instituto de Estadística y
Cartografía de Andalucía) publishes municipal statistics for Granada/Almería,
but sourcing and curating a dated, licensed snapshot for 25 small mountain
municipalities is out of scope for this pass; fabricating plausible-looking
numbers would be worse than reporting none. What this module guarantees is
narrower but load-bearing: every Sierra Nevada asset's municipality resolves
to its **real** Andalusian INE code, so nothing here can be confused with — or
silently fall back to — a Madrid/PNSG municipality.

Crosswalk source: the official INE municipal code list (Instituto Nacional de
Estadística, "Relación de municipios y sus códigos"), verified against a
direct byte-for-byte fetch of the current codelist — not transcribed from a
summary. See ``clean_assets/sierra_nevada_municipios_ine.csv``.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

from src.config.constants import (
    ALPINE_OAPN_RED_TOTAL_VISITORS,
    ALPINE_OAPN_REPORT_YEAR,
    ALPINE_OAPN_SIERRA_NEVADA_SHARE_PCT,
)
from src.socioeconomic.mapping import normalize_name

_ROOT = Path(__file__).resolve().parents[2]
CROSSWALK_PATH = _ROOT / "clean_assets" / "sierra_nevada_municipios_ine.csv"

__all__ = [
    "SierraNevadaMunicipio",
    "MunicipalContext",
    "load_sierra_nevada_crosswalk",
    "resolve_region_to_ine",
    "sierra_nevada_visitor_pressure",
    "build_municipal_context",
]


@dataclass(frozen=True)
class SierraNevadaMunicipio:
    """A real Andalusian municipality's identity — no economic data attached.

    Deliberately not :class:`src.socioeconomic.models.Municipality`: that
    dataclass's optional fields default to ``None`` but its shape still
    implies "an ALMUDENA-style record for which some fields are unpopulated".
    This one only ever claims identity, which is honest about what has
    actually been sourced.
    """

    ine_code: str
    name: str
    province: str  # "Granada" | "Almería"
    notes: str = ""


@lru_cache(maxsize=1)
def load_sierra_nevada_crosswalk(
    path: Path | None = None,
) -> tuple[SierraNevadaMunicipio, ...]:
    """Load the real Granada/Almería municipality crosswalk."""
    p = path or CROSSWALK_PATH
    rows: list[SierraNevadaMunicipio] = []
    with open(p, encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            rows.append(
                SierraNevadaMunicipio(
                    ine_code=(r.get("ine_code") or "").strip(),
                    name=(r.get("name") or "").strip(),
                    province=(r.get("province") or "").strip(),
                    notes=(r.get("notes") or "").strip(),
                )
            )
    return tuple(rows)


def resolve_region_to_ine(
    region: str, crosswalk: tuple[SierraNevadaMunicipio, ...] | None = None
) -> Optional[SierraNevadaMunicipio]:
    """Resolve an ``asset.region`` value to its real Andalusian municipality.

    ``None`` for anything that is not one of the 25 real municipalities —
    the massif-wide default region ("Sierra Nevada") and non-municipal park
    features (refuges, named crags) included. A caller must not paper over
    that ``None`` with a Madrid/PNSG lookup; it means "no municipality", not
    "data missing".
    """
    rows = crosswalk if crosswalk is not None else load_sierra_nevada_crosswalk()
    target = normalize_name(region)
    for row in rows:
        if normalize_name(row.name) == target:
            return row
    return None


@dataclass(frozen=True)
class MunicipalContext:
    """Coverage summary + the one real visitor-pressure figure, for the dashboard."""

    n_assets: int
    n_resolved: int
    n_municipios: int
    provinces: tuple[str, ...]
    unresolved_regions: tuple[str, ...]
    oapn_report_year: int
    oapn_sierra_nevada_visitors_estimate: int
    oapn_sierra_nevada_share_pct: float
    oapn_red_total_visitors: int


def sierra_nevada_visitor_pressure() -> tuple[int, float, int, int]:
    """The one real (OAPN, non-proxy) visitor-pressure figure for the park.

    Returns ``(report_year, share_pct, estimated_visitors, red_total)``.
    ``estimated_visitors`` is the park's share of the network total, rounded
    to the nearest visitor — OAPN publishes the share as a percentage, not a
    park-level absolute, so the absolute is a derived (not directly reported)
    figure. It is PARK-WIDE: do not attribute it to any single trail or
    municipality.
    """
    estimate = round(
        ALPINE_OAPN_RED_TOTAL_VISITORS * ALPINE_OAPN_SIERRA_NEVADA_SHARE_PCT / 100.0
    )
    return (
        ALPINE_OAPN_REPORT_YEAR,
        ALPINE_OAPN_SIERRA_NEVADA_SHARE_PCT,
        estimate,
        ALPINE_OAPN_RED_TOTAL_VISITORS,
    )


def build_municipal_context(assets: list) -> MunicipalContext:
    """Summarise how many Sierra Nevada assets resolve to a real municipality.

    Args:
        assets: ranked TerritorialAsset objects (any object with ``.region``).

    Returns:
        :class:`MunicipalContext`.
    """
    crosswalk = load_sierra_nevada_crosswalk()
    resolved: dict[str, SierraNevadaMunicipio] = {}
    unresolved: set[str] = set()

    for a in assets:
        region = getattr(a, "region", None) or ""
        match = resolve_region_to_ine(region, crosswalk)
        if match is not None:
            resolved[match.ine_code] = match
        else:
            unresolved.add(region)

    year, share, estimate, red_total = sierra_nevada_visitor_pressure()

    return MunicipalContext(
        n_assets=len(assets),
        n_resolved=sum(
            1
            for a in assets
            if resolve_region_to_ine(getattr(a, "region", "") or "", crosswalk)
            is not None
        ),
        n_municipios=len(resolved),
        provinces=tuple(sorted({m.province for m in resolved.values()})),
        unresolved_regions=tuple(sorted(unresolved)),
        oapn_report_year=year,
        oapn_sierra_nevada_visitors_estimate=estimate,
        oapn_sierra_nevada_share_pct=share,
        oapn_red_total_visitors=red_total,
    )
