# Trend Radar: VC Portfolio Monitoring System

**Date**: 2025-01-05
**Status**: Design Complete
**Purpose**: Detect emerging AI startup signals by monitoring VC/accelerator portfolio pages

---

## Overview

A separate Data API for querying VC/startup signals, consumed by internal team via scripts and notebooks. On-demand refresh with three intensity tiers (lite/standard/deep).

---

## Data Model

```
┌─────────────────┐      ┌─────────────────┐
│     Source      │      │    Company      │
├─────────────────┤      ├─────────────────┤
│ id              │      │ id              │
│ name            │      │ name            │
│ type            │      │ normalized_name │
│ url             │      │ website         │
│ tier (1/2/3)    │      │ description     │
│ parse_strategy  │      │ founded_year    │
│ frequency       │      │ country         │
│ enabled         │      │ rising_score    │
│ requires_js     │      │ first_seen_global│
│ last_fetched    │      │ last_seen_global │
└────────┬────────┘      └────────┬────────┘
         │                        │
         │    ┌───────────────┐   │
         └───►│  Observation  │◄──┘
              ├───────────────┤
              │ source_id     │
              │ company_id    │
              │ first_seen    │
              │ last_seen     │
              │ stage         │
              │ industry_tags │
              │ batch (YC)    │
              │ raw_data      │
              └───────────────┘
```

**Key fields:**
- `normalized_name`: Enables deduplication across sources
- `first_seen`: The "new investment" signal - when company first appeared in a source
- `rising_score`: Precomputed metric for "next-up" ranking

---

## Source Configuration

Located at `config/vc_sources.json`:

```json
{
  "default_tier": "standard",
  "tiers": {
    "lite": {
      "description": "Quick scan - highest signal sources",
      "sources": [
        {
          "id": "yc_directory",
          "name": "Y Combinator",
          "type": "accelerator",
          "url": "https://www.ycombinator.com/companies",
          "filter_url": "https://www.ycombinator.com/companies?tags=AI",
          "parse_strategy": "yc_grid",
          "frequency": "daily",
          "enabled": true,
          "requires_js": true,
          "notes": "Use AI tag filter; respects robots.txt"
        }
      ]
    },
    "standard": {
      "inherits": "lite",
      "sources": [ /* 15-20 more VCs + accelerators */ ]
    },
    "deep": {
      "inherits": "standard",
      "sources": [ /* 30-50 more + curated lists */ ]
    }
  }
}
```

**Tier inheritance**: `standard` includes all of `lite` plus more sources. Loader dedupes by `id`.

---

## Parser Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Crawler    │────►│    Parser    │────►│  Normalizer  │
│              │     │              │     │              │
│ - Pagination │     │ - HTML only  │     │ - Dedup      │
│ - JS render  │     │ - Per-card   │     │ - Merge      │
│ - Retries    │     │   error trap │     │              │
└──────────────┘     └──────────────┘     └──────────────┘
```

**Parser registry pattern:**

```python
PARSER_REGISTRY = {
    "yc_grid": parse_yc_grid,
    "a16z_cards": parse_a16z_cards,
    "sequoia_list": parse_sequoia_list,
    "generic_table": parse_generic_table,
}
```

**Parser contract:**
- Input: `(html: str, source_config: dict)`
- Output: `List[dict]` with normalized company fields
- Error handling: Per-card try/except, log and continue
- Pure functions: No network calls, crawler handles pagination

---

## API Design

### Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /companies` | List/search with pagination & filters |
| `GET /companies/{id}` | Single company with full observations |
| `GET /companies/new` | Newly detected companies (core signal) |
| `POST /companies/search` | Semantic search (for LLM agent) |
| `GET /sources` | List configured sources |
| `POST /refresh` | Trigger on-demand refresh (async) |
| `GET /jobs/{job_id}` | Check refresh job status |
| `GET /stats` | Trend summaries |
| `GET /clusters` | Company clusters by theme |

### Response Shapes

**`GET /companies`**

```json
{
  "count": 247,
  "limit": 50,
  "offset": 0,
  "next_offset": 50,
  "companies": [
    {
      "id": "abc123",
      "name": "Acme AI",
      "normalized_name": "acme-ai",
      "website": "https://acme.ai",
      "description": "AI-powered widget optimization",
      "founded_year": 2024,
      "country": "US",
      "source_count": 2,
      "first_seen_global": "2025-01-03",
      "last_seen_global": "2025-01-05",
      "rising_score": 78,
      "observations": [
        {
          "source": "yc_directory",
          "source_name": "Y Combinator",
          "first_seen": "2025-01-03",
          "batch": "W25",
          "industry_tags": ["AI", "DevTools"]
        }
      ]
    }
  ]
}
```

**`GET /companies/new`**

```json
{
  "count": 12,
  "time_window": {"from": "2024-12-29", "to": "2025-01-05"},
  "companies": [
    {
      "id": "abc123",
      "name": "Acme AI",
      "first_seen_global": "2025-01-05",
      "source_count": 2,
      "rising_score": 78,
      "new_sources": [
        {"source": "a16z_portfolio", "first_seen": "2025-01-05"}
      ]
    }
  ]
}
```

**`GET /stats`**

```json
{
  "time_window": {"from": "2024-12-05", "to": "2025-01-05"},
  "totals": {
    "new_companies": 120,
    "new_observations": 300
  },
  "by_sector": [
    {"sector": "AI infra", "new_companies": 30},
    {"sector": "Agents", "new_companies": 20}
  ],
  "by_stage": [
    {"stage": "Seed", "new_companies": 50},
    {"stage": "Series A", "new_companies": 25}
  ]
}
```

**`POST /refresh`**

```json
{
  "status": "accepted",
  "job_id": "refresh_2025-01-05T10:30:00Z_lite",
  "sources_queued": 8
}
```

---

## Project Structure

```
briefAI/
├── app.py                          # Existing Streamlit UI
├── main.py                         # Unified CLI (briefings + trend radar)
│
├── trend_radar/                    # NEW: VC Trend Radar module
│   ├── __init__.py
│   ├── api.py                      # FastAPI app
│   ├── client.py                   # Internal client for Streamlit
│   ├── models.py                   # SQLAlchemy + Pydantic, env-based DB URL
│   ├── crawler.py                  # Fetcher + pagination
│   ├── normalizer.py               # Dedup + company merging
│   ├── jobs.py                     # Refresh job runner
│   └── parsers/
│       ├── __init__.py             # Parser registry
│       ├── yc_grid.py
│       ├── a16z_cards.py
│       └── generic.py
│
├── utils/
│   ├── config_loader.py            # NEW: Shared config loading
│   ├── cache_manager.py            # Existing (reuse)
│   └── logger.py                   # Existing (reuse)
│
├── config/
│   └── vc_sources.json             # NEW: VC portfolio sources
│
├── data/
│   └── trend_radar.db              # SQLite (dev), Postgres (prod)
│
└── tests/
    ├── fixtures/
    │   ├── yc_grid_page1.html
    │   └── a16z_cards.html
    └── test_vc_parsers.py
```

---

## Integration Details

### Config Loader (`utils/config_loader.py`)

```python
import json
from pathlib import Path

CONFIG_DIR = Path(__file__).parent.parent / "config"

def load_vc_sources(path: str = None) -> dict:
    path = path or CONFIG_DIR / "vc_sources.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)
```

### DB Abstraction (`trend_radar/models.py`)

```python
import os
from sqlalchemy import create_engine

DATABASE_URL = os.getenv(
    "TREND_RADAR_DB_URL",
    "sqlite:///data/trend_radar.db"
)

engine = create_engine(DATABASE_URL)
```

### Internal Client (`trend_radar/client.py`)

```python
import os
import requests

BASE_URL = os.getenv("TREND_RADAR_API_URL", "http://localhost:8100")

def list_new_companies(days: int = 7, source_type: str = None) -> list:
    params = {"days": days}
    if source_type:
        params["source_type"] = source_type
    resp = requests.get(f"{BASE_URL}/companies/new", params=params)
    resp.raise_for_status()
    return resp.json()["companies"]

def trigger_refresh(tier: str = "standard") -> dict:
    resp = requests.post(f"{BASE_URL}/refresh", params={"tier": tier})
    resp.raise_for_status()
    return resp.json()
```

### CLI Commands (`main.py`)

```bash
# Start the Trend Radar API
python main.py --trend-radar-api

# Run a one-off refresh
python main.py --trend-radar-refresh --tier lite
```

---

## Implementation Phases

### Phase 1: Foundation (MVP)
- Data models (Company, Source, Observation)
- Config loader with tier inheritance
- 3 parsers (YC, a16z, Sequoia) - lite tier only
- Basic crawler (no JS rendering yet)
- SQLite storage
- CLI refresh command

### Phase 2: API Layer
- FastAPI endpoints (`/companies`, `/companies/new`, `/sources`)
- Pagination and filtering
- Internal client for Streamlit
- `/refresh` endpoint with job tracking

### Phase 3: Scale to Standard Tier
- 15-20 more parsers
- Playwright integration for JS-heavy sites
- Normalizer with dedup logic
- `rising_score` computation

### Phase 4: Deep Tier + Analytics
- Remaining 30-50 sources
- `/stats` endpoint
- `/clusters` endpoint
- Semantic search with embeddings

---

## Starter Sources (Phase 1 - Lite Tier)

| Source | Type | Parse Strategy |
|--------|------|----------------|
| Y Combinator | accelerator | `yc_grid` |
| a16z | vc_portfolio | `a16z_cards` |
| Sequoia | vc_portfolio | `sequoia_list` |
| Lightspeed | vc_portfolio | `lightspeed_table` |
| Index Ventures | vc_portfolio | `index_grid` |

---

## Source References

### Official VC Portfolios
- [a16z Portfolio](https://a16z.com/portfolio/)
- [Sequoia Companies](https://www.sequoiacap.com/our-companies/)
- [Lightspeed Companies](https://lsvp.com/companies/)
- [Index Ventures Companies](https://www.indexventures.com/companies/)
- [Greylock Portfolio](https://greylock.com/portfolio/)
- [Bessemer Portfolio](https://www.bvp.com/companies)
- [HongShan (红杉中国)](https://www.hongshan.com/portfolio)

### Accelerators
- [YC Startup Directory](https://www.ycombinator.com/companies)
- [YC AI Startups](https://www.ycombinator.com/companies?tags=AI)
- [a16z Speedrun](https://speedrun.a16z.com/companies)

### Databases & Cross-Validation
- [Dealroom.co](https://dealroom.co/)
- [CB Insights](https://www.cbinsights.com/)
- [RootData](https://www.rootdata.com/)

### Curated Lists
- [Awesome AI Market Maps (GitHub)](https://github.com/...)
- CB Insights AI 100
- Sequoia AI 50
- Forbes AI 50
