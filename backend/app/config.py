from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

EMBEDDING_DIM = 384


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://faro:faro@localhost:5432/faro"
    redis_url: str = "redis://localhost:6379/0"
    llm_provider: Literal["fake", "groq"] = "fake"
    embedding_provider: Literal["fake", "gemini"] = "fake"
    llm_model: str | None = None
    embedding_model: str | None = None
    gemini_api_key: str | None = None
    groq_api_key: str | None = None
    llm_timeout_seconds: float = 30
    max_upload_bytes: int = 20 * 1024 * 1024
    max_pages: int = 80
    chunk_size: int = 1000
    chunk_overlap: int = 150
    retrieval_top_k: int = 8
    min_cosine_similarity: float = 0.28
    otel_exporter_otlp_endpoint: str | None = None
    otel_service_name: str = "faro-api"


@lru_cache
def get_settings() -> Settings:
    return Settings()
