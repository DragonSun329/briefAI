# Experiment Reproducibility Guide

> How briefAI achieves research-grade reproducibility for forward-test experiments.

## Overview

briefAI is designed as a **publishable forecasting experiment**, not just a software tool. This means every prediction must be:

- **Auditable**: Complete provenance trail
- **Reproducible**: Same code → same methodology
- **Tamper-evident**: No post-hoc modifications possible
- **Externally verifiable**: Third parties can validate

This document explains the systems that enforce these properties.

---

## The Three Pillars

### 1. Run Lock (`utils/run_lock.py`)

**Purpose**: Prevents pipeline execution unless experimental conditions are met.

**Checks performed**:

| Check | What It Does | Failure Consequence |
|-------|--------------|---------------------|
| Active Experiment | Verifies `experiments.json` has active experiment | Pipeline aborts |
| Engine Tag | Confirms HEAD is descendant of engine tag | Pipeline aborts |
| Clean Tree | No modified `.py`, `.json`, `.md` in source dirs | Pipeline aborts |
| Git Access | Can read commit hash | Pipeline aborts |

**Usage**:

```python
from utils.run_lock import verify_run_integrity, require_run_integrity

# Option 1: Check and handle
report = verify_run_integrity()
if not report.valid:
    report.print_report()
    sys.exit(1)

# Option 2: Auto-abort on failure
report = require_run_integrity()  # Raises RuntimeError if invalid

# Option 3: Context manager
from utils.run_lock import RunLock
with RunLock() as lock:
    # Pipeline code here
    print(lock.report.experiment_id)
```

**Output Example**:

```
============================================================
✅ RUN INTEGRITY VERIFIED
============================================================
  Experiment:  v2_1_forward_test
  Engine Tag:  ENGINE_v2.1_DAY0
  Commit:      8eae743
  Verified:    2026-02-10T12:00:00Z
============================================================
```

### 2. Artifact Contract (`utils/run_artifact_contract.py`)

**Purpose**: Guarantees every run produces complete, valid outputs.

**Required Artifacts**:

| Artifact | Location | Format | Purpose |
|----------|----------|--------|---------|
| `forecast_history.jsonl` | Experiment ledger | JSONL | Append-only prediction log |
| `daily_snapshot_YYYY-MM-DD.json` | Experiment ledger | JSON | Frozen daily predictions |
| `run_metadata_YYYY-MM-DD.json` | Experiment ledger | JSON | Complete run context |
| `daily_brief_YYYY-MM-DD.md` | `data/reports/` | Markdown | Human-readable report |

**Verification Process**:

```python
from utils.run_artifact_contract import verify_run_artifacts, require_run_artifacts

# Check artifacts for today
report = verify_run_artifacts()
if not report.all_passed:
    report.print_report()
    # Handle failure

# Or auto-raise on failure
report = require_run_artifacts()  # Raises RunArtifactViolation
```

**Run Metadata Schema**:

```json
{
  "experiment_id": "v2_1_forward_test",
  "engine_tag": "ENGINE_v2.1_DAY0",
  "commit_hash": "8eae743...",
  "generation_timestamp": "2026-02-10T12:00:00Z",
  "date": "2026-02-10",
  "artifact_contract_passed": true,
  "sources": {
    "reddit": 575,
    "github": 171,
    "arxiv": 251,
    "news": 534
  },
  "scraper_failures": [],
  "duration_seconds": 180.5
}
```

### 3. Methodology Export (`scripts/generate_experiment_methodology.py`)

**Purpose**: Generates academic-style methodology documentation.

**Output Location**: `data/public/experiments/{experiment_id}/METHODOLOGY.md`

**Sections Generated**:

1. **Experiment Purpose**: Objective and design
2. **Forecasting Engine**: Architecture and determinism
3. **Data Sources**: Collection methodology
4. **Prediction Specification**: Types and structure
5. **Verification Methodology**: Evaluation rules
6. **Calibration Methodology**: Accuracy measurement
7. **Reproducibility Guarantee**: How to reproduce
8. **Appendices**: Glossary, file locations, audit trail

**Usage**:

```bash
# Generate for active experiment
python scripts/generate_experiment_methodology.py

# Generate for specific experiment
python scripts/generate_experiment_methodology.py --experiment v3_0_action_test

# Generate for all experiments
python scripts/generate_experiment_methodology.py
```

---

## Pipeline Integration

The pipeline should integrate these systems as follows:

```
┌─────────────────────────────────────────────────────────┐
│                    PIPELINE START                        │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
              ┌──────────────────────┐
              │  verify_run_integrity │
              │  (Run Lock)           │
              └──────────┬───────────┘
                         │
                    ┌────┴────┐
                    │ Valid?  │
                    └────┬────┘
                    No   │   Yes
                    │    │
              ┌─────┘    └─────┐
              ▼                ▼
        ┌──────────┐    ┌──────────────┐
        │  ABORT   │    │ Run Scrapers │
        └──────────┘    └──────┬───────┘
                               │
                               ▼
                       ┌───────────────┐
                       │ Process Data  │
                       │ (signals,     │
                       │  meta, hypo)  │
                       └───────┬───────┘
                               │
                               ▼
                       ┌───────────────┐
                       │ Write Outputs │
                       └───────┬───────┘
                               │
                               ▼
              ┌────────────────────────────┐
              │  verify_run_artifacts      │
              │  (Artifact Contract)       │
              └────────────┬───────────────┘
                           │
                      ┌────┴────┐
                      │ Valid?  │
                      └────┬────┘
                      No   │   Yes
                      │    │
                ┌─────┘    └─────┐
                ▼                ▼
          ┌───────────┐   ┌─────────────────┐
          │ Mark run  │   │ Write metadata  │
          │ as failed │   │ (contract=true) │
          └───────────┘   └─────────────────┘
                               │
                               ▼
                       ┌───────────────┐
                       │ Append Ledger │
                       └───────┬───────┘
                               │
                               ▼
              ┌────────────────────────────┐
              │  PIPELINE COMPLETE         │
              └────────────────────────────┘
```

---

## Experimental Isolation

### Why Isolation Matters

Different forecasting models cannot share the same ledger because:

1. **Model Contamination**: Can't compare v2.1 vs v3.0 if mixed
2. **Calibration Confusion**: Metrics would be meaningless
3. **Audit Failure**: Can't prove which model made which prediction

### How Isolation Works

```
data/public/
├── public_index.json          # Lists all experiments
├── experiments/
│   ├── v2_1_forward_test/     # Experiment A
│   │   ├── forecast_history.jsonl
│   │   ├── daily_snapshot_2026-02-10.json
│   │   ├── run_metadata_2026-02-10.json
│   │   └── METHODOLOGY.md
│   └── v3_0_action_test/      # Experiment B
│       ├── forecast_history.jsonl
│       ├── daily_snapshot_2026-02-11.json
│       ├── run_metadata_2026-02-11.json
│       └── METHODOLOGY.md
└── [legacy files preserved]
```

### Switching Experiments

```python
from utils.experiment_manager import set_active_experiment

# Switch to v3.0 experiment
set_active_experiment('v3_0_action_test')

# All future writes go to v3_0_action_test ledger
```

---

## Verification Workflow

### For Internal Review

```bash
# 1. Verify run integrity
python -c "from utils.run_lock import require_run_integrity; require_run_integrity()"

# 2. After run, verify artifacts
python -c "from utils.run_artifact_contract import require_run_artifacts; require_run_artifacts()"

# 3. Generate methodology
python scripts/generate_experiment_methodology.py
```

### For External Auditors

A third party can verify experiment integrity:

```bash
# 1. Clone and checkout engine tag
git clone https://github.com/[repo]/briefAI.git
git checkout ENGINE_v2.1_DAY0

# 2. Verify forecast_history.jsonl integrity
# - Check file hash
# - Verify append-only (no deletions in git history)
# - Cross-reference with daily snapshots

# 3. Verify predictions match methodology
# - Check confidence formula matches documented
# - Verify evaluation thresholds match documented
# - Confirm no LLM calls in core logic

# 4. Reproduce a single day
# - Run pipeline with --date flag
# - Compare structure (not exact data)
```

---

## Common Issues

### "Run integrity failed: dirty_working_tree"

**Cause**: Modified source files not committed.

**Fix**:
```bash
git add -A
git commit -m "chore: pre-run commit"
```

### "Run integrity failed: not_descendant_of_engine_tag"

**Cause**: Current HEAD is not at or after the experiment's engine tag.

**Fix**:
```bash
# Option 1: Checkout correct tag
git checkout ENGINE_v2.1_DAY0

# Option 2: Create new experiment for current code
```

### "Artifact contract violated"

**Cause**: Pipeline didn't produce all required files.

**Fix**:
- Check logs for scraper failures
- Verify disk space
- Re-run pipeline

---

## Best Practices

1. **Always commit before running pipeline**
   - Ensures exact reproducibility
   - Creates audit trail

2. **Tag engine versions explicitly**
   - Before any code changes
   - Use semantic naming: `ENGINE_v2.1_DAY0`

3. **Never edit forecast_history.jsonl**
   - Append-only is enforced by convention
   - Git history proves integrity

4. **Generate methodology after engine changes**
   - Documents what the new version does
   - Provides external verification reference

5. **Compare experiments fairly**
   - Same time period
   - Same evaluation thresholds
   - Separate ledgers

---

## Summary

briefAI's reproducibility layer converts it from a "cool project" into a "publishable experiment" by:

| Property | How Achieved |
|----------|--------------|
| **Auditable** | Git commit in every prediction |
| **Reproducible** | Engine tags, deterministic logic |
| **Tamper-evident** | Append-only ledgers, artifact contracts |
| **Publishable** | Auto-generated methodology docs |

This allows claims like:

> "briefAI predicted X before mainstream media, with Y% calibrated accuracy,
> using pre-committed models that can be independently verified."

That statement is now **provable**, not just a claim.
