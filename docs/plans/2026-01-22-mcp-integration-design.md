# MCP Integration Design for BriefAI

**Date:** 2026-01-22
**Status:** Design Complete

## Overview

Integrate Model Context Protocol (MCP) into BriefAI for JIT context loading, enabling:
- Parallel data fetching (5-10x faster pipeline)
- Semantic search on cached context
- Agentic tool use for adversarial agents

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     BriefAI Application                      │
│  ┌─────────────────┐   ┌─────────────────┐                  │
│  │ EnhancedLLMClient│   │ Pipeline Modules │                  │
│  │ (Kimi/OpenRouter)│   │ (Collection,     │                  │
│  └────────┬────────┘   │  Finalization)   │                  │
│           │            └────────┬─────────┘                  │
│           ▼                     ▼                            │
│  ┌─────────────────────────────────────────────┐             │
│  │           MCP Client (mcp_client.py)        │             │
│  │   - Tool invocation                         │             │
│  │   - Resource fetching                       │             │
│  │   - Response parsing                        │             │
│  └───────────────────┬─────────────────────────┘             │
└──────────────────────┼──────────────────────────────────────┘
                       │ stdio
┌──────────────────────▼──────────────────────────────────────┐
│               MCP Server (mcp_server/main.py)                │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐             │
│  │ Resources  │  │   Tools    │  │  Prompts   │             │
│  │ (passive)  │  │ (active)   │  │ (personas) │             │
│  └────────────┘  └────────────┘  └────────────┘             │
└─────────────────────────────────────────────────────────────┘
```

## Resources (Passive Data Access)

Read-only access to cached/stored data. No external API calls.

| Resource URI | Description | Returns |
|--------------|-------------|---------|
| `trend://latest` | Latest trend_radar.db snapshot | Top entities with scores |
| `trend://entity/{name}` | Single entity's trend history | 7-day signal history |
| `signals://financial/{ticker}` | Cached financial signals | PMS/CSS/MRS scores |
| `context://articles/{date}` | Cached articles for date | Article list with metadata |
| `conviction://scores` | Devil's Advocate results | Bull/Bear/Arbiter verdicts |
| `vc://firms` | OpenBook VC data | Firm + investor data |

## Tools (Active Operations)

Actions that fetch live data or perform computation.

| Tool | Description | When to Use |
|------|-------------|-------------|
| `scrape_url(url)` | Fetch & parse any URL | Missing context for an entity |
| `search_web(query)` | Google/Bing search | Finding recent news |
| `get_repo_health(owner, repo)` | Live GitHub stats | Verifying OSS claims |
| `fetch_funding(company)` | Crunchbase/Wikidata lookup | Skeptic needs funding data |
| `semantic_search(query, days)` | Vector search on cache | Finding related articles |
| `extract_entities(text)` | spaCy + LLM extraction | Processing new articles |
| `run_scraper(name)` | Execute specific scraper | Refreshing stale data |

## Prompts (Persona Templates)

Reusable system prompts stored as Markdown files.

| Prompt | File | Used By |
|--------|------|---------|
| `hypeman` | `prompts/hypeman.md` | Hype-Man Agent |
| `skeptic` | `prompts/skeptic.md` | Skeptic Agent |
| `arbiter` | `prompts/arbiter.md` | Arbiter Agent |
| `evaluator` | `prompts/evaluator.md` | NewsEvaluator |

**Benefit:** Persona prompts live in MCP config, not Python strings. Tune "skepticism level" by editing `skeptic.md` without touching agent code.

## File Structure

```
briefAI/
├── mcp_server/
│   ├── __init__.py
│   ├── main.py              # FastMCP app entry point
│   ├── errors.py            # Custom exceptions
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── web_scraper.py   # scrape_url, search_web
│   │   ├── github_tools.py  # get_repo_health
│   │   ├── data_tools.py    # fetch_funding, run_scraper
│   │   └── search_tools.py  # semantic_search, extract_entities
│   ├── resources/
│   │   ├── __init__.py
│   │   ├── trend_db.py      # trend://* resources
│   │   ├── signals_db.py    # signals://* resources
│   │   └── context.py       # context://* resources
│   └── prompts/
│       ├── __init__.py      # load_prompt() helper
│       ├── hypeman.md       # Bull thesis prompt
│       ├── skeptic.md       # Bear thesis prompt
│       ├── arbiter.md       # Synthesis prompt
│       └── evaluator.md     # Article scoring prompt
├── utils/
│   └── mcp_client.py        # Client that connects LLM → MCP
└── config/
    └── mcp_config.json      # Tool/resource configuration
```

## MCP Server Implementation

### main.py

```python
from fastmcp import FastMCP
from pathlib import Path

mcp = FastMCP("briefai-mcp")

# Register all modules
from mcp_server.tools import github_tools, web_scraper, data_tools, search_tools
from mcp_server.resources import trend_db, signals_db, context

github_tools.register(mcp)
web_scraper.register(mcp)
data_tools.register(mcp)
search_tools.register(mcp)
trend_db.register(mcp)
signals_db.register(mcp)
context.register(mcp)

# Register prompts with dynamic loading
from mcp_server.prompts import load_prompt

@mcp.prompt()
def skeptic(entity_name: str, bull_thesis: str = "") -> str:
    """Bear thesis generator persona"""
    template = load_prompt("skeptic.md")
    return template.format(entity_name=entity_name, bull_thesis=bull_thesis)

@mcp.prompt()
def hypeman(entity_name: str) -> str:
    """Bull thesis generator persona"""
    template = load_prompt("hypeman.md")
    return template.format(entity_name=entity_name)

@mcp.prompt()
def arbiter(bull_thesis: str, bear_thesis: str) -> str:
    """Synthesis and scoring persona"""
    template = load_prompt("arbiter.md")
    return template.format(bull_thesis=bull_thesis, bear_thesis=bear_thesis)

if __name__ == "__main__":
    mcp.run()
```

### prompts/__init__.py

```python
from pathlib import Path

def load_prompt(filename: str) -> str:
    """Load a Markdown prompt template."""
    prompt_path = Path(__file__).parent / filename
    if not prompt_path.exists():
        return f"Error: Prompt template {filename} not found."
    return prompt_path.read_text(encoding="utf-8")
```

### tools/github_tools.py

```python
import os
import requests
from fastmcp import FastMCP
from loguru import logger
from mcp_server.errors import MCPToolError, RateLimitedError

def get_headers():
    token = os.getenv("GITHUB_TOKEN")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}

def register(mcp: FastMCP):
    @mcp.tool()
    def get_repo_health(owner: str, repo: str) -> dict:
        """Get live GitHub repository health metrics.

        Args:
            owner: GitHub username or org
            repo: Repository name

        Returns:
            Dict with stars, forks, issues, last_commit, language
        """
        try:
            url = f"https://api.github.com/repos/{owner}/{repo}"
            resp = requests.get(url, headers=get_headers(), timeout=10)

            if resp.status_code == 403:
                raise RateLimitedError("github", retry_after=60)
            if resp.status_code == 404:
                raise MCPToolError("github", f"Repo not found: {owner}/{repo}")

            resp.raise_for_status()
            data = resp.json()

            return {
                "stars": data.get("stargazers_count"),
                "forks": data.get("forks_count"),
                "open_issues": data.get("open_issues_count"),
                "last_push": data.get("pushed_at"),
                "language": data.get("language"),
                "license": data.get("license", {}).get("spdx_id") if data.get("license") else None,
            }
        except requests.RequestException as e:
            logger.warning(f"GitHub API error: {e}")
            raise MCPToolError("github", str(e))
```

### resources/trend_db.py

```python
import json
import sqlite3
from pathlib import Path
from fastmcp import FastMCP

DB_PATH = Path(__file__).parent.parent.parent / "data" / "trend_radar.db"

def register(mcp: FastMCP):
    @mcp.resource("trend://latest")
    def get_latest_trends() -> str:
        """Get latest trending entities from trend_radar.db"""
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute("""
            SELECT entity_name, momentum_score, article_count
            FROM trend_signals
            ORDER BY momentum_score DESC
            LIMIT 20
        """)
        results = cursor.fetchall()
        conn.close()
        return json.dumps([
            {"entity": r[0], "momentum": r[1], "articles": r[2]}
            for r in results
        ])

    @mcp.resource("trend://entity/{name}")
    def get_entity_trends(name: str) -> str:
        """Get 7-day trend history for a specific entity"""
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute("""
            SELECT date, momentum_score, article_count, source
            FROM trend_signals
            WHERE entity_name = ?
            AND date > date('now', '-7 days')
            ORDER BY date DESC
        """, (name,))
        results = cursor.fetchall()
        conn.close()
        return json.dumps([
            {"date": r[0], "momentum": r[1], "articles": r[2], "source": r[3]}
            for r in results
        ])
```

## MCP Client Integration

### utils/mcp_client.py

```python
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import json
from loguru import logger

class MCPClient:
    """Client for BriefAI MCP server integration."""

    def __init__(self, server_script: str = "mcp_server/main.py"):
        self.server_params = StdioServerParameters(
            command="python",
            args=[server_script]
        )
        self._session = None
        self._tools_cache = None

    async def connect(self):
        """Establish connection to MCP server."""
        transport = await stdio_client(self.server_params)
        self._session = ClientSession(*transport)
        await self._session.initialize()

        tools_result = await self._session.list_tools()
        self._tools_cache = {t.name: t for t in tools_result.tools}
        logger.info(f"MCP connected. Tools: {list(self._tools_cache.keys())}")

    async def call_tool(self, name: str, arguments: dict) -> str:
        """Execute a tool and return result as string."""
        result = await self._session.call_tool(name, arguments)
        return result.content[0].text

    async def read_resource(self, uri: str) -> str:
        """Read a resource by URI."""
        result = await self._session.read_resource(uri)
        return result.contents[0].text

    async def get_prompt(self, name: str, arguments: dict = None) -> str:
        """Get a prompt template with arguments."""
        result = await self._session.get_prompt(name, arguments or {})
        return result.messages[0].content.text

    def get_tool_descriptions(self) -> str:
        """Format tool descriptions for LLM prompt."""
        if not self._tools_cache:
            return ""
        lines = []
        for name, tool in self._tools_cache.items():
            args = ", ".join(f"{p.name}: {p.type}" for p in tool.inputSchema.get("properties", {}).items())
            lines.append(f"- {name}({args}): {tool.description}")
        return "\n".join(lines)
```

## Tool-Calling Flow (Simulated)

Since Kimi/OpenRouter don't have native function calling, we use structured output:

```python
# agents/mcp_enabled_agent.py
class MCPEnabledAgent:
    """Agent that can use MCP tools via structured output."""

    TOOL_PROMPT = """You have access to the following tools:

{tool_descriptions}

To use a tool, respond with JSON in this exact format:
{{"tool": "tool_name", "args": {{"arg1": "value1"}}}}

If you don't need a tool, respond normally."""

    async def run_with_tools(self, task: str, max_tool_calls: int = 3):
        """Execute task with tool access."""
        messages = [{"role": "user", "content": task}]

        for _ in range(max_tool_calls):
            response = self.llm.chat(
                system_prompt=self.system_prompt + self.TOOL_PROMPT.format(
                    tool_descriptions=self.mcp.get_tool_descriptions()
                ),
                user_message=messages[-1]["content"]
            )

            tool_call = self._parse_tool_call(response)
            if tool_call:
                result = await self.mcp.call_tool(
                    tool_call["tool"],
                    tool_call["args"]
                )
                messages.append({
                    "role": "assistant",
                    "content": f"Tool result: {result}"
                })
            else:
                return response

        return response

    def _parse_tool_call(self, response: str) -> dict | None:
        """Extract tool call JSON from response."""
        try:
            if response.strip().startswith("{"):
                data = json.loads(response.strip())
                if "tool" in data and "args" in data:
                    return data
        except json.JSONDecodeError:
            pass
        return None
```

## Error Handling

```python
# mcp_server/errors.py
class MCPToolError(Exception):
    """Base error for MCP tool failures."""
    def __init__(self, tool: str, message: str, retryable: bool = False):
        self.tool = tool
        self.retryable = retryable
        super().__init__(f"[{tool}] {message}")

class RateLimitedError(MCPToolError):
    """External API rate limited."""
    def __init__(self, tool: str, retry_after: int = 60):
        self.retry_after = retry_after
        super().__init__(tool, f"Rate limited. Retry after {retry_after}s", retryable=True)

class ResourceNotFoundError(MCPToolError):
    """Requested resource doesn't exist."""
    def __init__(self, uri: str):
        super().__init__("resource", f"Not found: {uri}", retryable=False)
```

## Dependencies

Add to `requirements.txt`:
```
fastmcp>=0.1.0
mcp>=1.0.0
```

Add to `.env`:
```
GITHUB_TOKEN=ghp_your_token_here
```

## Implementation Priority

### Phase 1: Core Infrastructure
1. Create `mcp_server/` directory structure
2. Implement `main.py` with FastMCP
3. Add `trend_db.py` resource (most used)
4. Add `github_tools.py` (high impact)
5. Create `utils/mcp_client.py`

### Phase 2: Adversarial Integration
1. Move agent prompts to `prompts/*.md`
2. Update Skeptic to use `get_repo_health` tool
3. Update Hype-Man to use `trend://latest` resource
4. Add `semantic_search` tool for context building

### Phase 3: Pipeline Integration
1. Add parallel scraper execution via tools
2. Implement `fetch_funding` tool
3. Add caching layer with TTL
4. Integrate with finalization_mode.py

## Testing

```python
# tests/test_mcp_server.py
import pytest
from mcp_server.main import mcp

@pytest.mark.asyncio
async def test_trend_resource():
    result = await mcp.read_resource("trend://latest")
    data = json.loads(result)
    assert isinstance(data, list)
    assert len(data) > 0
    assert "entity" in data[0]

@pytest.mark.asyncio
async def test_github_tool():
    result = await mcp.call_tool("get_repo_health", {
        "owner": "anthropics",
        "repo": "anthropic-sdk-python"
    })
    assert "stars" in result
    assert "last_push" in result

@pytest.mark.asyncio
async def test_skeptic_prompt():
    result = await mcp.get_prompt("skeptic", {
        "entity_name": "TestCorp",
        "bull_thesis": "Strong growth"
    })
    assert "TestCorp" in result
```

## Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Pipeline execution time | 5-10 min | <2 min |
| Context retrieval latency | 500ms | <100ms |
| API calls per analysis | 15+ sequential | 5 parallel |
| Agent prompt updates | Code deploy | Config change |
