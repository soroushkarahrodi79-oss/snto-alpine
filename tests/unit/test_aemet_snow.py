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
)


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
        fetch_nivological_info()
    with pytest.raises(AemetCredentialsMissing):
        fetch_mountain_forecast()


def test_fetch_nivological_info_follows_the_two_step_pattern(monkeypatch) -> None:
    monkeypatch.setenv(API_KEY_ENV_VAR, "fake-key")
    envelope = json.dumps(
        {"descripcion": "exito", "estado": 200, "datos": "https://data.example/x"}
    ).encode("utf-8")
    payload = json.dumps({"bulletin": "nieve reciente en cotas altas"}).encode("utf-8")

    responses = [_mock_response(envelope), _mock_response(payload)]
    with patch("urllib.request.urlopen", side_effect=responses) as mock_open:
        result = fetch_nivological_info()

    assert mock_open.call_count == 2
    assert result.area == SIERRA_NEVADA_AREA_CODE
    assert result.raw == {"bulletin": "nieve reciente en cotas altas"}
    assert result.fetched_at


def test_second_call_uses_the_datos_url_unauthenticated(monkeypatch) -> None:
    monkeypatch.setenv(API_KEY_ENV_VAR, "fake-key")
    envelope = json.dumps(
        {"estado": 200, "datos": "https://data.example/specific-url"}
    ).encode("utf-8")
    payload = b'{"ok": true}'

    calls = []

    def _fake_urlopen(req, timeout=None):
        # Record whether this call carried an api_key header (step 1) or not (step 2).
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
            fetch_nivological_info()


def test_non_json_payload_degrades_to_text(monkeypatch) -> None:
    monkeypatch.setenv(API_KEY_ENV_VAR, "fake-key")
    envelope = json.dumps({"estado": 200, "datos": "https://data.example/x"}).encode(
        "utf-8"
    )
    payload = "boletín en texto plano, no JSON".encode("latin-1")

    responses = [_mock_response(envelope), _mock_response(payload)]
    with patch("urllib.request.urlopen", side_effect=responses):
        result = fetch_nivological_info()

    assert isinstance(result.raw, str)
    assert "bolet" in result.raw


def test_mountain_forecast_defaults_to_sierra_nevada_today(monkeypatch) -> None:
    monkeypatch.setenv(API_KEY_ENV_VAR, "fake-key")
    envelope = json.dumps({"estado": 200, "datos": "https://data.example/x"}).encode(
        "utf-8"
    )
    payload = b"{}"
    responses = [_mock_response(envelope), _mock_response(payload)]
    with patch("urllib.request.urlopen", side_effect=responses):
        result = fetch_mountain_forecast()
    assert result.area == "nev1"
    assert "dia/0" in result.endpoint
