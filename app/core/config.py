from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # 🚀 Set these as environment variables on Render (never hardcode secrets)
    MONGO_URI: str = "mongodb://localhost:27017"
    DB_NAME: str = "whatsapp_erp_crm"

    class Config:
        env_file = ".env"


settings = Settings()