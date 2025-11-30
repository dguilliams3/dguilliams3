"""Agent Frameworks domain configuration."""

from backend.models.domain import DomainConfig, SourceConfig

frameworks_config = DomainConfig(
    id="frameworks",
    name="Agent Frameworks",
    description=(
        "LLM agent frameworks, orchestration patterns, tool use, multi-agent systems: "
        "LangGraph, SmolAgents, CrewAI, AutoGen, etc."
    ),
    update_frequency_hours=24,
    sources=[
        SourceConfig(
            type="web_search",
            query="LLM agent framework 2025",
            max_results=10,
        ),
        SourceConfig(
            type="web_search",
            query="LangGraph SmolAgents update release",
            max_results=5,
        ),
        SourceConfig(
            type="web_search",
            query="AI agent orchestration patterns",
            max_results=5,
        ),
        SourceConfig(
            type="web_search",
            query="multi-agent systems LLM",
            max_results=5,
        ),
    ],
    filter_prompt="""
Prioritize:
- New framework releases or major version updates
- Novel architectural patterns with demonstrated benefits
- Benchmarks comparing agent approaches
- Production deployment case studies with real metrics

Deprioritize:
- Minor patch releases
- Tutorial content (unless introducing new patterns)
- Marketing content without technical substance
- Framework wars and subjective comparisons
""",
    synthesis_prompt="""
Structure as:
1. Framework landscape: what's maturing, what's emerging?
2. Architectural patterns: what's working in production?
3. Gaps: what problems lack good solutions?

Focus on practical utility for someone building agent systems.
Highlight trade-offs and design choices.
""",
)
