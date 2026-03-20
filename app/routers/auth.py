from fastapi import APIRouter, Depends
from app.dependencies import get_current_user, get_profile

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me")
async def get_me(
    user=Depends(get_current_user),
    profile=Depends(get_profile),
):
    return {
        "id": str(user.id),
        "email": user.email,
        "plan": profile.get("plan", "free"),
        "minutes_used_this_month": profile.get("minutes_used_this_month", 0),
        "quota_reset_at": profile.get("quota_reset_at"),
    }
