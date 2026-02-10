"""
Base Scorer Module

Abstract base class for all signal scorers.
Provides common scoring utilities and interface definition.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from datetime import datetime
import math


class BaseScorer(ABC):
    """
    Abstract base class for per-category signal scorers.

    Each scorer normalizes raw data from its category to a 0-100 scale.
    Different categories use different normalization methods:
    - Log scale for power-law distributions (stars, downloads, funding)
    - Bracket-based for rankings (CB Rank)
    - Linear for bounded metrics
    """

    @property
    @abstractmethod
    def category(self) -> str:
        """Return the signal category this scorer handles."""
        pass

    @abstractmethod
    def score(self, raw_data: Dict[str, Any]) -> float:
        """
        Calculate normalized score (0-100) from raw data.

        Args:
            raw_data: Source-specific raw metrics

        Returns:
            Normalized score 0-100
        """
        pass

    @abstractmethod
    def get_confidence(self, raw_data: Dict[str, Any]) -> float:
        """
        Calculate confidence (0-1) for this observation.

        Args:
            raw_data: Source-specific raw metrics

        Returns:
            Confidence score 0-1
        """
        pass

    def get_component_scores(self, raw_data: Dict[str, Any]) -> Dict[str, float]:
        """
        Get breakdown of component scores for transparency.

        Args:
            raw_data: Source-specific raw metrics

        Returns:
            Dictionary of component -> score
        """
        return {}

    # =========================================================================
    # Common Scoring Utilities
    # =========================================================================

    @staticmethod
    def log_scale(value: float, max_log: float = 6.0, base: float = 10.0) -> float:
        """
        Apply log-scale normalization for power-law distributions.

        Formula: min(100, log_base(value + 1) / max_log * 100)

        Args:
            value: Raw value (e.g., stars, downloads)
            max_log: Log value that maps to 100 (e.g., 6 means 1M = 100)
            base: Logarithm base

        Returns:
            Normalized score 0-100

        Examples:
            log_scale(1000, 6) ≈ 50    (1K stars)
            log_scale(10000, 6) ≈ 67   (10K stars)
            log_scale(100000, 6) ≈ 83  (100K stars)
            log_scale(1000000, 6) = 100 (1M stars)
        """
        if value <= 0:
            return 0.0

        log_value = math.log(value + 1, base)
        score = min(100.0, (log_value / max_log) * 100)
        return round(score, 2)

    @staticmethod
    def bracket_scale(value: float, brackets: List[tuple]) -> float:
        """
        Apply bracket-based scoring for ranked data.

        Args:
            value: Raw value (e.g., rank)
            brackets: List of (threshold, score) tuples, sorted by threshold ascending
                     Values <= threshold get that score

        Returns:
            Normalized score 0-100

        Example:
            brackets = [(100, 100), (1000, 80), (10000, 60), (100000, 40)]
            bracket_scale(50, brackets) = 100   (rank 50 <= 100)
            bracket_scale(500, brackets) = 80   (rank 500 <= 1000)
        """
        for threshold, score in brackets:
            if value <= threshold:
                return float(score)
        return brackets[-1][1] if brackets else 0.0

    @staticmethod
    def linear_scale(value: float, min_val: float, max_val: float) -> float:
        """
        Apply linear scaling with min/max bounds.

        Args:
            value: Raw value
            min_val: Value that maps to 0
            max_val: Value that maps to 100

        Returns:
            Normalized score 0-100
        """
        if max_val == min_val:
            return 50.0
        score = ((value - min_val) / (max_val - min_val)) * 100
        return round(max(0.0, min(100.0, score)), 2)

    @staticmethod
    def recency_decay(timestamp: Optional[datetime], half_life_days: int = 30) -> float:
        """
        Calculate recency factor with exponential decay.

        Args:
            timestamp: When the data was observed
            half_life_days: Days until score halves

        Returns:
            Decay factor 0-1 (1.0 = today, 0.5 = half_life_days ago)
        """
        if timestamp is None:
            return 0.5  # Default to half weight for unknown dates

        now = datetime.utcnow()
        age_days = (now - timestamp).days

        if age_days < 0:
            return 1.0  # Future dates treated as current

        # Exponential decay: factor = 0.5^(age/half_life)
        decay = 0.5 ** (age_days / half_life_days)
        return round(decay, 3)

    @staticmethod
    def weighted_average(components: Dict[str, tuple]) -> float:
        """
        Calculate weighted average of component scores.

        Args:
            components: Dict of name -> (score, weight)

        Returns:
            Weighted average score
        """
        total_weight = sum(weight for _, weight in components.values())
        if total_weight == 0:
            return 0.0

        weighted_sum = sum(score * weight for score, weight in components.values())
        return round(weighted_sum / total_weight, 2)

    @staticmethod
    def cap_score(score: float, min_val: float = 0.0, max_val: float = 100.0) -> float:
        """Cap score to valid range."""
        return max(min_val, min(max_val, score))
