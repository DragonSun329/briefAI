"""
Quantitative Signal Aggregator

Combines multiple quant signals into composite scores:
- Weighted signal combination
- Historical accuracy tracking
- Signal strength indicators
- Entity leaderboards ranked by combined signals
"""

from __future__ import annotations

import json
import statistics
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
from loguru import logger

import numpy as np


@dataclass
class CompositeSignal:
    """Combined signal from multiple sources."""
    entity_id: str
    entity_name: str
    composite_score: float  # 0-100
    signal_strength: float  # 0-1, confidence in the signal
    direction: str  # "bullish", "bearish", "neutral"
    components: Dict[str, float] = field(default_factory=dict)
    confidence: float = 0.5
    generated_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "entity_name": self.entity_name,
            "composite_score": round(self.composite_score, 2),
            "signal_strength": round(self.signal_strength, 4),
            "direction": self.direction,
            "components": {k: round(v, 4) for k, v in self.components.items()},
            "confidence": round(self.confidence, 4),
            "generated_at": self.generated_at.isoformat(),
        }


@dataclass
class SignalWeight:
    """Weight configuration for a signal type."""
    signal_name: str
    base_weight: float
    historical_accuracy: float = 0.5  # Track accuracy over time
    recent_performance: float = 0.5   # Recent accuracy
    adjusted_weight: float = 0.0
    
    def calculate_adjusted_weight(self):
        """Adjust weight based on historical accuracy."""
        # Combine base weight with accuracy to get adjusted weight
        accuracy_factor = (self.historical_accuracy * 0.6 + self.recent_performance * 0.4)
        self.adjusted_weight = self.base_weight * (0.5 + accuracy_factor)


@dataclass
class LeaderboardEntry:
    """Entry in the signal leaderboard."""
    rank: int
    entity_id: str
    entity_name: str
    composite_score: float
    signal_strength: float
    direction: str
    top_signals: List[str]
    momentum: str  # "accelerating", "steady", "decelerating"
    change_from_yesterday: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "rank": self.rank,
            "entity_id": self.entity_id,
            "entity_name": self.entity_name,
            "composite_score": round(self.composite_score, 2),
            "signal_strength": round(self.signal_strength, 4),
            "direction": self.direction,
            "top_signals": self.top_signals,
            "momentum": self.momentum,
            "change_from_yesterday": round(self.change_from_yesterday, 2),
        }


class QuantAggregator:
    """
    Aggregates quantitative signals into actionable composite scores.
    
    Features:
    - Weighted combination of correlation, momentum, and sentiment signals
    - Historical accuracy tracking to adjust weights
    - Confidence scoring based on data quality
    - Leaderboard generation for top-signal entities
    """
    
    # Default signal weights
    DEFAULT_WEIGHTS = {
        "correlation": SignalWeight("correlation", base_weight=0.20),
        "lead_lag_predictive": SignalWeight("lead_lag_predictive", base_weight=0.15),
        "buzz_momentum": SignalWeight("buzz_momentum", base_weight=0.15),
        "funding_momentum": SignalWeight("funding_momentum", base_weight=0.15),
        "sentiment_rsi": SignalWeight("sentiment_rsi", base_weight=0.10),
        "sentiment_ma_trend": SignalWeight("sentiment_ma_trend", base_weight=0.10),
        "volume_weighted_sentiment": SignalWeight("volume_weighted_sentiment", base_weight=0.10),
        "divergence": SignalWeight("divergence", base_weight=0.05),
    }
    
    def __init__(
        self,
        weights: Optional[Dict[str, SignalWeight]] = None,
        accuracy_history_path: Optional[Path] = None
    ):
        """
        Initialize aggregator.
        
        Args:
            weights: Custom signal weights
            accuracy_history_path: Path to load/save accuracy history
        """
        self.weights = weights or self.DEFAULT_WEIGHTS.copy()
        self.accuracy_history_path = accuracy_history_path
        self.accuracy_history: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        
        if accuracy_history_path and accuracy_history_path.exists():
            self._load_accuracy_history()
        
        # Calculate adjusted weights
        for weight in self.weights.values():
            weight.calculate_adjusted_weight()
        
        logger.info(f"QuantAggregator initialized with {len(self.weights)} signal types")
    
    def _load_accuracy_history(self):
        """Load historical accuracy data."""
        try:
            with open(self.accuracy_history_path, 'r') as f:
                self.accuracy_history = defaultdict(list, json.load(f))
        except Exception as e:
            logger.warning(f"Could not load accuracy history: {e}")
    
    def _save_accuracy_history(self):
        """Save accuracy history to file."""
        if self.accuracy_history_path:
            try:
                self.accuracy_history_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.accuracy_history_path, 'w') as f:
                    json.dump(dict(self.accuracy_history), f, indent=2)
            except Exception as e:
                logger.error(f"Could not save accuracy history: {e}")
    
    def record_accuracy(
        self,
        signal_name: str,
        prediction: str,
        actual: str,
        magnitude: float = 1.0
    ):
        """
        Record accuracy of a signal prediction.
        
        Args:
            signal_name: Name of the signal
            prediction: Predicted direction ("bullish", "bearish", "neutral")
            actual: Actual outcome
            magnitude: How strong the signal was (0-1)
        """
        correct = (
            (prediction == "bullish" and actual == "bullish") or
            (prediction == "bearish" and actual == "bearish") or
            (prediction == "neutral" and actual == "neutral")
        )
        
        record = {
            "date": date.today().isoformat(),
            "prediction": prediction,
            "actual": actual,
            "correct": correct,
            "magnitude": magnitude
        }
        
        self.accuracy_history[signal_name].append(record)
        
        # Keep only last 100 records per signal
        if len(self.accuracy_history[signal_name]) > 100:
            self.accuracy_history[signal_name] = self.accuracy_history[signal_name][-100:]
        
        # Update signal weight accuracy
        if signal_name in self.weights:
            self._update_signal_accuracy(signal_name)
        
        self._save_accuracy_history()
    
    def _update_signal_accuracy(self, signal_name: str):
        """Update accuracy metrics for a signal."""
        history = self.accuracy_history.get(signal_name, [])
        
        if not history:
            return
        
        # Overall accuracy
        total_correct = sum(1 for h in history if h.get("correct", False))
        self.weights[signal_name].historical_accuracy = total_correct / len(history)
        
        # Recent accuracy (last 20)
        recent = history[-20:]
        recent_correct = sum(1 for h in recent if h.get("correct", False))
        self.weights[signal_name].recent_performance = recent_correct / len(recent) if recent else 0.5
        
        # Recalculate adjusted weight
        self.weights[signal_name].calculate_adjusted_weight()
    
    def aggregate_signals(
        self,
        entity_id: str,
        entity_name: str,
        signal_data: Dict[str, Any]
    ) -> CompositeSignal:
        """
        Aggregate multiple signals into a composite score.
        
        Args:
            entity_id: Entity identifier
            entity_name: Display name
            signal_data: Dict with signal outputs from various modules
            
        Returns:
            CompositeSignal with combined score
        """
        components = {}
        total_weight = 0
        weighted_sum = 0
        bullish_signals = 0
        bearish_signals = 0
        confidence_sum = 0
        signal_count = 0
        
        # Process correlation signal
        if "correlation" in signal_data:
            corr = signal_data["correlation"]
            corr_value = corr.get("correlation", 0)
            significance = corr.get("significance", "low")
            
            # Normalize to 0-100
            score = (corr_value + 1) * 50  # -1 to 1 -> 0 to 100
            
            if significance != "low":
                weight = self.weights["correlation"].adjusted_weight
                components["correlation"] = score
                weighted_sum += score * weight
                total_weight += weight
                confidence_sum += 0.7 if significance == "high" else 0.5
                signal_count += 1
                
                if corr_value > 0.2:
                    bullish_signals += 1
                elif corr_value < -0.2:
                    bearish_signals += 1
        
        # Process lead/lag predictive signal
        if "lead_lag" in signal_data:
            lag = signal_data["lead_lag"]
            predictive_power = lag.get("predictive_power", 0)
            news_leads = lag.get("news_leads_stock", False)
            
            if predictive_power > 0.1:
                # If news leads stock with good correlation, it's tradeable
                score = predictive_power * 100
                weight = self.weights["lead_lag_predictive"].adjusted_weight
                components["lead_lag_predictive"] = score
                weighted_sum += score * weight
                total_weight += weight
                confidence_sum += min(0.8, predictive_power + 0.3)
                signal_count += 1
        
        # Process buzz momentum
        if "buzz_momentum" in signal_data:
            buzz = signal_data["buzz_momentum"]
            momentum = buzz.get("momentum", 0)
            trend = buzz.get("trend", "stable")
            
            # Normalize momentum to 0-100
            score = min(100, max(0, 50 + momentum))
            
            weight = self.weights["buzz_momentum"].adjusted_weight
            components["buzz_momentum"] = score
            weighted_sum += score * weight
            total_weight += weight
            
            confidence_sum += 0.6
            signal_count += 1
            
            if trend in ["accelerating", "strong_uptrend"]:
                bullish_signals += 1
            elif trend in ["decelerating", "strong_downtrend"]:
                bearish_signals += 1
        
        # Process funding momentum
        if "funding_momentum" in signal_data:
            funding = signal_data["funding_momentum"]
            sector_relative = funding.get("sector_relative", 0)
            runway_signal = funding.get("runway_signal", "quiet")
            
            # Score based on sector-relative velocity
            score = min(100, max(0, 50 + sector_relative * 25))
            
            weight = self.weights["funding_momentum"].adjusted_weight
            components["funding_momentum"] = score
            weighted_sum += score * weight
            total_weight += weight
            
            confidence_sum += 0.7 if runway_signal != "quiet" else 0.4
            signal_count += 1
            
            if runway_signal in ["raising", "actively_raising"]:
                bullish_signals += 1
        
        # Process sentiment RSI
        if "sentiment_rsi" in signal_data:
            rsi = signal_data["sentiment_rsi"]
            rsi_value = rsi.get("value", 50)
            interpretation = rsi.get("interpretation", "neutral")
            
            # RSI already 0-100
            score = rsi_value
            
            weight = self.weights["sentiment_rsi"].adjusted_weight
            components["sentiment_rsi"] = score
            weighted_sum += score * weight
            total_weight += weight
            
            confidence_sum += rsi.get("strength", 0.5)
            signal_count += 1
            
            # Contrarian: overbought is bearish, oversold is bullish
            if interpretation == "overbought":
                bearish_signals += 1
            elif interpretation == "oversold":
                bullish_signals += 1
        
        # Process sentiment MA trend
        if "moving_averages" in signal_data:
            ma = signal_data["moving_averages"]
            trend = ma.get("trend", "consolidating")
            golden_cross = ma.get("golden_cross", False)
            death_cross = ma.get("death_cross", False)
            
            # Score based on trend
            trend_scores = {
                "strong_bullish": 90,
                "bullish": 70,
                "consolidating": 50,
                "bearish": 30,
                "strong_bearish": 10
            }
            score = trend_scores.get(trend, 50)
            
            weight = self.weights["sentiment_ma_trend"].adjusted_weight
            components["sentiment_ma_trend"] = score
            weighted_sum += score * weight
            total_weight += weight
            
            confidence_sum += 0.7 if golden_cross or death_cross else 0.5
            signal_count += 1
            
            if golden_cross or trend.startswith("bullish") or trend == "strong_bullish":
                bullish_signals += 1
            if death_cross or trend.startswith("bearish") or trend == "strong_bearish":
                bearish_signals += 1
        
        # Process volume-weighted sentiment
        if "volume_weighted" in signal_data:
            vw = signal_data["volume_weighted"]
            vw_sentiment = vw.get("volume_weighted_sentiment", 5)
            gap = vw.get("volume_sentiment_gap", 0)
            
            # Normalize 0-10 to 0-100
            score = vw_sentiment * 10
            
            weight = self.weights["volume_weighted_sentiment"].adjusted_weight
            components["volume_weighted_sentiment"] = score
            weighted_sum += score * weight
            total_weight += weight
            
            confidence_sum += 0.65
            signal_count += 1
            
            # High-volume sources more bullish than low-volume
            if gap > 0.5:
                bullish_signals += 1
            elif gap < -0.5:
                bearish_signals += 1
        
        # Process divergence
        if "divergence" in signal_data:
            div = signal_data["divergence"]
            div_type = div.get("divergence_type", "neutral")
            magnitude = div.get("magnitude", 0)
            
            # Score based on divergence type
            if div_type == "bullish_divergence":
                score = 70 + magnitude * 30
                bullish_signals += 1
            elif div_type == "bearish_divergence":
                score = 30 - magnitude * 30
                bearish_signals += 1
            else:
                score = 50
            
            weight = self.weights["divergence"].adjusted_weight
            components["divergence"] = score
            weighted_sum += score * weight
            total_weight += weight
            
            confidence_sum += magnitude
            signal_count += 1
        
        # Calculate composite score
        if total_weight > 0:
            composite_score = weighted_sum / total_weight
        else:
            composite_score = 50  # Neutral if no signals
        
        # Calculate signal strength (confidence)
        signal_strength = confidence_sum / signal_count if signal_count > 0 else 0.3
        
        # Determine direction
        if bullish_signals > bearish_signals + 1:
            direction = "bullish"
        elif bearish_signals > bullish_signals + 1:
            direction = "bearish"
        else:
            direction = "neutral"
        
        return CompositeSignal(
            entity_id=entity_id,
            entity_name=entity_name,
            composite_score=composite_score,
            signal_strength=signal_strength,
            direction=direction,
            components=components,
            confidence=signal_strength
        )
    
    def generate_leaderboard(
        self,
        composite_signals: List[CompositeSignal],
        previous_scores: Optional[Dict[str, float]] = None,
        top_n: int = 20
    ) -> List[LeaderboardEntry]:
        """
        Generate ranked leaderboard of entities by signal strength.
        
        Args:
            composite_signals: List of composite signals
            previous_scores: Yesterday's scores for change calculation
            top_n: Number of entries to return
            
        Returns:
            Sorted list of LeaderboardEntry objects
        """
        if not composite_signals:
            return []
        
        # Sort by composite score * signal strength (quality-adjusted rank)
        sorted_signals = sorted(
            composite_signals,
            key=lambda s: s.composite_score * s.signal_strength,
            reverse=True
        )
        
        leaderboard = []
        
        for rank, signal in enumerate(sorted_signals[:top_n], 1):
            # Calculate change from yesterday
            change = 0.0
            if previous_scores and signal.entity_id in previous_scores:
                change = signal.composite_score - previous_scores[signal.entity_id]
            
            # Determine momentum based on components
            momentum = self._determine_momentum(signal)
            
            # Get top contributing signals
            top_signals = sorted(
                signal.components.keys(),
                key=lambda k: signal.components[k],
                reverse=True
            )[:3]
            
            entry = LeaderboardEntry(
                rank=rank,
                entity_id=signal.entity_id,
                entity_name=signal.entity_name,
                composite_score=signal.composite_score,
                signal_strength=signal.signal_strength,
                direction=signal.direction,
                top_signals=top_signals,
                momentum=momentum,
                change_from_yesterday=change
            )
            leaderboard.append(entry)
        
        return leaderboard
    
    def _determine_momentum(self, signal: CompositeSignal) -> str:
        """Determine momentum state from signal components."""
        buzz = signal.components.get("buzz_momentum", 50)
        funding = signal.components.get("funding_momentum", 50)
        ma_trend = signal.components.get("sentiment_ma_trend", 50)
        
        # Average of momentum-related components
        avg = (buzz + funding + ma_trend) / 3
        
        if avg > 65:
            return "accelerating"
        elif avg < 35:
            return "decelerating"
        else:
            return "steady"
    
    def get_signal_weights_summary(self) -> Dict[str, Dict[str, float]]:
        """Get summary of current signal weights."""
        return {
            name: {
                "base_weight": w.base_weight,
                "historical_accuracy": w.historical_accuracy,
                "recent_performance": w.recent_performance,
                "adjusted_weight": w.adjusted_weight
            }
            for name, w in self.weights.items()
        }
    
    def generate_report(
        self,
        leaderboard: List[LeaderboardEntry],
        market_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Generate comprehensive quant analysis report.
        
        Args:
            leaderboard: Generated leaderboard
            market_context: Optional market regime data
            
        Returns:
            Full report as dict
        """
        if not leaderboard:
            return {"error": "No leaderboard data"}
        
        # Calculate statistics
        scores = [e.composite_score for e in leaderboard]
        bullish = sum(1 for e in leaderboard if e.direction == "bullish")
        bearish = sum(1 for e in leaderboard if e.direction == "bearish")
        
        report = {
            "generated_at": datetime.now().isoformat(),
            "summary": {
                "total_entities": len(leaderboard),
                "bullish_count": bullish,
                "bearish_count": bearish,
                "neutral_count": len(leaderboard) - bullish - bearish,
                "bullish_ratio": bullish / len(leaderboard) if leaderboard else 0,
                "average_score": statistics.mean(scores) if scores else 0,
                "score_std": statistics.stdev(scores) if len(scores) > 1 else 0,
            },
            "top_bullish": [
                e.to_dict() for e in leaderboard 
                if e.direction == "bullish"
            ][:5],
            "top_bearish": [
                e.to_dict() for e in leaderboard 
                if e.direction == "bearish"
            ][:5],
            "accelerating": [
                e.to_dict() for e in leaderboard
                if e.momentum == "accelerating"
            ][:5],
            "biggest_movers": sorted(
                [e.to_dict() for e in leaderboard],
                key=lambda x: abs(x["change_from_yesterday"]),
                reverse=True
            )[:5],
            "signal_weights": self.get_signal_weights_summary(),
        }
        
        if market_context:
            report["market_context"] = market_context
        
        return report


def run_quant_aggregation(
    entity_signals: Dict[str, Dict[str, Any]],
    entity_names: Optional[Dict[str, str]] = None,
    previous_scores: Optional[Dict[str, float]] = None
) -> Dict[str, Any]:
    """
    Convenience function to run full quant aggregation.
    
    Args:
        entity_signals: Dict of entity_id -> signal_data
        entity_names: Optional mapping of entity_id -> name
        previous_scores: Yesterday's composite scores
        
    Returns:
        Full analysis result with leaderboard and report
    """
    aggregator = QuantAggregator()
    
    composite_signals = []
    
    for entity_id, signals in entity_signals.items():
        name = entity_names.get(entity_id, entity_id) if entity_names else entity_id
        composite = aggregator.aggregate_signals(entity_id, name, signals)
        composite_signals.append(composite)
    
    leaderboard = aggregator.generate_leaderboard(
        composite_signals,
        previous_scores=previous_scores
    )
    
    report = aggregator.generate_report(leaderboard)
    
    return {
        "composite_signals": [s.to_dict() for s in composite_signals],
        "leaderboard": [e.to_dict() for e in leaderboard],
        "report": report
    }


if __name__ == "__main__":
    # Test quant aggregator
    print("Testing Quant Aggregator")
    print("=" * 50)
    
    # Mock signal data for multiple entities
    entity_signals = {
        "nvidia": {
            "correlation": {"correlation": 0.65, "significance": "high"},
            "lead_lag": {"predictive_power": 0.25, "news_leads_stock": True},
            "buzz_momentum": {"momentum": 25, "trend": "accelerating"},
            "funding_momentum": {"sector_relative": 1.5, "runway_signal": "deployed"},
            "sentiment_rsi": {"value": 72, "interpretation": "overbought", "strength": 0.6},
            "moving_averages": {"trend": "strong_bullish", "golden_cross": False, "death_cross": False},
            "volume_weighted": {"volume_weighted_sentiment": 7.8, "volume_sentiment_gap": 0.5},
        },
        "openai": {
            "correlation": {"correlation": 0.3, "significance": "medium"},
            "buzz_momentum": {"momentum": 40, "trend": "strong_uptrend"},
            "funding_momentum": {"sector_relative": 3.0, "runway_signal": "actively_raising"},
            "sentiment_rsi": {"value": 65, "interpretation": "bullish_momentum", "strength": 0.5},
            "moving_averages": {"trend": "bullish", "golden_cross": True, "death_cross": False},
        },
        "anthropic": {
            "buzz_momentum": {"momentum": 15, "trend": "accelerating"},
            "funding_momentum": {"sector_relative": 2.0, "runway_signal": "raising"},
            "sentiment_rsi": {"value": 55, "interpretation": "bullish_momentum", "strength": 0.4},
            "moving_averages": {"trend": "consolidating", "golden_cross": False, "death_cross": False},
        },
        "meta": {
            "correlation": {"correlation": -0.2, "significance": "medium"},
            "buzz_momentum": {"momentum": -10, "trend": "decelerating"},
            "sentiment_rsi": {"value": 35, "interpretation": "bearish_momentum", "strength": 0.5},
            "moving_averages": {"trend": "bearish", "golden_cross": False, "death_cross": True},
            "divergence": {"divergence_type": "bearish_divergence", "magnitude": 0.6},
        },
    }
    
    entity_names = {
        "nvidia": "NVIDIA",
        "openai": "OpenAI",
        "anthropic": "Anthropic",
        "meta": "Meta Platforms",
    }
    
    result = run_quant_aggregation(entity_signals, entity_names)
    
    print("\nLeaderboard:")
    for entry in result["leaderboard"]:
        print(f"  #{entry['rank']} {entry['entity_name']}: "
              f"Score {entry['composite_score']:.1f}, "
              f"Direction: {entry['direction']}, "
              f"Momentum: {entry['momentum']}")
    
    print("\nReport Summary:")
    summary = result["report"]["summary"]
    print(f"  Bullish: {summary['bullish_count']}")
    print(f"  Bearish: {summary['bearish_count']}")
    print(f"  Neutral: {summary['neutral_count']}")
    print(f"  Average Score: {summary['average_score']:.1f}")
