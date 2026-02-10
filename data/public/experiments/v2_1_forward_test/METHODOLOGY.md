# Experiment Methodology: v2_1_forward_test

> Auto-generated methodology documentation for the **Narrative + metric prediction engine (Genesis)** forward-test experiment.

**Generated**: 2026-02-10 08:43:25 UTC  
**Engine Tag**: `ENGINE_v2.1_DAY0`  
**Start Date**: 2026-02-10  
**Status**: active

---

## 1. Experiment Purpose

### 1.1 Objective

This experiment evaluates the predictive accuracy of the briefAI forecasting system using a **forward-test** methodology. Unlike backtesting, forward-testing:

- Makes predictions **before** outcomes are known
- Freezes predictions at generation time (append-only ledger)
- Evaluates predictions only after the observation window expires
- Prevents look-ahead bias and p-hacking

### 1.2 Experiment Description

> Narrative + metric prediction engine (Genesis)

### 1.3 Prediction Types

This experiment generates the following prediction types:

- **Metric Trends**: Predictions about directional changes in measurable quantities (e.g., article count, stock price, job postings)
- **Media Attention**: Predictions about changes in media coverage patterns

## 2. Forecasting Engine

### 2.1 Engine Identification

| Property | Value |
|----------|-------|
| Engine Tag | `ENGINE_v2.1_DAY0` |
| Version | 2.1 |
| Reproducibility | Git tag frozen at experiment start |

### 2.2 Engine Architecture

The forecasting engine operates in multiple stages:

1. **Signal Collection**: Scrapes data from configured sources
2. **Signal Aggregation**: Clusters related signals into meta-signals
3. **Mechanism Detection**: Identifies causal mechanisms using keyword taxonomy
4. **Hypothesis Generation**: Creates testable hypotheses with predictions
5. **Prediction Registration**: Logs predictions to append-only ledger

### 2.3 Determinism

The engine is designed to be **deterministic**:

- No LLM calls in core prediction logic
- Rule-based mechanism detection
- Keyword-based pattern matching
- Fixed confidence scoring formula

This ensures that given the same input data and engine version, the same predictions will be generated.

## 3. Data Sources

### 3.1 Source Categories

The system collects data from multiple source types:

| Category | Description |
|----------|-------------|
| News | Tech news sites, RSS feeds |
| Social | Reddit, Twitter, HackerNews |
| Research | arXiv, Papers with Code |
| Financial | Yahoo Finance, SEC filings |
| Prediction Markets | Polymarket, Metaculus, Manifold |
| Developer | GitHub, HuggingFace, npm/PyPI |
| Alternative | Job postings, patents, app stores |

### 3.2 Collection Frequency

- **Daily scraping**: All sources scraped once per day
- **Deduplication**: Cross-source deduplication prevents double-counting
- **Storage**: Raw data stored in `data/` directory by date

### 3.3 Data Quality Controls

- Source credibility weighting
- Sentiment analysis validation
- Entity extraction verification
- Cross-source signal correlation

## 4. Prediction Specification

### 4.1 Prediction Structure

Each prediction includes:

| Field | Description |
|-------|-------------|
| `prediction_id` | Unique identifier (SHA-256 hash) |
| `experiment_id` | Parent experiment |
| `hypothesis_id` | Parent hypothesis |
| `entity` | Primary entity (e.g., "nvidia") |
| `canonical_metric` | Standardized metric name |
| `expected_direction` | "up", "down", or "flat" |
| `confidence` | Probability estimate (0-1) |
| `window_days` | Observation window |
| `created_at` | ISO timestamp |
| `evaluation_due` | When to evaluate |

### 4.2 Metric Trend Predictions

Metric trend predictions forecast directional changes in measurable quantities.

**Canonical Metrics** (standardized vocabulary):


## 5. Verification Methodology

### 5.1 Evaluation Timing

Predictions are evaluated **only after** the observation window expires:

- `evaluation_due = created_at + window_days`
- No predictions are evaluated early
- No predictions are modified after creation

### 5.2 Direction Evaluation Thresholds

| Outcome | Condition |
|---------|-----------|
| **Verified True** | Actual change ≥ 15% in predicted direction |
| **Verified False** | Actual change ≥ 15% in opposite direction |
| **Inconclusive** | Change < 15% (insufficient signal) |
| **Data Missing** | Unable to obtain metric value |

### 5.3 Evaluation Process

```
1. Retrieve baseline value (value at prediction time)
2. Retrieve current value (value at evaluation time)
3. Calculate percent change: (current - baseline) / baseline
4. Compare against expected direction
5. Apply threshold rules
6. Record verdict and evidence
```

### 5.4 No Retroactive Changes

The append-only ledger ensures:

- Predictions cannot be modified after creation
- Evaluations cannot be changed after recording
- Complete audit trail is preserved
- External observers can verify integrity

## 6. Calibration Methodology

### 6.1 Calibration Definition

A forecasting system is **well-calibrated** when:

> For predictions with confidence X%, approximately X% are verified true.

Example: Of 100 predictions made with 70% confidence, ~70 should be verified true.

### 6.2 Calibration Metrics

| Metric | Description |
|--------|-------------|
| **Brier Score** | Mean squared error of probability forecasts (lower is better) |
| **Calibration Curve** | Plot of predicted vs. actual frequencies |
| **Reliability Diagram** | Binned calibration visualization |
| **Resolution** | Variance of predictions (measures informativeness) |

### 6.3 Confidence Scoring

Confidence is calculated as:

```
confidence = (meta_confidence × 0.55) +
             (category_diversity × 0.15) +
             (persistence × 0.10) +
             (independence × 0.10) +
             (specificity × 0.10)
```

Modifiers applied:
- Action prediction bonus: +12%
- Media-only cap: 45% maximum
- Generic prediction penalty: -10%
- Weak mechanism penalty: -10%

### 6.4 Calibration Feedback Loop

After sufficient predictions are evaluated:

1. Compute calibration curve
2. Identify over/under-confidence regions
3. Adjust confidence formula (new engine version)
4. Create new experiment for revised model

## 7. Reproducibility Guarantee

### 7.1 Reproduction Steps

A third party can reproduce this experiment's predictions:

```bash
# 1. Clone repository
git clone https://github.com/[repo]/briefAI.git
cd briefAI

# 2. Checkout exact engine version
git checkout ENGINE_v2.1_DAY0

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set experiment
python -c "from utils.experiment_manager import set_active_experiment; set_active_experiment('v2_1_forward_test')"

# 5. Run pipeline
python scripts/daily_bloomberg.ps1
```

### 7.2 What Is Reproducible

| Component | Reproducible? | Notes |
|-----------|---------------|-------|
| Prediction structure | ✅ Yes | Same fields, formats |
| Confidence calculation | ✅ Yes | Deterministic formula |
| Mechanism detection | ✅ Yes | Rule-based, no LLM |
| Exact predictions | ❌ No | Data sources change daily |
| Methodology | ✅ Yes | Frozen at engine tag |

### 7.3 Integrity Verification

Each run produces metadata that enables verification:

- **Commit Hash**: Exact code version
- **Engine Tag**: Named version
- **Generation Timestamp**: When predictions were made
- **Artifact Contract**: Verification that all outputs exist

### 7.4 Append-Only Ledger

The `forecast_history.jsonl` file is append-only:

- New predictions are appended, never overwritten
- Historical predictions are never modified
- External observers can verify via file hash
- Git history provides additional verification

## Appendix A: Glossary

| Term | Definition |
|------|------------|
| **Forward-Test** | Prediction method where forecasts are made before outcomes |
| **Backtest** | Prediction method using historical data (prone to bias) |
| **Meta-Signal** | Aggregation of related individual signals |
| **Mechanism** | Causal pattern explaining signal cluster |
| **Canonical Metric** | Standardized metric from controlled vocabulary |
| **Observation Window** | Days between prediction and evaluation |
| **Calibration** | Agreement between confidence and accuracy |

## Appendix B: File Locations

| File | Description |
|------|-------------|
| `forecast_history.jsonl` | Append-only prediction ledger |
| `daily_snapshot_YYYY-MM-DD.json` | Daily prediction snapshot |
| `run_metadata_YYYY-MM-DD.json` | Run context and statistics |
| `daily_brief_YYYY-MM-DD.md` | Human-readable report |
| `METHODOLOGY.md` | This file |

## Appendix C: Audit Trail

To verify experiment integrity:

1. Check git history for engine tag
2. Verify `forecast_history.jsonl` is append-only
3. Cross-reference `run_metadata` commit hashes
4. Compare daily snapshots against ledger entries

---

*This methodology document was auto-generated by briefAI.*
*Last updated: 2026-02-10T08:43:25.058166 UTC*
