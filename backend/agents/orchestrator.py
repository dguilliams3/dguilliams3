"""Agent orchestrator with scheduling, lifecycle management, and domain coordination.

This module implements the Orchestrator - the top-level coordinator that manages
all domain agents, schedules periodic updates, and coordinates the discovery →
storage → synthesis pipeline.

Architecture Role:
    The Orchestrator is the "central nervous system" of the research dashboard:

    ┌─────────────────┐
    │  Orchestrator   │──┐
    └────────┬────────┘  │
             │            │ manages lifecycle
         creates          │
             ├────────────┴────────────┬────────────────┐
             ▼                         ▼                ▼
    ┌─────────────────┐     ┌─────────────────┐  ┌─────────────┐
    │ DomainAgent     │     │ DomainAgent     │  │ DomainAgent │
    │ (Physics)       │     │ (Alignment)     │  │ (...)       │
    └───────┬─────────┘     └───────┬─────────┘  └─────────────┘
            │                       │
        discovers items         discovers items
            │                       │
            ▼                       ▼
    ┌────────────────────────────────────────┐
    │  Orchestrator                          │
    │  • Stores items in database            │
    │  • Generates embeddings (ChromaDB)     │
    │  • Logs events (event sourcing)        │
    │  • Triggers synthesis                  │
    │  • Updates domain timestamps           │
    └────────────────────────────────────────┘

Design Philosophy (ADR-005, ADR-006):
    - Monolithic: All agents run in single process (vs microservices)
    - Dynamic agents: Create agents on-demand to pick up config changes
    - Scheduled updates: APScheduler triggers periodic domain refreshes
    - Coordinated pipeline: Discovery → filter → store → synthesize
    - Centralized persistence: Orchestrator owns database/storage logic

Responsibilities:
    1. **Initialization**: Run migrations, create domains, instantiate agents
    2. **Scheduling**: Set up periodic update jobs for each domain
    3. **Pipeline execution**: Coordinate discovery → storage → synthesis
    4. **Persistence**: Store items in SQLite, embeddings in ChromaDB
    5. **Event logging**: Append all operations to event log (ADR-008)
    6. **Error handling**: Gracefully handle agent failures, continue system

Update Pipeline (per domain):
    ```
    1. Discovery Phase
       └─> agent.discover() → raw_items (web search + fetch)

    2. Filtering Phase
       └─> agent.filter_and_score(raw_items) → significant_items (score >= threshold)

    3. Storage Phase
       ├─> item_repo.create(item) → SQLite (structured data)
       ├─> embeddings.add_item(item) → ChromaDB (vector search)
       └─> event_log.append("item_discovered", ...) → JSONL (audit trail)

    4. Synthesis Phase
       └─> agent.synthesize(stored_items) → update (summary + open questions)

    5. Finalization
       └─> domain_repo.update_last_updated() → timestamp
    ```

Scheduling Strategy:
    - Each domain has update_frequency_hours (e.g., 24h for physics)
    - APScheduler creates interval trigger for each domain
    - max_instances=1 prevents concurrent runs for same domain
    - Jobs run in background (non-blocking)
    - Manual triggers available via trigger_manual_update()

Concurrency Model:
    - Single AsyncIOScheduler manages all jobs
    - Each domain job runs sequentially (no parallel discovery)
    - Database operations are async (aiosqlite)
    - Agent operations are sync (SmolAgents runs blocking LLM calls)
    - asyncio bridges sync agent code with async persistence

Error Handling:
    - Agent failure doesn't crash orchestrator
    - Errors logged and appended to event log
    - Failed domain continues on next scheduled run
    - Other domains unaffected by failures

Initial vs Scheduled Updates:
    - Scheduled: Run every N hours (configured per domain)
    - Initial: Optional update on startup (settings.update_on_startup)
    - Manual: User clicks "Refresh Now" button (force=True bypasses throttle)

Manual Update Throttling:
    - Prevents spam: Won't run if updated < 1 hour ago
    - Override: force=True bypasses throttle
    - Use case: User clicks refresh, don't hammer API

Domain Configurations:
    Loaded from backend/agents/domains/:
    - physics_config: Quantum computing, condensed matter, high-energy physics
    - alignment_config: AI alignment, safety, interpretability
    - frameworks_config: LangChain, LlamaIndex, agent frameworks
    - infrastructure_config: GPU, model serving, ML infrastructure

Persistence Layers:
    1. **SQLite (structured data)**:
       - Domains: ID, name, description, update schedule
       - Items: Discovered research findings with metadata
       - Updates: Synthesis summaries with open questions
       - Annotations: User notes/tags (future feature)

    2. **ChromaDB (vector search)**:
       - Embeddings for all discovered items
       - Enables semantic search ("find similar items")
       - Used by RAG service for Q&A

    3. **JSONL Event Log (audit trail)**:
       - Append-only log of all system events
       - Source of truth for debugging/recovery
       - Can rebuild state from event log (ADR-008)

State Management:
    - Orchestrator is stateful (holds DB connections, agent refs)
    - Created once at app startup
    - Shutdown gracefully on app termination
    - No shared state between domains (isolated)

Usage Example:
    ```python
    # App startup (main.py)
    orchestrator = Orchestrator()
    await orchestrator.initialize()  # Migrations, create domains, agents
    orchestrator.start()  # Start scheduler

    # Scheduled update runs automatically
    # Every 24h for physics domain:
    #   1. orchestrator._run_domain_update("physics")
    #   2. Agent discovers items
    #   3. Orchestrator stores items
    #   4. Agent synthesizes update
    #   5. Orchestrator logs events

    # Manual trigger (user clicks Refresh Now)
    await orchestrator.trigger_manual_update("physics")

    # App shutdown
    orchestrator.stop()  # Stop scheduler
    ```

Performance Considerations:
    - Discovery: 30-60s per domain (web searches + fetches)
    - Storage: ~100ms per item (SQLite + ChromaDB)
    - Synthesis: 5-10s (Sonnet analyzing items)
    - Total: ~1-2 minutes per domain update
    - 4 domains × daily = ~5-10 minutes total compute per day

Future Enhancements:
    - Parallel domain updates (run physics + alignment simultaneously)
    - Incremental discovery (only search for new items since last update)
    - Adaptive scheduling (update more frequently if high activity detected)
    - Health checks (alert if agent fails repeatedly)
    - Metrics dashboard (token usage, latency, success rates)

See Also:
    - ARCHITECTURE_DECISIONS.md: ADR-005 (Dynamic agents), ADR-006 (Monolithic)
    - backend/agents/base.py: DomainAgent implementation
    - backend/main.py: FastAPI app that creates and manages orchestrator
"""

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
    """Orchestrates domain agents with scheduled updates and persistence.

    The Orchestrator is the central coordinator that:
    - Manages lifecycle of all domain agents
    - Schedules periodic updates for each domain
    - Coordinates discovery → storage → synthesis pipeline
    - Owns database connections and persistence logic
    - Logs all events for debugging and audit

    Architecture Pattern:
        Orchestrator (singleton) → manages → DomainAgents (one per domain)
        DomainAgents discover items → Orchestrator persists → DomainAgents synthesize

    Lifecycle:
        1. __init__(): Create database connections, load domain configs
        2. initialize(): Run migrations, ensure domains exist, create agents
        3. start(): Start scheduler, optionally run initial updates
        4. [running]: Scheduled jobs execute _run_domain_update() periodically
        5. stop(): Shutdown scheduler gracefully

    Thread Safety:
        - Runs in single async event loop (no multi-threading)
        - APScheduler uses AsyncIOScheduler (asyncio-safe)
        - Database operations are async (aiosqlite)
        - No concurrent updates for same domain (max_instances=1)

    State:
        - db: Database connection manager
        - domain_repo, item_repo, update_repo: Repository instances
        - event_log: Append-only event logger
        - embeddings: ChromaDB vector store
        - domain_configs: Static config for each domain
        - agents: Live DomainAgent instances (created in initialize())
        - scheduler: APScheduler instance for periodic jobs
    """

    def __init__(self) -> None:
        """Initialize orchestrator with database connections and domain configs.

        Creates:
            - Database connection manager
            - Repository instances for domains, items, updates
            - Event log for audit trail
            - Embedding store for vector search
            - Domain configuration registry
            - Empty agent dictionary (populated in initialize())
            - AsyncIO scheduler (started in start())

        Design Notes:
            - Initialization is synchronous (no I/O yet)
            - Actual setup happens in initialize() (async)
            - Configs are hardcoded in domains/ modules (could be dynamic)
        """
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
        """Initialize orchestrator: run migrations, create agents, setup schedules.

        Startup sequence:
            1. Run database migrations (create tables if needed)
            2. Ensure all domains exist in database
            3. Create DomainAgent instance for each domain
            4. Setup scheduled update jobs

        Design Notes:
            - Idempotent: Safe to call multiple times
            - Migrations use version tracking (won't re-run)
            - Domain creation is upsert-like (won't duplicate)
            - Agent creation is fresh (picks up latest code)

        Performance:
            - Migrations: <100ms (usually no-op after first run)
            - Domain creation: <50ms (4 domains)
            - Agent creation: Instant (no model loading yet)
            - Total: ~150ms startup overhead
        """
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
        """Ensure all configured domains exist in the database.

        For each domain in self.domain_configs:
            - Check if domain exists in database
            - If not, create new Domain record
            - If yes, skip (don't update existing)

        Design Notes:
            - Only creates missing domains (doesn't update)
            - Domain config is source of truth
            - Database just stores runtime state (last_updated_at)

        Future Enhancement:
            Could sync config changes (update name, description, frequency)
            Trade-off: More complex, could overwrite manual DB changes
        """
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
        """Setup scheduled updates for all domains using APScheduler.

        For each domain:
            - Create interval trigger (every N hours)
            - Add job calling _run_domain_update(domain_id)
            - Set max_instances=1 (prevent concurrent runs)
            - Set replace_existing=True (allow re-initialization)

        Scheduler Details:
            - Trigger: IntervalTrigger(hours=config.update_frequency_hours)
            - Job ID: "update_{domain_id}" (unique, stable)
            - Max instances: 1 (no parallel runs for same domain)
            - Executor: default (asyncio event loop)

        Design Notes:
            - Schedules are in-memory (lost on restart)
            - Jobs start after first interval (not immediately)
            - Use start() → _run_initial_updates() for immediate execution

        Example:
            Physics domain (24h frequency):
            - Job runs every 24 hours
            - First run: 24h after start()
            - Unless settings.update_on_startup=True (immediate)
        """
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
        """Run complete update cycle for a domain: discover → store → synthesize.

        Update Pipeline:
            1. Discovery: Agent searches web, fetches content, scores findings
            2. Filtering: Keep only significant items (score >= threshold)
            3. Storage: Save items to SQLite + ChromaDB, dedupe by URL
            4. Synthesis: Agent analyzes stored items, writes summary
            5. Finalization: Update domain's last_updated_at timestamp

        Args:
            domain_id: Domain identifier (e.g., "physics", "alignment")

        Pipeline Flow:
            ```
            _run_domain_update("physics")
            ├─> agent.discover() → 10 raw items
            ├─> agent.filter_and_score(10) → 5 significant items
            ├─> Store each item:
            │   ├─> item_repo.create() → SQLite (returns "" if duplicate)
            │   ├─> embeddings.add_item() → ChromaDB
            │   └─> event_log.append("item_discovered")
            ├─> agent.synthesize(5 items) → DomainUpdate
            ├─> update_repo.create(update) → SQLite
            └─> domain_repo.update_last_updated() → timestamp
            ```

        Error Handling:
            - Agent failures are caught and logged
            - Failed discovery → update timestamp, continue
            - Failed storage → skip item, continue with others
            - Failed synthesis → skip synthesis, items still stored
            - Event logged for all failures (debugging)

        Performance:
            - Discovery: 30-60s (web searches + fetches)
            - Filtering: <1s (LLM scoring)
            - Storage: ~100ms × N items
            - Synthesis: 5-10s (Sonnet)
            - Total: 1-2 minutes per domain

        Design Notes:
            - Runs synchronously (one domain at a time)
            - Updates last_updated even if no items found (important for staleness)
            - Duplicate detection: SQLite UNIQUE constraint on (domain_id, source_url)
            - Empty results are normal (no new items since last update)
        """
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
        """Trigger manual update for a domain (user-initiated refresh).

        Use Cases:
            - User clicks "Refresh Now" button in UI
            - Admin triggers update via API
            - Development testing

        Args:
            domain_id: Domain to update
            force: If True, bypass throttle check (default: False)

        Throttling:
            - Won't run if updated < 1 hour ago (prevents API spam)
            - Override with force=True
            - Scheduled updates ignore throttle

        Raises:
            ValueError: If domain_id doesn't exist

        Design Notes:
            - Same pipeline as scheduled updates (_run_domain_update)
            - Throttle protects against accidental spam
            - Force is useful for testing or admin overrides

        Example:
            ```python
            # User clicks refresh (throttled)
            await orchestrator.trigger_manual_update("physics")

            # Admin forces refresh (bypass throttle)
            await orchestrator.trigger_manual_update("physics", force=True)
            ```
        """
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
        """Start the scheduler and optionally run initial updates.

        Starts:
            1. APScheduler (begin processing scheduled jobs)
            2. Initial updates if settings.update_on_startup=True

        Initial Updates:
            - settings.update_on_startup=True → run all domains now
            - settings.update_on_startup=False → wait for first interval

        Design Notes:
            - Non-blocking (scheduler runs in background)
            - Initial updates run async (don't block startup)
            - Scheduler survives exceptions in jobs

        Typical Flow:
            ```python
            # App startup
            orchestrator = Orchestrator()
            await orchestrator.initialize()
            orchestrator.start()  # Returns immediately, scheduler runs in background
            # App is now serving requests while updates run periodically
            ```
        """
        self.scheduler.start()
        logger.info("Scheduler started")

        # Run initial updates if configured
        if settings.update_on_startup:
            logger.info("Running initial updates...")
            asyncio.create_task(self._run_initial_updates())

    async def _run_initial_updates(self) -> None:
        """Run updates for all domains on startup.

        Called by start() if settings.update_on_startup=True.

        Use Cases:
            - Development: Get data immediately on startup
            - Production: Ensure fresh data after deployment
            - Testing: Populate database for testing

        Error Handling:
            - Failures logged but don't prevent other domains
            - Each domain update is independent

        Performance:
            - Runs serially (one domain at a time)
            - Total: N domains × 1-2 min/domain
            - 4 domains × 2 min = ~8 minutes initial startup

        Design Note:
            Could run in parallel for faster startup.
            Trade-off: Higher API concurrency, more complex error handling.
        """
        for domain_id in self.agents.keys():
            try:
                await self._run_domain_update(domain_id)
            except Exception as e:
                logger.error(f"Initial update failed for {domain_id}: {e}")

    def stop(self) -> None:
        """Stop the scheduler and wait for jobs to complete.

        Shutdown:
            1. Stop accepting new jobs
            2. Wait for running jobs to complete (wait=True)
            3. Cleanup scheduler resources

        Design Notes:
            - Graceful shutdown (waits for jobs)
            - Should be called on app shutdown
            - Timeout: Default APScheduler timeout (30s)

        Usage:
            ```python
            # App shutdown
            orchestrator.stop()  # Blocks until jobs finish
            ```

        Future Enhancement:
            Could add timeout parameter for faster shutdown.
            Trade-off: May interrupt running updates.
        """
        self.scheduler.shutdown(wait=True)
        logger.info("Scheduler stopped")
