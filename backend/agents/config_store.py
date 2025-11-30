"""Runtime agent configuration store."""

from backend.models.api import AgentConfig


class AgentConfigStore:
    """In-memory store for agent configurations."""

    def __init__(self) -> None:
        self.configs: dict[str, AgentConfig] = {}

    def get(self, domain_id: str) -> AgentConfig:
        """Get configuration for a domain, or return defaults."""
        if domain_id not in self.configs:
            self.configs[domain_id] = AgentConfig()
        return self.configs[domain_id]

    def update(self, domain_id: str, config: AgentConfig) -> None:
        """Update configuration for a domain."""
        self.configs[domain_id] = config


# Global config store
agent_config_store = AgentConfigStore()
