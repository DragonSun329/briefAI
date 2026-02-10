# Prediction Verification Engine (PVE)

*Part of Gravity Engine v2.7 - Predictive Foresight Layer*

## Overview

The Prediction Verification Engine (PVE) tracks, verifies, and calibrates predictions made by the Hypothesis Engine. This closes the feedback loop between prediction generation and outcome observation.

```
┌─────────────────────────────────────────────────────────────────┐
│                    PREDICTION LIFECYCLE                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Hypothesis     →   Prediction    →   Observation   →   Verdict │
│  Engine              Store              Metrics          Report  │
│                                                                  │
│  • Creates           • Tracks           • Collects       • verified_true  │
│    predictions         due dates          baseline       • verified_false │
│  • Registers         • Manages           current         • inconclusive   │
│    to store            status            values          • data_missing   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Components

### 1. Prediction Verifier (`utils/prediction_verifier.py`)

Core module for prediction tracking and evaluation.

**Key Classes:**
- `PredictionRecord` - Immutable prediction data structure
- `PredictionStore` - JSONL-based persistence layer
- `PredictionStatus` - pending, evaluated
- `PredictionVerdict` - verified_true, verified_false, inconclusive, data_missing

**Key Functions:**
- `register_predictions_from_bundle()` - Register predictions from hypothesis bundle
- `evaluate_prediction()` - Evaluate prediction against observed data
- `evaluate_direction()` - Determine verdict from percent change

### 2. Metric Observer (`utils/metric_observer.py`)

Data collection layer for prediction verification.

**Supported Metrics:**
| Metric | Source | Description |
|--------|--------|-------------|
| `article_count` | news | Article mentions in news database |
| `keyword_frequency` | news | Total keyword occurrences |
| `repo_activity` | github | GitHub repository signals |
| `filing_mentions` | sec | SEC filing mentions |
| `job_postings_count` | jobs | Job posting activity |
| `discussion_volume` | social | Social media mentions |

**Observers:**
- `NewsObserver` - News database queries
- `GitHubObserver` - Package/repo signals
- `SECObserver` - Financial filings
- `JobsObserver` - Job market data
- `SocialObserver` - Social sentiment

### 3. Calibration Engine (`utils/calibration_engine.py`)

System accuracy measurement and reporting.

**Metrics Computed:**
- **Accuracy** - Correct predictions / Total evaluated
- **Precision** - True positives / Predicted positives
- **Recall** - True positives / Actual positives
- **Brier Score** - Mean squared error of probability predictions
- **Calibration Curve** - Binned accuracy vs confidence

**Breakdowns:**
- By mechanism (infra_scaling, regulatory_shift, etc.)
- By category (financial, technical, media, etc.)
- By metric type (article_count, filing_mentions, etc.)
- Weekly time series

### 4. Verification Scheduler (`scripts/run_prediction_verification.py`)

Daily/weekly workflow script.

```powershell
# Normal run - evaluate due predictions
python scripts/run_prediction_verification.py

# Force evaluate all pending
python scripts/run_prediction_verification.py --force

# Dry run
python scripts/run_prediction_verification.py --dry-run

# Debug mode
python scripts/run_prediction_verification.py --debug

# Show statistics
python scripts/run_prediction_verification.py --show-stats
```

### 5. Prediction Integration (`utils/prediction_integration.py`)

Bridge between Hypothesis Engine and Verification Engine.

```python
# Automatic integration (enabled by default)
result = run_hypothesis_engine(
    meta_signals_path,
    register_predictions=True,  # default
)

# Manual registration
from utils.prediction_integration import register_predictions
register_predictions(bundles)
```

## Data Flow

### 1. Prediction Registration

When hypotheses are generated:

```
HypothesisEngine.process_meta_signals()
    └── on_hypotheses_generated()
        └── register_predictions_from_bundle()
            └── PredictionStore.save_records()
                └── data/predictions/predictions.jsonl
```

### 2. Prediction Verification

When verification runs:

```
run_prediction_verification.py
    ├── PredictionStore.load_due_records()
    ├── UnifiedMetricObserver.observe_for_prediction()
    ├── evaluate_prediction()
    └── CalibrationEngine.compute_report()
        └── data/metrics/calibration_report.json
```

## File Locations

```
briefAI/
├── data/
│   ├── predictions/
│   │   └── predictions.jsonl      # All prediction records
│   └── metrics/
│       └── calibration_report.json  # System calibration
├── utils/
│   ├── prediction_verifier.py     # Core verifier
│   ├── metric_observer.py         # Data collection
│   ├── calibration_engine.py      # Accuracy metrics
│   └── prediction_integration.py  # HE integration
└── scripts/
    └── run_prediction_verification.py  # Scheduler
```

## Prediction Record Schema

```json
{
  "prediction_id": "pred_a1b2c3d4",
  "hypothesis_id": "hyp_20260210_nvidia_infra_scaling",
  "meta_id": "meta_nvidia_chip_demand_20260210",
  
  "entity": "nvidia",
  "canonical_metric": "filing_mentions",
  "expected_direction": "up",
  "category": "financial",
  "description": "CapEx mentions increase in SEC filings",
  
  "window_days": 30,
  "created_at": "2026-02-10T11:30:00",
  "evaluation_due": "2026-03-12T11:30:00",
  
  "status": "pending",
  "verdict": "pending",
  
  "confidence_at_prediction": 0.78,
  
  "observed_value_start": null,
  "observed_value_end": null,
  "percent_change": null,
  "evaluated_at": null,
  "evaluation_notes": null
}
```

## Evaluation Logic

### Direction Thresholds

| Direction | Verified True | Verified False | Inconclusive |
|-----------|---------------|----------------|--------------|
| `up` | ≥ +15% | ≤ -15% | -15% to +15% |
| `down` | ≤ -15% | ≥ +15% | -15% to +15% |
| `flat` | -15% to +15% | > ±15% | - |

### Verdict Assignment

```python
def evaluate_direction(direction, percent_change, threshold=0.15):
    if direction == 'up':
        if percent_change >= threshold:
            return 'verified_true'
        elif percent_change <= -threshold:
            return 'verified_false'
    elif direction == 'down':
        if percent_change <= -threshold:
            return 'verified_true'
        elif percent_change >= threshold:
            return 'verified_false'
    elif direction == 'flat':
        if abs(percent_change) <= threshold:
            return 'verified_true'
        else:
            return 'verified_false'
    
    return 'inconclusive'
```

## Calibration Report Example

```
============================================================
CALIBRATION REPORT
============================================================
Generated: 2026-02-10T12:00:00

SUMMARY
----------------------------------------
Total predictions: 150
Evaluated: 42

VERDICTS
----------------------------------------
Verified True: 28
Verified False: 10
Inconclusive: 3
Data Missing: 1

METRICS
----------------------------------------
Accuracy: 73.7%
Precision: 80.0%
Recall: 73.7%
Brier Score: 0.1832

CALIBRATION CURVE
----------------------------------------
Confidence      Count      Accuracy  
0.0-0.2         3          33.3%
0.2-0.4         5          40.0%
0.4-0.6         12         66.7%
0.6-0.8         15         80.0%
0.8-1.0         7          85.7%

BY MECHANISM
----------------------------------------
infra_scaling                     82.4%
enterprise_adoption               75.0%
competitive_pressure              66.7%

============================================================
```

## Integration with Daily Pipeline

Add to `daily_bloomberg.ps1`:

```powershell
# After hypothesis generation
Write-Host "Running prediction verification..." -ForegroundColor Yellow
python scripts/run_prediction_verification.py

# Check calibration report
if (Test-Path "data\metrics\calibration_report.json") {
    $report = Get-Content "data\metrics\calibration_report.json" | ConvertFrom-Json
    Write-Host "System Accuracy: $($report.accuracy * 100)%" -ForegroundColor Cyan
}
```

## Testing

```powershell
# Run all PVE tests
python tests/test_prediction_verifier.py

# Run individual module tests
python utils/metric_observer.py
python utils/calibration_engine.py
```

## Design Principles

1. **No LLM Calls** - All evaluation is deterministic
2. **Immutable Records** - Predictions never modified, only status updated
3. **JSONL Storage** - Simple, append-friendly, git-trackable
4. **Threshold-Based** - Clear 15% significance boundary
5. **Graceful Degradation** - Missing data → data_missing verdict
6. **Calibration Focus** - Track accuracy over time for system improvement

## Future Extensions

- [ ] Composite predictions (multiple metrics combined)
- [ ] Confidence-weighted accuracy
- [ ] Real-time streaming verification
- [ ] Alert on consistent prediction failures
- [ ] Mechanism-specific threshold tuning
- [ ] Historical trend visualization
