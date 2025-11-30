"""Base domain agent implementation."""

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
    """Agent for discovering and synthesizing research in a knowledge domain."""

    def __init__(
        self,
        config: DomainConfig,
        item_repo: ItemRepository,
        event_log: EventLog,
    ) -> None:
        self.config = config
        self.item_repo = item_repo
        self.event_log = event_log

        # Initialize tools
        self.tools = [
            WebSearchTool(api_key=settings.brave_search_api_key),
            FetchURLTool(),
        ]

    def _get_agent_config(self):
        """Get current agent configuration."""
        return agent_config_store.get(self.config.id)

    def _create_discovery_agent(self) -> ToolCallingAgent:
        """Create discovery agent with current config."""
        config = self._get_agent_config()
        model = AnthropicModel(
            model_id=config.discovery_model,
            api_key=settings.anthropic_api_key,
        )
        return ToolCallingAgent(
            tools=self.tools,
            model=model,
            max_steps=config.discovery_max_steps,
            verbosity_level=1,
        )

    def _create_synthesis_agent(self) -> ToolCallingAgent:
        """Create synthesis agent with current config."""
        config = self._get_agent_config()
        model = AnthropicModel(
            model_id=config.synthesis_model,
            api_key=settings.anthropic_api_key,
        )
        return ToolCallingAgent(
            tools=[],
            model=model,
            max_steps=config.synthesis_max_steps,
        )

    def build_discovery_prompt(self) -> str:
        """Build discovery prompt without executing it."""
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
        """Build synthesis prompt without executing it."""
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
        """
        Run discovery phase: search for new items in this domain.
        Returns a list of discovered items as dicts.
        """
        logger.info(f"Starting discovery for domain: {self.config.name}")

        # Build discovery prompt
        discover_prompt = self.build_discovery_prompt()

        try:
            # Create agent with current config
            discovery_agent = self._create_discovery_agent()

            # Run agent with tools
            result = discovery_agent.run(discover_prompt)

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
        """
        Convert discovered item dicts to Item objects.
        The discovery agent already scored items, so we just convert to domain models.
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
        """
        Create a synthesized domain update from significant items.
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

            result = synthesis_agent.run(synthesis_prompt)

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
        """Format items for inclusion in prompt."""
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
        """Format Item objects for synthesis prompt."""
        formatted = []
        for i, item in enumerate(items, 1):
            formatted.append(
                f"{i}. {item.title} (score: {item.significance_score:.1f})\n"
                f"   Source: {item.source}\n"
                f"   Summary: {item.summary}\n"
                f"   Significance: {item.significance}\n"
            )
        return "\n".join(formatted)
