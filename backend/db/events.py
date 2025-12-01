"""Append-only event log for system auditing and debugging."""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from backend.config import settings
from backend.models.domain import Event


class EventLog:
    """Append-only event log using JSONL format."""

    def __init__(self, log_path: Path | None = None) -> None:
        self.log_path = log_path or settings.events_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def append(
        self, event_type: str, domain_id: str | None = None, payload: dict[str, Any] | None = None
    ) -> Event:
        """Append a new event to the log synchronously.

        Note: This is intentionally synchronous for compatibility with synchronous
        contexts (like within SmolAgents tools). The file write is fast (<1ms)
        and buffered by the OS, so blocking is minimal.
        """
        event = Event(
            id=str(uuid4()),
            timestamp=datetime.utcnow(),
            event_type=event_type,
            domain_id=domain_id,
            payload=payload or {},
        )

        # Append to JSONL file
        with open(self.log_path, "a") as f:
            f.write(event.model_dump_json() + "\n")

        return event

    async def read_all(self, limit: int | None = None) -> list[Event]:
        """Read all events from the log.

        Note:
            Runs file I/O in thread pool to avoid blocking event loop.
        """
        if not self.log_path.exists():
            return []

        def _read_events() -> list[Event]:
            events: list[Event] = []
            with open(self.log_path, "r") as f:
                for line in f:
                    if line.strip():
                        event_data = json.loads(line)
                        events.append(Event(**event_data))
            return events

        events = await asyncio.to_thread(_read_events)

        # Return most recent first
        events.reverse()

        if limit:
            return events[:limit]
        return events

    async def read_by_domain(self, domain_id: str, limit: int | None = None) -> list[Event]:
        """Read events for a specific domain."""
        all_events = await self.read_all()
        domain_events = [e for e in all_events if e.domain_id == domain_id]

        if limit:
            return domain_events[:limit]
        return domain_events

    async def read_by_type(self, event_type: str, limit: int | None = None) -> list[Event]:
        """Read events of a specific type."""
        all_events = await self.read_all()
        typed_events = [e for e in all_events if e.event_type == event_type]

        if limit:
            return typed_events[:limit]
        return typed_events
