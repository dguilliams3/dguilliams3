"""Agent orchestrator with scheduling and lifecycle management."""

import asyncio
import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from backend.agents.base import DomainAgent
from backend.agents.domains.alignment import alignment_config
from backend.agents.domains.frameworks import frameworks_config
from backend.agents.domains.infrastructure import infrastructure_config
from backend.agents.domains.physics import physics_config
from backend.config import settings
from backend.db.chroma import EmbeddingStore
from backend.db.events import EventLog
from backend.db.sqlite import Database, DomainRepository, ItemRepository, UpdateRepository
from backend.models.domain import Domain, DomainConfig

logger = logging.getLogger(__name__)


class Orchestrator:
    """Orchestrates domain agents with scheduled updates."""

    def __init__(self) -> None:
        # Database components
        self.db = Database()
        self.domain_repo = DomainRepository(self.db)
        self.item_repo = ItemRepository(self.db)
        self.update_repo = UpdateRepository(self.db)
        self.event_log = EventLog()
        self.embeddings = EmbeddingStore()

        # Domain configurations
        self.domain_configs: dict[str, DomainConfig] = {
            "physics": physics_config,
            "alignment": alignment_config,
            "frameworks": frameworks_config,
            "infrastructure": infrastructure_config,
        }

        # Domain agents (will be initialized)
        self.agents: dict[str, DomainAgent] = {}

        # Scheduler
        self.scheduler = AsyncIOScheduler()

    async def initialize(self) -> None:
        """Initialize the orchestrator: run migrations, create agents, setup schedules."""
        logger.info("Initializing orchestrator...")

        # Run database migrations
        await self.db.run_migrations()

        # Ensure all domains exist in database
        await self._ensure_domains()

        # Create agents for each domain
        for domain_id, config in self.domain_configs.items():
            agent = DomainAgent(
                config=config,
                item_repo=self.item_repo,
                event_log=self.event_log,
            )
            self.agents[domain_id] = agent
            logger.info(f"Initialized agent for domain: {config.name}")

        # Setup update schedules
        self._setup_schedules()

        logger.info("Orchestrator initialized successfully")

    async def _ensure_domains(self) -> None:
        """Ensure all configured domains exist in the database."""
        for domain_id, config in self.domain_configs.items():
            existing = await self.domain_repo.get(domain_id)
            if not existing:
                domain = Domain(
                    id=config.id,
                    name=config.name,
                    description=config.description,
                    update_frequency_hours=config.update_frequency_hours,
                )
                await self.domain_repo.create(domain)
                logger.info(f"Created domain: {config.name}")

    def _setup_schedules(self) -> None:
        """Setup scheduled updates for all domains."""
        for domain_id, agent in self.agents.items():
            self.scheduler.add_job(
                self._run_domain_update,
                trigger=IntervalTrigger(hours=agent.config.update_frequency_hours),
                args=[domain_id],
                id=f"update_{domain_id}",
                replace_existing=True,
                max_instances=1,  # Prevent concurrent runs
            )
            logger.info(
                f"Scheduled updates for {agent.config.name} "
                f"every {agent.config.update_frequency_hours} hours"
            )

    async def _run_domain_update(self, domain_id: str) -> None:
        """Run a complete update cycle for a domain."""
        agent = self.agents.get(domain_id)
        if not agent:
            logger.error(f"No agent found for domain: {domain_id}")
            return

        logger.info(f"Starting update for domain: {agent.config.name}")
        start_time = datetime.utcnow()

        try:
            # 1. Discovery phase
            logger.info(f"Discovery phase for {agent.config.name}...")
            raw_items = await agent.discover()

            if not raw_items:
                logger.info(f"No items discovered for {agent.config.name}")
                await self.domain_repo.update_last_updated(domain_id, start_time)
                return

            # 2. Filter and score
            logger.info(f"Filtering {len(raw_items)} items for {agent.config.name}...")
            significant_items = await agent.filter_and_score(raw_items)

            if not significant_items:
                logger.info(f"No significant items for {agent.config.name}")
                await self.domain_repo.update_last_updated(domain_id, start_time)
                return

            # 3. Store items
            logger.info(f"Storing {len(significant_items)} items...")
            stored_items = []
            for item in significant_items:
                item_id = await self.item_repo.create(item)
                if item_id:  # Not a duplicate
                    # Add to vector store
                    await self.embeddings.add_item(item)
                    stored_items.append(item)
                    logger.debug(f"Stored item: {item.title}")

            if not stored_items:
                logger.info(f"All items were duplicates for {agent.config.name}")
                await self.domain_repo.update_last_updated(domain_id, start_time)
                return

            # 4. Synthesize update
            logger.info(f"Synthesizing update from {len(stored_items)} items...")
            update = await agent.synthesize(stored_items)

            if update:
                await self.update_repo.create(update)
                logger.info(
                    f"Created update for {agent.config.name} "
                    f"(tokens: {update.token_usage})"
                )

            # Update last_updated timestamp
            await self.domain_repo.update_last_updated(domain_id, datetime.utcnow())

            logger.info(f"✓ Update complete for {agent.config.name}")

        except Exception as e:
            logger.error(f"Update failed for {agent.config.name}: {e}", exc_info=True)
            self.event_log.append("update_failed", domain_id=domain_id, payload={"error": str(e)})

    async def trigger_manual_update(self, domain_id: str, force: bool = False) -> None:
        """Trigger a manual update for a domain."""
        # Check if domain exists
        domain = await self.domain_repo.get(domain_id)
        if not domain:
            raise ValueError(f"Domain not found: {domain_id}")

        # Check if recently updated (unless forced)
        if not force and domain.last_updated_at:
            hours_since_update = (datetime.utcnow() - domain.last_updated_at).total_seconds() / 3600
            if hours_since_update < 1:  # Don't update more than once per hour
                logger.info(
                    f"Domain {domain_id} was updated {hours_since_update:.1f}h ago, skipping"
                )
                return

        # Run update
        await self._run_domain_update(domain_id)

    def start(self) -> None:
        """Start the scheduler."""
        self.scheduler.start()
        logger.info("Scheduler started")

        # Run initial updates if configured
        if settings.update_on_startup:
            logger.info("Running initial updates...")
            asyncio.create_task(self._run_initial_updates())

    async def _run_initial_updates(self) -> None:
        """Run updates for all domains on startup."""
        for domain_id in self.agents.keys():
            try:
                await self._run_domain_update(domain_id)
            except Exception as e:
                logger.error(f"Initial update failed for {domain_id}: {e}")

    def stop(self) -> None:
        """Stop the scheduler."""
        self.scheduler.shutdown(wait=True)
        logger.info("Scheduler stopped")
