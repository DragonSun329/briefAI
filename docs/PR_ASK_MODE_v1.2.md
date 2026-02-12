# PR: Ask Mode v1.2 — Reflection + Diff + Stable Evidence

## Summary

Makes Ask Mode feel closer to a real analyst with three reliability/usability upgrades:

1. **Reflection Self-Check Loop**: Validates answers with deterministic rules, allows ONE repair iteration
2. **Daily Diff Mode**: "What changed today?" with structured comparison
3. **Stable Evidence Citations**: No fragile line numbers — uses `meta_id=`, `heading=`, `quote=` anchors

All changes maintain offline/deterministic operation. Write protection enforced.

## What's New

### 1. Reflection Self-Check Loop

**File:** `briefai/ask/reflection.py`

Workflow upgrade:
```
OLD: plan → tools → answer
NEW: plan → tools → draft → self-check → (repair?) → final
```

**Validation Rules (Deterministic, No LLM):**
| Rule | Requirement |
|------|-------------|
| `freshness_banner` | Must include data recency banner |
| `citation_diversity` | Must cite ≥2 independent artifact sources |
| `takeaway_citations` | Every Key Takeaway needs ≥1 citation |
| `watch_items` | Must include ≥1 measurable prediction with timeframe + direction |

**Repair Behavior:**
- ONE repair iteration allowed if validation fails
- Repair can call tools again
- If still failing → add `⚠️ Partial Confidence` banner
- All logged in scratchpad: `reflection_check`, `reflection_repair_attempt`

### 2. Daily Diff Mode

**Files:** `briefai/ask/diff_tool.py`, `briefai/ask/intent_router.py`

New intent: `DAILY_CHANGE`

**Triggers:**
- "What changed in AI today?"
- "Today's update"
- "What's new today?"
- "Daily diff"

**Tool:** `get_daily_diff(experiment_id, today_date, previous_date)`

**Compares:**
- Meta-signals (new, disappeared, strengthened, weakened)
- Predictions (new, resolved)
- Brief narratives (new, dropped)

**Output Format:**
```markdown
## Daily Diff: 2026-02-10 → 2026-02-11

**3 new signals emerged**
  - AI Pricing Shift
  - Enterprise Adoption

**2 signals strengthened**
  - Model Competition (+0.15)

**1 predictions resolved**
  - OpenAI pricing (confirmed)
```

### 3. Stable Evidence Citations

**File:** `briefai/ask/evidence_anchor.py`

**OLD (Fragile):**
```
[evidence: data/briefs/brief.md#L45-L60]
```

**NEW (Stable):**
```
[evidence: data/meta_signals/meta_signals_2026-02-11.json#meta_id=abc123]
[evidence: data/briefs/analyst_brief_2026-02-11.md#heading=ai-chip-market&quote=8fa21c3a]
```

**Anchor Types:**
| Type | Format | Use Case |
|------|--------|----------|
| `meta_id` | `#meta_id=abc123` | Meta-signals |
| `prediction_id` | `#prediction_id=h1:metric` | Forecasts |
| `heading` | `#heading=section-slug&quote=hash` | Markdown files |
| `quote` | `#quote=8fa21c3a` | Any text reference |

**Quote Hash:** `sha1(normalized_text)[:8]` — survives minor edits

### 4. Enhanced Freshness Banner

**Updated Output:**
```
📌 Data scope: local briefAI artifacts only
Latest available: 2026-02-11
Experiment: v2_2_forward_test
Staleness: fresh (today)
```

**Staleness Levels:**
- `fresh (today)` — 0 days
- `fresh (yesterday)` — 1 day
- `recent (N days)` — 2-3 days
- `⚠️ stale (N days old)` — 4+ days

### 5. Evidence Appendix

Every answer now ends with a deduplicated evidence list:

```markdown
---

## Evidence Used

- [evidence: data/meta_signals/meta_signals_2026-02-11.json#meta_id=sig1] (as of 2026-02-11)
- [evidence: data/briefs/analyst_brief_2026-02-11.md#heading=summary&quote=abc123] (as of 2026-02-11)
```

## Files Changed

| File | Change |
|------|--------|
| `briefai/ask/__init__.py` | Export new modules |
| `briefai/ask/engine.py` | Integrate reflection loop, repair, appendix |
| `briefai/ask/reflection.py` | **NEW** — Validation + repair logic |
| `briefai/ask/evidence_anchor.py` | **NEW** — Stable citation system |
| `briefai/ask/diff_tool.py` | **NEW** — Daily diff tool |
| `briefai/ask/intent_router.py` | Add `DAILY_CHANGE` intent |
| `briefai/ask/tools.py` | Register `get_daily_diff` tool |
| `briefai/ask/freshness.py` | Add staleness calculation |
| `briefai/ask/scratchpad.py` | Add reflection record types |
| `tests/test_ask_mode_v12.py` | **NEW** — 29 tests |

## Test Coverage

| Suite | Tests | Status |
|-------|-------|--------|
| v1.0 (original) | 26 | ✅ Pass |
| v1.1 (freshness/citations/intent) | 18 | ✅ Pass |
| v1.2 (reflection/diff/stable) | 29 | ✅ Pass |
| **Total** | **73** | ✅ Pass |

### New v1.2 Tests

| Test Class | Coverage |
|------------|----------|
| `TestReflectionValidation` | 8 tests — rule checks, repair generation |
| `TestReflectionRepair` | 2 tests — repair triggers, one-retry limit |
| `TestDiffMode` | 3 tests — intent routing, change detection |
| `TestStableAnchors` | 5 tests — format, hash stability, no line numbers |
| `TestEvidenceAppendix` | 3 tests — generation, deduplication |
| `TestWriteProtection` | 5 tests — ledger protection |
| `TestFreshnessBanner` | 2 tests — staleness calculation |
| `TestDailyChangeOutput` | 1 test — output format |

## Acceptance Criteria

✅ `python -m briefai ask "what changed in AI today?" --experiment v2_2_forward_test` produces:

1. ✅ Freshness banner with staleness
2. ✅ "What Changed" section (from diff tool)
3. ✅ ≥2 evidence citations in stable format
4. ✅ Evidence appendix at bottom
5. ✅ No writes to forecast ledger

## Write Protection (Enforced)

**FORBIDDEN (raises PermissionError):**
- `forecast_history.jsonl`
- `daily_snapshot_*.json`
- `run_metadata_*.json`
- Anything in `data/public/experiments/*` except ask_logs

**ALLOWED:**
- `ask_logs/ask_history.jsonl`
- `ask_logs/scratchpads/*`

## Example Output

```
python -m briefai ask "what changed in AI today?" --experiment v2_2_forward_test
```

```
📌 Data scope: local briefAI artifacts only
Latest available: 2026-02-11
Experiment: v2_2_forward_test
Staleness: fresh (today)

## What Changed

### New Signals
- **AI Pricing Dynamics** emerged with 0.75 confidence [evidence: data/meta_signals/meta_signals_2026-02-11.json#meta_id=sig3]

### Strengthened
- **Model Competition** increased from 0.5 → 0.7 (+0.2) [evidence: data/meta_signals/meta_signals_2026-02-11.json#meta_id=sig2]

## Key Takeaways
- Enterprise AI pricing is becoming more competitive [evidence: data/briefs/analyst_brief_2026-02-11.md#heading=key-insights&quote=8fa21c3a]
- Open-source alternatives gaining traction [evidence: data/meta_signals/meta_signals_2026-02-11.json#meta_id=sig3]

## What to Watch
- PREDICTION: api_pricing_index will decrease within 30 days [evidence: data/meta_signals/meta_signals_2026-02-11.json#meta_id=sig2]

---

## Evidence Used

- [evidence: data/meta_signals/meta_signals_2026-02-11.json#meta_id=sig2] (as of 2026-02-11) — Strengthened signal
- [evidence: data/meta_signals/meta_signals_2026-02-11.json#meta_id=sig3] (as of 2026-02-11) — New signal
- [evidence: data/briefs/analyst_brief_2026-02-11.md#heading=key-insights&quote=8fa21c3a] (as of 2026-02-11)
```

## Non-Goals (Confirmed)

- ❌ No web access or external APIs
- ❌ No LLM-as-judge for validation (pure rules)
- ❌ No changes to forecast pipeline
- ❌ No writes to experiment artifacts

## Migration

No migration needed. v1.2 is backwards compatible with v1.0/v1.1.

---

**Author:** Mia (AI Assistant)  
**Date:** 2026-02-11  
**Tests:** 73 passing
