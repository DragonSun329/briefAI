# briefAI Custom Screener System

## Overview

The Custom Screener system allows users to build powerful filters for finding entities that match specific criteria. It's designed to be intuitive for non-technical users while powerful enough for quantitative analysts.

## Features

- **Visual Filter Builder**: Drag-and-drop interface in Streamlit
- **DSL Query Language**: Write queries like SQL WHERE clauses
- **Preset Screeners**: Built-in screeners for common use cases
- **Save/Load**: Persist custom screeners for reuse
- **Export**: Download results as CSV or JSON
- **API Access**: REST API for programmatic access

## Components

### 1. Screener Engine (`utils/screener_engine.py`)

The core filtering engine that evaluates entities against criteria.

```python
from utils.screener_engine import ScreenerEngine, Criterion, FilterOperator, CriterionType

engine = ScreenerEngine()

# Simple filter
criteria = [
    Criterion(field="media_score", operator=FilterOperator.GT, value=70),
    Criterion(field="momentum_7d", operator=FilterOperator.GT, value=10)
]
result = engine.screen(criteria)

# Field comparison
criteria = [
    Criterion(
        field="media_score",
        operator=FilterOperator.FIELD_GT,
        compare_field="technical_score",
        criterion_type=CriterionType.COMPARISON
    )
]
```

### 2. Query DSL (`utils/screener_dsl.py`)

Simple query language for expressing filters:

```python
from utils.screener_dsl import parse_query, quick_screen

# Parse DSL to criteria
group = parse_query("media_score > 70 AND momentum_7d > 10%")

# Quick screen
results = quick_screen("media_score > technical_score AND region = 'us'")
```

#### DSL Syntax

```
# Comparison operators
media_score > 7
technical_score >= 50
momentum_7d < -5
composite_score = 100

# Boolean operators
has_divergence = true
has_funding_signal = false

# IN operator
sector IN ("ai-foundation", "ai-infrastructure")
region NOT IN ("russia", "iran")

# Field comparison
media_score > technical_score

# Date filters
last_signal_date > 7 days ago

# Logical operators
media_score > 70 AND momentum_7d > 10
region = "us" OR region = "china"

# Grouping
(media_score > 80 AND region = "us") OR (momentum_7d > 40)
```

### 3. Preset Screeners (`config/preset_screeners.json`)

Built-in screeners:

| Name | Description |
|------|-------------|
| Hot AI Startups | High media + strong momentum + startup type |
| Undervalued Tech | High technical + low media (divergence) |
| Momentum Leaders | Top entities by 7-day momentum |
| Risk Alerts | High volatility + negative momentum |
| China AI Watch | Chinese entities with recent signals |
| Funding Signals | Strong financial signals |
| Product Traction Stars | Strong product traction |
| Divergence Opportunities | Active signal divergences |
| Media Darlings | High media but lower technicals |
| Balanced All-Stars | Strong across multiple signals |

### 4. Streamlit UI (`modules/screener_ui.py`)

Visual interface for building and running screeners:

```python
from modules.screener_ui import render_screener_dashboard

# In your Streamlit app
render_screener_dashboard()
```

### 5. REST API (`api/routers/screener.py`)

API endpoints for programmatic access:

```bash
# Run a screener with criteria
POST /api/v1/screener/run
{
    "criteria": [
        {"field": "media_score", "operator": ">", "value": 70}
    ],
    "limit": 50
}

# Run a DSL query
POST /api/v1/screener/query
{
    "query": "media_score > 70 AND momentum_7d > 10%"
}

# List presets
GET /api/v1/screener/presets

# Run a preset
POST /api/v1/screener/presets/hot-ai-startups/run

# Save custom screener
POST /api/v1/screener/save
{
    "name": "my-screener",
    "criteria": [...],
    "description": "My custom filter"
}

# Get available fields
GET /api/v1/screener/fields
```

## Screenable Fields

### Score Fields (0-100)
- `technical_score` - Technical/research signal strength
- `company_score` - Company fundamentals strength
- `financial_score` - Financial/funding signal strength
- `product_score` - Product traction signal strength
- `media_score` - Media coverage signal strength
- `composite_score` - Weighted composite of all signals

### Momentum Fields (percentage)
- `momentum_7d` - 7-day score momentum
- `momentum_30d` - 30-day score momentum
- `buzz_momentum` - Mention velocity change
- `funding_momentum` - Funding acceleration

### Category Fields
- `entity_type` - company, technology, concept, person
- `sector` - Business sector
- `region` - Geographic region

### Signal Flags
- `has_divergence` - Active divergence detected
- `divergence_strength` - Divergence magnitude (0-1)
- `has_funding_signal` - Recent funding activity
- `has_product_launch` - Recent product launch
- `has_partnership` - Recent partnership

### Date Fields
- `last_signal_date` - Most recent signal
- `last_funding_date` - Most recent funding

### Activity Fields
- `signal_count_7d` - Signals in past 7 days
- `signal_count_30d` - Signals in past 30 days

## Examples

### Find Undervalued Tech

```python
# Using DSL
results = quick_screen("""
    technical_score >= 65 
    AND media_score < 40 
    AND technical_score > media_score
""")

# Using API
POST /api/v1/screener/query
{
    "query": "technical_score >= 65 AND media_score < 40 AND technical_score > media_score",
    "sort_by": "technical_score",
    "sort_order": "desc"
}
```

### China AI Momentum

```python
results = quick_screen("""
    region IN ("china", "cn") 
    AND momentum_7d > 20
    AND composite_score > 40
""")
```

### Divergence Arbitrage

```python
results = quick_screen("""
    has_divergence = true 
    AND divergence_strength > 0.6
    AND composite_score > 30
""")
```

### Media Hype Warning

```python
results = quick_screen("""
    media_score > 80 
    AND media_score > technical_score
    AND technical_score < 50
""")
```

## QueryBuilder API

For programmatic query building:

```python
from utils.screener_dsl import QueryBuilder

query = (QueryBuilder()
    .where("media_score", ">", 70)
    .and_where("momentum_7d", ">", 10)
    .field_gt("media_score", "technical_score")
    .in_list("sector", ["ai-foundation", "ai-infrastructure"])
    .build())

engine = ScreenerEngine()
result = engine.screen_with_group(query)
```

## SQL Generation

Convert DSL to SQL WHERE clauses:

```python
from utils.screener_dsl import to_sql_where

sql = to_sql_where("media_score > 70 AND sector = 'ai'", table_alias="e")
# Result: "(e.media_score > 70 AND e.sector = 'ai')"
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    User Interfaces                       │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │ Streamlit UI│  │  REST API   │  │ Python SDK    │  │
│  └──────┬──────┘  └──────┬───────┘  └───────┬───────┘  │
└─────────┼────────────────┼──────────────────┼──────────┘
          │                │                  │
          ▼                ▼                  ▼
┌─────────────────────────────────────────────────────────┐
│                    DSL Parser                            │
│  ┌─────────┐    ┌──────────┐    ┌──────────────────┐   │
│  │ Lexer   │───▶│ Parser   │───▶│ CriteriaGroup    │   │
│  └─────────┘    └──────────┘    └──────────────────┘   │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│                  Screener Engine                         │
│  ┌────────────────┐  ┌───────────────┐  ┌───────────┐  │
│  │ Entity Loader  │  │ Filter Engine │  │ Sorter    │  │
│  └────────┬───────┘  └───────┬───────┘  └─────┬─────┘  │
│           │                  │                │        │
│           ▼                  ▼                ▼        │
│  ┌─────────────────────────────────────────────────┐   │
│  │              ScreenerResult                     │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

## Testing

```bash
# Run screener tests
python -m pytest tests/test_screener.py -v

# Run specific test class
python -m pytest tests/test_screener.py::TestScreenerEngine -v
```
