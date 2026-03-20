from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Supabase
    supabase_url: str
    supabase_service_key: str

    # AI providers
    groq_api_key: str
    deepgram_api_key: str
    gemini_api_key: str

    # Stripe (Phase 2 — optionnel)
    stripe_secret_key: Optional[str] = None
    stripe_webhook_secret: Optional[str] = None
    stripe_pro_price_id: Optional[str] = None
    frontend_url: Optional[str] = None

    # Quotas (en minutes)
    free_plan_quota_minutes: float = 30.0


settings = Settings()
