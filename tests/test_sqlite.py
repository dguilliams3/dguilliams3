"""Tests for SQLite database repositories."""

import asyncio
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from backend.db.sqlite import Database, DomainRepository, ItemRepository, UpdateRepository
from backend.models.domain import Domain, DomainConfig, Item, DomainUpdate


@pytest.fixture
async def test_db(tmp_path):
    """Create a test database instance."""
    db_path = tmp_path / "test.db"
    db = Database(db_path)
    await db.initialize()
    await db.run_migrations()
    yield db
    await db.close()


@pytest.fixture
async def domain_repo(test_db):
    """Create a domain repository instance."""
    return DomainRepository(test_db)


@pytest.fixture
async def item_repo(test_db):
    """Create an item repository instance."""
    return ItemRepository(test_db)


@pytest.fixture
async def update_repo(test_db):
    """Create an update repository instance."""
    return UpdateRepository(test_db)


@pytest.fixture
def sample_domain_config():
    """Create a sample domain configuration."""
    return DomainConfig(
        id="test-domain",
        name="Test Domain",
        description="A test research domain",
        keywords=["test", "research"],
        sources=[],
        discovery_prompts=[],
        synthesis_prompt_template="",
        refresh_interval_hours=24,
    )


@pytest.fixture
def sample_domain(sample_domain_config):
    """Create a sample domain."""
    return Domain(
        id=sample_domain_config.id,
        name=sample_domain_config.name,
        description=sample_domain_config.description,
        config=sample_domain_config,
        created_at=datetime.utcnow(),
        last_updated_at=None,
    )


class TestDomainRepository:
    """Tests for DomainRepository."""

    @pytest.mark.asyncio
    async def test_create_domain(self, domain_repo, sample_domain):
        """Test creating a domain."""
        await domain_repo.create(sample_domain)

        # Verify it was created
        retrieved = await domain_repo.get(sample_domain.id)
        assert retrieved is not None
        assert retrieved.id == sample_domain.id
        assert retrieved.name == sample_domain.name
        assert retrieved.description == sample_domain.description

    @pytest.mark.asyncio
    async def test_create_domain_idempotent(self, domain_repo, sample_domain):
        """Test that creating the same domain twice doesn't error (idempotent)."""
        await domain_repo.create(sample_domain)
        await domain_repo.create(sample_domain)  # Should not raise

        # Verify only one exists
        domains = await domain_repo.list_all()
        assert len(domains) == 1

    @pytest.mark.asyncio
    async def test_get_nonexistent_domain(self, domain_repo):
        """Test getting a domain that doesn't exist returns None."""
        result = await domain_repo.get("nonexistent-id")
        assert result is None

    @pytest.mark.asyncio
    async def test_list_all_domains(self, domain_repo, sample_domain_config):
        """Test listing all domains."""
        # Create multiple domains
        domain1 = Domain(
            id="domain-1",
            name="Domain 1",
            description="First domain",
            config=sample_domain_config,
            created_at=datetime.utcnow(),
        )
        domain2 = Domain(
            id="domain-2",
            name="Domain 2",
            description="Second domain",
            config=sample_domain_config,
            created_at=datetime.utcnow(),
        )

        await domain_repo.create(domain1)
        await domain_repo.create(domain2)

        # List all
        domains = await domain_repo.list_all()
        assert len(domains) == 2
        ids = {d.id for d in domains}
        assert "domain-1" in ids
        assert "domain-2" in ids

    @pytest.mark.asyncio
    async def test_update_last_updated_at(self, domain_repo, sample_domain):
        """Test updating domain's last_updated_at timestamp."""
        await domain_repo.create(sample_domain)

        # Update timestamp
        now = datetime.utcnow()
        await domain_repo.update_last_updated_at(sample_domain.id, now)

        # Verify update
        retrieved = await domain_repo.get(sample_domain.id)
        assert retrieved.last_updated_at is not None
        # Allow for small time differences
        time_diff = abs((retrieved.last_updated_at - now).total_seconds())
        assert time_diff < 1  # Within 1 second


class TestItemRepository:
    """Tests for ItemRepository."""

    @pytest.mark.asyncio
    async def test_create_item(self, item_repo, domain_repo, sample_domain):
        """Test creating an item."""
        await domain_repo.create(sample_domain)

        item = Item(
            id="item-1",
            domain_id=sample_domain.id,
            title="Test Item",
            summary="A test research item",
            source="Test Source",
            source_url="https://example.com",
            significance="High impact finding",
            significance_score=0.9,
            discovered_at=datetime.utcnow(),
            raw_content="Raw content here",
        )

        item_id = await item_repo.create(item)
        assert item_id == "item-1"

        # Verify retrieval
        retrieved = await item_repo.get(item_id)
        assert retrieved is not None
        assert retrieved.title == "Test Item"
        assert retrieved.significance_score == 0.9

    @pytest.mark.asyncio
    async def test_create_item_idempotent(self, item_repo, domain_repo, sample_domain):
        """Test that creating the same item twice doesn't duplicate."""
        await domain_repo.create(sample_domain)

        item = Item(
            id="item-1",
            domain_id=sample_domain.id,
            title="Test Item",
            summary="Summary",
            source="Source",
            significance="Sig",
            significance_score=0.8,
            discovered_at=datetime.utcnow(),
        )

        await item_repo.create(item)
        await item_repo.create(item)  # Should not raise

        # Verify only one exists
        items = await item_repo.list_by_domain(sample_domain.id, limit=100)
        assert len(items) == 1

    @pytest.mark.asyncio
    async def test_list_by_domain(self, item_repo, domain_repo, sample_domain):
        """Test listing items by domain."""
        await domain_repo.create(sample_domain)

        # Create multiple items
        for i in range(5):
            item = Item(
                id=f"item-{i}",
                domain_id=sample_domain.id,
                title=f"Item {i}",
                summary=f"Summary {i}",
                source="Source",
                significance=f"Significance {i}",
                significance_score=0.5 + (i * 0.1),
                discovered_at=datetime.utcnow(),
            )
            await item_repo.create(item)

        # List all
        items = await item_repo.list_by_domain(sample_domain.id, limit=10)
        assert len(items) == 5

    @pytest.mark.asyncio
    async def test_list_by_domain_with_min_significance(
        self, item_repo, domain_repo, sample_domain
    ):
        """Test filtering items by minimum significance score."""
        await domain_repo.create(sample_domain)

        # Create items with different significance scores
        for i in range(5):
            item = Item(
                id=f"item-{i}",
                domain_id=sample_domain.id,
                title=f"Item {i}",
                summary=f"Summary {i}",
                source="Source",
                significance=f"Significance {i}",
                significance_score=0.2 * i,  # 0.0, 0.2, 0.4, 0.6, 0.8
                discovered_at=datetime.utcnow(),
            )
            await item_repo.create(item)

        # Filter by min_significance=0.5
        items = await item_repo.list_by_domain(
            sample_domain.id, limit=10, min_significance=0.5
        )
        # Should only get items with scores >= 0.5 (0.6 and 0.8)
        assert len(items) == 2
        assert all(item.significance_score >= 0.5 for item in items)

    @pytest.mark.asyncio
    async def test_list_by_domain_with_since_filter(
        self, item_repo, domain_repo, sample_domain
    ):
        """Test filtering items by discovery date."""
        await domain_repo.create(sample_domain)

        now = datetime.utcnow()
        yesterday = now - timedelta(days=1)
        last_week = now - timedelta(days=7)

        # Create items with different discovery dates
        item1 = Item(
            id="item-1",
            domain_id=sample_domain.id,
            title="Old Item",
            summary="Summary",
            source="Source",
            significance="Sig",
            significance_score=0.8,
            discovered_at=last_week,
        )
        item2 = Item(
            id="item-2",
            domain_id=sample_domain.id,
            title="Recent Item",
            summary="Summary",
            source="Source",
            significance="Sig",
            significance_score=0.8,
            discovered_at=now,
        )

        await item_repo.create(item1)
        await item_repo.create(item2)

        # Filter for items since yesterday
        items = await item_repo.list_by_domain(
            sample_domain.id, limit=10, since=yesterday
        )
        # Should only get the recent item
        assert len(items) == 1
        assert items[0].id == "item-2"

    @pytest.mark.asyncio
    async def test_count_by_domain(self, item_repo, domain_repo, sample_domain):
        """Test counting items in a domain."""
        await domain_repo.create(sample_domain)

        # Initially zero
        count = await item_repo.count_by_domain(sample_domain.id)
        assert count == 0

        # Create items
        for i in range(3):
            item = Item(
                id=f"item-{i}",
                domain_id=sample_domain.id,
                title=f"Item {i}",
                summary="Summary",
                source="Source",
                significance="Sig",
                significance_score=0.8,
                discovered_at=datetime.utcnow(),
            )
            await item_repo.create(item)

        # Count should be 3
        count = await item_repo.count_by_domain(sample_domain.id)
        assert count == 3

    @pytest.mark.asyncio
    async def test_get_avg_significance(self, item_repo, domain_repo, sample_domain):
        """Test calculating average significance score."""
        await domain_repo.create(sample_domain)

        # Create items with known scores
        scores = [0.2, 0.4, 0.6, 0.8, 1.0]
        for i, score in enumerate(scores):
            item = Item(
                id=f"item-{i}",
                domain_id=sample_domain.id,
                title=f"Item {i}",
                summary="Summary",
                source="Source",
                significance="Sig",
                significance_score=score,
                discovered_at=datetime.utcnow(),
            )
            await item_repo.create(item)

        # Average should be (0.2 + 0.4 + 0.6 + 0.8 + 1.0) / 5 = 0.6
        avg = await item_repo.get_avg_significance(sample_domain.id)
        assert abs(avg - 0.6) < 0.01  # Allow for floating point errors

    @pytest.mark.asyncio
    async def test_get_avg_significance_empty_domain(self, item_repo, domain_repo, sample_domain):
        """Test average significance returns 0 for empty domain."""
        await domain_repo.create(sample_domain)

        avg = await item_repo.get_avg_significance(sample_domain.id)
        assert avg == 0.0

    @pytest.mark.asyncio
    async def test_get_by_ids(self, item_repo, domain_repo, sample_domain):
        """Test retrieving multiple items by IDs."""
        await domain_repo.create(sample_domain)

        # Create items
        for i in range(5):
            item = Item(
                id=f"item-{i}",
                domain_id=sample_domain.id,
                title=f"Item {i}",
                summary="Summary",
                source="Source",
                significance="Sig",
                significance_score=0.8,
                discovered_at=datetime.utcnow(),
            )
            await item_repo.create(item)

        # Get subset by IDs
        items = await item_repo.get_by_ids(["item-1", "item-3"])
        assert len(items) == 2
        ids = {item.id for item in items}
        assert ids == {"item-1", "item-3"}

    @pytest.mark.asyncio
    async def test_get_by_ids_empty_list(self, item_repo):
        """Test that get_by_ids with empty list returns empty list."""
        items = await item_repo.get_by_ids([])
        assert items == []


class TestUpdateRepository:
    """Tests for UpdateRepository."""

    @pytest.mark.asyncio
    async def test_create_update(self, update_repo, domain_repo, sample_domain):
        """Test creating a domain update."""
        await domain_repo.create(sample_domain)

        update = DomainUpdate(
            id="update-1",
            domain_id=sample_domain.id,
            summary="Test update summary",
            key_findings=["Finding 1", "Finding 2"],
            item_count=10,
            token_usage=1000,
            created_at=datetime.utcnow(),
        )

        await update_repo.create(update)

        # Verify retrieval
        retrieved = await update_repo.get_latest(sample_domain.id)
        assert retrieved is not None
        assert retrieved.id == "update-1"
        assert retrieved.summary == "Test update summary"
        assert len(retrieved.key_findings) == 2

    @pytest.mark.asyncio
    async def test_get_latest_update(self, update_repo, domain_repo, sample_domain):
        """Test getting the latest update for a domain."""
        await domain_repo.create(sample_domain)

        # Create multiple updates
        for i in range(3):
            update = DomainUpdate(
                id=f"update-{i}",
                domain_id=sample_domain.id,
                summary=f"Update {i}",
                key_findings=[],
                item_count=i,
                token_usage=100,
                created_at=datetime.utcnow() + timedelta(seconds=i),
            )
            await update_repo.create(update)
            await asyncio.sleep(0.01)  # Ensure different timestamps

        # Get latest should return the last one
        latest = await update_repo.get_latest(sample_domain.id)
        assert latest is not None
        assert latest.id == "update-2"

    @pytest.mark.asyncio
    async def test_list_by_domain(self, update_repo, domain_repo, sample_domain):
        """Test listing updates for a domain."""
        await domain_repo.create(sample_domain)

        # Create multiple updates
        for i in range(5):
            update = DomainUpdate(
                id=f"update-{i}",
                domain_id=sample_domain.id,
                summary=f"Update {i}",
                key_findings=[],
                item_count=i,
                token_usage=100,
                created_at=datetime.utcnow() + timedelta(seconds=i),
            )
            await update_repo.create(update)

        # List with limit
        updates = await update_repo.list_by_domain(sample_domain.id, limit=3)
        assert len(updates) == 3
        # Should be in reverse chronological order
        assert updates[0].id == "update-4"
        assert updates[1].id == "update-3"
        assert updates[2].id == "update-2"

    @pytest.mark.asyncio
    async def test_count_by_domain(self, update_repo, domain_repo, sample_domain):
        """Test counting updates for a domain."""
        await domain_repo.create(sample_domain)

        # Initially zero
        count = await update_repo.count_by_domain(sample_domain.id)
        assert count == 0

        # Create updates
        for i in range(4):
            update = DomainUpdate(
                id=f"update-{i}",
                domain_id=sample_domain.id,
                summary=f"Update {i}",
                key_findings=[],
                item_count=i,
                token_usage=100,
                created_at=datetime.utcnow(),
            )
            await update_repo.create(update)

        # Count should be 4
        count = await update_repo.count_by_domain(sample_domain.id)
        assert count == 4

    @pytest.mark.asyncio
    async def test_get_total_token_usage(self, update_repo, domain_repo, sample_domain):
        """Test calculating total token usage across all updates."""
        await domain_repo.create(sample_domain)

        # Create updates with different token usage
        token_usages = [100, 200, 300, 400]
        for i, tokens in enumerate(token_usages):
            update = DomainUpdate(
                id=f"update-{i}",
                domain_id=sample_domain.id,
                summary=f"Update {i}",
                key_findings=[],
                item_count=i,
                token_usage=tokens,
                created_at=datetime.utcnow(),
            )
            await update_repo.create(update)

        # Total should be sum
        total = await update_repo.get_total_token_usage()
        assert total == sum(token_usages)  # 100 + 200 + 300 + 400 = 1000

    @pytest.mark.asyncio
    async def test_get_total_token_usage_empty(self, update_repo):
        """Test that total token usage returns 0 when no updates exist."""
        total = await update_repo.get_total_token_usage()
        assert total == 0
