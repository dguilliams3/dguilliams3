"""RAG (Retrieval Augmented Generation) service for Q&A."""

import logging
from typing import Any

from anthropic import Anthropic

from backend.config import settings
from backend.db.chroma import EmbeddingStore
from backend.db.sqlite import ItemRepository
from backend.models.api import AskRequest, AskResponse
from backend.models.domain import Item

logger = logging.getLogger(__name__)


class RAGService:
    """Service for answering questions using retrieval-augmented generation."""

    def __init__(
        self, anthropic_client: Anthropic, embeddings: EmbeddingStore, item_repo: ItemRepository
    ) -> None:
        self.anthropic = anthropic_client
        self.embeddings = embeddings
        self.item_repo = item_repo

    async def ask(self, request: AskRequest) -> AskResponse:
        """Answer a question using RAG over the knowledge base."""
        logger.info(f"RAG query: {request.question[:100]}...")

        try:
            # Retrieve relevant items
            if request.item_id:
                # Specific item context
                item = await self.item_repo.get(request.item_id)
                if not item:
                    return AskResponse(
                        answer="Error: Item not found", citations=[], token_usage=0
                    )
                relevant_items = [item]
            else:
                # Semantic search
                search_results = await self.embeddings.search(
                    query=request.question, domain_id=request.domain_id, limit=5
                )

                # Get full items from database
                item_ids = [item_dict["id"] for item_dict, _ in search_results]
                relevant_items = await self.item_repo.get_by_ids(item_ids)

            if not relevant_items:
                return AskResponse(
                    answer="I couldn't find any relevant information to answer your question.",
                    citations=[],
                    token_usage=0,
                )

            # Build context from retrieved items
            context = self._build_context(relevant_items)

            # Generate answer
            answer, token_usage = await self._generate_answer(request.question, context)

            return AskResponse(answer=answer, citations=relevant_items, token_usage=token_usage)

        except Exception as e:
            logger.error(f"RAG query failed: {e}", exc_info=True)
            return AskResponse(
                answer=f"Error processing question: {str(e)}", citations=[], token_usage=0
            )

    def _build_context(self, items: list[Item]) -> str:
        """Build context string from relevant items."""
        context_parts = ["Here is relevant information from the knowledge base:\n"]

        for i, item in enumerate(items, 1):
            context_parts.append(
                f"\n[Source {i}] {item.title}\n"
                f"Domain: {item.domain_id}\n"
                f"Source: {item.source} ({item.source_url})\n"
                f"Summary: {item.summary}\n"
                f"Significance: {item.significance}\n"
                f"Score: {item.significance_score}\n"
            )

            if item.raw_content:
                # Include truncated raw content
                truncated = item.raw_content[:1000]
                context_parts.append(f"Content: {truncated}\n")

        return "\n".join(context_parts)

    async def _generate_answer(self, question: str, context: str) -> tuple[str, int]:
        """Generate answer using Claude with provided context."""
        system_prompt = """You are a research assistant helping users understand developments in various scientific and technical fields.

When answering questions:
1. Base your answer ONLY on the provided context
2. Cite specific sources by number (e.g., [Source 1])
3. Be precise and avoid speculation
4. If the context doesn't contain enough information, say so clearly
5. Maintain epistemic humility - flag uncertainties
6. Use clear, technical language appropriate for domain experts"""

        user_prompt = f"""{context}

Question: {question}

Please provide a detailed answer based on the sources above. Cite your sources using [Source N] format."""

        try:
            response = self.anthropic.messages.create(
                model=settings.default_qa_model,
                max_tokens=2048,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )

            answer = response.content[0].text
            token_usage = response.usage.input_tokens + response.usage.output_tokens

            return answer, token_usage

        except Exception as e:
            logger.error(f"Failed to generate answer: {e}")
            raise
