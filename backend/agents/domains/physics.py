"""Physics domain configuration."""

from backend.models.domain import DomainConfig, SourceConfig

physics_config = DomainConfig(
    id="physics",
    name="Physics",
    description=(
        "Fundamental physics: quantum mechanics, relativity, particle physics, "
        "condensed matter, gravitational waves, cosmology"
    ),
    update_frequency_hours=24,
    sources=[
        SourceConfig(
            type="web_search",
            query="physics breakthrough 2025",
            max_results=10,
        ),
        SourceConfig(
            type="web_search",
            query="LIGO gravitational waves recent",
            max_results=5,
        ),
        SourceConfig(
            type="web_search",
            query="quantum computing qubit advances",
            max_results=5,
        ),
        SourceConfig(
            type="web_search",
            query="superconductivity research 2025",
            max_results=5,
        ),
        SourceConfig(
            type="web_search",
            query="particle physics LHC discovery",
            max_results=5,
        ),
    ],
    filter_prompt="""
Prioritize:
- Experimental confirmations of theoretical predictions
- New phenomena that challenge existing models
- Significant improvements in measurement precision
- Novel theoretical frameworks with testable predictions

Deprioritize:
- Incremental parameter refinements
- Review articles (unless field-defining)
- Speculative theory without near-term testability
- Popular science articles that add no new information
""",
    synthesis_prompt="""
Structure the summary as:
1. What's the current frontier? What questions are being actively investigated?
2. What moved this period? Any surprises or unexpected results?
3. What's blocked or stuck? Where is progress slow?

Maintain epistemic humility—flag claims that are preliminary or contested.
Connect findings to the broader physics landscape.
""",
)
