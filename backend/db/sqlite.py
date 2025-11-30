"""SQLite database connection and repository implementations."""

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
    """SQLite database connection manager."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or settings.db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[aiosqlite.Connection]:
        """Get a database connection."""
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            yield conn

    async def run_migrations(self) -> None:
        """Run all pending migrations."""
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
    """Repository for domain operations."""

    def __init__(self, db: Database) -> None:
        self.db = db

    async def create(self, domain: Domain) -> str:
        """Create a new domain."""
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
        """Get a domain by ID."""
        async with self.db.connection() as conn:
            async with conn.execute(
                "SELECT * FROM domains WHERE id = ?", (domain_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return self._row_to_domain(row)
                return None

    async def list_all(self) -> list[Domain]:
        """List all domains."""
        async with self.db.connection() as conn:
            async with conn.execute(
                "SELECT * FROM domains ORDER BY created_at DESC"
            ) as cursor:
                rows = await cursor.fetchall()
                return [self._row_to_domain(row) for row in rows]

    async def update_last_updated(self, domain_id: str, timestamp: datetime) -> None:
        """Update the last_updated_at timestamp for a domain."""
        async with self.db.connection() as conn:
            await conn.execute(
                "UPDATE domains SET last_updated_at = ? WHERE id = ?",
                (timestamp.isoformat(), domain_id),
            )
            await conn.commit()

    def _row_to_domain(self, row: aiosqlite.Row) -> Domain:
        """Convert a database row to a Domain model."""
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
    """Repository for item operations."""

    def __init__(self, db: Database) -> None:
        self.db = db

    async def create(self, item: Item) -> str:
        """Create a new item."""
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
        """Get an item by ID."""
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
        """List items for a domain with filters."""
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
        """Count items for a domain."""
        async with self.db.connection() as conn:
            async with conn.execute(
                "SELECT COUNT(*) FROM items WHERE domain_id = ?", (domain_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

    async def get_by_ids(self, item_ids: list[str]) -> list[Item]:
        """Get multiple items by their IDs."""
        if not item_ids:
            return []

        placeholders = ",".join("?" * len(item_ids))
        query = f"SELECT * FROM items WHERE id IN ({placeholders})"

        async with self.db.connection() as conn:
            async with conn.execute(query, item_ids) as cursor:
                rows = await cursor.fetchall()
                return [self._row_to_item(row) for row in rows]

    def _row_to_item(self, row: aiosqlite.Row) -> Item:
        """Convert a database row to an Item model."""
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
    """Repository for domain update operations."""

    def __init__(self, db: Database) -> None:
        self.db = db

    async def create(self, update: DomainUpdate) -> str:
        """Create a new domain update."""
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
        """Get the latest update for a domain."""
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
        """List updates for a domain."""
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
        """Get total token usage across all updates."""
        async with self.db.connection() as conn:
            async with conn.execute(
                "SELECT COALESCE(SUM(token_usage), 0) FROM updates"
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

    def _row_to_update(self, row: aiosqlite.Row) -> DomainUpdate:
        """Convert a database row to a DomainUpdate model."""
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
    """Repository for user annotation operations."""

    def __init__(self, db: Database) -> None:
        self.db = db

    async def create(self, annotation: UserAnnotation) -> str:
        """Create a new annotation."""
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
        """Update an existing annotation."""
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
        """Get annotation for an item."""
        async with self.db.connection() as conn:
            async with conn.execute(
                "SELECT * FROM user_annotations WHERE item_id = ?", (item_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return self._row_to_annotation(row)
                return None

    def _row_to_annotation(self, row: aiosqlite.Row) -> UserAnnotation:
        """Convert a database row to a UserAnnotation model."""
        return UserAnnotation(
            id=row["id"],
            item_id=row["item_id"],
            note=row["note"],
            tags=json.loads(row["tags"]) if row["tags"] else [],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
