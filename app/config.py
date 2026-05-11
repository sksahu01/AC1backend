"""
AEROCORE Backend Configuration
Load from .env file via python-dotenv
"""
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # Supabase
    supabase_url: str = Field(..., alias="SUPABASE_URL")
    supabase_key: str = Field(..., alias="SUPABASE_KEY")
    supabase_db_url: str = Field(..., alias="SUPABASE_DB_URL")

    # Auth
    secret_key: str = Field(..., alias="SECRET_KEY")

    # LLM
    llm_api_key: str = Field(..., alias="LLM_API_KEY")
    llm_model: str = Field(default="claude-sonnet-4-20250514", alias="LLM_MODEL")

    # Crawler config
    msg_batch_size: int = Field(default=20, alias="MSG_BATCH_SIZE")
    ops_batch_size: int = Field(default=20, alias="OPS_BATCH_SIZE")
    chat_batch_size: int = Field(default=30, alias="CHAT_BATCH_SIZE")
    crawler_fallback_sweep_sec: int = Field(default=30, alias="CRAWLER_FALLBACK_SWEEP_SEC")
    sla_crawler_interval_sec: int = Field(default=60, alias="SLA_CRAWLER_INTERVAL_SEC")

    # App
    environment: str = Field(default="development", alias="ENVIRONMENT")
    debug: bool = Field(default=True, alias="DEBUG")

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
