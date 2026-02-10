"""
Divergence Detector

Identifies divergences between signal types to surface opportunities and risks.
Key insight: when signals disagree, there's often a story worth investigating.

Divergence Types:
- Technical vs Financial: Innovation without funding (opportunity) or vice versa
- Financial vs Product: Heavy funding without traction (burn risk)
- Technical vs Media: Under-the-radar innovation or overhyped tech
- Product vs Media: Organic growth vs media darling
- Price vs Fundamental: Technical (price) disagrees with news sentiment → strong signal!

NEW: Price-Fundamental Divergence
When price action and news sentiment strongly disagree, it often precedes:
- Mean reversion (price catches up to fundamentals)
- Narrative shift (market knows something news doesn't)
Either way, it's actionable.
"""

from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
import json

from .signal_models import (
    SignalCategory, SignalProfile, SignalDivergence,
    DivergenceType, DivergenceInterpretation, DivergenceThresholds
)


@dataclass
class PriceFundamentalDivergence:
    """
    Divergence between price action and fundamental signals.
    
    These divergences often precede strong price moves:
    - Price bearish + Fundamentals bullish → Potential undervaluation
    - Price bullish + Fundamentals bearish → Potential overvaluation
    """
    entity_id: str
    entity_name: str
    
    # Price action
    price_change_5d: float  # 5-day price change %
    price_direction: str    # "bullish" / "bearish" / "neutral"
    
    # Fundamental signal (news sentiment)
    fundamental_score: float  # 1-10
    fundamental_direction: str
    fundamental_confidence: float
    
    # Divergence metrics
    divergence_magnitude: float  # How strongly they disagree (0-100)
    divergence_type: str  # "price_leads" or "fundamental_leads"
    
    # Interpretation
    signal_strength: str  # "strong" / "moderate" / "weak"
    interpretation: str
    recommended_action: str
    
    # Tracking
    detected_at: datetime = field(default_factory=datetime.now)
    resolution_window_hours: int = 120  # 5 days to track resolution
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "entity_name": self.entity_name,
            "price_change_5d": self.price_change_5d,
            "price_direction": self.price_direction,
            "fundamental_score": self.fundamental_score,
            "fundamental_direction": self.fundamental_direction,
            "divergence_magnitude": self.divergence_magnitude,
            "divergence_type": self.divergence_type,
            "signal_strength": self.signal_strength,
            "interpretation": self.interpretation,
            "recommended_action": self.recommended_action,
            "detected_at": self.detected_at.isoformat(),
        }


class DivergenceDetector:
    """
    Detects and interprets divergences between signal categories.

    A divergence occurs when two signal types show significantly
    different scores for the same entity. These divergences often
    reveal opportunities or risks not visible from any single signal.
    """

    # Divergence type mappings
    DIVERGENCE_PAIRS = {
        DivergenceType.TECHNICAL_VS_FINANCIAL: (
            SignalCategory.TECHNICAL,
            SignalCategory.FINANCIAL
        ),
        DivergenceType.FINANCIAL_VS_PRODUCT: (
            SignalCategory.FINANCIAL,
            SignalCategory.PRODUCT_TRACTION
        ),
        DivergenceType.TECHNICAL_VS_MEDIA: (
            SignalCategory.TECHNICAL,
            SignalCategory.MEDIA_SENTIMENT
        ),
        DivergenceType.PRODUCT_VS_MEDIA: (
            SignalCategory.PRODUCT_TRACTION,
            SignalCategory.MEDIA_SENTIMENT
        ),
    }

    def __init__(self, thresholds: Optional[DivergenceThresholds] = None):
        """
        Initialize detector with divergence thresholds.

        Args:
            thresholds: Custom thresholds. Uses defaults if None.
        """
        self.thresholds = thresholds or DivergenceThresholds()

    def detect_divergences(
        self,
        profile: SignalProfile,
        min_confidence: float = 0.5
    ) -> List[SignalDivergence]:
        """
        Detect all divergences for a single entity profile.

        Args:
            profile: SignalProfile to analyze
            min_confidence: Minimum confidence to report divergence

        Returns:
            List of detected SignalDivergence objects
        """
        divergences = []
        scores = profile.get_score_dict()

        for div_type, (cat_a, cat_b) in self.DIVERGENCE_PAIRS.items():
            score_a = scores.get(cat_a)
            score_b = scores.get(cat_b)

            # Skip if either score is missing
            if score_a is None or score_b is None:
                continue

            # Check for divergence
            threshold = self.thresholds.get_threshold(div_type)
            magnitude = abs(score_a - score_b)

            if magnitude >= threshold:
                # Determine which is high/low
                if score_a > score_b:
                    high_cat, high_score = cat_a, score_a
                    low_cat, low_score = cat_b, score_b
                else:
                    high_cat, high_score = cat_b, score_b
                    low_cat, low_score = cat_a, score_a

                # Interpret the divergence
                interpretation, rationale = self._interpret_divergence(
                    div_type, high_cat, high_score, low_cat, low_score
                )

                # Calculate confidence based on score confidence
                conf_a = getattr(profile, f"{self._cat_to_attr(cat_a)}_confidence", 0.5)
                conf_b = getattr(profile, f"{self._cat_to_attr(cat_b)}_confidence", 0.5)
                confidence = min(conf_a, conf_b)

                if confidence >= min_confidence:
                    divergence = SignalDivergence(
                        entity_id=profile.entity_id,
                        entity_name=profile.entity_name,
                        divergence_type=div_type,
                        high_signal_category=high_cat,
                        high_signal_score=high_score,
                        low_signal_category=low_cat,
                        low_signal_score=low_score,
                        divergence_magnitude=magnitude,
                        confidence=confidence,
                        interpretation=interpretation,
                        interpretation_rationale=rationale,
                    )
                    divergences.append(divergence)

        return divergences

    def detect_batch(
        self,
        profiles: List[SignalProfile],
        min_confidence: float = 0.5
    ) -> Dict[str, List[SignalDivergence]]:
        """
        Detect divergences for multiple profiles.

        Args:
            profiles: List of SignalProfiles
            min_confidence: Minimum confidence threshold

        Returns:
            Dict mapping entity_id to list of divergences
        """
        results = {}
        for profile in profiles:
            divergences = self.detect_divergences(profile, min_confidence)
            if divergences:
                results[profile.entity_id] = divergences
        return results

    def get_opportunities(
        self,
        profiles: List[SignalProfile],
        min_magnitude: float = 25.0
    ) -> List[SignalDivergence]:
        """
        Get all opportunity-type divergences across profiles.

        Args:
            profiles: Profiles to analyze
            min_magnitude: Minimum divergence magnitude

        Returns:
            List of opportunity divergences, sorted by magnitude
        """
        opportunities = []

        for profile in profiles:
            divergences = self.detect_divergences(profile)
            for div in divergences:
                if div.interpretation == DivergenceInterpretation.OPPORTUNITY:
                    if div.divergence_magnitude >= min_magnitude:
                        opportunities.append(div)

        # Sort by magnitude descending
        opportunities.sort(key=lambda d: d.divergence_magnitude, reverse=True)
        return opportunities

    def get_risks(
        self,
        profiles: List[SignalProfile],
        min_magnitude: float = 20.0
    ) -> List[SignalDivergence]:
        """
        Get all risk-type divergences across profiles.

        Args:
            profiles: Profiles to analyze
            min_magnitude: Minimum divergence magnitude

        Returns:
            List of risk divergences, sorted by magnitude
        """
        risks = []

        for profile in profiles:
            divergences = self.detect_divergences(profile)
            for div in divergences:
                if div.interpretation == DivergenceInterpretation.RISK:
                    if div.divergence_magnitude >= min_magnitude:
                        risks.append(div)

        risks.sort(key=lambda d: d.divergence_magnitude, reverse=True)
        return risks

    def _interpret_divergence(
        self,
        div_type: DivergenceType,
        high_cat: SignalCategory,
        high_score: float,
        low_cat: SignalCategory,
        low_score: float
    ) -> Tuple[DivergenceInterpretation, str]:
        """
        Interpret what a divergence means.

        Returns (interpretation, rationale) tuple.
        """
        # Technical vs Financial
        if div_type == DivergenceType.TECHNICAL_VS_FINANCIAL:
            if high_cat == SignalCategory.TECHNICAL:
                return (
                    DivergenceInterpretation.OPPORTUNITY,
                    f"Strong technical adoption (score {high_score:.0f}) without "
                    f"commensurate funding (score {low_score:.0f}). "
                    "Potential investment opportunity or partnership target."
                )
            else:
                return (
                    DivergenceInterpretation.RISK,
                    f"High funding (score {high_score:.0f}) but weak technical "
                    f"traction (score {low_score:.0f}). "
                    "Capital may not translate to developer adoption."
                )

        # Financial vs Product
        elif div_type == DivergenceType.FINANCIAL_VS_PRODUCT:
            if high_cat == SignalCategory.FINANCIAL:
                return (
                    DivergenceInterpretation.RISK,
                    f"Strong funding (score {high_score:.0f}) without product "
                    f"traction (score {low_score:.0f}). "
                    "Potential burn rate concern - money without customers."
                )
            else:
                return (
                    DivergenceInterpretation.OPPORTUNITY,
                    f"Strong product traction (score {high_score:.0f}) with "
                    f"limited funding (score {low_score:.0f}). "
                    "Organic growth story - potential fundraising candidate."
                )

        # Technical vs Media
        elif div_type == DivergenceType.TECHNICAL_VS_MEDIA:
            if high_cat == SignalCategory.TECHNICAL:
                return (
                    DivergenceInterpretation.OPPORTUNITY,
                    f"Strong technical signals (score {high_score:.0f}) but low "
                    f"media coverage (score {low_score:.0f}). "
                    "Under-the-radar innovation - early mover advantage."
                )
            else:
                return (
                    DivergenceInterpretation.RISK,
                    f"High media buzz (score {high_score:.0f}) without technical "
                    f"substance (score {low_score:.0f}). "
                    "Hype cycle warning - narrative may exceed reality."
                )

        # Product vs Media
        elif div_type == DivergenceType.PRODUCT_VS_MEDIA:
            if high_cat == SignalCategory.PRODUCT_TRACTION:
                return (
                    DivergenceInterpretation.OPPORTUNITY,
                    f"Strong product metrics (score {high_score:.0f}) but limited "
                    f"media presence (score {low_score:.0f}). "
                    "Organic growth without PR - sustainable traction."
                )
            else:
                return (
                    DivergenceInterpretation.RISK,
                    f"Media darling (score {high_score:.0f}) with weak product "
                    f"traction (score {low_score:.0f}). "
                    "Coverage exceeds customer adoption."
                )

        # Default
        return (
            DivergenceInterpretation.ANOMALY,
            f"Unusual signal pattern: {high_cat.value}={high_score:.0f}, "
            f"{low_cat.value}={low_score:.0f}"
        )

    def _cat_to_attr(self, category: SignalCategory) -> str:
        """Convert category to profile attribute name."""
        mapping = {
            SignalCategory.TECHNICAL: "technical",
            SignalCategory.COMPANY_PRESENCE: "company",
            SignalCategory.FINANCIAL: "financial",
            SignalCategory.PRODUCT_TRACTION: "product",
            SignalCategory.MEDIA_SENTIMENT: "media",
        }
        return mapping.get(category, category.value)

    def summarize_divergences(
        self,
        divergences: List[SignalDivergence]
    ) -> Dict[str, Any]:
        """
        Create summary statistics for a list of divergences.

        Args:
            divergences: List of divergences

        Returns:
            Summary dict with counts, top items, etc.
        """
        if not divergences:
            return {
                "total_count": 0,
                "opportunities": 0,
                "risks": 0,
                "by_type": {},
            }

        by_interpretation = defaultdict(list)
        by_type = defaultdict(list)

        for div in divergences:
            by_interpretation[div.interpretation.value].append(div)
            by_type[div.divergence_type.value].append(div)

        # Get top opportunities and risks
        opportunities = sorted(
            by_interpretation.get("opportunity", []),
            key=lambda d: d.divergence_magnitude,
            reverse=True
        )[:5]

        risks = sorted(
            by_interpretation.get("risk", []),
            key=lambda d: d.divergence_magnitude,
            reverse=True
        )[:5]

        return {
            "total_count": len(divergences),
            "opportunities": len(by_interpretation.get("opportunity", [])),
            "risks": len(by_interpretation.get("risk", [])),
            "anomalies": len(by_interpretation.get("anomaly", [])),
            "by_type": {k: len(v) for k, v in by_type.items()},
            "top_opportunities": [
                {
                    "entity": d.entity_name,
                    "type": d.divergence_type.value,
                    "magnitude": d.divergence_magnitude,
                    "rationale": d.interpretation_rationale,
                }
                for d in opportunities
            ],
            "top_risks": [
                {
                    "entity": d.entity_name,
                    "type": d.divergence_type.value,
                    "magnitude": d.divergence_magnitude,
                    "rationale": d.interpretation_rationale,
                }
                for d in risks
            ],
        }


class PriceFundamentalDivergenceDetector:
    """
    Detects divergences between price action and fundamental signals.
    
    Key insight: When technicals (price) and fundamentals (news) disagree,
    it often creates a strong trading signal.
    
    Scenarios:
    1. Price down + News bullish → Potential buying opportunity (undervalued)
    2. Price up + News bearish → Potential selling signal (overvalued)
    3. Price flat + News strong → Anticipate breakout in direction of fundamentals
    """
    
    # Thresholds
    PRICE_BULLISH_THRESHOLD = 0.03   # +3% in 5 days = bullish
    PRICE_BEARISH_THRESHOLD = -0.03  # -3% in 5 days = bearish
    FUNDAMENTAL_BULLISH_THRESHOLD = 6.5
    FUNDAMENTAL_BEARISH_THRESHOLD = 3.5
    DIVERGENCE_THRESHOLD = 40.0  # Minimum magnitude to flag
    
    def __init__(
        self,
        price_threshold: float = 0.03,
        fundamental_threshold: float = 1.5,  # Distance from neutral (5.0)
    ):
        self.price_threshold = price_threshold
        self.fundamental_threshold = fundamental_threshold
        self._resolution_history: Dict[str, List[Dict]] = {}
    
    def detect_divergence(
        self,
        entity_id: str,
        entity_name: str,
        price_change_5d: float,
        fundamental_score: float,
        fundamental_confidence: float = 0.5,
    ) -> Optional[PriceFundamentalDivergence]:
        """
        Detect if price and fundamentals diverge.
        
        Args:
            entity_id: Entity identifier
            entity_name: Display name
            price_change_5d: 5-day price change as decimal (0.05 = +5%)
            fundamental_score: News sentiment score (1-10)
            fundamental_confidence: Confidence in fundamental signal
            
        Returns:
            PriceFundamentalDivergence if detected, None otherwise
        """
        # Classify price direction
        if price_change_5d > self.price_threshold:
            price_direction = "bullish"
        elif price_change_5d < -self.price_threshold:
            price_direction = "bearish"
        else:
            price_direction = "neutral"
        
        # Classify fundamental direction
        if fundamental_score > self.FUNDAMENTAL_BULLISH_THRESHOLD:
            fundamental_direction = "bullish"
        elif fundamental_score < self.FUNDAMENTAL_BEARISH_THRESHOLD:
            fundamental_direction = "bearish"
        else:
            fundamental_direction = "neutral"
        
        # Check for divergence (directions disagree)
        has_divergence = False
        divergence_type = "none"
        
        if price_direction == "bullish" and fundamental_direction == "bearish":
            has_divergence = True
            divergence_type = "price_leads"
        elif price_direction == "bearish" and fundamental_direction == "bullish":
            has_divergence = True
            divergence_type = "fundamental_leads"
        elif price_direction == "neutral" and fundamental_direction != "neutral":
            # Price flat but fundamentals have signal - weaker divergence
            has_divergence = True
            divergence_type = "fundamental_anticipation"
        
        if not has_divergence:
            return None
        
        # Calculate divergence magnitude
        # Price component: scale 5-day return to 0-50 scale
        price_score = min(50, abs(price_change_5d) * 1000)  # 5% → 50
        
        # Fundamental component: distance from neutral scaled to 0-50
        fundamental_deviation = abs(fundamental_score - 5.0)
        fundamental_score_scaled = fundamental_deviation * 10  # 3 points deviation → 30
        
        divergence_magnitude = price_score + fundamental_score_scaled
        
        # Only flag if significant
        if divergence_magnitude < self.DIVERGENCE_THRESHOLD:
            return None
        
        # Determine signal strength
        if divergence_magnitude >= 70:
            signal_strength = "strong"
        elif divergence_magnitude >= 50:
            signal_strength = "moderate"
        else:
            signal_strength = "weak"
        
        # Generate interpretation
        interpretation, action = self._interpret_divergence(
            price_direction,
            fundamental_direction,
            divergence_type,
            price_change_5d,
            fundamental_score,
            signal_strength
        )
        
        return PriceFundamentalDivergence(
            entity_id=entity_id,
            entity_name=entity_name,
            price_change_5d=price_change_5d,
            price_direction=price_direction,
            fundamental_score=fundamental_score,
            fundamental_direction=fundamental_direction,
            fundamental_confidence=fundamental_confidence,
            divergence_magnitude=round(divergence_magnitude, 1),
            divergence_type=divergence_type,
            signal_strength=signal_strength,
            interpretation=interpretation,
            recommended_action=action,
        )
    
    def _interpret_divergence(
        self,
        price_dir: str,
        fund_dir: str,
        div_type: str,
        price_change: float,
        fund_score: float,
        strength: str
    ) -> Tuple[str, str]:
        """Generate interpretation and recommended action."""
        
        if div_type == "fundamental_leads":
            # Price bearish, fundamentals bullish
            interpretation = (
                f"Price down {abs(price_change)*100:.1f}% but news sentiment is bullish "
                f"(score {fund_score:.1f}). Market may be overreacting to short-term "
                "factors while fundamentals remain positive."
            )
            if strength == "strong":
                action = "Consider accumulation - strong buy signal"
            else:
                action = "Watch for stabilization - potential entry point"
        
        elif div_type == "price_leads":
            # Price bullish, fundamentals bearish
            interpretation = (
                f"Price up {abs(price_change)*100:.1f}% despite bearish news "
                f"(score {fund_score:.1f}). Either market sees something news "
                "doesn't, or price is extended."
            )
            if strength == "strong":
                action = "Caution - consider taking profits or hedging"
            else:
                action = "Monitor closely - watch for news to catch up"
        
        else:  # fundamental_anticipation
            interpretation = (
                f"Price flat but fundamentals show {fund_dir} signal "
                f"(score {fund_score:.1f}). Price may be coiling for a move."
            )
            if fund_dir == "bullish":
                action = "Watch for breakout - fundamentals suggest upside"
            else:
                action = "Watch for breakdown - fundamentals suggest downside"
        
        return interpretation, action
    
    def track_resolution(
        self,
        divergence: PriceFundamentalDivergence,
        outcome_price_change: float,
        resolution_days: int
    ) -> Dict[str, Any]:
        """
        Track how a divergence resolved.
        
        This data helps calibrate which divergences are most predictive.
        """
        resolution = {
            "entity_id": divergence.entity_id,
            "divergence_type": divergence.divergence_type,
            "divergence_magnitude": divergence.divergence_magnitude,
            "detected_at": divergence.detected_at.isoformat(),
            "fundamental_direction": divergence.fundamental_direction,
            "initial_price_direction": divergence.price_direction,
            "outcome_price_change": outcome_price_change,
            "resolution_days": resolution_days,
            "resolved_at": datetime.now().isoformat(),
        }
        
        # Determine if fundamental signal was correct
        if divergence.fundamental_direction == "bullish":
            resolution["fundamental_correct"] = outcome_price_change > 0.02
        elif divergence.fundamental_direction == "bearish":
            resolution["fundamental_correct"] = outcome_price_change < -0.02
        else:
            resolution["fundamental_correct"] = abs(outcome_price_change) < 0.03
        
        # Store for analysis
        if divergence.entity_id not in self._resolution_history:
            self._resolution_history[divergence.entity_id] = []
        self._resolution_history[divergence.entity_id].append(resolution)
        
        return resolution
    
    def get_resolution_stats(self) -> Dict[str, Any]:
        """Get statistics on divergence resolutions."""
        all_resolutions = []
        for resolutions in self._resolution_history.values():
            all_resolutions.extend(resolutions)
        
        if not all_resolutions:
            return {"total": 0, "fundamental_win_rate": None}
        
        fundamental_correct = sum(1 for r in all_resolutions if r.get("fundamental_correct", False))
        
        return {
            "total": len(all_resolutions),
            "fundamental_win_rate": fundamental_correct / len(all_resolutions),
            "by_type": {
                "fundamental_leads": [r for r in all_resolutions if r["divergence_type"] == "fundamental_leads"],
                "price_leads": [r for r in all_resolutions if r["divergence_type"] == "price_leads"],
            }
        }
    
    def analyze_batch(
        self,
        entities: List[Dict[str, Any]]
    ) -> List[PriceFundamentalDivergence]:
        """
        Analyze multiple entities for divergences.
        
        Args:
            entities: List of dicts with keys:
                - entity_id
                - entity_name
                - price_change_5d
                - fundamental_score
                - fundamental_confidence (optional)
                
        Returns:
            List of detected divergences, sorted by magnitude
        """
        divergences = []
        
        for entity in entities:
            div = self.detect_divergence(
                entity_id=entity["entity_id"],
                entity_name=entity.get("entity_name", entity["entity_id"]),
                price_change_5d=entity["price_change_5d"],
                fundamental_score=entity["fundamental_score"],
                fundamental_confidence=entity.get("fundamental_confidence", 0.5),
            )
            
            if div:
                divergences.append(div)
        
        # Sort by magnitude
        divergences.sort(key=lambda d: d.divergence_magnitude, reverse=True)
        
        return divergences


def detect_hype_cycle_position(profile: SignalProfile) -> Dict[str, Any]:
    """
    Estimate entity's position in the hype cycle based on signal patterns.

    Hype Cycle Phases:
    1. Innovation Trigger: High technical, low everything else
    2. Peak of Inflated Expectations: High media, moderate/low others
    3. Trough of Disillusionment: Declining media, stable/low others
    4. Slope of Enlightenment: Rising product, moderate media
    5. Plateau of Productivity: Balanced high scores

    Args:
        profile: Entity's SignalProfile

    Returns:
        Dict with phase estimate and confidence
    """
    tech = profile.technical_score or 0
    company = profile.company_score or 0
    financial = profile.financial_score or 0
    product = profile.product_score or 0
    media = profile.media_score or 0

    # Calculate averages
    avg_all = (tech + company + financial + product + media) / 5
    avg_non_media = (tech + company + financial + product) / 4

    # Phase detection logic
    if tech > 60 and media < 40 and product < 40:
        phase = "Innovation Trigger"
        description = "Early technical innovation, not yet widely known"
        confidence = min(0.9, (tech - media) / 100)

    elif media > 70 and media > tech and media > product:
        if product < 40:
            phase = "Peak of Inflated Expectations"
            description = "High media attention exceeding substance"
            confidence = min(0.9, (media - product) / 100)
        else:
            phase = "Slope of Enlightenment"
            description = "Media and product both strong - maturing"
            confidence = 0.7

    elif avg_non_media > 50 and media < avg_non_media - 20:
        phase = "Trough of Disillusionment"
        description = "Fundamentals exist but media interest waned"
        confidence = min(0.8, (avg_non_media - media) / 100)

    elif product > 60 and abs(media - product) < 20:
        if avg_all > 60:
            phase = "Plateau of Productivity"
            description = "Balanced strong signals - established player"
            confidence = 0.8
        else:
            phase = "Slope of Enlightenment"
            description = "Building product traction with balanced coverage"
            confidence = 0.7

    else:
        phase = "Uncertain"
        description = "Signal pattern doesn't match clear hype cycle phase"
        confidence = 0.3

    return {
        "phase": phase,
        "description": description,
        "confidence": confidence,
        "signal_pattern": {
            "technical": tech,
            "company": company,
            "financial": financial,
            "product": product,
            "media": media,
        }
    }


if __name__ == "__main__":
    # Test divergence detection
    print("Testing Divergence Detector")
    print("=" * 50)

    from .signal_models import EntityType

    # Create test profile with divergences
    profile = SignalProfile(
        entity_id="test-123",
        entity_name="HypeStartup Inc",
        entity_type=EntityType.COMPANY,
        technical_score=45,     # Low technical
        company_score=60,
        financial_score=85,     # High funding
        product_score=30,       # Low product traction
        media_score=90,         # High media buzz
        technical_confidence=0.8,
        company_confidence=0.8,
        financial_confidence=0.9,
        product_confidence=0.7,
        media_confidence=0.85,
    )

    detector = DivergenceDetector()
    divergences = detector.detect_divergences(profile)

    print(f"Entity: {profile.entity_name}")
    print(f"Found {len(divergences)} divergences:")
    print()

    for div in divergences:
        print(f"  {div.divergence_type.value}")
        print(f"    High: {div.high_signal_category.value} = {div.high_signal_score:.0f}")
        print(f"    Low:  {div.low_signal_category.value} = {div.low_signal_score:.0f}")
        print(f"    Magnitude: {div.divergence_magnitude:.0f}")
        print(f"    Interpretation: {div.interpretation.value}")
        print(f"    Rationale: {div.interpretation_rationale}")
        print()

    # Test hype cycle detection
    print("=" * 50)
    print("Hype Cycle Analysis:")
    hype = detect_hype_cycle_position(profile)
    print(f"  Phase: {hype['phase']}")
    print(f"  Description: {hype['description']}")
    print(f"  Confidence: {hype['confidence']:.0%}")
    
    # Test Price-Fundamental Divergence Detection
    print("\n" + "=" * 50)
    print("Price-Fundamental Divergence Detection")
    print("=" * 50)
    
    pf_detector = PriceFundamentalDivergenceDetector()
    
    # Test cases
    test_cases = [
        {
            "entity_id": "nvda",
            "entity_name": "NVIDIA",
            "price_change_5d": -0.08,  # Down 8%
            "fundamental_score": 8.5,   # Very bullish news
            "fundamental_confidence": 0.85,
        },
        {
            "entity_id": "meta",
            "entity_name": "Meta",
            "price_change_5d": 0.06,   # Up 6%
            "fundamental_score": 3.2,   # Bearish news
            "fundamental_confidence": 0.7,
        },
        {
            "entity_id": "msft",
            "entity_name": "Microsoft",
            "price_change_5d": 0.01,   # Flat
            "fundamental_score": 7.8,   # Bullish news
            "fundamental_confidence": 0.8,
        },
        {
            "entity_id": "googl",
            "entity_name": "Google",
            "price_change_5d": 0.02,   # Slightly up
            "fundamental_score": 5.5,   # Neutral news
            "fundamental_confidence": 0.6,
        },
    ]
    
    detected = pf_detector.analyze_batch(test_cases)
    
    print(f"\nAnalyzed {len(test_cases)} entities, found {len(detected)} divergences:")
    
    for div in detected:
        emoji = "🔴" if div.divergence_type == "price_leads" else "🟢"
        print(f"\n{emoji} {div.entity_name}")
        print(f"   Price: {div.price_change_5d*100:+.1f}% ({div.price_direction})")
        print(f"   Fundamental: {div.fundamental_score:.1f} ({div.fundamental_direction})")
        print(f"   Divergence: {div.divergence_magnitude:.0f} ({div.signal_strength})")
        print(f"   Type: {div.divergence_type}")
        print(f"   → {div.interpretation}")
        print(f"   Action: {div.recommended_action}")
