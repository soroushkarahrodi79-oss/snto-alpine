"""Unit tests for src.validation.cetursa_snow (issue #21). No live network.

Two fixtures:

* ``cetursa_parte_2026-08-23.json`` — a REAL payload captured live from
  Cetursa's Umbraco backend
  (``umb.sierranevada.es/umbraco/api/parte/previsiones?culture=es``,
  2026-08-23), verbatim for the snow-relevant sections (``general``,
  ``estadoestacion``, ``nieve``, ``meteorologia``). The bulky, snow-irrelevant
  lists (remontes, pistas, actividades, parkings, restauración) and the
  translation ``Diccionario`` were dropped to keep the fixture light; nothing in
  the retained sections was altered. Captured out of season (station closed), so
  it is exactly the case that exercises the honest sentinel -> ``None`` handling.
* ``_OPEN_SEASON`` — a small, hand-built parte in Cetursa's real schema, used
  only to exercise the numeric-parse path (real cm depths, open station). It is
  clearly synthetic: live winter data cannot be captured in August, and the
  backend serves no historical archive, so this is not presented as a real
  reading — only as a schema-faithful shape to test parsing.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.validation.cetursa_snow import (
    CETURSA_PARTE_URL,
    CetursaSnowReport,
    CetursaUnavailable,
    fetch_snow_report,
    has_snow_data,
    parse_snow_report,
)

_FIXTURE = Path(__file__).parent / "fixtures" / "cetursa_parte_2026-08-23.json"


def _real_payload() -> dict:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


# A schema-faithful OPEN-season parte (synthetic — see module docstring).
_OPEN_SEASON = {
    "Partes": [
        {
            "Name": "Hoy",
            "Parte": {
                "partenieve": {
                    "general": {
                        "fecha": "15/02/2025",
                        "hora": "08:30:00",
                        "textoprevisionapertura": "Estación abierta.",
                    },
                    "estadoestacion": "Abierta",
                    "nieve": {
                        "espesorminimo": "40",
                        "espesormaximo": "120",
                        "calidadnieve": "Polvo     ",
                        "superficieinnivada": "45 km2.",
                        "espesorveleta": "120",
                        "calidadveleta": "Polvo     ",
                        "espesorborreguiles": "80",
                        "calidadborreguiles": "Dura      ",
                        "espesorlaguna": "",
                        "calidadlaguna": "CERRADA   ",
                        "espesorlomadilar": "60",
                        "calidadlomadilar": "Primavera ",
                        "espesorparador": "40",
                        "calidadparador": "Dura      ",
                        "espesorrio": "50",
                        "calidadrio": "Polvo     ",
                    },
                    "meteorologia": {
                        "paginas": {
                            "pagina": [
                                {
                                    "temperaturaborreguiles": "-3",
                                    "temperaturapradollano": "-1",
                                    "temperaturaveleta": "-8",
                                },
                                {"textoprevision1dia": "..."},
                                {"riesgoavalancha": "3"},
                            ]
                        }
                    },
                }
            },
        }
    ]
}


def _mock_response(payload_bytes: bytes):
    cm = MagicMock()
    cm.__enter__.return_value.read.return_value = payload_bytes
    cm.__exit__.return_value = False
    return cm


# ── fetch_snow_report ───────────────────────────────────────────────────────


def test_fetch_is_a_single_unauthenticated_get() -> None:
    payload = json.dumps(_real_payload()).encode("utf-8")
    calls = []

    def _fake_urlopen(req, timeout=None):
        calls.append(req)
        return _mock_response(payload)

    with patch("urllib.request.urlopen", side_effect=_fake_urlopen):
        result = fetch_snow_report()

    assert len(calls) == 1  # no two-step handshake, unlike AEMET
    req = calls[0]
    assert req.full_url == CETURSA_PARTE_URL
    # No api_key / Authorization header — the backend is open.
    header_names = {k.lower() for k in req.headers}
    assert "api_key" not in header_names
    assert "authorization" not in header_names
    assert result.url == CETURSA_PARTE_URL
    assert result.fetched_at


def test_fetch_rejects_unexpected_shape() -> None:
    payload = json.dumps({"not": "a parte"}).encode("utf-8")
    with patch("urllib.request.urlopen", return_value=_mock_response(payload)):
        with pytest.raises(CetursaUnavailable):
            fetch_snow_report()


# ── parse_snow_report against the REAL (closed-season) payload ───────────────


def test_parses_real_closed_season_metadata() -> None:
    report = parse_snow_report(_real_payload())
    assert isinstance(report, CetursaSnowReport)
    assert report.fecha == "23/08/2026"
    assert report.hora == "18:31:25"
    assert report.estado_estacion == "Cerrada"
    assert report.estacion_abierta is False
    assert "Temporada de verano finalizada" in report.aviso


def test_closed_season_espesores_are_none_not_zero() -> None:
    """The whole point of the honest-fallback convention: sentinels/empties
    must be None, never a fabricated 0 cm."""
    report = parse_snow_report(_real_payload())
    # espesorminimo == "9999" is the closed sentinel -> None.
    assert report.espesor_min_cm is None
    # Every listed sector has an empty espesor out of season -> None.
    assert report.stations  # sectors ARE listed even when closed
    assert all(s.espesor_cm is None for s in report.stations)
    assert has_snow_data(report) is False


def test_real_sectors_and_quality_labels() -> None:
    report = parse_snow_report(_real_payload())
    sectors = {s.sector for s in report.stations}
    # The real payload lists these skiable-domain sectors.
    assert {"veleta", "borreguiles", "laguna", "lomadilar"} <= sectors
    borreguiles = next(s for s in report.stations if s.sector == "borreguiles")
    assert borreguiles.display_name == "Borreguiles"
    assert borreguiles.calidad == "CERRADA"  # whitespace stripped


def test_superficie_innivada_parsed_but_flagged_closed() -> None:
    """superficieinnivada is present year-round; parsed, but estacion_abierta
    tells the consumer it is not a live measurement."""
    report = parse_snow_report(_real_payload())
    assert report.superficie_innivada_km2 == 1143.0
    assert report.estacion_abierta is False


def test_real_temperatures_and_avalanche_risk() -> None:
    report = parse_snow_report(_real_payload())
    assert report.temp_pradollano_c == 16.0
    assert report.temp_borreguiles_c == 12.0
    assert report.temp_veleta_c == 8.0
    assert report.riesgo_aludes == 0


def test_prevision_parte_is_selectable() -> None:
    report = parse_snow_report(_real_payload(), parte_name="Previsión")
    assert report.parte_name == "Previsión"


def test_unknown_parte_name_raises() -> None:
    with pytest.raises(ValueError, match="not present"):
        parse_snow_report(_real_payload(), parte_name="Mañana")


def test_parse_rejects_unexpected_shape() -> None:
    with pytest.raises(ValueError):
        parse_snow_report({"not": "a parte"})
    with pytest.raises(ValueError):
        parse_snow_report([1, 2, 3])


# ── parse_snow_report against the OPEN-season (synthetic) shape ──────────────


def test_parses_open_season_real_depths() -> None:
    report = parse_snow_report(_OPEN_SEASON)
    assert report.estacion_abierta is True
    assert report.espesor_min_cm == 40.0
    assert report.espesor_max_cm == 120.0
    veleta = next(s for s in report.stations if s.sector == "veleta")
    assert veleta.espesor_cm == 120.0
    assert veleta.calidad == "Polvo"
    # A sector that is closed mid-season still degrades to None, not 0.
    laguna = next(s for s in report.stations if s.sector == "laguna")
    assert laguna.espesor_cm is None
    assert has_snow_data(report) is True


def test_open_season_avalanche_and_temps() -> None:
    report = parse_snow_report(_OPEN_SEASON)
    assert report.riesgo_aludes == 3
    assert report.temp_borreguiles_c == -3.0
    assert report.temp_veleta_c == -8.0
