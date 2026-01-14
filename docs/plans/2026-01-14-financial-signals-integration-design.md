# Financial Signals Integration Design

**Date**: 2026-01-14
**Status**: Approved
**Author**: Claude + User collaboration

## Overview

Integrate FinceptTerminal-style financial data sources into BriefAI's bucket scoring pipeline. This adds three new signal channels while preserving signal independence.

## Key Principle: Signal Separation

Each signal type remains a distinct channel. Divergences between channels are features, not bugs.

**New signals:**
- **PMS** (Public Market Signal) - from Yahoo Finance equities
- **CSS** (Crypto Sentiment Signal) - from AI tokens via Kraken
- **MRS** (Macro Regime Signal) - from DBnomics economic indicators

**Critical**: These do NOT merge into CCS. CCS remains VC/Crunchbase/private capital only.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Daily Pipeline                                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              financial_signals.py (NEW)                          │
│                                                                  │
│  Fetchers (raw data):                                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ Yahoo Finance│  │   DBnomics   │  │    Kraken    │           │
│  │  ~30 tickers │  │ ~10 series   │  │  ~8 tokens   │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
│                                                                  │
│  Output: financial_signals_YYYY-MM-DD.json                       │
│  ├── raw: {tickers: [...], tokens: [...], macro: [...]}         │
│  ├── bucket_signals: {bucket_id: {pms, css}}                    │
│  └── macro: {mrs: -0.4, indicators: {...}}                      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              bucket_scorers.py (MODIFIED)                        │
│                                                                  │
│  BucketProfile now has VECTOR output:                           │
│  {                                                               │
│    "bucket_id": "agent-orchestration",                          │
│    "signals": {                                                  │
│      "tms": 72,      // Technical Momentum (unchanged)          │
│      "ccs": 65,      // Capital Conviction (VC/CB only)         │
│      "eis": 45,      // Enterprise Institutional (unchanged)    │
│      "nas": 58,      // Narrative Attention (unchanged)         │
│      "pms": 71,      // NEW: Public Market Signal               │
│      "css": 88       // NEW: Crypto Sentiment Signal            │
│    },                                                            │
│    "context": {                                                  │
│      "mrs": -0.4     // Macro Regime Signal (global)            │
│    }                                                             │
│  }                                                               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              Divergence Detection / Alerts                       │
│                                                                  │
│  Examples:                                                       │
│  - CSS ↑↑ while TMS/CCS flat → "pump risk, retail hype"         │
│  - PMS ↓↓ while CCS ↑ → "smart money diverging from market"     │
│  - MRS negative + CCS rising → "conviction despite headwinds"   │
└─────────────────────────────────────────────────────────────────┘
```

**MRS Usage**: Never multiplies scores. It adjusts:
- Alert thresholds (require stronger evidence in risk-off)
- Confidence bands (wider uncertainty in volatile macro)

## Data Mappings

### Ticker-to-Bucket (Equities → PMS)

```json
{
  "ai-chips": ["NVDA", "AMD", "INTC", "AVGO", "MRVL"],
  "ai-infrastructure": ["SMCI", "ANET", "VRT", "DELL"],
  "llm-foundation": ["GOOGL", "META", "MSFT"],
  "ai-enterprise": ["CRM", "NOW", "WDAY", "PLTR"],
  "code-ai": ["MSFT", "ADBE", "NOW"],
  "ai-healthcare": ["VEEV", "ISRG", "DXCM"],
  "ai-finance": ["COIN", "SQ", "PYPL"],
  "autonomous-vehicles": ["TSLA", "GOOGL", "UBER", "GM"],
  "robotics-embodied": ["ISRG", "ROK", "ABB"],
  "vision-multimodal": ["ADBE", "SNAP", "U"],
  "ai-security": ["CRWD", "PANW", "ZS", "S"],
  "ai-data": ["SNOW", "MDB", "DDOG"]
}
```

~30 unique tickers. Equal weight within bucket.

### Token-to-Bucket (Crypto → CSS)

```json
{
  "FET": {"primary": "agent-orchestration", "secondary": ["ai-infrastructure"], "confidence": 0.8},
  "AGIX": {"primary": "ai-enterprise", "secondary": ["llm-foundation"], "confidence": 0.7},
  "OCEAN": {"primary": "ai-data", "secondary": [], "confidence": 0.8},
  "TAO": {"primary": "ai-infrastructure", "secondary": ["llm-foundation"], "confidence": 0.7},
  "RNDR": {"primary": "ai-infrastructure", "secondary": ["vision-multimodal"], "confidence": 0.8},
  "ARKM": {"primary": "ai-data", "secondary": ["ai-security"], "confidence": 0.6},
  "WLD": {"primary": "ai-consumer-assistants", "secondary": [], "confidence": 0.5},
  "AKT": {"primary": "ai-infrastructure", "secondary": [], "confidence": 0.7}
}
```

Tokens map to primary bucket + optional secondaries. Confidence reflects mapping clarity.

### Macro Indicators (DBnomics → MRS)

| Series ID | Use |
|-----------|-----|
| FRED/VIXCLS | Volatility (risk appetite) |
| FRED/FEDFUNDS | Interest rate environment |
| FRED/UNRATE | Employment health |
| OECD/MEI_CLI/USA | Leading economic indicator |
| BIS/CBS/Q.S.5A.A.A.A.TO1.A | Cross-border credit flows |

MRS = composite z-score, normalized to [-1, +1].

## Output Schema

```json
{
  "schema": {
    "name": "financial_signals",
    "version": "1.0",
    "compatible_with": ["1.0"]
  },
  "date": "2026-01-14",
  "generated_at": "2026-01-14T06:00:00Z",

  "quality": {
    "overall_status": "ok",
    "warnings": []
  },

  "sources": {
    "yahoo_finance": {"status": "ok", "tickers_fetched": 28, "tickers_expected": 30},
    "dbnomics": {"status": "ok", "series_fetched": 5, "series_expected": 5},
    "kraken": {"status": "degraded", "tokens_fetched": 7, "tokens_expected": 8, "note": "WLD unavailable"}
  },

  "methods": {
    "pms": {
      "window_days": [1, 7, 30],
      "weighting": "equal",
      "aggregation": "bucket_equal_weight",
      "transform": "percentile"
    },
    "css": {
      "window_days": [1, 7, 30],
      "weighting": "equal",
      "aggregation": "confidence_weighted",
      "transform": "percentile"
    },
    "mrs": {
      "components": ["volatility", "rates", "employment", "credit", "cli"],
      "transform": "zscore_composite",
      "normalize": "clip_-1_1"
    }
  },

  "raw": {
    "equities": [
      {
        "ticker": "NVDA",
        "asof": "2026-01-13T21:00:00Z",
        "price": 892.50,
        "change_1d_pct": 2.3,
        "change_7d_pct": 8.1,
        "change_30d_pct": 15.4,
        "volume": 45000000,
        "volume_avg_30d": 38000000,
        "volume_ratio": 1.18,
        "market_cap_b": 2210
      }
    ],
    "tokens": [
      {
        "symbol": "FET",
        "asof": "2026-01-14T05:55:00Z",
        "price_usd": 2.15,
        "change_1d_pct": 5.2,
        "change_7d_pct": 12.8,
        "change_30d_pct": -8.4,
        "volume_24h_usd": 180000000
      }
    ],
    "macro": [
      {"series_id": "FRED/VIXCLS", "asof": "2026-01-13T00:00:00Z", "value": 18.5, "z_score": 0.3},
      {"series_id": "FRED/FEDFUNDS", "asof": "2026-01-13T00:00:00Z", "value": 5.25, "z_score": 1.2},
      {"series_id": "FRED/UNRATE", "asof": "2026-01-10T00:00:00Z", "value": 3.9, "z_score": -0.4}
    ]
  },

  "macro_regime": {
    "mrs": -0.2,
    "interpretation": "mildly_risk_off",
    "components": {
      "volatility": {"z_score": 0.3, "weight": 0.25},
      "rates": {"z_score": 1.2, "weight": 0.25},
      "employment": {"z_score": -0.4, "weight": 0.20},
      "credit": {"z_score": null, "weight": 0.15, "note": "data pending"},
      "cli": {"z_score": -0.1, "weight": 0.15}
    }
  },

  "bucket_signals": {
    "ai-chips": {
      "pms": 78,
      "pms_coverage": {"tickers_present": 5, "tickers_total": 6, "missing": ["MRVL"]},
      "pms_contributors": [
        {"ticker": "NVDA", "change_7d_pct": 8.1, "weight": 0.2, "contribution": 16.2},
        {"ticker": "AMD", "change_7d_pct": 5.2, "weight": 0.2, "contribution": 10.4},
        {"ticker": "AVGO", "change_7d_pct": 3.8, "weight": 0.2, "contribution": 7.6}
      ],
      "pms_contributors_text": ["NVDA +8.1%", "AMD +5.2%", "AVGO +3.8%"],
      "css": null,
      "css_coverage": null
    },
    "agent-orchestration": {
      "pms": 62,
      "pms_coverage": {"tickers_present": 1, "tickers_total": 1, "missing": []},
      "pms_contributors": [
        {"ticker": "MSFT", "change_7d_pct": 2.1, "weight": 1.0, "contribution": 2.1}
      ],
      "pms_contributors_text": ["MSFT +2.1%"],
      "css": 85,
      "css_coverage": {"tokens_present": 1, "tokens_total": 1, "missing": []},
      "css_contributors": [
        {"symbol": "FET", "change_7d_pct": 12.8, "weight": 0.8, "contribution": 10.2}
      ],
      "css_contributors_text": ["FET +12.8%"]
    }
  }
}
```

## Integration Details

### Internal Client (trend_radar/client.py)

```python
"""Thin wrapper for Streamlit to call Trend Radar API."""

import os
import requests
from typing import List, Optional, Dict, Any

TREND_RADAR_URL = os.getenv("TREND_RADAR_URL", "http://localhost:8100")

def get_bucket_signals(bucket_id: str) -> Dict[str, Any]:
    resp = requests.get(f"{TREND_RADAR_URL}/buckets/{bucket_id}/signals")
    resp.raise_for_status()
    return resp.json()

def get_financial_signals(date: Optional[str] = None) -> Dict[str, Any]:
    params = {"date": date} if date else {}
    resp = requests.get(f"{TREND_RADAR_URL}/signals/financial", params=params)
    resp.raise_for_status()
    return resp.json()
```

### Unified Config Loader (utils/config_loader.py)

```python
"""Single source for loading all JSON configs."""

import json
from pathlib import Path
from functools import lru_cache

CONFIG_DIR = Path(__file__).parent.parent / "config"

@lru_cache(maxsize=16)
def _load_json(filename: str) -> dict:
    with open(CONFIG_DIR / filename, encoding="utf-8") as f:
        return json.load(f)

def load_ticker_buckets() -> dict:
    return _load_json("financial_mappings.json").get("ticker_to_bucket", {})

def load_token_buckets() -> dict:
    return _load_json("financial_mappings.json").get("token_to_bucket", {})

def reload_configs():
    _load_json.cache_clear()
```

### DB Abstraction (trend_radar/models.py)

```python
import os
from sqlalchemy import create_engine

DATABASE_URL = os.getenv(
    "TREND_RADAR_DB_URL",
    "sqlite:///data/trend_radar.db"
)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)
```

### CLI Integration (main.py)

```python
parser.add_argument("--financial-signals", action="store_true",
                    help="Fetch financial signals (Yahoo, DBnomics, Kraken)")
parser.add_argument("--trend-radar-api", action="store_true",
                    help="Run Trend Radar FastAPI server")
parser.add_argument("--trend-radar-refresh", action="store_true",
                    help="Run Trend Radar data refresh job")
parser.add_argument("--refresh-tier", choices=["lite", "standard", "deep"],
                    default="lite", help="Refresh tier")
```

## File Structure

### New Files

```
briefAI/
├── config/
│   └── financial_mappings.json      # ticker_to_bucket, token_to_bucket
├── utils/
│   ├── financial_signals.py         # Fetchers + aggregator (~400 lines)
│   └── config_loader.py             # Unified config loading (~60 lines)
├── trend_radar/
│   └── client.py                    # HTTP client for Streamlit (~80 lines)
```

### Modified Files

```
├── utils/
│   ├── bucket_scorers.py            # Add PMS/CSS to BucketProfile
│   └── bucket_models.py             # Extend BucketProfile dataclass
├── trend_radar/
│   └── models.py                    # Add DATABASE_URL env var
├── main.py                          # Add CLI flags
```

## Implementation Phases

| Phase | Task | Files |
|-------|------|-------|
| 1 | Create financial_mappings.json | config/financial_mappings.json |
| 2 | Create config_loader.py | utils/config_loader.py |
| 3 | Yahoo Finance fetcher | utils/financial_signals.py |
| 4 | Kraken fetcher | utils/financial_signals.py |
| 5 | DBnomics fetcher + MRS | utils/financial_signals.py |
| 6 | Extend BucketProfile | utils/bucket_models.py, bucket_scorers.py |
| 7 | Wire CLI | main.py |
| 8 | API client + endpoints | trend_radar/client.py, trend_radar/api.py |

## Dependencies

```
# requirements.txt additions
yfinance>=0.2.36
dbnomics>=1.2.0
krakenex>=2.1.0
```

## Data Refresh

- **Frequency**: Daily, batch with news pipeline
- **Trigger**: `python main.py --financial-signals`
- **Output**: `data/alternative_signals/financial_signals_YYYY-MM-DD.json`
