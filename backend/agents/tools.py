"""SmolAgents tool definitions for LLM-powered research discovery.

This module defines the tool layer for ToolCallingAgent instances. Tools are the
primitive actions that agents can execute to interact with the world (web search,
content fetching, data storage).

Design Philosophy (ADR-001):
    - SmolAgents ToolCallingAgent uses native function calling (not code generation)
    - Tools are explicitly defined with typed inputs/outputs
    - Tool descriptions guide LLM on when and how to use each tool
    - Tools return formatted strings that LLM can parse and act upon
    - Error handling is graceful (returns error strings, doesn't raise exceptions)

Architecture:
    ┌──────────────────┐
    │ ToolCallingAgent │
    └────────┬─────────┘
             │ calls tools based on prompt
             ├────────────┬────────────┬────────────┬──────────────┐
             ▼            ▼            ▼            ▼              ▼
      WebSearchTool  FetchURLTool  StoreItemTool  SemanticSearchTool  ...

Tool Lifecycle:
    1. Tool instantiated with dependencies (API keys, repositories)
    2. Agent receives prompt requesting information
    3. LLM determines which tool(s) to call with what parameters
    4. Tool executes action and returns formatted string result
    5. LLM processes result and decides next action or final answer

Tool Design Patterns:
    - Input schema: Typed dict with descriptions (guides LLM parameter selection)
    - Output type: Always "string" (LLM-friendly format)
    - Error handling: Return error strings, log exceptions, never raise
    - Formatting: Structured text output that LLM can parse (numbered lists, sections)
    - Truncation: Limit output length to prevent context overflow

Available Tools:
    - WebSearchTool: Search web using Brave API (returns titles, URLs, snippets)
    - FetchURLTool: Fetch and extract content from URLs (returns cleaned text)
    - StoreItemTool: Prepare research items for storage (returns confirmation)
    - SemanticSearchTool: Find similar items using embeddings (returns related items)

Usage Example:
    ```python
    from backend.agents.tools import WebSearchTool, FetchURLTool
    from smolagents import ToolCallingAgent, AnthropicModel

    # Create tools
    tools = [
        WebSearchTool(api_key=os.getenv("BRAVE_API_KEY")),
        FetchURLTool(),
    ]

    # Create agent with tools
    model = AnthropicModel(model_id="claude-3-haiku-20240307", api_key="...")
    agent = ToolCallingAgent(tools=tools, model=model, max_steps=15)

    # Agent autonomously decides when to call tools
    prompt = "Search for recent quantum computing breakthroughs and fetch the most significant one"
    result = agent.run(prompt)
    # Agent will: call web_search → analyze results → call fetch_url → analyze content → return final answer
    ```

Tool vs Direct API Calls:
    ❌ BAD - Direct API call (agent can't iterate):
        response = anthropic.messages.create(
            model="claude-3-haiku-20240307",
            messages=[{"role": "user", "content": "Find quantum news"}]
        )
        # LLM can't actually search - just hallucinates results

    ✅ GOOD - Tool-equipped agent (can iterate):
        agent = ToolCallingAgent(tools=[WebSearchTool(api_key=key)])
        result = agent.run("Find quantum news")
        # LLM calls web_search tool, gets real results, analyzes them

Integration with DomainAgent:
    DomainAgent creates ToolCallingAgent instances with appropriate tools:
    - Discovery phase: WebSearchTool + FetchURLTool (find and extract content)
    - Synthesis phase: SemanticSearchTool (find related context)
    - RAG phase: SemanticSearchTool (retrieve relevant items for Q&A)

Error Handling Strategy:
    Tools never raise exceptions to calling agent. Instead:
    1. Catch all exceptions in try/except blocks
    2. Log error details for debugging
    3. Return formatted error string to LLM
    4. LLM can see error and adjust strategy (try different query, skip item, etc.)

Performance Considerations:
    - web_search: ~500ms per query (Brave API latency)
    - fetch_url: ~1-3s per URL (network + parsing)
    - store_item: Instant (just prepares data)
    - semantic_search: ~50-100ms per query (ChromaDB)

    Max steps of 15 allows ~10 web searches + 5 fetches before termination.

Security Notes:
    - FetchURLTool includes User-Agent to identify bot traffic
    - Follows redirects but doesn't execute JavaScript
    - Truncates content to prevent excessive token usage
    - No code execution risk (vs CodeAgent which generates Python)

Future Enhancements:
    - ArXivSearchTool: Direct arXiv API integration
    - ScholarSearchTool: Google Scholar scraping (with rate limiting)
    - TwitterSearchTool: Track discussions on research topics
    - ValidationTool: Check if finding was debunked or corrected

See Also:
    - ARCHITECTURE_DECISIONS.md: ADR-001 (ToolCallingAgent vs CodeAgent)
    - backend/agents/base.py: DomainAgent using these tools
    - SmolAgents docs: https://huggingface.co/docs/smolagents
"""

import ipaddress
import logging
from datetime import datetime
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from bs4 import BeautifulSoup
from smolagents import Tool

from backend.db.sqlite import ItemRepository
from backend.models.domain import Item

logger = logging.getLogger(__name__)


def _is_safe_url(url: str) -> tuple[bool, str]:
    """Validate URL for SSRF protection.

    Args:
        url: URL to validate

    Returns:
        Tuple of (is_safe, error_message)

    Security Checks:
        - Scheme must be http or https
        - No private IP ranges (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)
        - No localhost or loopback (127.0.0.0/8, ::1)
        - No link-local addresses (169.254.0.0/16)
        - No cloud metadata endpoints
        - No special-use addresses

    Design Note:
        This prevents SSRF (Server-Side Request Forgery) attacks where
        malicious URLs could access internal services or cloud metadata.
    """
    try:
        parsed = urlparse(url)

        # Check scheme
        if parsed.scheme not in ("http", "https"):
            return False, f"Invalid scheme: {parsed.scheme}. Only http/https allowed."

        # Get hostname
        hostname = parsed.hostname
        if not hostname:
            return False, "No hostname in URL"

        # Try to resolve to IP address
        try:
            # Get IP address from hostname
            import socket
            ip = socket.gethostbyname(hostname)
            ip_addr = ipaddress.ip_address(ip)

            # Block private IP ranges
            if ip_addr.is_private:
                return False, f"Private IP address not allowed: {ip}"

            # Block loopback
            if ip_addr.is_loopback:
                return False, f"Loopback address not allowed: {ip}"

            # Block link-local (169.254.0.0/16 - AWS/cloud metadata)
            if ip_addr.is_link_local:
                return False, f"Link-local address not allowed: {ip}"

            # Block reserved/special-use addresses
            if ip_addr.is_reserved:
                return False, f"Reserved IP address not allowed: {ip}"

            # Additional check for cloud metadata endpoint
            if ip == "169.254.169.254":
                return False, "Cloud metadata endpoint not allowed"

        except socket.gaierror:
            # DNS resolution failed - could be invalid domain
            # We'll allow this and let httpx handle it with proper error
            pass

        return True, ""

    except Exception as e:
        return False, f"URL validation error: {str(e)}"


class WebSearchTool(Tool):
    """Search the web for recent information using Brave Search API.

    This tool enables agents to discover current research developments, news,
    papers, and discussions by searching the web. Returns formatted search
    results that the LLM can analyze to decide which sources to investigate.

    Input Parameters:
        query (str): Search query to execute (e.g., "quantum computing 2024 breakthrough")
        max_results (int): Max results to return, default 10 (higher = more context, slower)

    Output Format:
        Formatted string with numbered search results:
        ```
        Search results for: quantum computing

        1. Quantum breakthrough at IBM
           URL: https://ibm.com/news/...
           IBM researchers achieve error correction milestone...

        2. New quantum algorithm published
           URL: https://arxiv.org/...
           Researchers propose algorithm for factoring large numbers...
        ```

    Tool Use Cases:
        - Discovery phase: Find recent developments in research domains
        - Broad sweep: "quantum computing 2024" → get overview of recent work
        - Specific queries: "Claude 3.5 Sonnet release notes" → targeted information
        - Multi-step: Agent can issue multiple searches with refined queries

    API Details:
        - Provider: Brave Search API (https://brave.com/search/api/)
        - Rate limits: Varies by plan
        - Latency: ~500ms per query
        - Cost: Free tier available, paid plans for production

    Error Handling:
        - Missing API key → Returns error message (agent can't search)
        - Network failure → Returns error with details (agent can retry)
        - No results → Returns "No results found" (agent can refine query)
        - API error → Returns error (agent can try alternative approach)

    Design Notes:
        - Returns formatted text (not JSON) for LLM readability
        - Includes title, URL, and snippet for each result
        - Truncates descriptions to prevent token overflow
        - Agent decides which results merit deeper investigation (fetch_url)

    Example Agent Flow:
        ```
        Agent receives: "Find quantum computing breakthroughs from 2024"
        Agent calls: web_search(query="quantum computing breakthrough 2024", max_results=10)
        Tool returns: Formatted list of 10 results
        Agent analyzes: Picks 3 most promising based on titles/snippets
        Agent calls: fetch_url for each of the 3 URLs
        Agent synthesizes: Creates final answer from fetched content
        ```

    Comparison to Alternatives:
        - Google Search API: More expensive, similar quality
        - DuckDuckGo: No official API, scraping fragile
        - Bing API: Good alternative, slightly different results
        - Choice: Brave for privacy focus and good developer experience
    """

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
        """Initialize web search tool with Brave API key.

        Args:
            api_key: Brave Search API key. If None, tool will return errors.
                    Get key from: https://brave.com/search/api/

        Design Note:
            Accepts None to allow tool instantiation without key (useful for
            testing or when tool won't be used). Tool gracefully handles
            missing key by returning error message.
        """
        super().__init__()
        self.api_key = api_key

    def forward(self, query: str, max_results: int = 10) -> str:
        """Execute web search and return formatted results.

        Args:
            query: Search query string
            max_results: Number of results to return (default 10)

        Returns:
            Formatted string with search results or error message.
            Never raises exceptions - always returns string for LLM to parse.

        Implementation Notes:
            - Uses Brave Search REST API
            - Returns only web results (excludes news, images, videos)
            - Formats as numbered list for LLM readability
            - Logs errors but returns error string (doesn't raise)
        """
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
    """Fetch and extract text content from URLs.

    This tool enables agents to retrieve full content from promising URLs
    discovered via web search. Extracts clean text from HTML pages using
    BeautifulSoup, removing navigation, scripts, and styling.

    Input Parameters:
        url (str): URL to fetch (e.g., "https://arxiv.org/abs/2024.12345")

    Output Format:
        ```
        Content from https://example.com/article:

        [Cleaned text content with whitespace normalized]

        [Content truncated...] (if > 10000 chars)
        ```

    Tool Use Cases:
        - Deep dive: After web_search finds promising results
        - Content extraction: Pull full text from research papers, blog posts, news
        - Multi-source: Agent can fetch 3-5 URLs to build comprehensive understanding
        - Verification: Check if title/snippet accurately represent full content

    Extraction Strategy:
        1. Fetch HTML with httpx (follows redirects, 15s timeout)
        2. Parse with BeautifulSoup (lxml parser for speed)
        3. Remove non-content elements (nav, footer, header, script, style)
        4. Extract text with newline separators
        5. Clean whitespace (strip lines, remove empty lines)
        6. Truncate to 10000 chars (prevents token overflow)

    Error Handling:
        - Network errors (timeout, DNS failure) → Returns error message
        - HTTP errors (404, 500) → Returns error with status code
        - Parsing errors → Returns error (malformed HTML)
        - Paywall/login required → Returns partial content or error

    Design Notes:
        - 10000 char limit chosen to fit in ~2500 tokens
        - Truncates rather than fails (partial content better than none)
        - Includes URL in output so LLM knows source
        - User-Agent identifies as bot for transparency

    Example Agent Flow:
        ```
        Agent receives search results with 10 URLs
        Agent analyzes: Picks top 3 most relevant based on titles
        Agent calls: fetch_url(url_1), fetch_url(url_2), fetch_url(url_3)
        Tool returns: 3 text blocks with full content
        Agent reads: Analyzes all 3 to extract key findings
        Agent scores: Determines significance of each finding
        ```

    Limitations:
        - JavaScript rendering: Can't execute JS (no Playwright/Selenium)
        - Paywalls: Can't access content behind login
        - PDFs: Doesn't extract text from PDFs (could enhance)
        - Rate limiting: No built-in rate limiting (agent makes choices)

    Future Enhancements:
        - PDF extraction using PyPDF2 or pdfplumber
        - Retry logic with exponential backoff
        - Caching of fetched content (avoid re-fetch)
        - Smarter truncation (prefer complete paragraphs)

    Performance:
        - Latency: 1-3 seconds per URL (network + parsing)
        - Max steps budget: 15 steps allows ~5 fetches
        - Memory: BeautifulSoup is memory-efficient for small pages
    """

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
        """Fetch and extract text content from URL.

        Args:
            url: URL to fetch content from

        Returns:
            Formatted string with extracted content or error message.
            Never raises - always returns string for LLM.

        Implementation:
            - Validates URL for SSRF protection (blocks private IPs, localhost, etc.)
            - Uses httpx for async-capable HTTP (though called sync here)
            - BeautifulSoup with lxml for fast HTML parsing
            - Removes nav/footer/header/script/style for cleaner text
            - Truncates to 10000 chars to prevent token overflow

        Security:
            SSRF protection via _is_safe_url():
            - Only http/https schemes allowed
            - Blocks private IP ranges, localhost, cloud metadata
            - Prevents access to internal services

        Design Note:
            Returns formatted string prefixed with URL so LLM knows
            the source of content (important for citation/attribution).
        """
        # SECURITY: Validate URL to prevent SSRF attacks
        is_safe, error_msg = _is_safe_url(url)
        if not is_safe:
            logger.warning(f"Blocked unsafe URL: {url} - {error_msg}")
            return f"Error: URL blocked for security reasons - {error_msg}"

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
    """Prepare discovered research item for storage in knowledge base.

    NOTE: This tool currently just prepares/validates items but doesn't
    actually store them. Storage happens in orchestrator after agent completes.
    This design separates agent logic (discovery) from persistence (orchestrator).

    Input Parameters (all required):
        domain_id (str): Domain identifier (e.g., "physics", "alignment")
        title (str): Descriptive title of finding
        source (str): Source name (e.g., "Nature", "arXiv", "HackerNews")
        source_url (str): URL of the finding
        summary (str): Brief summary of what was found
        significance (str): Why this finding matters
        significance_score (float): Numeric score 0.0-1.0 (higher = more significant)

    Output Format:
        ```
        Item prepared for storage: abc-123 - Quantum breakthrough (score: 0.9)
        ```

    Tool Use Cases:
        - Discovery phase: After agent finds and scores a significant item
        - Structured output: Forces agent to provide all required fields
        - Validation: Ensures items have proper structure before storage

    Design Rationale:
        Why not actually store here?
        1. Tools are synchronous but storage is async (ItemRepository is async)
        2. Orchestrator needs to handle duplicates, embeddings, events
        3. Separation of concerns: Agent discovers, orchestrator persists
        4. Agent can "prepare" multiple items, orchestrator decides what to store

    Example Agent Flow:
        ```
        Agent searches and fetches content
        Agent determines item is significant (score > 0.7)
        Agent calls: store_item(
            domain_id="physics",
            title="Quantum error correction milestone",
            source="Nature",
            source_url="https://nature.com/...",
            summary="IBM achieves 99.9% fidelity in error correction",
            significance="Brings practical quantum computing closer",
            significance_score=0.9
        )
        Tool returns: Confirmation with item ID
        Agent continues: Looks for more items
        Agent finishes: Returns all prepared items via final_answer
        Orchestrator receives: List of prepared items
        Orchestrator stores: Each item in database + embeddings
        ```

    Significance Scoring Guidance:
        - 0.9-1.0: Breakthrough discoveries (major theoretical advances, paradigm shifts)
        - 0.7-0.9: Important findings (significant results, useful tools)
        - 0.5-0.7: Notable developments (incremental progress, interesting work)
        - 0.3-0.5: Minor updates (small improvements, blog posts)
        - 0.0-0.3: Low signal (opinion pieces, speculation)

        Agents typically filter for score >= 0.6 to avoid noise.

    Future Enhancement:
        Could make this actually async by using SmolAgents' async tool support,
        then directly store items. Trade-off: tighter coupling, less orchestrator control.
    """

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
        """Initialize store item tool with repository and domain.

        Args:
            repository: ItemRepository for database access (currently unused)
            domain_id: Domain this tool stores items for

        Design Note:
            Repository is accepted but not used since storage happens in
            orchestrator. Kept for future enhancement to direct storage.
        """
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
        """Prepare item for storage by creating Item instance.

        Args:
            domain_id: Domain identifier
            title: Item title
            source: Source name
            source_url: Source URL
            summary: Brief summary
            significance: Why it matters
            significance_score: Score 0.0-1.0

        Returns:
            Confirmation string with item ID and details.
            Never raises - returns error string on failure.

        Implementation Note:
            Creates Item instance but doesn't persist to database.
            Actual storage handled by orchestrator after agent completes.
            This separation allows orchestrator to handle:
            - Duplicate detection
            - Embedding generation
            - Event logging
            - Transaction management
        """
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
    """Search stored items using semantic similarity via embeddings.

    This tool enables agents to find previously discovered items that are
    semantically related to a query, even if they don't share exact keywords.
    Uses ChromaDB for vector search with automatic embeddings.

    Input Parameters:
        query (str): Natural language search query
        domain_id (str, optional): Filter to specific domain
        limit (int, optional): Max results to return (default: 5)

    Output Format:
        ```
        Similar items for: quantum error correction

        1. Quantum breakthrough at IBM (similarity: 0.92)
           IBM achieves 99.9% fidelity in error correction...

        2. New quantum algorithm published (similarity: 0.85)
           Researchers propose algorithm for factoring...
        ```

    Tool Use Cases:
        - Context gathering: Find related items before synthesis
        - Deduplication: Check if finding was already discovered
        - Cross-domain: Find connections between domains
        - RAG: Retrieve context for answering user questions

    Semantic vs Keyword Search:
        Keyword: "quantum computer" only matches exact phrase
        Semantic: "quantum computer" also matches:
            - "superconducting qubit processor"
            - "quantum information processing device"
            - "quantum computing system"

        Uses embeddings to understand meaning, not just word overlap.

    Embedding Details:
        - Model: ChromaDB's default (sentence-transformers)
        - Dimension: 384 (efficient for moderate corpus size)
        - Metric: Cosine similarity (ranges 0-1)
        - Generation: Automatic on item ingestion

    Performance:
        - Latency: 50-100ms for 1000s of items
        - Scales: Sub-second for 10K+ items
        - Memory: ChromaDB loads index into memory for speed

    Example Agent Flow - Synthesis:
        ```
        Agent receives: 5 newly discovered items to synthesize
        Agent calls: semantic_search("quantum computing", limit=10)
        Tool returns: 10 related items from past discoveries
        Agent analyzes: Compares new items to historical context
        Agent synthesizes: "Building on previous work [Source 3], new finding..."
        ```

    Example Agent Flow - RAG:
        ```
        User asks: "What are recent advances in quantum error correction?"
        Agent calls: semantic_search("quantum error correction", limit=5)
        Tool returns: 5 most relevant items
        Agent reads: All 5 items
        Agent answers: "Recent advances include [Source 1] which achieved..."
        ```

    Similarity Score Interpretation:
        - 0.9-1.0: Nearly identical (likely duplicates or very similar)
        - 0.8-0.9: Highly related (same topic, different angle)
        - 0.7-0.8: Related (overlapping concepts)
        - 0.6-0.7: Somewhat related (shared domain)
        - <0.6: Tangentially related or unrelated

    Future Enhancements:
        - Hybrid search: Combine semantic + keyword matching
        - Re-ranking: Use LLM to re-rank results for query
        - Filtering: Add date range, significance score filters
        - Cross-encoder: More accurate similarity via BERT cross-encoder
    """

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
        """Initialize semantic search tool with embedding store.

        Args:
            embeddings: EmbeddingStore instance (ChromaDB wrapper)

        Design Note:
            Type hint is Any to avoid circular import. Could use
            TYPE_CHECKING pattern for proper typing without runtime import.
        """
        super().__init__()
        self.embeddings = embeddings

    def forward(self, query: str, domain_id: str | None = None, limit: int = 5) -> str:
        """Search for semantically similar items using vector similarity.

        Args:
            query: Natural language search query
            domain_id: Optional domain filter (None = search all domains)
            limit: Max results to return

        Returns:
            Formatted string with similar items and scores, or error message.
            Never raises - returns error string on failure.

        Implementation:
            - Creates embedding for query (automatic via ChromaDB)
            - Computes cosine similarity with all items
            - Returns top K matches sorted by similarity
            - Formats as numbered list with similarity scores

        Design Note:
            Truncates item summaries to 200 chars to keep output concise.
            LLM can request full item details if needed.
        """
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
