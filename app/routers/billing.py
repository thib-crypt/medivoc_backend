from fastapi import APIRouter, Depends, Request, HTTPException, status
from app.dependencies import get_profile, get_current_user
from app.services import stripe_service
from app.config import settings
from app.services.supabase_client import get_supabase
import stripe

router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("/status")
async def get_billing_status(profile=Depends(get_profile)):
    return {
        "plan": profile.get("plan", "free"),
        "minutes_used_this_month": round(profile.get("minutes_used_this_month", 0), 2),
        "quota_reset_at": profile.get("quota_reset_at"),
        "stripe_configured": bool(settings.stripe_secret_key and settings.stripe_webhook_secret),
    }


@router.post("/checkout")
async def create_checkout(profile=Depends(get_profile), user=Depends(get_current_user)):
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=500, detail="Stripe is not configured.")
        
    try:
        stripe_customer_id = profile.get("stripe_customer_id")
        user_email = user.email
        user_id = str(user.id)
        
        checkout_url = stripe_service.create_checkout_session(
            user_id=user_id,
            user_email=user_email,
            stripe_customer_id=stripe_customer_id
        )
        return {"url": checkout_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/portal")
async def create_portal(profile=Depends(get_profile)):
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=500, detail="Stripe is not configured.")
        
    stripe_customer_id = profile.get("stripe_customer_id")
    if not stripe_customer_id:
        raise HTTPException(status_code=400, detail="Aucun client Stripe actif trouvé.")
        
    try:
        portal_url = stripe_service.create_customer_portal_session(stripe_customer_id)
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
