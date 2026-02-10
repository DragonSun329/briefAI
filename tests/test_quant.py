"""
Unit Tests for Quantitative Signal Modules

Tests for:
- utils/correlation_engine.py
- utils/momentum_signals.py
- utils/sentiment_technicals.py
- utils/quant_aggregator.py
"""

import pytest
from datetime import date, datetime, timedelta
from pathlib import Path
import json
import sys

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.correlation_engine import CorrelationEngine, CorrelationResult, LeadLagResult
from utils.momentum_signals import (
    MomentumCalculator, BuzzMomentum, FundingMomentum, MomentumSignal
)
from utils.sentiment_technicals import (
    SentimentTechnicals, SentimentMA, SentimentDivergence,
    VolumeWeightedSentiment, SentimentBollingerBands
)
from utils.quant_aggregator import (
    QuantAggregator, CompositeSignal, SignalWeight, LeaderboardEntry,
    run_quant_aggregation
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def sample_sentiment_history():
    """Generate sample sentiment history for testing."""
    base_date = date.today() - timedelta(days=60)
    history = {}
    sentiment = 5.0
    
    for i in range(60):
        dt = base_date + timedelta(days=i)
        # Slight upward drift with noise
        import random
        sentiment = max(1, min(10, sentiment + random.gauss(0.03, 0.3)))
        history[dt] = sentiment
    
    return history


@pytest.fixture
def sample_price_history():
    """Generate sample price history for testing."""
    base_date = date.today() - timedelta(days=60)
    history = {}
    price = 100.0
    
    for i in range(60):
        dt = base_date + timedelta(days=i)
        import random
        price = price * (1 + random.gauss(0.001, 0.02))
        history[dt] = price
    
    return history


@pytest.fixture
def sample_mention_history():
    """Generate sample mention counts for testing."""
    base_date = date.today() - timedelta(days=30)
    history = {}
    mentions = 50
    
    for i in range(30):
        dt = base_date + timedelta(days=i)
        import random
        mentions = max(1, int(mentions * (1 + random.gauss(0.05, 0.15))))
        history[dt] = mentions
    
    return history


@pytest.fixture
def sample_funding_events():
    """Generate sample funding events."""
    return [
        {"date": date.today() - timedelta(days=30), "amount_usd": 50_000_000, "round": "Series B"},
        {"date": date.today() - timedelta(days=180), "amount_usd": 10_000_000, "round": "Series A"},
        {"date": date.today() - timedelta(days=365), "amount_usd": 2_000_000, "round": "Seed"},
    ]


@pytest.fixture
def sample_articles():
    """Generate sample articles for volume-weighted sentiment."""
    return [
        {"source": "reuters", "sentiment": 7.5},
        {"source": "bloomberg", "sentiment": 7.0},
        {"source": "twitter", "sentiment": 8.5},
        {"source": "reddit", "sentiment": 9.0},
        {"source": "medium", "sentiment": 6.0},
        {"source": "hackernews", "sentiment": 6.5},
    ]


# =============================================================================
# Correlation Engine Tests
# =============================================================================

class TestCorrelationEngine:
    """Tests for CorrelationEngine."""
    
    def test_init(self):
        """Test engine initialization."""
        engine = CorrelationEngine()
        assert engine is not None
        assert engine.asset_mapping is not None
    
    def test_get_ticker_for_entity_public(self):
        """Test ticker lookup for public company."""
        engine = CorrelationEngine()
        ticker = engine.get_ticker_for_entity("nvidia")
        assert ticker == "NVDA"
    
    def test_get_ticker_for_entity_private(self):
        """Test ticker lookup for private company with proxy."""
        engine = CorrelationEngine()
        ticker = engine.get_ticker_for_entity("openai")
        # OpenAI uses MSFT as proxy
        assert ticker == "MSFT"
    
    def test_get_ticker_for_entity_unknown(self):
        """Test ticker lookup for unknown entity."""
        engine = CorrelationEngine()
        ticker = engine.get_ticker_for_entity("nonexistent-company-xyz")
        assert ticker is None
    
    def test_calculate_returns(self):
        """Test returns calculation."""
        engine = CorrelationEngine()
        
        prices = {
            date(2024, 1, 1): 100.0,
            date(2024, 1, 2): 102.0,
            date(2024, 1, 3): 101.0,
            date(2024, 1, 4): 105.0,
        }
        
        returns = engine.calculate_returns(prices, period_days=1)
        
        assert date(2024, 1, 2) in returns
        assert abs(returns[date(2024, 1, 2)] - 2.0) < 0.01  # ~2% return
    
    def test_correlate_sentiment_to_returns(self, sample_sentiment_history, sample_price_history):
        """Test correlation calculation."""
        engine = CorrelationEngine()
        returns = engine.calculate_returns(sample_price_history)
        
        result = engine.correlate_sentiment_to_returns(
            sample_sentiment_history,
            returns,
            lag_days=0
        )
        
        assert isinstance(result, CorrelationResult)
        assert -1 <= result.correlation <= 1
        assert result.sample_size > 0
    
    def test_find_optimal_lag(self, sample_sentiment_history):
        """Test lead/lag analysis."""
        engine = CorrelationEngine()
        
        result = engine.find_optimal_lag(
            "nvidia",
            sample_sentiment_history,
            max_lag_days=5
        )
        
        assert isinstance(result, LeadLagResult)
        assert result.ticker == "NVDA"
        assert -5 <= result.optimal_lag <= 5
        assert len(result.correlations_by_lag) > 0


# =============================================================================
# Momentum Signals Tests
# =============================================================================

class TestMomentumCalculator:
    """Tests for MomentumCalculator."""
    
    def test_calculate_rsi(self):
        """Test RSI calculation."""
        calc = MomentumCalculator()
        
        # Uptrending values should have high RSI
        values = [50 + i for i in range(20)]
        rsi = calc.calculate_rsi(values, period=14)
        
        assert 0 <= rsi <= 100
        assert rsi > 50  # Should be bullish with uptrend
    
    def test_calculate_rsi_downtrend(self):
        """Test RSI with downtrend."""
        calc = MomentumCalculator()
        
        values = [100 - i for i in range(20)]
        rsi = calc.calculate_rsi(values, period=14)
        
        assert 0 <= rsi <= 100
        assert rsi < 50  # Should be bearish with downtrend
    
    def test_calculate_macd(self):
        """Test MACD calculation."""
        calc = MomentumCalculator()
        
        values = list(range(50))
        macd, signal, histogram = calc.calculate_macd(values)
        
        # All should be numeric
        assert isinstance(macd, float)
        assert isinstance(signal, float)
        assert isinstance(histogram, float)
    
    def test_calculate_buzz_momentum(self, sample_mention_history):
        """Test buzz momentum calculation."""
        calc = MomentumCalculator()
        
        result = calc.calculate_buzz_momentum(
            "test-entity",
            sample_mention_history
        )
        
        assert isinstance(result, BuzzMomentum)
        assert result.entity_id == "test-entity"
        assert result.current_mentions > 0
        assert result.trend in ["accelerating", "decelerating", "stable", "strong_uptrend", "strong_downtrend"]
    
    def test_calculate_funding_momentum(self, sample_funding_events):
        """Test funding momentum calculation."""
        calc = MomentumCalculator()
        
        result = calc.calculate_funding_momentum(
            "test-entity",
            sample_funding_events
        )
        
        assert isinstance(result, FundingMomentum)
        assert result.entity_id == "test-entity"
        assert result.recent_funding_usd >= 0
        assert result.runway_signal in ["raising", "actively_raising", "deployed", "quiet"]
    
    def test_generate_sentiment_rsi(self, sample_sentiment_history):
        """Test sentiment RSI signal generation."""
        calc = MomentumCalculator()
        
        result = calc.generate_sentiment_rsi(
            "test-entity",
            sample_sentiment_history
        )
        
        assert isinstance(result, MomentumSignal)
        assert result.signal_type == "sentiment_rsi"
        assert 0 <= result.value <= 100
        assert result.interpretation in ["overbought", "oversold", "bullish_momentum", "bearish_momentum"]
    
    def test_calculate_all_momentum(self, sample_sentiment_history, sample_mention_history, sample_funding_events):
        """Test all momentum calculation."""
        calc = MomentumCalculator()
        
        result = calc.calculate_all_momentum(
            "test-entity",
            mention_history=sample_mention_history,
            sentiment_history=sample_sentiment_history,
            funding_events=sample_funding_events
        )
        
        assert "entity_id" in result
        assert "signals" in result
        assert len(result["signals"]) >= 1


# =============================================================================
# Sentiment Technicals Tests
# =============================================================================

class TestSentimentTechnicals:
    """Tests for SentimentTechnicals."""
    
    def test_calculate_sentiment_mas(self, sample_sentiment_history):
        """Test sentiment moving averages."""
        st = SentimentTechnicals()
        
        result = st.calculate_sentiment_mas(
            "test-entity",
            sample_sentiment_history
        )
        
        assert isinstance(result, SentimentMA)
        assert result.entity_id == "test-entity"
        assert result.sma_7 > 0
        assert result.sma_14 > 0
        assert result.sma_30 > 0
        assert result.trend in ["strong_bullish", "bullish", "consolidating", "bearish", "strong_bearish", "unknown"]
    
    def test_detect_divergence(self, sample_sentiment_history, sample_price_history):
        """Test divergence detection."""
        st = SentimentTechnicals()
        
        result = st.detect_divergence(
            "test-entity",
            sample_sentiment_history,
            sample_price_history
        )
        
        assert isinstance(result, SentimentDivergence)
        assert result.entity_id == "test-entity"
        assert result.divergence_type in [
            "bullish_divergence", "bearish_divergence", 
            "confirmation", "neutral", "insufficient_data"
        ]
    
    def test_volume_weighted_sentiment(self, sample_articles):
        """Test volume-weighted sentiment."""
        st = SentimentTechnicals()
        
        result = st.calculate_volume_weighted_sentiment(
            "test-entity",
            sample_articles
        )
        
        assert isinstance(result, VolumeWeightedSentiment)
        assert result.raw_sentiment > 0
        assert result.volume_weighted_sentiment > 0
        # High-volume sources (reuters, bloomberg) should pull VW closer to their sentiment
        assert result.high_volume_sentiment > 0
    
    def test_bollinger_bands(self, sample_sentiment_history):
        """Test Bollinger Bands calculation."""
        st = SentimentTechnicals()
        
        result = st.calculate_bollinger_bands(
            "test-entity",
            sample_sentiment_history
        )
        
        assert isinstance(result, SentimentBollingerBands)
        assert result.upper_band > result.middle_band
        assert result.middle_band > result.lower_band
        assert result.signal in [
            "overbought", "oversold", "normal", "squeeze",
            "upper_range", "lower_range", "insufficient_data"
        ]
    
    def test_analyze_entity(self, sample_sentiment_history, sample_price_history, sample_articles):
        """Test full entity analysis."""
        st = SentimentTechnicals()
        
        result = st.analyze_entity(
            "test-entity",
            sample_sentiment_history,
            price_history=sample_price_history,
            recent_articles=sample_articles
        )
        
        assert "entity_id" in result
        assert "moving_averages" in result
        assert "bollinger_bands" in result
        assert "net_signal" in result


# =============================================================================
# Quant Aggregator Tests
# =============================================================================

class TestQuantAggregator:
    """Tests for QuantAggregator."""
    
    def test_init(self):
        """Test aggregator initialization."""
        agg = QuantAggregator()
        assert len(agg.weights) > 0
    
    def test_signal_weight_adjustment(self):
        """Test that signal weights adjust based on accuracy."""
        weight = SignalWeight("test", base_weight=0.2)
        weight.historical_accuracy = 0.8
        weight.recent_performance = 0.7
        weight.calculate_adjusted_weight()
        
        # Adjusted weight should be higher than base with good accuracy
        assert weight.adjusted_weight > weight.base_weight * 0.5
    
    def test_aggregate_signals_empty(self):
        """Test aggregation with no signals."""
        agg = QuantAggregator()
        
        result = agg.aggregate_signals(
            "test-entity",
            "Test Entity",
            {}
        )
        
        assert isinstance(result, CompositeSignal)
        assert result.composite_score == 50  # Neutral
        assert result.direction == "neutral"
    
    def test_aggregate_signals_bullish(self):
        """Test aggregation with bullish signals."""
        agg = QuantAggregator()
        
        signals = {
            "correlation": {"correlation": 0.6, "significance": "high"},
            "buzz_momentum": {"momentum": 30, "trend": "accelerating"},
            "sentiment_rsi": {"value": 65, "interpretation": "bullish_momentum", "strength": 0.6},
            "moving_averages": {"trend": "bullish", "golden_cross": True, "death_cross": False},
        }
        
        result = agg.aggregate_signals("test", "Test", signals)
        
        assert result.composite_score > 50
        assert result.direction == "bullish"
    
    def test_aggregate_signals_bearish(self):
        """Test aggregation with bearish signals."""
        agg = QuantAggregator()
        
        signals = {
            "correlation": {"correlation": -0.3, "significance": "medium"},
            "buzz_momentum": {"momentum": -20, "trend": "decelerating"},
            "sentiment_rsi": {"value": 25, "interpretation": "bearish_momentum", "strength": 0.5},
            "moving_averages": {"trend": "bearish", "golden_cross": False, "death_cross": True},
        }
        
        result = agg.aggregate_signals("test", "Test", signals)
        
        assert result.composite_score < 50
        assert result.direction == "bearish"
    
    def test_generate_leaderboard(self):
        """Test leaderboard generation."""
        agg = QuantAggregator()
        
        signals = [
            CompositeSignal("a", "Entity A", 75, 0.8, "bullish"),  # 75*0.8 = 60
            CompositeSignal("b", "Entity B", 60, 0.6, "neutral"),  # 60*0.6 = 36
            CompositeSignal("c", "Entity C", 85, 0.9, "bullish"),  # 85*0.9 = 76.5
        ]
        
        leaderboard = agg.generate_leaderboard(signals)
        
        assert len(leaderboard) == 3
        assert leaderboard[0].entity_id == "c"  # Highest quality-adjusted score (76.5)
        assert leaderboard[0].rank == 1
    
    def test_generate_report(self):
        """Test report generation."""
        agg = QuantAggregator()
        
        leaderboard = [
            LeaderboardEntry(1, "a", "A", 80, 0.8, "bullish", ["corr"], "accelerating"),
            LeaderboardEntry(2, "b", "B", 60, 0.6, "neutral", ["buzz"], "steady"),
            LeaderboardEntry(3, "c", "C", 40, 0.7, "bearish", ["rsi"], "decelerating"),
        ]
        
        report = agg.generate_report(leaderboard)
        
        assert "summary" in report
        assert report["summary"]["bullish_count"] == 1
        assert report["summary"]["bearish_count"] == 1
        assert "top_bullish" in report
        assert "top_bearish" in report


class TestRunQuantAggregation:
    """Test the convenience function."""
    
    def test_run_quant_aggregation(self):
        """Test full aggregation flow."""
        entity_signals = {
            "nvidia": {
                "correlation": {"correlation": 0.5, "significance": "high"},
                "buzz_momentum": {"momentum": 20, "trend": "accelerating"},
            },
            "openai": {
                "buzz_momentum": {"momentum": 30, "trend": "strong_uptrend"},
                "funding_momentum": {"sector_relative": 2.0, "runway_signal": "raising"},
            },
        }
        
        result = run_quant_aggregation(
            entity_signals,
            {"nvidia": "NVIDIA", "openai": "OpenAI"}
        )
        
        assert "composite_signals" in result
        assert "leaderboard" in result
        assert "report" in result
        assert len(result["leaderboard"]) == 2


# =============================================================================
# Integration Tests
# =============================================================================

class TestQuantIntegration:
    """Integration tests combining multiple modules."""
    
    def test_full_pipeline(self, sample_sentiment_history, sample_mention_history, sample_funding_events):
        """Test full analysis pipeline."""
        # Run momentum analysis
        calc = MomentumCalculator()
        momentum_result = calc.calculate_all_momentum(
            "test-entity",
            mention_history=sample_mention_history,
            sentiment_history=sample_sentiment_history,
            funding_events=sample_funding_events
        )
        
        # Run sentiment technicals
        st = SentimentTechnicals()
        tech_result = st.analyze_entity(
            "test-entity",
            sample_sentiment_history
        )
        
        # Combine signals for aggregation
        combined_signals = {
            **momentum_result.get("signals", {}),
            **{k: v for k, v in tech_result.items() if isinstance(v, dict) and "entity_id" not in v}
        }
        
        # Aggregate
        agg = QuantAggregator()
        composite = agg.aggregate_signals(
            "test-entity",
            "Test Entity",
            combined_signals
        )
        
        assert composite.composite_score >= 0
        assert composite.composite_score <= 100
        assert len(composite.components) >= 1


# =============================================================================
# Asset Mapping Tests
# =============================================================================

class TestAssetMapping:
    """Test asset mapping file."""
    
    def test_mapping_file_exists(self):
        """Test that asset mapping file exists."""
        mapping_path = project_root / "data" / "asset_mapping.json"
        assert mapping_path.exists()
    
    def test_mapping_structure(self):
        """Test asset mapping structure."""
        mapping_path = project_root / "data" / "asset_mapping.json"
        
        with open(mapping_path, 'r') as f:
            mapping = json.load(f)
        
        assert "entities" in mapping
        assert "crypto_mapping" in mapping
        assert "sector_etfs" in mapping
        
        # Check specific entities
        assert "nvidia" in mapping["entities"]
        assert "openai" in mapping["entities"]
        
        # Check nvidia has ticker
        assert "tickers" in mapping["entities"]["nvidia"]
        assert "NVDA" in mapping["entities"]["nvidia"]["tickers"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
