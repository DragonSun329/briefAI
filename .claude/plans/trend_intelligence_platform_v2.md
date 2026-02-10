# Trend Intelligence Platform v2 - Implementation Plan

## Executive Summary

Upgrade the existing Trend Radar into a robust, production-grade Trend Intelligence Platform with enhanced signal confidence, persistent alerts with cooldowns, EWMA smoothing, historical baselines, and explainability features.

## Current State Assessment

### Strengths (Keep)
- ✅ Bucket scoring framework (TMS/CCS/EIS/NAS + PMS/CSS)
- ✅ Coverage tracking (has_tms_data, etc.)
- ✅ Alert types (Alpha/Hype/Enterprise/Disruption/Rotation)
- ✅ Confidence intervals with variance components
- ✅ 5T Investment Thesis scoring
- ✅ 18 alternative data scrapers

### Gaps to Address
- ❌ No EWMA smoothing for volatile signals (NAS/CSS)
- ❌ No historical baseline percentiles (12-26 week comparisons)
- ❌ Alerts lack persistence storage + cooldown enforcement
- ❌ No explainability payload (top evidence, why alert fired)
- ❌ No SimHash deduplication before LLM spend
- ❌ Signal metadata incomplete (freshness, source_counts missing)
- ❌ UI lacks evidence drawer and confidence visual encoding

---

## Phase 1: Signal Robustness Foundation (Week 1)

### 1.1 Enhanced Signal Metadata Schema

**File:** `utils/signal_metadata.py` (NEW)

```python
@dataclass
class EnhancedSignalMetadata:
    """Complete signal metadata with all robustness fields."""
    signal_name: str              # tms, ccs, nas, etc.
    value: Optional[float]        # 0-100 percentile (None if missing)
    raw_value: Optional[float]    # Pre-percentile value

    # Robustness metrics
    confidence: float             # 0-1, composite confidence
    coverage: float               # 0-1, entity_count / baseline
    freshness: float              # 0-1, decays with age (24h = 1.0, 7d = 0.5)
    source_count: int             # Number of distinct sources

    # Smoothing
    ewma_value: Optional[float]   # Exponentially weighted moving average
    ewma_alpha: float = 0.3       # Smoothing factor (higher = more reactive)

    # Historical context
    percentile_12w: Optional[float]  # Percentile vs 12-week baseline
    percentile_26w: Optional[float]  # Percentile vs 26-week baseline
    z_score: Optional[float]         # Std devs from historical mean

    # Lineage
    sources: List[str]            # Contributing data sources
    entity_count: int             # Entities contributing to signal
    last_updated: datetime
```

### 1.2 EWMA Smoothing Module

**File:** `utils/signal_smoothing.py` (NEW)

- EWMA for NAS/CSS (volatile signals)
- Winsorization (clip to 5th-95th percentile) before averaging
- Configurable alpha per signal type

### 1.3 Historical Baseline Calculator

**File:** `utils/historical_baselines.py` (NEW)

- Load 12-26 weeks of historical snapshots
- Compute per-bucket, per-signal percentiles
- Track: mean, std, percentile ranks over history
- Flag anomalies (z-score > 2.5)

### 1.4 Freshness Decay Function

- Exponential decay: `freshness = exp(-age_hours / half_life_hours)`
- Half-life: 48 hours for news, 168 hours for GitHub/HF data
- Stale data (>7d) gets coverage penalty

---

## Phase 2: Alert Engine Rewrite (Week 1-2)

### 2.1 Persistent Alert Storage

**File:** `utils/alert_store.py` (NEW)

```python
class AlertStore:
    """SQLite-based persistent alert storage."""

    def __init__(self, db_path: Path = "data/alerts.db"):
        self.conn = sqlite3.connect(db_path)
        self._create_tables()

    def save_alert(self, alert: BucketAlert) -> str:
        """Upsert alert, returns alert_id."""

    def get_active_alerts(self, bucket_id: str = None) -> List[BucketAlert]:
        """Get non-expired alerts, optionally filtered."""

    def check_cooldown(self, bucket_id: str, alert_type: str) -> bool:
        """Returns True if cooldown active (don't show alert)."""

    def mark_shown(self, alert_id: str) -> None:
        """Update last_shown timestamp."""

    def expire_alert(self, alert_id: str, reason: str) -> None:
        """Mark alert as expired with reason."""
```

**Alert Table Schema:**
```sql
CREATE TABLE alerts (
    alert_id TEXT PRIMARY KEY,
    bucket_id TEXT NOT NULL,
    alert_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    interpretation TEXT NOT NULL,
    first_detected DATE NOT NULL,
    last_updated DATE NOT NULL,
    last_shown DATE,
    weeks_persistent INTEGER DEFAULT 1,
    cooldown_expires DATE,
    expired_at DATE,
    expired_reason TEXT,
    trigger_scores JSON,
    evidence_payload JSON,
    UNIQUE(bucket_id, alert_type)
);
```

### 2.2 Cooldown Logic Enhancement

- Default cooldowns by severity:
  - INFO: 3 days
  - WARN: 7 days
  - CRIT: 14 days
- Override cooldown if severity escalates
- Manual dismiss option (user action stored)

### 2.3 Explainability Payload

**File:** `utils/alert_explainer.py` (NEW)

```python
@dataclass
class AlertExplanation:
    """Why did this alert fire?"""
    alert_id: str
    alert_type: AlertType

    # Trigger conditions met
    trigger_rules: List[str]  # e.g., ["TMS >= 90 (actual: 92)", "CCS <= 30 (actual: 25)"]

    # Top evidence
    top_entities: List[Dict]  # [{name, type, contribution_score}]
    top_articles: List[Dict]  # [{title, source, date, relevance}]
    top_repos: List[Dict]     # [{name, stars_delta, url}]

    # Historical context
    similar_past_alerts: List[Dict]  # Previous alerts of same type
    typical_resolution: str           # "Usually capital follows in 4-8 weeks"

    # Confidence breakdown
    confidence_factors: Dict[str, float]  # {coverage: 0.8, freshness: 0.9, ...}
```

---

## Phase 3: Pipeline Robustness (Week 2)

### 3.1 Event Schema for Ingestion

**File:** `utils/events.py` (NEW)

```python
@dataclass
class ArticleEvent:
    """Ingested article before processing."""
    event_id: str
    source: str
    url: str
    title: str
    content: str
    published_at: datetime
    scraped_at: datetime

    # Dedup
    simhash: str
    canonical_url: str

    # Processing state
    is_duplicate: bool = False
    duplicate_of: Optional[str] = None

@dataclass
class TrendUpdateEvent:
    """Signal update for a bucket."""
    event_id: str
    bucket_id: str
    signal_type: str  # tms, ccs, nas, etc.
    old_value: Optional[float]
    new_value: float
    delta: float
    triggered_at: datetime

    # Lineage
    contributing_entities: List[str]
    source_events: List[str]  # ArticleEvent IDs
```

### 3.2 SimHash Deduplication

**File:** `utils/dedup_simhash.py` (NEW)

- 64-bit SimHash fingerprinting
- LSH bucketing for O(1) duplicate lookup
- Threshold: Hamming distance <= 3 bits = duplicate
- Saves LLM costs by skipping duplicate articles

### 3.3 Graceful Source Degradation

**File:** `utils/source_health.py` (NEW)

- Track success/failure rate per scraper
- Circuit breaker: disable source after 3 consecutive failures
- Auto-retry with exponential backoff
- Dashboard shows source health status

---

## Phase 4: UI Trust Enhancements (Week 2)

### 4.1 Top Alerts Card Redesign

```
┌─────────────────────────────────────────────────────────────┐
│ 🟡 WARN: Alpha Zone Detected                                │
│ Bucket: RAG & Retrieval                                     │
│ ─────────────────────────────────────────────────────────── │
│ Type: Hidden Gem (OPPORTUNITY)                              │
│ Confidence: 87% ████████░░                                  │
│ Evidence: 12 repos, 47 articles, 3 companies                │
│ Persistent: 3 weeks                                         │
│ ─────────────────────────────────────────────────────────── │
│ Action Hint: Monitor for capital inflow signals             │
│ [Explain] [Dismiss for 7d] [Watch]                          │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 Bucket Explain Drawer

```
┌─────────────────────────────────────────────────────────────┐
│ RAG & Retrieval - Deep Dive                            [X]  │
├─────────────────────────────────────────────────────────────┤
│ 8-Week Signal Sparklines:                                   │
│ TMS: ▁▂▃▅▆▇█▇  (85 ↑12)  Coverage: 92%                     │
│ CCS: ▅▄▃▃▂▂▃▄  (42 ↓3)   Coverage: 78%                     │
│ NAS: ▃▄▅▆▆▇▇█  (72 ↑8)   Coverage: 95%                     │
│ EIS: ▂▃▃▄▅▅▆▆  (61 ↑5)   Coverage: 65%                     │
├─────────────────────────────────────────────────────────────┤
│ Top Entities:                                               │
│ • langchain/langchain (⭐ +2.3k this week)                  │
│ • vllm-project/vllm (⭐ +1.8k)                              │
│ • Pinecone (Series C, $100M)                                │
├─────────────────────────────────────────────────────────────┤
│ Active Alert: Alpha Zone                                    │
│ Rationale: TMS (92) >> CCS (25) divergence of 67 points    │
│ First detected: 2025-01-06 (3 weeks ago)                    │
│ Similar past: "AI Coding" bucket, Jan 2024 (capital        │
│               arrived 6 weeks later)                        │
├─────────────────────────────────────────────────────────────┤
│ Data Quality:                                               │
│ ████████░░ 85% confidence | 5/6 signals | Fresh (2h ago)   │
└─────────────────────────────────────────────────────────────┘
```

### 4.3 Confidence Visual Encoding

- **High confidence (>0.8)**: Solid fill, full opacity
- **Medium confidence (0.5-0.8)**: Solid fill, 70% opacity
- **Low confidence (<0.5)**: Dashed outline, 50% opacity
- **Missing data**: Gray with "?" badge

---

## File Tree (New/Modified)

```
briefAI/
├── utils/
│   ├── signal_metadata.py       # NEW: Enhanced signal dataclass
│   ├── signal_smoothing.py      # NEW: EWMA + winsorization
│   ├── historical_baselines.py  # NEW: 12-26 week percentiles
│   ├── alert_store.py           # NEW: SQLite alert persistence
│   ├── alert_explainer.py       # NEW: Explainability payloads
│   ├── events.py                # NEW: ArticleEvent, TrendUpdateEvent
│   ├── dedup_simhash.py         # NEW: SimHash fingerprinting
│   ├── source_health.py         # NEW: Scraper health tracking
│   ├── bucket_scorers.py        # MODIFY: Use EnhancedSignalMetadata
│   ├── bucket_models.py         # MODIFY: Add new fields
│   ├── bucket_alerts.py         # MODIFY: Use AlertStore
│   └── schemas.py               # MODIFY: Add event schemas
├── modules/
│   └── bucket_dashboard.py      # MODIFY: Add explain drawer, confidence viz
├── data/
│   ├── alerts.db                # NEW: SQLite alert store
│   └── historical/              # NEW: Weekly snapshot archive
│       ├── 2025-W01.json
│       ├── 2025-W02.json
│       └── ...
├── tests/
│   ├── test_signal_smoothing.py # NEW: EWMA tests
│   ├── test_alert_store.py      # NEW: Persistence tests
│   ├── test_dedup.py            # NEW: SimHash tests
│   └── test_baselines.py        # NEW: Percentile tests
└── config/
    └── signal_config.json       # NEW: EWMA alpha, cooldowns, thresholds
```

---

## Implementation Order

### Week 1 (Foundation)
1. `signal_metadata.py` - Core dataclass
2. `signal_smoothing.py` - EWMA implementation
3. `historical_baselines.py` - Baseline calculator
4. `alert_store.py` - SQLite persistence
5. `bucket_scorers.py` modifications
6. Unit tests for above

### Week 2 (Integration)
1. `alert_explainer.py` - Explainability
2. `events.py` - Event schemas
3. `dedup_simhash.py` - Deduplication
4. `source_health.py` - Health tracking
5. `bucket_dashboard.py` - UI enhancements
6. Integration tests

---

## Key Schemas

### SignalConfig (config/signal_config.json)
```json
{
  "ewma": {
    "nas": {"alpha": 0.3, "enabled": true},
    "css": {"alpha": 0.25, "enabled": true},
    "tms": {"alpha": 0.5, "enabled": false},
    "ccs": {"alpha": 0.5, "enabled": false}
  },
  "freshness": {
    "half_life_hours": {
      "news": 48,
      "github": 168,
      "huggingface": 168,
      "sec": 336
    }
  },
  "cooldowns": {
    "INFO": 3,
    "WARN": 7,
    "CRIT": 14
  },
  "baselines": {
    "short_window_weeks": 12,
    "long_window_weeks": 26,
    "min_weeks_required": 4
  },
  "dedup": {
    "simhash_threshold": 3,
    "enabled": true
  }
}
```

---

## Success Metrics

1. **Signal Quality**: All signals have confidence >= 0.5 or flagged as low-confidence
2. **Alert Precision**: <5% false positive rate (via manual review)
3. **Alert Fatigue**: <3 alerts per bucket per month (via cooldowns)
4. **Explainability**: 100% of alerts have evidence payload
5. **Data Freshness**: 90% of signals updated within 24h
6. **Dedup Savings**: 30%+ reduction in LLM calls via SimHash