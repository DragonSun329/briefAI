#!/usr/bin/env python
"""
Export Methodology - Auto-Generate Research Documentation.

Part of briefAI Validation & Public Credibility Layer.

This script auto-documents the briefAI system in research paper format.
The output is deterministic and regenerated programmatically.

Sections:
1. Data Sources
2. Signal Formation
3. Meta-Signal Clustering
4. Hypothesis Generation
5. Prediction Verification
6. Evidence-Based Belief Updating
7. Calibration Measurement
8. Lead-Time Definition

Output:
    docs/briefai_methodology.md

Usage:
    python scripts/export_methodology.py
"""

import sys
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger


# =============================================================================
# CONSTANTS
# =============================================================================

DEFAULT_DATA_DIR = Path(__file__).parent.parent / "data"
DEFAULT_DOCS_DIR = Path(__file__).parent.parent / "docs"
METHODOLOGY_FILE = "briefai_methodology.md"


# =============================================================================
# METHODOLOGY GENERATOR
# =============================================================================

class MethodologyGenerator:
    """Generates research methodology documentation."""
    
    def __init__(self, data_dir: Path = None, docs_dir: Path = None):
        """Initialize generator."""
        if data_dir is None:
            data_dir = DEFAULT_DATA_DIR
        if docs_dir is None:
            docs_dir = DEFAULT_DOCS_DIR
        
        self.data_dir = Path(data_dir)
        self.docs_dir = Path(docs_dir)
        self.docs_dir.mkdir(parents=True, exist_ok=True)
        
        self.output_file = self.docs_dir / METHODOLOGY_FILE
    
    def generate(self) -> str:
        """Generate methodology document."""
        sections = []
        
        # Header
        sections.append(self._header())
        
        # Abstract
        sections.append(self._abstract())
        
        # Section 1: Data Sources
        sections.append(self._data_sources())
        
        # Section 2: Signal Formation
        sections.append(self._signal_formation())
        
        # Section 3: Meta-Signal Clustering
        sections.append(self._meta_signal_clustering())
        
        # Section 4: Hypothesis Generation
        sections.append(self._hypothesis_generation())
        
        # Section 5: Prediction Verification
        sections.append(self._prediction_verification())
        
        # Section 6: Evidence-Based Belief Updating
        sections.append(self._belief_updating())
        
        # Section 7: Calibration Measurement
        sections.append(self._calibration_measurement())
        
        # Section 8: Lead-Time Definition
        sections.append(self._lead_time_definition())
        
        # Appendix: System Parameters
        sections.append(self._appendix_parameters())
        
        # Footer
        sections.append(self._footer())
        
        document = "\n".join(sections)
        
        # Save
        with open(self.output_file, 'w', encoding='utf-8') as f:
            f.write(document)
        
        logger.info(f"Generated methodology document: {self.output_file}")
        
        return document
    
    def _header(self) -> str:
        return """# briefAI: Research Methodology

**Version:** 1.0  
**Generated:** {date}  
**Status:** Research System Documentation

---
""".format(date=datetime.now().strftime("%Y-%m-%d"))
    
    def _abstract(self) -> str:
        return """## Abstract

briefAI is a signal intelligence system that detects emerging trends in the AI/technology sector by processing multi-source signals, generating testable hypotheses, and maintaining a calibrated forecasting model. The system employs strict temporal causality, ensuring that predictions are evaluated against future outcomes without forward-looking bias.

This document describes the methodology for signal processing, hypothesis generation, prediction verification, and calibration measurement.

---
"""
    
    def _data_sources(self) -> str:
        return """## 1. Data Sources

### 1.1 Signal Categories

briefAI ingests signals from multiple categories with defined reliability weights:

| Category | Sources | Reliability Weight |
|----------|---------|-------------------|
| Regulatory | SEC filings, earnings calls | 0.95 |
| Financial | Revenue data, guidance, analyst estimates | 0.90 |
| Technical | GitHub activity, package downloads, SDK releases | 0.85 |
| Labor Market | Job postings, hiring announcements | 0.75 |
| News/Media | Tech news, press releases | 0.50 |
| Social | Reddit, Twitter, discussion forums | 0.35 |

### 1.2 Temporal Constraints

All signals are timestamped at ingestion. The system enforces strict temporal causality:

- When evaluating predictions, only signals available at prediction time are considered
- Historical replay uses temporally-filtered data
- No forward-looking information leakage is permitted

### 1.3 Signal Volume

The system processes signals on a rolling basis, maintaining:
- Daily signal ingestion
- 90-day rolling window for trend detection
- Archival of historical signals for backtesting

---
"""
    
    def _signal_formation(self) -> str:
        return """## 2. Signal Formation

### 2.1 Raw Signal Processing

Raw signals are processed through:

1. **Deduplication**: Identical content across sources is merged
2. **Entity Extraction**: Named entities (companies, products, people) are identified
3. **Categorization**: Signals are classified by topic (infrastructure, enterprise, models, etc.)
4. **Timestamping**: UTC timestamps are assigned at ingestion

### 2.2 Signal Scoring

Each signal receives a base score based on:

- **Source reliability** (per category weights above)
- **Information density** (substantive content vs. noise)
- **Novelty** (new information vs. repetition)

### 2.3 Signal Schema

```json
{
  "signal_id": "string",
  "timestamp": "ISO8601",
  "source": "string",
  "category": "string",
  "entities": ["string"],
  "content": "string",
  "reliability_score": 0.0-1.0
}
```

---
"""
    
    def _meta_signal_clustering(self) -> str:
        return """## 3. Meta-Signal Clustering

### 3.1 Concept Formation

Related signals are clustered into meta-signals representing coherent trends or events:

1. **Semantic Similarity**: Signals with similar content are grouped
2. **Entity Co-occurrence**: Signals mentioning the same entities are linked
3. **Temporal Proximity**: Signals within a time window are considered related

### 3.2 Meta-Signal Properties

Each meta-signal captures:

- **Concept Name**: Human-readable trend description
- **Signal Count**: Number of contributing signals
- **Source Diversity**: Number of independent sources
- **Category Coverage**: Which signal categories are represented
- **Velocity**: Rate of signal accumulation
- **Confidence**: Weighted average of contributing signal scores

### 3.3 Independence Scoring

Meta-signals are scored for independence to prevent over-counting:

```
independence_score = unique_sources / total_sources
```

Meta-signals with low independence (< 0.5) are flagged as potentially echo-chamber effects.

---
"""
    
    def _hypothesis_generation(self) -> str:
        return """## 4. Hypothesis Generation

### 4.1 Mechanism Taxonomy

Meta-signals are mapped to causal mechanisms:

| Mechanism | Description |
|-----------|-------------|
| `infra_scaling` | Infrastructure demand driving compute expansion |
| `enterprise_adoption` | Enterprise deployment acceleration |
| `pricing_compression` | Commoditization pressure reducing margins |
| `distribution_shift` | Value migration toward applications |
| `competitive_pressure` | Market competition intensifying |
| `regulatory_shift` | Policy/regulatory environment changing |
| `talent_migration` | Key personnel moving between organizations |
| `capex_acceleration` | Capital expenditure commitment increasing |

### 4.2 Hypothesis Structure

Each hypothesis contains:

```json
{
  "hypothesis_id": "string",
  "title": "string (6-8 words, no company names)",
  "mechanism": "mechanism_code",
  "confidence": 0.0-1.0,
  "predicted_next_signals": [...],
  "falsifiers": [...]
}
```

### 4.3 Predicted Signals

Each prediction specifies:

- **Category**: Where to look (financial, technical, media, etc.)
- **Description**: What to observe
- **Canonical Metric**: Measurable quantity (article_count, repo_activity, etc.)
- **Expected Direction**: up, down, or flat
- **Timeframe**: Expected observation window (days)
- **Measurable**: Boolean indicating if prediction is testable

### 4.4 Observable Gate

Predictions must pass an observable gate to be registered:

- Must have a canonical metric
- Must have an expected direction
- Must be measurable within the system's data capabilities

Vague or untestable predictions are filtered out.

---
"""
    
    def _prediction_verification(self) -> str:
        return """## 5. Prediction Verification

### 5.1 Evaluation Timing

Predictions are evaluated when their timeframe expires:

```
evaluation_due = prediction_date + timeframe_days
```

### 5.2 Outcome Measurement

For each prediction:

1. Observe the canonical metric at prediction time (baseline)
2. Observe the canonical metric at evaluation time (current)
3. Calculate percent change: `(current - baseline) / |baseline|`

### 5.3 Verdict Assignment

| Expected Direction | Percent Change | Verdict |
|-------------------|----------------|---------|
| up | >= +15% | verified_true |
| up | <= -15% | verified_false |
| up | -15% to +15% | inconclusive |
| down | <= -15% | verified_true |
| down | >= +15% | verified_false |
| flat | within ±15% | verified_true |

### 5.4 Threshold Selection

The 15% threshold was selected to:

- Distinguish signal from noise
- Account for measurement uncertainty
- Avoid over-sensitivity to small fluctuations

### 5.5 Data Missing Handling

If baseline or current observations are unavailable, the verdict is `data_missing` and the prediction is excluded from accuracy calculations.

---
"""
    
    def _belief_updating(self) -> str:
        return """## 6. Evidence-Based Belief Updating

### 6.1 Evidence Model

Each verified prediction produces graded evidence:

```
evidence_score = min(1.0, |percent_change| / 0.30)
```

Evidence scores saturate at 30% change to prevent outliers from dominating.

### 6.2 Evidence Direction

| Observation | Direction |
|-------------|-----------|
| Matches expected direction | SUPPORT (+score) |
| Opposes expected direction | CONTRADICT (-score) |
| Within noise band | NEUTRAL (0) |

### 6.3 Evidence Weighting

Evidence is weighted by metric reliability:

```
weight = canonical_metric_weight × source_reliability
```

High-reliability sources (SEC filings) carry more weight than low-reliability sources (social media).

### 6.4 Belief Update Rule

```
evidence_delta = Σ(evidence_score × weight) / Σ(weight)
posterior = prior + 0.35 × evidence_delta
posterior = clip(posterior, 0.05, 0.98)
```

### 6.5 Safety Caps

To prevent overconfidence in fragile hypotheses:

| Hypothesis Quality | Maximum Posterior |
|-------------------|-------------------|
| review_required | 0.60 |
| weakly_validated | 0.75 |
| default | 0.95 |

---
"""
    
    def _calibration_measurement(self) -> str:
        return """## 7. Calibration Measurement

### 7.1 Calibration Definition

A forecasting system is well-calibrated if:

> When the system says "X% confidence", outcomes occur X% of the time.

### 7.2 Calibration Buckets

Predictions are grouped by confidence level:

| Bucket | Confidence Range |
|--------|-----------------|
| 1 | 0.50 - 0.60 |
| 2 | 0.60 - 0.70 |
| 3 | 0.70 - 0.80 |
| 4 | 0.80 - 0.90 |
| 5 | 0.90 - 1.00 |

### 7.3 Metrics

For each bucket, we measure:

- **Expected Accuracy**: Midpoint of confidence range
- **Actual Accuracy**: Verified_true / (Verified_true + Verified_false)
- **Calibration Error**: Actual - Expected

### 7.4 Brier Score

Overall forecast quality is measured by Brier score:

```
Brier = (1/N) × Σ(confidence - outcome)²
```

Where outcome = 1 for verified_true, 0 for verified_false.

Lower Brier scores indicate better calibration (0 = perfect, 1 = worst).

### 7.5 Calibration Quality

| Mean Calibration Error | Interpretation |
|-----------------------|----------------|
| < 5% | Well-calibrated |
| > 5% (negative) | Overconfident |
| > 5% (positive) | Underconfident |

---
"""
    
    def _lead_time_definition(self) -> str:
        return """## 8. Lead-Time Definition

### 8.1 Purpose

Lead time measures how early the system detects developments before mainstream coverage.

### 8.2 Calculation

```
lead_time = confirmation_date - prediction_date
```

Where:
- `prediction_date`: When the hypothesis was first generated
- `confirmation_date`: When the prediction was verified (event observed)

### 8.3 Interpretation

| Lead Time | Interpretation |
|-----------|----------------|
| 21+ days | Significant early detection |
| 14-21 days | Strong early detection |
| 7-14 days | Moderate early detection |
| 0-7 days | Near-real-time detection |
| Negative | Lagging (detected after mainstream) |

### 8.4 Aggregate Metrics

The system tracks:

- **Average Lead Time**: Mean days before confirmation
- **Median Lead Time**: Median days before confirmation
- **Early Detection Rate**: % of predictions with 7+ day lead time

### 8.5 By Mechanism

Lead times are also computed per mechanism to identify which signal types provide the most advance notice.

---
"""
    
    def _appendix_parameters(self) -> str:
        return """## Appendix A: System Parameters

### A.1 Thresholds

| Parameter | Value | Purpose |
|-----------|-------|---------|
| Significant Change | 15% | Verdict determination |
| Evidence Saturation | 30% | Maximum evidence score |
| Learning Rate | 0.35 | Belief update speed |
| Min Confidence | 5% | Posterior floor |
| Max Confidence | 98% | Posterior ceiling |
| Independence Threshold | 0.5 | Meta-signal quality |

### A.2 Weights

| Metric Category | Weight Range |
|-----------------|--------------|
| Regulatory/SEC | 0.90 - 0.98 |
| Financial | 0.80 - 0.90 |
| Technical | 0.70 - 0.85 |
| Labor Market | 0.60 - 0.75 |
| News/Media | 0.40 - 0.55 |
| Social | 0.25 - 0.40 |

### A.3 Time Windows

| Window | Duration | Purpose |
|--------|----------|---------|
| Signal Aggregation | 24 hours | Daily processing |
| Trend Detection | 90 days | Rolling trend window |
| Prediction Default | 30 days | Default evaluation window |
| Calibration Period | 30 days | Accuracy measurement |

---
"""
    
    def _footer(self) -> str:
        return """## Document Information

**Generated by:** `scripts/export_methodology.py`  
**Generation Date:** {date}  
**System Version:** briefAI v2.8

This document is auto-generated from system configuration and should be regenerated after significant methodology changes.

---

*End of Methodology Document*
""".format(date=datetime.now().strftime("%Y-%m-%d"))


# =============================================================================
# CLI
# =============================================================================

def main():
    """Main entry point."""
    print("=" * 60)
    print("METHODOLOGY EXPORT")
    print("=" * 60)
    print()
    
    generator = MethodologyGenerator()
    document = generator.generate()
    
    print(f"Generated: {generator.output_file}")
    print(f"Size: {len(document)} characters")
    print(f"Lines: {document.count(chr(10))}")
    print()
    print("=" * 60)


if __name__ == "__main__":
    main()
