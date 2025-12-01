"""Domain agent implementation using SmolAgents ToolCallingAgent pattern.

This module implements the core DomainAgent class that orchestrates autonomous research
discovery and synthesis for a specific knowledge domain (e.g., Physics, AI Alignment).

Architecture:
    - Uses SmolAgents ToolCallingAgent with Anthropic's Claude models
    - Separates prompt building from execution for transparency and debugging
    - Creates agents dynamically based on runtime configuration
    - Implements final_answer tool pattern with placeholder schemas (no concrete examples)

Key Design Decisions:
    1. ToolCallingAgent over CodeAgent: More reliable, uses native function calling
    2. Dynamic agent creation: Picks up config changes without restart
    3. Separated prompt building: Enables preview without execution
    4. Placeholder schemas: Prevents LLM overfitting to examples

Typical Flow:
    1. User triggers domain refresh via UI or schedule
    2. discover() builds prompt and runs discovery agent with web_search/fetch_url tools
    3. Agent returns structured JSON via final_answer tool
    4. filter_and_score() converts dicts to Item objects
    5. synthesize() builds synthesis prompt and creates domain update summary
    6. Results stored in database and displayed in UI

Example:
    ```python
    agent = DomainAgent(
        config=physics_config,
        item_repo=item_repository,
        event_log=event_log
    )

    # Discovery phase
    items_data = await agent.discover()  # Uses web search + fetch
    items = await agent.filter_and_score(items_data)  # Convert to Item objects

    # Synthesis phase
    update = await agent.synthesize(items)  # Create domain summary
    ```

See Also:
    - ARCHITECTURE_DECISIONS.md: ADR-001, ADR-002, ADR-004, ADR-005
    - SMOLAGENTS_GUIDE.md: Tool usage patterns and best practices
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any
from uuid import uuid4

from smolagents import ToolCallingAgent
from smolagents.models import AnthropicModel

from backend.agents.config_store import agent_config_store
from backend.agents.tools import FetchURLTool, WebSearchTool
from backend.config import settings
from backend.db.events import EventLog
from backend.db.sqlite import ItemRepository
from backend.models.domain import DomainConfig, DomainUpdate, Item

logger = logging.getLogger(__name__)


class DomainAgent:
    """Autonomous research agent for a specific knowledge domain.

    This agent performs two main functions:
    1. Discovery: Searches the web for recent developments, fetches content, scores significance
    2. Synthesis: Analyzes discovered items and creates comprehensive domain summaries

    The agent uses SmolAgents' ToolCallingAgent with the following tools:
    - WebSearchTool: Brave Search API integration for web discovery
    - FetchURLTool: Content extraction from URLs with BeautifulSoup

    Agent behavior is controlled by runtime configuration:
    - discovery_model: Which Claude model to use (haiku/sonnet/opus)
    - discovery_max_steps: How many tool calls allowed (default 15)
    - synthesis_model: Model for synthesis (default sonnet)
    - synthesis_max_steps: Tool calls for synthesis (default 3)

    Attributes:
        config (DomainConfig): Domain configuration with sources, prompts, filters
        item_repo (ItemRepository): Database repository for storing discovered items
        event_log (EventLog): Append-only event log for audit trail
        tools (list[Tool]): SmolAgents tools available to the agent

    Design Note:
        Agents are created dynamically on each run (not singletons) to:
        - Pick up fresh configuration without restart
        - Avoid stale state accumulation
        - Ensure clean agent lifecycle per run
    """

    def __init__(
        self,
        config: DomainConfig,
        item_repo: ItemRepository,
        event_log: EventLog,
    ) -> None:
        """Initialize domain agent with configuration and dependencies.

        Args:
            config: Domain configuration with name, sources, filter/synthesis prompts
            item_repo: Repository for persisting discovered items to database
            event_log: Event log for recording all agent actions

        Note:
            Does NOT create agents here - agents are created on-demand in
            _create_discovery_agent() and _create_synthesis_agent() to pick
            up latest configuration from agent_config_store.
        """
        self.config = config
        self.item_repo = item_repo
        self.event_log = event_log

        # Initialize tools (shared across all agent instances)
        self.tools = [
            WebSearchTool(api_key=settings.brave_search_api_key),
            FetchURLTool(),
        ]

    def _get_agent_config(self):
        """Fetch current runtime configuration for this domain.

        Returns:
            AgentConfig with current model selection and max_steps values

        Note:
            Config is fetched from runtime store, not database. This allows
            users to change configuration via UI without app restart.
        """
        return agent_config_store.get(self.config.id)

    def _create_discovery_agent(self) -> ToolCallingAgent:
        """Create discovery agent with current configuration.

        Discovery agent:
        - Uses web_search and fetch_url tools
        - Configured for multiple tool calls (default 15 max_steps)
        - Returns structured JSON via final_answer tool

        Returns:
            ToolCallingAgent configured for discovery with current model/max_steps

        Design Note:
            Created fresh on each discover() call to pick up config changes.
            Allows users to switch models mid-session without restart.
        """
        config = self._get_agent_config()
        model = AnthropicModel(
            model_id=config.discovery_model,
            api_key=settings.anthropic_api_key,
        )
        return ToolCallingAgent(
            tools=self.tools,
            model=model,
            max_steps=config.discovery_max_steps,
            verbosity_level=1,  # Log tool calls for debugging
        )

    def _create_synthesis_agent(self) -> ToolCallingAgent:
        """Create synthesis agent with current configuration.

        Synthesis agent:
        - No tools (just analyzes provided items)
        - Lower max_steps (default 3) since no tool use
        - Returns structured JSON via final_answer tool

        Returns:
            ToolCallingAgent configured for synthesis with current model/max_steps

        Design Note:
            Synthesis typically uses higher quality model (Sonnet) than
            discovery (Haiku) for better analytical writing.
        """
        config = self._get_agent_config()
        model = AnthropicModel(
            model_id=config.synthesis_model,
            api_key=settings.anthropic_api_key,
        )
        return ToolCallingAgent(
            tools=[],  # No tools needed for synthesis
            model=model,
            max_steps=config.synthesis_max_steps,
        )

    def build_discovery_prompt(self) -> str:
        """Build discovery prompt without executing agent.

        Constructs the full prompt that will be sent to the discovery agent,
        including:
        - Domain description and scope
        - Search queries from configured sources
        - Filtering criteria (prioritize/deprioritize)
        - Output schema with placeholder descriptions
        - Significance scoring guide

        Returns:
            Complete prompt string ready for agent execution

        Use Cases:
            - Preview in UI before running agent
            - Copy to Claude console for testing
            - Debug prompt structure
            - Validate search queries and filters

        Design Note:
            Uses placeholder descriptions ("[descriptive title]") not concrete
            examples ("Quantum breakthrough at MIT") to prevent LLM overfitting.
            See ADR-002 for rationale.
        """
        # Build search queries from sources
        search_queries = []
        for source in self.config.sources:
            if source.type == "web_search" and source.query:
                search_queries.append(source.query)

        return f"""You are researching recent developments in {self.config.name}.

Domain description: {self.config.description}

Your task:
1. Use web_search tool to find recent news, papers, and developments for each query below
2. For the most promising results (top 3-5), use fetch_url tool to get full content
3. Analyze each finding and score its significance

{self.config.filter_prompt}

Search queries to execute:
{chr(10).join(f'- {q}' for q in search_queries)}

Focus on developments from the last 7 days. Prioritize primary sources over news aggregators.

IMPORTANT: After gathering information, you MUST call final_answer with a JSON array of findings.

Expected output schema (use final_answer tool):
{{
  "findings": [
    {{
      "title": "[descriptive title of the finding]",
      "source": "[source name like Nature, arXiv, or publication name]",
      "source_url": "[full URL to the article]",
      "summary": "[2-3 sentence summary of what was discovered or announced]",
      "significance": "[explanation of why this finding matters to the field]",
      "significance_score": "[number between 0.0 and 1.0]",
      "raw_content": "[relevant excerpt from fetched content, if available]"
    }}
  ]
}}

Significance scoring guide:
- 0.0-0.3: Minor update, incremental progress
- 0.4-0.6: Notable development, worth tracking
- 0.7-0.9: Significant breakthrough or shift
- 1.0: Field-defining, paradigm-shifting

Only include items with significance_score >= 0.4.
"""

    def build_synthesis_prompt(self, items: list[Item]) -> str:
        """Build synthesis prompt for creating domain update summary.

        Constructs prompt for synthesizing multiple discovered items into:
        - 2-3 paragraph analytical summary
        - 3-5 open questions the field is investigating

        Args:
            items: List of Item objects to synthesize (usually 5-20 items)

        Returns:
            Complete synthesis prompt with formatted items and guidelines

        Design Note:
            Prompts agent to reference items by number ("Item 1 demonstrates...")
            for clear provenance. Uses placeholder schema to avoid example bias.
        """
        return f"""Synthesize a domain update for {self.config.name}.

{self.config.synthesis_prompt}

Significant items discovered:
{self._format_items_for_synthesis(items)}

Create a comprehensive update analyzing these developments.

IMPORTANT: Use final_answer tool with this exact JSON structure:
{{
  "summary": "[2-3 paragraph analysis of current state and key developments, referencing items by number]",
  "open_questions": [
    "[first open question the field is grappling with]",
    "[second open question]",
    "[third open question]",
    "[fourth open question - optional]",
    "[fifth open question - optional]"
  ]
}}

Guidelines for summary:
1. Analyze the current frontier and active areas of investigation
2. Highlight surprising developments or unexpected results
3. Note areas where progress is blocked or slow
4. Reference specific items by their number (e.g., "Item 1 demonstrates...")
5. Be analytical, not promotional - flag uncertainties and contested claims

Guidelines for open_questions:
- Focus on questions the field is actively trying to answer
- Avoid generic questions; make them specific to recent developments
- Include both technical challenges and conceptual puzzles
"""

    async def discover(self) -> list[dict[str, Any]]:
        """Execute discovery phase: search web, fetch content, score findings.

        Discovery Flow:
            1. Build discovery prompt with search queries
            2. Create ToolCallingAgent with current config
            3. Agent autonomously calls web_search for each query
            4. Agent analyzes results and selects top 3-5 to fetch
            5. Agent calls fetch_url to get full content
            6. Agent scores significance and returns via final_answer
            7. Parse JSON response into list of item dicts

        Returns:
            List of discovered item dicts with keys:
            - title, source, source_url, summary, significance, significance_score

        Logs:
            - items_discovered event with count
            - discovery_failed event on exception

        Example Result:
            [
                {
                    "title": "New quantum error correction method...",
                    "source": "Nature",
                    "source_url": "https://nature.com/...",
                    "summary": "Researchers demonstrated...",
                    "significance": "This addresses a key challenge...",
                    "significance_score": 0.75
                }
            ]

        Implementation Note:
            Agent execution runs in thread pool (asyncio.to_thread) to prevent
            blocking the event loop during long-running LLM operations.

        Note:
            Returns empty list on failure (doesn't raise exception).
            Failures logged to event log for debugging.
        """
        logger.info(f"Starting discovery for domain: {self.config.name}")

        # Build discovery prompt
        discover_prompt = self.build_discovery_prompt()

        try:
            # Create agent with current config
            discovery_agent = self._create_discovery_agent()

            # Run agent with tools (in thread pool to avoid blocking event loop)
            result = await asyncio.to_thread(discovery_agent.run, discover_prompt)

            logger.info(f"Discovery agent result type: {type(result)}")
            logger.info(f"Discovery result: {str(result)[:500]}...")

            # Parse the result - agent should return structured data via final_answer
            items_data: list[dict[str, Any]] = []

            if isinstance(result, dict) and "findings" in result:
                items_data = result["findings"]
            elif isinstance(result, list):
                items_data = result
            elif isinstance(result, str):
                # Try to parse JSON from string
                try:
                    parsed = json.loads(result)
                    if isinstance(parsed, dict) and "findings" in parsed:
                        items_data = parsed["findings"]
                    elif isinstance(parsed, list):
                        items_data = parsed
                except json.JSONDecodeError:
                    logger.warning("Could not parse result as JSON")

            logger.info(f"Discovered {len(items_data)} items")

            self.event_log.append(
                "items_discovered",
                domain_id=self.config.id,
                payload={"count": len(items_data)},
            )

            return items_data

        except Exception as e:
            logger.error(f"Discovery failed for {self.config.name}: {e}", exc_info=True)
            self.event_log.append(
                "discovery_failed", domain_id=self.config.id, payload={"error": str(e)}
            )
            return []

    async def filter_and_score(self, items_data: list[dict[str, Any]]) -> list[Item]:
        """Convert discovered item dicts to Item domain models.

        Since the discovery agent already scored items during discovery,
        this method just validates and converts to proper Item objects.

        Args:
            items_data: List of dicts from discover() with keys:
                title, source, source_url, summary, significance, significance_score

        Returns:
            List of Item objects with significance_score >= 0.4

        Validation:
            - Converts string scores to float
            - Ensures significance_score is numeric
            - Filters out items below 0.4 threshold
            - Generates UUIDs for new items

        Design Note:
            Originally this method called LLM for filtering, but that was
            redundant since discovery agent already scores. Now it's just a
            dict-to-model conversion layer.
        """
        if not items_data:
            return []

        logger.info(f"Converting {len(items_data)} discovered items to Item objects")

        items: list[Item] = []
        for item_data in items_data:
            # Ensure significance_score is a float
            sig_score = item_data.get("significance_score", 0.5)
            if isinstance(sig_score, str):
                try:
                    sig_score = float(sig_score)
                except ValueError:
                    sig_score = 0.5

            item = Item(
                id=str(uuid4()),
                domain_id=self.config.id,
                title=item_data.get("title", "Unknown"),
                source=item_data.get("source", "Unknown"),
                source_url=item_data.get("source_url"),
                summary=item_data.get("summary", ""),
                significance=item_data.get("significance", ""),
                significance_score=sig_score,
                discovered_at=datetime.utcnow(),
                raw_content=item_data.get("raw_content"),
            )
            items.append(item)

        # Filter by minimum threshold (discovery should already do this, but double-check)
        significant = [i for i in items if i.significance_score >= 0.4]

        logger.info(
            f"Converted to {len(significant)} significant items (>= 0.4 score)"
        )

        return significant

    async def synthesize(self, items: list[Item]) -> DomainUpdate | None:
        """Create synthesized domain update from significant items.

        Synthesis Flow:
            1. Build synthesis prompt with formatted items
            2. Create ToolCallingAgent with current config
            3. Agent analyzes items and creates summary + open questions
            4. Agent returns via final_answer with structured JSON
            5. Parse response and create DomainUpdate object

        Args:
            items: List of Item objects to synthesize (typically 5-20)

        Returns:
            DomainUpdate with:
            - summary: 2-3 paragraph analytical summary
            - open_questions: 3-5 questions the field is investigating
            - item_ids: References to items included
            - token_usage: Estimated token count

            None if no items provided or synthesis fails

        Logs:
            - update_synthesized event with metadata
            - synthesis_failed event on exception

        Example Output:
            DomainUpdate(
                summary="Recent developments in physics show...",
                open_questions=[
                    "How will quantum error correction scale to 1000+ qubits?",
                    "What mechanism explains the observed anomaly in..."
                ],
                item_ids=["uuid1", "uuid2", ...],
                token_usage=1250
            )

        Implementation Note:
            Agent execution runs in thread pool (asyncio.to_thread) to prevent
            blocking the event loop during long-running LLM operations.

        Design Note:
            Uses higher quality model (typically Sonnet) than discovery
            since synthesis requires deeper analytical capabilities.
        """
        if not items:
            logger.info(f"No items to synthesize for domain: {self.config.name}")
            return None

        logger.info(f"Synthesizing update from {len(items)} items for: {self.config.name}")

        # Build synthesis prompt
        synthesis_prompt = self.build_synthesis_prompt(items)

        try:
            # Create agent with current config
            synthesis_agent = self._create_synthesis_agent()

            # Run agent with tools (in thread pool to avoid blocking event loop)
            result = await asyncio.to_thread(synthesis_agent.run, synthesis_prompt)

            logger.info(f"Synthesis result type: {type(result)}")

            # Parse structured output
            summary_text = ""
            open_questions: list[str] = []

            if isinstance(result, dict):
                summary_text = result.get("summary", "")
                open_questions = result.get("open_questions", [])
            elif isinstance(result, str):
                # Try to parse JSON
                try:
                    parsed = json.loads(result)
                    summary_text = parsed.get("summary", result)
                    open_questions = parsed.get("open_questions", [])
                except json.JSONDecodeError:
                    summary_text = result
                    open_questions = []

            # Estimate token usage (rough approximation)
            token_usage = len(synthesis_prompt.split()) + len(summary_text.split())

            update = DomainUpdate(
                id=str(uuid4()),
                domain_id=self.config.id,
                created_at=datetime.utcnow(),
                summary=summary_text,
                item_ids=[item.id for item in items],
                open_questions=open_questions,
                token_usage=token_usage,
            )

            self.event_log.append(
                "update_synthesized",
                domain_id=self.config.id,
                payload={
                    "update_id": update.id,
                    "item_count": len(items),
                    "token_usage": token_usage,
                },
            )

            return update

        except Exception as e:
            logger.error(f"Synthesis failed for {self.config.name}: {e}", exc_info=True)
            self.event_log.append(
                "synthesis_failed", domain_id=self.config.id, payload={"error": str(e)}
            )
            return None

    def _format_items_for_prompt(self, items_data: list[dict[str, Any]]) -> str:
        """Format item dicts for inclusion in prompt.

        Args:
            items_data: List of item dicts

        Returns:
            Formatted string with numbered items and all fields
        """
        formatted = []
        for i, item in enumerate(items_data, 1):
            formatted.append(
                f"{i}. {item.get('title', 'No title')}\n"
                f"   Source: {item.get('source', 'Unknown')}\n"
                f"   URL: {item.get('source_url', 'N/A')}\n"
                f"   Summary: {item.get('summary', 'N/A')}\n"
                f"   Significance: {item.get('significance', 'N/A')}\n"
                f"   Score: {item.get('significance_score', 0.0)}\n"
            )
        return "\n".join(formatted)

    def _format_items_for_synthesis(self, items: list[Item]) -> str:
        """Format Item objects for synthesis prompt.

        Args:
            items: List of Item domain models

        Returns:
            Formatted string with numbered items for synthesis analysis

        Design Note:
            Includes item number for referencing in synthesis
            ("Item 1 demonstrates..." provides clear provenance)
        """
        formatted = []
        for i, item in enumerate(items, 1):
            formatted.append(
                f"{i}. {item.title} (score: {item.significance_score:.1f})\n"
                f"   Source: {item.source}\n"
                f"   Summary: {item.summary}\n"
                f"   Significance: {item.significance}\n"
            )
        return "\n".join(formatted)
