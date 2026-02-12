"""
Reflection Self-Check Loop for Ask Mode v1.2.

Validates answers using deterministic rules (no LLM scoring).
Allows ONE repair iteration if validation fails.

Validation Rules:
1. Must include freshness banner
2. Must cite >= 2 independent artifact sources
3. Every Key Takeaway must have >= 1 citation
4. Must include >= 1 "What to Watch" item with timeframe, direction, measurable flag
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Tuple, Any
from enum import Enum

from loguru import logger


# =============================================================================
# VALIDATION RESULT TYPES
# =============================================================================

class ValidationStatus(str, Enum):
    """Validation result status."""
    PASSED = "passed"
    FAILED = "failed"
    PARTIAL = "partial"  # Some rules passed


@dataclass
class RuleResult:
    """Result of a single validation rule."""
    rule_name: str
    passed: bool
    message: str
    details: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict:
        return {
            "rule_name": self.rule_name,
            "passed": self.passed,
            "message": self.message,
            "details": self.details,
        }


@dataclass
class ValidationReport:
    """Complete validation report."""
    status: ValidationStatus
    rules: List[RuleResult] = field(default_factory=list)
    passed_count: int = 0
    failed_count: int = 0
    repair_suggestions: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    
    def to_dict(self) -> Dict:
        return {
            "status": self.status.value,
            "passed_count": self.passed_count,
            "failed_count": self.failed_count,
            "rules": [r.to_dict() for r in self.rules],
            "repair_suggestions": self.repair_suggestions,
            "timestamp": self.timestamp,
        }
    
    @property
    def needs_repair(self) -> bool:
        return self.status == ValidationStatus.FAILED
    
    def get_failed_rules(self) -> List[RuleResult]:
        return [r for r in self.rules if not r.passed]


@dataclass 
class WatchItem:
    """Parsed 'What to Watch' item."""
    text: str
    entity: Optional[str] = None
    metric: Optional[str] = None
    timeframe_days: Optional[int] = None
    expected_direction: Optional[str] = None
    is_measurable: bool = False
    has_citation: bool = False


# =============================================================================
# VALIDATION RULES
# =============================================================================

def check_freshness_banner(answer: str) -> RuleResult:
    """Rule 1: Must include freshness banner."""
    # Look for the banner pattern
    banner_patterns = [
        r"📌\s*Data scope:",
        r"Data scope:\s*local",
        r"Latest available:\s*\d{4}-\d{2}-\d{2}",
        r"Experiment:\s*\w+",
    ]
    
    found_parts = sum(1 for p in banner_patterns if re.search(p, answer))
    
    if found_parts >= 3:
        return RuleResult(
            rule_name="freshness_banner",
            passed=True,
            message="Freshness banner present",
        )
    
    return RuleResult(
        rule_name="freshness_banner",
        passed=False,
        message=f"Freshness banner incomplete or missing (found {found_parts}/4 parts)",
        details={"found_parts": found_parts},
    )


def check_citation_diversity(answer: str, evidence_refs: List[Any]) -> RuleResult:
    """Rule 2: Must cite >= 2 independent artifact sources."""
    # Extract unique source types from citations
    citation_pattern = r"\[evidence:\s*([^\]#]+)"
    citations = re.findall(citation_pattern, answer)
    
    # Also check evidence_refs
    source_types: Set[str] = set()
    
    for citation in citations:
        # Extract source type from path
        if "meta_signals" in citation:
            source_types.add("meta_signals")
        elif "briefs" in citation or "reports" in citation:
            source_types.add("briefs")
        elif "news_signals" in citation:
            source_types.add("news_signals")
        elif "financial_signals" in citation:
            source_types.add("financial_signals")
        elif "daily_snapshot" in citation:
            source_types.add("forecasts")
        elif "hypotheses" in citation:
            source_types.add("hypotheses")
        elif "signals.db" in citation:
            source_types.add("entity_store")
        else:
            source_types.add("other")
    
    # Also count from evidence_refs list
    for ref in evidence_refs:
        if hasattr(ref, 'artifact_path'):
            path = ref.artifact_path
            if "meta_signals" in path:
                source_types.add("meta_signals")
            elif "briefs" in path:
                source_types.add("briefs")
            elif "news" in path:
                source_types.add("news_signals")
    
    if len(source_types) >= 2:
        return RuleResult(
            rule_name="citation_diversity",
            passed=True,
            message=f"Found {len(source_types)} independent sources: {sorted(source_types)}",
            details={"sources": list(source_types)},
        )
    
    return RuleResult(
        rule_name="citation_diversity",
        passed=False,
        message=f"Need >= 2 independent sources, found {len(source_types)}: {sorted(source_types)}",
        details={"sources": list(source_types), "needed": 2},
    )


def check_takeaway_citations(answer: str) -> RuleResult:
    """Rule 3: Every Key Takeaway must have >= 1 citation."""
    # Find the Key Takeaways section
    takeaway_section = None
    
    # Try different section patterns
    patterns = [
        r"##\s*Key\s*Takeaways?\s*\n(.*?)(?=\n##|\Z)",
        r"\*\*Key\s*Takeaways?\*\*\s*\n(.*?)(?=\n\*\*|\n##|\Z)",
        r"Key\s*Takeaways?:\s*\n(.*?)(?=\n\n|\Z)",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, answer, re.IGNORECASE | re.DOTALL)
        if match:
            takeaway_section = match.group(1)
            break
    
    if not takeaway_section:
        # No explicit section, check for bullet points with takeaways
        return RuleResult(
            rule_name="takeaway_citations",
            passed=False,
            message="No 'Key Takeaways' section found",
        )
    
    # Parse bullet points
    bullets = re.findall(r"[-•*]\s*(.+?)(?=\n[-•*]|\n\n|\Z)", takeaway_section, re.DOTALL)
    
    if not bullets:
        return RuleResult(
            rule_name="takeaway_citations",
            passed=False,
            message="No takeaway items found in section",
        )
    
    # Check each bullet for citation
    uncited = []
    for i, bullet in enumerate(bullets):
        if "[evidence:" not in bullet:
            uncited.append(i + 1)
    
    if not uncited:
        return RuleResult(
            rule_name="takeaway_citations",
            passed=True,
            message=f"All {len(bullets)} takeaways have citations",
        )
    
    return RuleResult(
        rule_name="takeaway_citations",
        passed=False,
        message=f"Takeaways {uncited} missing citations ({len(uncited)}/{len(bullets)} uncited)",
        details={"uncited_indices": uncited, "total": len(bullets)},
    )


def parse_watch_items(answer: str) -> List[WatchItem]:
    """Extract and parse 'What to Watch' items."""
    items = []
    
    # Find the Watch section
    watch_patterns = [
        r"##\s*What\s*to\s*Watch\s*\n(.*?)(?=\n##|\Z)",
        r"\*\*What\s*to\s*Watch\*\*\s*\n(.*?)(?=\n\*\*|\n##|\Z)",
        r"What\s*to\s*Watch:\s*\n(.*?)(?=\n\n|\Z)",
        r"PREDICTION[S]?:\s*(.*?)(?=\n\n|\Z)",
    ]
    
    watch_section = None
    for pattern in watch_patterns:
        match = re.search(pattern, answer, re.IGNORECASE | re.DOTALL)
        if match:
            watch_section = match.group(1)
            break
    
    if not watch_section:
        return items
    
    # Parse each bullet
    bullets = re.findall(r"[-•*]\s*(.+?)(?=\n[-•*]|\n\n|\Z)", watch_section, re.DOTALL)
    
    for bullet in bullets:
        item = WatchItem(text=bullet.strip())
        
        # Extract timeframe
        time_match = re.search(r"within\s+(\d+)\s*(days?|weeks?|months?)", bullet, re.I)
        if time_match:
            num = int(time_match.group(1))
            unit = time_match.group(2).lower()
            if "week" in unit:
                num *= 7
            elif "month" in unit:
                num *= 30
            item.timeframe_days = num
        
        # Extract direction
        if re.search(r"\b(increase|up|grow|rise|higher)\b", bullet, re.I):
            item.expected_direction = "up"
        elif re.search(r"\b(decrease|down|decline|fall|lower)\b", bullet, re.I):
            item.expected_direction = "down"
        elif re.search(r"\b(flat|stable|unchanged)\b", bullet, re.I):
            item.expected_direction = "flat"
        
        # Check if measurable (has metric-like terms)
        if re.search(r"\b(count|score|rate|percent|volume|stars|mentions)\b", bullet, re.I):
            item.is_measurable = True
        
        # Check for PREDICTION keyword (makes it measurable)
        if re.search(r"\bPREDICTION\b", bullet):
            item.is_measurable = True
        
        # Check for citation
        item.has_citation = "[evidence:" in bullet
        
        items.append(item)
    
    return items


def check_watch_items(answer: str) -> RuleResult:
    """Rule 4: Must include >= 1 'What to Watch' item with required fields."""
    items = parse_watch_items(answer)
    
    if not items:
        return RuleResult(
            rule_name="watch_items",
            passed=False,
            message="No 'What to Watch' items found",
        )
    
    # Check for at least one complete item
    complete_items = []
    for i, item in enumerate(items):
        issues = []
        if item.timeframe_days is None:
            issues.append("no timeframe")
        if item.expected_direction is None:
            issues.append("no direction")
        if not item.is_measurable:
            issues.append("not measurable")
        
        if not issues:
            complete_items.append(i + 1)
    
    if complete_items:
        return RuleResult(
            rule_name="watch_items",
            passed=True,
            message=f"Found {len(complete_items)} complete watch items",
            details={"complete_indices": complete_items, "total": len(items)},
        )
    
    # Build detailed failure message
    item_details = []
    for i, item in enumerate(items):
        missing = []
        if item.timeframe_days is None:
            missing.append("timeframe_days")
        if item.expected_direction is None:
            missing.append("direction")
        if not item.is_measurable:
            missing.append("measurable")
        item_details.append({"index": i + 1, "missing": missing})
    
    return RuleResult(
        rule_name="watch_items",
        passed=False,
        message=f"No complete watch items (need timeframe + direction + measurable)",
        details={"items": item_details},
    )


# =============================================================================
# MAIN VALIDATOR
# =============================================================================

def validate_answer(
    answer: str,
    evidence_refs: List[Any] = None,
    freshness_info: Any = None,
) -> ValidationReport:
    """
    Validate an answer using deterministic rules.
    
    Args:
        answer: The answer text to validate
        evidence_refs: List of EvidenceRef objects used
        freshness_info: FreshnessSummary object
    
    Returns:
        ValidationReport with pass/fail for each rule
    """
    evidence_refs = evidence_refs or []
    
    report = ValidationReport(status=ValidationStatus.PASSED)
    
    # Run all validation rules
    rules = [
        check_freshness_banner(answer),
        check_citation_diversity(answer, evidence_refs),
        check_takeaway_citations(answer),
        check_watch_items(answer),
    ]
    
    report.rules = rules
    report.passed_count = sum(1 for r in rules if r.passed)
    report.failed_count = sum(1 for r in rules if not r.passed)
    
    # Determine overall status
    if report.failed_count == 0:
        report.status = ValidationStatus.PASSED
    elif report.passed_count > 0:
        report.status = ValidationStatus.PARTIAL
    else:
        report.status = ValidationStatus.FAILED
    
    # Generate repair suggestions
    for rule in rules:
        if not rule.passed:
            suggestion = _generate_repair_suggestion(rule)
            if suggestion:
                report.repair_suggestions.append(suggestion)
    
    logger.debug(f"Validation: {report.status.value} ({report.passed_count}/{len(rules)} passed)")
    
    return report


def _generate_repair_suggestion(rule: RuleResult) -> Optional[str]:
    """Generate a repair suggestion for a failed rule."""
    suggestions = {
        "freshness_banner": "Add freshness banner at top: 📌 Data scope: local artifacts only | Latest available: YYYY-MM-DD | Experiment: ID",
        "citation_diversity": "Search additional artifact types (meta_signals, briefs, news_signals) for diverse evidence",
        "takeaway_citations": "Add [evidence: path#anchor] citation to each Key Takeaway bullet",
        "watch_items": "Add PREDICTION with format: PREDICTION: [entity] [metric] will [direction] within [N] days",
    }
    return suggestions.get(rule.rule_name)


# =============================================================================
# REPAIR HELPERS
# =============================================================================

def get_repair_instructions(report: ValidationReport) -> str:
    """Generate instructions for the repair iteration."""
    if not report.needs_repair:
        return ""
    
    instructions = ["The answer failed validation. Fix these issues:"]
    
    for i, suggestion in enumerate(report.repair_suggestions, 1):
        instructions.append(f"{i}. {suggestion}")
    
    instructions.append("\nYou may call tools again to gather missing evidence.")
    instructions.append("This is your ONLY repair attempt.")
    
    return "\n".join(instructions)


def create_partial_confidence_banner(report: ValidationReport) -> str:
    """Create a warning banner for answers that couldn't be fully repaired."""
    failed_rules = [r.rule_name for r in report.get_failed_rules()]
    
    return (
        f"⚠️ **Partial Confidence** - This answer failed {len(failed_rules)} validation rules: "
        f"{', '.join(failed_rules)}. Interpret with caution."
    )
