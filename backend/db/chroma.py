"""ChromaDB integration for semantic search and embeddings."""

import logging
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings

from backend.config import settings
from backend.models.domain import Item

logger = logging.getLogger(__name__)


class EmbeddingStore:
    """Vector store for semantic search using ChromaDB."""

    def __init__(self, persist_path: Path | None = None) -> None:
        self.persist_path = persist_path or settings.chroma_path
        self.persist_path.mkdir(parents=True, exist_ok=True)

        # Initialize ChromaDB client
        self.client = chromadb.PersistentClient(
            path=str(self.persist_path),
            settings=ChromaSettings(
                anonymized_telemetry=False,
                allow_reset=True,
            ),
        )

        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name="research_items",
            metadata={"description": "Research items with embeddings"},
        )

        logger.info(f"ChromaDB initialized at {self.persist_path}")

    async def add_item(self, item: Item) -> str:
        """Add an item to the vector store."""
        try:
            # Create document text from item fields
            document = self._item_to_document(item)

            # Create metadata
            metadata = {
                "domain_id": item.domain_id,
                "title": item.title,
                "source": item.source,
                "source_url": item.source_url or "",
                "significance_score": item.significance_score,
                "discovered_at": item.discovered_at.isoformat(),
            }

            # Add to collection
            self.collection.add(
                ids=[item.id],
                documents=[document],
                metadatas=[metadata],
            )

            logger.debug(f"Added item to vector store: {item.id}")
            return item.id

        except Exception as e:
            logger.error(f"Failed to add item to vector store: {e}")
            raise

    async def search(
        self, query: str, domain_id: str | None = None, limit: int = 5
    ) -> list[tuple[dict[str, Any], float]]:
        """
        Search for semantically similar items.
        Returns list of (item_dict, similarity_score) tuples.
        """
        try:
            # Build where filter if domain_id provided
            where_filter = {"domain_id": domain_id} if domain_id else None

            # Query collection
            results = self.collection.query(
                query_texts=[query], n_results=limit, where=where_filter
            )

            if not results["ids"] or not results["ids"][0]:
                return []

            # Format results
            items_with_scores: list[tuple[dict[str, Any], float]] = []
            for i, item_id in enumerate(results["ids"][0]):
                metadata = results["metadatas"][0][i] if results["metadatas"] else {}
                distance = results["distances"][0][i] if results["distances"] else 1.0

                # Convert distance to similarity (lower distance = higher similarity)
                similarity = 1.0 - distance

                item_dict = {
                    "id": item_id,
                    "title": metadata.get("title", ""),
                    "summary": results["documents"][0][i] if results["documents"] else "",
                    "domain_id": metadata.get("domain_id", ""),
                    "source": metadata.get("source", ""),
                    "source_url": metadata.get("source_url", ""),
                    "significance_score": metadata.get("significance_score", 0.0),
                }

                items_with_scores.append((item_dict, similarity))

            return items_with_scores

        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []

    async def get_by_id(self, item_id: str) -> dict[str, Any] | None:
        """Get an item from the vector store by ID."""
        try:
            result = self.collection.get(ids=[item_id])

            if not result["ids"]:
                return None

            metadata = result["metadatas"][0] if result["metadatas"] else {}
            document = result["documents"][0] if result["documents"] else ""

            return {
                "id": item_id,
                "title": metadata.get("title", ""),
                "summary": document,
                "domain_id": metadata.get("domain_id", ""),
                "source": metadata.get("source", ""),
                "source_url": metadata.get("source_url", ""),
                "significance_score": metadata.get("significance_score", 0.0),
            }

        except Exception as e:
            logger.error(f"Failed to get item from vector store: {e}")
            return None

    async def delete_item(self, item_id: str) -> None:
        """Delete an item from the vector store."""
        try:
            self.collection.delete(ids=[item_id])
            logger.debug(f"Deleted item from vector store: {item_id}")
        except Exception as e:
            logger.error(f"Failed to delete item from vector store: {e}")

    def count_items(self, domain_id: str | None = None) -> int:
        """Count items in the vector store."""
        try:
            if domain_id:
                result = self.collection.get(where={"domain_id": domain_id})
                return len(result["ids"]) if result["ids"] else 0
            else:
                return self.collection.count()
        except Exception as e:
            logger.error(f"Failed to count items: {e}")
            return 0

    def _item_to_document(self, item: Item) -> str:
        """Convert an Item to a document string for embedding."""
        parts = [
            f"Title: {item.title}",
            f"Summary: {item.summary}",
            f"Significance: {item.significance}",
        ]

        if item.raw_content:
            # Include truncated raw content
            truncated = item.raw_content[:1000]
            parts.append(f"Content: {truncated}")

        return "\n\n".join(parts)
