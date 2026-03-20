from fastapi import APIRouter, Depends
from app.dependencies import get_profile

router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("/status")
async def get_billing_status(profile=Depends(get_profile)):
    return {
        "plan": profile.get("plan", "free"),
        "minutes_used_this_month": round(profile.get("minutes_used_this_month", 0), 2),
        "quota_reset_at": profile.get("quota_reset_at"),
        "stripe_configured": False,
    }
