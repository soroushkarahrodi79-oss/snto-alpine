"""
Multi-date winter snow series for Sierra Nevada (issue #8).

Moves the winter product from a single February-2024 scene to a reproducible
multi-date series. Reuses existing infrastructure rather than inventing a
parallel one:

* :func:`src.features.alpine_spectral.compute_snowpack_duration` for the
  per-asset duration count (already series-aware).
* :class:`src.time_series.confidence.BootstrapCI` /
  :func:`block_bootstrap_ci` for the snowline uncertainty band (a moving-block
  bootstrap already used elsewhere for short, serially-dependent series).
* :class:`src.temporal.manifest.DataStatus` / :func:`classify_source` for the
  provenance trust-tier vocabulary, instead of a second one.

This module is pure aggregation logic — no rasterio/network I/O — so it is
testable without live data; :mod:`scripts.build_alpine_snow_series` supplies
the per-period observations from the real pipeline.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from src.features.alpine_spectral import compute_snowpack_duration
from src.geospatial.raster_mosaic import TileManifestEntry
from src.temporal.manifest import DataStatus, classify_source
from src.time_series.confidence import BootstrapCI, block_bootstrap_ci

# Quality floor: a mosaic run that covers less of the bbox than this is a gap,
# not evidence — mirrors SeriesSpec.min_valid_pixel_pct's intent (the
# documented quality rule issue #8 asks for).
MIN_VALID_PIXEL_PCT = 30.0


@dataclass(frozen=True)
class WinterPeriodObservation:
    """One month's regional winter snow observation."""

    period_key: str              # e.g. "2023-12"
    date_range: str              # STAC datetime filter used, for reproducibility
    mosaic_coverage_pct: float   # % of the bbox any tile covered (0-100)
    snowline_elevation_m: Optional[float]
    n_snow_pixels: int
    tiles: list[TileManifestEntry] = field(default_factory=list)

    @property
    def present(self) -> bool:
        """Real observation vs. gap: below the coverage floor, or no usable
        snowline estimate (too few snow pixels), is a gap — not a zero."""
        return (
            self.mosaic_coverage_pct >= MIN_VALID_PIXEL_PCT
            and self.snowline_elevation_m is not None
        )

    @property
    def data_status(self) -> DataStatus:
        if not self.present:
            return DataStatus.MISSING
        return classify_source("sentinel-2-l2a stac mosaic")


def snowline_series_ci(
    observations: list[WinterPeriodObservation],
    alpha: float = 0.05,
) -> Optional[BootstrapCI]:
    """Moving-block bootstrap CI for the mean snowline across *present* periods.

    None when fewer than 2 periods carry a usable snowline — a "confidence
    interval" from a single point would just restate the point.
    """
    values = [o.snowline_elevation_m for o in observations if o.present]
    if len(values) < 2:
        return None
    return block_bootstrap_ci(
        values, statistic=lambda s: sum(s) / len(s), alpha=alpha
    )


def asset_snowpack_duration(
    ndsi_by_period: dict[str, Optional[float]],
    period_order: list[str],
) -> int:
    """Snowpack duration (periods with snow) for one asset's NDSI series.

    ``ndsi_by_period`` need not have every key in ``period_order`` — a missing
    period is a gap (NaN), consistent with ``compute_snowpack_duration``'s
    contract: gaps are not counted as snow-free, just not counted.
    """
    series = [
        v if (v := ndsi_by_period.get(key)) is not None else float("nan")
        for key in period_order
    ]
    return compute_snowpack_duration(series)


def series_summary(observations: list[WinterPeriodObservation]) -> dict:
    """Lightweight dict the dashboard can render directly — periods, coverage,
    snowline + its uncertainty band (issue #8's "salida ligera consumible por
    dashboard")."""
    ci = snowline_series_ci(observations)
    present_snowlines = [o.snowline_elevation_m for o in observations if o.present]
    point = ci.point if ci else (present_snowlines[0] if present_snowlines else None)
    return {
        "n_expected": len(observations),
        "n_present": sum(1 for o in observations if o.present),
        "gaps": [o.period_key for o in observations if not o.present],
        "snowline_mean_m": point,
        "snowline_ci_low_m": ci.lower if ci else None,
        "snowline_ci_high_m": ci.upper if ci else None,
        "snowline_ci_alpha": ci.alpha if ci else None,
        "min_valid_pixel_pct": MIN_VALID_PIXEL_PCT,
        "periods": [
            {
                "period_key": o.period_key,
                "present": o.present,
                "data_status": o.data_status.value,
                "date_range": o.date_range,
                "mosaic_coverage_pct": round(o.mosaic_coverage_pct, 2),
                "snowline_elevation_m": o.snowline_elevation_m,
                "n_snow_pixels": o.n_snow_pixels,
                "tiles": [
                    {
                        "tile": t.tile,
                        "scene_id": t.scene_id,
                        "date": t.date,
                        "cloud_pct": t.cloud_pct,
                        "coverage_pct": t.coverage_pct,
                    }
                    for t in o.tiles
                ],
            }
            for o in observations
        ],
    }


def write_series_json(
    observations: list[WinterPeriodObservation], out_path: str | Path
) -> Path:
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(series_summary(observations), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return p
