"""Runtime agent configuration store for dynamic model and parameter management.

This module provides an in-memory configuration store that allows users to customize
agent behavior (model selection, max_steps) without restarting the application.

Design Rationale (ADR-003):
    - In-memory storage: Fast, simple, no database schema changes
    - Per-domain config: Each domain can use different models/settings
    - Runtime modification: UI changes apply immediately on next agent run
    - Sensible defaults: Returns default config if domain not yet configured
    - Session-scoped: Config resets on app restart (intentional for experimentation)

Architecture:
    - Single global instance (agent_config_store) shared across application
    - Accessed by DomainAgent when creating ToolCallingAgent instances
    - Modified via API endpoints from frontend UI
    - No persistence layer (future enhancement if needed)

Usage Example:
    ```python
    # Get current config (returns defaults if not set)
    config = agent_config_store.get("physics")

    # Update config
    new_config = AgentConfig(
        discovery_model="claude-3-opus-20240229",
        discovery_max_steps=20
    )
    agent_config_store.update("physics", new_config)

    # Next agent run will use new config
    agent = domain_agent._create_discovery_agent()  # Uses Opus with 20 steps
    ```

Future Enhancement:
    If persistence needed, migrate to database table:
    ```sql
    CREATE TABLE agent_configs (
        domain_id TEXT PRIMARY KEY,
        discovery_model TEXT,
        synthesis_model TEXT,
        discovery_max_steps INTEGER,
        synthesis_max_steps INTEGER,
        updated_at TIMESTAMP
    );
    ```

See Also:
    - ARCHITECTURE_DECISIONS.md: ADR-003 (Runtime Agent Configuration Store)
    - backend/main.py: API endpoints for get/update config
    - frontend/src/components/AgentSettings.tsx: UI for configuration
"""

from backend.models.api import AgentConfig


class AgentConfigStore:
    """In-memory store for per-domain agent configurations.

    Provides runtime configuration management for agent model selection and
    max_steps parameters. Configurations persist only for the current session
    and reset to defaults on application restart.

    Attributes:
        configs (dict[str, AgentConfig]): Map of domain_id to AgentConfig

    Default Configuration:
        discovery_model: claude-3-haiku-20240307 (fast & cheap)
        synthesis_model: claude-3-5-sonnet-20241022 (better quality)
        discovery_max_steps: 15 (allows thorough search + fetch)
        synthesis_max_steps: 3 (no tools, just analysis)

    Thread Safety:
        Not thread-safe. Assumes single-threaded access or external locking.
        For multi-threaded use, add threading.Lock around mutations.
    """

    def __init__(self) -> None:
        """Initialize empty configuration store.

        Configs are created on-demand with defaults when first accessed via get().
        """
        self.configs: dict[str, AgentConfig] = {}

    def get(self, domain_id: str) -> AgentConfig:
        """Get configuration for a domain, creating defaults if not exists.

        Args:
            domain_id: Domain identifier (e.g., "physics", "alignment")

        Returns:
            AgentConfig with model selections and max_steps. If domain not
            yet configured, returns new AgentConfig with default values.

        Example:
            ```python
            config = store.get("physics")
            # First call: Returns AgentConfig(discovery_model="haiku", ...)
            # Subsequent calls: Returns same config object
            ```

        Design Note:
            Always returns a valid config (never None) to simplify caller code.
            Defaults match what's defined in AgentConfig pydantic model.
        """
        if domain_id not in self.configs:
            self.configs[domain_id] = AgentConfig()
        return self.configs[domain_id]

    def update(self, domain_id: str, config: AgentConfig) -> None:
        """Update configuration for a domain.

        Args:
            domain_id: Domain identifier to update
            config: New AgentConfig with updated model/max_steps values

        Effect:
            Replaces entire config for domain. Next agent creation will use
            new values. Does not affect currently running agents.

        Example:
            ```python
            # User changes discovery model to Opus via UI
            new_config = AgentConfig(
                discovery_model="claude-3-opus-20240229",
                synthesis_model="claude-3-5-sonnet-20241022",
                discovery_max_steps=20,
                synthesis_max_steps=3
            )
            store.update("physics", new_config)

            # Next refresh will use Opus with 20 max_steps
            ```

        Design Note:
            Updates are immediate and not persisted. This encourages
            experimentation (easy to reset by restarting app).
        """
        self.configs[domain_id] = config


# Global config store instance
# Imported by DomainAgent and API endpoints for shared access
agent_config_store = AgentConfigStore()

