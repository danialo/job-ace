from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    data_root: Path = Path("artifacts")
    database_url: str = "sqlite:///./db.sqlite3"

    # LLM Models - separate configs for different tasks
    llm_extraction_model: str = "gpt-4o-mini"  # Job extraction: fast, structured outputs
    llm_resume_parsing_model: str = "gpt-4.1"  # Resume parsing: fast and accurate
    llm_tailoring_model: str = "gpt-4.1"  # Resume tailoring: reliable quality analysis

    openai_api_key: str = ""
    playwright_headless: bool = True
    intake_user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
    )

    # LLM Configuration
    llm_provider: str = "stub"  # "stub" | "anthropic"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-4-20250514"
    llm_max_tokens: int = 4096
    llm_temperature: float = 0.3

    model_config = {
        "env_prefix": "JOB_ACE_",
        "env_file": ".env",
    }


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.data_root.mkdir(parents=True, exist_ok=True)
    return settings
