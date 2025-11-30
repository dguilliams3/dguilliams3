"""FastAPI application for Research Dashboard."""

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import AsyncIterator

from anthropic import Anthropic
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from backend.agents.orchestrator import Orchestrator
from backend.config import settings
from backend.models.api import (
    AskRequest,
    AskResponse,
    DashboardStats,
    DomainDetail,
    DomainSummary,
    RefreshRequest,
    RefreshResponse,
)
from backend.models.domain import Domain, DomainUpdate, Item
from backend.services.rag import RAGService

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Global orchestrator instance
orchestrator: Orchestrator | None = None
rag_service: RAGService | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan manager."""
    global orchestrator, rag_service

    # Startup
    logger.info("Starting Research Dashboard API...")
    settings.ensure_data_dirs()

    # Initialize orchestrator
    orchestrator = Orchestrator()
    await orchestrator.initialize()

    # Initialize RAG service
    anthropic_client = Anthropic(api_key=settings.anthropic_api_key)
    rag_service = RAGService(
        anthropic_client=anthropic_client,
        embeddings=orchestrator.embeddings,
        item_repo=orchestrator.item_repo,
    )

    # Start scheduler
    orchestrator.start()
    logger.info("✓ Research Dashboard API started")

    yield

    # Shutdown
    logger.info("Shutting down Research Dashboard API...")
    if orchestrator:
        orchestrator.stop()
    logger.info("✓ Research Dashboard API stopped")


# Create FastAPI app
app = FastAPI(
    title="Research Dashboard API",
    description="Local-first research intelligence dashboard with LLM-powered agents",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Domain Endpoints ---


@app.get("/api/domains", response_model=list[DomainSummary])
async def list_domains() -> list[DomainSummary]:
    """List all domains with staleness info."""
    if not orchestrator:
        raise HTTPException(status_code=500, detail="Orchestrator not initialized")

    domains = await orchestrator.domain_repo.list_all()
    summaries: list[DomainSummary] = []

    for domain in domains:
        # Get item count
        item_count = await orchestrator.item_repo.count_by_domain(domain.id)

        # Calculate staleness
        staleness_hours = None
        if domain.last_updated_at:
            delta = datetime.utcnow() - domain.last_updated_at
            staleness_hours = delta.total_seconds() / 3600

        summaries.append(
            DomainSummary(
                id=domain.id,
                name=domain.name,
                description=domain.description,
                last_updated_at=domain.last_updated_at,
                item_count=item_count,
                staleness_hours=staleness_hours,
            )
        )

    return summaries


@app.get("/api/domains/{domain_id}", response_model=DomainDetail)
async def get_domain(domain_id: str) -> DomainDetail:
    """Get domain with recent items and latest update."""
    if not orchestrator:
        raise HTTPException(status_code=500, detail="Orchestrator not initialized")

    domain = await orchestrator.domain_repo.get(domain_id)
    if not domain:
        raise HTTPException(status_code=404, detail="Domain not found")

    # Get recent items (top 20 by significance)
    recent_items = await orchestrator.item_repo.list_by_domain(
        domain_id=domain_id, limit=20, min_significance=0.4
    )

    # Get latest update
    latest_update = await orchestrator.update_repo.get_latest(domain_id)

    return DomainDetail(domain=domain, recent_items=recent_items, latest_update=latest_update)


@app.get("/api/domains/{domain_id}/items", response_model=list[Item])
async def list_items(
    domain_id: str,
    limit: int = Query(50, ge=1, le=200),
    min_significance: float = Query(0.0, ge=0.0, le=1.0),
    since_hours: int | None = Query(None, ge=1),
) -> list[Item]:
    """List items for a domain with filters."""
    if not orchestrator:
        raise HTTPException(status_code=500, detail="Orchestrator not initialized")

    since = None
    if since_hours:
        since = datetime.utcnow() - timedelta(hours=since_hours)

    items = await orchestrator.item_repo.list_by_domain(
        domain_id=domain_id, limit=limit, min_significance=min_significance, since=since
    )

    return items


@app.get("/api/domains/{domain_id}/updates", response_model=list[DomainUpdate])
async def list_updates(domain_id: str, limit: int = Query(10, ge=1, le=50)) -> list[DomainUpdate]:
    """Get update history for a domain."""
    if not orchestrator:
        raise HTTPException(status_code=500, detail="Orchestrator not initialized")

    updates = await orchestrator.update_repo.list_by_domain(domain_id=domain_id, limit=limit)
    return updates


@app.post("/api/domains/{domain_id}/refresh", response_model=RefreshResponse)
async def refresh_domain(
    domain_id: str, request: RefreshRequest, background_tasks: BackgroundTasks
) -> RefreshResponse:
    """Trigger manual refresh of a domain."""
    if not orchestrator:
        raise HTTPException(status_code=500, detail="Orchestrator not initialized")

    # Verify domain exists
    domain = await orchestrator.domain_repo.get(domain_id)
    if not domain:
        raise HTTPException(status_code=404, detail="Domain not found")

    # Trigger update in background
    background_tasks.add_task(orchestrator.trigger_manual_update, domain_id, request.force)

    return RefreshResponse(
        status="refresh_started", message=f"Refresh started for domain: {domain.name}"
    )


# --- Search and Q&A Endpoints ---


@app.get("/api/search", response_model=list[Item])
async def semantic_search(
    q: str = Query(..., min_length=3),
    domain_id: str | None = None,
    limit: int = Query(10, ge=1, le=50),
) -> list[Item]:
    """Semantic search across items."""
    if not orchestrator:
        raise HTTPException(status_code=500, detail="Orchestrator not initialized")

    # Search embeddings
    search_results = await orchestrator.embeddings.search(
        query=q, domain_id=domain_id, limit=limit
    )

    # Get full items from database
    item_ids = [item_dict["id"] for item_dict, _ in search_results]
    items = await orchestrator.item_repo.get_by_ids(item_ids)

    return items


@app.post("/api/ask", response_model=AskResponse)
async def ask_question(request: AskRequest) -> AskResponse:
    """Ask a question using RAG over the knowledge base."""
    if not rag_service:
        raise HTTPException(status_code=500, detail="RAG service not initialized")

    response = await rag_service.ask(request)
    return response


# --- Stats and Monitoring ---


@app.get("/api/stats", response_model=DashboardStats)
async def get_stats() -> DashboardStats:
    """Get dashboard statistics."""
    if not orchestrator:
        raise HTTPException(status_code=500, detail="Orchestrator not initialized")

    # Get all domains
    domains = await orchestrator.domain_repo.list_all()

    # Count items by domain
    items_by_domain: dict[str, int] = {}
    avg_significance_by_domain: dict[str, float] = {}

    total_items = 0
    for domain in domains:
        count = await orchestrator.item_repo.count_by_domain(domain.id)
        items_by_domain[domain.id] = count
        total_items += count

        # Get items to calculate average significance
        items = await orchestrator.item_repo.list_by_domain(domain.id, limit=1000)
        if items:
            avg_sig = sum(item.significance_score for item in items) / len(items)
            avg_significance_by_domain[domain.id] = round(avg_sig, 2)
        else:
            avg_significance_by_domain[domain.id] = 0.0

    # Count updates
    total_updates = 0
    for domain in domains:
        updates = await orchestrator.update_repo.list_by_domain(domain.id, limit=1000)
        total_updates += len(updates)

    # Get total token usage
    total_token_usage = await orchestrator.update_repo.get_total_token_usage()

    return DashboardStats(
        total_domains=len(domains),
        total_items=total_items,
        total_updates=total_updates,
        total_token_usage=total_token_usage,
        items_by_domain=items_by_domain,
        avg_significance_by_domain=avg_significance_by_domain,
    )


@app.get("/api/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy", "version": "0.1.0"}


# --- SSE for live updates ---


@app.get("/api/events")
async def stream_events() -> EventSourceResponse:
    """Server-sent events stream for live updates."""

    async def event_generator() -> AsyncIterator[dict[str, str]]:
        """Generate events from the event log."""
        # This is a simple implementation
        # In production, you'd want a proper pub/sub system
        last_event_count = 0

        while True:
            if orchestrator:
                events = orchestrator.event_log.read_all(limit=100)
                if len(events) > last_event_count:
                    # New events available
                    for event in events[: len(events) - last_event_count]:
                        yield {
                            "event": event.event_type,
                            "data": event.model_dump_json(),
                        }
                    last_event_count = len(events)

            # Wait before checking again
            import asyncio

            await asyncio.sleep(5)

    return EventSourceResponse(event_generator())


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.api_host, port=settings.api_port)
