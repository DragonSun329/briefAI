# Real-Time Validation Pipeline

This document describes the real-time validation system that validates briefAI sentiment signals against live market data and technical indicators.

## Overview

The validation pipeline bridges briefAI's alternative data signals (sentiment, momentum, funding) with real-time market data to:

1. **Validate Signals** - Check if sentiment aligns with price action
2. **Enrich Signals** - Add technical indicators and market context
3. **Score Reliability** - Quantify how trustworthy a signal is
4. **Provide Economic Context** - Factor in macro conditions

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  briefAI Signal │────▶│  Signal Enricher │────▶│ Enriched Signal │
│  (sentiment,    │     │  (adds market    │     │ (with validation│
│   momentum)     │     │   data, TA)      │     │  scores)        │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │  Market Data     │
                    │  Provider        │
                    │  (yfinance,      │
                    │   pandas-ta)     │
                    └──────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │  Economic        │
                    │  Context         │
                    │  (macro regime,  │
                    │   sector trends) │
                    └──────────────────┘
```

## Components

### 1. Fincept Bridge (`integrations/fincept_bridge.py`)

The core data integration layer that provides:

- **Real-time Prices** via yfinance
- **Technical Analysis** via pandas-ta (or manual calculations)
- **Economic Indicators** via FRED API (optional) and market proxies

```python
from integrations.fincept_bridge import UnifiedFinceptBridge

bridge = UnifiedFinceptBridge()

# Get real-time price
price = await bridge.get_realtime_price("NVDA")
print(f"Price: ${price.price}, Change: {price.change_pct}%")

# Get technical analysis
ta = await bridge.get_technical_analysis("NVDA")
print(f"RSI: {ta.rsi_14}, Trend: {ta.trend_signal}")

# Full enrichment
enriched = await bridge.enrich_entity_signal(
    entity_id="nvidia",
    ticker="NVDA",
    sentiment=7.5,
    momentum="bullish",
    confidence=0.8
)
```

### 2. Signal Enricher (`integrations/signal_enricher.py`)

Hooks into the briefAI signal pipeline to add market validation:

```python
from integrations.signal_enricher import SignalEnricher

enricher = SignalEnricher()

# Enrich a single signal
result = await enricher.enrich_signal(
    entity_id="nvidia",
    briefai_sentiment=7.5,
    briefai_momentum="bullish",
    briefai_confidence=0.8
)

print(f"Validation Score: {result.validation_score}")
print(f"Trend Alignment: {result.trend_alignment}")

# Batch enrichment
signals = [
    {"entity_id": "nvidia", "sentiment": 7.5, "momentum": "bullish"},
    {"entity_id": "microsoft", "sentiment": 6.0, "momentum": "neutral"},
]
enriched = await enricher.enrich_batch(signals)
```

### 3. Economic Context (`integrations/economic_context.py`)

Provides macro backdrop for AI sector signals:

```python
from integrations.economic_context import EconomicContextProvider

provider = EconomicContextProvider()

# Get economic snapshot
snapshot = provider.get_economic_snapshot()
print(f"VIX: {snapshot.vix}")
print(f"Market Regime: {snapshot.regime.value}")

# Get AI sector context
sector = provider.get_sector_context()
print(f"Tech vs Market: {sector.tech_vs_market*100:.2f}%")
print(f"AI Momentum: {sector.ai_sector_momentum}")

# Full outlook
outlook = provider.generate_ai_sector_outlook()
print(f"Recommendation: {outlook['assessment']['recommendation']}")

# Contextualize a signal
context = provider.contextualize_signal("nvidia", 7.5, "bullish")
print(f"Adjusted Sentiment: {context['signal_adjustment']['adjusted_sentiment']}")
```

### 4. Real-Time Validator (`scripts/realtime_validator.py`)

Standalone validation script for testing:

```bash
# Validate default AI companies
python scripts/realtime_validator.py --all-ai

# Validate specific entities
python scripts/realtime_validator.py --entities "nvidia,microsoft,google"

# Detailed single entity analysis
python scripts/realtime_validator.py --entity nvidia --detailed

# Custom output
python scripts/realtime_validator.py --all-ai --output results.json
```

## Validation Methodology

### Direction Alignment
Checks if briefAI's bullish/bearish signal matches actual price movement:

| briefAI Signal | Price Action | Alignment |
|----------------|--------------|-----------|
| Bullish (>6.0) | Up (>1%)     | ✅ Aligned |
| Bearish (<4.0) | Down (<-1%)  | ✅ Aligned |
| Bullish (>6.0) | Down (<-1%)  | ❌ Divergent |
| Bearish (<4.0) | Up (>1%)     | ❌ Divergent |

### Magnitude Alignment
Checks if signal strength matches price magnitude:

- Strong signal (>0.5 strength) should match significant moves (>2%)
- Weak signal (<0.2 strength) should match small moves (<1%)

### Technical Confirmation
Validates against technical indicators:

- **RSI**: Confirms overbought/oversold conditions
- **MACD**: Confirms momentum direction
- **Bollinger Bands**: Confirms price position
- **SMA**: Confirms trend direction

### Validation Score

Score is calculated as:
```
score = (direction_weight * direction_aligned) +
        (magnitude_weight * magnitude_aligned) +
        (technical_weight * technical_confirmed)

score *= (0.5 + confidence * 0.5)  # Confidence modifier
```

Weights:
- Direction: 40%
- Magnitude: 30%
- Technical: 30%

### Grading Scale

| Score Range | Grade | Interpretation |
|-------------|-------|----------------|
| ≥0.80       | A     | Strong validation |
| 0.65-0.79   | B     | Good validation |
| 0.50-0.64   | C     | Moderate validation |
| 0.35-0.49   | D     | Weak validation |
| <0.35       | F     | Poor validation |

## Market Regime Detection

The system detects four market regimes:

1. **Risk-On**: Low VIX (<15), positive GDP, steep yield curve
   - AI sector likely to outperform
   - Bullish signals more reliable

2. **Risk-Off**: High VIX (>25), inverted yield curve
   - AI sector may underperform
   - Bearish signals more reliable

3. **High Volatility**: VIX >35
   - All signals less reliable
   - Widen confidence intervals

4. **Transitional**: Mixed signals
   - Standard reliability
   - No strong bias

## Technical Indicators Used

### RSI (14-period)
- Overbought: >70 (caution on bullish signals)
- Oversold: <30 (caution on bearish signals)
- Neutral: 30-70

### MACD (12, 26, 9)
- Histogram >0: Bullish momentum
- Histogram <0: Bearish momentum
- Crossovers: Trend changes

### Bollinger Bands (20, 2)
- Above upper: Potentially overextended
- Below lower: Potentially oversold
- %B: Position within bands

### Moving Averages
- SMA 20: Short-term trend
- SMA 50: Medium-term trend
- SMA 200: Long-term trend

## Data Sources

### Primary (Free)
- **yfinance**: Real-time prices, historical data
- **Manual calculations**: Technical indicators (when pandas-ta unavailable)

### Enhanced (Optional)
- **pandas-ta**: Advanced technical analysis (requires Python <3.14)
- **fredapi**: Economic indicators from Federal Reserve
- **Fincept Terminal**: Enhanced data feeds

## Installation

```bash
# Core requirements
pip install yfinance numpy requests

# Enhanced (if Python version compatible)
pip install pandas-ta fredapi

# Full Fincept integration (optional)
pip install fincept-terminal
```

## Configuration

### Asset Mapping (`data/asset_mapping.json`)
Maps entity IDs to tickers:

```json
{
  "entities": {
    "nvidia": {
      "name": "NVIDIA",
      "status": "public",
      "tickers": ["NVDA"]
    },
    "openai": {
      "name": "OpenAI",
      "status": "private",
      "proxy_tickers": ["MSFT"]
    }
  }
}
```

### FRED API Key (Optional)
Set environment variable for economic indicators:

```bash
export FRED_API_KEY="your-api-key"
```

## Output Examples

### Single Validation Result
```json
{
  "entity_id": "nvidia",
  "ticker": "NVDA",
  "briefai_signal": {
    "sentiment": 7.5,
    "momentum": "bullish",
    "confidence": 0.8
  },
  "market_reality": {
    "current_price": 142.50,
    "price_change_1d": "+1.25%",
    "price_change_5d": "+3.80%"
  },
  "technicals": {
    "rsi_14": 62.5,
    "macd_histogram": 0.45,
    "bollinger_position": "upper_half"
  },
  "validation": {
    "direction_aligned": true,
    "magnitude_aligned": true,
    "technical_confirmed": true,
    "score": 0.82,
    "grade": "A"
  }
}
```

### Summary Report
```json
{
  "total_entities": 5,
  "summary": {
    "average_validation_score": 0.65,
    "direction_aligned_pct": 80.0,
    "technical_confirmed_pct": 60.0
  },
  "grade_distribution": {
    "A": 1,
    "B": 2,
    "C": 1,
    "D": 1,
    "F": 0
  }
}
```

## Best Practices

1. **Use Multiple Timeframes**: Validate against 1D, 5D, and 20D price changes
2. **Consider Market Regime**: Adjust expectations based on VIX and macro
3. **Weight by Confidence**: Higher confidence signals should align more strongly
4. **Monitor Divergences**: Systematic divergences may indicate model issues
5. **Update Mappings**: Keep asset_mapping.json current with new entities

## Limitations

1. **Latency**: Data is ~15min delayed (free tier)
2. **Python 3.14**: pandas-ta not yet compatible
3. **Private Companies**: Use proxy tickers (less accurate)
4. **Weekend/Holiday**: No fresh data during market closure

## Future Enhancements

- [ ] Intraday validation with live streaming
- [ ] Machine learning for adaptive thresholds
- [ ] Multi-asset correlation analysis
- [ ] Automated alert system for divergences
- [ ] Integration with portfolio management
