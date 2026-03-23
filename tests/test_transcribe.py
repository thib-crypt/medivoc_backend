"""Tests for the /api/v1/transcribe endpoint."""

import io
import pytest
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException
from tests.conftest import FREE_PROFILE


FAKE_AUDIO = b"\x00" * 1600  # 0.1 s at 16 kHz — passes _estimate_duration fallback
FAKE_TRANSCRIPT = "Le patient présente une fièvre à 38,5 degrés."


class TestTranscribeAuth:
    def test_no_token_returns_403(self, client):
        response = client.post(
            "/api/v1/transcribe",
            files={"file": ("audio.wav", FAKE_AUDIO, "audio/wav")},
        )
        assert response.status_code == 403

    def test_quota_exceeded_returns_402(self, client, mock_user):
        """When check_transcription_quota raises 402, the route must propagate it."""
        from app.main import app
        from app.dependencies import get_current_user, check_transcription_quota

        def raise_quota():
            raise HTTPException(status_code=402, detail="Quota atteint")

        app.dependency_overrides[get_current_user] = lambda: mock_user
        app.dependency_overrides[check_transcription_quota] = raise_quota
        try:
            response = client.post(
                "/api/v1/transcribe",
                files={"file": ("audio.wav", FAKE_AUDIO, "audio/wav")},
            )
            assert response.status_code == 402
        finally:
            app.dependency_overrides.clear()


class TestTranscribeValidation:
    def test_invalid_provider_returns_400(self, authed_client):
        response = authed_client.post(
            "/api/v1/transcribe",
            data={"provider": "openai"},
            files={"file": ("audio.wav", FAKE_AUDIO, "audio/wav")},
        )
        assert response.status_code == 400
        assert "Fournisseur invalide" in response.json()["detail"]

    def test_empty_audio_file_returns_400(self, authed_client):
        response = authed_client.post(
            "/api/v1/transcribe",
            data={"provider": "groq"},
            files={"file": ("audio.wav", b"", "audio/wav")},
        )
        assert response.status_code == 400
        assert "vide" in response.json()["detail"]

    def test_missing_file_returns_422(self, authed_client):
        response = authed_client.post("/api/v1/transcribe", data={"provider": "groq"})
        assert response.status_code == 422


class TestTranscribeGroq:
    def test_groq_transcription_success(self, authed_client):
        with patch("app.services.groq.transcribe", new=AsyncMock(return_value=FAKE_TRANSCRIPT)):
            response = authed_client.post(
                "/api/v1/transcribe",
                data={"provider": "groq"},
                files={"file": ("audio.wav", FAKE_AUDIO, "audio/wav")},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["text"] == FAKE_TRANSCRIPT
        assert data["provider"] == "groq"
        assert data["duration_seconds"] >= 0

    def test_groq_service_error_returns_502(self, authed_client):
        with patch("app.services.groq.transcribe", new=AsyncMock(side_effect=Exception("API down"))):
            response = authed_client.post(
                "/api/v1/transcribe",
                data={"provider": "groq"},
                files={"file": ("audio.wav", FAKE_AUDIO, "audio/wav")},
            )
        assert response.status_code == 502
        assert "groq" in response.json()["detail"]

    def test_groq_is_default_provider(self, authed_client):
        """When no provider is specified, groq should be used."""
        with patch("app.services.groq.transcribe", new=AsyncMock(return_value=FAKE_TRANSCRIPT)) as mock_groq:
            response = authed_client.post(
                "/api/v1/transcribe",
                files={"file": ("audio.wav", FAKE_AUDIO, "audio/wav")},
            )
        assert response.status_code == 200
        assert response.json()["provider"] == "groq"


class TestTranscribeDeepgram:
    def test_deepgram_transcription_success(self, authed_client):
        with patch("app.services.deepgram.transcribe", new=AsyncMock(return_value=FAKE_TRANSCRIPT)):
            response = authed_client.post(
                "/api/v1/transcribe",
                data={"provider": "deepgram"},
                files={"file": ("audio.wav", FAKE_AUDIO, "audio/wav")},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["text"] == FAKE_TRANSCRIPT
        assert data["provider"] == "deepgram"

    def test_deepgram_service_error_returns_502(self, authed_client):
        with patch("app.services.deepgram.transcribe", new=AsyncMock(side_effect=Exception("Timeout"))):
            response = authed_client.post(
                "/api/v1/transcribe",
                data={"provider": "deepgram"},
                files={"file": ("audio.wav", FAKE_AUDIO, "audio/wav")},
            )
        assert response.status_code == 502
        assert "deepgram" in response.json()["detail"]


class TestEstimateDuration:
    """Unit tests for the private _estimate_duration helper."""

    def test_fallback_for_unknown_format(self):
        from app.routers.transcribe import _estimate_duration

        audio = b"\x00" * 32000  # 2 seconds at 16 kHz (fallback formula)
        duration = _estimate_duration(audio, "audio.unknown")
        assert duration == pytest.approx(2.0, abs=0.1)

    def test_minimum_duration_is_one_second(self):
        from app.routers.transcribe import _estimate_duration

        duration = _estimate_duration(b"\x00" * 100, "tiny.wav")
        assert duration >= 1.0
