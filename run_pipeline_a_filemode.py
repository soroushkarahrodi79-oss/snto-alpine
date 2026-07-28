"""
SNTO — Pipeline A en modo fichero (sin PostGIS)
================================================
Multi-territorio: Sierra del Rincón y PN Sierra de Guadarrama.

Ejecuta el Pipeline A real (EHS / ΔEHS / SCM / presupuesto) leyendo las
geometrías de senderos desde un GeoJSON en lugar de PostGIS, e importando
LA MISMA matemática que usan calculate_delta_ehs.py y run_scm_operational.py
(no se reimplementa nada: se reutilizan _compute_scene_baselines, _extract_band,
_trail_ehs, _sig, _classify_sig, _extract_zone_ndvi).

El ráster Sentinel-2 (tile T30TVL, 110×110 km) cubre AMBOS territorios, así que
los dos comparten data/clean_assets/spring_raster.tif | summer_raster.tif. Lo
único que cambia por territorio es qué cartografía de senderos se analiza y
dónde se escribe la salida.

Uso
---
    python run_pipeline_a_filemode.py                       # Sierra del Rincón (por defecto)
    python run_pipeline_a_filemode.py --territory pnsg      # PN Sierra de Guadarrama
    python run_pipeline_a_filemode.py --territory all       # ambos territorios

Entrada : data/raw_assets/vector_data/<trails_geojson del territorio>
          data/clean_assets/spring_raster.tif | summer_raster.tif (NDVI, NDMI)
Salida  : data/outputs/<territorio>/pipeline_a_results.csv  + _summary.json

Nota de provenance: los senderos de Rincón provienen de OpenStreetMap; los de
PNSG son una red cartográfica curada por sectores del parque.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import geopandas as gpd
from shapely.ops import linemerge, unary_union

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Reutilizamos la matemática real de los scripts de producción
from calculate_delta_ehs import _compute_scene_baselines, _extract_band, _trail_ehs
from run_scm_operational import _sig, _classify_sig, _extract_zone_ndvi
from src.config.constants import (
    EHS_P_BASE, EHS_P_FLOOR,
    SCM_LOCALIZED_FACTOR, SCM_MIXED_FACTOR, SCM_LANDSCAPE_FACTOR,
    TRAGSA_BASE_RATE_EUR_PER_M,
)
from src.config.territories import TERRITORIES, get as get_territory

CLEAN = _ROOT / "data" / "clean_assets"
# Rásters compartidos: el tile T30TVL cubre Rincón y Guadarrama.
SPRING = CLEAN / "spring_raster.tif"
SUMMER = CLEAN / "summer_raster.tif"
SPRING_SCL = CLEAN / "spring_scl.tif"   # ausente → masking SCL omitido
SUMMER_SCL = CLEAN / "summer_scl.tif"
VECTOR_DIR = _ROOT / "data" / "raw_assets" / "vector_data"
OUTDIR_ROOT = _ROOT / "data" / "outputs"

BUFFER_M = 50
CORE_M, NEAR_M, LAND_M = 50, 200, 1000
UTM = "EPSG:25830"
COST_PER_M = TRAGSA_BASE_RATE_EUR_PER_M  # €/m (TRAGSA 2023, orden de magnitud)

_CAUSAL = {
    "LOCALIZED_IMPACT": SCM_LOCALIZED_FACTOR,
    "MIXED": SCM_MIXED_FACTOR,
    "LANDSCAPE_DRIVEN": SCM_LANDSCAPE_FACTOR,
    None: SCM_MIXED_FACTOR,  # NULL tratado como MIXED (igual que tis_engine)
}


def load_trails_dissolved(trails_path: Path) -> gpd.GeoDataFrame:
    """Carga senderos del GeoJSON y los disuelve por nombre (1 geometría por nombre)."""
    gdf = gpd.read_file(trails_path)
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()
    merged = []
    for name, grp in gdf.groupby("name"):
        geom = unary_union(list(grp.geometry.values))
        try:
            geom = linemerge(geom)
        except Exception:
            pass
        merged.append({"name": name, "geometry": geom})
    out = gpd.GeoDataFrame(merged, crs="EPSG:4326")
    out.insert(0, "id", range(1, len(out) + 1))
    return out


def run_territory(territory_key: str) -> dict:
    """Ejecuta el Pipeline A para un territorio. Devuelve el dict de resumen."""
    cfg = get_territory(territory_key)
    trails_path = VECTOR_DIR / cfg.trails_geojson
    outdir = OUTDIR_ROOT / cfg.key

    print("=" * 72)
    print(f"  SNTO — Pipeline A (modo fichero) · {cfg.display_name}")
    print(f"  Cartografía: {cfg.trails_geojson}")
    print("=" * 72)

    if not trails_path.exists():
        print(f"  ERROR: No se encuentra la cartografía: {trails_path}")
        sys.exit(1)
    for r in (SPRING, SUMMER):
        if not r.exists():
            print(f"  ERROR: Falta el ráster compartido: {r}")
            print("  Genera spring_raster.tif / summer_raster.tif con prepare_raster.py")
            sys.exit(1)

    trails = load_trails_dissolved(trails_path)
    utm = trails.to_crs(UTM)
    print(f"  Senderos (nombres únicos): {len(trails)}")
    total_km = utm.geometry.length.sum() / 1000
    print(f"  Longitud total: {total_km:.1f} km")
    print()

    # Buffers EHS (50 m) y zonas SCM (core 0–50, landscape ring 200–1000)
    buf50 = utm.copy(); buf50["geometry"] = utm.geometry.buffer(BUFFER_M)
    core = utm.copy(); core["geometry"] = utm.geometry.buffer(CORE_M)
    land = utm.copy()
    land["geometry"] = utm.geometry.buffer(LAND_M).difference(utm.geometry.buffer(NEAR_M))

    # Baselines de escena (P90/P10), excluyendo píxeles dentro de buffers de sendero
    print("  Calculando baselines de escena (P90/P10)…")
    sp_nd_b, sp_nd_f = _compute_scene_baselines(SPRING, 1, buf50, SPRING_SCL if SPRING_SCL.exists() else None, EHS_P_BASE, EHS_P_FLOOR)
    sp_nm_b, sp_nm_f = _compute_scene_baselines(SPRING, 2, buf50, SPRING_SCL if SPRING_SCL.exists() else None, EHS_P_BASE, EHS_P_FLOOR)
    su_nd_b, su_nd_f = _compute_scene_baselines(SUMMER, 1, buf50, SUMMER_SCL if SUMMER_SCL.exists() else None, EHS_P_BASE, EHS_P_FLOOR)
    su_nm_b, su_nm_f = _compute_scene_baselines(SUMMER, 2, buf50, SUMMER_SCL if SUMMER_SCL.exists() else None, EHS_P_BASE, EHS_P_FLOOR)

    # Detección de banda NDMI degenerada (baseline ≤ floor → banda muerta / todo ceros).
    # En ese caso NDMI no aporta información: se computa EHS en modo NDVI-only
    # (peso completo a NDVI), en lugar de dejar que un déficit NDMI = 0 reduzca el EHS.
    ndmi_ok_spring = sp_nm_b > sp_nm_f
    ndmi_ok_summer = su_nm_b > su_nm_f
    if not (ndmi_ok_spring and ndmi_ok_summer):
        print("  AVISO: banda NDMI degenerada (todo ceros) — EHS se calcula en modo NDVI-only.")
    print()

    # Zonal stats EHS por sendero
    print("  Zonal stats EHS (buffer 50 m)…")
    sp_ndvi = _extract_band(buf50, SPRING, 1, "Spring NDVI")
    sp_ndmi = _extract_band(buf50, SPRING, 2, "Spring NDMI")
    su_ndvi = _extract_band(buf50, SUMMER, 1, "Summer NDVI")
    su_ndmi = _extract_band(buf50, SUMMER, 2, "Summer NDMI")

    # Zonal stats SCM (NDVI core vs landscape)
    print("  Zonal stats SCM (core vs landscape)…")
    sp_core = _extract_zone_ndvi(core, SPRING, "Spring core")
    sp_land = _extract_zone_ndvi(land, SPRING, "Spring land")
    su_core = _extract_zone_ndvi(core, SUMMER, "Summer core")
    su_land = _extract_zone_ndvi(land, SUMMER, "Summer land")
    print()

    rows = []
    geo_features = []
    for i in range(len(trails)):
        # NDMI sólo si la banda es válida; si está muerta, None → EHS NDVI-only.
        sp_nm = sp_ndmi[i] if ndmi_ok_spring else None
        su_nm = su_ndmi[i] if ndmi_ok_summer else None
        ehs_sp = _trail_ehs(sp_ndvi[i], sp_nm, sp_nd_b, sp_nd_f, sp_nm_b, sp_nm_f)
        ehs_su = _trail_ehs(su_ndvi[i], su_nm, su_nd_b, su_nd_f, su_nm_b, su_nm_f)
        delta = round(ehs_su - ehs_sp, 2) if (ehs_su is not None and ehs_sp is not None) else None
        sig_sp = _sig(sp_land[i], sp_core[i])
        sig_su = _sig(su_land[i], su_core[i])
        scm = _classify_sig(sig_su)
        length_m = float(utm.geometry.iloc[i].length)
        # Presupuesto indicativo: long × 15.50 × (EHS_summer/100) × factor_causal
        # (índice de tráfico no disponible en modo fichero → priority = EHS_summer)
        budget = None
        if ehs_su is not None:
            budget = round(length_m * COST_PER_M * (ehs_su / 100.0) * _CAUSAL[scm], 2)
        rows.append({
            "id": int(trails.id.iloc[i]),
            "name": trails.name.iloc[i],
            "length_m": round(length_m, 1),
            "ehs_spring": ehs_sp, "ehs_summer": ehs_su, "delta_ehs": delta,
            "sig_spring": round(sig_sp, 4) if sig_sp is not None else None,
            "sig_summer": round(sig_su, 4) if sig_su is not None else None,
            "scm_class": scm,
            "causal_factor": _CAUSAL[scm],
            "budget_eur": budget,
        })

        # Geometría real (WGS84) + propiedades calculadas → GeoJSON para el mapa.
        # mapping() devuelve coordenadas en el CRS del GeoDataFrame (EPSG:4326).
        from shapely.geometry import mapping
        geo_features.append({
            "type": "Feature",
            "geometry": mapping(trails.geometry.iloc[i]),
            "properties": {
                "id": int(trails.id.iloc[i]),
                "name": trails.name.iloc[i],
                "length_km": round(length_m / 1000.0, 2),
                "ehs_spring": ehs_sp,
                "ehs_summer": ehs_su,
                "delta_ehs": delta,
                "scm_class": scm,
                "budget_eur": budget,
            },
        })

    outdir.mkdir(parents=True, exist_ok=True)
    import csv
    with (outdir / "pipeline_a_results.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)

    # GeoJSON con geometría real + propiedades calculadas (consumido por el mapa).
    geojson = {"type": "FeatureCollection", "features": geo_features}
    (outdir / "pipeline_a_results.geojson").write_text(
        json.dumps(geojson, ensure_ascii=False), encoding="utf-8"
    )

    # ── Resumen ──
    valid_d = [r["delta_ehs"] for r in rows if r["delta_ehs"] is not None]
    valid_ehs = [r["ehs_summer"] for r in rows if r["ehs_summer"] is not None]
    from collections import Counter
    scm_counts = Counter(r["scm_class"] for r in rows)
    budgets = [r["budget_eur"] for r in rows if r["budget_eur"] is not None]

    def _mean(xs): return sum(xs) / len(xs) if xs else None

    summary = {
        "territory": cfg.key,
        "territory_name": cfg.display_name,
        "n_trails": len(rows),
        "total_length_km": round(total_km, 1),
        "ehs_summer_mean": round(_mean(valid_ehs), 2) if valid_ehs else None,
        "ehs_summer_min": round(min(valid_ehs), 2) if valid_ehs else None,
        "ehs_summer_max": round(max(valid_ehs), 2) if valid_ehs else None,
        "delta_ehs_mean": round(_mean(valid_d), 2) if valid_d else None,
        "n_degrading_positive_delta": sum(1 for d in valid_d if d > 0),
        "n_with_valid_delta": len(valid_d),
        "scm_localized": scm_counts.get("LOCALIZED_IMPACT", 0),
        "scm_mixed": scm_counts.get("MIXED", 0),
        "scm_landscape": scm_counts.get("LANDSCAPE_DRIVEN", 0),
        "scm_null": scm_counts.get(None, 0),
        "total_budget_eur": round(sum(budgets), 2) if budgets else 0.0,
    }
    (outdir / "pipeline_a_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print("-" * 72)
    print(f"  RESUMEN PIPELINE A — {cfg.display_name} (datos reales Sentinel-2)")
    print("-" * 72)
    for k, v in summary.items():
        print(f"  {k:<32} {v}")
    print()
    # Top-5 ΔEHS
    ranked = sorted([r for r in rows if r["delta_ehs"] is not None], key=lambda r: r["delta_ehs"], reverse=True)[:5]
    print("  TOP-5 senderos por ΔEHS (mayor degradación estacional):")
    for r in ranked:
        print(f"    {r['name'][:40]:<40} Δ={r['delta_ehs']:+6.2f}  EHS_v={r['ehs_summer']}  SCM={r['scm_class']}")
    print()
    print(f"  CSV:     {outdir/'pipeline_a_results.csv'}")
    print(f"  GeoJSON: {outdir/'pipeline_a_results.geojson'}")
    print(f"  JSON:    {outdir/'pipeline_a_summary.json'}")
    print()
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pipeline A multi-territorio (EHS/ΔEHS/SCM/presupuesto por senda)."
    )
    parser.add_argument(
        "--territory", default="sierra_del_rincon",
        help=f"Territorio: {', '.join(TERRITORIES)} o 'all'. Defecto: sierra_del_rincon",
    )
    args = parser.parse_args()

    if args.territory == "all":
        keys = list(TERRITORIES)
    else:
        keys = [args.territory]

    for key in keys:
        run_territory(key)


if __name__ == "__main__":
    main()
