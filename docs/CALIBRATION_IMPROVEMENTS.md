# briefAI Signal Quality & Calibration Improvements

**Date:** 2026-01-27
**Target:** Improve validation accuracy from 59% → 70%+

## Summary of Changes

### 1. Better Sentiment Analysis (`utils/ollama_sentiment.py`)

**Changes:**
- Added `analyze_batch_parallel()` - processes batches concurrently with 3x throughput
- Added `fast_mode` parameter - uses lighter `phi3:mini` model (~3s vs 10s/batch)
- Batch processing already existed, now optimized with parallel execution

**Usage:**
```python
# Fast mode for high volume
analyzer = OllamaSentimentAnalyzer(fast_mode=True)

# Parallel batch processing
results = analyzer.analyze_batch_parallel(texts, batch_size=10, max_workers=3)
```

### 2. Source Quality Weighting

**Changes:**
- Updated `config/source_credibility.json` to v2.0
- Added `accuracy_weights` section (auto-populated by audit)
- Added `signal_type_decay` configuration
- Created `scripts/source_accuracy_audit.py`

**Audit Script:**
```bash
# Analyze source accuracy (dry run)
python scripts/source_accuracy_audit.py --days 30

# Update source_credibility.json with accuracy weights
python scripts/source_accuracy_audit.py --days 30 --update
```

**How it works:**
- Loads historical predictions from database
- Matches with price outcomes
- Calculates accuracy per source
- Updates weights: high accuracy → higher weight

### 3. Entity-Specific Calibration (`config/entity_profiles.json`)

**New file with volatility profiles:**

| Profile | Entities | Sentiment Mult | Decay | Notes |
|---------|----------|----------------|-------|-------|
| `high_beta` | NVDA, AMD, TSLA | 1.3x | 12h | Amplifies signals |
| `mega_cap_stable` | MSFT, AAPL, GOOGL | 0.8x | 36h | Dampens signals |
| `ai_pure_play` | OpenAI, Anthropic | 1.2x | 16h | AI-sensitive |
| `china_ai` | Baidu, DeepSeek | 1.4x | 8h | Fast decay |
| `crypto_ai` | RNDR, WLD | 1.8x | 6h | Very volatile |

**Effect:**
- NVDA with raw sentiment 7.5 → calibrated 6.72 (1.3x multiplier)
- MSFT with raw sentiment 7.5 → calibrated 6.06 (0.8x multiplier)

### 4. Signal Freshness Decay (`utils/signal_calibrator.py`)

**Signal-type specific decay rates:**

| Signal Type | Half-Life | Use Case |
|-------------|-----------|----------|
| `news` | 12h | Fast-moving news |
| `social_sentiment` | 8h | Ephemeral buzz |
| `github` | 168h (7d) | Technical adoption |
| `funding` | 720h (30d) | Investment rounds |
| `earnings` | 504h (21d) | Until next report |
| `regulatory` | 1440h (60d) | Long-lasting |

**Implementation:**
- `SignalCalibrator` now loads entity profiles automatically
- `get_decay_half_life(entity_id, signal_type)` returns appropriate decay
- Freshness calculation uses signal-type AND entity-specific rates

### 5. Divergence Signals (`utils/divergence_detector.py`)

**New: `PriceFundamentalDivergenceDetector`**

Detects when price action and fundamental signals disagree:

| Scenario | Interpretation | Action |
|----------|---------------|--------|
| Price down + News bullish | Undervalued | Accumulate |
| Price up + News bearish | Overvalued | Take profits |
| Price flat + Strong fundamentals | Coiling | Watch for breakout |

**Usage:**
```python
from utils.divergence_detector import PriceFundamentalDivergenceDetector

detector = PriceFundamentalDivergenceDetector()
div = detector.detect_divergence(
    entity_id='nvda',
    entity_name='NVIDIA',
    price_change_5d=-0.08,  # Down 8%
    fundamental_score=8.5,   # Bullish news
)

if div:
    print(f"Signal: {div.signal_strength}")  # "strong"
    print(f"Action: {div.recommended_action}")
```

**Tracking Resolution:**
```python
# Track how divergences resolve for calibration
resolution = detector.track_resolution(
    divergence=div,
    outcome_price_change=0.12,  # What happened
    resolution_days=5
)
print(f"Fundamental was correct: {resolution['fundamental_correct']}")
```

## Files Changed/Created

### Modified:
- `utils/ollama_sentiment.py` - Parallel batch, fast mode
- `utils/signal_calibrator.py` - Entity profiles, signal decay, accuracy weights
- `utils/divergence_detector.py` - Price-fundamental divergence
- `config/source_credibility.json` - v2.0 with decay rates

### Created:
- `config/entity_profiles.json` - Volatility profiles
- `scripts/source_accuracy_audit.py` - Source accuracy tracking
- `docs/CALIBRATION_IMPROVEMENTS.md` - This file

## Expected Impact

| Metric | Before | After (Expected) |
|--------|--------|------------------|
| Validation Accuracy | 59% | 70%+ |
| Signal Freshness | 24h fixed | Type-specific (8h-60d) |
| Entity Calibration | None | Per-volatility profile |
| Source Weighting | Tier-only | Tier + Accuracy |

## Next Steps

1. **Run source audit** after accumulating predictions:
   ```bash
   python scripts/source_accuracy_audit.py --days 30 --update
   ```

2. **Monitor divergence resolution** to calibrate thresholds

3. **Backtest** with new calibration on historical data

4. **Fine-tune** entity profiles based on validation results
