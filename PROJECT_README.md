# Research Dashboard

> **Local-first research intelligence dashboard powered by LLM agents**

A sophisticated system that continuously monitors and synthesizes developments across configurable knowledge domains (Physics, AI Alignment, Agent Frameworks, AI Infrastructure, etc.). Uses LLM-powered agents to discover, filter, and synthesize information, presenting it through a clean React frontend.

**Core Value**: Open the app, see the current state of fields you care about, drill into anything interesting, never miss significant developments.

---

## Features

- ✨ **Autonomous Discovery**: SmolAgents-powered research agents continuously discover new developments
- 🧠 **Intelligent Filtering**: LLM-based significance scoring (0.0-1.0) to surface what matters
- 📊 **Synthesis Engine**: Automatic domain updates with summaries and open questions
- 🔍 **Semantic Search**: ChromaDB-powered vector search across all discoveries
- 💬 **RAG Q&A**: Ask questions about specific items with retrieval-augmented generation
- 📅 **Scheduled Updates**: Configurable update frequency per domain (12-24 hours)
- 💾 **Local-First**: All data stored locally (SQLite + ChromaDB), works offline
- 📝 **Event Sourcing**: Append-only event log for debugging and auditing

---

## Architecture

```
Frontend (React + Vite)
    ↓ REST + SSE
FastAPI Backend
    ↓
SmolAgents Orchestrator → Domain Agents (Physics, Alignment, etc.)
    ↓
Tools (WebSearch, FetchURL, Embeddings)
    ↓
Storage (SQLite + ChromaDB + Event Log)
```

### Tech Stack

| Component | Technology | Why |
|-----------|-----------|-----|
| Backend | FastAPI | Async-native, great typing |
| Agents | SmolAgents | Lightweight, code-first, good tool abstraction |
| LLM | Anthropic Claude | Primary (multi-provider ready) |
| Database | SQLite + aiosqlite | Local-first, zero config |
| Vector Store | ChromaDB | Simple, local, embeddings |
| Scheduling | APScheduler | Mature, async support |
| Frontend | React + Vite | Fast iteration |
| State | Zustand | Minimal boilerplate |
| Styling | Tailwind CSS | Rapid UI development |

---

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- API Keys:
  - **Anthropic API Key** (required)
  - **Brave Search API Key** (required for web search)

### 1. Clone and Setup

```bash
cd research-dashboard
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e .
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env and add your API keys:
# ANTHROPIC_API_KEY=sk-ant-...
# BRAVE_SEARCH_API_KEY=...
```

### 3. Initialize Database

```bash
python scripts/migrate.py
```

### 4. Run Backend

```bash
uvicorn backend.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`

API docs: `http://localhost:8000/docs`

### 5. Run Frontend (separate terminal)

```bash
cd frontend
npm install
npm run dev
```

The dashboard will be available at `http://localhost:5173`

---

## Domain Configuration

The system comes pre-configured with four domains:

### 1. **Physics**
- Update frequency: 24 hours
- Focus: Quantum mechanics, particle physics, gravitational waves, condensed matter
- Sources: Web search for breakthroughs, LIGO updates, quantum computing, superconductivity

### 2. **AI Alignment**
- Update frequency: 12 hours (faster-moving field)
- Focus: Interpretability, RLHF, constitutional AI, deception detection
- Sources: AI safety research, Anthropic updates, mechanistic interpretability

### 3. **Agent Frameworks**
- Update frequency: 24 hours
- Focus: LangGraph, SmolAgents, CrewAI, AutoGen, orchestration patterns
- Sources: Framework releases, architectural patterns, multi-agent systems

### 4. **AI Infrastructure**
- Update frequency: 24 hours
- Focus: Model serving, inference optimization, vector databases, MLOps
- Sources: Infrastructure updates, vLLM, vector databases, deployment patterns

### Adding New Domains

Create a new config file in `backend/agents/domains/`:

```python
from backend.models.domain import DomainConfig, SourceConfig

my_domain_config = DomainConfig(
    id="my_domain",
    name="My Research Domain",
    description="What this domain covers...",
    update_frequency_hours=24,
    sources=[
        SourceConfig(
            type="web_search",
            query="my domain recent developments",
            max_results=10,
        ),
    ],
    filter_prompt="""
    Prioritize:
    - Important criteria here

    Deprioritize:
    - Less important things
    """,
    synthesis_prompt="""
    Structure as:
    1. Current state
    2. Recent developments
    3. Open questions
    """,
)
```

Then add it to `backend/agents/orchestrator.py`:

```python
from backend.agents.domains.my_domain import my_domain_config

# In Orchestrator.__init__:
self.domain_configs = {
    # ... existing domains ...
    "my_domain": my_domain_config,
}
```

---

## API Endpoints

### Domains

```bash
GET  /api/domains                      # List all domains with staleness
GET  /api/domains/{domain_id}          # Get domain detail
GET  /api/domains/{domain_id}/items    # List items with filters
GET  /api/domains/{domain_id}/updates  # Get update history
POST /api/domains/{domain_id}/refresh  # Trigger manual refresh
```

### Search & Q&A

```bash
GET  /api/search?q={query}             # Semantic search
POST /api/ask                          # RAG-based Q&A
```

### Monitoring

```bash
GET /api/stats                         # Dashboard statistics
GET /api/health                        # Health check
GET /api/events                        # SSE stream for live updates
```

---

## Usage Examples

### Manual Domain Refresh

```bash
curl -X POST http://localhost:8000/api/domains/physics/refresh \
  -H "Content-Type: application/json" \
  -d '{"force": false}'
```

### Semantic Search

```bash
curl "http://localhost:8000/api/search?q=quantum+computing&domain_id=physics&limit=5"
```

### Ask a Question

```bash
curl -X POST http://localhost:8000/api/ask \
  -H "Content-Type: application/json" \
  -d '{
    "domain_id": "physics",
    "item_id": null,
    "question": "What are the latest developments in quantum computing?"
  }'
```

---

## Project Structure

```
research-dashboard/
├── backend/
│   ├── main.py                    # FastAPI app
│   ├── config.py                  # Settings
│   ├── models/                    # Pydantic models
│   │   ├── domain.py              # Domain, Item, Update
│   │   └── api.py                 # Request/Response models
│   ├── db/
│   │   ├── sqlite.py              # Database & repositories
│   │   ├── chroma.py              # Vector store
│   │   ├── events.py              # Event log
│   │   └── migrations/            # SQL migrations
│   ├── agents/
│   │   ├── base.py                # BaseDomainAgent
│   │   ├── tools.py               # SmolAgents tools
│   │   ├── orchestrator.py        # Scheduler & lifecycle
│   │   └── domains/               # Domain configs
│   └── services/
│       └── rag.py                 # RAG Q&A service
├── frontend/
│   └── src/
│       ├── stores/                # Zustand state
│       ├── components/            # React components
│       └── types/                 # TypeScript types
├── data/                          # Local persistence (gitignored)
├── scripts/
│   └── migrate.py                 # DB migration script
└── tests/
```

---

## Development

### Running Tests

```bash
# Backend tests
pytest tests/

# With coverage
pytest --cov=backend tests/
```

### Code Quality

```bash
# Type checking
mypy backend/

# Linting
ruff check backend/

# Format
ruff format backend/
```

### Database Migrations

1. Create a new migration file in `backend/db/migrations/`:
   - Name format: `00X_description.sql`
   - Include migration number and description

2. Run migrations:
   ```bash
   python scripts/migrate.py
   ```

---

## Configuration Options

All configuration via environment variables (`.env`):

```bash
# Required
ANTHROPIC_API_KEY=sk-ant-...
BRAVE_SEARCH_API_KEY=...

# Optional
LOG_LEVEL=INFO                    # DEBUG, INFO, WARNING, ERROR
DB_PATH=./data/research.db        # SQLite database path
CHROMA_PATH=./data/chroma          # ChromaDB storage
EVENTS_PATH=./data/events.jsonl   # Event log path
UPDATE_ON_STARTUP=false            # Run updates on app start

# Server
API_HOST=0.0.0.0
API_PORT=8000
FRONTEND_URL=http://localhost:5173
```

---

## Key Design Principles

1. **Local-First**: All data stored locally, works offline for viewing
2. **Event-Sourced**: Event log is source of truth, can rebuild from it
3. **Cost-Aware**: Track token usage, use cheapest models that work
4. **Incremental**: Never re-process known items, dedupe on (domain_id, source_url)
5. **Transparent**: Every claim traces to source items
6. **Fail Gracefully**: Handle network errors, API limits, malformed responses
7. **Extensible**: New domain = new config file, no code changes

---

## Troubleshooting

### "ModuleNotFoundError" when running backend

```bash
# Make sure you installed in editable mode
pip install -e .
```

### Database locked errors

```bash
# Make sure only one backend instance is running
pkill -f uvicorn
```

### ChromaDB errors

```bash
# Delete and recreate ChromaDB
rm -rf data/chroma
# Restart backend to recreate
```

### Frontend can't connect to backend

```bash
# Check backend is running on port 8000
curl http://localhost:8000/api/health

# Check CORS settings in backend/main.py
# Ensure frontend URL is in allow_origins
```

---

## Future Enhancements

- [ ] Multi-LLM provider support (OpenAI, Gemini)
- [ ] RSS feed sources
- [ ] arXiv paper integration
- [ ] Export to Markdown/PDF
- [ ] Email digest notifications
- [ ] Dark mode
- [ ] Advanced filtering UI
- [ ] Item tagging and annotations
- [ ] Custom domain creation via UI
- [ ] Agent performance analytics

---

## License

MIT

---

## Contributing

This is a personal research tool, but contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

---

## Acknowledgments

Built with:
- [FastAPI](https://fastapi.tiangolo.com/)
- [SmolAgents](https://github.com/huggingface/smolagents)
- [Anthropic Claude](https://www.anthropic.com/)
- [ChromaDB](https://www.trychroma.com/)
- [React](https://react.dev/)
- [Zustand](https://github.com/pmndrs/zustand)
- [Tailwind CSS](https://tailwindcss.com/)

---

**Built by Dan Guilliams** • [danguilliams.com](https://danguilliams.com)
