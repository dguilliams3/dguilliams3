"""Core domain models."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SourceConfig(BaseModel):
    """Configuration for a data source."""

    type: str = Field(..., description="Source type: web_search, rss, arxiv, specific_url")
    query: str | None = Field(None, description="Search query for web_search/arxiv")
    url: str | None = Field(None, description="URL for specific_url type")
    max_results: int = Field(10, description="Maximum results to fetch")


class DomainConfig(BaseModel):
    """Configuration for a knowledge domain."""

    id: str = Field(..., description="Unique domain identifier")
    name: str = Field(..., description="Human-readable domain name")
    description: str = Field(..., description="Domain description and scope")
    update_frequency_hours: int = Field(24, description="Update frequency in hours")
    sources: list[SourceConfig] = Field(..., description="Data sources for this domain")
    filter_prompt: str = Field(..., description="Prompt for filtering/scoring items")
    synthesis_prompt: str = Field(..., description="Prompt for synthesizing updates")


class Domain(BaseModel):
    """Persisted domain record."""

    id: str
    name: str
    description: str | None = None
    update_frequency_hours: int = 24
    last_updated_at: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Item(BaseModel):
    """A discovered research item."""

    id: str
    domain_id: str
    title: str
    source: str
    source_url: str | None = None
    published_date: datetime | None = None
    discovered_at: datetime = Field(default_factory=datetime.utcnow)
    summary: str
    significance: str
    significance_score: float = Field(..., ge=0.0, le=1.0)
    raw_content: str | None = None
    embedding_id: str | None = None


class DomainUpdate(BaseModel):
    """Synthesized domain summary."""

    id: str
    domain_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    summary: str
    item_ids: list[str] = Field(..., description="IDs of items included in this update")
    open_questions: list[str] = Field(default_factory=list)
    token_usage: int | None = None


class UserAnnotation(BaseModel):
    """User annotation on an item."""

    id: str
    item_id: str
    note: str | None = None
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Event(BaseModel):
    """Append-only event log entry."""

    id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    event_type: str = Field(
        ...,
        description="Event type: items_discovered, update_synthesized, item_annotated, update_failed",
    )
    domain_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
