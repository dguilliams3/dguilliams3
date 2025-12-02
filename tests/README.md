# Test Suite Documentation

Comprehensive test suite for the Research Dashboard with production-ready best practices.

## 📊 Test Coverage

Current test coverage: **>= 70%** for all core modules

- **Configuration**: 11 tests (test_config.py)
- **Database**: 25+ tests (test_sqlite.py)
- **Tools**: 17 tests (test_tools.py)
- **Total**: 53+ tests across unit and integration categories

## 🏗️ Test Structure

```
tests/
├── conftest.py           # Shared fixtures and pytest configuration
├── test_config.py        # Configuration and environment variable tests
├── test_sqlite.py        # Database repository integration tests
├── test_tools.py         # Tool resource management and security tests
└── README.md            # This file
```

## 🎯 Test Categories

Tests are automatically categorized using pytest markers:

### Unit Tests (`@pytest.mark.unit`)
- **Fast**: < 100ms execution time
- **Isolated**: No external dependencies (databases, APIs, files)
- **Mocked**: All external interactions mocked
- **Examples**: Configuration validation, tool initialization, SSRF protection

```bash
# Run only unit tests
pytest tests/ -m unit
```

### Integration Tests (`@pytest.mark.integration`)
- **Database**: Tests with real database operations (using tmp_path)
- **Multi-component**: Tests involving multiple system components
- **Examples**: Repository CRUD operations, database migrations

```bash
# Run only integration tests
pytest tests/ -m integration
```

### Slow Tests (`@pytest.mark.slow`)
- Tests that take > 1 second to execute
- Usually involve heavy computation or I/O

```bash
# Exclude slow tests for quick feedback
pytest tests/ -m "not slow"
```

### API Tests (`@pytest.mark.requires_api`)
- Tests requiring real API credentials
- Skipped in CI/CD pipelines
- Use for manual testing with real services

```bash
# Skip API tests (default in CI)
pytest tests/ -m "not requires_api"
```

## 🔧 Running Tests

### Basic Test Execution

```bash
# Run all tests
pytest tests/

# Run with coverage report
pytest tests/ --cov=backend --cov-report=html

# Run specific test file
pytest tests/test_config.py

# Run specific test
pytest tests/test_config.py::TestSettingsValidation::test_settings_requires_anthropic_api_key

# Run tests matching pattern
pytest tests/ -k "api_key"
```

### Parallel Execution

```bash
# Run tests in parallel (requires pytest-xdist)
pytest tests/ -n auto

# Run with 4 workers
pytest tests/ -n 4
```

### Verbose Output

```bash
# Verbose with local variables on failure
pytest tests/ -vv --showlocals

# Show print statements
pytest tests/ -s

# Stop on first failure
pytest tests/ -x
```

### Coverage Reports

```bash
# Terminal report
pytest tests/ --cov=backend --cov-report=term-missing

# HTML report (opens in browser)
pytest tests/ --cov=backend --cov-report=html
open htmlcov/index.html

# Generate coverage badge
pytest tests/ --cov=backend --cov-report=term --cov-report=xml
```

## 🛠️ Test Fixtures

### Configuration Fixtures (conftest.py)

#### Mock Credentials
```python
def test_something(mock_anthropic_key, mock_brave_key):
    # Use mock API keys for testing
    assert mock_anthropic_key.startswith("sk-ant-test-")
```

#### Test Environment
```python
def test_with_env(test_env):
    # Isolated environment with mock credentials and temp paths
    from backend.config import settings
    assert settings.anthropic_api_key  # Mock key is set
```

### Database Fixtures

```python
async def test_with_database(test_db, domain_repo, item_repo):
    # test_db: Initialized database with migrations
    # domain_repo: DomainRepository instance
    # item_repo: ItemRepository instance

    domain = Domain(...)
    await domain_repo.create(domain)
```

### Model Fixtures

```python
def test_with_sample_data(sample_domain, sample_item):
    # Pre-configured domain and item instances
    assert sample_domain.id == "test-domain"
    assert sample_item.domain_id == sample_domain.id
```

### Mock Service Fixtures

```python
def test_with_mocks(mock_anthropic_client, mock_httpx_client):
    # mock_anthropic_client: Mocked Anthropic API
    # mock_httpx_client: Mocked HTTP client

    response = mock_anthropic_client.messages.create(...)
    assert response.content[0].text == "This is a mock AI response."
```

## 🔐 Security Best Practices

### API Key Management

**NEVER commit real API keys to version control!**

```python
# ❌ BAD - Hardcoded credentials
def test_bad():
    api_key = "sk-ant-real-key-abc123"  # NEVER DO THIS

# ✅ GOOD - Use fixtures
def test_good(mock_anthropic_key):
    api_key = mock_anthropic_key  # Mock key from conftest.py

# ✅ GOOD - Use monkeypatch
def test_good_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "mock-key")
```

### Environment Isolation

```python
# ❌ BAD - Direct os.environ manipulation
def test_bad():
    os.environ["KEY"] = "value"  # Pollutes global state

# ✅ GOOD - Use monkeypatch fixture
def test_good(monkeypatch):
    monkeypatch.setenv("KEY", "value")  # Auto-cleanup
```

### Database Isolation

```python
# ✅ GOOD - Use tmp_path fixture
async def test_database(tmp_path):
    db_path = tmp_path / "test.db"  # Isolated temp file
    db = Database(db_path)
    # Automatically cleaned up after test
```

## 🧪 Writing New Tests

### Test Naming Convention

```python
# Format: test_<what>_<when>_<expected>
def test_settings_requires_anthropic_api_key():
    """Test that Settings raises error if ANTHROPIC_API_KEY is missing."""
    pass

def test_domain_create_idempotent():
    """Test that creating the same domain twice doesn't duplicate."""
    pass
```

### Test Structure (AAA Pattern)

```python
def test_example(monkeypatch):
    # Arrange - Set up test conditions
    monkeypatch.setenv("API_KEY", "mock-key")

    # Act - Execute the code under test
    result = function_to_test()

    # Assert - Verify the results
    assert result == expected_value
```

### Async Test Template

```python
@pytest.mark.asyncio
async def test_async_function(test_db):
    # Arrange
    repo = Repository(test_db)

    # Act
    result = await repo.some_async_method()

    # Assert
    assert result is not None
```

### Mock External Services

```python
from unittest.mock import Mock, patch

@patch("httpx.Client.get")
def test_http_call(mock_get):
    # Arrange
    mock_response = Mock()
    mock_response.json.return_value = {"key": "value"}
    mock_get.return_value = mock_response

    # Act
    result = function_that_calls_http()

    # Assert
    assert "value" in result
```

## 📝 Test Documentation

Every test should have:

1. **Descriptive name**: `test_<what>_<when>_<expected>`
2. **Docstring**: Explain what is being tested and why
3. **Comments**: Clarify non-obvious setup or assertions
4. **Markers**: Categorize the test appropriately

```python
@pytest.mark.unit
def test_settings_env_var_precedence(tmp_path, monkeypatch):
    """Test that environment variables take precedence over .env file.

    Security Note: Ensures deployment environment variables
    can override .env file values (important for production).

    This validates the expected behavior where:
    1. .env file provides defaults
    2. Environment variables override defaults
    3. Deployment configs can safely override local configs
    """
    # Arrange - Create .env file
    env_file = tmp_path / ".env"
    env_file.write_text("API_KEY=from-file\n")

    # Arrange - Set environment variable
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("API_KEY", "from-env")

    # Act
    settings = Settings()

    # Assert - Environment variable wins
    assert settings.api_key == "from-env"
```

## 🚀 CI/CD Integration

### GitHub Actions Example

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: |
          pip install -e ".[dev]"

      - name: Run tests
        run: |
          pytest tests/ \
            -m "not requires_api" \
            --cov=backend \
            --cov-report=xml \
            --cov-report=term-missing

      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          file: ./coverage.xml
```

## 📚 Additional Resources

- [pytest Documentation](https://docs.pytest.org/)
- [pytest-asyncio Documentation](https://pytest-asyncio.readthedocs.io/)
- [pytest-cov Documentation](https://pytest-cov.readthedocs.io/)
- [Testing Best Practices](https://docs.python-guide.org/writing/tests/)

## ❓ FAQ

### Q: Why use monkeypatch instead of direct os.environ manipulation?

**A:** monkeypatch provides:
- Automatic cleanup (even if test fails)
- Test isolation (changes don't affect other tests)
- Thread safety (for parallel test execution)
- Best practice recommended by pytest

### Q: When should I use unit vs integration tests?

**A:**
- **Unit**: Testing a single function/class in isolation
- **Integration**: Testing interactions between components

### Q: How do I test async code?

**A:** Use `@pytest.mark.asyncio` decorator and `async def test_...():` syntax. Pytest-asyncio handles the event loop automatically.

### Q: How do I mock external APIs?

**A:** Use `unittest.mock.patch` or pytest-mock fixtures. See examples in test_tools.py.

### Q: How do I skip tests in CI but run them locally?

**A:** Mark tests with `@pytest.mark.requires_api` and skip them in CI with `-m "not requires_api"`.

## 🤝 Contributing

When adding new tests:

1. Follow existing patterns in conftest.py and test files
2. Use appropriate fixtures from conftest.py
3. Add markers (`@pytest.mark.unit`, etc.)
4. Include comprehensive docstrings
5. Ensure tests pass: `pytest tests/ -v`
6. Check coverage: `pytest tests/ --cov=backend`
7. Run linters: `ruff check tests/`

## 📧 Support

For questions about testing:
1. Check this README
2. Review existing tests for examples
3. Check pytest documentation
4. Ask the team
