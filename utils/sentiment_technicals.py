"""
Sentiment Technicals Module

Technical analysis tools adapted for sentiment data:
- Moving averages of sentiment scores
- Sentiment divergence detection (price vs sentiment)
- Volume-weighted sentiment (high-volume sources matter more)
- Bollinger Bands for sentiment anomaly detection
"""

from __future__ import annotations

import statistics
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
from loguru import logger

import numpy as np


@dataclass
class SentimentMA:
    """Moving average result for sentiment."""
    entity_id: str
    current_sentiment: float
    sma_7: float   # 7-day simple MA
    sma_14: float  # 14-day simple MA
    sma_30: float  # 30-day simple MA
    ema_7: float   # 7-day exponential MA
    ema_14: float  # 14-day exponential MA
    trend: str     # "bullish", "bearish", "consolidating"
    golden_cross: bool  # Short-term crossed above long-term
    death_cross: bool   # Short-term crossed below long-term
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "current_sentiment": round(self.current_sentiment, 3),
            "sma_7": round(self.sma_7, 3),
            "sma_14": round(self.sma_14, 3),
            "sma_30": round(self.sma_30, 3),
            "ema_7": round(self.ema_7, 3),
            "ema_14": round(self.ema_14, 3),
            "trend": self.trend,
            "golden_cross": self.golden_cross,
            "death_cross": self.death_cross,
        }


@dataclass
class SentimentDivergence:
    """Divergence between sentiment and price/other metric."""
    entity_id: str
    divergence_type: str  # "bullish_divergence", "bearish_divergence", "confirmation"
    sentiment_direction: str  # "up", "down", "flat"
    price_direction: str  # "up", "down", "flat"
    magnitude: float  # 0-1, how significant
    interpretation: str
    actionable: bool
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "divergence_type": self.divergence_type,
            "sentiment_direction": self.sentiment_direction,
            "price_direction": self.price_direction,
            "magnitude": round(self.magnitude, 4),
            "interpretation": self.interpretation,
            "actionable": self.actionable,
        }


@dataclass
class VolumeWeightedSentiment:
    """Volume-weighted sentiment calculation."""
    entity_id: str
    raw_sentiment: float
    volume_weighted_sentiment: float
    high_volume_sentiment: float  # Sentiment from high-volume sources only
    low_volume_sentiment: float   # Sentiment from low-volume sources
    volume_sentiment_gap: float   # High - Low volume sentiment
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "raw_sentiment": round(self.raw_sentiment, 3),
            "volume_weighted_sentiment": round(self.volume_weighted_sentiment, 3),
            "high_volume_sentiment": round(self.high_volume_sentiment, 3),
            "low_volume_sentiment": round(self.low_volume_sentiment, 3),
            "volume_sentiment_gap": round(self.volume_sentiment_gap, 3),
        }


@dataclass
class SentimentBollingerBands:
    """Bollinger Bands for sentiment anomaly detection."""
    entity_id: str
    current_sentiment: float
    middle_band: float  # SMA
    upper_band: float   # SMA + 2*std
    lower_band: float   # SMA - 2*std
    bandwidth: float    # Band width (volatility indicator)
    percent_b: float    # Where current is relative to bands (0-1)
    signal: str         # "overbought", "oversold", "normal", "squeeze"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "current_sentiment": round(self.current_sentiment, 3),
            "middle_band": round(self.middle_band, 3),
            "upper_band": round(self.upper_band, 3),
            "lower_band": round(self.lower_band, 3),
            "bandwidth": round(self.bandwidth, 3),
            "percent_b": round(self.percent_b, 3),
            "signal": self.signal,
        }


class SentimentTechnicals:
    """
    Technical analysis tools for sentiment data.
    
    These tools help identify:
    - Trend direction and strength
    - Overbought/oversold conditions
    - Divergences between sentiment and price
    - Anomalies in sentiment patterns
    """
    
    SOURCE_VOLUME_WEIGHTS = {
        # Major news outlets
        "reuters": 1.0,
        "bloomberg": 1.0,
        "wsj": 0.95,
        "ft": 0.9,
        "techcrunch": 0.85,
        "the_verge": 0.8,
        "wired": 0.8,
        "ars_technica": 0.75,
        
        # Research / Academia
        "arxiv": 0.7,
        "nature": 0.9,
        "science": 0.9,
        
        # Social
        "twitter": 0.5,
        "reddit": 0.4,
        "hackernews": 0.6,
        
        # Blogs / Other
        "medium": 0.3,
        "substack": 0.4,
        "default": 0.5
    }
    
    def __init__(self):
        pass
    
    def _sma(self, values: List[float], period: int) -> float:
        """Calculate Simple Moving Average."""
        if not values:
            return 0.0
        if len(values) < period:
            return sum(values) / len(values)
        return sum(values[-period:]) / period
    
    def _ema(self, values: List[float], period: int) -> float:
        """Calculate Exponential Moving Average."""
        if not values:
            return 0.0
        if len(values) < period:
            return sum(values) / len(values)
        
        multiplier = 2 / (period + 1)
        ema = sum(values[:period]) / period
        
        for value in values[period:]:
            ema = (value - ema) * multiplier + ema
        
        return ema
    
    def _std(self, values: List[float], period: int) -> float:
        """Calculate standard deviation."""
        if len(values) < 2:
            return 0.0
        
        subset = values[-period:] if len(values) >= period else values
        return statistics.stdev(subset) if len(subset) > 1 else 0.0
    
    def calculate_sentiment_mas(
        self,
        entity_id: str,
        sentiment_history: Dict[date, float]
    ) -> SentimentMA:
        """
        Calculate moving averages for sentiment scores.
        
        Args:
            entity_id: Entity identifier
            sentiment_history: Dict of date -> sentiment score
            
        Returns:
            SentimentMA with all MA calculations
        """
        sorted_dates = sorted(sentiment_history.keys())
        values = [sentiment_history[d] for d in sorted_dates]
        
        if not values:
            return SentimentMA(
                entity_id=entity_id,
                current_sentiment=0,
                sma_7=0, sma_14=0, sma_30=0,
                ema_7=0, ema_14=0,
                trend="unknown",
                golden_cross=False,
                death_cross=False
            )
        
        current = values[-1]
        sma_7 = self._sma(values, 7)
        sma_14 = self._sma(values, 14)
        sma_30 = self._sma(values, 30)
        ema_7 = self._ema(values, 7)
        ema_14 = self._ema(values, 14)
        
        # Determine trend
        if current > sma_7 > sma_14 > sma_30:
            trend = "strong_bullish"
        elif current > sma_7 and sma_7 > sma_14:
            trend = "bullish"
        elif current < sma_7 < sma_14 < sma_30:
            trend = "strong_bearish"
        elif current < sma_7 and sma_7 < sma_14:
            trend = "bearish"
        else:
            trend = "consolidating"
        
        # Check for crossovers (need previous day data)
        golden_cross = False
        death_cross = False
        
        if len(values) >= 2:
            # Calculate yesterday's MAs
            prev_values = values[:-1]
            prev_sma_7 = self._sma(prev_values, 7)
            prev_sma_14 = self._sma(prev_values, 14)
            
            # Golden cross: short MA crosses above long MA
            if prev_sma_7 <= prev_sma_14 and sma_7 > sma_14:
                golden_cross = True
            
            # Death cross: short MA crosses below long MA
            if prev_sma_7 >= prev_sma_14 and sma_7 < sma_14:
                death_cross = True
        
        return SentimentMA(
            entity_id=entity_id,
            current_sentiment=current,
            sma_7=sma_7,
            sma_14=sma_14,
            sma_30=sma_30,
            ema_7=ema_7,
            ema_14=ema_14,
            trend=trend,
            golden_cross=golden_cross,
            death_cross=death_cross
        )
    
    def detect_divergence(
        self,
        entity_id: str,
        sentiment_history: Dict[date, float],
        price_history: Dict[date, float],
        lookback_days: int = 14
    ) -> SentimentDivergence:
        """
        Detect divergence between sentiment and price.
        
        Bullish divergence: Price falling, sentiment rising (buy signal)
        Bearish divergence: Price rising, sentiment falling (sell signal)
        
        Args:
            entity_id: Entity identifier
            sentiment_history: Dict of date -> sentiment
            price_history: Dict of date -> price
            lookback_days: Period to analyze
            
        Returns:
            SentimentDivergence with analysis
        """
        # Get aligned data
        common_dates = set(sentiment_history.keys()) & set(price_history.keys())
        if len(common_dates) < 5:
            return SentimentDivergence(
                entity_id=entity_id,
                divergence_type="insufficient_data",
                sentiment_direction="unknown",
                price_direction="unknown",
                magnitude=0,
                interpretation="Insufficient overlapping data",
                actionable=False
            )
        
        sorted_dates = sorted(common_dates)[-lookback_days:]
        
        # Calculate direction of each series
        sent_start = sentiment_history[sorted_dates[0]]
        sent_end = sentiment_history[sorted_dates[-1]]
        price_start = price_history[sorted_dates[0]]
        price_end = price_history[sorted_dates[-1]]
        
        # Percentage changes
        sent_change = (sent_end - sent_start) / max(abs(sent_start), 0.01)
        price_change = (price_end - price_start) / max(abs(price_start), 0.01)
        
        # Determine directions
        threshold = 0.05  # 5% change threshold
        
        if sent_change > threshold:
            sent_dir = "up"
        elif sent_change < -threshold:
            sent_dir = "down"
        else:
            sent_dir = "flat"
        
        if price_change > threshold:
            price_dir = "up"
        elif price_change < -threshold:
            price_dir = "down"
        else:
            price_dir = "flat"
        
        # Detect divergence type
        if sent_dir == "up" and price_dir == "down":
            div_type = "bullish_divergence"
            interpretation = "Sentiment improving while price declining - potential reversal signal"
            actionable = True
        elif sent_dir == "down" and price_dir == "up":
            div_type = "bearish_divergence"
            interpretation = "Sentiment deteriorating while price rising - caution warranted"
            actionable = True
        elif sent_dir == price_dir:
            div_type = "confirmation"
            interpretation = f"Sentiment and price both moving {sent_dir} - trend confirmed"
            actionable = False
        else:
            div_type = "neutral"
            interpretation = "No clear divergence pattern"
            actionable = False
        
        # Magnitude is the sum of absolute changes
        magnitude = min(1.0, (abs(sent_change) + abs(price_change)) / 2)
        
        return SentimentDivergence(
            entity_id=entity_id,
            divergence_type=div_type,
            sentiment_direction=sent_dir,
            price_direction=price_dir,
            magnitude=magnitude,
            interpretation=interpretation,
            actionable=actionable
        )
    
    def calculate_volume_weighted_sentiment(
        self,
        entity_id: str,
        articles: List[Dict[str, Any]]
    ) -> VolumeWeightedSentiment:
        """
        Calculate volume-weighted sentiment from articles.
        
        High-volume sources (Reuters, Bloomberg) get more weight than
        low-volume sources (blogs, social).
        
        Args:
            entity_id: Entity identifier
            articles: List of articles with "source", "sentiment" keys
            
        Returns:
            VolumeWeightedSentiment analysis
        """
        if not articles:
            return VolumeWeightedSentiment(
                entity_id=entity_id,
                raw_sentiment=0,
                volume_weighted_sentiment=0,
                high_volume_sentiment=0,
                low_volume_sentiment=0,
                volume_sentiment_gap=0
            )
        
        # Raw average sentiment
        sentiments = [a.get("sentiment", 0) for a in articles if "sentiment" in a]
        raw_sentiment = sum(sentiments) / len(sentiments) if sentiments else 0
        
        # Volume-weighted sentiment
        weighted_sum = 0
        total_weight = 0
        high_volume_sum = 0
        high_volume_weight = 0
        low_volume_sum = 0
        low_volume_weight = 0
        
        HIGH_VOLUME_THRESHOLD = 0.7
        
        for article in articles:
            sentiment = article.get("sentiment", 0)
            source = article.get("source", "default").lower().replace(" ", "_")
            weight = self.SOURCE_VOLUME_WEIGHTS.get(source, self.SOURCE_VOLUME_WEIGHTS["default"])
            
            weighted_sum += sentiment * weight
            total_weight += weight
            
            if weight >= HIGH_VOLUME_THRESHOLD:
                high_volume_sum += sentiment * weight
                high_volume_weight += weight
            else:
                low_volume_sum += sentiment * weight
                low_volume_weight += weight
        
        vw_sentiment = weighted_sum / total_weight if total_weight > 0 else 0
        high_vol_sent = high_volume_sum / high_volume_weight if high_volume_weight > 0 else 0
        low_vol_sent = low_volume_sum / low_volume_weight if low_volume_weight > 0 else 0
        
        return VolumeWeightedSentiment(
            entity_id=entity_id,
            raw_sentiment=raw_sentiment,
            volume_weighted_sentiment=vw_sentiment,
            high_volume_sentiment=high_vol_sent,
            low_volume_sentiment=low_vol_sent,
            volume_sentiment_gap=high_vol_sent - low_vol_sent
        )
    
    def calculate_bollinger_bands(
        self,
        entity_id: str,
        sentiment_history: Dict[date, float],
        period: int = 20,
        num_std: float = 2.0
    ) -> SentimentBollingerBands:
        """
        Calculate Bollinger Bands for sentiment.
        
        Useful for detecting sentiment extremes and volatility.
        
        Args:
            entity_id: Entity identifier
            sentiment_history: Dict of date -> sentiment
            period: MA period for middle band
            num_std: Number of standard deviations for bands
            
        Returns:
            SentimentBollingerBands analysis
        """
        sorted_dates = sorted(sentiment_history.keys())
        values = [sentiment_history[d] for d in sorted_dates]
        
        if len(values) < period:
            return SentimentBollingerBands(
                entity_id=entity_id,
                current_sentiment=values[-1] if values else 0,
                middle_band=self._sma(values, period),
                upper_band=0,
                lower_band=0,
                bandwidth=0,
                percent_b=0.5,
                signal="insufficient_data"
            )
        
        current = values[-1]
        middle = self._sma(values, period)
        std = self._std(values, period)
        
        upper = middle + (num_std * std)
        lower = middle - (num_std * std)
        
        # Bandwidth (volatility indicator)
        bandwidth = (upper - lower) / middle if middle != 0 else 0
        
        # Percent B (where current is relative to bands)
        # 0 = at lower band, 1 = at upper band, 0.5 = at middle
        if upper != lower:
            percent_b = (current - lower) / (upper - lower)
        else:
            percent_b = 0.5
        
        # Determine signal
        if percent_b > 1.0:
            signal = "overbought"
        elif percent_b < 0.0:
            signal = "oversold"
        elif bandwidth < 0.1:
            signal = "squeeze"  # Low volatility, potential breakout
        elif percent_b > 0.8:
            signal = "upper_range"
        elif percent_b < 0.2:
            signal = "lower_range"
        else:
            signal = "normal"
        
        return SentimentBollingerBands(
            entity_id=entity_id,
            current_sentiment=current,
            middle_band=middle,
            upper_band=upper,
            lower_band=lower,
            bandwidth=bandwidth,
            percent_b=percent_b,
            signal=signal
        )
    
    def analyze_entity(
        self,
        entity_id: str,
        sentiment_history: Dict[date, float],
        price_history: Optional[Dict[date, float]] = None,
        recent_articles: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Complete sentiment technical analysis for an entity.
        
        Args:
            entity_id: Entity identifier
            sentiment_history: Historical sentiment data
            price_history: Optional price data for divergence
            recent_articles: Optional articles for volume-weighted sentiment
            
        Returns:
            Dict with all technical indicators
        """
        result = {
            "entity_id": entity_id,
            "analyzed_at": datetime.now().isoformat(),
        }
        
        # Moving averages
        mas = self.calculate_sentiment_mas(entity_id, sentiment_history)
        result["moving_averages"] = mas.to_dict()
        
        # Bollinger bands
        bb = self.calculate_bollinger_bands(entity_id, sentiment_history)
        result["bollinger_bands"] = bb.to_dict()
        
        # Divergence (if price data available)
        if price_history:
            div = self.detect_divergence(entity_id, sentiment_history, price_history)
            result["divergence"] = div.to_dict()
        
        # Volume-weighted sentiment (if articles available)
        if recent_articles:
            vws = self.calculate_volume_weighted_sentiment(entity_id, recent_articles)
            result["volume_weighted"] = vws.to_dict()
        
        # Summary signals
        signals = []
        
        if mas.golden_cross:
            signals.append({"type": "golden_cross", "direction": "bullish", "weight": 0.7})
        if mas.death_cross:
            signals.append({"type": "death_cross", "direction": "bearish", "weight": 0.7})
        
        if bb.signal == "overbought":
            signals.append({"type": "overbought", "direction": "bearish", "weight": 0.5})
        elif bb.signal == "oversold":
            signals.append({"type": "oversold", "direction": "bullish", "weight": 0.5})
        elif bb.signal == "squeeze":
            signals.append({"type": "volatility_squeeze", "direction": "neutral", "weight": 0.3})
        
        if price_history:
            if result.get("divergence", {}).get("divergence_type") == "bullish_divergence":
                signals.append({"type": "bullish_divergence", "direction": "bullish", "weight": 0.8})
            elif result.get("divergence", {}).get("divergence_type") == "bearish_divergence":
                signals.append({"type": "bearish_divergence", "direction": "bearish", "weight": 0.8})
        
        result["signals"] = signals
        
        # Net signal strength
        bullish_strength = sum(s["weight"] for s in signals if s["direction"] == "bullish")
        bearish_strength = sum(s["weight"] for s in signals if s["direction"] == "bearish")
        
        result["net_signal"] = {
            "bullish_strength": round(bullish_strength, 2),
            "bearish_strength": round(bearish_strength, 2),
            "net": round(bullish_strength - bearish_strength, 2),
            "bias": "bullish" if bullish_strength > bearish_strength else 
                   "bearish" if bearish_strength > bullish_strength else "neutral"
        }
        
        return result


if __name__ == "__main__":
    # Test sentiment technicals
    print("Testing Sentiment Technicals")
    print("=" * 50)
    
    from random import gauss
    
    st = SentimentTechnicals()
    
    # Generate synthetic sentiment data
    base_date = date.today() - timedelta(days=60)
    sentiment_history = {}
    sentiment = 5.0
    
    for i in range(60):
        dt = base_date + timedelta(days=i)
        # Add slight upward trend + noise
        sentiment = max(1, min(10, sentiment + gauss(0.02, 0.3)))
        sentiment_history[dt] = sentiment
    
    # Test MAs
    mas = st.calculate_sentiment_mas("test-entity", sentiment_history)
    print(f"\nMoving Averages:")
    print(f"  Current: {mas.current_sentiment:.2f}")
    print(f"  SMA 7: {mas.sma_7:.2f}")
    print(f"  SMA 14: {mas.sma_14:.2f}")
    print(f"  SMA 30: {mas.sma_30:.2f}")
    print(f"  Trend: {mas.trend}")
    print(f"  Golden Cross: {mas.golden_cross}")
    print(f"  Death Cross: {mas.death_cross}")
    
    # Test Bollinger Bands
    bb = st.calculate_bollinger_bands("test-entity", sentiment_history)
    print(f"\nBollinger Bands:")
    print(f"  Current: {bb.current_sentiment:.2f}")
    print(f"  Middle: {bb.middle_band:.2f}")
    print(f"  Upper: {bb.upper_band:.2f}")
    print(f"  Lower: {bb.lower_band:.2f}")
    print(f"  %B: {bb.percent_b:.2f}")
    print(f"  Signal: {bb.signal}")
    
    # Test volume-weighted sentiment
    sample_articles = [
        {"source": "reuters", "sentiment": 7.5},
        {"source": "bloomberg", "sentiment": 7.0},
        {"source": "twitter", "sentiment": 8.5},
        {"source": "reddit", "sentiment": 9.0},
        {"source": "medium", "sentiment": 6.0},
    ]
    
    vws = st.calculate_volume_weighted_sentiment("test-entity", sample_articles)
    print(f"\nVolume-Weighted Sentiment:")
    print(f"  Raw: {vws.raw_sentiment:.2f}")
    print(f"  Volume-Weighted: {vws.volume_weighted_sentiment:.2f}")
    print(f"  High-Volume Sources: {vws.high_volume_sentiment:.2f}")
    print(f"  Low-Volume Sources: {vws.low_volume_sentiment:.2f}")
    print(f"  Gap: {vws.volume_sentiment_gap:.2f}")
    
    # Full analysis
    print("\n" + "=" * 50)
    print("Full Analysis:")
    
    # Generate price data (diverging from sentiment)
    price_history = {}
    price = 100.0
    for dt in sentiment_history.keys():
        # Price goes opposite direction
        price = price * (1 + gauss(-0.005, 0.02))
        price_history[dt] = price
    
    result = st.analyze_entity(
        "test-entity",
        sentiment_history,
        price_history=price_history,
        recent_articles=sample_articles
    )
    
    print(f"  Signals: {len(result['signals'])}")
    for sig in result['signals']:
        print(f"    - {sig['type']}: {sig['direction']} (weight {sig['weight']})")
    
    print(f"\n  Net Signal:")
    net = result['net_signal']
    print(f"    Bullish: {net['bullish_strength']}")
    print(f"    Bearish: {net['bearish_strength']}")
    print(f"    Bias: {net['bias']}")
