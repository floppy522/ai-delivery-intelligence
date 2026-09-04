from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ADI_", env_file=".env", extra="ignore")

    root: Path = Path(".")
    database_url: str = "sqlite+aiosqlite:///./adi.db"
    source_config_path: Path | None = None
    jira_base_url: str | None = None
    jira_email: str | None = None
    jira_token: str | None = None
    kaiten_base_url: str | None = None
    kaiten_token: str | None = None
    openai_api_key: str | None = None
    openai_model: str = "gpt-5-mini"
