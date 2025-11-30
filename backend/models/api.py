"""API request and response models."""

from datetime import datetime

from pydantic import BaseModel, Field

from backend.models.domain import Domain, DomainUpdate, Item


class DomainSummary(BaseModel):
    """Domain summary for list view."""

    id: str
    name: str
    description: str | None
    last_updated_at: datetime | None
    item_count: int = 0
    staleness_hours: float | None = None  # Hours since last update


class DomainDetail(BaseModel):
    """Detailed domain view with recent items and updates."""

    domain: Domain
    recent_items: list[Item] = Field(default_factory=list)
    latest_update: DomainUpdate | None = None


class AskRequest(BaseModel):
    """Request for drill-down Q&A."""

    domain_id: str | None = Field(None, description="Optional domain filter")
    item_id: str | None = Field(None, description="Optional specific item context")
    question: str = Field(..., description="User question")


class AskResponse(BaseModel):
    """Response for drill-down Q&A with citations."""

    answer: str
    citations: list[Item] = Field(default_factory=list)
    token_usage: int | None = None


class RefreshRequest(BaseModel):
    """Manual refresh request."""

    force: bool = Field(False, description="Force refresh even if recently updated")


class RefreshResponse(BaseModel):
    """Refresh response."""

    status: str
    message: str


class DashboardStats(BaseModel):
    """Dashboard statistics."""

    total_domains: int
    total_items: int
    total_updates: int
    total_token_usage: int
    items_by_domain: dict[str, int]
    avg_significance_by_domain: dict[str, float]
