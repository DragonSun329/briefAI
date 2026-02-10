"""
Signal Calibrator Module

Addresses calibration issues found in validation:
1. Freshness decay - older signals weighted less
2. Source quality weighting - higher quality sources matter more
3. Volume normalization - high-volume entities normalized
4. Category-specific adjustments
5. Direction confidence boosting
6. Macro-economic context adjustments (NEW)

Root Causes Identified:
- NVDA/GOOGL divergence: Neutral sentiment (4-5) when price moved
- Reason: Mock signals were being used, not actual database signals
- Solution: Connect to real signal sources + calibration adjustments

Macro Integration:
- Market regime (bull/bear/sideways/crisis) affects signal confidence
- VIX levels modify reliability
- Sector rotation context adjusts bullish/bearish bias
- Geopolitical risk factors for China-exposed entities
"""

import json
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import numpy as np

from loguru import logger

# Import macro context (optional)
try:
    from integrations.economic_context import EconomicContextProvider
except ImportError:
    EconomicContextProvider = None
    logger.warning("Economic context not available for calibration")

try:
    from utils.regime_classifier import RegimeClassifier, get_current_regime
except ImportError:
    RegimeClassifier = None
    get_current_regime = None
    logger.warning("Regime classifier not available")


# Config paths
CONFIG_DIR = Path(__file__).parent.parent / "config"
ENTITY_PROFILES_PATH = CONFIG_DIR / "entity_profiles.json"
SOURCE_CREDIBILITY_PATH = CONFIG_DIR / "source_credibility.json"


class SignalQuality(Enum):
    """Signal source quality tiers."""
    PREMIUM = 4      # Professional financial data (Bloomberg, Reuters)
    HIGH = 3         # Established sources (SEC, major news)
    MEDIUM = 2       # Community sources (Reddit, HN, GitHub)
    LOW = 1          # Unverified sources


@dataclass
class EntityProfile:
    """Entity-specific calibration profile."""
    entity_id: str
    profile_name: str
    sentiment_multiplier: float = 1.0
    direction_threshold_bullish: float = 6.0
    direction_threshold_bearish: float = 4.0
    decay_half_life_hours: float = 24.0
    confidence_boost: float = 0.0
    
    @classmethod
    def from_config(cls, entity_id: str, profile_data: dict) -> 'EntityProfile':
        return cls(
            entity_id=entity_id,
            profile_name=profile_data.get("name", "custom"),
            sentiment_multiplier=profile_data.get("sentiment_multiplier", 1.0),
            direction_threshold_bullish=profile_data.get("direction_threshold_bullish", 6.0),
            direction_threshold_bearish=profile_data.get("direction_threshold_bearish", 4.0),
            decay_half_life_hours=profile_data.get("decay_half_life_hours", 24.0),
            confidence_boost=profile_data.get("confidence_boost", 0.0),
        )


class EntityProfileLoader:
    """Loads and caches entity-specific calibration profiles."""
    
    _instance = None
    _profiles: Dict[str, EntityProfile] = {}
    _config: Dict = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_profiles()
        return cls._instance
    
    def _load_profiles(self):
        """Load profiles from config file."""
        if ENTITY_PROFILES_PATH.exists():
            try:
                with open(ENTITY_PROFILES_PATH) as f:
                    self._config = json.load(f)
                
                # Build entity -> profile mapping
                for profile_name, profile_data in self._config.get("volatility_profiles", {}).items():
                    for entity in profile_data.get("entities", []):
                        self._profiles[entity.lower()] = EntityProfile(
                            entity_id=entity,
                            profile_name=profile_name,
                            sentiment_multiplier=profile_data.get("sentiment_multiplier", 1.0),
                            direction_threshold_bullish=profile_data.get("direction_threshold_bullish", 6.0),
                            direction_threshold_bearish=profile_data.get("direction_threshold_bearish", 4.0),
                            decay_half_life_hours=profile_data.get("decay_half_life_hours", 24.0),
                            confidence_boost=profile_data.get("confidence_boost", 0.0),
                        )
                
                logger.info(f"Loaded {len(self._profiles)} entity profiles")
            except Exception as e:
                logger.warning(f"Failed to load entity profiles: {e}")
    
    def get_profile(self, entity_id: str) -> EntityProfile:
        """Get profile for an entity, falling back to default."""
        entity_lower = entity_id.lower()
        
        if entity_lower in self._profiles:
            return self._profiles[entity_lower]
        
        # Return default profile
        default = self._config.get("default_profile", {})
        return EntityProfile(
            entity_id=entity_id,
            profile_name="default",
            sentiment_multiplier=default.get("sentiment_multiplier", 1.0),
            direction_threshold_bullish=default.get("direction_threshold_bullish", 6.0),
            direction_threshold_bearish=default.get("direction_threshold_bearish", 4.0),
            decay_half_life_hours=default.get("decay_half_life_hours", 24.0),
            confidence_boost=default.get("confidence_boost", 0.0),
        )
    
    def get_signal_decay(self, signal_type: str) -> float:
        """Get decay half-life for a signal type."""
        decay_rates = self._config.get("sector_decay_rates", {})
        
        if signal_type in decay_rates:
            return decay_rates[signal_type].get("half_life_hours", 24)
        
        # Check for partial match
        signal_lower = signal_type.lower()
        for key, data in decay_rates.items():
            if key in signal_lower or signal_lower in key:
                return data.get("half_life_hours", 24)
        
        return 24  # Default


@dataclass
class CalibratedSignal:
    """A signal after calibration adjustments."""
    entity_id: str
    raw_sentiment: float
    calibrated_sentiment: float
    raw_confidence: float
    calibrated_confidence: float
    freshness_factor: float
    source_quality_factor: float
    volume_adjustment: float
    direction_boost: float
    calibration_notes: List[str] = field(default_factory=list)
    
    @property
    def total_adjustment(self) -> float:
        return self.calibrated_sentiment - self.raw_sentiment


class SignalCalibrator:
    """
    Calibrates sentiment signals for improved validation accuracy.
    
    Key calibration factors:
    1. Freshness decay: Exponential decay based on signal age AND signal type
    2. Source quality: Premium sources weighted higher + accuracy-based weights
    3. Volume normalization: Adjusts for high-frequency entities
    4. Direction confidence: Boosts signals with clear directional agreement
    5. Entity-specific: Per-entity volatility profiles adjust thresholds
    
    NEW in v2:
    - Signal-type specific decay (news=12h, github=7d, funding=30d)
    - Entity volatility profiles (NVDA=high-beta, MSFT=stable)
    - Accuracy-based source weighting from audit results
    """
    
    # Default source quality mappings
    SOURCE_QUALITY = {
        # Premium sources
        "bloomberg": SignalQuality.PREMIUM,
        "reuters": SignalQuality.PREMIUM,
        "sec_edgar": SignalQuality.PREMIUM,
        "fincept": SignalQuality.PREMIUM,
        "yfinance": SignalQuality.PREMIUM,
        
        # High quality sources
        "arxiv": SignalQuality.HIGH,
        "news_search": SignalQuality.HIGH,
        "financial_signals": SignalQuality.HIGH,
        "crunchbase": SignalQuality.HIGH,
        "openbook_vc": SignalQuality.HIGH,
        
        # Medium quality sources  
        "github": SignalQuality.MEDIUM,
        "reddit": SignalQuality.MEDIUM,
        "hackernews": SignalQuality.MEDIUM,
        "polymarket": SignalQuality.MEDIUM,
        "manifold": SignalQuality.MEDIUM,
        "social_sentiment": SignalQuality.MEDIUM,
        
        # Low quality sources
        "producthunt": SignalQuality.LOW,
        "google_trends": SignalQuality.LOW,
        "paperswithcode": SignalQuality.LOW,
    }
    
    # Signal type to decay category mapping
    SIGNAL_TYPE_DECAY = {
        "news": "news",
        "news_search": "news",
        "social_sentiment": "social_sentiment",
        "twitter": "social_sentiment",
        "reddit": "social_sentiment",
        "github": "github",
        "github_trending": "github",
        "huggingface": "github",
        "funding": "funding",
        "crunchbase": "funding",
        "openbook_vc": "funding",
        "earnings": "earnings",
        "sec_edgar": "earnings",
        "product_launch": "product_launch",
        "producthunt": "product_launch",
        "regulatory": "regulatory",
    }
    
    # Freshness decay parameters (default, overridden by entity/signal profiles)
    FRESHNESS_HALF_LIFE_HOURS = 24  # Signal loses half weight every 24h
    FRESHNESS_MAX_AGE_HOURS = 168   # 7 days max
    
    # Volume normalization parameters
    VOLUME_BASELINE = 100           # Expected signals per week for a typical entity
    VOLUME_DAMPENING = 0.5          # Sqrt dampening for high-volume entities
    
    # Direction boost parameters
    DIRECTION_AGREEMENT_THRESHOLD = 0.6  # % of signals agreeing for boost
    DIRECTION_BOOST_FACTOR = 0.15        # Max sentiment adjustment
    
    def __init__(
        self,
        custom_source_quality: Optional[Dict[str, SignalQuality]] = None,
        freshness_half_life: float = 24,
        enable_direction_boost: bool = True,
        use_entity_profiles: bool = True,
        use_signal_decay_profiles: bool = True,
    ):
        """
        Initialize calibrator.
        
        Args:
            custom_source_quality: Override source quality mappings
            freshness_half_life: Default hours until signal weight halves
            enable_direction_boost: Whether to apply direction boost
            use_entity_profiles: Use per-entity volatility profiles
            use_signal_decay_profiles: Use signal-type specific decay rates
        """
        self.source_quality = {**self.SOURCE_QUALITY}
        if custom_source_quality:
            self.source_quality.update(custom_source_quality)
        
        self.freshness_half_life = freshness_half_life
        self.enable_direction_boost = enable_direction_boost
        self.use_entity_profiles = use_entity_profiles
        self.use_signal_decay_profiles = use_signal_decay_profiles
        
        # Load entity profiles
        self.profile_loader = EntityProfileLoader() if use_entity_profiles else None
        
        # Load accuracy-based weights if available
        self._accuracy_weights = self._load_accuracy_weights()
        
        logger.info(f"SignalCalibrator initialized (half_life={freshness_half_life}h, entity_profiles={use_entity_profiles})")
    
    def _load_accuracy_weights(self) -> Dict[str, float]:
        """Load accuracy-based source weights from credibility config."""
        weights = {}
        if SOURCE_CREDIBILITY_PATH.exists():
            try:
                with open(SOURCE_CREDIBILITY_PATH) as f:
                    config = json.load(f)
                
                for source_id, data in config.get("accuracy_weights", {}).items():
                    # Skip meta keys
                    if source_id.startswith("_"):
                        continue
                    # Handle both dict and float formats
                    if isinstance(data, dict):
                        weights[source_id] = data.get("weight", 0.5)
                    elif isinstance(data, (int, float)):
                        weights[source_id] = float(data)
            except Exception as e:
                logger.warning(f"Failed to load accuracy weights: {e}")
        return weights
    
    def get_decay_half_life(
        self,
        entity_id: Optional[str] = None,
        signal_type: Optional[str] = None
    ) -> float:
        """
        Get appropriate decay half-life based on entity and signal type.
        
        Priority:
        1. Signal-type specific decay (if enabled and known)
        2. Entity-specific decay (if enabled and has profile)
        3. Default half-life
        """
        # Signal type specific decay
        if self.use_signal_decay_profiles and signal_type and self.profile_loader:
            decay_category = self.SIGNAL_TYPE_DECAY.get(signal_type, signal_type)
            type_decay = self.profile_loader.get_signal_decay(decay_category)
            if type_decay != 24:  # Non-default value
                return type_decay
        
        # Entity-specific decay
        if self.use_entity_profiles and entity_id and self.profile_loader:
            profile = self.profile_loader.get_profile(entity_id)
            if profile.profile_name != "default":
                return profile.decay_half_life_hours
        
        return self.freshness_half_life
    
    def calculate_freshness_factor(
        self,
        signal_time: datetime,
        current_time: Optional[datetime] = None,
        entity_id: Optional[str] = None,
        signal_type: Optional[str] = None
    ) -> float:
        """
        Calculate freshness decay factor with signal/entity-specific decay.
        
        Uses exponential decay: factor = 0.5 ^ (age_hours / half_life)
        
        Decay rates vary by signal type:
        - News: 12h half-life (fast decay)
        - GitHub: 168h / 7d half-life (slow decay)
        - Funding: 720h / 30d half-life (very slow)
        
        Args:
            signal_time: When the signal was observed
            current_time: Current time (defaults to now)
            entity_id: Entity for entity-specific decay
            signal_type: Signal type for type-specific decay
            
        Returns:
            Freshness factor between 0 and 1
        """
        if current_time is None:
            current_time = datetime.now()
        
        # Handle timezone-naive comparison
        if signal_time.tzinfo is not None:
            signal_time = signal_time.replace(tzinfo=None)
        if current_time.tzinfo is not None:
            current_time = current_time.replace(tzinfo=None)
        
        age_hours = (current_time - signal_time).total_seconds() / 3600
        
        # Get appropriate half-life
        half_life = self.get_decay_half_life(entity_id, signal_type)
        
        # Adjust max age based on half-life (signals live for ~7 half-lives)
        max_age = max(self.FRESHNESS_MAX_AGE_HOURS, half_life * 7)
        
        # Cap at max age
        if age_hours > max_age:
            return 0.0
        
        # Exponential decay
        factor = math.pow(0.5, age_hours / half_life)
        
        return round(factor, 4)
    
    def get_source_quality_weight(self, source_id: str) -> float:
        """
        Get quality weight for a signal source.
        
        Uses accuracy-based weights if available, falls back to tier-based.
        
        Returns:
            Weight between 0.25 (low) and 1.0 (premium)
        """
        source_lower = source_id.lower()
        
        # First check accuracy-based weights (from audit)
        if source_lower in self._accuracy_weights:
            return self._accuracy_weights[source_lower]
        
        # Check partial match in accuracy weights
        for key, weight in self._accuracy_weights.items():
            if key in source_lower or source_lower in key:
                return weight
        
        # Fall back to tier-based quality
        quality = self.source_quality.get(source_id)
        
        # Try partial match
        if quality is None:
            for key, q in self.source_quality.items():
                if key in source_lower or source_lower in key:
                    quality = q
                    break
        
        # Default to medium
        if quality is None:
            quality = SignalQuality.MEDIUM
        
        return quality.value / SignalQuality.PREMIUM.value
    
    def calculate_volume_adjustment(
        self,
        signal_count: int,
        time_window_hours: float = 168  # 1 week
    ) -> float:
        """
        Calculate volume normalization adjustment.
        
        High-volume entities (many signals) get dampened to avoid
        over-representation.
        
        Args:
            signal_count: Number of signals in time window
            time_window_hours: Time window for counting
            
        Returns:
            Volume adjustment factor (typically 0.5 - 1.5)
        """
        # Calculate signals per week equivalent
        signals_per_week = signal_count * (168 / time_window_hours)
        
        # Volume ratio vs baseline
        ratio = signals_per_week / self.VOLUME_BASELINE
        
        # Apply sqrt dampening for high volume
        if ratio > 1:
            adjustment = 1.0 / math.pow(ratio, self.VOLUME_DAMPENING)
        else:
            # Boost low-volume (less frequently covered) entities
            adjustment = 1.0 + (1 - ratio) * 0.2
        
        return round(min(1.5, max(0.5, adjustment)), 3)
    
    def calculate_direction_boost(
        self,
        signals: List[Dict[str, Any]]
    ) -> Tuple[float, str]:
        """
        Calculate direction boost when signals agree.
        
        When many signals agree on direction, boost confidence.
        
        Args:
            signals: List of signal dicts with 'sentiment' key
            
        Returns:
            Tuple of (boost_factor, direction)
        """
        if not self.enable_direction_boost or len(signals) < 3:
            return 0.0, "neutral"
        
        # Count directions
        bullish = sum(1 for s in signals if s.get('sentiment', 5) > 6)
        bearish = sum(1 for s in signals if s.get('sentiment', 5) < 4)
        total = len(signals)
        
        bullish_pct = bullish / total
        bearish_pct = bearish / total
        
        if bullish_pct >= self.DIRECTION_AGREEMENT_THRESHOLD:
            # Strong bullish agreement
            boost = self.DIRECTION_BOOST_FACTOR * (bullish_pct - 0.5) * 2
            return round(boost, 3), "bullish"
        elif bearish_pct >= self.DIRECTION_AGREEMENT_THRESHOLD:
            # Strong bearish agreement
            boost = -self.DIRECTION_BOOST_FACTOR * (bearish_pct - 0.5) * 2
            return round(boost, 3), "bearish"
        
        return 0.0, "neutral"
    
    def calibrate_signal(
        self,
        entity_id: str,
        raw_sentiment: float,
        raw_confidence: float,
        signal_time: datetime,
        source_id: str,
        signal_count: int = 1,
        related_signals: Optional[List[Dict]] = None,
        signal_type: Optional[str] = None,
    ) -> CalibratedSignal:
        """
        Apply full calibration to a single signal.
        
        Now includes entity-specific adjustments:
        - Volatility multiplier for high-beta entities
        - Confidence boost/penalty per entity type
        - Signal-type specific decay rates
        
        Args:
            entity_id: Entity identifier
            raw_sentiment: Original sentiment score (0-10)
            raw_confidence: Original confidence (0-1)
            signal_time: When signal was observed
            source_id: Source identifier
            signal_count: Number of signals for entity
            related_signals: Other signals for direction boost
            signal_type: Type of signal (news, github, funding, etc.)
            
        Returns:
            CalibratedSignal with adjustments
        """
        notes = []
        
        # Get entity profile for custom calibration
        entity_profile = None
        if self.use_entity_profiles and self.profile_loader:
            entity_profile = self.profile_loader.get_profile(entity_id)
            if entity_profile.profile_name != "default":
                notes.append(f"Profile: {entity_profile.profile_name}")
        
        # 1. Freshness decay (now signal-type aware)
        freshness = self.calculate_freshness_factor(
            signal_time, 
            entity_id=entity_id,
            signal_type=signal_type or source_id
        )
        if freshness < 0.5:
            notes.append(f"Stale signal (freshness={freshness:.2f})")
        
        # 2. Source quality (now accuracy-aware)
        quality = self.get_source_quality_weight(source_id)
        if quality < 0.5:
            notes.append(f"Low-quality source ({source_id})")
        
        # 3. Volume normalization
        volume_adj = self.calculate_volume_adjustment(signal_count)
        if volume_adj < 0.8:
            notes.append(f"High-volume dampening (adj={volume_adj:.2f})")
        
        # 4. Direction boost
        direction_boost = 0.0
        direction = "neutral"
        if related_signals:
            direction_boost, direction = self.calculate_direction_boost(related_signals)
            if direction_boost != 0:
                notes.append(f"Direction boost ({direction}: {direction_boost:+.2f})")
        
        # 5. Entity-specific sentiment multiplier
        sentiment_multiplier = 1.0
        confidence_boost = 0.0
        if entity_profile:
            sentiment_multiplier = entity_profile.sentiment_multiplier
            confidence_boost = entity_profile.confidence_boost
            if sentiment_multiplier != 1.0:
                notes.append(f"Volatility adj: {sentiment_multiplier:.1f}x")
        
        # Apply calibrations
        # Sentiment adjustment: move toward neutral if stale/low-quality
        # Then apply entity-specific volatility multiplier
        sentiment_deviation = (raw_sentiment - 5.0) * freshness * quality
        # Apply volatility multiplier to amplify/dampen the deviation
        adjusted_deviation = sentiment_deviation * sentiment_multiplier
        calibrated_sentiment = 5.0 + adjusted_deviation + direction_boost
        calibrated_sentiment = max(1.0, min(10.0, calibrated_sentiment))
        
        # Confidence adjustment (with entity-specific boost)
        calibrated_confidence = raw_confidence * freshness * quality * volume_adj
        calibrated_confidence = calibrated_confidence + confidence_boost
        calibrated_confidence = max(0.1, min(1.0, calibrated_confidence))
        
        return CalibratedSignal(
            entity_id=entity_id,
            raw_sentiment=raw_sentiment,
            calibrated_sentiment=round(calibrated_sentiment, 2),
            raw_confidence=raw_confidence,
            calibrated_confidence=round(calibrated_confidence, 3),
            freshness_factor=freshness,
            source_quality_factor=quality,
            volume_adjustment=volume_adj,
            direction_boost=direction_boost,
            calibration_notes=notes,
        )
    
    def calibrate_aggregated_signal(
        self,
        entity_id: str,
        signals: List[Dict[str, Any]],
        current_time: Optional[datetime] = None,
    ) -> CalibratedSignal:
        """
        Calibrate and aggregate multiple signals for an entity.
        
        This is the main entry point for calibrating entity signals.
        
        Args:
            entity_id: Entity identifier
            signals: List of signal dicts with keys:
                - sentiment: float (0-10)
                - confidence: float (0-1)
                - observed_at: datetime or ISO string
                - source_id: str
            current_time: Current time for freshness calc
            
        Returns:
            CalibratedSignal representing aggregated view
        """
        if not signals:
            # Return neutral signal
            return CalibratedSignal(
                entity_id=entity_id,
                raw_sentiment=5.0,
                calibrated_sentiment=5.0,
                raw_confidence=0.1,
                calibrated_confidence=0.1,
                freshness_factor=0.0,
                source_quality_factor=0.5,
                volume_adjustment=1.0,
                direction_boost=0.0,
                calibration_notes=["No signals available"],
            )
        
        if current_time is None:
            current_time = datetime.now()
        
        # Process each signal
        calibrated_signals = []
        for sig in signals:
            # Parse time
            obs_time = sig.get('observed_at')
            if isinstance(obs_time, str):
                try:
                    obs_time = datetime.fromisoformat(obs_time.replace('Z', '+00:00'))
                except:
                    obs_time = current_time - timedelta(hours=48)
            elif obs_time is None:
                obs_time = current_time - timedelta(hours=48)
            
            cal = self.calibrate_signal(
                entity_id=entity_id,
                raw_sentiment=sig.get('sentiment', 5.0),
                raw_confidence=sig.get('confidence', 0.5),
                signal_time=obs_time,
                source_id=sig.get('source_id', 'unknown'),
                signal_count=len(signals),
                related_signals=signals,
            )
            calibrated_signals.append(cal)
        
        # Weighted aggregation
        total_weight = sum(
            c.freshness_factor * c.source_quality_factor * c.calibrated_confidence
            for c in calibrated_signals
        )
        
        if total_weight == 0:
            total_weight = 1.0
        
        # Weighted average sentiment
        weighted_sentiment = sum(
            c.calibrated_sentiment * c.freshness_factor * c.source_quality_factor * c.calibrated_confidence
            for c in calibrated_signals
        ) / total_weight
        
        # Average other factors
        avg_freshness = sum(c.freshness_factor for c in calibrated_signals) / len(calibrated_signals)
        avg_quality = sum(c.source_quality_factor for c in calibrated_signals) / len(calibrated_signals)
        avg_confidence = sum(c.calibrated_confidence for c in calibrated_signals) / len(calibrated_signals)
        
        # Direction boost on aggregated
        direction_boost, direction = self.calculate_direction_boost(signals)
        
        # Build notes
        notes = []
        if avg_freshness < 0.5:
            notes.append(f"Signals mostly stale (avg freshness={avg_freshness:.2f})")
        if avg_quality < 0.6:
            notes.append(f"Lower quality sources (avg={avg_quality:.2f})")
        if direction_boost != 0:
            notes.append(f"Direction consensus: {direction} ({direction_boost:+.2f})")
        notes.append(f"Aggregated from {len(signals)} signals")
        
        return CalibratedSignal(
            entity_id=entity_id,
            raw_sentiment=sum(s.get('sentiment', 5) for s in signals) / len(signals),
            calibrated_sentiment=round(weighted_sentiment + direction_boost, 2),
            raw_confidence=sum(s.get('confidence', 0.5) for s in signals) / len(signals),
            calibrated_confidence=round(avg_confidence, 3),
            freshness_factor=round(avg_freshness, 3),
            source_quality_factor=round(avg_quality, 3),
            volume_adjustment=self.calculate_volume_adjustment(len(signals)),
            direction_boost=direction_boost,
            calibration_notes=notes,
        )


class CalibratedValidator:
    """
    Extended validator that uses calibrated signals.
    """
    
    def __init__(self, calibrator: Optional[SignalCalibrator] = None):
        self.calibrator = calibrator or SignalCalibrator()
    
    def generate_calibrated_signal(
        self,
        entity_id: str,
        price_data: Dict[str, Any],
        news_sentiment: Optional[float] = None,
        technical_signals: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """
        Generate a properly calibrated signal from multiple sources.
        
        Unlike mock signals, this combines:
        1. Price momentum (recent price action)
        2. News sentiment (if available)
        3. Technical indicators
        
        Args:
            entity_id: Entity identifier
            price_data: Dict with 'changes' key containing price changes
            news_sentiment: Optional news-based sentiment (0-10)
            technical_signals: Optional list of technical signal dicts
            
        Returns:
            Calibrated signal dict
        """
        signals = []
        now = datetime.now()
        
        # 1. Price momentum signal (high quality, fresh)
        price_5d = price_data.get('changes', {}).get('5d', 0)
        price_20d = price_data.get('changes', {}).get('20d', 0)
        
        # Convert price change to sentiment
        # +5% → ~7.5 sentiment, -5% → ~2.5 sentiment
        price_sentiment = 5.0 + (price_5d * 50)  # Scale factor
        price_sentiment = max(1.0, min(10.0, price_sentiment))
        
        signals.append({
            'sentiment': price_sentiment,
            'confidence': 0.9,  # High confidence in price data
            'observed_at': now,
            'source_id': 'yfinance',
        })
        
        # 2. Momentum signal (20d trend)
        if abs(price_20d) > 0.02:
            momentum_sentiment = 5.0 + (price_20d * 30)
            momentum_sentiment = max(1.0, min(10.0, momentum_sentiment))
            signals.append({
                'sentiment': momentum_sentiment,
                'confidence': 0.7,
                'observed_at': now - timedelta(hours=6),
                'source_id': 'yfinance',
            })
        
        # 3. News sentiment (if provided)
        if news_sentiment is not None:
            signals.append({
                'sentiment': news_sentiment,
                'confidence': 0.6,
                'observed_at': now - timedelta(hours=12),
                'source_id': 'news_search',
            })
        
        # 4. Technical signals
        if technical_signals:
            for ts in technical_signals:
                signals.append(ts)
        
        # Calibrate and aggregate
        calibrated = self.calibrator.calibrate_aggregated_signal(
            entity_id=entity_id,
            signals=signals,
            current_time=now,
        )
        
        # Determine momentum label
        if calibrated.calibrated_sentiment > 6.0:
            momentum = "bullish"
        elif calibrated.calibrated_sentiment < 4.0:
            momentum = "bearish"
        else:
            momentum = "neutral"
        
        return {
            'entity_id': entity_id,
            'sentiment': calibrated.calibrated_sentiment,
            'momentum': momentum,
            'confidence': calibrated.calibrated_confidence,
            'raw_sentiment': calibrated.raw_sentiment,
            'adjustments': {
                'freshness': calibrated.freshness_factor,
                'quality': calibrated.source_quality_factor,
                'volume': calibrated.volume_adjustment,
                'direction_boost': calibrated.direction_boost,
            },
            'notes': calibrated.calibration_notes,
        }


class MacroAwareCalibrator:
    """
    Extended calibrator that incorporates macro-economic context.
    
    Adjusts signals based on:
    - Market regime (bull/bear/sideways/crisis)
    - VIX/volatility regime
    - Sector relative strength
    - Geopolitical risk factors
    """
    
    # Entities with significant China exposure
    CHINA_EXPOSED = {
        "nvidia", "amd", "intel", "qualcomm", "micron",
        "apple", "tesla", "tsmc", "broadcom", "asml",
        "applied_materials", "lam_research", "kla",
    }
    
    def __init__(
        self,
        base_calibrator: Optional[SignalCalibrator] = None,
        enable_macro: bool = True,
    ):
        """
        Initialize macro-aware calibrator.
        
        Args:
            base_calibrator: Underlying calibrator (created if None)
            enable_macro: Whether to apply macro adjustments
        """
        self.base_calibrator = base_calibrator or SignalCalibrator()
        self.enable_macro = enable_macro
        
        # Lazy-loaded providers
        self._economic_provider = None
        self._regime_classifier = None
        
        # Cache
        self._macro_cache = {}
        self._cache_time = None
        self._cache_ttl = timedelta(hours=1)
        
        # Load risk config
        self._risk_config = self._load_risk_config()
        
        logger.info(f"MacroAwareCalibrator initialized (macro={enable_macro})")
    
    def _load_risk_config(self) -> Dict[str, Any]:
        """Load risk indicators config."""
        config_path = Path(__file__).parent.parent / "config" / "risk_indicators.json"
        if config_path.exists():
            try:
                with open(config_path, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Could not load risk config: {e}")
        return {}
    
    def _get_macro_context(self) -> Dict[str, Any]:
        """Get current macro context with caching."""
        now = datetime.now()
        
        # Return cached if fresh
        if (self._cache_time and 
            now - self._cache_time < self._cache_ttl and
            self._macro_cache):
            return self._macro_cache
        
        context = {
            "regime": "unknown",
            "regime_confidence": 0.5,
            "vix_level": 20,
            "vix_regime": "normal",
            "sector_strength": "inline",
            "geopolitical_risk": "moderate",
            "confidence_modifier": 1.0,
            "bullish_adjustment": 0.0,
            "bearish_adjustment": 0.0,
        }
        
        # Try regime classifier
        if get_current_regime:
            try:
                regime_data = get_current_regime()
                context["regime"] = regime_data.get("regime", "unknown")
                context["regime_confidence"] = regime_data.get("confidence", 0.5)
                
                snapshot = regime_data.get("snapshot", {})
                context["vix_level"] = snapshot.get("vix_level", 20)
                
                adj = regime_data.get("signal_adjustments", {})
                context["confidence_modifier"] = adj.get("sentiment_reliability", 1.0)
                context["bullish_adjustment"] = adj.get("bullish_signal_boost", 0)
                context["bearish_adjustment"] = adj.get("bearish_signal_penalty", 0)
            except Exception as e:
                logger.warning(f"Could not get regime: {e}")
        
        # Try economic context
        if EconomicContextProvider:
            try:
                if self._economic_provider is None:
                    self._economic_provider = EconomicContextProvider()
                
                vix = self._economic_provider.get_vix_analysis()
                context["vix_regime"] = vix.get("regime", "normal")
                context["vix_level"] = vix.get("current", 20)
                
                sector = self._economic_provider.get_sector_etf_relative_strength()
                context["sector_strength"] = sector.get("ai_sector_strength", "inline")
                
                geo = self._economic_provider.get_geopolitical_risk_context()
                context["geopolitical_risk"] = geo.get("overall_risk_level", "moderate")
            except Exception as e:
                logger.warning(f"Could not get economic context: {e}")
        
        # Calculate VIX-based modifier
        vix = context.get("vix_level", 20)
        vix_modifiers = {
            "complacent": (0, 15, 1.0),
            "normal": (15, 20, 0.95),
            "elevated": (20, 25, 0.85),
            "high": (25, 30, 0.75),
            "fear": (30, 40, 0.6),
            "extreme": (40, 100, 0.4),
        }
        for regime, (low, high, mod) in vix_modifiers.items():
            if low <= vix < high:
                context["vix_confidence_modifier"] = mod
                context["vix_regime"] = regime
                break
        
        self._macro_cache = context
        self._cache_time = now
        return context
    
    def calibrate_with_macro(
        self,
        entity_id: str,
        signals: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Calibrate signals with macro context applied.
        
        Example adjustments:
        - Bullish AI signal + rising rates = lower confidence
        - Bearish signal in bear market = higher conviction
        - China-exposed entity + elevated geopolitical risk = penalty
        
        Args:
            entity_id: Entity identifier
            signals: List of signal dicts
            
        Returns:
            Dict with calibrated signal and macro context
        """
        # Base calibration
        calibrated = self.base_calibrator.calibrate_aggregated_signal(
            entity_id=entity_id,
            signals=signals,
        )
        
        if not self.enable_macro:
            return {
                "entity_id": entity_id,
                "calibrated_sentiment": calibrated.calibrated_sentiment,
                "calibrated_confidence": calibrated.calibrated_confidence,
                "macro_applied": False,
                "base_calibration": calibrated,
            }
        
        # Get macro context
        macro = self._get_macro_context()
        
        # Start with calibrated values
        final_sentiment = calibrated.calibrated_sentiment
        final_confidence = calibrated.calibrated_confidence
        adjustments = []
        
        # 1. Regime-based adjustment
        regime = macro.get("regime", "unknown")
        is_bullish = final_sentiment > 6.0
        is_bearish = final_sentiment < 4.0
        
        if regime == "bull" and is_bullish:
            final_sentiment += macro.get("bullish_adjustment", 0)
            adjustments.append(f"Bull regime boost: +{macro.get('bullish_adjustment', 0):.2f}")
        elif regime == "bear" and is_bullish:
            final_sentiment -= 0.15
            final_confidence *= 0.9
            adjustments.append("Bullish signal in bear market: -0.15, confidence reduced")
        elif regime == "bear" and is_bearish:
            final_confidence *= 1.1
            adjustments.append("Bearish signal confirmed by bear regime")
        elif regime == "crisis":
            final_confidence *= 0.6
            adjustments.append("Crisis regime: confidence heavily reduced")
        
        # 2. VIX-based confidence adjustment
        vix_mod = macro.get("vix_confidence_modifier", 1.0)
        if vix_mod < 1.0:
            final_confidence *= vix_mod
            adjustments.append(f"VIX regime ({macro.get('vix_regime')}): conf x{vix_mod:.2f}")
        
        # 3. Sector strength adjustment
        sector = macro.get("sector_strength", "inline")
        if sector in ["strong_outperformance", "outperforming"] and is_bullish:
            final_sentiment += 0.1
            adjustments.append("AI sector outperforming: bullish boost +0.1")
        elif sector in ["underperforming", "strong_underperformance"] and is_bullish:
            final_sentiment -= 0.1
            adjustments.append("AI sector weak: bullish penalty -0.1")
        
        # 4. Geopolitical risk for China-exposed entities
        entity_lower = entity_id.lower()
        geo_risk = macro.get("geopolitical_risk", "moderate")
        is_china_exposed = any(e in entity_lower for e in self.CHINA_EXPOSED)
        
        if is_china_exposed and geo_risk in ["elevated", "high"]:
            penalty = -0.15 if geo_risk == "elevated" else -0.25
            final_sentiment += penalty
            final_confidence *= 0.9
            adjustments.append(f"China exposure + {geo_risk} geopolitical risk: {penalty:.2f}")
        
        # Clamp values
        final_sentiment = max(1.0, min(10.0, final_sentiment))
        final_confidence = max(0.1, min(1.0, final_confidence))
        
        # Determine momentum
        if final_sentiment > 6.0:
            momentum = "bullish"
        elif final_sentiment < 4.0:
            momentum = "bearish"
        else:
            momentum = "neutral"
        
        return {
            "entity_id": entity_id,
            "calibrated_sentiment": round(final_sentiment, 2),
            "calibrated_confidence": round(final_confidence, 3),
            "momentum": momentum,
            "macro_applied": True,
            "macro_adjustments": adjustments,
            "macro_context": {
                "regime": regime,
                "vix_regime": macro.get("vix_regime"),
                "sector_strength": sector,
                "geopolitical_risk": geo_risk,
            },
            "base_calibration": {
                "sentiment": calibrated.calibrated_sentiment,
                "confidence": calibrated.calibrated_confidence,
            },
        }
    
    def get_macro_summary(self) -> Dict[str, Any]:
        """Get current macro context summary."""
        return self._get_macro_context()


# Utility functions for easy access
def calibrate_entity_signals(
    entity_id: str,
    signals: List[Dict[str, Any]],
    **kwargs
) -> CalibratedSignal:
    """Quick access to calibrate signals for an entity."""
    calibrator = SignalCalibrator(**kwargs)
    return calibrator.calibrate_aggregated_signal(entity_id, signals)


def calibrate_with_macro_context(
    entity_id: str,
    signals: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Calibrate signals with macro-economic context."""
    calibrator = MacroAwareCalibrator()
    return calibrator.calibrate_with_macro(entity_id, signals)


def apply_freshness_decay(
    sentiment: float,
    signal_age_hours: float,
    half_life: float = 24.0
) -> float:
    """Apply freshness decay to a single sentiment value."""
    decay = math.pow(0.5, signal_age_hours / half_life)
    return 5.0 + (sentiment - 5.0) * decay


if __name__ == "__main__":
    # Test calibration
    print("=" * 60)
    print("Signal Calibrator Test")
    print("=" * 60)
    
    calibrator = SignalCalibrator()
    
    # Test freshness decay
    print("\n[FRESHNESS TEST]")
    for hours in [0, 6, 12, 24, 48, 72, 168]:
        signal_time = datetime.now() - timedelta(hours=hours)
        factor = calibrator.calculate_freshness_factor(signal_time)
        print(f"  {hours:3d}h old: {factor:.3f}")
    
    # Test source quality
    print("\n[SOURCE QUALITY TEST]")
    for source in ['bloomberg', 'sec_edgar', 'reddit', 'github', 'unknown']:
        weight = calibrator.get_source_quality_weight(source)
        print(f"  {source}: {weight:.2f}")
    
    # Test full calibration
    print("\n[FULL CALIBRATION TEST]")
    
    # Simulate signals for NVDA
    test_signals = [
        {'sentiment': 6.5, 'confidence': 0.8, 'observed_at': datetime.now() - timedelta(hours=2), 'source_id': 'news_search'},
        {'sentiment': 5.8, 'confidence': 0.6, 'observed_at': datetime.now() - timedelta(hours=12), 'source_id': 'reddit'},
        {'sentiment': 7.2, 'confidence': 0.9, 'observed_at': datetime.now() - timedelta(hours=6), 'source_id': 'yfinance'},
        {'sentiment': 4.5, 'confidence': 0.5, 'observed_at': datetime.now() - timedelta(hours=72), 'source_id': 'social_sentiment'},  # Stale
    ]
    
    result = calibrator.calibrate_aggregated_signal('nvidia', test_signals)
    
    print(f"\n  Entity: {result.entity_id}")
    print(f"  Raw sentiment: {result.raw_sentiment:.2f}")
    print(f"  Calibrated sentiment: {result.calibrated_sentiment:.2f}")
    print(f"  Raw confidence: {result.raw_confidence:.2f}")
    print(f"  Calibrated confidence: {result.calibrated_confidence:.3f}")
    print(f"  Freshness factor: {result.freshness_factor:.3f}")
    print(f"  Source quality: {result.source_quality_factor:.3f}")
    print(f"  Direction boost: {result.direction_boost:+.3f}")
    print(f"  Notes: {result.calibration_notes}")
    
    print("\n" + "=" * 60)
    print("Calibration module ready for integration")
    print("=" * 60)
