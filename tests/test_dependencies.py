"""Unit tests for dependency helper functions in app/dependencies.py."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, AsyncMock
from fastapi import HTTPException

from tests.conftest import MOCK_USER_ID, FREE_PROFILE, PRO_PROFILE, EXHAUSTED_PROFILE


# ---------------------------------------------------------------------------
# check_quota_from_profile — pure synchronous function, no external deps
# ---------------------------------------------------------------------------

class TestCheckQuotaFromProfile:
    def test_pro_plan_always_passes(self):
        from app.dependencies import check_quota_from_profile

        # Should not raise for any minutes_used value
        check_quota_from_profile({**PRO_PROFILE, "minutes_used_this_month": 999})

    def test_free_plan_under_quota_passes(self):
        from app.dependencies import check_quota_from_profile

        check_quota_from_profile({**FREE_PROFILE, "minutes_used_this_month": 0})
        check_quota_from_profile({**FREE_PROFILE, "minutes_used_this_month": 29.99})

    def test_free_plan_at_quota_raises_402(self):
        from app.dependencies import check_quota_from_profile

        with pytest.raises(HTTPException) as exc_info:
            check_quota_from_profile(EXHAUSTED_PROFILE)
        assert exc_info.value.status_code == 402

    def test_free_plan_over_quota_raises_402(self):
        from app.dependencies import check_quota_from_profile

        with pytest.raises(HTTPException) as exc_info:
            check_quota_from_profile({**FREE_PROFILE, "minutes_used_this_month": 50})
        assert exc_info.value.status_code == 402

    def test_402_detail_mentions_pro_plan(self):
        from app.dependencies import check_quota_from_profile

        with pytest.raises(HTTPException) as exc_info:
            check_quota_from_profile(EXHAUSTED_PROFILE)
        assert "Pro" in exc_info.value.detail

    def test_missing_minutes_used_treated_as_zero(self):
        from app.dependencies import check_quota_from_profile

        profile = {**FREE_PROFILE}
        del profile["minutes_used_this_month"]
        # Should not raise — 0 minutes used, well under quota
        check_quota_from_profile(profile)


# ---------------------------------------------------------------------------
# get_profile_by_user_id — async, calls Supabase and handles quota reset
# ---------------------------------------------------------------------------

class TestGetProfileByUserId:
    @pytest.mark.asyncio
    async def test_returns_profile_when_found(self, monkeypatch):
        from app.dependencies import get_profile_by_user_id

        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=FREE_PROFILE
        )
        monkeypatch.setattr("app.dependencies.get_supabase", lambda: mock_db)

        profile = await get_profile_by_user_id(MOCK_USER_ID)
        assert profile["id"] == MOCK_USER_ID
        assert profile["plan"] == "free"

    @pytest.mark.asyncio
    async def test_raises_404_when_not_found(self, monkeypatch):
        from app.dependencies import get_profile_by_user_id

        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=None
        )
        monkeypatch.setattr("app.dependencies.get_supabase", lambda: mock_db)

        with pytest.raises(HTTPException) as exc_info:
            await get_profile_by_user_id(MOCK_USER_ID)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_resets_quota_when_reset_date_passed(self, monkeypatch):
        """When quota_reset_at is in the past, minutes_used should be reset to 0."""
        from app.dependencies import get_profile_by_user_id
        from tests.conftest import make_supabase_mock

        past_reset = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        profile_with_past_reset = {
            **EXHAUSTED_PROFILE,
            "quota_reset_at": past_reset,
        }

        mock_db = make_supabase_mock()
        # Override execute return value so the profile read returns our dict
        mock_db.execute.return_value = MagicMock(data=profile_with_past_reset)
        monkeypatch.setattr("app.dependencies.get_supabase", lambda: mock_db)

        profile = await get_profile_by_user_id(MOCK_USER_ID)
        assert profile["minutes_used_this_month"] == 0

    @pytest.mark.asyncio
    async def test_does_not_reset_quota_when_date_in_future(self, monkeypatch):
        from app.dependencies import get_profile_by_user_id

        future_reset = "2099-01-01T00:00:00+00:00"
        profile_future = {**EXHAUSTED_PROFILE, "quota_reset_at": future_reset}

        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=profile_future
        )
        monkeypatch.setattr("app.dependencies.get_supabase", lambda: mock_db)

        profile = await get_profile_by_user_id(MOCK_USER_ID)
        # Minutes should NOT have been reset
        assert profile["minutes_used_this_month"] == EXHAUSTED_PROFILE["minutes_used_this_month"]


# ---------------------------------------------------------------------------
# get_current_user_from_token — used by WebSocket routes
# ---------------------------------------------------------------------------

class TestGetCurrentUserFromToken:
    @pytest.mark.asyncio
    async def test_valid_token_returns_user(self, monkeypatch):
        from app.dependencies import get_current_user_from_token

        mock_user = MagicMock()
        mock_user.id = MOCK_USER_ID
        mock_response = MagicMock()
        mock_response.user = mock_user

        mock_db = MagicMock()
        mock_db.auth.get_user.return_value = mock_response
        monkeypatch.setattr("app.dependencies.get_supabase", lambda: mock_db)

        user = await get_current_user_from_token("valid-token")
        assert user.id == MOCK_USER_ID

    @pytest.mark.asyncio
    async def test_exception_raises_401(self, monkeypatch):
        from app.dependencies import get_current_user_from_token

        mock_db = MagicMock()
        mock_db.auth.get_user.side_effect = Exception("network error")
        monkeypatch.setattr("app.dependencies.get_supabase", lambda: mock_db)

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user_from_token("bad-token")
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_null_user_raises_401(self, monkeypatch):
        from app.dependencies import get_current_user_from_token

        mock_response = MagicMock()
        mock_response.user = None
        mock_db = MagicMock()
        mock_db.auth.get_user.return_value = mock_response
        monkeypatch.setattr("app.dependencies.get_supabase", lambda: mock_db)

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user_from_token("token-without-user")
        assert exc_info.value.status_code == 401
