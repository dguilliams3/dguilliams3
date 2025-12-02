"""Tests for configuration management."""

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.config import Settings


class TestSettingsValidation:
    """Test configuration validation and defaults."""

    def test_settings_requires_anthropic_api_key(self):
        """Test that Settings raises error if ANTHROPIC_API_KEY is missing."""
        # Clear environment variable if it exists
        original = os.environ.get("ANTHROPIC_API_KEY")
        if "ANTHROPIC_API_KEY" in os.environ:
            del os.environ["ANTHROPIC_API_KEY"]

        try:
            with pytest.raises(ValidationError) as exc_info:
                Settings()

            assert "anthropic_api_key" in str(exc_info.value)
        finally:
            # Restore original value
            if original:
                os.environ["ANTHROPIC_API_KEY"] = original

    def test_settings_with_api_key(self):
        """Test that Settings loads successfully with API key."""
        os.environ["ANTHROPIC_API_KEY"] = "test-key-12345"

        try:
            settings = Settings()
            assert settings.anthropic_api_key == "test-key-12345"
        finally:
            del os.environ["ANTHROPIC_API_KEY"]

    def test_settings_default_values(self):
        """Test that Settings has correct default values."""
        os.environ["ANTHROPIC_API_KEY"] = "test-key"

        try:
            settings = Settings()

            # Database paths
            assert settings.db_path == Path("./data/research.db")
            assert settings.chroma_path == Path("./data/chroma")
            assert settings.events_path == Path("./data/events.jsonl")

            # Application settings
            assert settings.log_level == "INFO"
            assert settings.update_on_startup is False

            # Server configuration
            assert settings.api_host == "0.0.0.0"
            assert settings.api_port == 8000
            assert settings.frontend_url == "http://localhost:5173"

            # Model selection
            assert settings.default_filter_model == "claude-3-haiku-20240307"
            assert settings.default_synthesis_model == "claude-3-5-sonnet-20241022"
            assert settings.default_qa_model == "claude-3-5-sonnet-20241022"
        finally:
            del os.environ["ANTHROPIC_API_KEY"]

    def test_settings_optional_brave_api_key(self):
        """Test that Brave API key is optional."""
        os.environ["ANTHROPIC_API_KEY"] = "test-key"

        try:
            settings = Settings()
            assert settings.brave_search_api_key is None

            # Now set it
            os.environ["BRAVE_SEARCH_API_KEY"] = "brave-key"
            settings2 = Settings()
            assert settings2.brave_search_api_key == "brave-key"
        finally:
            del os.environ["ANTHROPIC_API_KEY"]
            if "BRAVE_SEARCH_API_KEY" in os.environ:
                del os.environ["BRAVE_SEARCH_API_KEY"]

    def test_settings_case_insensitive(self):
        """Test that environment variables are case insensitive."""
        os.environ["anthropic_api_key"] = "test-key-lowercase"

        try:
            settings = Settings()
            assert settings.anthropic_api_key == "test-key-lowercase"
        finally:
            del os.environ["anthropic_api_key"]

    def test_ensure_data_dirs_creates_directories(self, tmp_path):
        """Test that ensure_data_dirs creates all required directories."""
        os.environ["ANTHROPIC_API_KEY"] = "test-key"
        os.environ["DB_PATH"] = str(tmp_path / "db" / "research.db")
        os.environ["CHROMA_PATH"] = str(tmp_path / "chroma")
        os.environ["EVENTS_PATH"] = str(tmp_path / "events" / "events.jsonl")

        try:
            settings = Settings()
            settings.ensure_data_dirs()

            # Check directories were created
            assert (tmp_path / "db").exists()
            assert (tmp_path / "chroma").exists()
            assert (tmp_path / "events").exists()
        finally:
            del os.environ["ANTHROPIC_API_KEY"]
            del os.environ["DB_PATH"]
            del os.environ["CHROMA_PATH"]
            del os.environ["EVENTS_PATH"]

    def test_log_level_validation(self):
        """Test that log_level only accepts valid values."""
        os.environ["ANTHROPIC_API_KEY"] = "test-key"
        os.environ["LOG_LEVEL"] = "INVALID"

        try:
            with pytest.raises(ValidationError) as exc_info:
                Settings()

            assert "log_level" in str(exc_info.value)
        finally:
            del os.environ["ANTHROPIC_API_KEY"]
            del os.environ["LOG_LEVEL"]

    def test_log_level_accepts_valid_values(self):
        """Test that all valid log levels are accepted."""
        os.environ["ANTHROPIC_API_KEY"] = "test-key"

        try:
            for level in ["DEBUG", "INFO", "WARNING", "ERROR"]:
                os.environ["LOG_LEVEL"] = level
                settings = Settings()
                assert settings.log_level == level
        finally:
            del os.environ["ANTHROPIC_API_KEY"]
            if "LOG_LEVEL" in os.environ:
                del os.environ["LOG_LEVEL"]
