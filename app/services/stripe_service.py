import stripe
from app.config import settings

stripe.api_key = settings.stripe_secret_key

def create_checkout_session(user_id: str, user_email: str, stripe_customer_id: str = None):
    """
    Crée une session de paiement Stripe pour le plan Pro.
    """
    session_params = {
        "payment_method_types": ["card"],
        "line_items": [
            {
                "price": settings.stripe_pro_price_id,
                "quantity": 1,
            }
        ],
        "mode": "subscription",
        "success_url": f"{settings.frontend_url}/dashboard/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
        "cancel_url": f"{settings.frontend_url}/dashboard/billing",
        "client_reference_id": user_id,
        "customer_email": user_email if not stripe_customer_id else None,
        "customer": stripe_customer_id if stripe_customer_id else None,
    }
    
    # Remove None values
    session_params = {k: v for k, v in session_params.items() if v is not None}
    
    session = stripe.checkout.Session.create(**session_params)
    return session.url


def create_customer_portal_session(stripe_customer_id: str):
    """
    Crée une session pour le portail client Stripe (gestion d'abonnement).
    """
    session = stripe.billing_portal.Session.create(
        customer=stripe_customer_id,
        return_url=f"{settings.frontend_url}/dashboard/billing",
    )
    return session.url

def construct_event(payload: bytes, sig_header: str):
    """
    Vérifie la signature du webhook et convertit le payload en événement Stripe.
    """
    return stripe.Webhook.construct_event(
        payload, sig_header, settings.stripe_webhook_secret
    )
