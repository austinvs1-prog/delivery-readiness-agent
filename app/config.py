from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Delivery Readiness Intelligence Assistant"
    database_url: str = "postgresql+psycopg://delivery_user:delivery_pass@db:5432/delivery_readiness"
    redis_url: str = "redis://redis:6379/0"
    ollama_url: str = "http://ollama:11434"
    ollama_model: str = "qwen3:4b"
    llm_mode: str = "ollama"
    context_budget_default: int = 1800
    token_safety_margin: int = 120

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
