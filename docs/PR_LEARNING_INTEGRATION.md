# PR: Learning Integration — Config Patches, Evolution System, Status Reports

## Summary

Implements the complete Learning Loop connecting review suggestions to reproducible, human-approved engine evolution.

## Components

### 1. Config Patch Generator

**File:** `briefai/review/config_patch.py`

Converts review suggestions into structured config patches.

```bash
# Generate patches from suggestions
python -c "
from briefai.review.config_patch import generate_config_patches
from pathlib import Path
generate_config_patches(Path('data/reviews/suggestions_2026-02-25.json'))
"
```

**Output:** `data/reviews/config_patch_YYYY-MM-DD.json`

**Patch format:**
```json
{
  "patch_id": "patch_e80d3948bdec",
  "config_file": "config/signal_config.json",
  "parameter_path": "confidence.global_multiplier",
  "old_value": 1.0,
  "proposed_value": 0.85,
  "rationale": "Calibration error of 0.28 indicates overconfidence",
  "source_suggestion_id": "sug_859d04ea96f4",
  "requires_manual_review": true,
  "is_actionable": true
}
```

**Supported targets:**
| Target | Config File | Parameters |
|--------|-------------|------------|
| `confidence_cap` | signal_config.json | global_multiplier, bucket_caps |
| `mechanism_weight` | mechanism_taxonomy.json | mechanisms.{name}.weight |
| `media_only_threshold` | evidence_weights.json | validation.media_only |
| `check_date_policy` | signal_config.json | prediction.default_timeframe_days |
| `signal_retention` | signal_config.json | storage.signal_retention_days |

### 2. Engine Evolution Protocol

**Files:** `briefai/evolve/__init__.py`, `briefai/evolve/cli.py`

**CLI:**
```bash
# Validate patch file
python -m briefai evolve --validate data/reviews/config_patch_2026-02-25.json

# Dry-run (preview changes)
python -m briefai evolve --dry-run data/reviews/config_patch_2026-02-25.json

# Apply patches (requires confirmation)
python -m briefai evolve --apply-patch data/reviews/config_patch_2026-02-25.json
```

**What happens on apply:**
1. Validate all patches
2. Apply changes to config files
3. Create git commit with details
4. Create tag: `ENGINE_vX.Y_LEARNING_N`

**Tag format:** `ENGINE_v2.2_LEARNING_1`, `ENGINE_v2.2_LEARNING_2`, etc.

### 3. Conditional Daily Review

**File:** `scripts/run_daily_review.py` (updated)

```bash
python scripts/run_daily_review.py --experiment v2_2_forward_test
```

**Behavior:**
- Checks for expired predictions
- If none exist: `"No expired predictions — review skipped."`
- If found: runs full review pipeline

### 4. Learning Status Report

**File:** `scripts/generate_learning_status.py`

```bash
python scripts/generate_learning_status.py --days 30
```

**Output:** `data/reviews/learning_status.md`

**Includes:**
- Rolling 30-day accuracy
- Calibration error
- Top performing mechanisms
- Worst performing mechanisms
- Overconfidence metric

### 5. Documentation

**File:** `docs/LEARNING_LOOP.md`

Comprehensive documentation of the complete loop:
```
Prediction → Review → Patch → Evolve → New Engine
```

## Files Created/Modified

| File | Action |
|------|--------|
| `briefai/review/config_patch.py` | New |
| `briefai/evolve/__init__.py` | New |
| `briefai/evolve/cli.py` | New |
| `scripts/generate_learning_status.py` | New |
| `docs/LEARNING_LOOP.md` | New |
| `docs/PR_LEARNING_INTEGRATION.md` | New (this file) |
| `tests/test_learning_integration.py` | New |
| `scripts/run_daily_review.py` | Updated |
| `briefai/__main__.py` | Updated (added evolve command) |
| `briefai/review/__init__.py` | Updated (exports config_patch) |

## Tests

**Total:** 70 tests (50 existing + 20 new)

New test classes in `test_learning_integration.py`:
- `TestConfigPatchGeneration` — patch conversion
- `TestPatchValidation` — validation logic
- `TestEvolutionCLI` — CLI functions
- `TestConfigMappings` — mapping definitions
- `TestPatchSafety` — safety constraints
- `TestDeterminism` — reproducibility

## Example Workflow

```bash
# 1. Run daily review (predictions expire)
python scripts/run_daily_review.py --experiment v2_2_forward_test

# 2. Generate config patches from suggestions
python -c "
from briefai.review.config_patch import generate_config_patches
from pathlib import Path
generate_config_patches(Path('data/reviews/suggestions_2026-02-25.json'))
"

# 3. Review the patches
cat data/reviews/config_patch_2026-02-25.json

# 4. Validate
python -m briefai evolve --validate data/reviews/config_patch_2026-02-25.json

# 5. Dry-run
python -m briefai evolve --dry-run data/reviews/config_patch_2026-02-25.json

# 6. Apply (human decision)
python -m briefai evolve --apply-patch data/reviews/config_patch_2026-02-25.json

# 7. Check learning status
python scripts/generate_learning_status.py
```

## Safety Constraints

- ✅ **No Auto-Apply**: All patches require `--apply-patch` with confirmation
- ✅ **No Ledger Modification**: Historical predictions never touched
- ✅ **Reproducibility**: Every evolution is git committed and tagged
- ✅ **No LLM Calls**: All analysis is deterministic
- ✅ **Patch Safety**: All patches have `requires_manual_review: true`

## Data Flow

```
READ ONLY                           WRITE TO
─────────                           ────────
suggestions_*.json ───► Patch  ───► config_patch_*.json
                        Gen            │
                                       ▼ (human approval)
config/*.json ────────► Evolve ────► config/*.json (updated)
                        System        git commit
                                      git tag

review_*.json ────────► Status ────► learning_status.md
                        Report
```

## Integration with daily_bloomberg.ps1

```powershell
# Run daily review
python scripts/run_daily_review.py --experiment v2_2_forward_test

# Generate learning status
python scripts/generate_learning_status.py

# Optional: Generate patches (for human review)
# python -c "from briefai.review.config_patch import generate_config_patches; ..."
```

## Version

All components are v1.0.0 except:
- Review System: v1.2.0 (added config_patch integration)
