"""Tests for SmolAgents tools with resource management.

Test Categories:
- Resource Management: Validates __del__ cleanup of httpx.Client instances
- Security: Tests SSRF protection for URL fetching
- Error Handling: Validates graceful degradation on failures

Best Practices Applied:
- Uses fixtures from conftest.py for mock credentials
- Proper resource cleanup with gc.collect()
- Mock-based testing to avoid real network calls
- Security testing for SSRF vulnerabilities
- Error case coverage

Test Type: Unit tests (marked automatically by conftest.py)
"""

import gc
from unittest.mock import Mock, patch

import httpx
import pytest

from backend.agents.tools import FetchURLTool, WebSearchTool


@pytest.mark.unit
class TestWebSearchToolResourceManagement:
    """Test WebSearchTool resource cleanup and lifecycle.

    Validates:
    - Client initialization
    - Resource cleanup via __del__
    - Error handling
    - API key validation
    """

    def test_client_initialized_on_creation(self, mock_brave_key):
        """Test that httpx.Client is created during __init__."""
        tool = WebSearchTool(api_key=mock_brave_key)
        assert hasattr(tool, "client")
        assert isinstance(tool.client, httpx.Client)
        # Cleanup
        del tool
        gc.collect()

    def test_client_closed_on_deletion(self, mock_brave_key):
        """Test that httpx.Client is closed when tool is destroyed.

        Security Note: Ensures no resource leaks in long-running processes.
        """
        tool = WebSearchTool(api_key=mock_brave_key)
        client = tool.client

        # Mock the close method to verify it's called
        with patch.object(client, "close") as mock_close:
            del tool
            gc.collect()  # Force garbage collection
            mock_close.assert_called_once()

    def test_del_safe_with_missing_client(self, mock_brave_key):
        """Test that __del__ doesn't error if client wasn't initialized.

        Edge Case: Validates defensive programming with hasattr() check.
        """
        tool = WebSearchTool(api_key=mock_brave_key)
        # Remove client attribute to simulate partial initialization
        delattr(tool, "client")

        # Should not raise
        try:
            del tool
            gc.collect()
        except Exception as e:
            pytest.fail(f"__del__ raised exception with missing client: {e}")

    @patch("httpx.Client.get")
    def test_search_with_valid_api_key(self, mock_get, mock_brave_key, mock_brave_search_response):
        """Test web search with valid API key returns results."""
        # Use mock response from conftest
        mock_response = Mock()
        mock_response.json.return_value = mock_brave_search_response
        mock_get.return_value = mock_response

        tool = WebSearchTool(api_key=mock_brave_key)
        result = tool.forward("test query")

        assert "Test Result 1" in result
        assert "https://example.com/1" in result
        assert "First test result description" in result

        # Cleanup
        del tool
        gc.collect()

    def test_search_without_api_key(self):
        """Test web search without API key returns error.

        Security: Validates that tool fails gracefully without credentials.
        """
        tool = WebSearchTool(api_key=None)
        result = tool.forward("test query")

        assert "Error: Search API key not configured" in result

        # Cleanup
        del tool
        gc.collect()

    @patch("httpx.Client.get")
    def test_search_handles_http_errors(self, mock_get, mock_brave_key):
        """Test web search handles HTTP errors gracefully.

        Fault Tolerance: Tools never raise, always return error strings.
        """
        mock_get.side_effect = httpx.HTTPError("Connection failed")

        tool = WebSearchTool(api_key=mock_brave_key)
        result = tool.forward("test query")

        assert "Error performing search" in result
        assert "Connection failed" in result

        # Cleanup
        del tool
        gc.collect()

    @patch("httpx.Client.get")
    def test_search_with_no_results(self, mock_get, mock_brave_key):
        """Test web search when API returns no results."""
        # Empty results
        mock_response = Mock()
        mock_response.json.return_value = {"web": {"results": []}}
        mock_get.return_value = mock_response

        tool = WebSearchTool(api_key=mock_brave_key)
        result = tool.forward("very specific query with no results")

        assert "No results found" in result

        # Cleanup
        del tool
        gc.collect()


@pytest.mark.unit
class TestFetchURLToolResourceManagement:
    """Test FetchURLTool resource cleanup and lifecycle.

    Validates:
    - Client initialization
    - Resource cleanup via __del__
    - SSRF protection
    - Content extraction
    - Error handling
    """

    def test_client_initialized_on_creation(self):
        """Test that httpx.Client is created during __init__."""
        tool = FetchURLTool()
        assert hasattr(tool, "client")
        assert isinstance(tool.client, httpx.Client)
        # Cleanup
        del tool
        gc.collect()

    def test_client_closed_on_deletion(self):
        """Test that httpx.Client is closed when tool is destroyed.

        Security Note: Ensures no resource leaks in long-running processes.
        """
        tool = FetchURLTool()
        client = tool.client

        # Mock the close method to verify it's called
        with patch.object(client, "close") as mock_close:
            del tool
            gc.collect()  # Force garbage collection
            mock_close.assert_called_once()

    def test_del_safe_with_missing_client(self):
        """Test that __del__ doesn't error if client wasn't initialized.

        Edge Case: Validates defensive programming with hasattr() check.
        """
        tool = FetchURLTool()
        # Remove client attribute to simulate partial initialization
        delattr(tool, "client")

        # Should not raise
        try:
            del tool
            gc.collect()
        except Exception as e:
            pytest.fail(f"__del__ raised exception with missing client: {e}")

    # SSRF Protection Tests
    def test_fetch_blocks_private_ip(self):
        """Test that SSRF protection blocks private IP addresses.

        Security: Prevents access to internal networks (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16).
        """
        tool = FetchURLTool()
        result = tool.forward("http://192.168.1.1/admin")

        assert "Error: URL blocked for security reasons" in result
        assert "Private IP address not allowed" in result

        # Cleanup
        del tool
        gc.collect()

    def test_fetch_blocks_localhost(self):
        """Test that SSRF protection blocks localhost.

        Security: Prevents access to services running on localhost/127.0.0.1.
        """
        tool = FetchURLTool()
        result = tool.forward("http://localhost:8080/secret")

        assert "Error: URL blocked for security reasons" in result
        assert "Loopback address not allowed" in result

        # Cleanup
        del tool
        gc.collect()

    def test_fetch_blocks_cloud_metadata(self):
        """Test that SSRF protection blocks cloud metadata endpoint.

        Security: Prevents access to AWS/GCP/Azure metadata service (169.254.169.254).
        Critical for cloud deployments.
        """
        tool = FetchURLTool()
        result = tool.forward("http://169.254.169.254/latest/meta-data/")

        assert "Error: URL blocked for security reasons" in result

        # Cleanup
        del tool
        gc.collect()

    def test_fetch_blocks_link_local(self):
        """Test that SSRF protection blocks link-local addresses.

        Security: Prevents access to link-local range (169.254.0.0/16).
        """
        tool = FetchURLTool()
        result = tool.forward("http://169.254.1.1/config")

        assert "Error: URL blocked for security reasons" in result

        # Cleanup
        del tool
        gc.collect()

    @patch("httpx.Client.get")
    def test_fetch_valid_url_extracts_content(self, mock_get):
        """Test fetching valid URL extracts and returns content.

        Validates: HTML parsing and text extraction with BeautifulSoup.
        """
        # Mock HTML response
        mock_response = Mock()
        mock_response.text = """
        <html>
            <head><title>Test Page</title></head>
            <body>
                <h1>Test Heading</h1>
                <p>Test paragraph content.</p>
            </body>
        </html>
        """
        mock_get.return_value = mock_response

        tool = FetchURLTool()
        result = tool.forward("https://example.com/article")

        assert "Test Heading" in result
        assert "Test paragraph content" in result

        # Cleanup
        del tool
        gc.collect()

    @patch("httpx.Client.get")
    def test_fetch_handles_http_errors(self, mock_get):
        """Test fetch handles HTTP errors gracefully.

        Fault Tolerance: Tools never raise, always return error strings.
        """
        mock_get.side_effect = httpx.HTTPError("404 Not Found")

        tool = FetchURLTool()
        result = tool.forward("https://example.com/missing")

        assert "Error fetching URL" in result
        assert "404 Not Found" in result

        # Cleanup
        del tool
        gc.collect()

    @patch("httpx.Client.get")
    def test_fetch_truncates_long_content(self, mock_get):
        """Test that fetched content is truncated to prevent token overflow.

        Performance: Limits content to 10000 chars to avoid excessive LLM token usage.
        """
        # Mock very long content
        long_content = "A" * 20000  # 20k characters
        mock_response = Mock()
        mock_response.text = f"<html><body><p>{long_content}</p></body></html>"
        mock_get.return_value = mock_response

        tool = FetchURLTool()
        result = tool.forward("https://example.com/long-article")

        # Should be truncated (with some overhead for HTML tags)
        assert len(result) < 12000  # 10k content + some overhead

        # Cleanup
        del tool
        gc.collect()
