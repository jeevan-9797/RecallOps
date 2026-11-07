"""
RecallOps Application Configuration
Uses pydantic-settings for robust environment variable validation.
"""

import json
from typing import List, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Centralized RecallOps backend configuration settings.
    Loads from environment variables or .env file.
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Core Application Settings
    PROJECT_NAME: str = "RecallOps API"
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = Field(default="development", description="Runtime environment (development, staging, production)")
    DEBUG_MODE: bool = Field(default=False, description="Enable verbose debug logging")
    LOG_LEVEL: str = Field(default="INFO", description="Logging verbosity")
    PORT: int = Field(default=8000, description="Server listening port")
    DEMO_RESET_TOKEN: Optional[str] = Field(
        default=None,
        description="Secret token required to invoke POST /api/demo/reset in production",
    )

    # Groq LLM Configuration
    GROQ_API_KEY: Optional[str] = Field(default=None, description="API Key for Groq cloud inference")
    PRIMARY_MODEL: str = Field(default="openai/gpt-oss-120b", description="Primary deep causal reasoning model")
    SECONDARY_MODEL: str = Field(default="qwen/qwen3-32b", description="Fallback low-latency model")

    # Hindsight Cloud Dual-Memory Configuration
    HINDSIGHT_ENABLED: bool = Field(default=False, description="Enable live Hindsight Cloud operations")
    HINDSIGHT_API_KEY: Optional[str] = Field(default=None, description="Hindsight Cloud API key")
    HINDSIGHT_ENDPOINT: str = Field(default="https://api.hindsight.vectorize.io", description="Hindsight base URL")
    HINDSIGHT_BANK_ID: str = Field(default="kartly-sre", description="Approved default Hindsight memory bank ID")

    # Database Configuration (PostgreSQL Docker / Supabase)
    DATABASE_URL: Optional[str] = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/recallops",
        description="PostgreSQL async connection string",
    )
    SUPABASE_URL: Optional[str] = Field(default=None, description="Hosted Supabase project URL")
    SUPABASE_KEY: Optional[str] = Field(default=None, description="Hosted Supabase service/anon key")

    # Band Multi-Agent Room Integration
    BAND_ROOM_WEBHOOK_URL: Optional[str] = Field(default=None, description="Band room incoming webhook URL")
    BAND_AGENT_ID: Optional[str] = Field(default=None, description="Band remote agent UUID")
    BAND_API_KEY: Optional[str] = Field(default=None, description="Band agent API key")
    BAND_DEFAULT_ROOM_ID: Optional[str] = Field(default=None, description="Default Band chat room ID for incident alerts")
    BAND_API_BASE_URL: str = Field(default="https://app.band.ai", description="Band platform REST API base URL")
    BAND_DELIVERY_TIMEOUT: float = Field(default=5.0, description="Total timeout in seconds for Band delivery")
    BAND_MAX_RETRIES: int = Field(default=2, description="Maximum retry attempts for transient Band delivery failures")

    # CORS Origins for Frontend Integration
    CORS_ORIGINS: List[str] = Field(
        default=["http://localhost:3000", "http://127.0.0.1:3000"],
        description="Allowed CORS origin domains",
    )

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("[") and v.endswith("]"):
                try:
                    return json.loads(v)
                except json.JSONDecodeError:
                    pass
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    def is_groq_ready(self) -> bool:
        """Returns True if Groq API key is present and non-empty."""
        return bool(self.GROQ_API_KEY and self.GROQ_API_KEY.strip() and not self.GROQ_API_KEY.startswith("your_"))

    def is_hindsight_ready(self) -> bool:
        """Returns True only if Hindsight is explicitly enabled AND API key is present."""
        return bool(
            self.HINDSIGHT_ENABLED
            and self.HINDSIGHT_API_KEY
            and self.HINDSIGHT_API_KEY.strip()
            and not self.HINDSIGHT_API_KEY.startswith("your_")
        )

    def is_supabase_ready(self) -> bool:
        """Returns True if Supabase URL and Key are present."""
        return bool(self.SUPABASE_URL and self.SUPABASE_KEY and not self.SUPABASE_URL.startswith("https://your-"))

    def is_band_ready(self) -> bool:
        """Returns True if Band API key is present and non-empty."""
        return bool(self.BAND_API_KEY and self.BAND_API_KEY.strip() and not self.BAND_API_KEY.startswith("your_"))


# Cached global settings singleton
settings = Settings()
