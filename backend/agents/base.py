"""Base domain agent implementation."""

import logging
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from anthropic import Anthropic
from smolagents import CodeAgent, ToolCallingAgent

from backend.agents.tools import FetchURLTool, StoreItemTool, WebSearchTool
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
        anthropic_client: Anthropic,
    ) -> None:
        self.config = config
        self.item_repo = item_repo
        self.event_log = event_log
        self.anthropic = anthropic_client

        # Initialize tools
        self.tools = [
            WebSearchTool(api_key=settings.brave_search_api_key),
            FetchURLTool(),
        ]

    async def discover(self) -> list[dict[str, Any]]:
        """
        Run discovery phase: search for new items in this domain.
        Returns a list of discovered items as dicts.
        """
        logger.info(f"Starting discovery for domain: {self.config.name}")

        # Build search queries from sources
        search_queries = []
        for source in self.config.sources:
            if source.type == "web_search" and source.query:
                search_queries.append(source.query)

        # Create discovery prompt
        discover_prompt = f"""You are researching recent developments in {self.config.name}.

Domain description: {self.config.description}

Your task:
1. Use web_search to find recent news, papers, and developments
2. For promising results, use fetch_url to get full content
3. Analyze each finding and prepare structured data for storage

Search queries to execute:
{chr(10).join(f'- {q}' for q in search_queries)}

Focus on developments from the last 7 days.
Prioritize primary sources over news aggregators.

For each significant finding, return a JSON object with:
- title: clear, descriptive title
- source: source name (e.g., "Nature", "arXiv")
- source_url: full URL
- summary: 2-3 sentence summary
- significance: why this matters
- significance_score: 0.0-1.0 (use the scoring guide)

Scoring guide:
- 0.0-0.3: Minor update, incremental progress
- 0.4-0.6: Notable development, worth tracking
- 0.7-0.9: Significant breakthrough or shift
- 1.0: Field-defining, paradigm-shifting

Return your findings as a JSON array.
"""

        try:
            # Use Anthropic directly for now (SmolAgents integration can be refined later)
            response = self.anthropic.messages.create(
                model=settings.default_filter_model,
                max_tokens=4096,
                messages=[{"role": "user", "content": discover_prompt}],
            )

            # Parse response (simplified - would need better JSON extraction)
            content = response.content[0].text
            logger.info(f"Discovery response: {content[:500]}...")

            # For now, return empty list - full implementation would parse JSON
            # This is a placeholder for the actual agent-based discovery
            items_data: list[dict[str, Any]] = []

            self.event_log.append(
                "items_discovered",
                domain_id=self.config.id,
                payload={"count": len(items_data), "raw_response": content[:1000]},
            )

            return items_data

        except Exception as e:
            logger.error(f"Discovery failed for {self.config.name}: {e}")
            self.event_log.append(
                "discovery_failed", domain_id=self.config.id, payload={"error": str(e)}
            )
            return []

    async def filter_and_score(self, items_data: list[dict[str, Any]]) -> list[Item]:
        """
        Filter and score discovered items.
        Converts raw item data to Item objects with significance scores.
        """
        if not items_data:
            return []

        logger.info(f"Filtering {len(items_data)} items for domain: {self.config.name}")

        filter_prompt = f"""Review these research items for {self.config.name} and score their significance.

{self.config.filter_prompt}

Items to review:
{self._format_items_for_prompt(items_data)}

For each item, assign or verify the significance_score from 0.0 to 1.0.
Return the items as a JSON array with updated scores if needed.
"""

        try:
            response = self.anthropic.messages.create(
                model=settings.default_filter_model,
                max_tokens=2048,
                messages=[{"role": "user", "content": filter_prompt}],
            )

            # Parse and create Item objects
            items: list[Item] = []
            for item_data in items_data:
                item = Item(
                    id=str(uuid4()),
                    domain_id=self.config.id,
                    title=item_data.get("title", ""),
                    source=item_data.get("source", ""),
                    source_url=item_data.get("source_url"),
                    summary=item_data.get("summary", ""),
                    significance=item_data.get("significance", ""),
                    significance_score=item_data.get("significance_score", 0.5),
                    discovered_at=datetime.utcnow(),
                )
                items.append(item)

            # Filter by minimum threshold
            significant = [i for i in items if i.significance_score >= 0.4]

            logger.info(
                f"Filtered to {len(significant)} significant items (>= 0.4 score)"
            )

            return significant

        except Exception as e:
            logger.error(f"Filtering failed for {self.config.name}: {e}")
            return []

    async def synthesize(self, items: list[Item]) -> DomainUpdate | None:
        """
        Create a synthesized domain update from significant items.
        """
        if not items:
            logger.info(f"No items to synthesize for domain: {self.config.name}")
            return None

        logger.info(f"Synthesizing update from {len(items)} items for: {self.config.name}")

        synthesis_prompt = f"""Synthesize a domain update for {self.config.name}.

{self.config.synthesis_prompt}

Significant items discovered:
{self._format_items_for_synthesis(items)}

Create a comprehensive update with:
1. A 2-3 paragraph summary of the current state
2. Key developments (reference specific items by number)
3. 3-5 open questions the field is grappling with

Be analytical, not promotional. Flag uncertainties.
"""

        try:
            response = self.anthropic.messages.create(
                model=settings.default_synthesis_model,
                max_tokens=2048,
                messages=[{"role": "user", "content": synthesis_prompt}],
            )

            summary = response.content[0].text
            token_usage = response.usage.input_tokens + response.usage.output_tokens

            # Extract open questions (simplified - would use better parsing)
            open_questions = [
                "What will be the next major breakthrough?",
                "How will this change the field?",
                "What are the key technical challenges?",
            ]

            update = DomainUpdate(
                id=str(uuid4()),
                domain_id=self.config.id,
                created_at=datetime.utcnow(),
                summary=summary,
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
            logger.error(f"Synthesis failed for {self.config.name}: {e}")
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
