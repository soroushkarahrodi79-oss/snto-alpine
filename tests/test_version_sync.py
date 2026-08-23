"""CI guards for canonical project and publication metadata."""
import json
import re
import tomllib
from datetime import date
from pathlib import Path

from scripts.sync_readme import _apply_substitutions

ROOT = Path(__file__).parent.parent
# These DOIs belong to the BASE observatory, not to the Alpine Edition. The
# Alpine Edition has no Zenodo deposit of its own, so these must never be
# presented as this repository's own identifiers — only cited as attribution.
BASE_CONCEPT_DOI = "10.5281/zenodo.20818269"
BASE_V2_CANONICAL_DOI = "10.5281/zenodo.21472647"


def test_readme_version_matches_pyproject() -> None:
    with open(ROOT / "pyproject.toml", "rb") as f:
        version = tomllib.load(f)["project"]["version"]
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert f"SNTO v{version}" in readme, (
        f"README no contiene 'SNTO v{version}' (versión de pyproject.toml). "
        f"Ejecuta: python scripts/sync_readme.py"
    )


def test_citation_version_matches_pyproject() -> None:
    with open(ROOT / "pyproject.toml", "rb") as f:
        version = tomllib.load(f)["project"]["version"]
    citation = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    match = re.search(r'^version:\s*["\']?([^"\'\s]+)', citation, re.MULTILINE)
    assert match is not None, "CITATION.cff debe declarar version"
    assert match.group(1) == version, (
        "CITATION.cff y pyproject.toml deben declarar la misma versión"
    )


def test_alpine_edition_declares_no_own_doi() -> None:
    """The Alpine Edition has no Zenodo deposit; it must not claim a DOI.

    CITATION.cff must not carry a top-level ``doi:`` field, and the README must
    not render a DOI shields.io badge. The base DOIs may still appear, but only
    inside an attribution/disclaimer context (verified separately).
    """
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    citation = (ROOT / "CITATION.cff").read_text(encoding="utf-8")

    assert not re.search(r'^doi:\s', citation, re.MULTILINE), (
        "CITATION.cff no debe declarar un DOI propio: la Edición Alpina no "
        "tiene depósito Zenodo."
    )
    assert "img.shields.io/badge/DOI" not in readme, (
        "El README no debe mostrar un badge de DOI propio."
    )


def test_base_dois_appear_only_as_attribution() -> None:
    """If the base DOIs are mentioned, it must be as attribution, not as ours."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    citation = (ROOT / "CITATION.cff").read_text(encoding="utf-8")

    # In CITATION they may only appear inside a comment (lines starting with #).
    for line in citation.splitlines():
        if BASE_CONCEPT_DOI in line or BASE_V2_CANONICAL_DOI in line:
            assert line.lstrip().startswith("#"), (
                f"El DOI base solo puede aparecer en comentarios de CITATION: {line!r}"
            )

    # In the README, the base DOIs must sit near an attribution/disclaimer word.
    if BASE_CONCEPT_DOI in readme:
        idx = readme.index(BASE_CONCEPT_DOI)
        window = readme[max(0, idx - 400):idx + 100].lower()
        disclaimer_words = ("base", "no los uses", "no aplica", "pertenec")
        assert any(w in window for w in disclaimer_words), (
            "El DOI base en el README debe ir acompañado de una nota de atribución."
        )


def test_zenodo_metadata_is_alpine_and_release_agnostic() -> None:
    metadata = json.loads((ROOT / ".zenodo.json").read_text(encoding="utf-8"))

    assert "Alpine Edition" in metadata["title"], (
        ".zenodo.json debe titularse como la Edición Alpina, no como el base"
    )
    assert "version" not in metadata, (
        "La versión de Zenodo debe proceder del tag de GitHub, no quedar fija"
    )


def test_alpine_deploy_is_manual_disabled_and_isolated() -> None:
    """A normal merge must never deploy Alpine over the base application."""
    workflow = (
        ROOT / ".github" / "workflows" / "deploy-azure-container-apps.yml"
    ).read_text(encoding="utf-8")

    assert "workflow_run:" not in workflow
    assert "workflow_dispatch:" in workflow
    assert "github.ref == 'refs/heads/main'" in workflow
    assert "SNTO_ALPINE_DEPLOY_ENABLED" in workflow
    assert "inputs.confirm_target == 'alpine-production'" in workflow
    assert "RESOURCE_GROUP: rg-snto-alpine-app" in workflow
    assert "APP_NAME: snto-alpine" in workflow
    assert "IMAGE_REPO: snto-alpine" in workflow


def test_alpine_roadmap_is_the_documented_authority() -> None:
    roadmap_index = (ROOT / "docs" / "roadmap" / "README.md").read_text(
        encoding="utf-8"
    )
    alpine_roadmap = ROOT / "docs" / "roadmap" / "alpine-v0.1.md"

    assert alpine_roadmap.is_file()
    assert "alpine-v0.1.md" in roadmap_index
    assert "No representan las versiones" in roadmap_index


def test_readme_sync_preserves_count_when_pytest_is_unavailable() -> None:
    footer = (
        "<sub>SNTO v1.0.0 · Python ≥ 3.12 · 927 tests passing · junio 2026</sub>"
    )

    updated = _apply_substitutions(
        footer,
        version="2.1.0.dev0",
        count=None,
        today=date(2026, 7, 23),
    )

    assert updated == (
        "<sub>SNTO v2.1.0.dev0 · Python ≥ 3.12 · "
        "927 tests passing · julio 2026</sub>"
    )
