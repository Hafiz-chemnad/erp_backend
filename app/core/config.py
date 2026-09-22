from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── MongoDB ───────────────────────────────────────────────────────────
    MONGO_URI: str = "mongodb://localhost:27017"
    DB_NAME: str = "tymdb"           # same DB as Node backend

    # ── Redis (bot session store) ─────────────────────────────────────────
    # On Render: add REDIS_URL from your Redis instance (e.g. Upstash)
    REDIS_URL: str = "redis://localhost:6379"
    BOT_SESSION_TTL_SECONDS: int = 86400   # 24 hours — abandoned sessions auto-expire

    # ── Meta / WhatsApp Cloud API ─────────────────────────────────────────
    META_VERIFY_TOKEN: str = "verify123"   # set in Render env
    META_APP_SECRET: str = ""              # for webhook signature verification
    META_GRAPH_URL: str = "https://graph.facebook.com/v19.0"

    # ── Auth (delivery boy JWT) ───────────────────────────────────────────
    JWT_SECRET: str = "change-me-in-render-env"
    JWT_EXPIRE_DAYS: int = 30

    # ── Google Sheets (catalog sync) ──────────────────────────────────────
    GOOGLE_SERVICE_ACCOUNT_JSON: str = ""  # JSON string of service account creds

    class Config:
        env_file = ".env"


settings = Settings()