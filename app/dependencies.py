from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.services.supabase_client import get_supabase
from app.config import settings
from datetime import datetime, timezone

security = HTTPBearer()

FREE_PLAN_QUOTA_MINUTES = settings.free_plan_quota_minutes


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    token = credentials.credentials
    supabase = get_supabase()

    try:
        user_response = supabase.auth.get_user(token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide ou expiré.",
        )

    if not user_response or not user_response.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Utilisateur non trouvé.",
        )

    return user_response.user


async def get_profile(user=Depends(get_current_user)):
    supabase = get_supabase()
    result = supabase.table("profiles").select("*").eq("id", str(user.id)).single().execute()

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profil utilisateur introuvable.",
        )

    return result.data


async def get_current_user_from_token(token: str):
    """Auth sans Depends — utilisable dans les routes WebSocket."""
    supabase = get_supabase()
    try:
        user_response = supabase.auth.get_user(token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide ou expiré.",
        )
    if not user_response or not user_response.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Utilisateur non trouvé.",
        )
    return user_response.user


async def get_profile_by_user_id(user_id: str) -> dict:
    """Récupère le profil sans Depends — utilisable dans les routes WebSocket."""
    supabase = get_supabase()
    result = supabase.table("profiles").select("*").eq("id", user_id).single().execute()
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profil utilisateur introuvable.",
        )
    profile = result.data

    now = datetime.now(timezone.utc)
    quota_reset_at_raw = profile.get("quota_reset_at")
    if quota_reset_at_raw:
        if isinstance(quota_reset_at_raw, str):
            quota_reset_at = datetime.fromisoformat(quota_reset_at_raw.replace("Z", "+00:00"))
        else:
            quota_reset_at = quota_reset_at_raw
        if now >= quota_reset_at:
            from dateutil.relativedelta import relativedelta
            next_reset = quota_reset_at + relativedelta(months=1)
            supabase.table("profiles").update({
                "minutes_used_this_month": 0,
                "quota_reset_at": next_reset.isoformat(),
            }).eq("id", user_id).execute()
            profile["minutes_used_this_month"] = 0

    return profile


def check_quota_from_profile(profile: dict):
    """Vérifie le quota sans Depends — lève HTTPException si dépassé."""
    if profile.get("plan") == "pro":
        return
    minutes_used = profile.get("minutes_used_this_month", 0)
    if minutes_used >= FREE_PLAN_QUOTA_MINUTES:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Quota atteint : {FREE_PLAN_QUOTA_MINUTES} minutes/mois pour le plan gratuit. Passez au plan Pro pour continuer.",
        )


async def check_transcription_quota(profile=Depends(get_profile)):
    now = datetime.now(timezone.utc)

    quota_reset_at_raw = profile.get("quota_reset_at")
    if quota_reset_at_raw:
        if isinstance(quota_reset_at_raw, str):
            quota_reset_at = datetime.fromisoformat(quota_reset_at_raw.replace("Z", "+00:00"))
        else:
            quota_reset_at = quota_reset_at_raw

        if now >= quota_reset_at:
            supabase = get_supabase()
            from dateutil.relativedelta import relativedelta
            next_reset = quota_reset_at + relativedelta(months=1)
            supabase.table("profiles").update({
                "minutes_used_this_month": 0,
                "quota_reset_at": next_reset.isoformat(),
            }).eq("id", profile["id"]).execute()
            profile["minutes_used_this_month"] = 0

    if profile.get("plan") == "pro":
        return profile

    minutes_used = profile.get("minutes_used_this_month", 0)
    if minutes_used >= FREE_PLAN_QUOTA_MINUTES:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Quota atteint : {FREE_PLAN_QUOTA_MINUTES} minutes/mois pour le plan gratuit. Passez au plan Pro pour continuer.",
        )

    return profile
