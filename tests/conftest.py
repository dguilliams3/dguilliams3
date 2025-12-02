"""Pytest configuration and shared fixtures.

This module provides:
1. Mock credentials for all tests (never use real API keys)
2. Shared database fixtures for integration tests
3. Mock external service fixtures (Anthropic, Brave Search)
4. Test categorization markers
5. Pytest hooks for test environment setup

Best Practices:
- All fixtures use proper cleanup (yield pattern or context managers)
- Mock credentials follow realistic format for validation testing
- Database fixtures use tmp_path for isolation
- External services are mocked to avoid real API calls
- Test markers enable selective test execution

Test Categories:
- unit: Fast, isolated unit tests (no external dependencies)
- integration: Tests with database or multiple components
- slow: Tests that take > 1 second
- requires_api: Tests that need real API credentials (skip in CI)
"""

from pathlib import Path
from typing import AsyncIterator
from unittest.mock import Mock, AsyncMock
from datetime import datetime

import pytest
import pytest_asyncio

# Mock Credentials - NEVER use real API keys in tests
# Format matches real keys for validation testing
MOCK_ANTHROPIC_API_KEY = "sk-ant-test-mock-key-12345678901234567890123456789012"
MOCK_BRAVE_SEARCH_API_KEY = "BSAabcdefghijklmnopqrstuvwxyz1234567890ABCD"


# =============================================================================
# Configuration Fixtures
# =============================================================================


@pytest.fixture
def mock_anthropic_key():
    """Provide mock Anthropic API key.

    Usage:
        def test_something(mock_anthropic_key, monkeypatch):
            monkeypatch.setenv("ANTHROPIC_API_KEY", mock_anthropic_key)
            # ... test code
    """
    return MOCK_ANTHROPIC_API_KEY


@pytest.fixture
def mock_brave_key():
    """Provide mock Brave Search API key."""
    return MOCK_BRAVE_SEARCH_API_KEY


@pytest.fixture
def test_env(monkeypatch, tmp_path):
    """Set up isolated test environment with mock credentials.

    Provides:
    - Mock API keys
    - Temporary data directories
    - Test-safe configuration

    Automatically cleans up after test completion.

    Usage:
        def test_something(test_env):
            from backend.config import settings
            # settings will have mock credentials and temp paths
    """
    # Set mock API keys
    monkeypatch.setenv("ANTHROPIC_API_KEY", MOCK_ANTHROPIC_API_KEY)
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", MOCK_BRAVE_SEARCH_API_KEY)

    # Set temporary paths to avoid touching real data directories
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("CHROMA_PATH", str(tmp_path / "chroma"))
    monkeypatch.setenv("EVENTS_PATH", str(tmp_path / "events.jsonl"))

    # Return tmp_path in case test needs it
    return tmp_path


# =============================================================================
# Database Fixtures
# =============================================================================


@pytest_asyncio.fixture
async def test_db(tmp_path):
    """Create isolated test database.

    Returns:
        Database: Initialized database instance with migrations applied

    Cleanup:
        Automatically closes database connection after test

    Usage:
        async def test_something(test_db):
            # Use test_db for database operations
            # Automatically cleaned up after test
    """
    from backend.db.sqlite import Database

    db_path = tmp_path / "test.db"
    db = Database(db_path)
    await db.initialize()
    await db.run_migrations()

    yield db

    await db.close()


@pytest_asyncio.fixture
async def domain_repo(test_db):
    """Create domain repository with test database.

    Usage:
        async def test_domain_ops(domain_repo):
            domain = Domain(...)
            await domain_repo.create(domain)
    """
    from backend.db.sqlite import DomainRepository

    return DomainRepository(test_db)


@pytest_asyncio.fixture
async def item_repo(test_db):
    """Create item repository with test database."""
    from backend.db.sqlite import ItemRepository

    return ItemRepository(test_db)


@pytest_asyncio.fixture
async def update_repo(test_db):
    """Create update repository with test database."""
    from backend.db.sqlite import UpdateRepository

    return UpdateRepository(test_db)


@pytest_asyncio.fixture
async def annotation_repo(test_db):
    """Create annotation repository with test database."""
    from backend.db.sqlite import AnnotationRepository

    return AnnotationRepository(test_db)


# =============================================================================
# Domain Model Fixtures
# =============================================================================


@pytest.fixture
def sample_domain_config():
    """Create sample domain configuration for testing.

    Returns:
        DomainConfig: Minimal valid domain configuration
    """
    from backend.models.domain import DomainConfig

    return DomainConfig(
        id="test-domain",
        name="Test Domain",
        description="A test research domain",
        keywords=["test", "research"],
        sources=[],
        discovery_prompts=["Find recent test research"],
        synthesis_prompt_template="Summarize test findings",
        refresh_interval_hours=24,
    )


@pytest.fixture
def sample_domain(sample_domain_config):
    """Create sample domain for testing.

    Returns:
        Domain: Complete domain instance
    """
    from backend.models.domain import Domain

    return Domain(
        id=sample_domain_config.id,
        name=sample_domain_config.name,
        description=sample_domain_config.description,
        config=sample_domain_config,
        created_at=datetime.utcnow(),
        last_updated_at=None,
    )


@pytest.fixture
def sample_item(sample_domain):
    """Create sample item for testing.

    Returns:
        Item: Complete item instance
    """
    from backend.models.domain import Item

    return Item(
        id="test-item-1",
        domain_id=sample_domain.id,
        title="Test Research Item",
        summary="A test summary of research findings",
        source="Test Source",
        source_url="https://example.com/test",
        significance="High impact test finding",
        significance_score=0.85,
        discovered_at=datetime.utcnow(),
        raw_content="Full text content of the test item...",
    )


# =============================================================================
# External Service Mocks
# =============================================================================


@pytest.fixture
def mock_anthropic_client():
    """Mock Anthropic API client.

    Returns:
        Mock: Anthropic client with mocked messages.create method

    Usage:
        def test_rag(mock_anthropic_client):
            # mock_anthropic_client.messages.create returns mock response
            service = RAGService(anthropic=mock_anthropic_client)
    """
    mock_client = Mock()
    mock_message = Mock()
    mock_message.content = [Mock(text="This is a mock AI response.")]
    mock_message.usage = Mock(input_tokens=100, output_tokens=50)

    mock_client.messages.create = Mock(return_value=mock_message)

    return mock_client


@pytest.fixture
def mock_httpx_client():
    """Mock httpx.Client for HTTP requests.

    Returns:
        Mock: HTTP client that returns successful responses

    Usage:
        def test_tool(mock_httpx_client, monkeypatch):
            monkeypatch.setattr("httpx.Client", lambda **kwargs: mock_httpx_client)
            tool = FetchURLTool()
            # tool.client is now mocked
    """
    mock_client = Mock()
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.text = "<html><body>Test content</body></html>"
    mock_response.json.return_value = {"results": []}

    mock_client.get = Mock(return_value=mock_response)
    mock_client.close = Mock()

    return mock_client


@pytest.fixture
def mock_brave_search_response():
    """Mock Brave Search API response data.

    Returns:
        dict: Valid Brave Search API response structure
    """
    return {
        "web": {
            "results": [
                {
                    "title": "Test Result 1",
                    "url": "https://example.com/1",
                    "description": "First test result description",
                },
                {
                    "title": "Test Result 2",
                    "url": "https://example.com/2",
                    "description": "Second test result description",
                },
            ]
        }
    }


# =============================================================================
# Pytest Hooks
# =============================================================================


def pytest_configure(config):
    """Register custom pytest markers.

    Markers:
    - unit: Fast isolated unit tests
    - integration: Tests with database or multiple components
    - slow: Tests that take > 1 second
    - requires_api: Tests that need real API credentials
    """
    config.addinivalue_line("markers", "unit: Fast isolated unit tests")
    config.addinivalue_line(
        "markers", "integration: Tests with database or multiple components"
    )
    config.addinivalue_line("markers", "slow: Tests that take > 1 second")
    config.addinivalue_line(
        "markers", "requires_api: Tests that need real API credentials (skip in CI)"
    )


def pytest_collection_modifyitems(config, items):
    """Automatically mark tests based on their characteristics.

    Auto-marking rules:
    - Tests with 'test_db' fixture -> integration
    - Tests with 'async' in name -> integration (usually DB operations)
    - Tests in test_sqlite.py -> integration
    - Tests in test_config.py, test_tools.py -> unit (unless marked otherwise)
    """
    for item in items:
        # Get test file name
        test_file = item.nodeid.split("::")[0]

        # Auto-mark integration tests
        if "test_db" in item.fixturenames:
            item.add_marker(pytest.mark.integration)
        elif "test_sqlite" in test_file:
            item.add_marker(pytest.mark.integration)

        # Auto-mark unit tests
        elif "test_config" in test_file or "test_tools" in test_file:
            if "integration" not in [m.name for m in item.iter_markers()]:
                item.add_marker(pytest.mark.unit)


# =============================================================================
# Test Utilities
# =============================================================================


@pytest.fixture
def assert_dict_subset():
    """Helper to assert dictionary contains expected keys/values.

    Usage:
        def test_something(assert_dict_subset):
            result = {"a": 1, "b": 2, "c": 3}
            assert_dict_subset(result, {"a": 1, "b": 2})  # Passes
    """

    def _assert_subset(actual: dict, expected: dict):
        """Assert actual dict contains all keys/values from expected dict."""
        for key, value in expected.items():
            assert key in actual, f"Key '{key}' not found in {actual}"
            assert (
                actual[key] == value
            ), f"Expected {key}={value}, got {key}={actual[key]}"

    return _assert_subset
