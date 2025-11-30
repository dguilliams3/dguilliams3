"""SmolAgents tool definitions for research discovery."""

import logging
from datetime import datetime
from typing import Any
from uuid import uuid4

import httpx
from bs4 import BeautifulSoup
from smolagents import Tool

from backend.db.sqlite import ItemRepository
from backend.models.domain import Item

logger = logging.getLogger(__name__)


class WebSearchTool(Tool):
    """Search the web for recent information using Brave Search API."""

    name = "web_search"
    description = """Search the web for recent information on a topic.
    Returns a formatted list of search results with titles, URLs, and snippets.
    Use this to discover recent news, papers, and developments in a domain."""

    inputs = {
        "query": {
            "type": "string",
            "description": "The search query to execute",
        },
        "max_results": {
            "type": "integer",
            "description": "Maximum number of results to return (default: 10)",
            "nullable": True,
        },
    }
    output_type = "string"

    def __init__(self, api_key: str | None = None) -> None:
        super().__init__()
        self.api_key = api_key

    def forward(self, query: str, max_results: int = 10) -> str:
        """Execute web search."""
        if not self.api_key:
            return "Error: Search API key not configured"

        try:
            url = "https://api.search.brave.com/res/v1/web/search"
            headers = {
                "Accept": "application/json",
                "X-Subscription-Token": self.api_key,
            }
            params = {"q": query, "count": max_results}

            response = httpx.get(url, headers=headers, params=params, timeout=10.0)
            response.raise_for_status()

            data = response.json()
            results = data.get("web", {}).get("results", [])

            if not results:
                return f"No results found for query: {query}"

            formatted = [f"Search results for: {query}\n"]
            for i, result in enumerate(results, 1):
                title = result.get("title", "No title")
                url = result.get("url", "")
                description = result.get("description", "")
                formatted.append(f"{i}. {title}\n   URL: {url}\n   {description}\n")

            return "\n".join(formatted)

        except Exception as e:
            logger.error(f"Web search failed: {e}")
            return f"Error performing search: {str(e)}"


class FetchURLTool(Tool):
    """Fetch and extract content from a URL."""

    name = "fetch_url"
    description = """Fetch content from a URL and extract the main text.
    Returns cleaned text content suitable for analysis.
    Use this to get full content from promising search results."""

    inputs = {
        "url": {
            "type": "string",
            "description": "The URL to fetch",
        }
    }
    output_type = "string"

    def forward(self, url: str) -> str:
        """Fetch and extract content from URL."""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (compatible; ResearchBot/1.0)",
            }
            response = httpx.get(url, headers=headers, timeout=15.0, follow_redirects=True)
            response.raise_for_status()

            # Extract text using BeautifulSoup
            soup = BeautifulSoup(response.content, "lxml")

            # Remove script and style elements
            for script in soup(["script", "style", "nav", "footer", "header"]):
                script.decompose()

            # Get text
            text = soup.get_text(separator="\n", strip=True)

            # Clean up whitespace
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            cleaned = "\n".join(lines)

            # Truncate if too long (keep first 10000 chars)
            if len(cleaned) > 10000:
                cleaned = cleaned[:10000] + "\n\n[Content truncated...]"

            return f"Content from {url}:\n\n{cleaned}"

        except Exception as e:
            logger.error(f"Failed to fetch {url}: {e}")
            return f"Error fetching URL: {str(e)}"


class StoreItemTool(Tool):
    """Store a discovered research item in the knowledge base."""

    name = "store_item"
    description = """Store a discovered research item in the database.
    Use this after discovering and analyzing a significant finding.
    All fields are required."""

    inputs = {
        "domain_id": {
            "type": "string",
            "description": "The domain ID this item belongs to",
        },
        "title": {
            "type": "string",
            "description": "Title of the research item",
        },
        "source": {
            "type": "string",
            "description": "Source name (e.g., 'Nature', 'arXiv', 'Tech blog')",
        },
        "source_url": {
            "type": "string",
            "description": "URL of the source",
        },
        "summary": {
            "type": "string",
            "description": "Brief summary of the finding",
        },
        "significance": {
            "type": "string",
            "description": "Why this finding is significant",
        },
        "significance_score": {
            "type": "number",
            "description": "Significance score from 0.0 to 1.0",
        },
    }
    output_type = "string"

    def __init__(self, repository: ItemRepository, domain_id: str) -> None:
        super().__init__()
        self.repository = repository
        self.domain_id = domain_id

    def forward(
        self,
        domain_id: str,
        title: str,
        source: str,
        source_url: str,
        summary: str,
        significance: str,
        significance_score: float,
    ) -> str:
        """Store item in database."""
        try:
            # Create item
            item = Item(
                id=str(uuid4()),
                domain_id=domain_id,
                title=title,
                source=source,
                source_url=source_url,
                summary=summary,
                significance=significance,
                significance_score=significance_score,
                discovered_at=datetime.utcnow(),
            )

            # This is a synchronous tool, but the repository is async
            # We'll handle this in the agent orchestrator
            # For now, just return the item data
            return f"Item prepared for storage: {item.id} - {title} (score: {significance_score})"

        except Exception as e:
            logger.error(f"Failed to prepare item: {e}")
            return f"Error preparing item: {str(e)}"


class SemanticSearchTool(Tool):
    """Search stored items by semantic similarity."""

    name = "semantic_search"
    description = """Search stored research items using semantic similarity.
    Returns items relevant to your query, even if they don't match exact keywords.
    Use this to find related previous discoveries."""

    inputs = {
        "query": {
            "type": "string",
            "description": "The search query",
        },
        "domain_id": {
            "type": "string",
            "description": "Optional domain filter",
            "nullable": True,
        },
        "limit": {
            "type": "integer",
            "description": "Maximum number of results (default: 5)",
            "nullable": True,
        },
    }
    output_type = "string"

    def __init__(self, embeddings: Any) -> None:  # EmbeddingStore type
        super().__init__()
        self.embeddings = embeddings

    def forward(self, query: str, domain_id: str | None = None, limit: int = 5) -> str:
        """Search for semantically similar items."""
        try:
            # This will be implemented with ChromaDB
            results = self.embeddings.search(query, domain_id=domain_id, limit=limit)

            if not results:
                return f"No similar items found for: {query}"

            formatted = [f"Similar items for: {query}\n"]
            for i, (item, score) in enumerate(results, 1):
                formatted.append(
                    f"{i}. {item.title} (similarity: {score:.2f})\n"
                    f"   {item.summary[:200]}...\n"
                )

            return "\n".join(formatted)

        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            return f"Error performing semantic search: {str(e)}"
