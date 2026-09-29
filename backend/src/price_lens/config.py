from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    log_level: str = "INFO"
    database_url: str = Field(
        default="postgresql+psycopg://price_lens:change-me-local-only@localhost:5432/price_lens"
    )
    text2sql_database_url: str = Field(
        default=(
            "postgresql+psycopg://price_lens_text2sql:"
            "change-me-text2sql-local-only@localhost:5432/price_lens"
        )
    )
    text2sql_role_name: str = Field(
        default="price_lens_text2sql", pattern=r"^[a-z0-9_]+$"
    )
    text2sql_statement_timeout_ms: int = Field(default=2000, ge=100, le=10000)
    text2sql_lock_timeout_ms: int = Field(default=500, ge=50, le=5000)
    text2sql_max_rows: int = Field(default=100, ge=1, le=500)
    text2sql_max_explain_cost: float = Field(default=100000, gt=0)
    ai_provider: str = "rules"
    ai_model: str = "price-lens-rules-v1"
    moa_api_base_url: str = "https://data.moa.gov.tw/api/v1"
    moa_request_timeout_seconds: float = 30.0
    moa_max_concurrency: int = Field(default=5, ge=1, le=20)
    moa_max_retries: int = Field(default=3, ge=1, le=6)
    moa_etl_chunk_days: int = Field(default=31, ge=1, le=93)
    rag_retrieval_limit: int = Field(default=5, ge=1, le=10)


@lru_cache
def get_settings() -> Settings:
    return Settings()
