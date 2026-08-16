"""
Mantiene README.md sincronizado con la versión de pyproject.toml y el conteo
actual de tests.

Modos de uso:
  python scripts/sync_readme.py                # actualiza README en sitio
  python scripts/sync_readme.py --check-version # (CI) sale con código 1 si
                                                #   la versión del README no
                                                #   coincide con pyproject.toml
"""
from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
README = ROOT / "README.md"

_MESES_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def _get_version() -> str:
    with open(PYPROJECT, "rb") as f:
        return tomllib.load(f)["project"]["version"]


def _get_test_count() -> int | None:
    """Return the number of tests that actually passed, not merely collected.

    The Alpine suite has an intentional skip, so using ``--collect-only`` made
    the README overstate the passing count by one. CI uses ``--check-version``
    and never enters this path; the full run is only paid when a maintainer asks
    the script to refresh the README metadata.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "--no-header",
            "--disable-warnings",
        ],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    for line in reversed(result.stdout.splitlines()):
        m = re.search(r"(\d+) passed", line)
        if m:
            return int(m.group(1))
    return None


def _apply_substitutions(
    text: str,
    version: str,
    count: int | None,
    today: date,
) -> str:
    # 1. Badge de tests: tests-493%20passing-brightgreen
    if count is not None:
        text = re.sub(
            r"(img\.shields\.io/badge/tests-)\d+(%20passing-brightgreen)",
            rf"\g<1>{count}\g<2>",
            text,
        )

    # 2. Párrafo de revisores: **493 tests, CI separado
    if count is not None:
        text = re.sub(
            r"\*\*\d+ tests, CI separado",
            f"**{count} tests, CI separado",
            text,
        )

    # 3. Tabla de estado + §8: "493 passing, 0 regresiones"
    if count is not None:
        text = re.sub(
            r"\d+ passing, 0 regresiones",
            f"{count} passing, 0 regresiones",
            text,
        )

    # 4. Pie de página: versión, Python, conteo de tests y fecha.
    mes = _MESES_ES[today.month - 1]
    footer_pattern = (
        r"<sub>SNTO v[\w.]+ · Python ≥ 3\.12 · "
        r"(?P<count>\d+) tests passing · [^<]+</sub>"
    )

    def replace_footer(match: re.Match[str]) -> str:
        count_part = str(count) if count is not None else match.group("count")
        return (
            f"<sub>SNTO v{version} · Python ≥ 3.12 · {count_part} tests passing "
            f"· {mes} {today.year}</sub>"
        )

    text = re.sub(
        footer_pattern,
        replace_footer,
        text,
    )

    return text


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    check_only = "--check-version" in args

    version = _get_version()
    original = README.read_text(encoding="utf-8")

    if check_only:
        # CI: only check version — fast, no pytest collection needed.
        if f"SNTO v{version}" not in original:
            print(
                f"[version-sync] ERROR: README missing 'SNTO v{version}' "
                f"(pyproject.toml version).\n"
                f"Run: python scripts/sync_readme.py"
            )
            return 1
        print(f"[version-sync] OK - README version matches pyproject.toml ({version})")
        return 0

    # Full update mode
    count = _get_test_count()
    today = date.today()
    updated = _apply_substitutions(original, version, count, today)

    if updated == original:
        count_info = f"{count} tests" if count else "no change"
        print(f"[sync_readme] README already up to date (v{version}, {count_info})")
        return 0

    README.write_text(updated, encoding="utf-8")
    mes = _MESES_ES[today.month - 1]
    print(
        f"[sync_readme] README updated -> "
        f"v{version}, {count} tests, {mes} {today.year}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
