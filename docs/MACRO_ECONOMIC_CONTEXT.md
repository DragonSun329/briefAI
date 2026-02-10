# Macro-Economic Context Integration

## Overview

This module adds macro-economic context to briefAI signals to improve interpretation and confidence calibration. The integration provides:

1. **Economic Indicators** - Fed funds rate, Treasury yields, PMI, VIX
2. **Regime Detection** - Bull, bear, sideways, crisis classification
3. **Sector Context** - Tech ETF relative strength vs SPY
4. **Geopolitical Risk** - US-China tech tensions monitoring
5. **Signal Calibration** - Macro-aware confidence adjustments

## Components

### 1. Economic Context Provider (`integrations/economic_context.py`)

Provides comprehensive macro data:

```python
from integrations.economic_context import EconomicContextProvider

provider = EconomicContextProvider()

# Individual analyses
rates = provider.get_interest_rate_analysis()
vix = provider.get_vix_analysis()
sector = provider.get_sector_etf_relative_strength()
pmi = provider.get_pmi_ism_analysis()
geo = provider.get_geopolitical_risk_context()

# All-in-one
full_context = provider.get_comprehensive_macro_context()
```

#### Key Methods

| Method | Description |
|--------|-------------|
| `get_interest_rate_analysis()` | Fed funds, Treasury yields, yield curve |
| `get_vix_analysis()` | VIX level, regime, signal reliability |
| `get_sector_etf_relative_strength()` | QQQ, SOXX, IGV vs SPY |
| `get_pmi_ism_analysis()` | Enterprise spending outlook |
| `get_geopolitical_risk_context()` | US-China tension levels |
| `get_comprehensive_macro_context()` | Combined analysis with summary |

### 2. Regime Classifier (`utils/regime_classifier.py`)

Classifies market regime for signal interpretation:

```python
from utils.regime_classifier import RegimeClassifier, get_current_regime

# Quick access
regime_data = get_current_regime()
print(f"Regime: {regime_data['regime']}")  # bull, bear, sideways, crisis, recovery

# Detailed analysis
classifier = RegimeClassifier()
snapshot = classifier.classify_regime()

# Save to history
classifier.save_regime_snapshot(snapshot)
```

#### Regime Definitions

| Regime | Conditions |
|--------|------------|
| **Bull** | SPX > 200MA, positive momentum, VIX < 20 |
| **Bear** | SPX < 200MA, negative momentum, risk-off rotation |
| **Sideways** | Range-bound, mixed signals |
| **Crisis** | VIX > 30, extreme drawdowns |
| **Recovery** | SPX crossing above 200MA from below |

### 3. Macro-Aware Calibrator (`utils/signal_calibrator.py`)

Adjusts signals based on macro context:

```python
from utils.signal_calibrator import MacroAwareCalibrator, calibrate_with_macro_context

# Quick function
result = calibrate_with_macro_context(
    entity_id="nvidia",
    signals=[
        {"sentiment": 7.5, "confidence": 0.8, "source_id": "news_search"},
        {"sentiment": 7.2, "confidence": 0.9, "source_id": "yfinance"},
    ]
)

print(f"Calibrated sentiment: {result['calibrated_sentiment']}")
print(f"Macro adjustments: {result['macro_adjustments']}")
```

#### Macro Adjustments Applied

| Condition | Adjustment |
|-----------|------------|
| Bull regime + bullish signal | Confidence boost |
| Bear regime + bullish signal | Sentiment -0.15, confidence reduced |
| Crisis regime | Confidence heavily reduced (x0.6) |
| VIX > 25 | Confidence reduced based on level |
| AI sector outperforming + bullish | Sentiment +0.1 |
| China-exposed + elevated geo risk | Sentiment penalty, confidence reduced |

## Configuration

### Risk Indicators (`config/risk_indicators.json`)

Defines geopolitical risk factors and signal adjustments:

```json
{
  "geopolitical": {
    "us_china_tech": {
      "current_level": "elevated",
      "affected_entities": ["nvidia", "amd", "intel", ...],
      "monitoring_keywords": ["export controls", "chip ban", ...]
    }
  },
  "signal_adjustments": {
    "geopolitical_elevated": {
      "china_exposed_entities": -0.15,
      "confidence_modifier": 0.9
    }
  }
}
```

### Regime History (`data/regime_history.json`)

Stores regime snapshots for backtesting:

```json
[
  {
    "timestamp": "2026-01-27T10:00:00",
    "regime": "sideways",
    "confidence": 0.5,
    "momentum_score": 0.0,
    "vix_level": 16.0,
    "notes": ["Mixed signals - range-bound"]
  }
]
```

## Data Sources

| Source | Data Provided | Requirement |
|--------|---------------|-------------|
| FRED API | Interest rates, employment, PMI | `fredapi` package + API key |
| yfinance | VIX, ETF prices, market data | `yfinance` package |
| Config files | Risk indicators, thresholds | Included in repo |

## Integration Examples

### Example 1: Full Signal Calibration

```python
from utils.signal_calibrator import calibrate_with_macro_context

# Calibrate an AI company signal
result = calibrate_with_macro_context(
    entity_id="anthropic",
    signals=[
        {"sentiment": 8.0, "confidence": 0.85, "source_id": "news_search"},
        {"sentiment": 7.5, "confidence": 0.9, "source_id": "github"},
    ]
)

# Result includes:
# - calibrated_sentiment: Adjusted for macro
# - calibrated_confidence: Modified by regime/VIX
# - macro_context: Current regime, VIX, sector strength
# - macro_adjustments: List of adjustments applied
```

### Example 2: Regime-Aware Dashboard

```python
from utils.regime_classifier import get_current_regime

regime = get_current_regime()

if regime['regime'] == 'crisis':
    display_warning("High volatility - reduce position sizes")
elif regime['regime'] == 'bull':
    display_info("Favorable environment for AI signals")

# Show sector rotation
ai_sector = regime['ai_sector']
if ai_sector['sector_rotation_favorable']:
    display_positive("Tech/AI sectors outperforming")
```

### Example 3: Economic Dashboard Widget

```python
from integrations.economic_context import EconomicContextProvider

provider = EconomicContextProvider()
context = provider.get_comprehensive_macro_context()

summary = context['summary']
print(f"Headline: {summary['headline']}")
print(f"Key Points: {summary['key_points']}")
print(f"Recommendation: {summary['signal_implications']['recommendation']}")
```

## Signal Interpretation Guidelines

### When to Trust Bullish Signals

| Condition | Trust Level |
|-----------|-------------|
| Bull regime + AI outperforming | High |
| Sideways + low VIX | Moderate |
| Bear regime | Low - require more confirmation |
| Crisis/High VIX | Very Low |

### When to Trust Bearish Signals

| Condition | Trust Level |
|-----------|-------------|
| Bear regime + defensive rotation | High |
| Sideways + elevated VIX | Moderate |
| Bull regime | Low - may be contrarian |

### Geopolitical Risk Adjustments

Entities with significant China exposure:
- NVIDIA, AMD, Intel, Qualcomm, Micron
- Apple, Tesla, TSMC
- Applied Materials, Lam Research, KLA, ASML

When geopolitical risk is elevated/high:
- Apply sentiment penalty (-0.15 to -0.25)
- Reduce confidence modifier (0.8-0.9)
- Note China exposure in signal output

## Testing

Run the integration test:

```bash
cd C:\Users\admin\briefAI
python scripts/test_macro_integration.py
```

This tests:
1. Economic context provider
2. Regime classifier
3. Macro-aware calibrator
4. Full integration flow

## Dependencies

Required packages:
- `yfinance` - Market data (required)
- `fredapi` - FRED economic data (optional, enhances rate data)
- `numpy` - Calculations
- `loguru` - Logging

Install:
```bash
pip install yfinance fredapi numpy loguru
```

## Future Enhancements

1. **Real-time VIX monitoring** - Alert on VIX spikes
2. **Sector rotation signals** - Detect rotation patterns
3. **Credit spread alerts** - Monitor for stress signals
4. **Earnings calendar integration** - Adjust around events
5. **Fed meeting calendar** - Reduce confidence before FOMC
