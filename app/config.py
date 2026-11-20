"""Application settings and YAML config loaders."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT_DIR / "config"


class Settings(BaseSettings):
    """Runtime settings from environment / .env."""

    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://brief:brief@localhost:5432/brief"
    tz: str = "Asia/Ho_Chi_Minh"

    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_max_items_per_day: int = 50

    embedding_model: str = "BAAI/bge-m3"
    embedding_dim: int = 1024

    github_token: str = ""
    hf_token: str = ""
    reddit_user_agent: str = "ai-morning-brief/0.1"
    user_agent: str = "ai-morning-brief/0.1 (+https://github.com/local/ai-morning-brief)"

    brief_schedule_hour: int = 6
    brief_schedule_minute: int = 0

    teams_webhook_url: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    email_to: str = ""
    dashboard_url: str = "http://localhost:8501"


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def load_yaml(name: str) -> Any:
    """Load a YAML file from config/ by name (with or without .yaml)."""
    filename = name if name.endswith((".yaml", ".yml")) else f"{name}.yaml"
    path = CONFIG_DIR / filename
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def reload_configs() -> None:
    """Clear YAML and settings caches (e.g. after watchlist edit)."""
    load_yaml.cache_clear()
    get_settings.cache_clear()
