# AGENTS.md — briefAI Coding Standards

## Project Overview

briefAI is a multi-pipeline AI intelligence platform. It scrapes, scores, and
surfaces AI industry news, investment signals, product launches, and Chinese AI
ecosystem data through a unified dashboard API.

## Architecture

```
briefAI/
├── pipeline/          # Pipeline framework (base, orchestrator, per-pipeline impls)
│   ├── base.py        # BasePipeline ABC, PipelineRegistry, event types
│   ├── orchestrator.py# Multi-pipeline coordinator
│   ├── run_store.py   # SQLite persistence for pipeline runs
│   └── news_pipeline.py # Reference pipeline implementation
├── agents/            # LLM-based analysis agents (adversarial pipeline)
├── api/               # FastAPI backend
│   ├── main.py        # App entry, middleware, router wiring
│   └── routers/       # Endpoint modules (signals, articles, pipeline_runs, etc.)
├── config/            # JSON/YAML configs (sources, categories, models, pipelines)
├── modules/           # Core processing (scraper, evaluator, formatter, etc.)
├── scrapers/          # Data source scrapers
├── utils/             # Shared utilities (LLM client, cache, scoring, etc.)
├── frontend/          # React + Vite dashboard
├── data/              # Generated data, caches, reports
├── scripts/           # One-off and maintenance scripts
└── tests/             # Test suite
```

## Python Standards

### Environment
- Python 3.11+
- Package manager: pip + requirements.txt
- Virtual environment: `.venv/` or `venv/`

### Build/Lint/Test Commands
```bash
# Setup environment
source setup.sh
# or manually:
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

# Run all tests
python -m pytest

# Run single test file
python -m pytest tests/test_quant.py

# Run specific test class/method
python -m pytest tests/test_quant.py::TestCorrelationEngine::test_init

# Run with verbose output
python -m pytest -v

# Run with coverage (if pytest-cov installed)
python -m pytest --cov=. --cov-report=html
```

Note: The project doesn't currently enforce linting tools. Consider adding:
- `black` for code formatting
- `flake8` for linting  
- `mypy` for type checking

### Imports
- Avoid inline imports unless breaking circular dependencies.
- Group: stdlib → third-party → local, separated by blank lines.
- Prefer qualified imports when importing 3+ names from one module.

### Type Hints
- Add type hints to all public APIs and function signatures.
- Use `Optional[X]` (not `X | None`) for Python 3.11 compat.
- Use dataclasses or pydantic models over raw dicts for structured data.

### Logging
- Use `loguru` everywhere. No `print()` in library code.
- `logger.info` for key events; `logger.debug` for verbose detail.
- Never log API keys or sensitive data.

### Error Handling
- Catch specific exceptions. Avoid bare `except:`.
- Keep try/except depth ≤ 2 levels.
- Use guard clauses for early returns.

### Structure
- Functions under 200 lines. Split into helpers.
- No nested function definitions — extract to module level.
- Separate I/O, parsing, and business logic.

### Documentation
- Use docstrings for all public classes and methods
- Follow Google-style docstring format
- Include type hints in docstring when helpful

### Testing
- Use `pytest` for all tests
- Place tests in `tests/` directory mirroring source structure
- Use descriptive test names that explain what they test
- Use fixtures for common test data
- Mock external dependencies

### Naming
- `snake_case` for functions and variables.
- `PascalCase` for classes.
- Constants: `UPPER_SNAKE_CASE` in a constants module or top of file.
- No magic strings — centralize in config files or constants.

## Pipeline Interface

All pipelines inherit from `pipeline.base.BasePipeline`:

```python
from pipeline.base import BasePipeline, PipelineConfig, PipelineEvent

class MyPipeline(BasePipeline):
    @property
    def pipeline_id(self) -> str:
        return "my_pipeline"

    @property
    def display_name(self) -> str:
        return "My Pipeline"

    async def run(self, config: PipelineConfig) -> AsyncGenerator[PipelineEvent, None]:
        yield self._stage_start("scrape")
        # ... do work, yield events ...
        yield self._result(result)
```

Register in `api/routers/pipeline_runs.py::_register_defaults()`.

## Model Configuration

Per-pipeline model selection lives in `config/models.yaml`.
Access via `utils/model_config.py`:

```python
from utils.model_config import get_model_config
config = get_model_config(pipeline="investing")
# config.model, config.provider, config.temperature, config.max_tokens
```

Environment variable overrides: `BRIEFAI_{PIPELINE}_MODEL`, `BRIEFAI_{PIPELINE}_PROVIDER`.

## Agent Orchestrator

The orchestrator (`agents/orchestrator.py`) implements the full multi-agent pipeline:

```
User Query → Super Agent (triage) → Planner (decompose) → Executor (parallel) → Synthesis
```

**Super Agent**: Lightweight LLM call that decides — answer directly or hand off to planner.
Enriches queries with structure (ticker symbols, analysis dimensions, entity types).

**LLM Planner**: Takes enriched query + available agent cards → produces `List[TaskPlan]`.
Dynamically discovers agents via `AgentRegistry.list_cards()`. Validates agent IDs.
Falls back to single-agent execution if planning fails.

**Async Task Executor**: Runs independent tasks concurrently via `asyncio.as_completed()`.
Supports task dependencies (sequential execution when `depends_on` is set).
Streams events through SSE as each task starts/completes.

**Conversation Store**: In-memory conversation history for follow-up context.
Enables "tell me more about X" queries without re-explaining context.

API: `POST /api/v1/orchestrator/query` (SSE stream)

```python
# Programmatic usage
from agents.orchestrator import AgentOrchestrator
orchestrator = AgentOrchestrator(registry=registry)
async for event in orchestrator.process("为什么寒武纪今天跌了8%?"):
    print(event.to_dict())
```

## Agent Interface

Analysis agents inherit from `agents.base.BaseAgent`:

```python
from agents.base import BaseAgent, AgentCard, AgentInput, AgentOutput

class MyAgent(BaseAgent):
    @property
    def card(self) -> AgentCard:
        return AgentCard(
            agent_id="my_agent",
            name="My Agent",
            description="Does smart analysis",
            model_task="deep_research",  # maps to config/models.yaml
        )

    async def run(self, input: AgentInput) -> AgentOutput:
        result = self._query_llm(prompt, system_prompt)
        return AgentOutput(agent_id="my_agent", data=result)
```

Register in `api/routers/agents.py::_register_defaults()`.

Built-in agents:
- **HypeManAgent** (`hypeman`): Bull case — adoption velocity, momentum signals
- **SkepticAgent** (`skeptic`): Bear case — risk analysis, commercial maturity
- **ArbiterAgent** (`arbiter`): Synthesis — conviction scores, recommendations

API: `GET /api/v1/agents`, `POST /api/v1/agents/{id}/run`

## API Conventions

- All REST endpoints under `/api/` prefix.
- v1 endpoints under `/api/v1/`.
- Pipeline SSE streaming: `POST /api/v1/pipelines/run` returns `text/event-stream`.
- Use pydantic models for request/response validation.
- Return JSON with consistent error format: `{"detail": "message"}`.

## Git Conventions

- Commit messages: conventional commits (`feat:`, `fix:`, `refactor:`, `docs:`).
- Don't commit temp files, JSON dumps, or log files.
- Run `pytest` before pushing.

## Key Dependencies

- **Core**: Python 3.11+, openai, requests, python-dotenv
- **Web UI**: streamlit
- **Scraping**: beautifulsoup4, lxml, feedparser, playwright
- **Data**: pyyaml, python-dateutil
- **NLP**: spacy, spacy-lookups-data
- **ML/AI**: sentence-transformers, chromadb, rapidfuzz
- **Financial**: yfinance, dbnomics, ccxt
- **Logging**: loguru
- **Testing**: pytest
