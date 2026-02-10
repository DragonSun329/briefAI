"""
Momentum Signals Module

Implements technical indicators for non-price data:
- Buzz Momentum: Rate of change in mentions/coverage
- Funding Momentum: Acceleration of capital deployment
- RSI-style indicators for sentiment and engagement
- MACD-style crossover signals for trend detection
"""

from __future__ import annotations

import statistics
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from collections import deque
from loguru import logger

import numpy as np


@dataclass
class MomentumSignal:
    """A single momentum signal measurement."""
    entity_id: str
    signal_type: str  # "buzz", "funding", "sentiment_rsi", "media_macd"
    value: float
    interpretation: str  # "overbought", "oversold", "neutral", "bullish_crossover", etc.
    strength: float  # 0-1
    as_of: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "signal_type": self.signal_type,
            "value": round(self.value, 4),
            "interpretation": self.interpretation,
            "strength": round(self.strength, 4),
            "as_of": self.as_of.isoformat(),
        }


@dataclass
class BuzzMomentum:
    """Buzz momentum calculation result."""
    entity_id: str
    current_mentions: int
    ma_short: float  # Short-term moving average
    ma_long: float   # Long-term moving average
    momentum: float  # Rate of change
    acceleration: float  # Second derivative
    trend: str  # "accelerating", "decelerating", "stable"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "current_mentions": self.current_mentions,
            "ma_short": round(self.ma_short, 2),
            "ma_long": round(self.ma_long, 2),
            "momentum": round(self.momentum, 4),
            "acceleration": round(self.acceleration, 4),
            "trend": self.trend,
        }


@dataclass
class FundingMomentum:
    """Funding momentum calculation result."""
    entity_id: str
    recent_funding_usd: float
    funding_velocity: float  # $/day
    funding_acceleration: float  # Change in velocity
    runway_signal: str  # "raising", "deployed", "quiet"
    sector_relative: float  # Relative to sector average
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "recent_funding_usd": self.recent_funding_usd,
            "funding_velocity": round(self.funding_velocity, 2),
            "funding_acceleration": round(self.funding_acceleration, 4),
            "runway_signal": self.runway_signal,
            "sector_relative": round(self.sector_relative, 4),
        }


class MomentumCalculator:
    """
    Calculates momentum indicators for non-price data.
    
    Adapts traditional technical indicators (RSI, MACD, ROC) to work with:
    - News mention counts
    - Sentiment scores
    - Funding amounts
    - GitHub stars/activity
    """
    
    def __init__(self):
        self._ema_cache: Dict[str, deque] = {}
    
    def calculate_rsi(
        self,
        values: List[float],
        period: int = 14
    ) -> float:
        """
        Calculate Relative Strength Index for any time series.
        
        Args:
            values: Time series values (oldest to newest)
            period: RSI period (default 14)
            
        Returns:
            RSI value (0-100)
        """
        if len(values) < period + 1:
            return 50.0  # Neutral when insufficient data
        
        # Calculate price changes
        changes = [values[i] - values[i-1] for i in range(1, len(values))]
        
        # Use most recent period
        recent_changes = changes[-(period):]
        
        gains = [max(0, c) for c in recent_changes]
        losses = [abs(min(0, c)) for c in recent_changes]
        
        avg_gain = sum(gains) / period if gains else 0
        avg_loss = sum(losses) / period if losses else 0.0001  # Avoid division by zero
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def calculate_macd(
        self,
        values: List[float],
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9
    ) -> Tuple[float, float, float]:
        """
        Calculate MACD (Moving Average Convergence Divergence).
        
        Args:
            values: Time series values
            fast_period: Fast EMA period
            slow_period: Slow EMA period
            signal_period: Signal line period
            
        Returns:
            Tuple of (macd_line, signal_line, histogram)
        """
        if len(values) < slow_period:
            return 0.0, 0.0, 0.0
        
        fast_ema = self._ema(values, fast_period)
        slow_ema = self._ema(values, slow_period)
        
        macd_line = fast_ema - slow_ema
        
        # For signal line, we need MACD history
        # Simplified: use recent values
        macd_values = []
        for i in range(signal_period, len(values) + 1):
            subset = values[:i]
            fast = self._ema(subset, fast_period)
            slow = self._ema(subset, slow_period)
            macd_values.append(fast - slow)
        
        signal_line = self._ema(macd_values, signal_period) if len(macd_values) >= signal_period else macd_line
        histogram = macd_line - signal_line
        
        return macd_line, signal_line, histogram
    
    def calculate_rate_of_change(
        self,
        values: List[float],
        period: int = 10
    ) -> float:
        """
        Calculate Rate of Change (ROC).
        
        Args:
            values: Time series values
            period: Lookback period
            
        Returns:
            ROC as percentage
        """
        if len(values) < period + 1:
            return 0.0
        
        current = values[-1]
        past = values[-(period + 1)]
        
        if past == 0:
            return 0.0
        
        return ((current - past) / abs(past)) * 100
    
    def calculate_acceleration(
        self,
        values: List[float],
        period: int = 5
    ) -> float:
        """
        Calculate acceleration (second derivative).
        
        Args:
            values: Time series values
            period: Period for calculating changes
            
        Returns:
            Acceleration value
        """
        if len(values) < period * 2 + 1:
            return 0.0
        
        # First derivative (velocity)
        velocities = []
        for i in range(period, len(values)):
            vel = values[i] - values[i - period]
            velocities.append(vel)
        
        if len(velocities) < 2:
            return 0.0
        
        # Second derivative (acceleration)
        recent_vel = velocities[-1]
        past_vel = velocities[-(min(period, len(velocities)))]
        
        return recent_vel - past_vel
    
    def _ema(self, values: List[float], period: int) -> float:
        """Calculate Exponential Moving Average."""
        if not values:
            return 0.0
        if len(values) < period:
            return sum(values) / len(values)
        
        multiplier = 2 / (period + 1)
        ema = sum(values[:period]) / period  # Start with SMA
        
        for value in values[period:]:
            ema = (value - ema) * multiplier + ema
        
        return ema
    
    def _sma(self, values: List[float], period: int) -> float:
        """Calculate Simple Moving Average."""
        if not values:
            return 0.0
        if len(values) < period:
            return sum(values) / len(values)
        return sum(values[-period:]) / period
    
    def calculate_buzz_momentum(
        self,
        entity_id: str,
        mention_history: Dict[date, int],
        short_period: int = 7,
        long_period: int = 30
    ) -> BuzzMomentum:
        """
        Calculate buzz momentum from mention counts.
        
        Args:
            entity_id: Entity identifier
            mention_history: Dict of date -> mention count
            short_period: Short MA period (days)
            long_period: Long MA period (days)
            
        Returns:
            BuzzMomentum with trend analysis
        """
        if not mention_history:
            return BuzzMomentum(
                entity_id=entity_id,
                current_mentions=0,
                ma_short=0,
                ma_long=0,
                momentum=0,
                acceleration=0,
                trend="stable"
            )
        
        # Sort and extract values
        sorted_dates = sorted(mention_history.keys())
        values = [mention_history[d] for d in sorted_dates]
        
        current = values[-1] if values else 0
        ma_short = self._sma(values, short_period)
        ma_long = self._sma(values, long_period)
        
        momentum = self.calculate_rate_of_change(values, short_period)
        acceleration = self.calculate_acceleration(values, short_period // 2)
        
        # Determine trend
        if acceleration > 0 and momentum > 10:
            trend = "accelerating"
        elif acceleration < 0 and momentum < -10:
            trend = "decelerating"
        elif momentum > 20:
            trend = "strong_uptrend"
        elif momentum < -20:
            trend = "strong_downtrend"
        else:
            trend = "stable"
        
        return BuzzMomentum(
            entity_id=entity_id,
            current_mentions=current,
            ma_short=ma_short,
            ma_long=ma_long,
            momentum=momentum,
            acceleration=acceleration,
            trend=trend
        )
    
    def calculate_funding_momentum(
        self,
        entity_id: str,
        funding_events: List[Dict[str, Any]],
        sector_avg_velocity: float = 1000000.0  # $1M/day default
    ) -> FundingMomentum:
        """
        Calculate funding momentum from funding events.
        
        Args:
            entity_id: Entity identifier
            funding_events: List of {"date": date, "amount_usd": float, "round": str}
            sector_avg_velocity: Average $/day for sector comparison
            
        Returns:
            FundingMomentum analysis
        """
        if not funding_events:
            return FundingMomentum(
                entity_id=entity_id,
                recent_funding_usd=0,
                funding_velocity=0,
                funding_acceleration=0,
                runway_signal="quiet",
                sector_relative=0
            )
        
        # Sort by date
        sorted_events = sorted(funding_events, key=lambda x: x.get("date", date.min))
        
        # Calculate total recent funding (last 180 days)
        cutoff = date.today() - timedelta(days=180)
        recent_events = [e for e in sorted_events if e.get("date", date.min) >= cutoff]
        recent_funding = sum(e.get("amount_usd", 0) for e in recent_events)
        
        # Calculate velocity ($/day over period)
        if recent_events:
            first_date = min(e.get("date", date.today()) for e in recent_events)
            days_span = max(1, (date.today() - first_date).days)
            velocity = recent_funding / days_span
        else:
            velocity = 0.0
        
        # Calculate acceleration (compare to prior 180 days)
        prior_cutoff = cutoff - timedelta(days=180)
        prior_events = [e for e in sorted_events if prior_cutoff <= e.get("date", date.min) < cutoff]
        prior_funding = sum(e.get("amount_usd", 0) for e in prior_events)
        
        if prior_events:
            first_prior = min(e.get("date", date.today()) for e in prior_events)
            prior_days = max(1, (cutoff - first_prior).days)
            prior_velocity = prior_funding / prior_days
        else:
            prior_velocity = 0.0
        
        acceleration = velocity - prior_velocity
        
        # Determine runway signal
        if velocity > sector_avg_velocity * 2:
            runway_signal = "actively_raising"
        elif velocity > sector_avg_velocity:
            runway_signal = "raising"
        elif velocity > 0:
            runway_signal = "deployed"
        else:
            runway_signal = "quiet"
        
        # Sector relative
        sector_relative = velocity / sector_avg_velocity if sector_avg_velocity > 0 else 0
        
        return FundingMomentum(
            entity_id=entity_id,
            recent_funding_usd=recent_funding,
            funding_velocity=velocity,
            funding_acceleration=acceleration,
            runway_signal=runway_signal,
            sector_relative=sector_relative
        )
    
    def generate_sentiment_rsi(
        self,
        entity_id: str,
        sentiment_history: Dict[date, float],
        period: int = 14
    ) -> MomentumSignal:
        """
        Generate RSI signal for sentiment scores.
        
        Args:
            entity_id: Entity identifier
            sentiment_history: Dict of date -> sentiment (0-10 or -1 to 1)
            period: RSI period
            
        Returns:
            MomentumSignal with RSI interpretation
        """
        sorted_dates = sorted(sentiment_history.keys())
        values = [sentiment_history[d] for d in sorted_dates]
        
        rsi = self.calculate_rsi(values, period)
        
        # Interpret RSI
        if rsi > 70:
            interpretation = "overbought"
            strength = (rsi - 70) / 30
        elif rsi < 30:
            interpretation = "oversold"
            strength = (30 - rsi) / 30
        elif rsi > 50:
            interpretation = "bullish_momentum"
            strength = (rsi - 50) / 20
        else:
            interpretation = "bearish_momentum"
            strength = (50 - rsi) / 20
        
        return MomentumSignal(
            entity_id=entity_id,
            signal_type="sentiment_rsi",
            value=rsi,
            interpretation=interpretation,
            strength=min(1.0, strength)
        )
    
    def generate_media_macd(
        self,
        entity_id: str,
        media_score_history: Dict[date, float]
    ) -> MomentumSignal:
        """
        Generate MACD signal for media coverage.
        
        Args:
            entity_id: Entity identifier
            media_score_history: Dict of date -> media score
            
        Returns:
            MomentumSignal with MACD interpretation
        """
        sorted_dates = sorted(media_score_history.keys())
        values = [media_score_history[d] for d in sorted_dates]
        
        macd, signal, histogram = self.calculate_macd(values)
        
        # Interpret MACD
        if histogram > 0 and macd > signal:
            if histogram > abs(macd) * 0.1:
                interpretation = "strong_bullish_crossover"
                strength = min(1.0, histogram / (abs(macd) + 0.01))
            else:
                interpretation = "bullish_crossover"
                strength = 0.5
        elif histogram < 0 and macd < signal:
            if abs(histogram) > abs(macd) * 0.1:
                interpretation = "strong_bearish_crossover"
                strength = min(1.0, abs(histogram) / (abs(macd) + 0.01))
            else:
                interpretation = "bearish_crossover"
                strength = 0.5
        else:
            interpretation = "neutral"
            strength = 0.2
        
        return MomentumSignal(
            entity_id=entity_id,
            signal_type="media_macd",
            value=histogram,
            interpretation=interpretation,
            strength=strength
        )
    
    def calculate_all_momentum(
        self,
        entity_id: str,
        mention_history: Optional[Dict[date, int]] = None,
        sentiment_history: Optional[Dict[date, float]] = None,
        media_score_history: Optional[Dict[date, float]] = None,
        funding_events: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Calculate all momentum indicators for an entity.
        
        Args:
            entity_id: Entity identifier
            mention_history: Historical mention counts
            sentiment_history: Historical sentiment scores
            media_score_history: Historical media scores
            funding_events: Funding event data
            
        Returns:
            Dict with all momentum indicators
        """
        result = {
            "entity_id": entity_id,
            "calculated_at": datetime.now().isoformat(),
            "signals": {}
        }
        
        if mention_history:
            buzz = self.calculate_buzz_momentum(entity_id, mention_history)
            result["signals"]["buzz_momentum"] = buzz.to_dict()
        
        if sentiment_history:
            rsi = self.generate_sentiment_rsi(entity_id, sentiment_history)
            result["signals"]["sentiment_rsi"] = rsi.to_dict()
        
        if media_score_history:
            macd = self.generate_media_macd(entity_id, media_score_history)
            result["signals"]["media_macd"] = macd.to_dict()
        
        if funding_events:
            funding = self.calculate_funding_momentum(entity_id, funding_events)
            result["signals"]["funding_momentum"] = funding.to_dict()
        
        # Composite signal
        signals = result["signals"]
        if signals:
            signal_strengths = []
            bullish_signals = 0
            bearish_signals = 0
            
            for name, sig in signals.items():
                if "strength" in sig:
                    signal_strengths.append(sig["strength"])
                if "interpretation" in sig:
                    interp = sig["interpretation"]
                    if "bullish" in interp or interp in ["accelerating", "strong_uptrend", "raising", "actively_raising"]:
                        bullish_signals += 1
                    elif "bearish" in interp or interp in ["decelerating", "strong_downtrend", "overbought"]:
                        bearish_signals += 1
            
            result["composite"] = {
                "average_strength": sum(signal_strengths) / len(signal_strengths) if signal_strengths else 0,
                "bullish_signals": bullish_signals,
                "bearish_signals": bearish_signals,
                "net_signal": bullish_signals - bearish_signals,
                "total_signals": len(signals)
            }
        
        return result


def rank_entities_by_momentum(
    entities: List[str],
    momentum_results: Dict[str, Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Rank entities by momentum signals.
    
    Args:
        entities: List of entity IDs
        momentum_results: Dict of entity_id -> momentum result
        
    Returns:
        Sorted list of entities with rankings
    """
    rankings = []
    
    for entity_id in entities:
        result = momentum_results.get(entity_id, {})
        composite = result.get("composite", {})
        
        score = 0
        # Net signal contribution
        net = composite.get("net_signal", 0)
        score += net * 10
        
        # Strength contribution
        avg_strength = composite.get("average_strength", 0)
        score += avg_strength * 20
        
        # Buzz momentum bonus
        buzz = result.get("signals", {}).get("buzz_momentum", {})
        if buzz.get("trend") == "accelerating":
            score += 15
        elif buzz.get("trend") == "strong_uptrend":
            score += 10
        
        # Funding momentum bonus
        funding = result.get("signals", {}).get("funding_momentum", {})
        if funding.get("runway_signal") == "actively_raising":
            score += 20
        elif funding.get("runway_signal") == "raising":
            score += 10
        
        rankings.append({
            "entity_id": entity_id,
            "momentum_score": round(score, 2),
            "composite": composite,
            "signals": result.get("signals", {})
        })
    
    # Sort by momentum score descending
    rankings.sort(key=lambda x: x["momentum_score"], reverse=True)
    
    return rankings


if __name__ == "__main__":
    # Test momentum calculator
    print("Testing Momentum Calculator")
    print("=" * 50)
    
    calc = MomentumCalculator()
    
    # Generate synthetic data
    from random import random, gauss
    
    base_date = date.today() - timedelta(days=60)
    
    # Mention history (increasing trend)
    mention_history = {}
    mentions = 50
    for i in range(60):
        dt = base_date + timedelta(days=i)
        mentions = int(mentions * (1 + gauss(0.02, 0.1)))  # Upward drift
        mention_history[dt] = max(1, mentions)
    
    # Sentiment history (oscillating)
    sentiment_history = {}
    sentiment = 5.0
    for i in range(60):
        dt = base_date + timedelta(days=i)
        sentiment = max(1, min(10, sentiment + gauss(0, 0.5)))
        sentiment_history[dt] = sentiment
    
    # Test buzz momentum
    buzz = calc.calculate_buzz_momentum("test-entity", mention_history)
    print(f"\nBuzz Momentum:")
    print(f"  Current mentions: {buzz.current_mentions}")
    print(f"  MA Short: {buzz.ma_short:.1f}")
    print(f"  MA Long: {buzz.ma_long:.1f}")
    print(f"  Momentum: {buzz.momentum:.1f}%")
    print(f"  Trend: {buzz.trend}")
    
    # Test RSI
    rsi = calc.generate_sentiment_rsi("test-entity", sentiment_history)
    print(f"\nSentiment RSI:")
    print(f"  RSI Value: {rsi.value:.1f}")
    print(f"  Interpretation: {rsi.interpretation}")
    print(f"  Strength: {rsi.strength:.2f}")
    
    # Test MACD
    media_history = {k: v * 10 for k, v in sentiment_history.items()}  # Scale to 0-100
    macd = calc.generate_media_macd("test-entity", media_history)
    print(f"\nMedia MACD:")
    print(f"  Histogram: {macd.value:.3f}")
    print(f"  Interpretation: {macd.interpretation}")
    
    # Test all momentum
    print("\n" + "=" * 50)
    print("All Momentum Signals:")
    result = calc.calculate_all_momentum(
        "test-entity",
        mention_history=mention_history,
        sentiment_history=sentiment_history,
        media_score_history=media_history
    )
    
    print(f"  Signals calculated: {len(result['signals'])}")
    if result.get("composite"):
        comp = result["composite"]
        print(f"  Average strength: {comp['average_strength']:.2f}")
        print(f"  Net signal: {comp['net_signal']} ({comp['bullish_signals']} bullish, {comp['bearish_signals']} bearish)")
