"""Tests for /api/v1/process-text and /api/v1/process-text/stream."""

import json
import pytest
from unittest.mock import AsyncMock, patch


FAKE_LLM_RESULT = "Compte-rendu médical structuré : le patient présente..."


async def fake_stream_text(*args, **kwargs):
    for chunk in ["Compte-rendu ", "médical ", "structuré."]:
        yield chunk


class TestProcessTextAuth:
    def test_no_token_returns_403(self, client):
        response = client.post(
            "/api/v1/process-text",
            json={"text": "Bonjour", "instructions": ""},
        )
        assert response.status_code == 403

    def test_no_token_stream_returns_403(self, client):
        response = client.post(
            "/api/v1/process-text/stream",
            json={"text": "Bonjour", "instructions": ""},
        )
        assert response.status_code == 403


class TestProcessTextValidation:
    def test_empty_text_returns_400(self, authed_client):
        response = authed_client.post(
            "/api/v1/process-text",
            json={"text": "   ", "instructions": ""},
        )
        assert response.status_code == 400
        assert "vide" in response.json()["detail"]

    def test_empty_text_stream_returns_400(self, authed_client):
        response = authed_client.post(
            "/api/v1/process-text/stream",
            json={"text": "", "instructions": ""},
        )
        assert response.status_code == 400

    def test_missing_text_field_returns_422(self, authed_client):
        response = authed_client.post(
            "/api/v1/process-text",
            json={"instructions": ""},
        )
        assert response.status_code == 422


class TestProcessTextSync:
    def test_success_returns_result(self, authed_client):
        with patch("app.routers.process_text.process_text", new=AsyncMock(return_value=FAKE_LLM_RESULT)):
            response = authed_client.post(
                "/api/v1/process-text",
                json={"text": "Le patient souffre de fièvre.", "instructions": "Structurer le compte-rendu."},
            )
        assert response.status_code == 200
        assert response.json()["result"] == FAKE_LLM_RESULT

    def test_llm_error_returns_502(self, authed_client):
        with patch("app.routers.process_text.process_text", new=AsyncMock(side_effect=Exception("Gemini down"))):
            response = authed_client.post(
                "/api/v1/process-text",
                json={"text": "Texte médical."},
            )
        assert response.status_code == 502
        assert "LLM" in response.json()["detail"]

    def test_with_files_parameter(self, authed_client):
        payload = {
            "text": "Analyser ce document.",
            "files": [{"mime_type": "application/pdf", "data": "ZmFrZQ=="}],
        }
        with patch("app.routers.process_text.process_text", new=AsyncMock(return_value="Analyse OK")):
            response = authed_client.post("/api/v1/process-text", json=payload)
        assert response.status_code == 200

    def test_custom_model_is_forwarded(self, authed_client):
        with patch("app.routers.process_text.process_text", new=AsyncMock(return_value="OK")) as mock_fn:
            authed_client.post(
                "/api/v1/process-text",
                json={"text": "Hello", "model": "gemini-1.5-pro"},
            )
            call_args = mock_fn.call_args
            assert call_args[0][2] == "gemini-1.5-pro"  # positional arg: model


class TestProcessTextStream:
    def test_stream_returns_sse_content_type(self, authed_client):
        with patch("app.routers.process_text.stream_text", new=fake_stream_text):
            response = authed_client.post(
                "/api/v1/process-text/stream",
                json={"text": "Texte médical."},
            )
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

    def test_stream_contains_chunks_and_done(self, authed_client):
        with patch("app.routers.process_text.stream_text", new=fake_stream_text):
            response = authed_client.post(
                "/api/v1/process-text/stream",
                json={"text": "Texte médical."},
            )
        body = response.text
        assert "[DONE]" in body
        # Each chunk should be a valid SSE data line
        lines = [l for l in body.splitlines() if l.startswith("data: ")]
        assert len(lines) > 0
        # All data lines except [DONE] should be valid JSON
        for line in lines:
            payload = line[len("data: "):]
            if payload != "[DONE]":
                parsed = json.loads(payload)
                assert "chunk" in parsed or "error" in parsed

    def test_stream_no_cache_headers(self, authed_client):
        with patch("app.routers.process_text.stream_text", new=fake_stream_text):
            response = authed_client.post(
                "/api/v1/process-text/stream",
                json={"text": "Test."},
            )
        assert response.headers.get("cache-control") == "no-cache"
