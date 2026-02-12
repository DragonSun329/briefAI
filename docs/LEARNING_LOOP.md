# briefAI Learning Loop

The Learning Loop is briefAI's self-improvement system. It connects prediction outcomes to engine evolution through a reproducible, human-approved workflow.

## Overview

```
┌─────────────────┐
│   PREDICTION    │  Engine generates predictions with confidence scores
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│    REVIEW       │  After check_date, review system resolves outcomes
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│    PATCH        │  Suggestions converted to config patches
└────────┬────────┘
         │
         ▼ (human approval)
┌─────────────────┐
│    EVOLVE       │  Patches applied, new engine version tagged
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   NEW ENGINE    │  Updated weights/thresholds for future predictions
└─────────────────┘
```

## 1. Prediction Phase

The Hypothesis Engine generates predictions with:
- **Entity**: What is being predicted
- **Direction**: Bullish (up), bearish (down), or neutral
- **Confidence**: 0.0-1.0 score
- **Mechanism**: Why this prediction (e.g., product_launch, media_attention_spike)
- **Check Date**: When to evaluate the prediction

Predictions are logged to `forecast_history.jsonl` (NEVER modified by the learning system).

## 2. Review Phase

After a prediction's check_date passes, the Review System:

1. **Detects expired predictions** from the ledger
2. **Resolves outcomes** (correct/incorrect/unclear) using signal data
3. **Computes metrics** (accuracy, calibration, breakdown by mechanism)
4. **Discovers patterns** (what's working, what's not)
5. **Synthesizes lessons** (actionable insights)
6. **Generates suggestions** (proposed config changes)

### Running a Review

```bash
# Run review for an experiment
python -m briefai review --experiment v2_2_forward_test --verbose

# Or as part of daily pipeline
python scripts/run_daily_review.py --experiment v2_2_forward_test
```

### Outputs

| File | Purpose |
|------|---------|
| `review_YYYY-MM-DD.json` | Machine-readable review |
| `review_YYYY-MM-DD.md` | Human-readable report |
| `suggestions_YYYY-MM-DD.json` | Proposed improvements |

## 3. Patch Phase

The Config Patch Generator converts suggestions to structured patches:

```bash
# Generate patches from suggestions
python -c "
from briefai.review.config_patch import generate_config_patches
from pathlib import Path
generate_config_patches(Path('data/reviews/suggestions_2026-02-25.json'))
"
```

### Patch Format

```json
{
  "patch_id": "patch_abc123",
  "config_file": "config/signal_config.json",
  "parameter_path": "confidence.global_multiplier",
  "old_value": 1.0,
  "proposed_value": 0.85,
  "rationale": "Calibration error of 0.28 indicates overconfidence",
  "source_suggestion_id": "sug_xyz789",
  "requires_manual_review": true
}
```

### Supported Patch Targets

| Target | Config File | Parameters |
|--------|-------------|------------|
| `confidence_cap` | signal_config.json | global_multiplier, bucket_caps |
| `mechanism_weight` | mechanism_taxonomy.json | mechanisms.{name}.weight |
| `media_only_threshold` | evidence_weights.json | validation.media_only |
| `check_date_policy` | signal_config.json | prediction.default_timeframe_days |
| `signal_retention` | signal_config.json | storage.signal_retention_days |

## 4. Evolve Phase (Human Approval Required)

The Engine Evolution system applies approved patches:

```bash
# Validate a patch file
python -m briefai evolve --validate data/reviews/config_patch_2026-02-25.json

# Preview changes (dry run)
python -m briefai evolve --dry-run data/reviews/config_patch_2026-02-25.json

# Apply patches (requires confirmation)
python -m briefai evolve --apply-patch data/reviews/config_patch_2026-02-25.json
```

### What Happens

1. **Validation**: Checks patch file, config files, parameter paths
2. **Application**: Updates config JSON files
3. **Git Commit**: Creates commit with patch details
4. **Git Tag**: Creates `ENGINE_vX.Y_LEARNING_N` tag

### Example Tag

```
ENGINE_v2.2_LEARNING_1
ENGINE_v2.2_LEARNING_2
ENGINE_v2.2_LEARNING_3
```

## 5. New Engine

After evolution, the engine uses updated parameters:
- Adjusted confidence multipliers
- Modified mechanism weights
- Updated validation thresholds

**Future predictions use the new configuration, but historical ledgers are NEVER modified.**

## Learning Status Report

Monitor rolling performance with:

```bash
python scripts/generate_learning_status.py --days 30
```

Outputs `data/reviews/learning_status.md` with:
- Rolling 30-day accuracy
- Calibration error trend
- Top/worst performing mechanisms
- Overconfidence metric

## Integration with Daily Pipeline

Add to `daily_bloomberg.ps1`:

```powershell
# Run daily review (if expired predictions exist)
python scripts/run_daily_review.py --experiment v2_2_forward_test

# Generate learning status
python scripts/generate_learning_status.py
```

## Safety Constraints

1. **No Auto-Apply**: Patches always require human approval
2. **No Ledger Modification**: Historical predictions never changed
3. **Reproducibility**: Every change is tagged and committed
4. **No LLM Calls**: All analysis is deterministic

## Example Workflow

```bash
# Day 1: Predictions made
# ...

# Day 15: Predictions expire, run review
python scripts/run_daily_review.py --experiment v2_2_forward_test --verbose

# Review output
cat data/reviews/review_2026-02-25.md

# Generate patches
python -c "
from briefai.review.config_patch import generate_config_patches
from pathlib import Path
generate_config_patches(Path('data/reviews/suggestions_2026-02-25.json'))
"

# Review patches
cat data/reviews/config_patch_2026-02-25.json

# Dry run
python -m briefai evolve --dry-run data/reviews/config_patch_2026-02-25.json

# Apply (after human review)
python -m briefai evolve --apply-patch data/reviews/config_patch_2026-02-25.json

# Verify
git log --oneline -1
git describe --tags
```

## Data Flow Diagram

```
READ ONLY                              WRITE TO
─────────                              ────────
forecast_history.jsonl ──┐
                         │
meta_signals/*.json ─────┼───► Review  ───► data/reviews/
                         │     System       ├── review_*.json
insights/*.json ─────────┤                  ├── review_*.md
                         │                  ├── suggestions_*.json
briefs/*.json ───────────┘                  └── config_patch_*.json
                                                      │
                                                      ▼ (human approval)
                                            Evolve ───► config/*.json
                                            System      git commit
                                                        git tag
```

## Versioning

| Component | Version |
|-----------|---------|
| Review System | 1.1.0 |
| Config Patch | 1.0.0 |
| Evolve System | 1.0.0 |

Tags follow: `ENGINE_v{MAJOR}.{MINOR}_LEARNING_{N}`

Where:
- `MAJOR.MINOR` = base engine version
- `N` = sequential learning iteration count
