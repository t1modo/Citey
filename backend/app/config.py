import os
from functools import lru_cache

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# Every backend route is served under this prefix, locally and on Vercel,
# where one project sends /api/* to the backend and the rest to the site.
API_PREFIX = "/api"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        # Lets Settings(clerk_publishable_key=...) work for fields that read
        # an aliased environment variable.
        populate_by_name=True,
    )

    # Firebase
    firebase_service_account_json: str = ""
    firebase_service_account_path: str = ""

    # Resend
    resend_api_key: str = ""

    # Email
    email_from_address: str = "hello@citey.email"
    email_from_name: str = "Citey"

    # App
    app_name: str = "Citey"
    app_url: str = "http://localhost:3000"
    # Public base URL of this API, used in links inside emails. Falls back to
    # the incoming request's base URL when unset.
    api_url: str = ""
    support_email: str = "support@citey.email"
    # Where contact form messages go. support@citey.email reaches the owner
    # through a forwarder, which can hold or drop mail; set this to the inbox
    # itself to skip it. Empty means SUPPORT_EMAIL.
    support_inbox: str = ""
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

    # Semantic Scholar. Without a key, requests share an anonymous pool that
    # is rate limited heavily at night. Free key:
    # https://www.semanticscholar.org/product/api#api-key-form
    s2_api_key: str = ""

    # OpenAlex. Works without a key, but keyless use has a small daily
    # allowance and later requests get 401. Free key from openalex.org (sign in, then API settings)
    openalex_api_key: str = ""

    # Neon Postgres. DATABASE_URL is the pooled connection string for app
    # traffic; DATABASE_URL_UNPOOLED is the direct one, for migrations.
    database_url: str = ""
    database_url_unpooled: str = ""

    # Clerk. The publishable key names the instance whose session tokens the
    # API accepts; the site uses the same NEXT_PUBLIC_ variable, so one value
    # in Vercel serves both. Tokens are checked against Clerk's public keys,
    # so no secret is needed to verify them.
    clerk_publishable_key: str = Field(
        default="",
        validation_alias=AliasChoices("CLERK_PUBLISHABLE_KEY", "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY"),
    )

    # OpenCitations. Optional; a free token raises the rate limit:
    # https://opencitations.net/accesstoken
    opencitations_access_token: str = ""

    # CORS
    allowed_origins: str = "*"

    # Scheduler. Production sets DISABLE_SCHEDULER=true and Inngest runs the
    # scheduled jobs instead; APScheduler only runs locally. It defaults to
    # off on Vercel (which sets VERCEL=1), where a background thread is
    # frozen between requests and would never fire.
    disable_scheduler: bool = Field(
        default_factory=lambda: bool(os.environ.get("VERCEL"))
    )

    # Inngest runs the nightly and weekly jobs by calling /api/inngest.
    # Production needs the signing key (verifies Inngest's requests) and the
    # event key (the jobs send one event per user). INNGEST_DEV=1, or the Dev
    # Server's URL, uses a local Dev Server instead and needs neither key.
    inngest_signing_key: str = ""
    inngest_event_key: str = ""
    inngest_dev: str = ""

    @field_validator("app_url", "api_url")
    @classmethod
    def _strip_trailing_slash(cls, v: str) -> str:
        # "https://www.citey.email/" + "/dashboard" produced "//dashboard"
        # in every emailed link.
        return v.rstrip("/")

    @property
    def is_local(self) -> bool:
        return "localhost" in self.app_url or "127.0.0.1" in self.app_url

    @property
    def cron_secret_is_default(self) -> bool:
        return self.cron_secret in ("", "changeme")


@lru_cache()
def get_settings() -> Settings:
    return Settings()
