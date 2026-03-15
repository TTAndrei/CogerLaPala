from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "CogerLaPala API"
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4.1-mini", alias="OPENAI_MODEL")
    min_match_score: float = Field(default=60.0, alias="MIN_MATCH_SCORE")
    max_daily_applications: int = Field(default=10, alias="MAX_DAILY_APPLICATIONS")
    default_dry_run: bool = Field(default=True, alias="DEFAULT_DRY_RUN")
    screenshot_dir: str = Field(default=".artifacts/screenshots", alias="SCREENSHOT_DIR")
    linkedin_email: str | None = Field(default=None, alias="LINKEDIN_EMAIL")
    linkedin_password: str | None = Field(default=None, alias="LINKEDIN_PASSWORD")
    linkedin_storage_state: str = Field(
        default=".artifacts/linkedin-storage-state.json",
        alias="LINKEDIN_STORAGE_STATE",
    )
    linkedin_headless: bool = Field(default=False, alias="LINKEDIN_HEADLESS")
    linkedin_manual_login_timeout_seconds: int = Field(
        default=180,
        alias="LINKEDIN_MANUAL_LOGIN_TIMEOUT_SECONDS",
    )
    linkedin_max_search_pages: int = Field(default=3, alias="LINKEDIN_MAX_SEARCH_PAGES")
    linkedin_ai_navigation_enabled: bool = Field(
        default=True,
        alias="LINKEDIN_AI_NAVIGATION_ENABLED",
    )
    linkedin_ai_navigation_model: str = Field(
        default="gpt-4.1-mini",
        alias="LINKEDIN_AI_NAVIGATION_MODEL",
    )
    linkedin_ai_navigation_max_attempts: int = Field(
        default=1,
        alias="LINKEDIN_AI_NAVIGATION_MAX_ATTEMPTS",
    )

    model_config = SettingsConfigDict(
        # Load local overrides first, then fallback to .env if needed.
        env_file=(".env.local", ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
