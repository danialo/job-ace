from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    data_root: Path = Path("artifacts")
    database_url: str = "sqlite:///./db.sqlite3"
    llm_model: str = "stub-model"
    playwright_headless: bool = True
    intake_user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
    )

    model_config = {
        "env_prefix": "JOB_ACE_",
        "env_file": ".env",
    }


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.data_root.mkdir(parents=True, exist_ok=True)
    return settings
