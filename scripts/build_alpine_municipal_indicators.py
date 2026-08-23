"""
Build real IECA/SIMA municipal indicators for Sierra Nevada (issue #22).

Fetches "Andalucía pueblo a pueblo" — IECA's public per-municipality fact
sheet — for every real municipality in
``clean_assets/sierra_nevada_municipios_ine.csv`` (issue #10's crosswalk),
parses it with :func:`src.socioeconomic.alpine_indicators.parse_sima_ficha_html`,
and writes a committed snapshot:

    src/socioeconomic/snapshot/sierra_nevada_municipal_indicators.json

Ships inside the package (like the PNSG snapshot) so it reaches CI and the
Azure image without a live fetch at runtime. A courtesy delay between
requests keeps this polite to IECA's server; there is no bulk/API endpoint
for this data, only the per-municipality HTML page.

Running::

    PYTHONPATH=. python scripts/build_alpine_municipal_indicators.py
"""
from __future__ import annotations

import csv
import json
import time
import urllib.request
from pathlib import Path

from src.socioeconomic.alpine_indicators import SIMA_FICHA_URL, parse_sima_ficha_html

_ROOT = Path(__file__).resolve().parents[1]
_CROSSWALK = _ROOT / "clean_assets" / "sierra_nevada_municipios_ine.csv"
_OUT = (
    _ROOT / "src" / "socioeconomic" / "snapshot"
    / "sierra_nevada_municipal_indicators.json"
)
_USER_AGENT = "Mozilla/5.0 (compatible; snto-alpine research pipeline)"
_REQUEST_DELAY_S = 1.0


def _fetch(ine_code: str) -> str:
    url = SIMA_FICHA_URL.format(ine_code=ine_code)
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def main() -> None:
    rows = list(csv.DictReader(open(_CROSSWALK, encoding="utf-8-sig")))
    print(f"Fetching IECA/SIMA fichas for {len(rows)} municipalities …")

    records: dict[str, dict] = {}
    for i, row in enumerate(rows):
        ine_code = row["ine_code"].strip()
        name = row["name"].strip()
        print(f"  [{i + 1}/{len(rows)}] {name} ({ine_code}) …")
        try:
            html = _fetch(ine_code)
            rec = parse_sima_ficha_html(ine_code, html)
        except Exception as exc:  # pragma: no cover - network failure path
            print(f"    FAILED: {exc}")
            continue
        records[ine_code] = rec.to_dict()
        if i < len(rows) - 1:
            time.sleep(_REQUEST_DELAY_S)

    n_with_population = sum(1 for r in records.values() if r["population"] is not None)
    print(
        f"Parsed {len(records)}/{len(rows)} fichas "
        f"({n_with_population} with a real population figure)."
    )

    payload = {
        "source": "IECA/SIMA — Andalucía pueblo a pueblo",
        "source_url_template": SIMA_FICHA_URL,
        "n_municipalities": len(records),
        "municipalities": records,
    }
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {_OUT}")


if __name__ == "__main__":
    main()
