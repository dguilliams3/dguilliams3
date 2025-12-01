# Architecture Decision Records

This document outlines key architectural decisions made in the Research Dashboard project, with rationale and trade-offs.

---

## ADR-001: SmolAgents ToolCallingAgent over CodeAgent

**Status**: Accepted
**Date**: 2025-12-01

### Context
Need to choose between SmolAgents' `ToolCallingAgent` (uses native function calling) vs `CodeAgent` (writes Python code to use tools).

### Decision
Use `ToolCallingAgent` for all agent operations (discovery and synthesis).

### Rationale
1. **Reliability**: Native function calling is more predictable than generated code
2. **Debugging**: Tool calls are explicit and logged, easier to trace
3. **Security**: No code execution risks
4. **Error handling**: Cleaner error messages from API calls vs runtime exceptions
5. **Performance**: Direct API calls are faster than code interpretation

### Trade-offs
- Less flexibility than CodeAgent (can't write custom logic)
- Limited to predefined tools
- Can't dynamically create new tools during execution

### Consequences
- Tools must be well-designed upfront
- Agents work within defined tool boundaries
- Predictable, production-ready behavior

---

## ADR-002: Final Answer Tool Pattern with Placeholder Schemas

**Status**: Accepted
**Date**: 2025-12-01

### Context
Agents need to return structured data. Should we use:
- Concrete examples in schemas ("title": "Quantum breakthrough at MIT")
- Placeholder descriptions ("title": "[descriptive title of finding]")

### Decision
Always use placeholder descriptions, never concrete examples in output schemas.

### Rationale
1. **Prevents overfitting**: Agents don't copy example formats verbatim
2. **Reduces bias**: No bias toward example sources (e.g., "Nature")
3. **Avoids anchoring**: Scores don't cluster around example values (e.g., 0.8)
4. **Maintains diversity**: Each response is genuinely original
5. **LLM best practice**: Placeholder descriptions are recommended by Anthropic

### Example
```python
# ❌ BAD - Concrete example
{
  "title": "Quantum computing breakthrough at IBM",
  "significance_score": "0.8"
}

# ✅ GOOD - Placeholder description
{
  "title": "[descriptive title of the finding]",
  "significance_score": "[number between 0.0 and 1.0]"
}
```

### Consequences
- All prompts use placeholder format
- Training examples in docs use placeholders
- Agent outputs are more diverse and unbiased

---

## ADR-003: Runtime Agent Configuration Store

**Status**: Accepted
**Date**: 2025-12-01

### Context
Users need to configure agent models and max_steps. Should we:
- Store in database (persistent)
- Store in config files (static)
- Store in memory (runtime)

### Decision
Use in-memory runtime configuration store that resets on app restart.

### Rationale
1. **Simplicity**: No database schema changes needed
2. **Fast**: Instant reads/writes, no I/O
3. **Experimentation-friendly**: Easy to test different configs
4. **Safe defaults**: Restarts reset to sensible defaults
5. **Sufficient for use case**: Users configure per session

### Trade-offs
- Configuration lost on restart
- Not suitable for multi-instance deployments
- Can't track config history

### Future Enhancement
If persistence needed, migrate to database table with:
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

### Consequences
- Config lives in `backend/agents/config_store.py`
- Agents created on-demand from current config
- UI warns that changes apply on next run

---

## ADR-004: Separate Prompt Building from Execution

**Status**: Accepted
**Date**: 2025-12-01

### Context
How should agents handle prompts? Options:
- Build and execute together (monolithic)
- Separate building from execution (modular)

### Decision
Separate prompt building into dedicated methods (`build_discovery_prompt()`, `build_synthesis_prompt()`).

### Rationale
1. **Enables preview**: Users can see prompts without executing
2. **Testing**: Can unit test prompt generation separately
3. **Debugging**: Easier to validate prompt structure
4. **Transparency**: Users understand what agents will do
5. **Reusability**: Can use prompts in other contexts

### Implementation
```python
class DomainAgent:
    def build_discovery_prompt(self) -> str:
        """Build discovery prompt without executing."""
        # Returns full prompt string

    async def discover(self) -> list[dict]:
        """Execute discovery using built prompt."""
        prompt = self.build_discovery_prompt()
        agent = self._create_discovery_agent()
        result = agent.run(prompt)
        return self._parse_result(result)
```

### Consequences
- Two API endpoints: one for preview, one for execution
- UI can show exact prompts before running
- Better developer experience for debugging

---

## ADR-005: Dynamic Agent Creation vs Singleton

**Status**: Accepted
**Date**: 2025-12-01

### Context
Should we:
- Create agents once on startup (singleton pattern)
- Create agents on-demand for each run (dynamic)

### Decision
Create agents dynamically using `_create_discovery_agent()` and `_create_synthesis_agent()` helpers.

### Rationale
1. **Fresh configuration**: Each run uses latest config from store
2. **No stale state**: Agents don't accumulate state between runs
3. **Memory efficient**: Agents garbage collected after use
4. **Model switching**: Can switch models mid-session
5. **Debugging**: Each run is independent

### Trade-offs
- Slight overhead creating agents (~50ms)
- Can't accumulate learning across runs
- No persistent agent memory

### Implementation
```python
def _create_discovery_agent(self) -> ToolCallingAgent:
    """Create discovery agent with current config."""
    config = agent_config_store.get(self.config.id)
    model = AnthropicModel(model_id=config.discovery_model, ...)
    return ToolCallingAgent(tools=self.tools, model=model, ...)
```

### Consequences
- Config changes apply immediately on next run
- No need to restart app for model changes
- Clean agent lifecycle

---

## ADR-006: Monolithic Backend vs Microservices

**Status**: Accepted
**Date**: 2025-12-01

### Context
Should the backend be:
- Monolithic (single FastAPI app)
- Microservices (separate services for discovery, synthesis, storage)

### Decision
Monolithic FastAPI application with all components in one process.

### Rationale
1. **Simplicity**: Single deployment, single config
2. **Local-first**: Designed for single-user local deployment
3. **Shared resources**: Database connections, event log, vector store
4. **Development speed**: Faster iteration without inter-service communication
5. **Debugging**: Easier to trace requests through single codebase

### Trade-offs
- Can't scale components independently
- All-or-nothing restarts
- Shared memory space

### When to Reconsider
If requirements change to:
- Multi-user SaaS deployment
- Need to scale discovery independently
- Want isolated failure domains
- Require different deployment schedules

### Consequences
- One `uvicorn` process serves all endpoints
- Agents run in background tasks
- Shared orchestrator coordinates all domains

---

## ADR-007: Local-First Data Architecture

**Status**: Accepted
**Date**: 2025-12-01

### Context
Should data be:
- Cloud-first (remote database, cloud storage)
- Local-first (SQLite, ChromaDB, JSONL files)

### Decision
Local-first with all data stored in `./data/` directory.

### Rationale
1. **Privacy**: Research data stays on user's machine
2. **Offline capability**: Works without internet (for viewing)
3. **Zero setup**: No database servers to configure
4. **Portability**: Copy `data/` folder to backup/migrate
5. **Cost**: No cloud storage costs
6. **Speed**: No network latency for queries

### Components
```
data/
├── research.db          # SQLite - structured data
├── chroma/             # ChromaDB - embeddings
└── events.jsonl        # Append-only event log
```

### Trade-offs
- Single-user only
- No cross-device sync
- Limited to disk capacity
- No automatic backups

### Consequences
- `.gitignore` excludes `data/`
- Users responsible for backups
- Migration script rebuilds from events if needed

---

## ADR-008: Event Sourcing with Append-Only Log

**Status**: Accepted
**Date**: 2025-12-01

### Context
How should we handle debugging and audit trails?

### Decision
Maintain append-only event log in JSONL format alongside structured database.

### Rationale
1. **Debugging**: Full audit trail of all agent actions
2. **Reproducibility**: Can replay events to rebuild state
3. **Analytics**: Analyze agent behavior over time
4. **Recovery**: Rebuild database from event log if corrupted
5. **Simple format**: JSONL is human-readable and grep-able

### Event Types
```json
{"event_type": "items_discovered", "domain_id": "physics", "payload": {"count": 5}}
{"event_type": "update_synthesized", "domain_id": "physics", "payload": {"update_id": "..."}}
{"event_type": "discovery_failed", "domain_id": "physics", "payload": {"error": "..."}}
```

### Trade-offs
- File grows unbounded (need log rotation)
- No queries on event log (need external tools)
- Duplicate data with database

### Consequences
- All agent operations log events
- Event log is source of truth
- Can rebuild structured DB from events

---

## ADR-009: Haiku for Discovery, Sonnet for Synthesis

**Status**: Accepted
**Date**: 2025-12-01

### Context
Which models should be default for each agent phase?

### Decision
- **Discovery**: claude-3-haiku-20240307 (default)
- **Synthesis**: claude-3-5-sonnet-20241022 (default)

### Rationale

**Haiku for Discovery:**
1. Fast execution (~2-5s per search)
2. Cost-efficient ($0.25/MTok input, $1.25/MTok output)
3. Good at structured tasks (web search, fetch, score)
4. 15 tool calls @ ~$0.10-0.20 per domain
5. Quality sufficient for filtering

**Sonnet for Synthesis:**
1. Better analytical writing
2. Deeper insight synthesis
3. More nuanced open questions
4. Still fast enough (~5-10s)
5. Worth the cost for final output

### Cost Analysis
```
Discovery (Haiku):  ~$0.15/domain
Synthesis (Sonnet): ~$0.10/domain
Total: ~$0.25/domain per update

4 domains × daily = ~$1/day
Monthly: ~$30
```

### User Override
Users can change via UI if they want:
- Opus for highest quality (expensive)
- Haiku for synthesis (cheaper, less depth)

### Consequences
- Default config balances cost/quality
- Most users won't need to change
- Power users can experiment

---

## ADR-010: ChromaDB for Embeddings over Alternatives

**Status**: Accepted
**Date**: 2025-12-01

### Context
Which vector database for semantic search? Options:
- ChromaDB (embedded)
- Pinecone (cloud)
- Weaviate (self-hosted)
- FAISS (local)

### Decision
ChromaDB with local persistence.

### Rationale
1. **Local-first**: No external dependencies
2. **Simple setup**: `pip install chromadb`
3. **Good enough performance**: <100ms for searches with 1000s of items
4. **Auto-embeddings**: Can use default embedding model
5. **Mature**: Production-ready, well-documented

### Trade-offs
- Not as fast as FAISS for huge datasets
- No cloud sync capabilities
- Single-machine only

### When to Reconsider
- If corpus grows to 100K+ items
- If need distributed search
- If require sub-10ms latency

### Consequences
- Embeddings stored in `data/chroma/`
- Automatic embedding on item ingest
- Semantic search endpoint for UI

---

## Summary Table

| Decision | Choice | Main Rationale |
|----------|--------|----------------|
| Agent Type | ToolCallingAgent | Reliability > Flexibility |
| Schema Format | Placeholders | Prevents overfitting |
| Config Storage | In-memory | Experimentation-friendly |
| Prompt Building | Separate methods | Enables preview |
| Agent Lifecycle | Dynamic creation | Fresh config each run |
| Architecture | Monolithic | Local-first simplicity |
| Data Storage | Local files | Privacy & offline capability |
| Audit Trail | Event sourcing | Debugging & recovery |
| Models | Haiku + Sonnet | Cost/quality balance |
| Vector DB | ChromaDB | Simple local embedding |

---

## Future Considerations

### Potential Enhancements
1. **Persistent config**: Migrate to database table
2. **Agent memory**: Accumulate context across runs
3. **Multi-user**: Add authentication and per-user data
4. **Cloud sync**: Optional backup to S3/Drive
5. **Distributed agents**: Scale discovery across machines
6. **Custom tools**: User-defined tools via plugin system

### Migration Paths
If requirements evolve:
- **Microservices**: Extract discovery/synthesis to separate services
- **Cloud deployment**: Move to PostgreSQL + managed vector DB
- **Multi-tenancy**: Add user_id to all tables
- **Real-time**: Add WebSocket for live agent progress

---

## How to Use This Document

**For LLM Coding Assistants:**
- Read relevant ADRs before making architectural changes
- Follow established patterns (e.g., placeholder schemas)
- Update ADRs if decisions change

**For Developers:**
- Understand why things are built this way
- Reference when proposing changes
- Update when decisions evolve

**For Users:**
- Understand trade-offs and limitations
- Know what's possible to customize
- See roadmap for future features
