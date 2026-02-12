# PR: Ask Mode v1.1 — Freshness Banner + Evidence Citations + Intent Router

## Summary

Enhances Ask Mode with three UX improvements for better trust and reduced tool thrash:

1. **Freshness Banner**: Every answer shows data recency at the top
2. **Evidence Citations**: Grep-able `[evidence: path#anchor]` format for all claims
3. **Intent Router**: Deterministic query classification to optimize tool selection

All changes maintain offline/deterministic operation and write protection.

## Changes

### A) Freshness Banner

New file: `briefai/ask/freshness.py`

| Function | Purpose |
|----------|---------|
| `get_latest_artifact_dates(experiment_id)` | Scan all artifact locations |
| `FreshnessSummary.to_banner()` | Generate banner string |
| `scan_*()` | Individual scanners for each artifact type |

**Scanned Locations:**
- `data/briefs/` (daily briefs)
- `data/public/experiments/{id}/` (snapshots, metadata)
- `data/meta_signals/` (meta-signals)
- `data/news_signals/` (news signals)

**Output:**
```
📌 Data scope: local artifacts only | Latest available: 2026-02-11 | Experiment: v2_2_forward_test
```

### B) Evidence Citations

New model: `EvidenceRef` in `briefai/ask/models.py`

**Citation Format:**
```
[evidence: <artifact_path>#<anchor>]
```

**Examples:**
| Artifact | Citation |
|----------|----------|
| Meta-signal | `[evidence: data/meta_signals/meta_signals_2026-02-11.json#meta_id=abc123]` |
| Brief | `[evidence: data/briefs/analyst_brief_2026-02-11.md#L1-L50]` |
| Snapshot | `[evidence: data/public/experiments/v2_2/daily_snapshot_2026-02-11.json#predictions]` |

**Tool Updates:**
All tools now return `evidence_refs: List[EvidenceRef]` and `as_of_date: str`.

### C) Intent Router

New file: `briefai/ask/intent_router.py`

| Intent | Trigger Examples | Required Tools | Max Iter |
|--------|------------------|----------------|----------|
| `bull_bear_case` | "bull and bear case", "long/short thesis" | get_entity_profile, search_meta_signals | 6 |
| `what_changed` | "what changed", "vs yesterday" | summarize_daily_brief | 4 |
| `trend_explain` | "explain trend", "trending" | search_meta_signals | 4 |
| `entity_status` | entity name detected | get_entity_profile | 4 |
| `compare` | "compare", "vs" | get_entity_profile | 5 |
| `forecast_check` | "forecast", "prediction" | get_forecast_snapshot | 4 |
| `general` | (fallback) | search_meta_signals | 6 |

**Routing is deterministic** (keyword + regex, no LLM).

## Files Changed

| File | Change |
|------|--------|
| `briefai/ask/__init__.py` | Export new modules |
| `briefai/ask/models.py` | Add `EvidenceRef` |
| `briefai/ask/tools.py` | Add `evidence_refs`, `as_of_date` to all tools |
| `briefai/ask/engine.py` | Integrate intent router + freshness + citations |
| `briefai/ask/freshness.py` | **NEW** - Data freshness scanning |
| `briefai/ask/intent_router.py` | **NEW** - Query classification |
| `tests/test_ask_mode_v11.py` | **NEW** - v1.1 tests (18 tests) |
| `docs/ASK_MODE.md` | Updated with v1.1 features |

## Test Coverage

**Original tests:** 26 passed  
**v1.1 tests:** 18 passed  
**Total:** 44 passed

### New Tests

| Test Class | Coverage |
|------------|----------|
| `TestFreshnessBanner` | Banner exists, shows experiment, matches latest date |
| `TestEvidenceCitations` | Format, roundtrip, citations in tool results |
| `TestIntentRouting` | bull_bear, what_changed, trend_explain, entity detection |
| `TestToolThrashReduction` | Iteration limits, required tools |
| `TestV11Integration` | Full flow with citations |
| `TestDateExtraction` | Date parsing from filenames |

## Example Output

```
python -m briefai ask "What's the bull and bear case for NVDA?" --experiment v2_2_forward_test
```

```
📌 Data scope: local artifacts only | Latest available: 2026-02-11 | Experiment: v2_2_forward_test

## Key Takeaways
- NVDA shows strong signal momentum in AI chip demand [evidence: data/meta_signals/meta_signals_2026-02-11.json#meta_id=52f11143]
- Enterprise adoption accelerating [evidence: data/briefs/analyst_brief_2026-02-11.md#L45-L60]

## What to Watch
- PREDICTION: NVDA article_count will increase within 14 days [evidence: data/news_signals/techmeme_2026-02-11.json#id=nvda_001]
- PREDICTION: AI_chip_demand github_stars will increase within 30 days [evidence: data/meta_signals/meta_signals_2026-02-11.json#meta_id=chip123]

## Confidence & Caveats
Confidence: medium
Sources: 2 categories (meta, media)
```

## Non-Goals (Confirmed)

- ❌ No web access or external APIs
- ❌ No LLM-as-judge evals
- ❌ No changes to forecast pipeline
- ❌ No writes to forecast artifacts

## Acceptance Criteria

| Criterion | Status |
|-----------|--------|
| Freshness banner in final answer | ✅ |
| Banner shows experiment ID | ✅ |
| Banner latest matches max artifact date | ✅ |
| Key takeaways have citations | ✅ |
| Citations are grep-able format | ✅ |
| Intent router reduces tool thrash | ✅ |
| All 44 tests pass | ✅ |
| Write protection maintained | ✅ |

## Migration

No migration needed. v1.1 is backwards compatible.

---

**Author:** Mia (AI Assistant)  
**Date:** 2026-02-11  
**PR:** Ask Mode v1.1
