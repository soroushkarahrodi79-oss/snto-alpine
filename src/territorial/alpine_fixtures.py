"""
SNTO Alpine Edition — Sierra Nevada dashboard assets (Sierra Nevada pilot)
=========================================================================
Builds the ``TerritorialAsset`` list the dashboard needs for Sierra Nevada,
from the real GEE time series shipped in
``clean_assets/timeseries/pn_sierra_nevada_gee_timeseries.csv`` (53 OAPN trails
and MTB routes, 66 monthly NDVI/NDMI/EVI composites, 2021–2026).

What is REAL here and what is a PROXY — stated plainly, because the whole
edition's evidence discipline demands it:

* **Real (satellite-derived):** ``ehs`` (from growing-season EVI/NDMI against the
  alpine borreguil baselines, penalised by the Mann-Kendall trend and by NDVI
  volatility), ``trend_direction`` / ``mk_p_value`` (Mann-Kendall on the monthly
  NDVI series), and the data-coverage part of ``dcs``.
* **Proxy (NOT observed):** ``visitor_capacity_annual``, ``economic_importance``,
  ``accessibility_score`` (deterministic per-asset placeholders by category — no
  visitor-counting campaign exists), ``scm_classification`` (a territory-relative
  degradation heuristic, not the zone-based SCM), and the approximate map
  position (municipality centroid parsed from the trail name + jitter, the same
  approximation the base dashboard uses).

None of this is field-validated. The EHS here is a **prototype fixture score**,
deliberately distinct from the operational percentile-anchored EHS.
"""
from __future__ import annotations

import csv
import hashlib
from collections import defaultdict
from pathlib import Path
from typing import Optional

from src.features.alpine_spectral import compute_soil_degradation
from src.territorial.models import AssetType, TerritorialAsset
from src.time_series.mann_kendall import mann_kendall_test

_ROOT = Path(__file__).resolve().parents[2]
_CSV = _ROOT / "clean_assets" / "timeseries" / "pn_sierra_nevada_gee_timeseries.csv"

# Growing season for the borreguiles (short, high-altitude). Falls back to all
# available months when a trail has no growing-season composite.
_GROWING_MONTHS = frozenset({6, 7, 8, 9})
_EXPECTED_MONTHS = 66  # 2021-01 … 2026-06, per the GEE template

# Municipalities that appear in the OAPN trail names, with approximate WGS84
# centroids. Region strings must match keys added to
# ``src.platform.map_layers._REGION_CENTROIDS`` so the map places them on the
# massif rather than at the base reserve's default centroid.
_MUNICIPIOS: tuple[tuple[str, tuple[float, float]], ...] = (
    ("Monachil", (37.126, -3.531)),
    ("Güéjar Sierra", (37.163, -3.437)),
    ("Güejar Sierra", (37.163, -3.437)),
    ("Dílar", (37.070, -3.577)),
    ("Lanjarón", (36.922, -3.479)),
    ("Soportújar", (36.930, -3.412)),
    ("Cáñar", (36.945, -3.427)),
    ("Capileira", (37.001, -3.359)),
    ("Bubión", (36.994, -3.362)),
    ("Pampaneira", (36.963, -3.368)),
    ("Trevélez", (36.995, -3.269)),
    ("Pórtugos", (36.939, -3.311)),
    ("Portugos", (36.939, -3.311)),
    ("Busquístar", (36.938, -3.293)),
    ("Bérchules", (36.982, -3.208)),
    ("Mecina Bombarón", (36.980, -3.152)),
    ("Mecina Bombaron", (36.980, -3.152)),
    ("Yegen", (36.992, -3.130)),
    ("Válor", (36.993, -3.101)),
    ("Valor", (36.993, -3.101)),
    ("Cádiar", (36.931, -3.190)),
    ("Jérez del Marquesado", (37.190, -3.140)),
    ("Postero Alto", (37.160, -3.120)),   # refugio, vertiente norte
    ("Aldeire", (37.201, -3.100)),
    ("La Calahorra", (37.181, -3.052)),
    ("Lanteira", (37.199, -3.078)),
    ("Niguelas", (36.981, -3.527)),       # Valle de Lecrín
    ("Cumbres Verdes", (37.089, -3.507)), # La Zubia / Trevenque
    ("Arenales del Trevenque", (37.093, -3.503)),
    ("Abrucena", (37.132, -2.797)),       # vertiente norte (Almería)
    ("Bayarcal", (37.030, -2.883)),       # Almería
    ("Laujar", (36.993, -2.897)),         # Laujar de Andarax (Almería)
    ("Refugio Poqueira", (37.020, -3.330)),
)
_MASSIF_DEFAULT_REGION = "Sierra Nevada"


def _region_for(name: str) -> str:
    """First recognised municipality in the trail name, else the massif label."""
    low = name.lower()
    for muni, _ in _MUNICIPIOS:
        if muni.lower() in low:
            return muni
    return _MASSIF_DEFAULT_REGION


def sierra_nevada_region_centroids() -> dict[str, tuple[float, float]]:
    """Region → (lat, lon) for every Sierra Nevada municipality used here.

    Consumed by ``src.platform.map_layers`` to extend its centroid table.
    """
    out: dict[str, tuple[float, float]] = {m: c for m, c in _MUNICIPIOS}
    out[_MASSIF_DEFAULT_REGION] = (37.055, -3.310)
    return out


def _det_unit(asset_id: str, salt: str) -> float:
    """Deterministic pseudo-random value in [0, 1) from an id — for proxies."""
    h = hashlib.sha1(f"{asset_id}:{salt}".encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _alert_level(risk: float, trend: str) -> str:
    if risk >= 0.55:
        return "CRITICAL_INTERVENTION"
    if risk >= 0.40:
        return "URGENT_MONITORING"
    if risk >= 0.25 or trend == "decreasing":
        return "PREVENTIVE_ACTION"
    return "ROUTINE_MONITORING"


def _load_rows() -> dict[str, list[dict]]:
    if not _CSV.exists():
        raise FileNotFoundError(
            f"Sierra Nevada GEE time series not found at {_CSV}. "
            "It ships in clean_assets/timeseries/."
        )
    by_asset: dict[str, list[dict]] = defaultdict(list)
    with open(_CSV, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            by_asset[row["asset_id"]].append(row)
    return by_asset


def _float(row: dict, key: str) -> Optional[float]:
    raw = row.get(key)
    if raw in (None, "", "null", "NaN"):
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def build_sierra_nevada_territory() -> list[TerritorialAsset]:
    """Build the 53 Sierra Nevada assets from the real GEE time series.

    Returns raw (unranked) ``TerritorialAsset`` objects; ``rank_assets`` assigns
    TPI/tier downstream, exactly as for the base territories.
    """
    by_asset = _load_rows()

    # First pass: per-asset spectral aggregates, needed before the SCM proxy
    # (which is territory-relative to the median degradation).
    agg: dict[str, dict] = {}
    for asset_id, rows in by_asset.items():
        rows_sorted = sorted(rows, key=lambda r: (int(r["year"]), int(r["month"])))
        ndvi_series = [v for r in rows_sorted if (v := _float(r, "ndvi")) is not None]

        grow = [r for r in rows_sorted if int(r["month"]) in _GROWING_MONTHS]
        season = grow or rows_sorted
        mean_evi = _mean([v for r in season if (v := _float(r, "evi")) is not None])
        mean_ndmi = _mean([v for r in season if (v := _float(r, "ndmi")) is not None])
        mean_std = _mean(
            [v for r in rows_sorted if (v := _float(r, "ndvi_stdDev")) is not None]
        )
        mk = mann_kendall_test(ndvi_series)
        degradation = compute_soil_degradation(mean_evi, mean_ndmi)

        agg[asset_id] = {
            "name": rows_sorted[0]["nombre"],
            "category": rows_sorted[0]["category"],
            "n_obs": len(ndvi_series),
            "mean_evi": mean_evi,
            "mean_ndmi": mean_ndmi,
            "mean_std": mean_std,
            "mk": mk,
            "degradation": degradation,
        }

    degradations = sorted(a["degradation"] for a in agg.values())
    median_deg = degradations[len(degradations) // 2] if degradations else 0.0

    assets: list[TerritorialAsset] = []
    for asset_id, a in agg.items():
        mk = a["mk"]
        trend = mk.trend_direction

        # ── EHS (real, prototype fixture score) ──────────────────────────────
        base_health = 100.0 * (1.0 - a["degradation"])
        trend_pen = 15.0 if trend == "decreasing" and mk.is_significant else (
            7.0 if trend == "decreasing" else 0.0
        )
        vol_pen = min(10.0, a["mean_std"] * 40.0)  # NDVI stdDev → up to 10 pts
        ehs = max(20.0, min(98.0, base_health - trend_pen - vol_pen))
        risk = max(0.0, min(1.0, 1.0 - ehs / 100.0))

        # ── DCS (coverage real + trend-significance bonus) ───────────────────
        coverage = a["n_obs"] / _EXPECTED_MONTHS
        sig_bonus = 10.0 if mk.is_significant else 0.0
        dcs = max(0.0, min(95.0, 35.0 + 55.0 * coverage + sig_bonus))

        # ── SCM (territory-relative degradation heuristic — proxy) ───────────
        if a["degradation"] > median_deg * 1.15:
            scm_class, scm_conf = "LOCALIZED_IMPACT", "MODERATE"
        elif a["degradation"] < median_deg * 0.85:
            scm_class, scm_conf = "LANDSCAPE_DRIVEN", "MODERATE"
        else:
            scm_class, scm_conf = "MIXED", "LOW"

        is_bike = a["category"] == "ciclismo"
        asset_type = AssetType.CYCLING_ROUTE if is_bike else AssetType.TRAIL

        # ── Socioeconomic / access (deterministic proxies, NOT observed) ─────
        vis_lo, vis_hi = (6_000, 28_000) if is_bike else (3_000, 22_000)
        visitors = int(vis_lo + _det_unit(asset_id, "vis") * (vis_hi - vis_lo))
        economic = round(0.30 + _det_unit(asset_id, "eco") * 0.55, 3)
        access = round(0.40 + _det_unit(asset_id, "acc") * 0.50, 3)

        assets.append(
            TerritorialAsset(
                asset_id=asset_id,
                name=a["name"],
                asset_type=asset_type,
                region=_region_for(a["name"]),
                ehs=round(ehs, 1),
                risk_score=round(risk, 4),
                dcs=round(dcs, 1),
                alert_level=_alert_level(risk, trend),
                scm_classification=scm_class,
                scm_confidence=scm_conf,
                trend_direction=trend,
                mk_p_value=round(mk.p_value, 4),
                visitor_capacity_annual=visitors,
                economic_importance=economic,
                accessibility_score=access,
                description=(
                    f"{'Ruta BTT' if is_bike else 'Sendero'} · Sierra Nevada · "
                    f"EHS y tendencia derivados de serie Sentinel-2 real (GEE); "
                    f"atributos socioeconómicos estimados (proxy)."
                ),
            )
        )

    return assets
