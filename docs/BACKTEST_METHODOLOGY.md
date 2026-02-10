# Backtest Methodology

**Date**: 2026-01-27  
**Version**: 2.0  
**Status**: Active

---

## Executive Summary

This document describes the rigorous backtesting methodology used in briefAI to validate signal accuracy before deployment. Our approach combines walk-forward validation, statistical hypothesis testing, and probability calibration to ensure predictions meet publication-quality standards.

### Key Principles

1. **No Lookahead Bias**: Walk-forward validation ensures predictions only use past data
2. **Statistical Rigor**: All results include p-values and confidence intervals
3. **Minimum Sample Sizes**: Flag any results with n < 30
4. **Significance Threshold**: Require p < 0.05 for publication
5. **Probability Calibration**: Track Brier scores for forecast accuracy

---

## Ground Truth Dataset

### Overview

| Metric | Value |
|--------|-------|
| Total Events | 155 |
| Time Period | 2024-01-01 to 2026-01-27 |
| Event Types | funding, product_launch, partnership, negative, regulatory, earnings |
| Categories | llm, robotics, video, image, audio, code-ai, infrastructure, etc. |

### Event Type Distribution

| Type | Count | Description |
|------|-------|-------------|
| funding | 68 | VC funding rounds, investments |
| product_launch | 42 | New product/model releases |
| partnership | 18 | Strategic partnerships, integrations |
| negative | 15 | Layoffs, delays, controversies |
| regulatory | 12 | Legal cases, regulations |

### Data Sources

1. **Curated Events** (high confidence)
   - Major AI funding rounds from Bloomberg, WSJ, TechCrunch
   - Product launches from official announcements
   - Verified dates from multiple sources

2. **Crunchbase API** (medium confidence)
   - Funding rounds > $10M
   - AI/ML company classifications
   - Automated date extraction

3. **News Archives** (validated)
   - Cross-referenced with multiple outlets
   - Breakout dates verified against mainstream coverage

---

## Walk-Forward Validation

### Why Walk-Forward?

Traditional train/test splits can leak future information into the training process. Walk-forward validation mimics real-world deployment:

```
Time →
|--------- Train (70%) ---------|--- Validate (30%) ---|
                               Cutoff
```

Each fold uses only past data to predict future events.

### Implementation

```python
from utils.statistical_validation import WalkForwardValidator

validator = WalkForwardValidator(
    train_ratio=0.7,      # 70% for training
    min_train_size=30,    # Minimum samples before validation
    step_days=7           # Weekly prediction cadence
)

# Create train/validate splits
splits = validator.create_splits(events, date_field="breakout_date")

# Run validation
results = validator.run_walk_forward(events, prediction_func)
```

### Expanding Window Approach

We use an expanding window (not rolling) to maximize training data:

| Fold | Train Events | Validate Events | Cutoff Date |
|------|--------------|-----------------|-------------|
| 1 | 1-70 | 71-155 | 2024-09-15 |
| 2 | 1-85 | 86-155 | 2024-11-01 |
| 3 | 1-100 | 101-155 | 2024-12-15 |
| 4 | 1-115 | 116-155 | 2025-02-01 |
| 5 | 1-130 | 131-155 | 2025-03-15 |

---

## Statistical Methods

### Accuracy Confidence Intervals

We use Wilson score intervals for proportions (better than normal approximation for small samples):

```
p̂ ± z * sqrt(p̂(1-p̂)/n + z²/4n²) / (1 + z²/n)
```

Where:
- p̂ = observed proportion
- z = 1.96 for 95% CI
- n = sample size

### Hypothesis Testing

**Null Hypothesis**: Accuracy equals random guessing (50%)

**Test Statistic**: 
```
z = (p̂ - 0.5) / sqrt(0.25/n)
```

**Decision Rule**: Reject H₀ if p-value < 0.05

### Correlation Tests

For signal-outcome correlations, we use Pearson's r with t-test:

```
t = r * sqrt(n-2) / sqrt(1-r²)
df = n - 2
```

**Required for publication**:
- |r| > 0.3 (moderate correlation)
- p < 0.05 (statistically significant)
- n ≥ 30 (sufficient sample size)

### Multiple Testing Correction

When testing multiple horizons/categories, apply Bonferroni correction:

```
adjusted_alpha = 0.05 / number_of_tests
```

---

## Probability Calibration (Brier Score)

### What is Brier Score?

Brier Score measures how well-calibrated probability forecasts are:

```
BS = (1/n) * Σ(forecast_i - outcome_i)²
```

| Score | Interpretation |
|-------|---------------|
| < 0.10 | Excellent |
| 0.10-0.15 | Good |
| 0.15-0.20 | Acceptable |
| 0.20-0.25 | Fair |
| > 0.25 | Poor |

### Reliability Diagram

A well-calibrated model shows predictions matching observed frequencies:

```
Predicted Prob | Observed Freq | Calibration Error
0.1            | 0.12          | 0.02 ✓
0.3            | 0.28          | 0.02 ✓
0.5            | 0.53          | 0.03 ✓
0.7            | 0.65          | 0.05 ⚠
0.9            | 0.82          | 0.08 ⚠
```

### Implementation

```python
from utils.statistical_validation import BrierScoreTracker

brier = BrierScoreTracker()

for prediction in predictions:
    brier.add_prediction(
        entity_id=prediction.entity_id,
        predicted_probability=prediction.confidence,
        actual_outcome=1 if prediction.correct else 0,
        prediction_date=prediction.date,
        horizon_days=prediction.horizon
    )

# Get overall Brier score
score = brier.get_brier_score()

# Get calibration curve
curve = brier.get_calibration_curve(n_bins=10)
```

---

## Multi-Horizon Testing

### Horizons Tested

| Horizon | Use Case | Expected Accuracy |
|---------|----------|-------------------|
| 7 days | Short-term alerts | 40-50% |
| 14 days | News cycle | 50-60% |
| 30 days | Medium-term | 60-70% |
| 60 days | **Optimal** | **70-80%** |
| 90 days | Long-term | 75-85% |

### Running Multi-Horizon Backtest

```bash
python scripts/multi_horizon_backtest.py
python scripts/multi_horizon_backtest.py --horizons 30 60 90
python scripts/multi_horizon_backtest.py --start-date 2024-01-01 --output-format json
```

### Interpreting Results

```
Horizon    Accuracy    95% CI              P-value    Status
7d         45.2%       [38.1%, 52.5%]      0.1523     ⚠ Not sig.
14d        58.3%       [51.2%, 65.0%]      0.0234     ✓ Significant
30d        67.8%       [61.1%, 73.9%]      0.0001     ✓ Significant
60d        74.2%       [68.0%, 79.6%]      <0.0001    ✓ Significant
90d        79.1%       [73.2%, 84.1%]      <0.0001    ✓ Significant
```

---

## Quality Thresholds

### Publication Requirements

A result **PASSES** quality check if ALL of:

| Criterion | Threshold | Rationale |
|-----------|-----------|-----------|
| Sample Size | n ≥ 30 | CLT requires sufficient samples |
| P-value | p < 0.05 | Statistical significance |
| Accuracy | > 50% | Better than random |
| CI Width | < 20% | Precision requirement |

### Warning Flags

| Flag | Meaning | Action |
|------|---------|--------|
| `p > 0.05` | Not statistically significant | Collect more data |
| `n < 30` | Insufficient samples | Wait for more events |
| `CI > 20%` | Wide confidence interval | Need more precision |
| `Brier > 0.25` | Poor calibration | Adjust confidence scores |
| `Declining accuracy` | Temporal instability | Retrain model |

---

## Example Workflow

### 1. Expand Ground Truth

```bash
# Generate/update ground truth from sources
python scripts/expand_ground_truth.py

# Verify event count
cat config/ground_truth_expanded.json | jq '._meta.event_count'
# Should be: 155
```

### 2. Run Multi-Horizon Backtest

```bash
python scripts/multi_horizon_backtest.py
```

Output:
```
STATISTICAL SUMMARY
  Optimal Horizon: 60 days
  Optimal Accuracy: 74.2% [68.0%, 79.6%]
  Significant Tests: 4/5

RECOMMENDATIONS
  • Use 60-day horizon as primary (accuracy: 74.2%)
  • 30-day horizon is viable for faster signals (67.8%)
  • Probability calibration is good (Brier = 0.142)
```

### 3. Run Walk-Forward Validation

```bash
python scripts/backfill_predictions.py walk-forward --horizon 60
```

Output:
```
WALK-FORWARD VALIDATION
  Mean Accuracy: 72.3% ± 4.1%
  95% CI: [64.5%, 79.8%]
  P-value: 0.0003
  Temporal Stability: stable
```

### 4. Check for Warnings

```bash
python scripts/backfill_predictions.py validate
```

Review any warnings:
```
⚠ 7d horizon: accuracy not statistically significant (p=0.152)
⚠ robotics category: insufficient samples (n=12)
```

---

## Results Storage

### Directory Structure

```
data/backtests/
├── multi_horizon_backtest_2026-01-27.json
├── walk_forward_2026-01-27.json
├── horizon_comparison_2026-01-26.json
└── backtest_2024-12-01_2025-01-15.json
```

### JSON Schema

```json
{
  "meta": {
    "generated_at": "2026-01-27T10:30:00",
    "start_date": "2024-01-01",
    "end_date": "2025-12-31",
    "total_events": 155,
    "horizons_tested": [7, 14, 30, 60, 90]
  },
  "by_horizon": {
    "60": {
      "accuracy": 0.742,
      "ci_lower": 0.680,
      "ci_upper": 0.796,
      "p_value": 0.0001,
      "is_significant": true,
      "total_predictions": 523
    }
  },
  "statistical_summary": {
    "optimal_horizon": 60,
    "optimal_accuracy": 0.742,
    "significant_tests": 4,
    "total_tests": 5
  },
  "warnings": []
}
```

---

## Appendix: Key Formulas

### Wilson Score Interval
```
centre = (p + z²/2n) / (1 + z²/n)
margin = z * sqrt((p(1-p) + z²/4n) / n) / (1 + z²/n)
CI = [centre - margin, centre + margin]
```

### Brier Score
```
BS = (1/n) * Σ(f_i - o_i)²
where f_i = forecast, o_i = outcome (0 or 1)
```

### Pearson Correlation Test
```
r = Σ(x_i - x̄)(y_i - ȳ) / sqrt(Σ(x_i - x̄)² * Σ(y_i - ȳ)²)
t = r * sqrt(n-2) / sqrt(1-r²)
p = 2 * (1 - T.cdf(|t|, df=n-2))
```

### Bonferroni Correction
```
adjusted_alpha = alpha / k
where k = number of tests
```

---

## References

1. Wilson, E. B. (1927). Probable inference, the law of succession, and statistical inference. JASA.
2. Brier, G. W. (1950). Verification of forecasts expressed in terms of probability. Monthly Weather Review.
3. Bergmeir, C., & Benítez, J. M. (2012). On the use of cross-validation for time series predictor evaluation.

---

**Author**: briefAI Backtesting Framework  
**Last Updated**: 2026-01-27
