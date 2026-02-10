# Evidence Engine v1.0

*Part of briefAI Gravity Engine v2.8: Evidence-Based Belief Updates*

## Overview

The Evidence Engine upgrades the Prediction Verification Engine from binary evaluation into a continuous evidence-based belief system.

**Before:** Predictions evaluated as verified_true / verified_false / inconclusive
**After:** Predictions generate graded evidence, hypotheses update their posterior confidence

This converts briefAI from a backtesting checker into a Bayesian-style learning trend radar.

## Core Concepts

### Evidence vs Verdicts

Binary truth is too harsh for real markets:

| Metric | Old System | New System |
|--------|-----------|------------|
| ARR up 9% | Inconclusive | Weak support |
| GitHub repos up 40% | True | Strong support |
| Mentions down 3% | False | Weak contradiction |

The system now accumulates partial evidence.

### Evidence Direction

```
EvidenceDirection:
  SUPPORT      - Observation confirms hypothesis direction
  CONTRADICT   - Observation opposes hypothesis direction
  NEUTRAL      - Change within noise band (±15%)
  DATA_MISSING - No data available
```

### Evidence Scoring

```python
# Calculate direction
if expected == 'up' and percent_change >= 0.15:
    direction = SUPPORT
elif expected == 'up' and percent_change <= -0.15:
    direction = CONTRADICT
else:
    direction = NEUTRAL

# Calculate score (-1.0 to +1.0)
# Saturates at 30% change
evidence_score = min(1.0, abs(percent_change) / 0.30)

if direction == SUPPORT:
    score = +evidence_score
elif direction == CONTRADICT:
    score = -evidence_score
else:
    score = 0.0
```

### Metric Weighting

Evidence is weighted by importance:

| Source | Weight |
|--------|--------|
| SEC filings | Very high (0.95) |
| ARR/Revenue | High (0.85) |
| GitHub repos | Medium (0.70) |
| News articles | Low (0.45) |
| Reddit/Twitter | Very low (0.25-0.35) |

Combined weight = `canonical_metric_weight × source_reliability`

## Belief Updates

### Update Rule

```python
evidence_delta = Σ(evidence_score × weight) / Σ(weight)
posterior = prior + 0.35 × evidence_delta
posterior = clip(posterior, 0.05, 0.98)
posterior = min(posterior, safety_cap)
```

### Safety Caps

| Hypothesis Quality | Max Posterior |
|-------------------|---------------|
| review_required | 0.60 |
| weakly_validated | 0.75 |
| default | 0.95 |

## Example Trajectory

Hypothesis: "Enterprise AI adoption accelerating" (prior: 0.62)

| Day | Signal | Evidence | Posterior |
|-----|--------|----------|-----------|
| 1 | job postings ↑18% | support (+0.60) | 0.83 |
| 3 | GitHub SDK ↑40% | support (+1.00) | 0.91 |
| 7 | ARR ↑35% | strong support (+1.00) | 0.94 |
| 10 | media ↓22% | contradiction (-0.75) | 0.87 |

The hypothesis learns from accumulated evidence.

## Components

### evidence_engine.py

- `EvidenceDirection` - Direction enum
- `EvidenceResult` - Evidence data structure
- `EvidenceWeights` - Weight configuration
- `EvidenceGenerator` - Creates evidence from observations
- `EvidenceStore` - JSONL persistence

### belief_updater.py

- `BeliefState` - Hypothesis belief state
- `BeliefStore` - Beliefs persistence
- `BeliefUpdater` - Update logic + batch processing

### evidence_weights.json

Configuration for metric weights and source reliability.

## File Outputs

```
data/predictions/
├── evidence_YYYY-MM-DD.jsonl  # Daily evidence log (append-only)
├── beliefs.json               # Current belief states
└── belief_history.jsonl       # Confidence trajectory over time
```

## Usage

### Automatic (Pipeline)

```bash
# Runs verification + evidence + belief updates
python scripts/run_prediction_verification.py
```

### Manual

```python
from utils.evidence_engine import EvidenceGenerator
from utils.belief_updater import BeliefUpdater

# Generate evidence
gen = EvidenceGenerator()
evidence = gen.generate_evidence(
    prediction_id='pred_001',
    hypothesis_id='hyp_001',
    meta_id='meta_001',
    entity='nvidia',
    canonical_metric='filing_mentions',
    category='financial',
    expected_direction='up',
    baseline=100,
    current=125,
    source='sec',
)

# Update beliefs
updater = BeliefUpdater()
updated = updater.process_evidence_batch([evidence], hypothesis_priors)
```

### Show Beliefs

```bash
python scripts/run_prediction_verification.py --show-beliefs
```

## CLI Options

```bash
# Full run with evidence
python scripts/run_prediction_verification.py

# Skip evidence (legacy mode)
python scripts/run_prediction_verification.py --no-evidence

# Force all pending
python scripts/run_prediction_verification.py --force

# Dry run
python scripts/run_prediction_verification.py --dry-run

# Show statistics
python scripts/run_prediction_verification.py --show-stats

# Show belief states
python scripts/run_prediction_verification.py --show-beliefs
```

## Testing

```bash
# Evidence engine tests
python tests/test_evidence_engine.py

# Belief updater tests
python tests/test_belief_updater.py

# Full integration tests
python tests/test_pve_evidence_integration.py
```

## Design Principles

1. **No LLM Calls** - All scoring is deterministic
2. **Graded Evidence** - Partial support/contradiction
3. **Weighted Accumulation** - High-quality sources matter more
4. **Safety Caps** - Prevents fragile hypotheses from becoming "certain"
5. **Audit Trail** - Every evidence result logged
6. **Learning System** - Beliefs evolve with new data

## Why This Matters

Markets rarely move in a single confirming event. Real trends look like:

- Day 1: small signs
- Day 3: technical confirmation
- Day 7: financial confirmation
- Day 20: mainstream adoption

Binary verification cannot capture this. Evidence accumulation can.

This turns briefAI into: **a system that learns whether its ideas are right.**
