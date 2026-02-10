"""
Evidence Ledger v1.0 - Auditable Belief Updates.

This is the REAL killer feature.

Instead of "nvidia repo activity +42%", show:
- Which repo?
- Compared to when?
- Across how many contributors?
- Is it seasonal noise?

Every belief update must be traceable to empirical evidence.

This crosses briefAI from "AI thinks something" to 
"Here is the empirical basis for the belief update."
"""

import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from collections import defaultdict

from loguru import logger


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class EvidenceDetail:
    """Detailed breakdown of a single evidence observation."""
    
    # What was measured
    metric_name: str
    metric_type: str  # technical, financial, labor-market, media, regulatory
    
    # The change
    baseline_value: float
    current_value: float
    percent_change: float
    
    # Context
    source: str
    entities: List[str]
    
    # Reliability
    reliability_category: str
    reliability_score: float
    
    # Supporting details (the audit trail)
    details: Dict[str, Any] = field(default_factory=dict)
    
    # Direction
    direction: str = "support"  # support, contradict, neutral
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @property
    def direction_symbol(self) -> str:
        if self.direction == "support":
            return "+"
        elif self.direction == "contradict":
            return "-"
        else:
            return "~"
    
    def format_summary(self) -> str:
        """Format as single-line summary."""
        pct = f"{self.percent_change:+.0%}" if self.percent_change else "changed"
        return f"{self.direction_symbol} {self.metric_name}: {self.baseline_value:.0f} → {self.current_value:.0f} ({pct})"
    
    def format_detailed(self) -> List[str]:
        """Format as multi-line detailed breakdown."""
        lines = []
        
        # Header
        direction_word = {
            "support": "Supporting",
            "contradict": "Contradicting", 
            "neutral": "Neutral"
        }.get(self.direction, "")
        
        lines.append(f"{self.direction_symbol} **{self.metric_name}** ({direction_word})")
        
        # Core metrics
        pct = f"{self.percent_change:+.0%}" if self.percent_change else "changed"
        lines.append(f"  - Value: {self.baseline_value:.0f} → {self.current_value:.0f} ({pct})")
        
        # Details breakdown
        for key, value in self.details.items():
            # Format key nicely
            key_formatted = key.replace("_", " ")
            lines.append(f"  - {key_formatted}: {value}")
        
        # Reliability
        lines.append(f"  - Reliability: {self.reliability_category} ({self.reliability_score:.2f})")
        
        return lines


@dataclass
class BeliefLedger:
    """Complete evidence ledger for a belief update."""
    
    hypothesis_id: str
    hypothesis_title: str
    concept_name: str
    
    # Confidence change
    prior_confidence: float
    posterior_confidence: float
    
    # Evidence breakdown
    supporting_evidence: List[EvidenceDetail]
    contradicting_evidence: List[EvidenceDetail]
    neutral_evidence: List[EvidenceDetail]
    
    # Timestamps
    observation_period_start: str
    observation_period_end: str
    updated_at: str = ""
    
    def __post_init__(self):
        if not self.updated_at:
            self.updated_at = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "hypothesis_title": self.hypothesis_title,
            "concept_name": self.concept_name,
            "prior_confidence": self.prior_confidence,
            "posterior_confidence": self.posterior_confidence,
            "confidence_change": self.confidence_change,
            "supporting_evidence": [e.to_dict() for e in self.supporting_evidence],
            "contradicting_evidence": [e.to_dict() for e in self.contradicting_evidence],
            "neutral_evidence": [e.to_dict() for e in self.neutral_evidence],
            "observation_period_start": self.observation_period_start,
            "observation_period_end": self.observation_period_end,
            "updated_at": self.updated_at,
        }
    
    @property
    def confidence_change(self) -> float:
        return self.posterior_confidence - self.prior_confidence
    
    @property
    def total_evidence_count(self) -> int:
        return len(self.supporting_evidence) + len(self.contradicting_evidence) + len(self.neutral_evidence)
    
    def format_markdown(self) -> str:
        """Format the ledger as markdown for the brief."""
        lines = []
        
        # Header
        lines.append(f"### {self.hypothesis_title}")
        lines.append(f"*{self.concept_name}*")
        lines.append("")
        
        # Confidence change - THE MONEY LINE
        if self.confidence_change > 0:
            arrow = "↑"
        elif self.confidence_change < 0:
            arrow = "↓"
        else:
            arrow = "→"
        
        lines.append(f"**Confidence: {self.prior_confidence:.0%} {arrow} {self.posterior_confidence:.0%}** ({self.confidence_change:+.0%})")
        lines.append("")
        
        # Evidence Ledger header
        lines.append("**Evidence Added Today:**")
        lines.append("")
        
        # Supporting evidence (detailed)
        for evidence in self.supporting_evidence:
            for line in evidence.format_detailed():
                lines.append(line)
            lines.append("")
        
        # Contradicting evidence (detailed)
        for evidence in self.contradicting_evidence:
            for line in evidence.format_detailed():
                lines.append(line)
            lines.append("")
        
        # Neutral evidence (just summary)
        if self.neutral_evidence:
            lines.append("*Neutral observations (within noise band):*")
            for evidence in self.neutral_evidence:
                lines.append(f"  {evidence.format_summary()}")
            lines.append("")
        
        # Observation period
        lines.append(f"*Observation period: {self.observation_period_start} to {self.observation_period_end}*")
        lines.append("")
        
        return "\n".join(lines)


# =============================================================================
# EVIDENCE DETAIL BUILDER
# =============================================================================

class EvidenceDetailBuilder:
    """Builds detailed evidence breakdowns from raw evidence."""
    
    # Reliability categories and scores
    RELIABILITY_SCORES = {
        "sec_filing": ("regulatory", 0.98),
        "earnings_call": ("financial", 0.95),
        "sec": ("regulatory", 0.95),
        "financial": ("financial", 0.90),
        "github": ("technical", 0.85),
        "package": ("technical", 0.80),
        "jobs": ("labor-market", 0.75),
        "news": ("media", 0.50),
        "social": ("social", 0.35),
        "reddit": ("social", 0.30),
        "twitter": ("social", 0.25),
    }
    
    # Metric type mappings
    METRIC_TYPES = {
        "filing_mentions": "regulatory",
        "earnings_mentions": "financial",
        "contract_count": "regulatory",
        "arr": "financial",
        "revenue": "financial",
        "repo_activity": "technical",
        "repo_stars": "technical",
        "repo_forks": "technical",
        "sdk_release": "technical",
        "package_downloads": "technical",
        "job_postings_count": "labor-market",
        "hiring_activity": "labor-market",
        "article_count": "media",
        "headline_mentions": "media",
        "keyword_frequency": "media",
        "discussion_volume": "social",
        "sentiment_score": "social",
    }
    
    def build_detail(
        self,
        evidence: Dict[str, Any],
        additional_context: Dict[str, Any] = None,
    ) -> EvidenceDetail:
        """
        Build an EvidenceDetail from raw evidence data.
        
        Args:
            evidence: Raw evidence dict (from evidence_engine)
            additional_context: Optional additional context for details
        
        Returns:
            EvidenceDetail with full breakdown
        """
        metric = evidence.get("canonical_metric", "unknown")
        source = evidence.get("source", self._infer_source(metric))
        
        # Get reliability
        reliability_category, reliability_score = self.RELIABILITY_SCORES.get(
            source, ("unknown", 0.50)
        )
        
        # Get metric type
        metric_type = self.METRIC_TYPES.get(metric, "general")
        
        # Build details dict
        details = self._build_details(evidence, additional_context)
        
        # Build friendly metric name
        metric_name = self._format_metric_name(metric, evidence)
        
        return EvidenceDetail(
            metric_name=metric_name,
            metric_type=metric_type,
            baseline_value=evidence.get("baseline_value") or evidence.get("observed_value_start", 0),
            current_value=evidence.get("current_value") or evidence.get("observed_value_end", 0),
            percent_change=evidence.get("percent_change", 0),
            source=source,
            entities=self._extract_entities(evidence),
            reliability_category=reliability_category,
            reliability_score=reliability_score,
            details=details,
            direction=evidence.get("direction", "neutral"),
        )
    
    def _infer_source(self, metric: str) -> str:
        """Infer source from metric name."""
        if metric in ["filing_mentions", "contract_count", "earnings_mentions"]:
            return "sec"
        elif metric in ["repo_activity", "repo_stars", "repo_forks", "sdk_release"]:
            return "github"
        elif metric in ["job_postings_count", "hiring_activity"]:
            return "jobs"
        elif metric in ["article_count", "headline_mentions", "keyword_frequency"]:
            return "news"
        elif metric in ["discussion_volume", "sentiment_score"]:
            return "social"
        return "unknown"
    
    def _format_metric_name(self, metric: str, evidence: Dict) -> str:
        """Format metric name for display."""
        entity = evidence.get("entity", "")
        category = evidence.get("category", "")
        
        # Build descriptive name
        metric_readable = metric.replace("_", " ").title()
        
        if entity and category:
            return f"{metric_readable} ({entity}, {category})"
        elif entity:
            return f"{metric_readable} ({entity})"
        elif category:
            return f"{metric_readable} ({category})"
        else:
            return metric_readable
    
    def _extract_entities(self, evidence: Dict) -> List[str]:
        """Extract entities from evidence."""
        entities = []
        
        if evidence.get("entity"):
            entities.append(evidence["entity"])
        
        # Check observable_query for more entities
        obs_query = evidence.get("observable_query", {})
        query_terms = obs_query.get("query_terms", {})
        
        if query_terms.get("entities"):
            for e in query_terms["entities"]:
                if e not in entities:
                    entities.append(e)
        
        return entities
    
    def _build_details(
        self,
        evidence: Dict,
        additional_context: Dict = None,
    ) -> Dict[str, Any]:
        """Build details breakdown for the evidence."""
        details = {}
        
        # Add any observable query details
        obs_query = evidence.get("observable_query", {})
        if obs_query.get("query"):
            details["query"] = obs_query["query"]
        if obs_query.get("window_days"):
            details["observation_window"] = f"{obs_query['window_days']} days"
        
        # Add effect size if significant
        effect_size = evidence.get("effect_size", 0)
        if effect_size > 0.2:
            details["effect_magnitude"] = "large" if effect_size > 0.4 else "moderate"
        
        # Add weight info
        weight = evidence.get("weight", 0)
        if weight > 0:
            details["evidence_weight"] = f"{weight:.2f}"
        
        # Add any notes
        notes = evidence.get("notes", "")
        if notes and ";" in notes:
            for note in notes.split(";"):
                if "=" in note:
                    key, value = note.split("=", 1)
                    details[key.strip()] = value.strip()
        
        # Merge additional context
        if additional_context:
            details.update(additional_context)
        
        return details


# =============================================================================
# LEDGER GENERATOR
# =============================================================================

class LedgerGenerator:
    """Generates evidence ledgers from evidence and belief data."""
    
    def __init__(self):
        self.detail_builder = EvidenceDetailBuilder()
    
    def generate_ledger(
        self,
        hypothesis_id: str,
        hypothesis_title: str,
        concept_name: str,
        prior_confidence: float,
        posterior_confidence: float,
        evidence_list: List[Dict[str, Any]],
        observation_start: str,
        observation_end: str,
    ) -> BeliefLedger:
        """
        Generate a complete belief ledger.
        
        Args:
            hypothesis_id: ID of the hypothesis
            hypothesis_title: Title of the hypothesis
            concept_name: Name of the parent concept
            prior_confidence: Prior confidence
            posterior_confidence: Posterior confidence
            evidence_list: List of evidence dicts
            observation_start: Start of observation period
            observation_end: End of observation period
        
        Returns:
            BeliefLedger with full breakdown
        """
        supporting = []
        contradicting = []
        neutral = []
        
        for evidence in evidence_list:
            detail = self.detail_builder.build_detail(evidence)
            
            if detail.direction == "support":
                supporting.append(detail)
            elif detail.direction == "contradict":
                contradicting.append(detail)
            else:
                neutral.append(detail)
        
        # Sort by reliability score (highest first)
        supporting.sort(key=lambda x: x.reliability_score, reverse=True)
        contradicting.sort(key=lambda x: x.reliability_score, reverse=True)
        
        return BeliefLedger(
            hypothesis_id=hypothesis_id,
            hypothesis_title=hypothesis_title,
            concept_name=concept_name,
            prior_confidence=prior_confidence,
            posterior_confidence=posterior_confidence,
            supporting_evidence=supporting,
            contradicting_evidence=contradicting,
            neutral_evidence=neutral,
            observation_period_start=observation_start,
            observation_period_end=observation_end,
        )
    
    def generate_ledgers_from_data(
        self,
        evidence_list: List[Dict],
        beliefs: Dict[str, Dict],
        hypotheses: Dict = None,
        date: str = None,
    ) -> List[BeliefLedger]:
        """
        Generate all ledgers from evidence and belief data.
        
        Args:
            evidence_list: List of evidence dicts
            beliefs: Dict of belief states by hypothesis_id
            hypotheses: Optional hypotheses data for titles
            date: Date for observation period
        
        Returns:
            List of BeliefLedger objects
        """
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        
        # Build hypothesis lookup
        hyp_titles = {}
        hyp_concepts = {}
        if hypotheses:
            for bundle in hypotheses.get("bundles", []):
                concept = bundle.get("concept_name", "")
                for hyp in bundle.get("hypotheses", []):
                    hyp_id = hyp.get("hypothesis_id", "")
                    hyp_titles[hyp_id] = hyp.get("title", "Untitled")
                    hyp_concepts[hyp_id] = concept
        
        # Group evidence by hypothesis
        evidence_by_hyp: Dict[str, List[Dict]] = defaultdict(list)
        for e in evidence_list:
            hyp_id = e.get("hypothesis_id", "")
            evidence_by_hyp[hyp_id].append(e)
        
        # Generate ledgers
        ledgers = []
        
        for hyp_id, ev_list in evidence_by_hyp.items():
            belief = beliefs.get(hyp_id, {})
            
            prior = belief.get("prior_confidence", 0.5)
            posterior = belief.get("posterior_confidence", prior)
            
            # Skip if no significant change
            if abs(posterior - prior) < 0.01:
                continue
            
            ledger = self.generate_ledger(
                hypothesis_id=hyp_id,
                hypothesis_title=hyp_titles.get(hyp_id, hyp_id),
                concept_name=hyp_concepts.get(hyp_id, ""),
                prior_confidence=prior,
                posterior_confidence=posterior,
                evidence_list=ev_list,
                observation_start=date,
                observation_end=date,
            )
            
            ledgers.append(ledger)
        
        # Sort by absolute confidence change
        ledgers.sort(key=lambda x: abs(x.confidence_change), reverse=True)
        
        return ledgers


# =============================================================================
# BRIEF SECTION GENERATOR
# =============================================================================

def generate_evidence_ledger_section(
    ledgers: List[BeliefLedger],
    max_ledgers: int = 10,
) -> str:
    """
    Generate the Evidence Ledger section for the analyst brief.
    
    Args:
        ledgers: List of BeliefLedger objects
        max_ledgers: Maximum ledgers to show
    
    Returns:
        Formatted markdown section
    """
    lines = []
    lines.append("## 4. What Changed Today (Evidence Ledger)")
    lines.append("")
    lines.append("*Detailed audit trail of belief updates with empirical evidence.*")
    lines.append("")
    
    if not ledgers:
        lines.append("*No significant belief changes today.*")
        lines.append("")
        return "\n".join(lines)
    
    for ledger in ledgers[:max_ledgers]:
        lines.append(ledger.format_markdown())
        lines.append("---")
        lines.append("")
    
    return "\n".join(lines)


# =============================================================================
# TESTS
# =============================================================================

def _test_evidence_detail():
    """Test EvidenceDetail formatting."""
    detail = EvidenceDetail(
        metric_name="GitHub Org Activity (openai, anthropic)",
        metric_type="technical",
        baseline_value=312,
        current_value=441,
        percent_change=0.41,
        source="github",
        entities=["openai", "anthropic"],
        reliability_category="technical",
        reliability_score=0.85,
        details={
            "commits": "312 -> 441",
            "unique_contributors": "84 -> 129",
            "repos_affected": "17",
        },
        direction="support",
    )
    
    # Test summary
    summary = detail.format_summary()
    assert "+" in summary
    assert "441" in summary
    
    # Test detailed
    detailed = detail.format_detailed()
    assert len(detailed) > 3
    assert any("commits" in line for line in detailed)
    
    print("[PASS] _test_evidence_detail")


def _test_ledger_generation():
    """Test ledger generation."""
    generator = LedgerGenerator()
    
    evidence = [
        {
            "hypothesis_id": "hyp_001",
            "canonical_metric": "repo_activity",
            "entity": "nvidia",
            "category": "technical",
            "direction": "support",
            "baseline_value": 100,
            "current_value": 142,
            "percent_change": 0.42,
            "weight": 0.85,
        },
        {
            "hypothesis_id": "hyp_001",
            "canonical_metric": "article_count",
            "entity": "nvidia",
            "category": "media",
            "direction": "contradict",
            "baseline_value": 80,
            "current_value": 62,
            "percent_change": -0.225,
            "weight": 0.45,
        },
    ]
    
    ledger = generator.generate_ledger(
        hypothesis_id="hyp_001",
        hypothesis_title="Infrastructure Scaling",
        concept_name="NVIDIA Compute Demand",
        prior_confidence=0.75,
        posterior_confidence=0.88,
        evidence_list=evidence,
        observation_start="2026-02-10",
        observation_end="2026-02-10",
    )
    
    assert ledger.confidence_change == 0.13
    assert len(ledger.supporting_evidence) == 1
    assert len(ledger.contradicting_evidence) == 1
    
    # Test markdown output
    md = ledger.format_markdown()
    assert "75%" in md
    assert "88%" in md
    assert "Infrastructure Scaling" in md
    
    print("[PASS] _test_ledger_generation")


def run_tests():
    """Run all tests."""
    print("\n=== EVIDENCE LEDGER TESTS ===\n")
    
    _test_evidence_detail()
    _test_ledger_generation()
    
    print("\n=== ALL TESTS PASSED ===")


if __name__ == "__main__":
    run_tests()
