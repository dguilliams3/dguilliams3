"""SQLite database connection manager and repository implementations.

This module provides the data access layer for the research dashboard using SQLite
for structured data storage. Implements the repository pattern with async/await
for non-blocking database operations.

Design Philosophy (ADR-007):
    - Local-first: SQLite file in ./data/ directory (no server required)
    - Privacy: All data stays on user's machine
    - Portability: Copy data/ folder to backup/migrate
    - Zero setup: No database server configuration
    - Async I/O: aiosqlite for non-blocking operations

Architecture:
    ┌──────────────────────┐
    │     Database         │  Connection manager
    └──────────┬───────────┘
               │ provides connections to
               ├────────────┬────────────┬────────────┬────────────┐
               ▼            ▼            ▼            ▼            ▼
        DomainRepo   ItemRepo   UpdateRepo   AnnotationRepo   (more...)

Repository Pattern:
    - Each table gets a Repository class
    - Repository encapsulates all SQL queries
    - Type-safe: Returns Pydantic models, not raw rows
    - Async: All database operations are async
    - Transaction management: Context managers for connections

Data Model:
    ```
    domains                    items                     updates
    ├─ id (PK)                ├─ id (PK)                ├─ id (PK)
    ├─ name                   ├─ domain_id (FK)         ├─ domain_id (FK)
    ├─ description            ├─ title                  ├─ created_at
    ├─ update_frequency_hours ├─ source                 ├─ summary
    ├─ last_updated_at        ├─ source_url             ├─ item_ids (JSON)
    └─ created_at             ├─ summary                ├─ open_questions (JSON)
                              ├─ significance           └─ token_usage
                              ├─ significance_score
                              ├─ discovered_at
                              └─ UNIQUE(domain_id, source_url)  # Deduplication

    user_annotations
    ├─ id (PK)
    ├─ item_id (FK)
    ├─ note
    ├─ tags (JSON)
    ├─ created_at
    └─ updated_at
    ```

Migration System:
    - SQL files in backend/db/migrations/
    - Numbered: 001_init.sql, 002_add_annotations.sql, etc.
    - Version tracking: schema_migrations table
    - Auto-apply on startup: run_migrations() in orchestrator
    - Idempotent: Safe to run multiple times

Deduplication Strategy:
    - Items: UNIQUE constraint on (domain_id, source_url)
    - Prevents duplicate discoveries from same URL
    - ItemRepository.create() returns "" if duplicate
    - Orchestrator skips duplicate items (doesn't add to embeddings)

Connection Pooling:
    - aiosqlite doesn't have built-in pooling
    - Use context managers for each operation
    - Short-lived connections (open → query → close)
    - Acceptable for local file (no network latency)

Error Handling:
    - sqlite3.IntegrityError: Duplicate key violations (expected)
    - sqlite3.OperationalError: Table doesn't exist (migrations needed)
    - Other errors: Raise to caller for handling

Performance:
    - Local file: <1ms for single row operations
    - Batch inserts: ~100ms for 10 items
    - Indexes: domain_id, discovered_at for fast queries
    - Row factory: aiosqlite.Row for column name access

Type Conversion:
    - Dates: Store as ISO 8601 strings (e.g., "2024-12-01T10:30:00")
    - JSON: Store as JSON strings (item_ids, open_questions, tags)
    - Booleans: SQLite integers (0/1)
    - UUIDs: Store as strings

Usage Example:
    ```python
    # Initialize
    db = Database()
    await db.run_migrations()

    # Create repository
    domain_repo = DomainRepository(db)

    # Create domain
    domain = Domain(
        id="physics",
        name="Physics",
        description="Latest in quantum and condensed matter",
        update_frequency_hours=24
    )
    await domain_repo.create(domain)

    # Query domain
    domain = await domain_repo.get("physics")
    print(domain.name)  # "Physics"

    # List all
    all_domains = await domain_repo.list_all()
    ```

Repository Responsibilities:
    - **DomainRepository**: CRUD for research domains
    - **ItemRepository**: CRUD for discovered items, deduplication
    - **UpdateRepository**: CRUD for synthesis updates, token tracking
    - **AnnotationRepository**: User notes/tags (future feature)

Future Enhancements:
    - Connection pooling for concurrent requests
    - Read replicas for analytics queries
    - Backup automation to S3/cloud storage
    - Migration rollback support
    - Query builder for complex filters

See Also:
    - ARCHITECTURE_DECISIONS.md: ADR-007 (Local-first data architecture)
    - backend/db/migrations/: SQL migration files
    - backend/models/domain.py: Pydantic models for type safety
"""

import json
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator
from uuid import uuid4

import aiosqlite

from backend.config import settings
from backend.models.domain import Domain, DomainUpdate, Item, UserAnnotation


class Database:
    """SQLite database connection manager with migration support.

    Provides:
        - Async connection context manager
        - Migration runner with version tracking
        - Row factory for named column access

    Usage:
        ```python
        db = Database()
        await db.run_migrations()

        async with db.connection() as conn:
            async with conn.execute("SELECT * FROM domains") as cursor:
                rows = await cursor.fetchall()
        ```

    Design Notes:
        - Connections are short-lived (created per operation)
        - No connection pooling (acceptable for local file)
        - Row factory set to aiosqlite.Row for dict-like access
    """

    def __init__(self, db_path: Path | None = None) -> None:
        """Initialize database with path.

        Args:
            db_path: Path to SQLite file. If None, uses settings.db_path
                    (defaults to ./data/research.db)

        Side Effects:
            Creates parent directory if it doesn't exist.
        """
        self.db_path = db_path or settings.db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[aiosqlite.Connection]:
        """Get async database connection with row factory.

        Yields:
            aiosqlite.Connection with row_factory set to aiosqlite.Row

        Usage:
            ```python
            async with db.connection() as conn:
                await conn.execute("INSERT INTO domains ...")
                await conn.commit()
            ```

        Design Notes:
            - Connection auto-closes on context exit
            - Row factory allows row["column_name"] access
            - Not a persistent connection pool
        """
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            yield conn

    async def run_migrations(self) -> None:
        """Run all pending database migrations.

        Migration Process:
            1. Check if schema_migrations table exists
            2. Read applied migrations from table
            3. Find .sql files in migrations/ directory
            4. Apply unapplied migrations in numeric order
            5. Record applied versions in schema_migrations

        Migration File Naming:
            - 001_initial_schema.sql
            - 002_add_annotations.sql
            - Version = first numeric part (001, 002, etc.)

        Idempotence:
            - Safe to call multiple times
            - Only applies new migrations
            - Version tracking prevents re-application

        Side Effects:
            - Creates/modifies database tables
            - Inserts version records into schema_migrations
            - Prints migration progress to stdout

        Error Handling:
            - sqlite3.OperationalError if migrations table doesn't exist
            - Creates empty applied set and proceeds
            - SQL syntax errors will raise during executescript()
        """
        migrations_dir = Path(__file__).parent / "migrations"
        migration_files = sorted(migrations_dir.glob("*.sql"))

        async with self.connection() as conn:
            # Get applied migrations
            try:
                async with conn.execute("SELECT version FROM schema_migrations") as cursor:
                    applied = {row[0] for row in await cursor.fetchall()}
            except sqlite3.OperationalError:
                # Migrations table doesn't exist yet
                applied = set()

            # Apply pending migrations
            for migration_file in migration_files:
                version = int(migration_file.stem.split("_")[0])
                if version not in applied:
                    print(f"Applying migration {version}: {migration_file.name}")
                    sql = migration_file.read_text()
                    await conn.executescript(sql)
                    await conn.commit()


class DomainRepository:
    """Repository for domain CRUD operations.

    Domains represent research areas being tracked (physics, AI alignment, etc.).

    Operations:
        - create: Insert new domain
        - get: Fetch domain by ID
        - list_all: Get all domains ordered by creation date
        - update_last_updated: Set last_updated_at timestamp

    Design Notes:
        - IDs are user-defined (not auto-generated)
        - No update() method (domains are mostly static config)
        - last_updated_at is runtime state (managed by orchestrator)
    """

    def __init__(self, db: Database) -> None:
        """Initialize repository with database connection manager.

        Args:
            db: Database instance for connection management
        """
        self.db = db

    async def create(self, domain: Domain) -> str:
        """Create a new domain.

        Args:
            domain: Domain model with all fields populated

        Returns:
            domain.id on success

        Raises:
            sqlite3.IntegrityError: If domain.id already exists

        Design Note:
            Caller should handle IntegrityError for idempotent creation.
        """
        async with self.db.connection() as conn:
            await conn.execute(
                """
                INSERT INTO domains (id, name, description, update_frequency_hours, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    domain.id,
                    domain.name,
                    domain.description,
                    domain.update_frequency_hours,
                    domain.created_at.isoformat(),
                ),
            )
            await conn.commit()
            return domain.id

    async def get(self, domain_id: str) -> Domain | None:
        """Get a domain by ID.

        Args:
            domain_id: Domain identifier (e.g., "physics")

        Returns:
            Domain model if found, None otherwise

        Performance:
            - Single row lookup by primary key
            - <1ms typical latency
        """
        async with self.db.connection() as conn:
            async with conn.execute(
                "SELECT * FROM domains WHERE id = ?", (domain_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return self._row_to_domain(row)
                return None

    async def list_all(self) -> list[Domain]:
        """List all domains ordered by creation date (newest first).

        Returns:
            List of Domain models

        Use Cases:
            - Dashboard domain selector
            - API /domains endpoint
            - Orchestrator initialization

        Performance:
            - Full table scan (acceptable for small # of domains)
            - ~5-10ms for 4 domains
        """
        async with self.db.connection() as conn:
            async with conn.execute(
                "SELECT * FROM domains ORDER BY created_at DESC"
            ) as cursor:
                rows = await cursor.fetchall()
                return [self._row_to_domain(row) for row in rows]

    async def update_last_updated(self, domain_id: str, timestamp: datetime) -> None:
        """Update the last_updated_at timestamp for a domain.

        Called by orchestrator after each update cycle.

        Args:
            domain_id: Domain to update
            timestamp: New last_updated_at value (usually datetime.utcnow())

        Design Note:
            This is the only mutable field for domains.
            Used for staleness calculation in UI.
        """
        async with self.db.connection() as conn:
            await conn.execute(
                "UPDATE domains SET last_updated_at = ? WHERE id = ?",
                (timestamp.isoformat(), domain_id),
            )
            await conn.commit()

    def _row_to_domain(self, row: aiosqlite.Row) -> Domain:
        """Convert database row to Domain model.

        Args:
            row: aiosqlite.Row from SELECT query

        Returns:
            Domain pydantic model with type-safe fields

        Type Conversions:
            - ISO timestamp strings → datetime objects
            - NULL last_updated_at → None (not yet updated)
        """
        return Domain(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            update_frequency_hours=row["update_frequency_hours"],
            last_updated_at=datetime.fromisoformat(row["last_updated_at"])
            if row["last_updated_at"]
            else None,
            created_at=datetime.fromisoformat(row["created_at"]),
        )


class ItemRepository:
    """Repository for discovered item CRUD operations.

    Items are research findings discovered by agents (papers, news, blog posts).

    Deduplication:
        - UNIQUE constraint on (domain_id, source_url)
        - create() returns "" if URL already exists in domain
        - Orchestrator skips duplicates (doesn't add to embeddings)

    Operations:
        - create: Insert item (returns "" if duplicate)
        - get: Fetch item by ID
        - list_by_domain: Query items with filters
        - count_by_domain: Count items for a domain
        - get_by_ids: Batch fetch by IDs (for RAG)

    Design Notes:
        - No update/delete (items are immutable discoveries)
        - Filters support date range, significance threshold
        - Pagination via limit parameter
    """

    def __init__(self, db: Database) -> None:
        """Initialize repository with database connection manager.

        Args:
            db: Database instance for connection management
        """
        self.db = db

    async def create(self, item: Item) -> str:
        """Create a new item with deduplication.

        Args:
            item: Item model with all fields populated

        Returns:
            item.id on success, "" if duplicate URL

        Deduplication:
            - UNIQUE(domain_id, source_url) constraint
            - Returns "" instead of raising on duplicate
            - Allows orchestrator to skip duplicate gracefully

        Design Note:
            Empty string return is more ergonomic than catching IntegrityError.
            Orchestrator can use `if item_id:` to check success.
        """
        async with self.db.connection() as conn:
            try:
                await conn.execute(
                    """
                    INSERT INTO items (
                        id, domain_id, title, source, source_url, published_date,
                        discovered_at, summary, significance, significance_score,
                        raw_content, embedding_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item.id,
                        item.domain_id,
                        item.title,
                        item.source,
                        item.source_url,
                        item.published_date.isoformat() if item.published_date else None,
                        item.discovered_at.isoformat(),
                        item.summary,
                        item.significance,
                        item.significance_score,
                        item.raw_content,
                        item.embedding_id,
                    ),
                )
                await conn.commit()
                return item.id
            except sqlite3.IntegrityError:
                # Duplicate (domain_id, source_url)
                return ""

    async def get(self, item_id: str) -> Item | None:
        """Get an item by ID.

        Args:
            item_id: Item UUID

        Returns:
            Item model if found, None otherwise

        Use Cases:
            - Drill-down modal in UI
            - RAG context fetching
            - Annotation lookup
        """
        async with self.db.connection() as conn:
            async with conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return self._row_to_item(row)
                return None

    async def list_by_domain(
        self,
        domain_id: str,
        limit: int = 50,
        min_significance: float = 0.0,
        since: datetime | None = None,
    ) -> list[Item]:
        """List items for a domain with filters.

        Args:
            domain_id: Domain to query
            limit: Max items to return (default: 50)
            min_significance: Minimum significance_score (default: 0.0)
            since: Only items discovered after this date (optional)

        Returns:
            List of Item models ordered by discovered_at DESC (newest first)

        Use Cases:
            - Domain detail page (recent discoveries)
            - API /domains/{id}/items endpoint
            - Synthesis context (fetch last N items)

        Performance:
            - Index on (domain_id, discovered_at) for fast filtering
            - Limit prevents large result sets
        """
        query = """
            SELECT * FROM items
            WHERE domain_id = ? AND significance_score >= ?
        """
        params: list[str | float] = [domain_id, min_significance]

        if since:
            query += " AND discovered_at >= ?"
            params.append(since.isoformat())

        query += " ORDER BY discovered_at DESC LIMIT ?"
        params.append(limit)

        async with self.db.connection() as conn:
            async with conn.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                return [self._row_to_item(row) for row in rows]

    async def count_by_domain(self, domain_id: str) -> int:
        """Count items for a domain.

        Args:
            domain_id: Domain to count

        Returns:
            Total number of items in domain

        Use Cases:
            - Dashboard stats
            - Domain summary cards
        """
        async with self.db.connection() as conn:
            async with conn.execute(
                "SELECT COUNT(*) FROM items WHERE domain_id = ?", (domain_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

    async def get_avg_significance(self, domain_id: str) -> float:
        """Get average significance score for a domain's items.

        Args:
            domain_id: Domain to calculate average for

        Returns:
            Average significance score (0.0 if no items)

        Use Cases:
            - Dashboard stats
            - Domain quality metrics

        Performance Note:
            Uses SQL AVG() function - much more efficient than fetching
            all items and calculating in Python. O(1) query vs O(n) fetch.
        """
        async with self.db.connection() as conn:
            async with conn.execute(
                "SELECT AVG(significance_score) FROM items WHERE domain_id = ?",
                (domain_id,)
            ) as cursor:
                row = await cursor.fetchone()
                # AVG returns NULL if no rows
                return round(row[0], 2) if row and row[0] is not None else 0.0

    async def get_by_ids(self, item_ids: list[str]) -> list[Item]:
        """Get multiple items by their IDs (batch fetch).

        Args:
            item_ids: List of item UUIDs

        Returns:
            List of Item models (may be shorter if some IDs not found)

        Use Cases:
            - RAG: Fetch full items after semantic search
            - Synthesis: Get items referenced in update.item_ids

        Performance:
            - Single query with IN clause
            - ~5ms for 5-10 items

        Design Note:
            Returns empty list if item_ids is empty (no database hit).
        """
        if not item_ids:
            return []

        placeholders = ",".join("?" * len(item_ids))
        query = f"SELECT * FROM items WHERE id IN ({placeholders})"

        async with self.db.connection() as conn:
            async with conn.execute(query, item_ids) as cursor:
                rows = await cursor.fetchall()
                return [self._row_to_item(row) for row in rows]

    def _row_to_item(self, row: aiosqlite.Row) -> Item:
        """Convert database row to Item model.

        Args:
            row: aiosqlite.Row from SELECT query

        Returns:
            Item pydantic model with type-safe fields

        Type Conversions:
            - ISO timestamp strings → datetime objects
            - NULL dates → None
        """
        return Item(
            id=row["id"],
            domain_id=row["domain_id"],
            title=row["title"],
            source=row["source"],
            source_url=row["source_url"],
            published_date=datetime.fromisoformat(row["published_date"])
            if row["published_date"]
            else None,
            discovered_at=datetime.fromisoformat(row["discovered_at"]),
            summary=row["summary"],
            significance=row["significance"],
            significance_score=row["significance_score"],
            raw_content=row["raw_content"],
            embedding_id=row["embedding_id"],
        )


class UpdateRepository:
    """Repository for domain update CRUD operations.

    Updates are synthesis summaries created by agents after discovering items.

    Operations:
        - create: Insert new update
        - get_latest: Fetch most recent update for domain
        - list_by_domain: Query update history
        - get_total_token_usage: Sum token usage across all updates

    Design Notes:
        - Updates reference items via item_ids (JSON array)
        - open_questions stored as JSON array
        - token_usage tracks LLM API costs
    """

    def __init__(self, db: Database) -> None:
        """Initialize repository with database connection manager.

        Args:
            db: Database instance for connection management
        """
        self.db = db

    async def create(self, update: DomainUpdate) -> str:
        """Create a new domain update.

        Args:
            update: DomainUpdate model with all fields populated

        Returns:
            update.id on success

        JSON Serialization:
            - item_ids: list[str] → JSON array
            - open_questions: list[str] → JSON array

        Design Note:
            No deduplication (each synthesis is a new update).
        """
        async with self.db.connection() as conn:
            await conn.execute(
                """
                INSERT INTO updates (
                    id, domain_id, created_at, summary, item_ids, open_questions, token_usage
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    update.id,
                    update.domain_id,
                    update.created_at.isoformat(),
                    update.summary,
                    json.dumps(update.item_ids),
                    json.dumps(update.open_questions),
                    update.token_usage,
                ),
            )
            await conn.commit()
            return update.id

    async def get_latest(self, domain_id: str) -> DomainUpdate | None:
        """Get the latest update for a domain.

        Args:
            domain_id: Domain to query

        Returns:
            DomainUpdate model if any updates exist, None otherwise

        Use Cases:
            - Domain detail page (show latest summary)
            - API /domains/{id} endpoint

        Performance:
            - Index on (domain_id, created_at) for fast sorting
            - Returns single most recent row
        """
        async with self.db.connection() as conn:
            async with conn.execute(
                """
                SELECT * FROM updates
                WHERE domain_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (domain_id,),
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return self._row_to_update(row)
                return None

    async def list_by_domain(self, domain_id: str, limit: int = 10) -> list[DomainUpdate]:
        """List updates for a domain (newest first).

        Args:
            domain_id: Domain to query
            limit: Max updates to return (default: 10)

        Returns:
            List of DomainUpdate models ordered by created_at DESC

        Use Cases:
            - Update history page
            - API /domains/{id}/updates endpoint
        """
        async with self.db.connection() as conn:
            async with conn.execute(
                """
                SELECT * FROM updates
                WHERE domain_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (domain_id, limit),
            ) as cursor:
                rows = await cursor.fetchall()
                return [self._row_to_update(row) for row in rows]

    async def get_total_token_usage(self) -> int:
        """Get total token usage across all updates.

        Returns:
            Sum of token_usage for all updates

        Use Cases:
            - Dashboard stats (total LLM API usage)
            - Cost estimation

        Design Note:
            Uses COALESCE to return 0 if no updates (vs NULL).
        """
        async with self.db.connection() as conn:
            async with conn.execute(
                "SELECT COALESCE(SUM(token_usage), 0) FROM updates"
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

    def _row_to_update(self, row: aiosqlite.Row) -> DomainUpdate:
        """Convert database row to DomainUpdate model.

        Args:
            row: aiosqlite.Row from SELECT query

        Returns:
            DomainUpdate pydantic model with type-safe fields

        Type Conversions:
            - ISO timestamp string → datetime
            - JSON strings → list[str] (item_ids, open_questions)
            - NULL open_questions → [] (empty list)
        """
        return DomainUpdate(
            id=row["id"],
            domain_id=row["domain_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            summary=row["summary"],
            item_ids=json.loads(row["item_ids"]),
            open_questions=json.loads(row["open_questions"]) if row["open_questions"] else [],
            token_usage=row["token_usage"],
        )


class AnnotationRepository:
    """Repository for user annotation CRUD operations.

    Annotations are user notes and tags on discovered items (future feature).

    Operations:
        - create: Insert new annotation
        - update: Modify existing annotation
        - get_by_item: Fetch annotation for an item

    Design Notes:
        - One annotation per item (1:1 relationship)
        - Tags stored as JSON array
        - updated_at auto-updated on modification
    """

    def __init__(self, db: Database) -> None:
        """Initialize repository with database connection manager.

        Args:
            db: Database instance for connection management
        """
        self.db = db

    async def create(self, annotation: UserAnnotation) -> str:
        """Create a new annotation.

        Args:
            annotation: UserAnnotation model with all fields

        Returns:
            annotation.id on success

        Design Note:
            created_at and updated_at initially the same.
        """
        async with self.db.connection() as conn:
            await conn.execute(
                """
                INSERT INTO user_annotations (id, item_id, note, tags, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    annotation.id,
                    annotation.item_id,
                    annotation.note,
                    json.dumps(annotation.tags),
                    annotation.created_at.isoformat(),
                    annotation.updated_at.isoformat(),
                ),
            )
            await conn.commit()
            return annotation.id

    async def update(self, annotation: UserAnnotation) -> None:
        """Update an existing annotation.

        Args:
            annotation: UserAnnotation model with modifications

        Side Effects:
            Sets updated_at to datetime.utcnow()

        Design Note:
            Caller should fetch, modify, then call update().
        """
        annotation.updated_at = datetime.utcnow()
        async with self.db.connection() as conn:
            await conn.execute(
                """
                UPDATE user_annotations
                SET note = ?, tags = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    annotation.note,
                    json.dumps(annotation.tags),
                    annotation.updated_at.isoformat(),
                    annotation.id,
                ),
            )
            await conn.commit()

    async def get_by_item(self, item_id: str) -> UserAnnotation | None:
        """Get annotation for an item.

        Args:
            item_id: Item UUID

        Returns:
            UserAnnotation model if exists, None otherwise

        Use Cases:
            - Item detail page (show user notes)
            - API /items/{id}/annotation endpoint
        """
        async with self.db.connection() as conn:
            async with conn.execute(
                "SELECT * FROM user_annotations WHERE item_id = ?", (item_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return self._row_to_annotation(row)
                return None

    def _row_to_annotation(self, row: aiosqlite.Row) -> UserAnnotation:
        """Convert database row to UserAnnotation model.

        Args:
            row: aiosqlite.Row from SELECT query

        Returns:
            UserAnnotation pydantic model with type-safe fields

        Type Conversions:
            - ISO timestamp strings → datetime objects
            - JSON string → list[str] (tags)
            - NULL tags → [] (empty list)
        """
        return UserAnnotation(
            id=row["id"],
            item_id=row["item_id"],
            note=row["note"],
            tags=json.loads(row["tags"]) if row["tags"] else [],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
