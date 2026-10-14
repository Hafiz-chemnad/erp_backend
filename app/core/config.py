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

    # ── Insights (Group C) — free-tier LLM for "Ask Your Data" + upsell copy ──
    # Groq tried first (fast, free tier), Gemini Flash as fallback. Both optional:
    # if neither is set, Insights still works for the rule-based upsell/churn
    # detection, just without the LLM-written suggestion text / Q&A answers.
    GROQ_API_KEY: str = ""
    GEMINI_API_KEY: str = ""

    # ── AI Agent bridge (Group D) — points at the separately-deployed
    # agent-backend service. INTERNAL_API_KEY is optional for now (auth on
    # agent-backend's side is deferred) — when it's turned on there, set the
    # same value here and it'll be sent as X-Internal-Key automatically.
    AGENT_BACKEND_URL: str = ""
    AGENT_BACKEND_INTERNAL_KEY: str = ""
    # Public base URL of THIS erp_backend deployment — needed so the Tools we
    # register on agent-backend have a real URL to call back into (e.g. the
    # place-order endpoint). Set this to your Render URL, e.g.
    # https://your-erp-backend.onrender.com
    ERP_BACKEND_PUBLIC_URL: str = ""

    class Config:
        env_file = ".env"


settings = Settings()