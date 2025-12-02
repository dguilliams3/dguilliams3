"""Tests for configuration management.

Best Practices Applied:
- Uses monkeypatch fixture for environment variable isolation
- No direct os.environ manipulation (prevents test pollution)
- Mock credentials defined as constants (not hardcoded in tests)
- Automatic cleanup guaranteed by pytest
- Thread-safe for parallel test execution
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.config import Settings

# Mock credentials - never use real API keys in tests
MOCK_ANTHROPIC_KEY = "sk-ant-test-mock-key-12345678901234567890"
MOCK_BRAVE_KEY = "BSA-mock-brave-search-api-key-for-testing"


class TestSettingsValidation:
    """Test configuration validation and defaults.

    Test Type: Unit tests
    Isolation: Uses monkeypatch for environment variable isolation
    """

    def test_settings_requires_anthropic_api_key(self, monkeypatch):
        """Test that Settings raises error if ANTHROPIC_API_KEY is missing.

        Security Note: Ensures API key is always required, preventing
        accidental deployment without credentials.
        """
        # Ensure the key is not set
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        with pytest.raises(ValidationError) as exc_info:
            Settings()

        assert "anthropic_api_key" in str(exc_info.value)

    def test_settings_with_api_key(self, monkeypatch):
        """Test that Settings loads successfully with API key."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", MOCK_ANTHROPIC_KEY)

        settings = Settings()
        assert settings.anthropic_api_key == MOCK_ANTHROPIC_KEY

    def test_settings_default_values(self, monkeypatch):
        """Test that Settings has correct default values."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", MOCK_ANTHROPIC_KEY)

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

    def test_settings_optional_brave_api_key(self, monkeypatch):
        """Test that Brave API key is optional."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", MOCK_ANTHROPIC_KEY)

        # Without Brave key
        settings = Settings()
        assert settings.brave_search_api_key is None

        # With Brave key
        monkeypatch.setenv("BRAVE_SEARCH_API_KEY", MOCK_BRAVE_KEY)
        settings2 = Settings()
        assert settings2.brave_search_api_key == MOCK_BRAVE_KEY

    def test_settings_case_insensitive(self, monkeypatch):
        """Test that environment variables are case insensitive.

        Validates pydantic-settings case_sensitive=False configuration.
        """
        monkeypatch.setenv("anthropic_api_key", MOCK_ANTHROPIC_KEY)

        settings = Settings()
        assert settings.anthropic_api_key == MOCK_ANTHROPIC_KEY

    def test_ensure_data_dirs_creates_directories(self, tmp_path, monkeypatch):
        """Test that ensure_data_dirs creates all required directories."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", MOCK_ANTHROPIC_KEY)
        monkeypatch.setenv("DB_PATH", str(tmp_path / "db" / "research.db"))
        monkeypatch.setenv("CHROMA_PATH", str(tmp_path / "chroma"))
        monkeypatch.setenv("EVENTS_PATH", str(tmp_path / "events" / "events.jsonl"))

        settings = Settings()
        settings.ensure_data_dirs()

        # Check directories were created
        assert (tmp_path / "db").exists()
        assert (tmp_path / "chroma").exists()
        assert (tmp_path / "events").exists()

    def test_log_level_validation(self, monkeypatch):
        """Test that log_level only accepts valid values.

        Validates Literal type constraint on log_level field.
        """
        monkeypatch.setenv("ANTHROPIC_API_KEY", MOCK_ANTHROPIC_KEY)
        monkeypatch.setenv("LOG_LEVEL", "INVALID")

        with pytest.raises(ValidationError) as exc_info:
            Settings()

        assert "log_level" in str(exc_info.value)

    def test_log_level_accepts_valid_values(self, monkeypatch):
        """Test that all valid log levels are accepted."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", MOCK_ANTHROPIC_KEY)

        for level in ["DEBUG", "INFO", "WARNING", "ERROR"]:
            monkeypatch.setenv("LOG_LEVEL", level)
            settings = Settings()
            assert settings.log_level == level

    def test_settings_from_env_file(self, tmp_path, monkeypatch):
        """Test that Settings can load from .env file.

        Production Use Case: Validates that .env file loading works
        for local development and deployment scenarios.
        """
        # Create temporary .env file
        env_file = tmp_path / ".env"
        env_file.write_text(f"ANTHROPIC_API_KEY={MOCK_ANTHROPIC_KEY}\n")

        # Point to the temp .env file
        monkeypatch.chdir(tmp_path)

        settings = Settings()
        assert settings.anthropic_api_key == MOCK_ANTHROPIC_KEY

    def test_settings_env_var_precedence_over_env_file(self, tmp_path, monkeypatch):
        """Test that environment variables take precedence over .env file.

        Security Note: Ensures deployment environment variables
        can override .env file values (important for production).
        """
        # Create .env file with one value
        env_file = tmp_path / ".env"
        env_file.write_text("ANTHROPIC_API_KEY=from-env-file\n")

        monkeypatch.chdir(tmp_path)
        # Set environment variable with different value
        monkeypatch.setenv("ANTHROPIC_API_KEY", MOCK_ANTHROPIC_KEY)

        settings = Settings()
        # Environment variable should take precedence
        assert settings.anthropic_api_key == MOCK_ANTHROPIC_KEY
        assert settings.anthropic_api_key != "from-env-file"
