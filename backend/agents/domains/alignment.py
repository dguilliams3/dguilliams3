"""AI Alignment domain configuration."""

from backend.models.domain import DomainConfig, SourceConfig

alignment_config = DomainConfig(
    id="alignment",
    name="AI Alignment",
    description=(
        "AI safety and alignment research: interpretability, RLHF, constitutional AI, "
        "deception detection, multi-agent dynamics, empirical alignment"
    ),
    update_frequency_hours=12,  # Faster-moving field
    sources=[
        SourceConfig(
            type="web_search",
            query="AI alignment research 2025",
            max_results=10,
        ),
        SourceConfig(
            type="web_search",
            query="Anthropic safety research interpretability",
            max_results=5,
        ),
        SourceConfig(
            type="web_search",
            query="AI mechanistic interpretability",
            max_results=5,
        ),
        SourceConfig(
            type="web_search",
            query="RLHF reinforcement learning human feedback",
            max_results=5,
        ),
    ],
    filter_prompt="""
Prioritize:
- Empirical findings that constrain alignment approaches
- Novel attack vectors or failure modes discovered
- Scalable oversight techniques with demonstrated results
- Interpretability breakthroughs with mechanistic understanding

Deprioritize:
- Philosophical arguments without empirical grounding
- Policy discussions (unless directly relevant to technical approaches)
- Speculation without technical content
- Announcements without technical details
""",
    synthesis_prompt="""
Structure as:
1. What empirical results changed our understanding this period?
2. What techniques are gaining/losing traction and why?
3. What open problems saw progress? What's still stuck?

Be concrete about what was actually demonstrated vs. claimed.
Distinguish between theoretical proposals and validated approaches.
""",
)
