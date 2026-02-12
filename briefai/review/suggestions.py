"""
Suggestions Generation Engine

Generates actionable but non-automatic suggestions for system improvement.
All suggestions require manual review before application.

v1.1: New module for actionable suggestions output.

NO LLM USAGE. All suggestions are rule-based from pattern data.
"""

import json
import hashlib
from datetime import date
from pathlib import Path
from typing import Optional

from .models import (
    LearningInsight,
    Lesson,
    ReviewMetrics,
    Suggestion,
)


def generate_suggestion_id(target: str, pattern: str, review_date: date) -> str:
    """Generate a deterministic suggestion ID."""
    raw = f"{target}:{pattern}:{review_date.isoformat()}"
    return f"sug_{hashlib.sha256(raw.encode()).hexdigest()[:12]}"


def generate_confidence_suggestions(
    metrics: ReviewMetrics,
    insights: list[LearningInsight],
    review_date: date,
) -> list[Suggestion]:
    """
    Generate suggestions for confidence score adjustments.
    
    Triggered by calibration errors or overconfidence patterns.
    """
    suggestions = []
    
    # High calibration error suggests global confidence adjustment needed
    if metrics.calibration_error > 0.15:
        suggestions.append(Suggestion(
            suggestion_id=generate_suggestion_id("confidence_cap", "global", review_date),
            target="confidence_cap",
            rationale=f"Calibration error of {metrics.calibration_error:.2f} indicates systematic overconfidence. Pattern: calibration_error > 0.15",
            proposed_change={
                "action": "reduce_confidence_multiplier",
                "factor": 0.85,  # Reduce all confidences by 15%
                "scope": "global",
            },
            safety="manual_review_required",
            source_pattern="calibration_error",
            source_category="metrics",
            sample_size=metrics.total_predictions,
            success_rate=metrics.overall_accuracy,
        ))
    
    # Check for overconfident calibration buckets
    for insight in insights:
        if insight.category == "calibration" and "overconfident" in insight.interpretation.lower():
            if insight.sample_size >= 5:  # Require sufficient data
                suggestions.append(Suggestion(
                    suggestion_id=generate_suggestion_id("confidence_cap", insight.pattern, review_date),
                    target="confidence_cap",
                    rationale=f"Pattern '{insight.pattern}' shows overconfidence: {insight.interpretation}. n={insight.sample_size}, actual={insight.success_rate:.0%}",
                    proposed_change={
                        "action": "cap_confidence_at_bucket",
                        "bucket": insight.pattern,
                        "max_confidence": insight.success_rate + 0.1,  # Cap slightly above actual
                    },
                    safety="manual_review_required",
                    source_pattern=insight.pattern,
                    source_category=insight.category,
                    sample_size=insight.sample_size,
                    success_rate=insight.success_rate,
                ))
    
    return suggestions


def generate_mechanism_suggestions(
    insights: list[LearningInsight],
    review_date: date,
) -> list[Suggestion]:
    """
    Generate suggestions for mechanism weight adjustments.
    
    Triggered by consistently underperforming or overperforming mechanisms.
    """
    suggestions = []
    
    mechanism_insights = [i for i in insights if i.category == "mechanism"]
    
    for insight in mechanism_insights:
        if insight.sample_size < 5:  # Require sufficient data
            continue
        
        # Underperforming mechanism
        if insight.success_rate < 0.35:
            suggestions.append(Suggestion(
                suggestion_id=generate_suggestion_id("mechanism_weight", insight.pattern, review_date),
                target="mechanism_weight",
                rationale=f"Mechanism '{insight.pattern}' has {insight.success_rate:.0%} accuracy (n={insight.sample_size}). Consider reducing its weight in hypothesis generation.",
                proposed_change={
                    "action": "reduce_mechanism_weight",
                    "mechanism": insight.pattern,
                    "current_weight": 1.0,
                    "suggested_weight": 0.5,
                },
                safety="manual_review_required",
                source_pattern=insight.pattern,
                source_category=insight.category,
                sample_size=insight.sample_size,
                success_rate=insight.success_rate,
            ))
        
        # Overperforming mechanism
        elif insight.success_rate > 0.75:
            suggestions.append(Suggestion(
                suggestion_id=generate_suggestion_id("mechanism_weight", insight.pattern, review_date),
                target="mechanism_weight",
                rationale=f"Mechanism '{insight.pattern}' has {insight.success_rate:.0%} accuracy (n={insight.sample_size}). Consider increasing its weight.",
                proposed_change={
                    "action": "increase_mechanism_weight",
                    "mechanism": insight.pattern,
                    "current_weight": 1.0,
                    "suggested_weight": 1.5,
                },
                safety="manual_review_required",
                source_pattern=insight.pattern,
                source_category=insight.category,
                sample_size=insight.sample_size,
                success_rate=insight.success_rate,
            ))
    
    return suggestions


def generate_category_suggestions(
    insights: list[LearningInsight],
    review_date: date,
) -> list[Suggestion]:
    """
    Generate suggestions for signal category thresholds.
    
    Triggered by category-specific accuracy patterns.
    """
    suggestions = []
    
    category_insights = [i for i in insights if i.category == "signal_category"]
    
    for insight in category_insights:
        if insight.sample_size < 5:
            continue
        
        # Media-only predictions often need extra validation
        if insight.pattern == "media" and insight.success_rate < 0.45:
            suggestions.append(Suggestion(
                suggestion_id=generate_suggestion_id("media_only_threshold", insight.pattern, review_date),
                target="media_only_threshold",
                rationale=f"Media-only signals have {insight.success_rate:.0%} accuracy (n={insight.sample_size}). Consider requiring multi-source validation.",
                proposed_change={
                    "action": "require_multi_source",
                    "category": "media",
                    "min_sources": 2,
                },
                safety="manual_review_required",
                source_pattern=insight.pattern,
                source_category=insight.category,
                sample_size=insight.sample_size,
                success_rate=insight.success_rate,
            ))
    
    return suggestions


def generate_timeframe_suggestions(
    insights: list[LearningInsight],
    review_date: date,
) -> list[Suggestion]:
    """
    Generate suggestions for check_date policy adjustments.
    
    Triggered by timeframe-specific accuracy patterns.
    """
    suggestions = []
    
    timeframe_insights = [i for i in insights if i.category == "timeframe"]
    
    # Check if long-term predictions are unreliable
    long_term = next((i for i in timeframe_insights if i.pattern == "long_term" and i.sample_size >= 5), None)
    if long_term and long_term.success_rate < 0.4:
        suggestions.append(Suggestion(
            suggestion_id=generate_suggestion_id("check_date_policy", "long_term", review_date),
            target="check_date_policy",
            rationale=f"Long-term predictions (>14 days) have {long_term.success_rate:.0%} accuracy (n={long_term.sample_size}). Consider shortening default timeframes.",
            proposed_change={
                "action": "reduce_default_timeframe",
                "current_days": 14,
                "suggested_days": 10,
            },
            safety="manual_review_required",
            source_pattern=long_term.pattern,
            source_category=long_term.category,
            sample_size=long_term.sample_size,
            success_rate=long_term.success_rate,
        ))
    
    # Check if short-term is more reliable
    short_term = next((i for i in timeframe_insights if i.pattern == "short_term" and i.sample_size >= 5), None)
    medium_term = next((i for i in timeframe_insights if i.pattern == "medium_term" and i.sample_size >= 5), None)
    
    if short_term and medium_term:
        if short_term.success_rate > medium_term.success_rate + 0.2:
            suggestions.append(Suggestion(
                suggestion_id=generate_suggestion_id("check_date_policy", "prefer_short", review_date),
                target="check_date_policy",
                rationale=f"Short-term ({short_term.success_rate:.0%}) significantly outperforms medium-term ({medium_term.success_rate:.0%}). Consider defaulting to shorter horizons.",
                proposed_change={
                    "action": "prefer_shorter_timeframes",
                    "short_term_accuracy": short_term.success_rate,
                    "medium_term_accuracy": medium_term.success_rate,
                },
                safety="manual_review_required",
                source_pattern="short_term_vs_medium",
                source_category="timeframe",
                sample_size=short_term.sample_size + medium_term.sample_size,
                success_rate=short_term.success_rate,
            ))
    
    return suggestions


def generate_unclear_suggestions(
    metrics: ReviewMetrics,
    review_date: date,
) -> list[Suggestion]:
    """
    Generate suggestions based on unclear outcome patterns.
    
    High unclear rates indicate systemic data or methodology issues.
    """
    suggestions = []
    
    if metrics.unclear_rate > 0.5:
        # More than half are unclear - significant issue
        suggestions.append(Suggestion(
            suggestion_id=generate_suggestion_id("data_coverage", "unclear_rate", review_date),
            target="data_coverage",
            rationale=f"Unclear rate of {metrics.unclear_rate:.0%} indicates insufficient signal data coverage. Breakdown: {metrics.unclear_breakdown}",
            proposed_change={
                "action": "expand_signal_sources",
                "unclear_rate": metrics.unclear_rate,
                "breakdown": metrics.unclear_breakdown,
            },
            safety="manual_review_required",
            source_pattern="unclear_rate",
            source_category="metrics",
            sample_size=metrics.total_predictions,
            success_rate=metrics.overall_accuracy,
        ))
    
    # Check specific unclear reasons
    if metrics.unclear_breakdown:
        data_missing = metrics.unclear_breakdown.get("data_missing", 0)
        total_unclear = metrics.total_unclear
        
        if total_unclear > 0 and data_missing / total_unclear > 0.6:
            suggestions.append(Suggestion(
                suggestion_id=generate_suggestion_id("signal_retention", "data_missing", review_date),
                target="signal_retention",
                rationale=f"{data_missing}/{total_unclear} unclear outcomes are due to missing data. Consider longer signal retention or broader entity matching.",
                proposed_change={
                    "action": "extend_signal_retention",
                    "current_days": 7,
                    "suggested_days": 14,
                },
                safety="manual_review_required",
                source_pattern="data_missing",
                source_category="unclear_reason",
                sample_size=total_unclear,
                success_rate=0.0,
            ))
    
    return suggestions


def generate_suggestions(
    metrics: ReviewMetrics,
    insights: list[LearningInsight],
    lessons: list[Lesson],
    review_date: date,
) -> list[Suggestion]:
    """
    Generate all suggestions from review results.
    
    Main entry point for suggestion generation.
    
    Args:
        metrics: Computed review metrics
        insights: Discovered patterns
        lessons: Synthesized lessons
        review_date: Date of the review
    
    Returns:
        List of Suggestion objects (never auto-applied)
    """
    all_suggestions = []
    
    # Generate from different sources
    all_suggestions.extend(generate_confidence_suggestions(metrics, insights, review_date))
    all_suggestions.extend(generate_mechanism_suggestions(insights, review_date))
    all_suggestions.extend(generate_category_suggestions(insights, review_date))
    all_suggestions.extend(generate_timeframe_suggestions(insights, review_date))
    all_suggestions.extend(generate_unclear_suggestions(metrics, review_date))
    
    return all_suggestions


def write_suggestions_json(
    suggestions: list[Suggestion],
    output_dir: Path,
    review_date: date,
) -> Path:
    """
    Write suggestions to JSON file.
    
    Returns path to written file.
    """
    output_path = output_dir / f"suggestions_{review_date.isoformat()}.json"
    
    # Serialize suggestions
    data = {
        "review_date": review_date.isoformat(),
        "total_suggestions": len(suggestions),
        "safety_notice": "All suggestions require manual review. Never auto-apply.",
        "suggestions": [
            {
                "suggestion_id": s.suggestion_id,
                "target": s.target,
                "rationale": s.rationale,
                "proposed_change": s.proposed_change,
                "safety": s.safety,
                "source_pattern": s.source_pattern,
                "source_category": s.source_category,
                "sample_size": s.sample_size,
                "success_rate": s.success_rate,
            }
            for s in suggestions
        ],
    }
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    return output_path


def format_suggestions_markdown(suggestions: list[Suggestion]) -> str:
    """
    Format suggestions as markdown for inclusion in review report.
    """
    if not suggestions:
        return "## Suggested Next PRs\n\n_No suggestions generated._\n"
    
    lines = [
        "## Suggested Next PRs",
        "",
        "> **Safety Notice:** All suggestions require manual review. Never auto-apply.",
        "",
    ]
    
    # Group by target
    by_target = {}
    for s in suggestions:
        if s.target not in by_target:
            by_target[s.target] = []
        by_target[s.target].append(s)
    
    for target, target_suggestions in by_target.items():
        lines.append(f"### {target.replace('_', ' ').title()}")
        lines.append("")
        
        for s in target_suggestions:
            lines.append(f"**{s.suggestion_id}**")
            lines.append(f"- **Rationale:** {s.rationale}")
            lines.append(f"- **Proposed:** `{s.proposed_change}`")
            lines.append(f"- **Evidence:** n={s.sample_size}, accuracy={s.success_rate:.0%}")
            lines.append("")
    
    return "\n".join(lines)
