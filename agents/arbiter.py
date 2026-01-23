"""
Arbiter Agent (The Judge)

Synthesizes conflicting Bull/Bear data into a single conviction score.
Uses weighted scoring based on entity type (OSS gets more credit for technical adoption).
"""

import json
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from enum import Enum
from loguru import logger

from agents.hypeman import HypeManOutput
from agents.skeptic import SkepticOutput


class ConflictIntensity(Enum):
    """Level of disagreement between Hype-Man and Skeptic."""
    HIGH = "HIGH"      # Big spread (>40) - needs human review
    MEDIUM = "MEDIUM"  # Moderate uncertainty (20-40)
    LOW = "LOW"        # Consensus (<20)


class Recommendation(Enum):
    """Actionable recommendation states."""
    ALERT = "ALERT"           # Conviction > 80, push notification
    INVESTIGATE = "INVESTIGATE"  # High conflict, needs human review
    MONITOR = "MONITOR"       # Conviction 40-79, add to watchlist
    IGNORE = "IGNORE"         # Conviction < 40 or high risk


@dataclass
class SignalBreakdown:
    """Breakdown of component scores."""
    technical_velocity: int
    commercial_maturity: int
    brand_safety: int


@dataclass
class Verdict:
    """Synthesized verdict from both agents."""
    bull_thesis: str
    bear_thesis: str
    synthesis: str
    key_uncertainty: str


@dataclass
class ArbiterOutput:
    """Output schema for Arbiter agent."""
    entity: str
    entity_type: str
    conviction_score: int
    conflict_intensity: str
    verdict: Dict[str, str]
    signal_breakdown: Dict[str, int]
    recommendation: str
    momentum_bonus: int
    risk_penalty: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ArbiterAgent:
    """
    The Judge - synthesizes Hype-Man and Skeptic outputs into conviction score.

    Weighted Scoring Logic (OSS Defense):
    - OSS projects: 70% technical velocity, 30% commercial maturity
    - Commercial SaaS: 50% technical, 50% commercial

    Recommendation States:
    - ALERT: Conviction > 80, high confidence breakout
    - INVESTIGATE: High conflict, needs human review
    - MONITOR: Conviction 40-79, watchlist
    - IGNORE: Conviction < 40 or risk_penalty > -30
    """

    def __init__(self, llm_client=None):
        """
        Initialize Arbiter agent.

        Args:
            llm_client: LLM client for synthesis (optional)
        """
        self.llm_client = llm_client

    def _get_llm_client(self):
        """Lazy load LLM client."""
        if self.llm_client is None:
            from utils.llm_client import LLMClient
            self.llm_client = LLMClient(enable_caching=True)
        return self.llm_client

    def calculate_conviction(
        self,
        entity_type: str,
        technical_score: int,
        commercial_score: int,
        brand_safety_score: int,
        velocity_trend: str = "linear"
    ) -> tuple[int, int, int]:
        """
        Calculate conviction score with dynamic weighting.

        OSS projects get more credit for technical adoption.
        SaaS products must prove commercial viability.

        Args:
            entity_type: "OSS_PROJECT" or "COMMERCIAL_SAAS"
            technical_score: Technical velocity score (0-100)
            commercial_score: Commercial maturity score (0-100)
            brand_safety_score: Brand safety score (0-100)
            velocity_trend: "exponential", "linear", or "declining"

        Returns:
            Tuple of (conviction_score, momentum_bonus, risk_penalty)
        """
        # Dynamic weighting based on entity type
        if entity_type == "OSS_PROJECT":
            base_score = (technical_score * 0.7) + (commercial_score * 0.3)
        else:  # COMMERCIAL_SAAS or UNKNOWN
            base_score = (technical_score * 0.5) + (commercial_score * 0.5)

        # Momentum bonus for viral growth
        momentum_bonus = 0
        if velocity_trend == "exponential":
            momentum_bonus = 10
        elif velocity_trend == "linear" and technical_score > 70:
            momentum_bonus = 5

        # Risk penalty based on brand safety
        risk_penalty = 0
        if brand_safety_score < 50:
            risk_penalty = -20
        elif brand_safety_score < 70:
            risk_penalty = -10
        elif brand_safety_score < 80:
            risk_penalty = -5

        conviction = int(base_score + momentum_bonus + risk_penalty)
        conviction = max(0, min(100, conviction))

        return conviction, momentum_bonus, risk_penalty

    def calculate_conflict(self, technical_score: int, commercial_score: int) -> ConflictIntensity:
        """
        Measure disagreement between Hype-Man and Skeptic.

        High conflict = interesting trend (viral but unproven).

        Args:
            technical_score: From Hype-Man
            commercial_score: From Skeptic

        Returns:
            ConflictIntensity level
        """
        gap = abs(technical_score - commercial_score)

        if gap > 40:
            return ConflictIntensity.HIGH
        elif gap > 20:
            return ConflictIntensity.MEDIUM
        else:
            return ConflictIntensity.LOW

    def determine_recommendation(
        self,
        conviction_score: int,
        conflict: ConflictIntensity,
        risk_penalty: int
    ) -> Recommendation:
        """
        Determine actionable recommendation.

        Args:
            conviction_score: Final conviction score
            conflict: Conflict intensity between agents
            risk_penalty: Risk penalty applied

        Returns:
            Recommendation state
        """
        # High risk entities should be ignored regardless of conviction
        if risk_penalty < -30:
            return Recommendation.IGNORE

        # High conviction = alert
        if conviction_score >= 80:
            return Recommendation.ALERT

        # High conflict = needs investigation
        if conflict == ConflictIntensity.HIGH:
            return Recommendation.INVESTIGATE

        # Medium conviction = monitor
        if conviction_score >= 40:
            return Recommendation.MONITOR

        # Low conviction = ignore
        return Recommendation.IGNORE

    def detect_velocity_trend(self, momentum_signals: List[Dict[str, Any]]) -> str:
        """
        Detect velocity trend from momentum signals.

        Args:
            momentum_signals: List of momentum signals from Hype-Man

        Returns:
            "exponential", "linear", or "declining"
        """
        for signal in momentum_signals:
            trend = signal.get("trend", "").lower()
            velocity = signal.get("velocity", "").lower()

            if "exponential" in trend or "viral" in trend:
                return "exponential"
            if "+8000" in velocity or "+5000" in velocity:
                return "exponential"
            if "declining" in trend or "falling" in trend:
                return "declining"

        return "linear"

    def synthesize(
        self,
        entity_name: str,
        hypeman_output: HypeManOutput,
        skeptic_output: SkepticOutput
    ) -> ArbiterOutput:
        """
        Synthesize Hype-Man and Skeptic outputs into final verdict.

        Args:
            entity_name: Name of the entity
            hypeman_output: Output from Hype-Man agent
            skeptic_output: Output from Skeptic agent

        Returns:
            ArbiterOutput with conviction score and recommendation
        """
        logger.info(f"Arbiter synthesizing: {entity_name}")

        # Extract scores
        technical_score = hypeman_output.technical_velocity_score
        risk_assessment = skeptic_output.risk_assessment
        commercial_score = risk_assessment.get("commercial_maturity_score", 50)
        brand_safety_score = risk_assessment.get("brand_safety_score", 80)
        entity_type = skeptic_output.entity_type

        # Detect velocity trend
        velocity_trend = self.detect_velocity_trend(hypeman_output.momentum_signals)

        # Calculate conviction score
        conviction_score, momentum_bonus, risk_penalty = self.calculate_conviction(
            entity_type=entity_type,
            technical_score=technical_score,
            commercial_score=commercial_score,
            brand_safety_score=brand_safety_score,
            velocity_trend=velocity_trend
        )

        # Calculate conflict intensity
        conflict = self.calculate_conflict(technical_score, commercial_score)

        # Determine recommendation
        recommendation = self.determine_recommendation(
            conviction_score, conflict, risk_penalty
        )

        # Generate synthesis using LLM (optional, can work without)
        synthesis = self._generate_synthesis(
            entity_name, hypeman_output, skeptic_output, conviction_score
        )

        return ArbiterOutput(
            entity=entity_name,
            entity_type=entity_type,
            conviction_score=conviction_score,
            conflict_intensity=conflict.value,
            verdict={
                "bull_thesis": hypeman_output.bull_thesis,
                "bear_thesis": skeptic_output.skeptic_verdict.get("bear_thesis", ""),
                "synthesis": synthesis,
                "key_uncertainty": self._identify_key_uncertainty(
                    hypeman_output, skeptic_output
                )
            },
            signal_breakdown={
                "technical_velocity": technical_score,
                "commercial_maturity": commercial_score,
                "brand_safety": brand_safety_score
            },
            recommendation=recommendation.value,
            momentum_bonus=momentum_bonus,
            risk_penalty=risk_penalty
        )

    def _generate_synthesis(
        self,
        entity_name: str,
        hypeman_output: HypeManOutput,
        skeptic_output: SkepticOutput,
        conviction_score: int
    ) -> str:
        """
        Generate a synthesis statement combining bull and bear cases.

        Args:
            entity_name: Name of the entity
            hypeman_output: Bull case output
            skeptic_output: Bear case output
            conviction_score: Calculated conviction

        Returns:
            Synthesis statement
        """
        entity_type = skeptic_output.entity_type
        technical_score = hypeman_output.technical_velocity_score
        commercial_score = skeptic_output.risk_assessment.get("commercial_maturity_score", 50)

        # Build synthesis based on scores
        if conviction_score >= 80:
            qualifier = "Strong"
        elif conviction_score >= 60:
            qualifier = "Moderate"
        else:
            qualifier = "Weak"

        if entity_type == "OSS_PROJECT":
            type_context = "open-source project"
            path_comment = "Commercial path secondary for OSS."
        else:
            type_context = "commercial product"
            path_comment = "Must demonstrate product-market fit."

        synthesis = (
            f"{qualifier} signal as a {type_context}. "
            f"Technical velocity ({technical_score}/100) "
            f"{'outpaces' if technical_score > commercial_score else 'lags'} "
            f"commercial maturity ({commercial_score}/100). "
            f"{path_comment}"
        )

        return synthesis

    def _identify_key_uncertainty(
        self,
        hypeman_output: HypeManOutput,
        skeptic_output: SkepticOutput
    ) -> str:
        """
        Identify the key uncertainty to watch.

        Args:
            hypeman_output: Bull case output
            skeptic_output: Bear case output

        Returns:
            Key uncertainty statement
        """
        primary_risk = skeptic_output.skeptic_verdict.get("primary_risk_factor", "UNKNOWN")
        entity_type = skeptic_output.entity_type

        uncertainty_map = {
            "VAPORWARE": "Will the product ship in a usable form?",
            "MAINTENANCE_DEBT": "Can the maintainers sustain development velocity?",
            "BURN_RATE": "Will they raise another round before running out of runway?",
            "REGULATORY": "How will regulations impact their market?",
            "COMPETITION": "Can they defend against well-funded competitors?",
            "UNKNOWN_TEAM": "Who is actually behind this project?"
        }

        base_uncertainty = uncertainty_map.get(
            primary_risk,
            "What will drive the next phase of adoption?"
        )

        if entity_type == "OSS_PROJECT":
            return f"{base_uncertainty} Watch for: enterprise adoption, cloud partnerships."
        else:
            return f"{base_uncertainty} Watch for: revenue growth, customer testimonials."


if __name__ == "__main__":
    # Test the Arbiter with mock data
    from agents.hypeman import HypeManOutput
    from agents.skeptic import SkepticOutput

    # Mock Hype-Man output
    hypeman = HypeManOutput(
        entity="DeepSeek",
        bull_thesis="Fastest open-source LLM adoption in history: 50K GitHub stars in 3 weeks.",
        momentum_signals=[
            {"signal": "GitHub stars", "value": 52000, "velocity": "+8000/week"},
            {"signal": "HF downloads", "value": 2400000, "trend": "exponential"}
        ],
        technical_velocity_score=95
    )

    # Mock Skeptic output
    skeptic = SkepticOutput(
        entity_type="OSS_PROJECT",
        risk_assessment={
            "commercial_maturity_score": 40,
            "brand_safety_score": 80
        },
        skeptic_verdict={
            "bear_thesis": "Commercial viability unproven; regulatory cloud over China-origin models.",
            "primary_risk_factor": "REGULATORY",
            "red_flags": [
                {"signal": "No enterprise pricing", "severity": "LOW"},
                {"signal": "Geopolitical risk", "severity": "MEDIUM"}
            ]
        },
        missing_critical_signals=["Enterprise customer logos"],
        confidence_in_assessment="HIGH"
    )

    # Run Arbiter
    arbiter = ArbiterAgent()
    result = arbiter.synthesize("DeepSeek", hypeman, skeptic)

    print(json.dumps(result.to_dict(), indent=2))
