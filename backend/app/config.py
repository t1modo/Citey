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
    # Public base URL of this API, used in links inside emails. Falls back to
    # the incoming request's base URL when unset.
    api_url: str = ""
    support_email: str = "support@citey.app"
    cron_secret: str = "changeme"
    # Secret for signing unsubscribe / RSS links. Kept separate from
    # cron_secret so rotating one never invalidates or exposes the other.
    # Falls back to cron_secret when unset so links in already sent emails
    # keep working until a dedicated value is configured.
    token_secret: str = ""

    # Scheduler
    scheduler_interval_hours: int = 24

    # Anthropic
    anthropic_api_key: str = ""

    # NASA ADS (Astrophysics Data System)
    # Free token: https://ui.adsabs.harvard.edu/user/settings/token
    ads_api_key: str = ""

    # CORS
    allowed_origins: str = "*"

    # Scheduler — set DISABLE_SCHEDULER=true on Cloud Run (Cloud Scheduler
    # calls the HTTP endpoints instead; APScheduler only runs locally)
    disable_scheduler: bool = False


    @property
    def is_local(self) -> bool:
        return "localhost" in self.app_url or "127.0.0.1" in self.app_url

    @property
    def cron_secret_is_default(self) -> bool:
        return self.cron_secret in ("", "changeme")


@lru_cache()
def get_settings() -> Settings:
    return Settings()
