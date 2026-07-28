"""
SNTO TIS Engine -- Environmental Health Stress & Investment Simulator
======================================================================
Pilot Territory: Sierra del Rincón Biosphere Reserve, Madrid, Spain

For each hiking trail in production_hiking_trails this script:
  1. Reads the precomputed seasonal EHS (written by calculate_delta_ehs.py),
     annual_visitors, and precise trail length (PostGIS ST_Length).
     The season is controlled by EHS_SEASON_FOR_BUDGET (default "summer").
  2. Uses the seasonal EHS index [0–100] directly as the stress input.
     EHS is not recomputed here — it is anchored to the real pixel
     distribution of each Sentinel-2 scene by calculate_delta_ehs.py.
  3. Computes traffic_index by normalising annual_visitors to [0, 100]:
       traffic_index = (visitors − min) / (max − min) × 100
       NULL annual_visitors are treated as 0.
  4. Computes priority_score = (EHS × 0.60) + (traffic_index × 0.40)
       Trails with NULL EHS receive NULL priority_score.
  5. Sets needs_intervention = True when priority_score > 60
  6. Computes tis_budget_eur = length_m × 15.50 EUR/m × (priority_score / 100)
       Non-critical trails receive a budget of 0.
  7. Reads scm_classification (written by run_scm_operational.py) and applies
     the causal factor (polluter-pays principle):
       LOCALIZED_IMPACT  → tis_budget_causal_eur = tis_budget_eur × 1.0
       MIXED / NULL      → tis_budget_causal_eur = tis_budget_eur × 0.5
       LANDSCAPE_DRIVEN  → tis_budget_causal_eur = 0.0
  8. Writes results back to the database and prints a management report.

Run calculate_delta_ehs.py before this script so that ehs_spring /
ehs_summer columns are populated.

Credentials (env vars with fallbacks):
  SNTO_DB_HOST  localhost
  SNTO_DB_PORT  5432
  SNTO_DB_NAME  snto
  SNTO_DB_USER  postgres
  SNTO_DB_PASS  secret
"""
from __future__ import annotations

import io
import os
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(_PROJECT_ROOT))

import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import execute_values

load_dotenv()  # carga .env antes de os.getenv() a nivel de módulo

from src.config.constants import (
    SCM_LOCALIZED_FACTOR,
    SCM_MIXED_FACTOR,
    SCM_LANDSCAPE_FACTOR,
    TRAGSA_BASE_RATE_EUR_PER_M,
)

SEP = "=" * 72
DIV = "-" * 72

# ── Thresholds, weights & cost constants ──────────────────────────────────────
PRIORITY_CRITICAL_THRESHOLD: float = 60.0
EHS_WEIGHT: float = 0.60
TRAFFIC_WEIGHT: float = 0.40
BASE_RESTORATION_COST_EUR_PER_M: float = TRAGSA_BASE_RATE_EUR_PER_M
# Which seasonal EHS column to use for priority and budget.
# Must be "summer" or "spring"; must match EHS_SEASON_FOR_BUDGET in
# src/config/constants.py (used by calculate_delta_ehs.py to produce the column).
EHS_SEASON_FOR_BUDGET: str = "summer"

# ── Credentials (override via environment variables) ──────────────────────────
DB_HOST = os.getenv("SNTO_DB_HOST", "localhost")
DB_PORT = int(os.getenv("SNTO_DB_PORT", "5432"))
DB_NAME = os.getenv("SNTO_DB_NAME", "snto")
DB_USER = os.getenv("SNTO_DB_USER", "postgres")
DB_PASS = os.getenv("SNTO_DB_PASS", "")

# Column in production_hiking_trails that holds the budget-season EHS.
_EHS_BUDGET_COLUMN: str = f"ehs_{EHS_SEASON_FOR_BUDGET}"


# ── Connection helper ─────────────────────────────────────────────────────────

def _connect() -> psycopg2.extensions.connection:
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        connect_timeout=10,
    )


# ── Schema helper ─────────────────────────────────────────────────────────────

def _ensure_columns(conn: psycopg2.extensions.connection) -> None:
    """Add output columns to production_hiking_trails if not already present."""
    new_cols = [
        ("ehs_index",             "FLOAT"),
        ("needs_intervention",    "BOOLEAN"),
        ("tis_budget_eur",        "FLOAT"),
        ("tis_budget_causal_eur", "FLOAT"),
        ("priority_score",        "FLOAT"),
        ("scm_classification",    "TEXT"),
    ]
    with conn.cursor() as cur:
        for col, col_type in new_cols:
            cur.execute(
                """
                SELECT 1 FROM information_schema.columns
                WHERE  table_schema = 'public'
                  AND  table_name   = 'production_hiking_trails'
                  AND  column_name  = %s
                """,
                (col,),
            )
            if cur.fetchone() is None:
                print(f"    Adding column '{col}' {col_type} ...")
                cur.execute(
                    f"ALTER TABLE production_hiking_trails ADD COLUMN {col} {col_type}"
                )
            else:
                print(f"    Column '{col}' already exists — will overwrite values.")
    conn.commit()


# ── Demand normalisation ──────────────────────────────────────────────────────

def _traffic_index(visitors: int | None, min_v: int, max_v: int) -> float:
    """
    Normalise annual_visitors to [0, 100].
    NULL visitors → 0.  Flat distribution (all equal) → 0.
    """
    if visitors is None or max_v == min_v:
        return 0.0
    return round((visitors - min_v) / (max_v - min_v) * 100.0, 2)


# ── Priority & TIS algorithm ──────────────────────────────────────────────────

def _compute_priority(ehs: float | None, ti: float) -> float | None:
    """
    priority_score = (EHS × 0.60) + (traffic_index × 0.40)
    Returns None when EHS is unavailable (calculate_delta_ehs.py not yet run).
    """
    if ehs is None:
        return None
    return round(ehs * EHS_WEIGHT + ti * TRAFFIC_WEIGHT, 2)


def _compute_tis(priority_score: float | None, length_m: float) -> tuple[bool, float]:
    """Returns (needs_intervention, tis_budget_eur) using priority_score as severity."""
    if priority_score is None or priority_score <= PRIORITY_CRITICAL_THRESHOLD:
        return False, 0.0
    budget = length_m * BASE_RESTORATION_COST_EUR_PER_M * (priority_score / 100.0)
    return True, round(budget, 2)


def _causal_factor(scm_classification: str | None) -> float:
    """Return the causal fraction of degradation attributable to local trail use."""
    if scm_classification == "LOCALIZED_IMPACT":
        return SCM_LOCALIZED_FACTOR
    if scm_classification == "LANDSCAPE_DRIVEN":
        return SCM_LANDSCAPE_FACTOR
    return SCM_MIXED_FACTOR  # MIXED or NULL → default to half


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    print(SEP)
    print("  SNTO TIS Engine -- Environmental Health Stress & Investment Simulator")
    print("  Pilot: Sierra del Rincón Biosphere Reserve, Madrid, Spain")
    print(f"  Target: postgresql://{DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}")
    print(SEP)
    print(f"  EHS source column: {_EHS_BUDGET_COLUMN}  "
          f"(EHS_SEASON_FOR_BUDGET={EHS_SEASON_FOR_BUDGET!r})")
    print()

    # ── [1/5] Connect ─────────────────────────────────────────────────────────
    print("  [1/5] Connecting to PostgreSQL ...")
    try:
        conn = _connect()
    except (psycopg2.OperationalError, UnicodeDecodeError) as exc:
        print()
        print("  ERROR: Cannot reach the PostgreSQL server.")
        print(f"  Detail: {type(exc).__name__} — server may not be running.")
        print()
        print("  To resolve:")
        print("    1. Start PostgreSQL via pgAdmin or Windows Services")
        print("    2. Run calculate_delta_ehs.py to populate ehs_spring / ehs_summer")
        print("    3. Override credentials if needed:")
        print("         SNTO_DB_HOST  SNTO_DB_PORT  SNTO_DB_NAME  SNTO_DB_USER  SNTO_DB_PASS")
        sys.exit(1)

    major, minor = divmod(conn.server_version, 10000)
    print(f"  Connected to '{DB_NAME}'. PostgreSQL {major}.{minor}")
    print()

    try:
        # ── [2/5] Ensure output columns ───────────────────────────────────────
        print("  [2/5] Ensuring output columns exist ...")
        _ensure_columns(conn)
        print()

        # ── [3/5] Fetch trail data ─────────────────────────────────────────────
        print(
            f"  [3/5] Fetching trails with {_EHS_BUDGET_COLUMN}, "
            "visitor counts, PostGIS lengths and SCM classification ..."
        )
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    id,
                    name,
                    {_EHS_BUDGET_COLUMN},
                    annual_visitors,
                    ST_Length(geometry::geography) AS length_m,
                    scm_classification
                FROM production_hiking_trails
                ORDER BY id
                """
            )
            rows = cur.fetchall()

        n_total    = len(rows)
        n_ehs      = sum(1 for r in rows if r[2] is not None)
        n_visitors = sum(1 for r in rows if r[3] is not None)
        n_scm      = sum(1 for r in rows if r[5] is not None)
        print(f"    Trails fetched              : {n_total}")
        print(f"    With {_EHS_BUDGET_COLUMN:<12}: {n_ehs}")
        print(f"    With annual_visitors        : {n_visitors}")
        print(f"    With scm_classification     : {n_scm}")
        if n_ehs == 0:
            print()
            print(
                "  WARNING: No EHS values found in column "
                f"'{_EHS_BUDGET_COLUMN}'."
            )
            print("  Run calculate_delta_ehs.py first to populate seasonal EHS.")
        print()

        if n_total == 0:
            print("  WARNING: No trails found. Run db_production_seeder.py,")
            print("  etl_raster_intersection.py and etl_tourist_traffic.py first.")
            sys.exit(0)

        # Visitor bounds for dataset-level normalisation
        visitor_values = [r[3] for r in rows if r[3] is not None]
        min_v = min(visitor_values) if visitor_values else 0
        max_v = max(visitor_values) if visitor_values else 0

        # ── [4/5] Compute and batch-update ────────────────────────────────────
        print("  [4/5] Computing traffic index, priority score, TIS and causal budget ...")
        update_rows: list[tuple] = []

        for trail_id, name, ehs, annual_visitors, length_m, scm_cls in rows:
            ti                              = _traffic_index(annual_visitors, min_v, max_v)
            priority                        = _compute_priority(ehs, ti)
            needs_intervention, tis_budget  = _compute_tis(priority, float(length_m or 0.0))
            causal_budget                   = round(tis_budget * _causal_factor(scm_cls), 2)
            update_rows.append(
                (ehs, priority, needs_intervention, tis_budget, causal_budget, trail_id)
            )

        with conn.cursor() as cur:
            execute_values(
                cur,
                """
                UPDATE production_hiking_trails AS t SET
                    ehs_index             = v.ehs_index,
                    priority_score        = v.priority_score,
                    needs_intervention    = v.needs_intervention,
                    tis_budget_eur        = v.tis_budget_eur,
                    tis_budget_causal_eur = v.tis_budget_causal_eur
                FROM (VALUES %s) AS v(
                    ehs_index, priority_score, needs_intervention,
                    tis_budget_eur, tis_budget_causal_eur, id
                )
                WHERE t.id = v.id
                """,
                update_rows,
                template="(%s::FLOAT, %s::FLOAT, %s::BOOLEAN, %s::FLOAT, %s::FLOAT, %s::INT)",
            )

        conn.commit()
        print(f"    Rows updated: {len(update_rows)}")
        print()

        # ── [5/5] Management report ───────────────────────────────────────────
        print("  [5/5] Fetching final figures for management report ...")
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    COUNT(*)                                              AS total_trails,
                    COUNT(ehs_index)                                      AS ehs_computed,
                    COUNT(priority_score)                                 AS priority_computed,
                    COUNT(*) FILTER (WHERE needs_intervention = TRUE)     AS critical_trails,
                    COALESCE(SUM(tis_budget_eur), 0)                      AS total_budget_gross,
                    COALESCE(SUM(tis_budget_causal_eur), 0)               AS total_budget_causal,
                    ROUND(AVG(priority_score)::NUMERIC, 2)                AS mean_priority,
                    ROUND(MIN(priority_score)::NUMERIC, 2)                AS min_priority,
                    ROUND(MAX(priority_score)::NUMERIC, 2)                AS max_priority
                FROM production_hiking_trails
                """
            )
            stats = cur.fetchone()
            (
                total_trails, ehs_computed, priority_computed, critical_trails,
                total_budget_gross, total_budget_causal,
                mean_priority, min_priority, max_priority,
            ) = stats

            cur.execute(
                """
                SELECT
                    name,
                    ehs_index,
                    priority_score,
                    annual_visitors,
                    tis_budget_eur,
                    tis_budget_causal_eur,
                    scm_classification,
                    ST_Length(geometry::geography) AS length_m
                FROM   production_hiking_trails
                WHERE  needs_intervention = TRUE
                ORDER  BY priority_score DESC NULLS LAST
                """
            )
            critical_rows = cur.fetchall()

        print()
        print(SEP)
        print("  SNTO MANAGEMENT REPORT — Priority Score & Investment Budget")
        print("  Demand Layer: Tourist Pressure integrated (CETS Phase I)")
        print(SEP)
        print()
        print(f"  Total trails analysed        : {total_trails}")
        print(f"  Trails with EHS computed     : {ehs_computed}")
        print(f"  Trails with priority score   : {priority_computed}")
        print(f"  Priority score range         : {min_priority}  –  {max_priority}  (mean: {mean_priority})")
        print(f"  Critical threshold (score>60): {PRIORITY_CRITICAL_THRESHOLD:.0f}")
        print(f"  Visitor range (annual)       : {min_v:,}  –  {max_v:,}")
        print()
        print(DIV)
        print(f"  Trails requiring intervention : {critical_trails} / {total_trails}")
        print(f"  Total Budget (gross)          : EUR {total_budget_gross:,.2f}")
        print(f"  Total Budget (causal, SCM)    : EUR {total_budget_causal:,.2f}")
        print(DIV)
        print()

        if critical_rows:
            print(
                f"  {'Trail name':<32} "
                f"{'EHS':>6}  {'Priority':>8}  {'Budget €':>10}  {'Causal €':>10}  {'SCM':>18}"
            )
            print(
                f"  {'-'*32} "
                f"{'-'*6}  {'-'*8}  {'-'*10}  {'-'*10}  {'-'*18}"
            )
            for name, ehs, priority, visitors, budget, causal_bud, scm_cls, length_m in critical_rows:
                label    = (name or "—")[:31]
                ehs_str  = f"{ehs:.1f}"      if ehs      is not None else "N/A"
                pri_str  = f"{priority:.1f}" if priority is not None else "N/A"
                bud_str  = f"{budget:,.0f}"  if budget   is not None else "N/A"
                cau_str  = f"{causal_bud:,.0f}" if causal_bud is not None else "N/A"
                scm_str  = (scm_cls or "—")[:18]
                print(
                    f"  {label:<32} "
                    f"{ehs_str:>6}  {pri_str:>8}  {bud_str:>10}  {cau_str:>10}  {scm_str:>18}"
                )
            print()
        else:
            print("  No trails exceed the critical priority threshold.")
            print()

        cost_km = BASE_RESTORATION_COST_EUR_PER_M * 1000
        print("  Assumptions:")
        print(
            f"    Base restoration cost  : EUR {BASE_RESTORATION_COST_EUR_PER_M:.2f}/m  "
            f"(EUR {cost_km:,.0f}/km)"
        )
        print(
            f"    EHS source             : {_EHS_BUDGET_COLUMN} "
            f"(percentile-anchored, scene-relative)"
        )
        print(
            f"    Priority formula       : "
            f"(EHS × {EHS_WEIGHT:.2f}) + (traffic_index × {TRAFFIC_WEIGHT:.2f})"
        )
        print(f"    Severity multiplier    : priority_score / 100")
        print(
            f"    Budget formula (gross) : "
            f"length_m × {BASE_RESTORATION_COST_EUR_PER_M} × (priority_score / 100)"
        )
        print(
            f"    Causal factors (SCM)   : "
            f"LOCALIZED×{SCM_LOCALIZED_FACTOR:.1f}  "
            f"MIXED×{SCM_MIXED_FACTOR:.1f}  "
            f"LANDSCAPE×{SCM_LANDSCAPE_FACTOR:.1f}  "
            f"(NULL→MIXED)"
        )
        print()
        print(SEP)

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
