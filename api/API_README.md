# briefAI Professional API v1

## Bloomberg Terminal for AI Trends

A professional-grade API for AI industry signal analysis, divergence detection, and real-time trend tracking. Designed for quantitative workflows, data pipelines, and investment research.

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Authentication](#authentication)
3. [Rate Limiting](#rate-limiting)
4. [API Endpoints](#api-endpoints)
   - [Health & Info](#health--info)
   - [Entities](#entities)
   - [Signals](#signals)
   - [Divergences](#divergences)
   - [Events](#events)
   - [Export](#export)
   - [Query Builder](#query-builder-premium)
5. [WebSocket Real-Time Feed](#websocket-real-time-feed)
6. [Python SDK](#python-sdk)
7. [Response Formats](#response-formats)
8. [Error Handling](#error-handling)
9. [Best Practices](#best-practices)

---

## Quick Start

### Start the API Server

```bash
cd C:\Users\admin\briefAI
uvicorn api.main:app --reload --port 8000
```

### Access Documentation

- **Swagger UI**: http://localhost:8000/api/docs
- **ReDoc**: http://localhost:8000/api/redoc
- **OpenAPI JSON**: http://localhost:8000/api/openapi.json

### First Request

```bash
# Without authentication (free tier rate limits)
curl http://localhost:8000/api/v1/entities/search?q=openai

# With API key
curl -H "X-API-Key: bai_p_your_key" http://localhost:8000/api/v1/entities/search?q=openai
```

---

## Authentication

### API Key Methods

```bash
# Via Header (recommended)
curl -H "X-API-Key: bai_your_key" http://localhost:8000/api/v1/stats

# Via Query Parameter
curl "http://localhost:8000/api/v1/stats?api_key=bai_your_key"
```

### Key Prefixes

| Prefix | Tier | Description |
|--------|------|-------------|
| `bai_f_` | Free | Basic access |
| `bai_p_` | Pro | Professional features |
| `bai_m_` | Premium | Full access |
| `bai_e_` | Enterprise | Unlimited |

### Generating API Keys (Admin)

```python
from api.auth import get_key_store

store = get_key_store()

# Generate a pro key
key = store.generate_api_key(
    name="my-trading-app",
    tier="pro",
    owner_email="dev@example.com",
    expires_days=365
)
print(f"API Key: {key}")  # Save this - shown only once!

# List all keys
for k in store.list_keys():
    print(f"{k.name}: {k.tier} ({k.total_requests} requests)")
```

---

## Rate Limiting

### Tier Limits

| Tier | Requests/Min | Daily Limit | Burst | Features |
|------|--------------|-------------|-------|----------|
| **Free** | 10 | 1,000 | 5 | Basic export |
| **Pro** | 100 | 50,000 | 20 | Query builder, streaming |
| **Premium** | 500 | 200,000 | 50 | Excel export, priority |
| **Enterprise** | 1,000 | 1,000,000 | 100 | Unlimited, SLA |

### Rate Limit Headers

Every response includes:

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 2025-01-27T12:01:00Z
X-Response-Time: 25.5ms
```

### Handling Rate Limits

```python
import time
import requests

response = requests.get(url, headers={"X-API-Key": key})

if response.status_code == 429:
    retry_after = int(response.headers.get("Retry-After", 60))
    time.sleep(retry_after)
    # Retry request
```

---

## API Endpoints

### Health & Info

```bash
GET /api/health          # Health check
GET /api/info            # API info and endpoints
GET /api/v1/stats        # Data statistics
```

---

### Entities

#### Search Entities

```bash
GET /api/v1/entities/search?q=openai&entity_type=company&limit=20
```

**Parameters:**
- `q` (required): Search query
- `entity_type`: Filter by type (company, technology, person, concept)
- `limit`: Max results (1-100, default: 20)
- `offset`: Pagination offset

**Response:**
```json
{
    "query": "openai",
    "results": [
        {
            "id": "openai",
            "canonical_id": "openai",
            "name": "OpenAI",
            "entity_type": "company",
            "description": "AI research company...",
            "website": "https://openai.com",
            "headquarters": "San Francisco, CA",
            "founded_date": "2015-12-11",
            "sector": "ai_research",
            "industry": "research_lab"
        }
    ],
    "pagination": {
        "total": 1,
        "limit": 20,
        "offset": 0,
        "has_more": false
    }
}
```

#### Get Entity

```bash
GET /api/v1/entities/{entity_id}
```

#### Get Entity Profile

```bash
GET /api/v1/entities/{entity_id}/profile
```

**Response:**
```json
{
    "entity_id": "openai",
    "entity_name": "OpenAI",
    "entity_type": "company",
    "as_of": "2025-01-27T00:00:00Z",
    "technical_score": 85.5,
    "company_score": 78.2,
    "financial_score": 92.1,
    "product_score": 88.0,
    "media_score": 95.3,
    "composite_score": 87.8,
    "momentum_7d": 2.5,
    "momentum_30d": 8.3
}
```

---

### Signals

#### Signal History

```bash
GET /api/v1/signals/{entity_id}/history?category=technical&days=30
```

**Parameters:**
- `entity_id` (required): Entity ID
- `category`: Filter by category (technical, company, financial, product, media)
- `days`: History window (1-365, default: 30)
- `limit`: Max results (1-1000, default: 100)
- `offset`: Pagination offset

#### Signal Categories

```bash
GET /api/v1/signals/categories
```

**Response:**
```json
{
    "categories": [
        {"id": "technical", "name": "Technical", "description": "Developer adoption (GitHub, HuggingFace, Papers)"},
        {"id": "company", "name": "Company Presence", "description": "Market position (Crunchbase, LinkedIn)"},
        {"id": "financial", "name": "Financial", "description": "Capital flows (SEC, Funding rounds)"},
        {"id": "product", "name": "Product Traction", "description": "User demand (ProductHunt, App stores)"},
        {"id": "media", "name": "Media Sentiment", "description": "Public perception (News)"}
    ]
}
```

---

### Divergences

#### Active Divergences

```bash
GET /api/v1/divergences/active?interpretation=opportunity&min_magnitude=30
```

**Parameters:**
- `interpretation`: Filter by type (opportunity, risk, anomaly, neutral)
- `entity_id`: Filter by entity
- `min_magnitude`: Minimum divergence magnitude (0-100)
- `limit`: Max results (1-200, default: 50)

**Response:**
```json
{
    "divergences": [
        {
            "id": "div_123",
            "entity_id": "startup_x",
            "entity_name": "Startup X",
            "divergence_type": "tech_vs_financial",
            "high_signal_category": "technical",
            "high_signal_score": 85.0,
            "low_signal_category": "financial",
            "low_signal_score": 35.0,
            "divergence_magnitude": 50.0,
            "confidence": 0.85,
            "interpretation": "opportunity",
            "interpretation_rationale": "High developer adoption with limited funding suggests undervaluation",
            "detected_at": "2025-01-27T10:00:00Z"
        }
    ],
    "pagination": {...}
}
```

---

### Events

#### Event Timeline

```bash
GET /api/v1/events/{entity_id}?event_type=divergence_detected&days=90
```

---

### Export

#### Quick Export (Streaming)

```bash
# CSV
GET /api/v1/export/signals?format=csv&start_date=2025-01-01&categories=technical

# JSON
GET /api/v1/export/signals?format=json&min_score=50&limit=5000

# JSON Lines (streaming)
GET /api/v1/export/signals/stream?categories=technical,financial

# Parquet
GET /api/v1/export/profiles?format=parquet&min_score=60
```

**Export Formats:**
- `csv` - Comma-separated values
- `json` - JSON with metadata
- `jsonl` - JSON Lines (streaming)
- `parquet` - Apache Parquet (data science)
- `excel` - Formatted Excel workbook (Premium)

#### Async Export Jobs (Large Datasets)

```bash
# Create job
POST /api/v1/export/jobs
{
    "export_type": "signals",
    "format": "parquet",
    "start_date": "2024-01-01",
    "end_date": "2025-01-01",
    "categories": ["technical", "financial"],
    "min_score": 50,
    "compress": true
}

# Check status
GET /api/v1/export/jobs/{job_id}

# Download when complete
GET /api/v1/export/jobs/{job_id}/download
```

#### Paginated Export

```bash
POST /api/v1/export/paginated
{
    "export_type": "signals",
    "page": 1,
    "page_size": 5000,
    "format": "jsonl",
    "order_by": "created_at",
    "order_desc": true
}
```

#### Excel Export (Premium)

```bash
POST /api/v1/export/excel?export_types=signals,entities,profiles&include_charts=true
```

---

### Query Builder (Premium)

#### SQL-like Queries

```bash
POST /api/v1/query?query=SELECT * FROM signals WHERE category='technical' AND score >= 70 ORDER BY score DESC LIMIT 100
```

#### Boolean Queries

```bash
POST /api/v1/query/boolean
{
    "table": "signals",
    "select": ["entity_id", "entity_name", "score", "category"],
    "and_conditions": [
        {"field": "category", "operator": "=", "value": "technical"},
        {"field": "score", "operator": ">=", "value": 70}
    ],
    "or_conditions": [
        {"field": "entity_name", "operator": "LIKE", "value": "%OpenAI%"},
        {"field": "entity_name", "operator": "LIKE", "value": "%Anthropic%"}
    ],
    "date_from": "2025-01-01",
    "min_confidence": 0.8,
    "sector": "ai_research",
    "order_by": "score",
    "order_desc": true,
    "limit": 50
}
```

**Available Tables:**
- `signals` - Signal scores
- `entities` - Entity master data
- `profiles` - Signal profiles
- `divergences` - Divergence alerts
- `observations` - Raw observations
- `scores` - Computed scores

**Operators:**
- `=`, `!=`, `>`, `>=`, `<`, `<=`
- `LIKE`, `ILIKE` (case-insensitive)
- `IN`, `NOT IN`
- `BETWEEN`
- `IS NULL`, `IS NOT NULL`

---

## WebSocket Real-Time Feed

### Connection

```javascript
const ws = new WebSocket('ws://localhost:8000/ws?api_key=your_key');

// For reconnection
const ws = new WebSocket('ws://localhost:8000/ws?api_key=your_key&reconnect_id=prev_connection_id');
```

### Subscriptions

```javascript
// Subscribe to specific entity
ws.send(JSON.stringify({
    type: 'subscribe',
    subscription_type: 'entity',
    target: 'openai'
}));

// Subscribe to signal category
ws.send(JSON.stringify({
    type: 'subscribe',
    subscription_type: 'category',
    target: 'technical'
}));

// Subscribe to divergence alerts
ws.send(JSON.stringify({
    type: 'subscribe',
    subscription_type: 'divergence',
    min_severity: 'high'  // low, medium, high, critical
}));

// Subscribe to all updates
ws.send(JSON.stringify({
    type: 'subscribe',
    subscription_type: 'all'
}));

// Unsubscribe
ws.send(JSON.stringify({
    type: 'unsubscribe',
    subscription_type: 'entity',
    target: 'openai'
}));
```

### Message Types

**Server → Client:**

```javascript
// Signal update
{
    "type": "signal_update",
    "entity_id": "openai",
    "category": "technical",
    "data": {
        "score": 85.5,
        "percentile": 92,
        "delta_7d": 2.3
    },
    "timestamp": "2025-01-27T12:00:00Z"
}

// Divergence alert
{
    "type": "divergence_alert",
    "entity_id": "startup_x",
    "entity_name": "Startup X",
    "severity": "high",
    "data": {
        "interpretation": "opportunity",
        "magnitude": 45.0,
        "confidence": 0.88
    },
    "timestamp": "2025-01-27T12:00:00Z"
}

// Heartbeat (every 30s)
{
    "type": "heartbeat",
    "timestamp": "2025-01-27T12:00:00Z",
    "server_time": 1737979200000
}
```

### Batching (Premium)

```javascript
// Enable batching for high throughput
ws.send(JSON.stringify({
    type: 'configure',
    batch_enabled: true,
    batch_size: 10,
    batch_interval_ms: 1000
}));

// Batch message
{
    "type": "batch",
    "messages": [...],
    "count": 10,
    "timestamp": "2025-01-27T12:00:00Z"
}
```

### Keepalive

```javascript
// Respond to heartbeats with ping
ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.type === 'heartbeat') {
        ws.send(JSON.stringify({type: 'ping'}));
    }
};
```

---

## Python SDK

### Installation

```bash
pip install requests websocket-client
```

### Basic Usage

```python
from api.sdk.briefai_client import BriefAIClient, QueryBuilder

# Initialize client
client = BriefAIClient(
    api_key="bai_p_your_key",
    base_url="http://localhost:8000",
    retry_on_rate_limit=True
)

# Search entities
entities, pagination = client.entities.search("openai", entity_type="company")

# Get signal history
signals, _ = client.signals.history("openai", category="technical", days=30)

# Get divergences
divergences, _ = client.divergences.active(
    interpretation="opportunity",
    min_magnitude=30
)

# Export to CSV
csv_data = client.export.signals(
    format="csv",
    start_date="2025-01-01",
    categories=["technical", "financial"]
)

# Query builder (Premium)
result = client.query.execute(
    QueryBuilder("signals")
        .select("entity_id", "score", "category")
        .where("score", ">=", 70)
        .order_by("score", desc=True)
        .limit(100)
        .build()
)

# Real-time streaming
for update in client.stream.subscribe(entities=["openai", "anthropic"]):
    print(f"{update['type']}: {update.get('entity_id')}")
```

### Async Client

```python
import asyncio
from api.sdk.briefai_client import AsyncBriefAIClient

async def main():
    async with AsyncBriefAIClient(api_key="your_key") as client:
        entities = await client.search_entities("openai")
        signals = await client.get_signal_history("openai", category="technical")
        print(f"Found {len(entities)} entities")

asyncio.run(main())
```

---

## Response Formats

### Pagination

```json
{
    "data": [...],
    "pagination": {
        "total": 150,
        "limit": 50,
        "offset": 0,
        "has_more": true
    }
}
```

### Error Response

```json
{
    "detail": {
        "error": "rate_limit_exceeded",
        "message": "Rate limit exceeded. Limit: 100/min for Professional tier.",
        "tier": "pro",
        "upgrade_url": "/api/v1/account/upgrade"
    }
}
```

---

## Error Handling

| Code | Error | Description |
|------|-------|-------------|
| 400 | `validation_error` | Invalid request parameters |
| 401 | `authentication_required` | Missing API key |
| 401 | `invalid_api_key` | Invalid or expired key |
| 403 | `insufficient_tier` | Feature requires higher tier |
| 403 | `feature_not_available` | Feature disabled for tier |
| 404 | `not_found` | Resource not found |
| 429 | `rate_limit_exceeded` | Too many requests |
| 500 | `internal_error` | Server error |

---

## Best Practices

### 1. Use Appropriate Tier

Start with Free tier for development, upgrade for production.

### 2. Handle Rate Limits

```python
import time
from api.sdk.briefai_client import BriefAIClient, RateLimitError

client = BriefAIClient(api_key="key", retry_on_rate_limit=True)

try:
    result = client.signals.history("openai")
except RateLimitError as e:
    print(f"Rate limited. Retry in {e.retry_after}s")
```

### 3. Use Streaming for Large Data

```python
# Instead of this (loads all into memory):
data = client.export.signals(limit=1000000)

# Use streaming:
for line in client.export.signals_stream():
    process(line)

# Or async jobs:
job = client.export.create_job(export_type="signals", format="parquet")
client.export.wait_for_job(job.job_id)
```

### 4. Subscribe Selectively

```javascript
// Don't do this:
ws.send({type: 'subscribe', subscription_type: 'all'});

// Do this:
ws.send({type: 'subscribe', subscription_type: 'entity', target: 'openai'});
ws.send({type: 'subscribe', subscription_type: 'divergence', min_severity: 'high'});
```

### 5. Use Query Builder for Complex Queries

```python
# Instead of multiple API calls, use query builder:
result = client.query.execute(
    QueryBuilder("signals")
        .where("category", "IN", ["technical", "financial"])
        .where("score", ">=", 70)
        .date_range("2025-01-01", "2025-06-01")
        .min_confidence(0.8)
        .limit(1000)
        .build()
)
```

---

## Architecture

```
api/
├── main.py              # FastAPI app, middleware
├── auth.py              # API key auth, rate limiting
├── query_builder.py     # SQL-like query parser
├── websocket.py         # Real-time WebSocket feeds
├── API_README.md        # This documentation
├── requirements.txt     # Dependencies
├── routers/
│   ├── v1.py            # Main v1 endpoints
│   ├── export.py        # Bulk export
│   └── ...              # Other routers
└── sdk/
    ├── briefai_client.py    # Python SDK
    └── examples/            # Usage examples
```

---

## Support

- **API Docs**: http://localhost:8000/api/docs
- **SDK Examples**: `api/sdk/examples/`
- **Issues**: Contact your account manager

---

*briefAI API v1.0.0 - Professional AI Industry Intelligence*
