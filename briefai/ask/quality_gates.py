"""
Quality Gates for Ask Mode.

Deterministic rules (no LLM) for validating answer quality:
1. Source diversity - require >= 2 source categories for strong conclusions
2. Measurable checks - require >= 2 verifiable predictions
3. Media-only cap - cap confidence if only media sources used
4. Evidence linking - ensure all claims have evidence

These gates ensure reproducible, auditable answers.
"""

import re
from dataclasses import dataclass
from typing import List, Set, Tuple, Optional, Dict, Any

from briefai.ask.models import (
    AskLogEntry,
    EvidenceLink,
    MeasurableCheck,
    SourceCategory,
)


@dataclass
class QualityAssessment:
    """Result of quality gate evaluation."""
    passed: bool
    confidence_level: str  # "insufficient", "low", "medium", "high"
    review_required: bool
    notes: List[str]
    suggested_next_steps: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "confidence_level": self.confidence_level,
            "review_required": self.review_required,
            "notes": self.notes,
            "suggested_next_steps": self.suggested_next_steps,
        }


class QualityGates:
    """
    Deterministic quality validation for ask responses.
    
    Configuration:
        min_source_categories: Minimum unique source categories required (default 2)
        min_measurable_checks: Minimum measurable predictions required (default 2)
        media_only_confidence_cap: Max confidence if only media sources (default "low")
    """
    
    # Default thresholds
    MIN_SOURCE_CATEGORIES = 2
    MIN_MEASURABLE_CHECKS = 2
    MEDIA_ONLY_CONFIDENCE_CAP = "low"
    
    # Confidence level ordering
    CONFIDENCE_LEVELS = ["insufficient", "low", "medium", "high"]
    
    def __init__(
        self,
        min_source_categories: int = MIN_SOURCE_CATEGORIES,
        min_measurable_checks: int = MIN_MEASURABLE_CHECKS,
        media_only_confidence_cap: str = MEDIA_ONLY_CONFIDENCE_CAP,
    ):
        self.min_source_categories = min_source_categories
        self.min_measurable_checks = min_measurable_checks
        self.media_only_confidence_cap = media_only_confidence_cap
    
    def evaluate(
        self,
        evidence_links: List[EvidenceLink],
        measurable_checks: List[MeasurableCheck],
        has_strong_conclusion: bool = True,
    ) -> QualityAssessment:
        """
        Evaluate quality of an answer.
        
        Args:
            evidence_links: Evidence used in the answer
            measurable_checks: Verifiable predictions extracted
            has_strong_conclusion: Whether answer makes strong claims
        
        Returns:
            QualityAssessment with pass/fail and confidence
        """
        notes = []
        next_steps = []
        review_required = False
        
        # Get unique source categories
        categories = self._get_unique_categories(evidence_links)
        category_count = len(categories)
        
        # Check 1: Source diversity
        source_diversity_ok = category_count >= self.min_source_categories
        
        if not source_diversity_ok and has_strong_conclusion:
            notes.append(
                f"⚠️ Insufficient source diversity: {category_count} categories "
                f"(need {self.min_source_categories})"
            )
            next_steps.append(
                f"Search additional source types: {self._suggest_missing_categories(categories)}"
            )
        
        # Check 2: Measurable checks
        check_count = len(measurable_checks)
        measurable_ok = check_count >= self.min_measurable_checks
        
        if not measurable_ok and has_strong_conclusion:
            notes.append(
                f"⚠️ Insufficient measurable checks: {check_count} "
                f"(need {self.min_measurable_checks})"
            )
            next_steps.append(
                "Add specific predictions: metric + direction + window_days"
            )
        
        # Check 3: Media-only cap
        is_media_only = self._is_media_only(categories)
        
        if is_media_only and has_strong_conclusion:
            notes.append("⚠️ Evidence is media-only; confidence capped")
            review_required = True
            next_steps.append("Find corroborating non-media signals (financial, technical, product)")
        
        # Determine confidence level
        confidence_level = self._calculate_confidence(
            source_diversity_ok=source_diversity_ok,
            measurable_ok=measurable_ok,
            is_media_only=is_media_only,
            category_count=category_count,
            check_count=check_count,
        )
        
        # Overall pass/fail
        # Pass if: (has enough sources OR not making strong claims) AND has some checks
        passed = (source_diversity_ok or not has_strong_conclusion) and check_count > 0
        
        if not passed:
            confidence_level = "insufficient"
            if not next_steps:
                next_steps.append("Gather more evidence before drawing conclusions")
        
        return QualityAssessment(
            passed=passed,
            confidence_level=confidence_level,
            review_required=review_required,
            notes=notes,
            suggested_next_steps=next_steps,
        )
    
    def _get_unique_categories(self, evidence_links: List[EvidenceLink]) -> Set[SourceCategory]:
        """Get unique source categories from evidence."""
        return {
            el.category for el in evidence_links
            if el.category != SourceCategory.UNKNOWN
        }
    
    def _is_media_only(self, categories: Set[SourceCategory]) -> bool:
        """Check if all evidence is from media sources."""
        if not categories:
            return True
        
        non_media = {
            SourceCategory.FINANCIAL,
            SourceCategory.TECHNICAL,
            SourceCategory.PRODUCT,
            SourceCategory.COMPANY,
        }
        
        return not categories.intersection(non_media)
    
    def _suggest_missing_categories(self, have: Set[SourceCategory]) -> str:
        """Suggest categories to add for diversity."""
        all_categories = {
            SourceCategory.FINANCIAL,
            SourceCategory.TECHNICAL,
            SourceCategory.MEDIA,
            SourceCategory.SOCIAL,
            SourceCategory.PRODUCT,
            SourceCategory.COMPANY,
        }
        
        missing = all_categories - have
        if not missing:
            return "N/A"
        
        # Prioritize useful categories
        priority = [
            SourceCategory.FINANCIAL,
            SourceCategory.TECHNICAL,
            SourceCategory.PRODUCT,
        ]
        
        for cat in priority:
            if cat in missing:
                return f"Try {cat.value} signals"
        
        return f"Try {list(missing)[0].value} signals"
    
    def _calculate_confidence(
        self,
        source_diversity_ok: bool,
        measurable_ok: bool,
        is_media_only: bool,
        category_count: int,
        check_count: int,
    ) -> str:
        """Calculate confidence level based on quality factors."""
        
        # Start with base confidence
        if not source_diversity_ok or not measurable_ok:
            base = "low"
        elif category_count >= 3 and check_count >= 3:
            base = "high"
        else:
            base = "medium"
        
        # Apply media-only cap
        if is_media_only:
            base = self._cap_confidence(base, self.media_only_confidence_cap)
        
        return base
    
    def _cap_confidence(self, current: str, cap: str) -> str:
        """Cap confidence at a maximum level."""
        current_idx = self.CONFIDENCE_LEVELS.index(current)
        cap_idx = self.CONFIDENCE_LEVELS.index(cap)
        
        return self.CONFIDENCE_LEVELS[min(current_idx, cap_idx)]
    
    # -------------------------------------------------------------------------
    # Extraction helpers
    # -------------------------------------------------------------------------
    
    @staticmethod
    def extract_measurable_checks_from_answer(answer: str) -> List[MeasurableCheck]:
        """
        Extract measurable predictions from answer text.
        
        This is a simple heuristic extractor. For production use,
        consider using a structured output format from the LLM.
        
        Patterns detected:
        - "X metric will increase/decrease"
        - "expect Y to grow by Z%"
        - "within N days"
        """
        import re
        
        checks = []
        
        # Pattern: "metric will [direction]"
        # e.g., "article_count will increase", "github stars will grow"
        metric_direction = re.findall(
            r"(\w+(?:_\w+)*)\s+(?:will|should|expected to)\s+(increase|decrease|grow|decline|rise|fall|stay|remain)",
            answer.lower()
        )
        
        for metric, direction in metric_direction:
            dir_map = {
                "increase": "up", "grow": "up", "rise": "up",
                "decrease": "down", "decline": "down", "fall": "down",
                "stay": "flat", "remain": "flat",
            }
            checks.append(MeasurableCheck(
                metric=metric,
                entity="",  # Would need NER to extract
                direction=dir_map.get(direction, "up"),
                window_days=14,  # Default
            ))
        
        # Pattern: "within N days/weeks"
        timeframes = re.findall(r"within\s+(\d+)\s+(days?|weeks?)", answer.lower())
        if timeframes and checks:
            # Apply to last check
            num, unit = timeframes[0]
            days = int(num) * (7 if "week" in unit else 1)
            checks[-1].window_days = days
        
        return checks
    
    @staticmethod
    def has_strong_conclusion(answer: str) -> bool:
        """
        Detect if answer makes strong claims requiring evidence.
        
        Strong indicators:
        - "will", "expect", "predict", "forecast"
        - High confidence language
        - Specific predictions
        
        Weak indicators (don't require full evidence):
        - "may", "might", "could", "possibly"
        - Questions
        - Disclaimers
        """
        answer_lower = answer.lower()
        
        # Strong claim patterns
        strong_patterns = [
            r"\bwill\s+(?:likely\s+)?(?:increase|decrease|grow|decline)",
            r"\bexpect\s+",
            r"\bpredict\s+",
            r"\bforecast\s+",
            r"\bconfident\s+that\b",
            r"\bhigh\s+probability\b",
            r"\bstrong\s+signal\b",
        ]
        
        for pattern in strong_patterns:
            if re.search(pattern, answer_lower):
                return True
        
        # Weak claim patterns (don't count as strong)
        weak_patterns = [
            r"\bmight\b",
            r"\bcould\b",
            r"\bpossibly\b",
            r"\bunclear\b",
            r"\binsufficient\s+evidence\b",
            r"\bnot\s+enough\s+data\b",
        ]
        
        has_weak = any(re.search(p, answer_lower) for p in weak_patterns)
        
        return not has_weak


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def validate_answer(
    evidence_links: List[EvidenceLink],
    measurable_checks: List[MeasurableCheck],
    answer: str,
) -> QualityAssessment:
    """
    Convenience function to validate an answer.
    
    Usage:
        result = validate_answer(evidence, checks, answer_text)
        if not result.passed:
            print(f"Quality issues: {result.notes}")
    """
    gates = QualityGates()
    has_strong = gates.has_strong_conclusion(answer)
    return gates.evaluate(evidence_links, measurable_checks, has_strong)


def extract_and_validate(
    evidence_links: List[EvidenceLink],
    answer: str,
) -> Tuple[QualityAssessment, List[MeasurableCheck]]:
    """
    Extract measurable checks from answer and validate.
    
    Returns:
        (QualityAssessment, extracted_checks)
    """
    gates = QualityGates()
    checks = gates.extract_measurable_checks_from_answer(answer)
    has_strong = gates.has_strong_conclusion(answer)
    assessment = gates.evaluate(evidence_links, checks, has_strong)
    return assessment, checks
