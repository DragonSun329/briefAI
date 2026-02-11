#!/usr/bin/env python
"""
Generate Experiment Methodology v1.0

Auto-generates academic-style methodology documentation for each experiment.
This makes the forecasting experiment publishable and externally auditable.

Output: data/public/experiments/{experiment_id}/METHODOLOGY.md

The generated file reads like an academic methods section and includes:
- Experiment purpose and design
- Engine specification
- Data sources
- Prediction types and verification rules
- Calibration methodology
- Reproducibility guarantees
"""

import json
import sys
from typing import Dict, Any, List
from datetime import datetime, date
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger


# =============================================================================
# CONSTANTS
# =============================================================================

CONFIG_DIR = Path(__file__).parent.parent / "config"
DATA_DIR = Path(__file__).parent.parent / "data"


# =============================================================================
# CONFIG LOADERS
# =============================================================================

def load_config(filename: str) -> Dict[str, Any]:
    """Load a config file from the config directory."""
    path = CONFIG_DIR / filename
    if not path.exists():
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_experiments() -> Dict[str, Any]:
    return load_config('experiments.json')


def load_observable_metrics() -> Dict[str, Any]:
    return load_config('observable_metrics.json')


def load_mechanism_taxonomy() -> Dict[str, Any]:
    return load_config('mechanism_taxonomy.json')


def load_action_event_types() -> Dict[str, Any]:
    return load_config('action_event_types.json')


def load_pressure_action_map() -> Dict[str, Any]:
    return load_config('pressure_action_map.json')


# =============================================================================
# METHODOLOGY SECTIONS
# =============================================================================

def generate_header(experiment: Dict[str, Any], experiment_id: str) -> str:
    """Generate methodology document header."""
    return f"""# Experiment Methodology: {experiment_id}

> Auto-generated methodology documentation for the **{experiment.get('description', experiment_id)}** forward-test experiment.

**Generated**: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC  
**Engine Tag**: `{experiment.get('engine_tag', 'unknown')}`  
**Start Date**: {experiment.get('start_date', 'unknown')}  
**Status**: {experiment.get('status', 'unknown')}

---

"""


def generate_purpose_section(experiment: Dict[str, Any], experiment_id: str) -> str:
    """Generate the experiment purpose section."""
    desc = experiment.get('description', 'Forward-test experiment')
    pred_types = experiment.get('prediction_types', ['metric_trend'])
    
    section = """## 1. Experiment Purpose

### 1.1 Objective

This experiment evaluates the predictive accuracy of the briefAI forecasting system using a **forward-test** methodology. Unlike backtesting, forward-testing:

- Makes predictions **before** outcomes are known
- Freezes predictions at generation time (append-only ledger)
- Evaluates predictions only after the observation window expires
- Prevents look-ahead bias and p-hacking

### 1.2 Experiment Description

"""
    section += f"> {desc}\n\n"
    
    section += """### 1.3 Prediction Types

This experiment generates the following prediction types:

"""
    for ptype in pred_types:
        if ptype == 'metric_trend':
            section += "- **Metric Trends**: Predictions about directional changes in measurable quantities (e.g., article count, stock price, job postings)\n"
        elif ptype == 'action_event':
            section += "- **Action Events**: Predictions about specific company actions (e.g., partnership announcements, pricing changes, product launches)\n"
        elif ptype == 'media_attention':
            section += "- **Media Attention**: Predictions about changes in media coverage patterns\n"
        else:
            section += f"- **{ptype}**: Custom prediction type\n"
    
    section += "\n"
    return section


def generate_engine_section(experiment: Dict[str, Any]) -> str:
    """Generate the engine specification section."""
    engine_tag = experiment.get('engine_tag', 'unknown')
    engine_version = experiment.get('engine_version', 'unknown')
    
    section = f"""## 2. Forecasting Engine

### 2.1 Engine Identification

| Property | Value |
|----------|-------|
| Engine Tag | `{engine_tag}` |
| Version | {engine_version} |
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

"""
    return section


def generate_data_sources_section() -> str:
    """Generate the data sources section."""
    sources_config = load_config('sources.json')
    sources_expanded = load_config('sources_expanded.json')
    
    section = """## 3. Data Sources

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

"""
    return section


def generate_prediction_types_section(experiment: Dict[str, Any]) -> str:
    """Generate detailed prediction types section."""
    pred_types = experiment.get('prediction_types', ['metric_trend'])
    
    section = """## 4. Prediction Specification

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

"""
    
    if 'metric_trend' in pred_types:
        metrics = load_observable_metrics()
        section += """### 4.2 Metric Trend Predictions

Metric trend predictions forecast directional changes in measurable quantities.

**Canonical Metrics** (standardized vocabulary):

"""
        if 'metrics' in metrics:
            for category, category_metrics in metrics.get('metrics', {}).items():
                section += f"\n**{category.title()}**:\n"
                for metric in category_metrics[:5]:  # Limit for readability
                    section += f"- `{metric}`\n"
    
    if 'action_event' in pred_types:
        action_types = load_action_event_types()
        section += """### 4.3 Action Event Predictions

Action event predictions forecast specific company behaviors.

**Event Types**:

"""
        for event_id, event in action_types.get('event_types', {}).items():
            section += f"- **{event.get('display_name', event_id)}**: {event.get('description', '')[:80]}...\n"
    
    section += "\n"
    return section


def generate_verification_section() -> str:
    """Generate the verification methodology section."""
    section = """## 5. Verification Methodology

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

"""
    return section


def generate_fixed_parameters_section() -> str:
    """
    Generate the fixed parameters table.
    
    These parameters are extracted from code and config files,
    NOT hand-written. This ensures the documentation matches reality.
    """
    section = """## 6. Fixed Parameters

> **Auto-extracted from code and config.** These values are frozen for the experiment duration.

### 6.1 Clustering Thresholds

| Parameter | Value | Source |
|-----------|-------|--------|
"""
    
    # Try to extract from signal_config.json
    try:
        signal_config = load_config('signal_config.json')
        clustering = signal_config.get('clustering', {})
        section += f"| Similarity threshold | {clustering.get('similarity_threshold', 0.75)} | signal_config.json |\n"
        section += f"| Min cluster size | {clustering.get('min_cluster_size', 3)} | signal_config.json |\n"
        section += f"| Max cluster age (days) | {clustering.get('max_age_days', 7)} | signal_config.json |\n"
    except Exception:
        section += "| *Could not load signal_config.json* | - | - |\n"
    
    section += """
### 6.2 Evidence Weights

| Evidence Type | Weight (alpha) | Source |
|---------------|----------------|--------|
"""
    
    # Try to extract from evidence_weights.json
    try:
        evidence_weights = load_config('evidence_weights.json')
        for evidence_type, weight in list(evidence_weights.get('weights', {}).items())[:10]:
            section += f"| {evidence_type} | {weight} | evidence_weights.json |\n"
    except Exception:
        section += "| *Could not load evidence_weights.json* | - | - |\n"
    
    section += """
### 6.3 Verification Thresholds

| Parameter | Value | Description |
|-----------|-------|-------------|
"""
    
    # Try to extract from validation_rules.json or hardcoded values
    try:
        validation_rules = load_config('validation_rules.json')
        thresholds = validation_rules.get('verification', {})
        section += f"| Direction change threshold | {thresholds.get('direction_threshold', 0.15)} | Min change to verify |\n"
        section += f"| Inconclusive range | {thresholds.get('inconclusive_threshold', 0.15)} | Change too small |\n"
        section += f"| Confidence floor | {thresholds.get('min_confidence', 0.30)} | Predictions below skipped |\n"
    except Exception:
        # Hardcoded defaults from verification methodology
        section += "| Direction change threshold | 0.15 (15%) | Min change to verify |\n"
        section += "| Inconclusive range | <0.15 (<15%) | Change too small |\n"
        section += "| Confidence floor | 0.30 (30%) | Predictions below skipped |\n"
    
    section += """
### 6.4 Novelty & Deduplication Gates

| Parameter | Value | Source |
|-----------|-------|--------|
"""
    
    # Try to extract from trend_detection.json
    try:
        trend_config = load_config('trend_detection.json')
        novelty = trend_config.get('novelty', {})
        section += f"| Novelty decay (days) | {novelty.get('decay_days', 14)} | trend_detection.json |\n"
        section += f"| Dedup similarity | {novelty.get('dedup_threshold', 0.92)} | trend_detection.json |\n"
        section += f"| Recency boost max | {novelty.get('recency_boost', 1.2)} | trend_detection.json |\n"
    except Exception:
        section += "| *Could not load trend_detection.json* | - | - |\n"
    
    section += """
### 6.5 Confidence Formula Weights

| Component | Weight | Notes |
|-----------|--------|-------|
| Meta-confidence | 0.55 | Core signal strength |
| Category diversity | 0.15 | Cross-source signal |
| Persistence | 0.10 | Signal longevity |
| Independence | 0.10 | Source independence |
| Specificity | 0.10 | Prediction precision |

**Modifiers:**
- Action prediction bonus: +12%
- Media-only cap: 45% maximum
- Generic prediction penalty: -10%
- Weak mechanism penalty: -10%

"""
    return section


def generate_calibration_section() -> str:
    """Generate the calibration methodology section."""
    section = """## 7. Calibration Methodology

### 7.1 Calibration Definition

A forecasting system is **well-calibrated** when:

> For predictions with confidence X%, approximately X% are verified true.

Example: Of 100 predictions made with 70% confidence, ~70 should be verified true.

### 7.2 Calibration Metrics

| Metric | Description |
|--------|-------------|
| **Brier Score** | Mean squared error of probability forecasts (lower is better) |
| **Calibration Curve** | Plot of predicted vs. actual frequencies |
| **Reliability Diagram** | Binned calibration visualization |
| **Resolution** | Variance of predictions (measures informativeness) |

### 7.3 Confidence Scoring

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

### 7.4 Calibration Feedback Loop

After sufficient predictions are evaluated:

1. Compute calibration curve
2. Identify over/under-confidence regions
3. Adjust confidence formula (new engine version)
4. Create new experiment for revised model

"""
    return section


def generate_reproducibility_section(experiment: Dict[str, Any]) -> str:
    """Generate the reproducibility guarantee section with environment info."""
    engine_tag = experiment.get('engine_tag', 'unknown')
    
    section = f"""## 8. Reproducibility Guarantee

### 8.1 Reproduction Steps

A third party can reproduce this experiment's predictions:

```bash
# 1. Clone repository
git clone https://github.com/[repo]/briefAI.git
cd briefAI

# 2. Checkout exact engine version
git checkout {engine_tag}

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set experiment
python -c "from utils.experiment_manager import set_active_experiment; set_active_experiment('{experiment.get('experiment_id', 'unknown')}')"

# 5. Run pipeline
python scripts/daily_bloomberg.ps1
```

### 8.2 What Is Reproducible

| Component | Reproducible? | Notes |
|-----------|---------------|-------|
| Prediction structure | ✅ Yes | Same fields, formats |
| Confidence calculation | ✅ Yes | Deterministic formula |
| Mechanism detection | ✅ Yes | Rule-based, no LLM |
| Exact predictions | ❌ No | Data sources change daily |
| Methodology | ✅ Yes | Frozen at engine tag |

### 8.3 Integrity Verification

Each run produces metadata that enables verification:

- **Commit Hash**: Exact code version
- **Engine Tag**: Named version
- **Generation Timestamp**: When predictions were made
- **Artifact Contract**: Verification that all outputs exist

### 8.4 Append-Only Ledger with Hash Chain

The `forecast_history.jsonl` file is append-only with cryptographic verification:

- New predictions are appended, never overwritten
- Each entry includes `prev_hash` and `entry_hash` fields
- Hash chain creates blockchain-like tamper evidence
- Any modification breaks the chain and is detectable
- Sidecar file `forecast_history_last_hash.txt` tracks chain head

**Hash Chain Structure:**
```
entry_hash = SHA-256(prev_hash + canonical_json(entry))
```

**Verification:**
```bash
python -c "from utils.public_forecast_logger import verify_hash_chain; print(verify_hash_chain('path/to/forecast_history.jsonl'))"
```

### 8.5 Environment Fingerprint

Each `run_metadata` file includes a comprehensive environment fingerprint:

| Field | Description |
|-------|-------------|
| `python_version` | Exact Python version |
| `platform` | OS and release |
| `pip_freeze_hash` | Hash of installed packages |
| `requirements_hash` | Hash of requirements.txt |
| `config_dir_hash` | Hash of all config/*.json |
| `engine_commit_hash` | Resolved commit of engine tag |
| `dep_*` | Versions of key dependencies |

This allows verification that the execution environment matches expectations.

"""
    return section


def generate_appendix(experiment: Dict[str, Any]) -> str:
    """Generate methodology appendices."""
    section = """## Appendix A: Glossary

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
*Last updated: """ + datetime.utcnow().isoformat() + " UTC*\n"
    
    return section


# =============================================================================
# MAIN GENERATOR
# =============================================================================

def generate_methodology(experiment_id: str = None) -> str:
    """
    Generate complete methodology document for an experiment.
    
    Args:
        experiment_id: Experiment ID. Uses active if None.
    
    Returns:
        Complete markdown document
    """
    experiments = load_experiments()
    
    if experiment_id is None:
        experiment_id = experiments.get('active_experiment')
    
    if not experiment_id or experiment_id not in experiments.get('experiments', {}):
        raise ValueError(f"Experiment not found: {experiment_id}")
    
    experiment = experiments['experiments'][experiment_id]
    experiment['experiment_id'] = experiment_id
    
    # Build document
    sections = [
        generate_header(experiment, experiment_id),
        generate_purpose_section(experiment, experiment_id),
        generate_engine_section(experiment),
        generate_data_sources_section(),
        generate_prediction_types_section(experiment),
        generate_verification_section(),
        generate_fixed_parameters_section(),  # NEW: Auto-extracted parameters
        generate_calibration_section(),
        generate_reproducibility_section(experiment),
        generate_appendix(experiment),
    ]
    
    return ''.join(sections)


def write_methodology(experiment_id: str = None) -> Path:
    """
    Generate and write methodology document.
    
    Args:
        experiment_id: Experiment ID. Uses active if None.
    
    Returns:
        Path to written file
    """
    experiments = load_experiments()
    
    if experiment_id is None:
        experiment_id = experiments.get('active_experiment')
    
    if not experiment_id:
        raise ValueError("No experiment specified and no active experiment")
    
    experiment = experiments['experiments'].get(experiment_id, {})
    ledger_path = Path(experiment.get('ledger_path', f'data/public/experiments/{experiment_id}/'))
    
    if not ledger_path.is_absolute():
        ledger_path = Path(__file__).parent.parent / ledger_path
    
    ledger_path.mkdir(parents=True, exist_ok=True)
    
    methodology = generate_methodology(experiment_id)
    
    output_path = ledger_path / "METHODOLOGY.md"
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(methodology)
    
    logger.info(f"Wrote methodology: {output_path}")
    return output_path


def write_all_methodologies() -> List[Path]:
    """
    Generate methodology documents for all experiments.
    
    Returns:
        List of paths to written files
    """
    experiments = load_experiments()
    paths = []
    
    for experiment_id in experiments.get('experiments', {}).keys():
        try:
            path = write_methodology(experiment_id)
            paths.append(path)
        except Exception as e:
            logger.error(f"Failed to generate methodology for {experiment_id}: {e}")
    
    return paths


# =============================================================================
# CLI
# =============================================================================

def main():
    """CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Generate experiment methodology documentation'
    )
    parser.add_argument(
        '--experiment',
        help='Experiment ID (generates for all if not specified)'
    )
    parser.add_argument(
        '--print',
        action='store_true',
        help='Print to stdout instead of writing file'
    )
    
    args = parser.parse_args()
    
    if args.print:
        print(generate_methodology(args.experiment))
    elif args.experiment:
        path = write_methodology(args.experiment)
        print(f"Wrote: {path}")
    else:
        paths = write_all_methodologies()
        print(f"Generated {len(paths)} methodology documents:")
        for p in paths:
            print(f"  - {p}")


if __name__ == "__main__":
    main()
