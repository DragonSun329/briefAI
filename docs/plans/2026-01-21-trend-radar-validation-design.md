# Trend Radar: Multi-Signal Validation System

**Date**: 2026-01-21
**Status**: Design Complete
**Purpose**: Improve trend radar accuracy through cross-source validation

---

## Overview

Enhance the existing trend radar to validate detected signals against multiple independent data sources. Primary detection remains news-based; validation layers from GitHub, HuggingFace, Reddit, HackerNews, SEC, Crunchbase, and prediction markets provide corroboration.

**Key principle:** Validation ≠ Maturity ≠ Importance. These are three independent dimensions.

---

## Core Concepts

### Three Independent Scores

| Score | Question | Inputs |
|-------|----------|--------|
| **Validation Score** | Is this signal real or noise? | Source count, diversity, temporal alignment |
| **Momentum Score** | How fast is this growing? | Week-over-week velocity, baseline comparison |
| **Impact Score** | How strategically important? | Article relevance, entity type, topic category |

These are NOT combined. Users filter by different combinations based on use case.

### Validation Categories

| Category | Sources | What it validates |
|----------|---------|-------------------|
| Technical | GitHub, HuggingFace, arXiv, Papers w/ Code | Real engineering activity |
| Social | Reddit, HackerNews, Twitter | Community buzz |
| Financial | SEC, Crunchbase, OpenBook VC | Capital movement |
| Predictive | Polymarket, Manifold, Metaculus | Market expectations |

---

## Entity Type Hierarchy

```
ENTITY (canonical)
└─ "DeepSeek" (type: company)

LINKED ASSETS:
├─ org: "deepseek-ai" (GitHub, HuggingFace)
├─ model: "deepseek-v3", "deepseek-r1"
├─ repo: "DeepSeek-V3", "DeepSeek-Coder"
└─ topic: "deepseek" (news/social mentions)
```

**Entity types:** company, org, model, repo, person, topic

---

## Entity Matching Strategy

### Three-Tier Matching

| Tier | Method | Confidence | Example |
|------|--------|------------|---------|
| 1 | Registry lookup or exact match | High (1.0) | "DeepSeek" → registry → "DeepSeek" |
| 2 | Org/namespace prefix match | Medium (0.6) | "deepseek-ai" → prefix → "DeepSeek" |
| 3 | Substring match | Low (0.2) | "...DeepSeek announced..." → substring |

### Coherence Checks (Tier 2 → Tier 1 upgrade)

| Check | Confidence boost |
|-------|------------------|
| GitHub org links to company website | +0.3 |
| README mentions company name | +0.2 |
| HuggingFace model card mentions company | +0.2 |
| GitHub org = HuggingFace namespace | +0.1 |

### Canonical Entity Registry

**File:** `config/entity_registry.json`

```json
{
  "deepseek": {
    "canonical_name": "DeepSeek",
    "type": "company",
    "aliases": ["deepseek ai", "deep seek"],
    "github_orgs": ["deepseek-ai"],
    "hf_namespaces": ["deepseek-ai"],
    "products": ["deepseek-v3", "deepseek-r1", "deepseek-coder"],
    "website": "deepseek.com"
  }
}
```

### Ambiguity Rules

**File:** `config/ambiguous_entities.json`

```json
{
  "ambiguous_terms": [
    {"term": "claude", "reason": "common name vs Anthropic product", "require_context": ["anthropic", "ai", "model"]},
    {"term": "gemini", "reason": "Google model vs astrology", "require_context": ["google", "ai", "model"]},
    {"term": "llama", "reason": "Meta model vs animal", "require_context": ["meta", "ai", "llm"]}
  ],
  "denylist_patterns": ["^the ", "^a ", "\\d{4}$"]
}
```

### EntityMatcher Output

```python
@dataclass
class EntityResolution:
    primary_match: Optional[str]           # Best canonical entity
    primary_type: Optional[str]            # company, model, org, etc.
    candidates: List[EntityCandidate]      # All candidates with scores
    resolution_confidence: float           # 0-1
    ambiguity_flags: List[str]             # ["common_name", "multiple_orgs"]
    resolution_path: str                   # "registry" | "tier1" | "tier2" | "tier3"
```

---

## Validation Score Algorithm

### Split: Coverage vs Strength

```python
@dataclass
class ValidationResult:
    # Coverage: did we have data to check?
    validation_coverage: float             # 0-1
    sources_checked: List[str]
    sources_missing: List[str]             # No snapshot available
    sources_no_data: List[str]             # Checked but empty

    # Strength: how strong is the evidence?
    validation_strength: float             # 0-1
    corroborating_sources: Dict[str, SourceMatch]
    tier_distribution: Dict[int, int]      # {1: 2, 2: 1, 3: 0}

    # Combined
    validation_score: float                # coverage * strength

    # Debug
    validation_fail_reasons: Dict[str, str]
```

### Source Count Factor (40% of strength)

| Categories with signal | Raw score |
|------------------------|-----------|
| 1 (news only) | 0.2 |
| 2 | 0.5 |
| 3 | 0.75 |
| 4+ | 1.0 |

*Multiple sources in same category count as 1.*

### Diversity Factor (30% of strength)

```python
SOURCE_CATEGORIES = {
    "technical": ["github", "huggingface", "arxiv", "paperswithcode"],
    "social": ["reddit", "hackernews", "twitter"],
    "financial": ["sec", "crunchbase", "openbook_vc"],
    "predictive": ["polymarket", "manifold", "metaculus"],
}

# Rules:
# - Each category counts at most once
# - Cross-category gets bonus (technical + financial = +0.15)
# - Predictive + any other = +0.1
```

### Temporal Alignment Factor (30% of strength)

| Alignment | Raw score |
|-----------|-----------|
| All signals same week | 1.0 |
| Signals within 2 weeks | 0.7 |
| Signals >2 weeks apart | 0.4 |
| Only 1 source | 0.0 |

### Tier Weights

| Match tier | Weight | Counts toward validated? |
|------------|--------|--------------------------|
| Tier 1 | 1.0 | Yes |
| Tier 2 | 0.6 | Yes |
| Tier 2 + coherence | 0.9 | Yes |
| Tier 3 | 0.2 | No (flag only) |
| Tier 3 + ambiguous | 0.0 | Rejected |

### Validation Threshold

"Validated" requires:
- At least 2 sources with Tier 1/2 weight ≥0.6
- OR: 1 Tier 1 + 2 Tier 3 (with context keywords)

---

## Architecture

### Two-Stage Pipeline

```
STAGE 1: INGEST (daily/scheduled)
├─ GitHub Scraper → data/alternative_signals/github_*.json
├─ HuggingFace Scraper → data/alternative_signals/huggingface_*.json
├─ Reddit Scraper → data/alternative_signals/reddit_*.json
└─ ... other scrapers ...
         │
         ▼
    SnapshotBuilder → data/snapshots/source_snapshot_YYYY-MM-DD.json

STAGE 2: VALIDATE (on-demand, offline)
├─ TrendAggregator.detect_trend_signals() → raw signals
├─ TrendSignalEnricher (reads snapshots only)
│   ├─ EntityMatcher.resolve_entity()
│   ├─ find_corroboration()
│   └─ compute_validation()
└─ → ValidatedTrendSignal[]
```

**Benefits:**
- Reproducible: same snapshot → same results
- No API/rate limits during validation
- Can re-run with updated matcher without re-scraping

### Key Classes

**EntityMatcher** (`utils/entity_matcher.py`)
```python
class EntityMatcher:
    def __init__(self, registry_path, ambiguity_path):
        self.registry = load_json(registry_path)
        self.ambiguity = load_json(ambiguity_path)

    def resolve_entity(self, name: str, source: str) -> EntityResolution:
        """Resolve raw name to canonical entity with candidates."""
```

**SignalValidator** (`utils/signal_validator.py`)
```python
class SignalValidator:
    def compute_validation(
        self,
        matches: Dict[str, SourceMatch],
        resolution: EntityResolution
    ) -> ValidationResult:
        """Compute coverage and strength from matches."""
```

**TrendSignalEnricher** (`utils/trend_signal_enricher.py`)
```python
class TrendSignalEnricher:
    def __init__(self, snapshot_dir: Path, matcher: EntityMatcher):
        self.snapshots = self._load_latest_snapshots()

    def enrich(self, signals: List[TrendSignal]) -> List[ValidatedTrendSignal]:
        """Add validation to raw signals."""
```

### Output Schema

```python
@dataclass
class ValidatedTrendSignal:
    # Original signal
    entity_id: str
    entity_name: str
    entity_type: str
    signal_type: str
    current_week: str
    momentum_score: float

    # Entity resolution
    entity_resolution: EntityResolution

    # Validation
    validation: ValidationResult

    @property
    def validation_status(self) -> str:
        if self.validation.validation_score >= 0.7:
            return "high_confidence"
        elif self.validation.validation_score >= 0.5:
            return "validated"
        elif self.validation.validation_coverage < 0.5:
            return "insufficient_data"
        else:
            return "unvalidated"
```

---

## Implementation Phases

### Phase 1: Foundation

**Files to create:**
- `config/entity_registry.json` — 20-30 key AI entities
- `config/ambiguous_entities.json` — Ambiguity rules + denylist
- `config/source_categories.json` — Category mappings
- `utils/entity_matcher.py` — EntityMatcher, EntityResolution, EntityCandidate

**Test:**
```python
matcher = EntityMatcher()
result = matcher.resolve_entity("deepseek-v3", source="huggingface")
assert result.primary_match == "DeepSeek"
```

### Phase 2: Snapshot Consolidation

**Files to create:**
- `utils/snapshot_builder.py` — Consolidates scraper outputs

**Schema:**
```json
{
  "snapshot_date": "2026-01-21",
  "sources": {
    "github": {"orgs": [...], "trending_repos": [...]},
    "huggingface": {"models": [...], "spaces": [...]},
    "reddit": {"posts": [...]},
    ...
  },
  "data_health": {
    "sources_available": [...],
    "sources_missing": [...],
    "sources_stale": [...]
  }
}
```

### Phase 3: Validation Logic

**Files to create:**
- `utils/signal_validator.py` — ValidationResult, scoring
- `utils/trend_signal_enricher.py` — Orchestrator

### Phase 4: Integration

**Modify:**
- `test_trend_radar.py` — Show validated output

**Example output:**
```
=== Trend Signals (2026-W04) ===

1. DeepSeek (company)
   Signal: velocity_spike (+350%)
   Momentum: 85%
   Validation: 78% (high_confidence)
   └─ Coverage: 4/5 sources
   └─ Strength: Tier 1 (GitHub, HuggingFace), Tier 2 (Reddit)

2. Qwen (model)
   Signal: new_entity
   Momentum: 62%
   Validation: 45% (insufficient_data)
   └─ Coverage: 2/5 sources
   └─ Fail: github=no_match, huggingface=stale_data
```

### Phase 5: Registry Growth

**Process:**
1. Log entities with low `resolution_confidence`
2. Review and add to registry
3. Track registry hit rate as health metric

---

## Files Summary

| Phase | File | Purpose |
|-------|------|---------|
| 1 | `config/entity_registry.json` | Canonical entities |
| 1 | `config/ambiguous_entities.json` | Ambiguity rules |
| 1 | `config/source_categories.json` | Category mappings |
| 1 | `utils/entity_matcher.py` | Entity resolution |
| 2 | `utils/snapshot_builder.py` | Consolidate scrapers |
| 3 | `utils/signal_validator.py` | Validation scoring |
| 3 | `utils/trend_signal_enricher.py` | Orchestrator |
| 4 | `test_trend_radar.py` (modify) | Test integration |
