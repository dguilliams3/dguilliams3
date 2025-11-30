"""Configuration management using pydantic-settings."""

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False
    )

    # LLM API Keys
    anthropic_api_key: str = Field(..., description="Anthropic API key")
    brave_search_api_key: str | None = Field(None, description="Brave Search API key")

    # Database paths
    db_path: Path = Field(Path("./data/research.db"), description="SQLite database path")
    chroma_path: Path = Field(Path("./data/chroma"), description="ChromaDB storage path")
    events_path: Path = Field(Path("./data/events.jsonl"), description="Event log path")

    # Application settings
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    update_on_startup: bool = False

    # Server configuration
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    frontend_url: str = "http://localhost:5173"

    # Model selection
    default_filter_model: str = "claude-3-haiku-20240307"  # Cheap for filtering
    default_synthesis_model: str = "claude-3-5-sonnet-20241022"  # Better for synthesis
    default_qa_model: str = "claude-3-5-sonnet-20241022"  # Best for Q&A

    def ensure_data_dirs(self) -> None:
        """Create data directories if they don't exist."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.chroma_path.mkdir(parents=True, exist_ok=True)
        self.events_path.parent.mkdir(parents=True, exist_ok=True)


# Global settings instance
settings = Settings()
