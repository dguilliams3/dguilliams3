#!/usr/bin/env python3
"""Database migration script."""

import asyncio
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.config import settings
from backend.db.sqlite import Database


async def main() -> None:
    """Run database migrations."""
    print("Research Dashboard - Database Migration")
    print(f"Database: {settings.db_path}")
    print()

    settings.ensure_data_dirs()

    db = Database()
    await db.run_migrations()

    print()
    print("✓ All migrations applied successfully")


if __name__ == "__main__":
    asyncio.run(main())
