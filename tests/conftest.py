"""
Shared fixtures and setup for all tests.

Environment variables are set BEFORE any app import so that Pydantic Settings
can initialise correctly without a real .env file.
"""

import os

# Must come before any app import — Pydantic Settings reads these at instantiation
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "test-service-key")
os.environ.setdefault("GROQ_API_KEY", "test-groq-key")
os.environ.setdefault("DEEPGRAM_API_KEY", "test-deepgram-key")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("STRIPE_SECRET_KEY", "sk_test_fake123")
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_fake123")
os.environ.setdefault("STRIPE_PRO_PRICE_ID", "price_fake123")

import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

MOCK_USER_ID = "user-abc-123"
MOCK_EMAIL = "doctor@test.com"

FREE_PROFILE = {
    "id": MOCK_USER_ID,
    "email": MOCK_EMAIL,
    "plan": "free",
    "minutes_used_this_month": 5.0,
    "quota_reset_at": "2099-04-01T00:00:00+00:00",  # far future → no reset
    "stripe_customer_id": None,
    "stripe_subscription_id": None,
}

PRO_PROFILE = {
    **FREE_PROFILE,
    "plan": "pro",
    "stripe_customer_id": "cus_abc123",
}

EXHAUSTED_PROFILE = {
    **FREE_PROFILE,
    "minutes_used_this_month": 30.0,  # equals FREE_PLAN_QUOTA_MINUTES
}


def make_mock_user():
    user = MagicMock()
    user.id = MOCK_USER_ID
    user.email = MOCK_EMAIL
    return user


def make_supabase_mock():
    """
    Returns a MagicMock that supports the Supabase fluent builder pattern:
        supabase.table("x").select("*").eq("id", v).single().execute()
        supabase.table("x").update({}).eq("id", v).execute()
        supabase.table("x").insert({}).execute()
    """
    mock = MagicMock()
    # Every chained call returns the same mock so the whole chain resolves.
    mock.table.return_value = mock
    mock.select.return_value = mock
    mock.eq.return_value = mock
    mock.single.return_value = mock
    mock.update.return_value = mock
    mock.insert.return_value = mock
    mock.execute.return_value = MagicMock(data=None)
    return mock


# ---------------------------------------------------------------------------
# Autouse fixture: patch Supabase everywhere to avoid real DB connections
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def patch_supabase(monkeypatch):
    """Patch get_supabase in every module that imports it."""
    mock_db = make_supabase_mock()
    monkeypatch.setattr("app.dependencies.get_supabase", lambda: mock_db)
    monkeypatch.setattr("app.routers.transcribe.get_supabase", lambda: mock_db)
    monkeypatch.setattr("app.routers.process_text.get_supabase", lambda: mock_db)
    monkeypatch.setattr("app.routers.billing.get_supabase", lambda: mock_db)
    return mock_db


# ---------------------------------------------------------------------------
# Client fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    """Unauthenticated TestClient."""
    from app.main import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture
def mock_user():
    return make_mock_user()


@pytest.fixture
def authed_client(mock_user):
    """TestClient authenticated as a free-plan user."""
    from app.main import app
    from app.dependencies import get_current_user, get_profile, check_transcription_quota

    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_profile] = lambda: FREE_PROFILE
    app.dependency_overrides[check_transcription_quota] = lambda: FREE_PROFILE
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def pro_client(mock_user):
    """TestClient authenticated as a pro-plan user."""
    from app.main import app
    from app.dependencies import get_current_user, get_profile, check_transcription_quota

    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_profile] = lambda: PRO_PROFILE
    app.dependency_overrides[check_transcription_quota] = lambda: PRO_PROFILE
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()
