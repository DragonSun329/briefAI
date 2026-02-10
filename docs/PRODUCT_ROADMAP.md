# briefAI Product Roadmap

*From Research Project to Strategy Engine*

## Overview

The system has passed the intelligence threshold. The bottleneck is no longer understanding information — it's turning understanding into decisions and proving reliability.

## Phase 1: Analyst Brief ✅ COMPLETE

**The First Real Product Surface**

Before: Internal artifacts (cluster_feed, meta_signals, hypotheses, beliefs)
After: One human-readable daily report

### Output

```
data/briefs/analyst_brief_YYYY-MM-DD.md
```

### Sections

1. **What Actually Happened** — Top event clusters
2. **What Is Changing** — Trends ranked by belief × velocity × independence
3. **What We Think Will Happen** — Predictions with timeframes
4. **What Changed Today** — THE KILLER FEATURE

### The Killer Feature

```markdown
### Enterprise AI Adoption Accelerating

Confidence: 0.83 → 0.91 (+8%)

Reason: GitHub enterprise SDK activity +42% across 3 vendors

Evidence: 3 supporting, 0 contradicting
```

This is what humans check every day.

### Usage

```bash
python scripts/generate_analyst_brief.py
python scripts/generate_analyst_brief.py --date 2026-02-10
python scripts/generate_analyst_brief.py --print
```

## Phase 2: Decision Engine ✅ COMPLETE

**Map Beliefs to Actions**

Before: "What is happening?"
After: "What should I do?"

### File

```
utils/decision_engine.py
```

### Signal → Action Mapping

| Signal | Decision |
|--------|----------|
| infra_scaling ↑ | Buy semiconductor suppliers |
| enterprise_adoption ↑ | B2B SaaS expansion |
| pricing_compression ↑ | Avoid foundation model startups |
| distribution_shift ↑ | Invest in application layer |

### Brief Section 5: Recommended Actions

```markdown
### 📈 Positive exposure to AI infrastructure providers

Confidence: 74%
Sector: semiconductors
Timeframe: medium term

Supporting signals:
- NVIDIA compute demand ↑
- Datacenter capex ↑
- Cloud GPU backlog ↑

Rationale: Infrastructure scaling signals increased compute demand
```

## Phase 3: Forecast Calibration ✅ COMPLETE

**The Real Moat**

The most important feature: measuring and improving forecast accuracy.

### File

```
utils/forecast_calibration.py
```

### Metrics Computed

- **Brier Score**: Mean squared error of probability predictions
- **Reliability Curve**: Predicted probability vs actual outcome by bin
- **Overconfidence Penalty**: How much system overestimates
- **Per-Mechanism Accuracy**: Which mechanisms predict best
- **Calibration Factor**: Automatic confidence adjustment

### How It Works

```python
# System learns it's overconfident
calibration_factor = 0.85  # Raw confidence × 0.85

# Per-mechanism adjustments
infra_scaling_factor = 0.92  # This mechanism is well-calibrated
competitive_pressure_factor = 0.68  # This mechanism is overconfident
```

### Brief Section: System Calibration

```markdown
## System Calibration

Last Updated: 2026-02-10
Sample Size: 127 predictions

Forecast Quality: Good (Brier score: 0.182)

Calibration: Overconfident - reducing raw confidence (factor: 0.87)

Mechanism Accuracy:
- infra_scaling: 78% (45 samples)
- enterprise_adoption: 72% (32 samples)
- pricing_compression: 61% (18 samples)
```

### This Is The Difference Between

- News aggregator ❌
- Forecasting engine ✅

## Phase 4: UI (NOT YET)

**Only After Calibration Has Data**

### The Belief Dashboard

3 charts only:
1. Top active beliefs
2. Confidence over time
3. Evidence accumulation

That alone is a viable paid product.

### When to Build

- Wait for 100+ evaluated predictions
- Wait for calibration state to stabilize
- Wait for belief trajectories to have history

## Phase 5: Data Advantage (FUTURE)

**The Real Long-Term Play**

News reports after reality. Markets move when reality changes.

### Highest Value Additions

| Source | Lead Time | Difficulty |
|--------|-----------|------------|
| GitHub org-level activity | 2-4 weeks | Medium |
| Job postings | 3-6 weeks | Medium |
| Earnings call transcripts | 1-2 weeks | Easy |
| Developer docs updates | 1-4 weeks | Medium |
| Hiring headcount growth | 4-8 weeks | Hard |

### Goal

Signals that occur before TechMeme.

## What NOT To Do

❌ Add more scoring dimensions
❌ Improve clustering
❌ Tune embeddings
❌ Add another agent layer

You already passed the intelligence threshold.

## Current Status

| Phase | Status | File(s) |
|-------|--------|---------|
| 1. Analyst Brief | ✅ Complete | `scripts/generate_analyst_brief.py` |
| 2. Decision Engine | ✅ Complete | `utils/decision_engine.py` |
| 3. Calibration | ✅ Complete | `utils/forecast_calibration.py` |
| 4. Evidence Engine | ✅ Complete | `utils/evidence_engine.py` |
| 5. Validation Layer | ✅ Complete | See below |
| 6. UI | ⏳ Waiting for data | - |
| 7. Data Advantage | 🔮 Future | - |

## Phase 5: Validation & Public Credibility Layer ✅ COMPLETE

**Prove the system works with verifiable public records.**

### Components

| Component | File | Purpose |
|-----------|------|---------|
| Historical Replay | `utils/historical_replay_runner.py` | Backtest with temporal causality |
| Public Forecast Log | `utils/public_forecast_logger.py` | Append-only audit trail |
| Lead-Time Evaluator | `utils/lead_time_evaluator.py` | Measure prediction earliness |
| Calibration Report | `scripts/generate_calibration_report.py` | Bucket-by-bucket accuracy |
| Methodology Export | `scripts/export_methodology.py` | Auto-generate research docs |

### Data Outputs

```
data/
├── backtest/                    # Historical replay results
│   └── YYYY-MM-DD/
│       ├── signals.json
│       ├── metas.json
│       ├── hypotheses.json
│       └── predictions.json
├── public/
│   └── forecast_history.jsonl   # Append-only public ledger
└── metrics/
    ├── calibration_report.json
    └── lead_time_report.json
```

### Key Metrics

1. **Lead Time** — Days before event confirmation
2. **Calibration** — Confidence vs. actual accuracy by bucket
3. **Brier Score** — Overall forecast quality (lower = better)
4. **Early Detection Rate** — % with 7+ day lead time

### Usage

```bash
# Run historical replay
python scripts/run_historical_replay.py --start 2025-11-01 --end 2026-02-01

# Generate calibration report
python scripts/generate_calibration_report.py --print

# Export methodology
python scripts/export_methodology.py
```

### Documentation

```
docs/briefai_methodology.md      # Auto-generated research methodology
```

## Running the Daily Brief

```bash
# Generate today's brief
python scripts/generate_analyst_brief.py

# Output: data/briefs/analyst_brief_2026-02-10.md
```

## File Structure

```
briefAI/
├── scripts/
│   ├── generate_analyst_brief.py        # Phase 1: The product
│   ├── generate_briefs.py               # Multi-audience briefs
│   ├── run_historical_replay.py         # Phase 5: Backtest runner
│   ├── generate_calibration_report.py   # Phase 5: Calibration metrics
│   └── export_methodology.py            # Phase 5: Research docs
├── utils/
│   ├── decision_engine.py               # Phase 2: Actions
│   ├── forecast_calibration.py          # Phase 3: Calibration
│   ├── evidence_engine.py               # Phase 4: Evidence processing
│   ├── belief_updater.py                # Phase 4: Bayesian updates
│   ├── historical_replay_runner.py      # Phase 5: Temporal replay
│   ├── public_forecast_logger.py        # Phase 5: Audit trail
│   └── lead_time_evaluator.py           # Phase 5: Lead time metrics
├── config/
│   ├── decision_rules.json              # Action mappings
│   └── evidence_weights.json            # Signal importance
├── docs/
│   └── briefai_methodology.md           # Auto-generated research docs
└── data/
    ├── briefs/                          # Daily briefs
    │   └── analyst_brief_YYYY-MM-DD.md
    ├── backtest/                        # Historical replay results
    │   └── YYYY-MM-DD/
    ├── public/                          # Public audit trail
    │   └── forecast_history.jsonl
    └── metrics/
        ├── calibration_state.json
        ├── calibration_report.json
        └── lead_time_report.json
```

## The Product Is The Brief

Everything else is infrastructure.

The brief is what humans read.
The brief is what proves value.
The brief is the product.
