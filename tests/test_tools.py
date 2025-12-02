"""Tests for SmolAgents tools with resource management."""

import gc
from unittest.mock import Mock, patch

import httpx
import pytest

from backend.agents.tools import FetchURLTool, WebSearchTool


class TestWebSearchToolResourceManagement:
    """Test WebSearchTool resource cleanup and lifecycle."""

    def test_client_initialized_on_creation(self):
        """Test that httpx.Client is created during __init__."""
        tool = WebSearchTool(api_key="test-key")
        assert hasattr(tool, "client")
        assert isinstance(tool.client, httpx.Client)
        # Cleanup
        del tool
        gc.collect()

    def test_client_closed_on_deletion(self):
        """Test that httpx.Client is closed when tool is destroyed."""
        tool = WebSearchTool(api_key="test-key")
        client = tool.client

        # Mock the close method to verify it's called
        with patch.object(client, "close") as mock_close:
            del tool
            gc.collect()  # Force garbage collection
            mock_close.assert_called_once()

    def test_del_safe_with_missing_client(self):
        """Test that __del__ doesn't error if client wasn't initialized."""
        tool = WebSearchTool(api_key="test-key")
        # Remove client attribute to simulate partial initialization
        delattr(tool, "client")

        # Should not raise
        try:
            del tool
            gc.collect()
        except Exception as e:
            pytest.fail(f"__del__ raised exception with missing client: {e}")

    @patch("httpx.Client.get")
    def test_search_with_valid_api_key(self, mock_get):
        """Test web search with valid API key returns results."""
        # Mock response
        mock_response = Mock()
        mock_response.json.return_value = {
            "web": {
                "results": [
                    {
                        "title": "Test Result",
                        "url": "https://example.com",
                        "description": "Test description",
                    }
                ]
            }
        }
        mock_get.return_value = mock_response

        tool = WebSearchTool(api_key="test-key")
        result = tool.forward("test query")

        assert "Test Result" in result
        assert "https://example.com" in result
        assert "Test description" in result

        # Cleanup
        del tool
        gc.collect()

    def test_search_without_api_key(self):
        """Test web search without API key returns error."""
        tool = WebSearchTool(api_key=None)
        result = tool.forward("test query")

        assert "Error: Search API key not configured" in result

        # Cleanup
        del tool
        gc.collect()

    @patch("httpx.Client.get")
    def test_search_handles_http_errors(self, mock_get):
        """Test web search handles HTTP errors gracefully."""
        mock_get.side_effect = httpx.HTTPError("Connection failed")

        tool = WebSearchTool(api_key="test-key")
        result = tool.forward("test query")

        assert "Error performing search" in result
        assert "Connection failed" in result

        # Cleanup
        del tool
        gc.collect()


class TestFetchURLToolResourceManagement:
    """Test FetchURLTool resource cleanup and lifecycle."""

    def test_client_initialized_on_creation(self):
        """Test that httpx.Client is created during __init__."""
        tool = FetchURLTool()
        assert hasattr(tool, "client")
        assert isinstance(tool.client, httpx.Client)
        # Cleanup
        del tool
        gc.collect()

    def test_client_closed_on_deletion(self):
        """Test that httpx.Client is closed when tool is destroyed."""
        tool = FetchURLTool()
        client = tool.client

        # Mock the close method to verify it's called
        with patch.object(client, "close") as mock_close:
            del tool
            gc.collect()  # Force garbage collection
            mock_close.assert_called_once()

    def test_del_safe_with_missing_client(self):
        """Test that __del__ doesn't error if client wasn't initialized."""
        tool = FetchURLTool()
        # Remove client attribute to simulate partial initialization
        delattr(tool, "client")

        # Should not raise
        try:
            del tool
            gc.collect()
        except Exception as e:
            pytest.fail(f"__del__ raised exception with missing client: {e}")

    def test_fetch_blocks_private_ip(self):
        """Test that SSRF protection blocks private IP addresses."""
        tool = FetchURLTool()
        result = tool.forward("http://192.168.1.1/admin")

        assert "Error: URL blocked for security reasons" in result
        assert "Private IP address not allowed" in result

        # Cleanup
        del tool
        gc.collect()

    def test_fetch_blocks_localhost(self):
        """Test that SSRF protection blocks localhost."""
        tool = FetchURLTool()
        result = tool.forward("http://localhost:8080/secret")

        assert "Error: URL blocked for security reasons" in result
        assert "Loopback address not allowed" in result

        # Cleanup
        del tool
        gc.collect()

    def test_fetch_blocks_cloud_metadata(self):
        """Test that SSRF protection blocks cloud metadata endpoint."""
        tool = FetchURLTool()
        result = tool.forward("http://169.254.169.254/latest/meta-data/")

        assert "Error: URL blocked for security reasons" in result

        # Cleanup
        del tool
        gc.collect()

    @patch("httpx.Client.get")
    def test_fetch_valid_url_extracts_content(self, mock_get):
        """Test fetching valid URL extracts and returns content."""
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
        """Test fetch handles HTTP errors gracefully."""
        mock_get.side_effect = httpx.HTTPError("404 Not Found")

        tool = FetchURLTool()
        result = tool.forward("https://example.com/missing")

        assert "Error fetching URL" in result
        assert "404 Not Found" in result

        # Cleanup
        del tool
        gc.collect()
