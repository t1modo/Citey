from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Firebase
    firebase_service_account_json: str = ""
    firebase_service_account_path: str = ""

    # Resend
    resend_api_key: str = ""

    # Email
    email_from_address: str = "notifications@citey.app"
    email_from_name: str = "Citey"

    # App
    app_name: str = "Citey"
    app_url: str = "http://localhost:3000"
    support_email: str = "support@citey.app"
    cron_secret: str = "changeme"

    # Scheduler
    scheduler_interval_hours: int = 24

    # Anthropic
    anthropic_api_key: str = ""

    # CORS
    allowed_origins: str = "*"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
