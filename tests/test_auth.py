"""Tests for authentication endpoints (/auth/me)."""

import pytest
from unittest.mock import MagicMock
from tests.conftest import MOCK_USER_ID, MOCK_EMAIL, FREE_PROFILE, PRO_PROFILE


class TestGetMe:
    def test_get_me_no_token_returns_403(self, client):
        response = client.get("/auth/me")
        assert response.status_code == 403

    def test_get_me_invalid_token_returns_401(self, client, monkeypatch):
        """An invalid token rejected by Supabase → 401."""
        def bad_get_user(token):
            raise Exception("invalid JWT")

        mock_supabase = MagicMock()
        mock_supabase.auth.get_user.side_effect = bad_get_user
        monkeypatch.setattr("app.dependencies.get_supabase", lambda: mock_supabase)

        response = client.get("/auth/me", headers={"Authorization": "Bearer bad-token"})
        assert response.status_code == 401

    def test_get_me_token_with_no_user_returns_401(self, client, monkeypatch):
        """Supabase returns a response but user is None → 401."""
        mock_supabase = MagicMock()
        mock_response = MagicMock()
        mock_response.user = None
        mock_supabase.auth.get_user.return_value = mock_response
        monkeypatch.setattr("app.dependencies.get_supabase", lambda: mock_supabase)

        response = client.get("/auth/me", headers={"Authorization": "Bearer some-token"})
        assert response.status_code == 401

    def test_get_me_authenticated_free_user(self, authed_client):
        response = authed_client.get("/auth/me")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == MOCK_USER_ID
        assert data["email"] == MOCK_EMAIL
        assert data["plan"] == "free"
        assert data["minutes_used_this_month"] == FREE_PROFILE["minutes_used_this_month"]
        assert data["quota_reset_at"] == FREE_PROFILE["quota_reset_at"]

    def test_get_me_authenticated_pro_user(self, pro_client):
        response = pro_client.get("/auth/me")
        assert response.status_code == 200
        data = response.json()
        assert data["plan"] == "pro"

    def test_get_me_response_has_required_fields(self, authed_client):
        response = authed_client.get("/auth/me")
        data = response.json()
        required_fields = {"id", "email", "plan", "minutes_used_this_month", "quota_reset_at"}
        assert required_fields.issubset(data.keys())
