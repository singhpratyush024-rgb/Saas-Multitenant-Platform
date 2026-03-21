# app/core/config.py

from pydantic_settings import BaseSettings
from pydantic import ConfigDict


class Settings(BaseSettings):

    # ── Database ──────────────────────────────────────────────────
    DATABASE_URL: str
    SYNC_DATABASE_URL: str

    # ── Redis ─────────────────────────────────────────────────────
    REDIS_URL: str

    # ── Email ─────────────────────────────────────────────────────
    MAIL_USERNAME: str
    MAIL_PASSWORD: str
    MAIL_FROM: str
    MAIL_FROM_NAME: str = "SaaS Platform"
    MAIL_PORT: int = 587
    MAIL_SERVER: str
    MAIL_STARTTLS: bool = True
    MAIL_SSL_TLS: bool = False

    # ── App ───────────────────────────────────────────────────────
    APP_BASE_URL: str = "http://localhost:8000"

    # ── Stripe ────────────────────────────────────────────────────
    STRIPE_SECRET_KEY: str
    STRIPE_WEBHOOK_SECRET: str = ""   # set after creating webhook in Stripe dashboard

    model_config = ConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()