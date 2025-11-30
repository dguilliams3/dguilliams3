"""AI Infrastructure domain configuration."""

from backend.models.domain import DomainConfig, SourceConfig

infrastructure_config = DomainConfig(
    id="infrastructure",
    name="AI Infrastructure",
    description=(
        "AI infrastructure and tooling: model serving, inference optimization, "
        "vector databases, MLOps, observability, LLM deployment"
    ),
    update_frequency_hours=24,
    sources=[
        SourceConfig(
            type="web_search",
            query="AI infrastructure 2025 model serving",
            max_results=10,
        ),
        SourceConfig(
            type="web_search",
            query="LLM inference optimization vLLM",
            max_results=5,
        ),
        SourceConfig(
            type="web_search",
            query="vector database embeddings",
            max_results=5,
        ),
        SourceConfig(
            type="web_search",
            query="MLOps LLM deployment",
            max_results=5,
        ),
    ],
    filter_prompt="""
Prioritize:
- Performance benchmarks with reproducible results
- New tools that solve real production problems
- Cost optimization techniques with quantified savings
- Novel approaches to scaling or efficiency

Deprioritize:
- Vendor marketing without benchmarks
- Incremental version updates without notable changes
- Tutorials on existing well-known tools
- Theoretical optimizations without implementation
""",
    synthesis_prompt="""
Structure as:
1. What's changing in production AI infrastructure?
2. New tools or major updates worth knowing about
3. Emerging patterns in how teams deploy and scale models

Be practical. Focus on what's available now, not roadmaps.
Highlight cost/performance trade-offs.
""",
)
