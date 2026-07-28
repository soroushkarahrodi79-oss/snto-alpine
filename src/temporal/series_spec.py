"""
SNTO — Temporal Series Specification (F2 scaffolding)
=====================================================
Canonical, declarative definition of a multi-year satellite time series.

This module does NOT fetch data. It defines *what* series the observatory
intends to build (territory, year span, cadence, tile, indices, quality
floor) so that ingestion, the Mann-Kendall validity gate (``trend_gate``) and
the provenance manifest (``manifest``) all agree on the same plan and the same
set of expected periods.

The 5-year PNSG plan (``PNSG_5Y``) is the reference series the project is
structuring toward: monthly Sentinel-2 composites 2021–2026. Until that series
is actually ingested via Google Earth Engine, this spec is the contract the
rest of the temporal layer is written against.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Cadence(str, Enum):
    """Temporal resolution at which composites are built."""
    MONTHLY = "monthly"
    SEASONAL = "seasonal"


# Meteorological seasons (Northern Hemisphere) → the months they aggregate.
# Winter is anchored to the year of Jan/Feb (Dec belongs to the prior winter).
SEASON_MONTHS: dict[str, tuple[int, ...]] = {
    "winter": (1, 2, 12),
    "spring": (3, 4, 5),
    "summer": (6, 7, 8),
    "autumn": (9, 10, 11),
}
SEASON_ORDER: tuple[str, ...] = ("winter", "spring", "summer", "autumn")


@dataclass(frozen=True)
class Period:
    """A single period of a series.

    For MONTHLY cadence ``month`` is 1–12 and ``season`` is None.
    For SEASONAL cadence ``season`` is set and ``month`` is None.
    """
    year: int
    month: Optional[int] = None
    season: Optional[str] = None

    @property
    def key(self) -> str:
        if self.month is not None:
            return f"{self.year}-{self.month:02d}"
        return f"{self.year}-{self.season}"


@dataclass(frozen=True)
class SeriesSpec:
    """Declarative plan for one territory's multi-year series.

    Attributes:
        territory_key: registry key (see ``src.config.territories``).
        start_year / end_year: inclusive calendar-year span.
        cadence: MONTHLY or SEASONAL.
        s2_tile: Sentinel-2 MGRS tile expected to cover the AOI.
        indices: spectral indices the series carries.
        min_valid_pixel_pct: quality floor — composites below this cloud-free
            fraction are treated as gaps, not observations.
        collection: GEE/STAC collection id the series is built from.
    """
    territory_key: str
    start_year: int
    end_year: int
    cadence: Cadence = Cadence.MONTHLY
    s2_tile: str = "T30TVL"
    indices: tuple[str, ...] = ("NDVI", "NDMI", "EVI", "NDSI")
    min_valid_pixel_pct: float = 0.30
    collection: str = "COPERNICUS/S2_SR_HARMONIZED"

    def __post_init__(self) -> None:
        if self.end_year < self.start_year:
            raise ValueError(
                f"end_year ({self.end_year}) < start_year ({self.start_year})"
            )

    def years(self) -> list[int]:
        return list(range(self.start_year, self.end_year + 1))

    def periods(self) -> list[Period]:
        """All expected periods of the series, in chronological order."""
        out: list[Period] = []
        for year in self.years():
            if self.cadence is Cadence.MONTHLY:
                out.extend(Period(year=year, month=m) for m in range(1, 13))
            else:
                out.extend(Period(year=year, season=s) for s in SEASON_ORDER)
        return out

    def period_keys(self) -> list[str]:
        return [p.key for p in self.periods()]

    def n_expected(self) -> int:
        """Number of periods a fully-populated series would contain."""
        span = self.end_year - self.start_year + 1
        return span * (12 if self.cadence is Cadence.MONTHLY else 4)

    def span_years(self) -> int:
        return self.end_year - self.start_year + 1

    def label(self) -> str:
        return f"{self.start_year}–{self.end_year}"


def spec_for_territory(
    territory_key: str,
    start_year: int,
    end_year: int,
    cadence: Cadence = Cadence.MONTHLY,
) -> SeriesSpec:
    """Build a SeriesSpec from the territory registry (tile auto-resolved).

    Keeps the Sentinel-2 tile in sync with ``src.config.territories`` so a
    series plan can never silently disagree with the territory definition.
    """
    from src.config import territories

    cfg = territories.get(territory_key)
    return SeriesSpec(
        territory_key=territory_key,
        start_year=start_year,
        end_year=end_year,
        cadence=cadence,
        s2_tile=cfg.s2_tile,
    )


# ── Reference series the project is structuring toward ──────────────────────────
# PNSG, monthly Sentinel-2 composites, 2021–2026 (six calendar years → 72 months).
PNSG_5Y = SeriesSpec(
    territory_key="pnsg",
    start_year=2021,
    end_year=2026,
    cadence=Cadence.MONTHLY,
    s2_tile="T30TVL",
)
