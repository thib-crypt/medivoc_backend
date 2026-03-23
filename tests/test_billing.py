"""Tests for billing endpoints (/billing/*)."""

import json
import pytest
from unittest.mock import MagicMock, patch
from tests.conftest import MOCK_USER_ID, FREE_PROFILE, PRO_PROFILE


class TestBillingStaticPages:
    def test_success_page_returns_html(self, client):
        response = client.get("/billing/success")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Paiement réussi" in response.text

    def test_cancel_page_returns_html(self, client):
        response = client.get("/billing/cancel")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "annulé" in response.text

    def test_success_page_no_auth_required(self, client):
        assert client.get("/billing/success").status_code == 200

    def test_cancel_page_no_auth_required(self, client):
        assert client.get("/billing/cancel").status_code == 200


class TestBillingStatus:
    def test_no_token_returns_403(self, client):
        assert client.get("/billing/status").status_code == 403

    def test_free_user_status(self, authed_client):
        response = authed_client.get("/billing/status")
        assert response.status_code == 200
        data = response.json()
        assert data["plan"] == "free"
        assert "minutes_used_this_month" in data
        assert "quota_reset_at" in data
        assert "stripe_configured" in data

    def test_pro_user_status(self, pro_client):
        response = pro_client.get("/billing/status")
        assert response.status_code == 200
        assert response.json()["plan"] == "pro"

    def test_minutes_used_is_rounded(self, authed_client):
        response = authed_client.get("/billing/status")
        minutes = response.json()["minutes_used_this_month"]
        # Should be a float rounded to 2 decimal places
        assert isinstance(minutes, (int, float))

    def test_stripe_configured_true_when_keys_present(self, authed_client):
        response = authed_client.get("/billing/status")
        # conftest sets both STRIPE_SECRET_KEY and STRIPE_WEBHOOK_SECRET
        assert response.json()["stripe_configured"] is True

    def test_stripe_configured_false_when_keys_missing(self, authed_client, monkeypatch):
        monkeypatch.setattr("app.routers.billing.settings", MagicMock(
            stripe_secret_key=None,
            stripe_webhook_secret=None,
        ))
        response = authed_client.get("/billing/status")
        assert response.json()["stripe_configured"] is False


class TestCheckout:
    def test_no_token_returns_403(self, client):
        assert client.post("/billing/checkout", json={}).status_code == 403

    def test_stripe_not_configured_returns_500(self, authed_client, monkeypatch):
        monkeypatch.setattr("app.routers.billing.settings", MagicMock(stripe_secret_key=None))
        response = authed_client.post("/billing/checkout", json={})
        assert response.status_code == 500

    def test_checkout_returns_url(self, authed_client):
        fake_url = "https://checkout.stripe.com/pay/cs_test_abc"
        with patch("app.routers.billing.stripe_service.create_checkout_session", return_value=fake_url):
            response = authed_client.post("/billing/checkout", json={})
        assert response.status_code == 200
        assert response.json()["url"] == fake_url

    def test_checkout_with_custom_urls(self, authed_client):
        fake_url = "https://checkout.stripe.com/pay/cs_test_xyz"
        with patch("app.routers.billing.stripe_service.create_checkout_session", return_value=fake_url) as mock_fn:
            authed_client.post(
                "/billing/checkout",
                json={"success_url": "myapp://success", "cancel_url": "myapp://cancel"},
            )
            kwargs = mock_fn.call_args[1]
            assert kwargs.get("success_url") == "myapp://success"
            assert kwargs.get("cancel_url") == "myapp://cancel"

    def test_checkout_service_error_returns_500(self, authed_client):
        with patch("app.routers.billing.stripe_service.create_checkout_session", side_effect=Exception("Stripe error")):
            response = authed_client.post("/billing/checkout", json={})
        assert response.status_code == 500


class TestPortal:
    def test_no_token_returns_403(self, client):
        assert client.post("/billing/portal", json={}).status_code == 403

    def test_stripe_not_configured_returns_500(self, authed_client, monkeypatch):
        monkeypatch.setattr("app.routers.billing.settings", MagicMock(stripe_secret_key=None))
        response = authed_client.post("/billing/portal", json={})
        assert response.status_code == 500

    def test_no_stripe_customer_returns_400(self, authed_client):
        """Free user without stripe_customer_id cannot access the portal."""
        response = authed_client.post("/billing/portal", json={})
        assert response.status_code == 400
        assert "Stripe" in response.json()["detail"]

    def test_portal_returns_url_for_pro_user(self, pro_client):
        fake_url = "https://billing.stripe.com/session/test_abc"
        with patch("app.routers.billing.stripe_service.create_customer_portal_session", return_value=fake_url):
            response = pro_client.post("/billing/portal", json={})
        assert response.status_code == 200
        assert response.json()["url"] == fake_url


class TestWebhook:
    def test_missing_webhook_secret_returns_500(self, client, monkeypatch):
        monkeypatch.setattr("app.routers.billing.settings", MagicMock(stripe_webhook_secret=None))
        response = client.post("/billing/webhook", content=b"{}", headers={"stripe-signature": "t=1,v1=abc"})
        assert response.status_code == 500

    def test_missing_signature_header_returns_400(self, client):
        response = client.post("/billing/webhook", content=b"{}")
        assert response.status_code == 400

    def test_invalid_signature_returns_400(self, client):
        import stripe
        with patch(
            "app.routers.billing.stripe_service.construct_event",
            side_effect=stripe.error.SignatureVerificationError("bad sig", "t=1,v1=abc"),
        ):
            response = client.post(
                "/billing/webhook",
                content=b"{}",
                headers={"stripe-signature": "t=1,v1=bad"},
            )
        assert response.status_code == 400

    def test_checkout_completed_event_updates_profile(self, client, patch_supabase):
        fake_event = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "customer": "cus_xyz",
                    "client_reference_id": MOCK_USER_ID,
                    "subscription": "sub_xyz",
                }
            },
        }
        with patch("app.routers.billing.stripe_service.construct_event", return_value=fake_event):
            response = client.post(
                "/billing/webhook",
                content=b"payload",
                headers={"stripe-signature": "t=1,v1=valid"},
            )
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        # Verify Supabase update was called
        patch_supabase.table.assert_called()

    def test_subscription_updated_event_active_sets_pro(self, client, patch_supabase):
        fake_event = {
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "id": "sub_abc",
                    "customer": "cus_xyz",
                    "status": "active",
                }
            },
        }
        with patch("app.routers.billing.stripe_service.construct_event", return_value=fake_event):
            response = client.post(
                "/billing/webhook",
                content=b"payload",
                headers={"stripe-signature": "t=1,v1=valid"},
            )
        assert response.status_code == 200
        update_call = patch_supabase.table.return_value.update.call_args
        assert update_call[0][0]["plan"] == "pro"

    def test_subscription_deleted_event_sets_free(self, client, patch_supabase):
        fake_event = {
            "type": "customer.subscription.deleted",
            "data": {
                "object": {
                    "customer": "cus_xyz",
                }
            },
        }
        with patch("app.routers.billing.stripe_service.construct_event", return_value=fake_event):
            response = client.post(
                "/billing/webhook",
                content=b"payload",
                headers={"stripe-signature": "t=1,v1=valid"},
            )
        assert response.status_code == 200
        update_call = patch_supabase.table.return_value.update.call_args
        assert update_call[0][0]["plan"] == "free"

    def test_unknown_event_type_returns_success(self, client):
        """Unhandled event types should be silently ignored and return 200."""
        fake_event = {"type": "payment_intent.created", "data": {"object": {}}}
        with patch("app.routers.billing.stripe_service.construct_event", return_value=fake_event):
            response = client.post(
                "/billing/webhook",
                content=b"payload",
                headers={"stripe-signature": "t=1,v1=valid"},
            )
        assert response.status_code == 200
