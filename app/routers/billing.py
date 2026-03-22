from fastapi import APIRouter, Depends, Request, HTTPException, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional
from app.dependencies import get_profile, get_current_user
from app.services import stripe_service
from app.config import settings
from app.services.supabase_client import get_supabase
import stripe

class CheckoutRequest(BaseModel):
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None

class PortalRequest(BaseModel):
    return_url: Optional[str] = None


router = APIRouter(prefix="/billing", tags=["billing"])

@router.get("/success")
async def checkout_success():
    html_content = """
    <html>
        <head>
            <title>Paiement réussi</title>
            <meta charset="utf-8">
            <style>
                body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; text-align: center; padding: 50px; background: #f9fafb; margin: 0; }
                h1 { color: #10b981; }
                p { color: #4b5563; font-size: 18px; }
                .btn { display: inline-block; padding: 12px 24px; background-color: #3b82f6; color: white; text-decoration: none; border-radius: 8px; font-weight: bold; margin-top: 20px; transition: background 0.2s; }
                .btn:hover { background-color: #2563eb; }
            </style>
            <script>
                setTimeout(function() {
                    window.location.href = "medivoc://billing/success";
                }, 500);
            </script>
        </head>
        <body>
            <h1>Paiement réussi ! 🎉</h1>
            <p>Merci pour votre abonnement Medivoc Pro.</p>
            <p>La page va automatiquement essayer de rouvrir l'application.</p>
            <br>
            <a href="medivoc://billing/success" class="btn">Ouvrir Medivoc</a>
        </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@router.get("/cancel")
async def checkout_cancel():
    html_content = """
    <html>
        <head>
            <title>Paiement annulé</title>
            <meta charset="utf-8">
            <style>
                body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; text-align: center; padding: 50px; background: #f9fafb; margin: 0; }
                h1 { color: #ef4444; }
                p { color: #4b5563; font-size: 18px; }
                .btn { display: inline-block; padding: 12px 24px; background-color: #3b82f6; color: white; text-decoration: none; border-radius: 8px; font-weight: bold; margin-top: 20px; transition: background 0.2s; }
                .btn:hover { background-color: #2563eb; }
            </style>
            <script>
                setTimeout(function() {
                    window.location.href = "medivoc://billing/cancel";
                }, 500);
            </script>
        </head>
        <body>
            <h1>Paiement annulé</h1>
            <p>Votre processus d'abonnement n'a pas été finalisé.</p>
            <p>La page va automatiquement essayer de rouvrir l'application.</p>
            <br>
            <a href="medivoc://billing/cancel" class="btn">Retour à Medivoc</a>
        </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@router.get("/status")
async def get_billing_status(profile=Depends(get_profile)):
    return {
        "plan": profile.get("plan", "free"),
        "minutes_used_this_month": round(profile.get("minutes_used_this_month", 0), 2),
        "quota_reset_at": profile.get("quota_reset_at"),
        "stripe_configured": bool(settings.stripe_secret_key and settings.stripe_webhook_secret),
    }


@router.post("/checkout")
async def create_checkout(request_data: CheckoutRequest, profile=Depends(get_profile), user=Depends(get_current_user)):
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=500, detail="Stripe is not configured.")
        
    try:
        stripe_customer_id = profile.get("stripe_customer_id")
        user_email = user.email
        user_id = str(user.id)
        
        checkout_url = stripe_service.create_checkout_session(
            user_id=user_id,
            user_email=user_email,
            stripe_customer_id=stripe_customer_id,
            success_url=request_data.success_url,
            cancel_url=request_data.cancel_url
        )
        return {"url": checkout_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/portal")
async def create_portal(request_data: PortalRequest, profile=Depends(get_profile)):
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=500, detail="Stripe is not configured.")
        
    stripe_customer_id = profile.get("stripe_customer_id")
    if not stripe_customer_id:
        raise HTTPException(status_code=400, detail="Aucun client Stripe actif trouvé.")
        
    try:
        portal_url = stripe_service.create_customer_portal_session(
            stripe_customer_id,
            return_url=request_data.return_url
        )
        return {"url": portal_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/webhook")
async def stripe_webhook(request: Request):
    if not settings.stripe_webhook_secret:
        raise HTTPException(status_code=500, detail="Stripe webhook secret not configured.")
        
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    
    if not sig_header:
        raise HTTPException(status_code=400, detail="Missing stripe-signature header")

    try:
        event = stripe_service.construct_event(payload, sig_header)
    except ValueError as e:
        # Invalid payload
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        raise HTTPException(status_code=400, detail="Invalid signature")
        
    supabase = get_supabase()
    
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        customer_id = session.get('customer')
        user_id = session.get('client_reference_id')
        subscription_id = session.get('subscription')
        
        if user_id and customer_id:
            supabase.table("profiles").update({
                "stripe_customer_id": customer_id,
                "stripe_subscription_id": subscription_id,
                "plan": "pro"
            }).eq("id", user_id).execute()
            
    elif event['type'] == 'customer.subscription.updated':
        subscription = event['data']['object']
        customer_id = subscription.get('customer')
        status = subscription.get('status')
        
        plan = "pro" if status in ["active", "trialing"] else "free"
        
        supabase.table("profiles").update({
            "stripe_subscription_id": subscription.get("id"),
            "plan": plan
        }).eq("stripe_customer_id", customer_id).execute()
        
    elif event['type'] == 'customer.subscription.deleted':
        subscription = event['data']['object']
        customer_id = subscription.get('customer')
        
        supabase.table("profiles").update({
            "plan": "free",
            "stripe_subscription_id": None
        }).eq("stripe_customer_id", customer_id).execute()
        
    return {"status": "success"}
