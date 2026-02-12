# PR: Review System v1.1 — Explainability, Sample-Size Protection, Suggestions

## Summary

Upgrades the Prediction Review System with five key improvements:

1. **Outcome Resolver Explainability** — debug_features, decision_trace, unclear_reason
2. **Unclear Bucketing + Reporting** — unclear_rate, unclear_breakdown by reason
3. **Sample-Size Protection** — insight_strength, reliability_score, qualified lessons
4. **Suggestions Output** — actionable but non-automatic improvement suggestions
5. **Optional Daily Hook** — script for daily pipeline integration

## Changes

### A. Outcome Resolver Explainability

**File:** `briefai/review/outcome_resolver.py`, `briefai/review/models.py`

Extended `ResolvedOutcome` model with:
```python
debug_features: dict[str, float]  # feature -> normalized score
decision_trace: list[str]         # human-readable steps
unclear_reason: UnclearReason     # data_missing | mixed_evidence | low_signal | none
```

New `UnclearReason` enum:
```python
class UnclearReason(Enum):
    DATA_MISSING = "data_missing"     # No signal data available
    MIXED_EVIDENCE = "mixed_evidence"  # Conflicting signals
    LOW_SIGNAL = "low_signal"          # Signals too weak
    NONE = "none"                      # Outcome resolved
```

Features extracted:
- `meta_signal_presence` (0/1)
- `mention_delta_7d` (float)
- `momentum_direction` (-1/0/1)
- `source_diversity_count` (int)
- `signal_persistent` (0/1)
- `final_score` (float)

### B. Unclear Bucketing + Reporting

**File:** `briefai/review/metrics.py`, `briefai/review/models.py`

Added to `ReviewMetrics`:
```python
unclear_rate: float = 0.0
unclear_breakdown: dict = {}  # {reason: count}
accuracy_excluding_unclear: float = 0.0
```

New function `compute_unclear_breakdown()` categorizes unclear outcomes.

### C. Sample-Size Protection

**File:** `briefai/review/patterns.py`, `briefai/review/lessons.py`, `briefai/review/models.py`

Added to `LearningInsight`:
```python
insight_strength: str = "weak"   # weak (<5) | moderate (5-9) | strong (>=10)
reliability_score: float = 0.0  # n * |success_rate - 0.5|
```

Added to `Lesson`:
```python
sample_size: int = 0
success_rate: float = 0.0
insight_strength: str = "weak"
```

**Rules:**
- Insights/lessons with n<5 marked as `[Weak]` and do NOT emit strong claims
- Insights ranked by `reliability_score` (prioritizes reliable learnings)
- New helper: `get_reliable_insights(insights, min_strength="moderate")`

### D. Suggestions Output

**File:** `briefai/review/suggestions.py` (new)

New `Suggestion` model:
```python
@dataclass
class Suggestion:
    suggestion_id: str
    target: str           # confidence_cap, mechanism_weight, etc.
    rationale: str        # cites triggering pattern
    proposed_change: dict
    safety: str = "manual_review_required"  # NEVER auto-apply
```

Generates suggestions for:
- `confidence_cap` — when calibration error > 0.15
- `mechanism_weight` — when mechanism accuracy <35% or >75%
- `media_only_threshold` — when media category underperforms
- `check_date_policy` — when long-term predictions fail
- `data_coverage` — when unclear_rate > 50%
- `signal_retention` — when data_missing dominates unclear

**Output files:**
- `data/reviews/suggestions_YYYY-MM-DD.json`
- "Suggested Next PRs" section in review markdown

### E. Optional Daily Hook

**File:** `scripts/run_daily_review.py` (new)

Usage:
```bash
python scripts/run_daily_review.py --experiment v2_2_forward_test --verbose
```

Behavior:
- Checks for expired predictions
- If none: prints `SKIP: No expired predictions` and exits 0
- If found: runs full review and prints output paths

**Integration snippet for `daily_bloomberg.ps1`:**
```powershell
# Optional: Run prediction review (uncomment to enable)
# Write-Host "Running daily review..."
# python scripts/run_daily_review.py --experiment v2_2_forward_test --verbose
```

## Data Flow

```
READ ONLY:
├── data/public/experiments/{id}/forecast_history.jsonl
├── data/meta_signals/
├── data/insights/
└── data/briefs/

WRITE TO:
└── data/reviews/
    ├── review_YYYY-MM-DD.json
    ├── review_YYYY-MM-DD.md
    └── suggestions_YYYY-MM-DD.json
```

## Tests Added

| Test Class | Coverage |
|------------|----------|
| `TestUnclearReasonClassification` | unclear_reason assignment |
| `TestDebugFeatures` | debug_features presence & stability |
| `TestSampleSizeProtection` | insight_strength, reliability_score |
| `TestUnclearBreakdown` | compute_unclear_breakdown |
| `TestSuggestionsGeneration` | suggestion generation & format |
| `TestDailyHook` | skip/run behavior |

**Total tests:** 50 (31 existing + 19 new)

## Example Output

### Unclear Analysis (v1.1)
```markdown
## Unclear Analysis

**Unclear Rate:** 60.0% (3/5)

| Reason | Count |
|--------|-------|
| data_missing | 3 |
| mixed_evidence | 0 |
| low_signal | 0 |
```

### Sample-Size Qualified Lesson (v1.1)
```
- ✅ [Weak] Mechanism 'media_attention_spike' may underperform (0% accuracy, n=2) - needs more data
```

### Suggestion (v1.1)
```json
{
  "suggestion_id": "sug_859d04ea96f4",
  "target": "confidence_cap",
  "rationale": "Calibration error of 0.28 indicates systematic overconfidence.",
  "proposed_change": {
    "action": "reduce_confidence_multiplier",
    "factor": 0.85,
    "scope": "global"
  },
  "safety": "manual_review_required"
}
```

## Constraints Maintained

- ✅ **READ ONLY**: Never writes to forecast_history.jsonl, daily_snapshot_*.json, run_metadata_*.json
- ✅ **WRITE TO**: Only data/reviews/
- ✅ **Deterministic**: No LLM calls, reproducible output
- ✅ **Sample-Size Protected**: Weak insights (n<5) don't emit strong claims

## Migration

No breaking changes. Existing v1.0 review outputs remain valid.

New fields have defaults:
- `debug_features`: `{}`
- `decision_trace`: `[]`
- `unclear_reason`: `UnclearReason.NONE`
- `insight_strength`: `"weak"`
- `reliability_score`: `0.0`

## Version

`review_version: "1.1.0"` in all output files.
