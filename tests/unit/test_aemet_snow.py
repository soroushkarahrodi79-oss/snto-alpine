"""Unit tests for src.validation.aemet_snow (issue #21). No live network calls."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from src.validation.aemet_snow import (
    API_KEY_ENV_VAR,
    SIERRA_NEVADA_AREA_CODE,
    AemetCredentialsMissing,
    fetch_mountain_forecast,
    fetch_nivological_info,
    has_credentials,
    parse_mountain_forecast,
)

# A real response captured live from AEMET OpenData
# (GET /api/prediccion/especifica/montaña/pasada/area/nev1/dia/0,
# 2026-08-23), trimmed of nothing — this is the actual payload shape, not a
# guess. Kept as a fixture so the parser is tested against real AEMET output
# without requiring a live API key in CI.
_REAL_NEV1_FORECAST = [
    {
        "origen": {
            "productor": "Agencia Estatal de Meteorología - AEMET - Gobierno de España",
            "web": "http://www.aemet.es",
            "tipo": "Predicción de montaña",
            "language": "es",
            "copyright": "© AEMET.",
            "notaLegal": "http://www.aemet.es/es/nota_legal",
        },
        "seccion": [
            {
                "apartado": [
                    {
                        "cabecera": "Estado del cielo",
                        "texto": "Poco nuboso o despejado.",
                        "nombre": "nubosidad",
                    },
                    {
                        "cabecera": "Precipitaciones",
                        "texto": "No se esperan.",
                        "nombre": "pcp",
                    },
                    {
                        "cabecera": "Tormentas",
                        "texto": "No se esperan.",
                        "nombre": "tormentas",
                    },
                    {
                        "cabecera": "Temperaturas",
                        "texto": "Con pocos cambios.",
                        "nombre": "temperatura",
                    },
                    {
                        "cabecera": "Viento",
                        "texto": "Fuerte del suroeste en cotas altas.",
                        "nombre": "viento",
                    },
                ],
                "lugar": [],
                "parrafo": [],
                "nombre": "prediccion",
            },
            {
                "apartado": [
                    {
                        "cabecera": "Altitud de la isoterma de 0 ºC",
                        "texto": "4600 m",
                        "nombre": "isocero",
                    },
                    {
                        "cabecera": "Altitud de la isoterma de -10 ºC",
                        "texto": "6200 m",
                        "nombre": "iso10",
                    },
                    {
                        "cabecera": "Viento en atmósfera libre a 1500 metros",
                        "texto": "S 30 km/h",
                        "nombre": "v1500",
                    },
                    {
                        "cabecera": "Viento en atmósfera libre a 3000 metros",
                        "texto": "SW 60 km/h",
                        "nombre": "v3000",
                    },
                ],
                "lugar": [],
                "parrafo": [],
                "nombre": "atmosferalibre",
            },
            {
                "apartado": [],
                "lugar": [
                    {
                        "minima": 15,
                        "stminima": 15,
                        "maxima": 20,
                        "stmaxima": 20,
                        "nombre": "Pradollano",
                        "altitud": "2165 m",
                    },
                    {
                        "minima": 11,
                        "stminima": 11,
                        "maxima": 15,
                        "stmaxima": 15,
                        "nombre": "Borreguiles",
                        "altitud": "2665 m",
                    },
                ],
                "parrafo": [],
                "nombre": "sensacion_termica",
            },
        ],
        "id": "nev1",
        "nombre": "Predicción",
    }
]


@pytest.fixture(autouse=True)
def _clear_api_key(monkeypatch):
    monkeypatch.delenv(API_KEY_ENV_VAR, raising=False)


def _mock_response(payload_bytes: bytes):
    cm = MagicMock()
    cm.__enter__.return_value.read.return_value = payload_bytes
    cm.__exit__.return_value = False
    return cm


def test_has_credentials_false_without_env_var() -> None:
    assert has_credentials() is False


def test_has_credentials_true_with_env_var(monkeypatch) -> None:
    monkeypatch.setenv(API_KEY_ENV_VAR, "fake-key")
    assert has_credentials() is True


def test_fetch_raises_without_credentials() -> None:
    with pytest.raises(AemetCredentialsMissing, match=API_KEY_ENV_VAR):
        fetch_nivological_info(area="0")
    with pytest.raises(AemetCredentialsMissing):
        fetch_mountain_forecast()


def test_fetch_mountain_forecast_follows_the_two_step_pattern(monkeypatch) -> None:
    monkeypatch.setenv(API_KEY_ENV_VAR, "fake-key")
    envelope = json.dumps(
        {"descripcion": "exito", "estado": 200, "datos": "https://data.example/x"}
    ).encode("utf-8")
    payload = json.dumps(_REAL_NEV1_FORECAST).encode("utf-8")

    responses = [_mock_response(envelope), _mock_response(payload)]
    with patch("urllib.request.urlopen", side_effect=responses) as mock_open:
        result = fetch_mountain_forecast()

    assert mock_open.call_count == 2
    assert result.area == SIERRA_NEVADA_AREA_CODE
    assert isinstance(result.raw, list)
    assert result.fetched_at


def test_second_call_uses_the_datos_url_unauthenticated(monkeypatch) -> None:
    monkeypatch.setenv(API_KEY_ENV_VAR, "fake-key")
    envelope = json.dumps(
        {"estado": 200, "datos": "https://data.example/specific-url"}
    ).encode("utf-8")
    payload = b'{"ok": true}'

    calls = []

    def _fake_urlopen(req, timeout=None):
        if hasattr(req, "headers"):
            calls.append(dict(req.headers))
        else:
            calls.append({})
        return responses.pop(0)

    responses = [_mock_response(envelope), _mock_response(payload)]
    with patch("urllib.request.urlopen", side_effect=_fake_urlopen):
        fetch_mountain_forecast(dia="1")

    assert any(k.lower() == "api_key" for k in calls[0])
    # Step 2 is a plain string URL, not a Request carrying our api_key header.
    assert calls[1] == {}


def test_raises_when_envelope_has_no_data_url(monkeypatch) -> None:
    monkeypatch.setenv(API_KEY_ENV_VAR, "fake-key")
    envelope = json.dumps({"estado": 404, "descripcion": "not found"}).encode("utf-8")
    with patch("urllib.request.urlopen", return_value=_mock_response(envelope)):
        with pytest.raises(RuntimeError, match="did not return a data URL"):
            fetch_nivological_info(area="0")


def test_nivologica_area_0_and_1_only_no_sierra_nevada_default() -> None:
    """Verified live: nivológica only accepts area 0/1 (Pyrenees); nev1 404s.
    fetch_nivological_info takes no default precisely so a caller can't
    accidentally assume Sierra Nevada coverage that doesn't exist."""
    import inspect

    sig = inspect.signature(fetch_nivological_info)
    assert sig.parameters["area"].default is inspect.Parameter.empty


def test_non_json_payload_degrades_to_text(monkeypatch) -> None:
    """The real nivológica endpoint returns plain-text prose, not JSON."""
    monkeypatch.setenv(API_KEY_ENV_VAR, "fake-key")
    envelope = json.dumps({"estado": 200, "datos": "https://data.example/x"}).encode(
        "utf-8"
    )
    payload = "Información nivológica para el Pirineo Catalán".encode("utf-8")

    responses = [_mock_response(envelope), _mock_response(payload)]
    with patch("urllib.request.urlopen", side_effect=responses):
        result = fetch_nivological_info(area="0")

    assert isinstance(result.raw, str)
    assert "nivol" in result.raw.lower()


def test_latin1_encoded_json_still_parses(monkeypatch) -> None:
    """AEMET data URLs are inconsistently encoded across endpoints; a JSON
    body served as latin-1 must still parse as JSON, not fall through to text."""
    monkeypatch.setenv(API_KEY_ENV_VAR, "fake-key")
    envelope = json.dumps({"estado": 200, "datos": "https://data.example/x"}).encode(
        "utf-8"
    )
    payload = json.dumps({"cabecera": "Predicción"}, ensure_ascii=False).encode(
        "latin-1"
    )

    responses = [_mock_response(envelope), _mock_response(payload)]
    with patch("urllib.request.urlopen", side_effect=responses):
        result = fetch_mountain_forecast()

    assert result.raw == {"cabecera": "Predicción"}


def test_mountain_forecast_defaults_to_sierra_nevada_today(monkeypatch) -> None:
    monkeypatch.setenv(API_KEY_ENV_VAR, "fake-key")
    envelope = json.dumps({"estado": 200, "datos": "https://data.example/x"}).encode(
        "utf-8"
    )
    payload = json.dumps(_REAL_NEV1_FORECAST).encode("utf-8")
    responses = [_mock_response(envelope), _mock_response(payload)]
    with patch("urllib.request.urlopen", side_effect=responses):
        result = fetch_mountain_forecast()
    assert result.area == "nev1"
    assert "dia/0" in result.endpoint


# ── parse_mountain_forecast, against the real captured response ─────────────


def test_parses_real_response_free_text_categories() -> None:
    summary = parse_mountain_forecast(_REAL_NEV1_FORECAST)
    assert summary.area == "nev1"
    assert summary.cloud == "Poco nuboso o despejado."
    assert summary.precipitation == "No se esperan."
    assert summary.storms == "No se esperan."


def test_parses_real_isotherm_altitudes() -> None:
    summary = parse_mountain_forecast(_REAL_NEV1_FORECAST)
    assert summary.isotherm_0c_m == 4600.0
    assert summary.isotherm_minus10c_m == 6200.0
    assert summary.wind_1500m == "S 30 km/h"
    assert summary.wind_3000m == "SW 60 km/h"


def test_parses_real_place_readings() -> None:
    summary = parse_mountain_forecast(_REAL_NEV1_FORECAST)
    names = {p.name for p in summary.places}
    assert names == {"Pradollano", "Borreguiles"}
    pradollano = next(p for p in summary.places if p.name == "Pradollano")
    assert pradollano.altitude_m == 2165.0
    assert pradollano.min_temp_c == 15
    assert pradollano.max_temp_c == 20


def test_parse_tolerates_missing_sections() -> None:
    minimal = [{"id": "nev1", "nombre": "Predicción", "seccion": []}]
    summary = parse_mountain_forecast(minimal)
    assert summary.cloud is None
    assert summary.isotherm_0c_m is None
    assert summary.places == []


def test_parse_rejects_an_unexpected_shape() -> None:
    with pytest.raises(ValueError):
        parse_mountain_forecast({"not": "a list"})
    with pytest.raises(ValueError):
        parse_mountain_forecast([])
