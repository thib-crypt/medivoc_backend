"""Tests for the /health endpoint."""


def test_health_returns_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "medivoc-api"


def test_health_no_auth_required(client):
    """Health check must be accessible without authentication."""
    response = client.get("/health")
    assert response.status_code == 200
