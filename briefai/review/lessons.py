"""
Lesson Synthesis Engine

Generates actionable conclusions from discovered patterns.

NO LLM USAGE. All lessons are rule-based from pattern data.

v1.1: Added sample-size protection. Lessons include sample_size/success_rate.
      Weak insights (n<5) do NOT emit strong claims.
"""

from typing import Optional

from .models import (
    LearningInsight,
    Lesson,
    ReviewMetrics,
)
from .patterns import (
    get_top_performers,
    get_worst_performers,
    get_overconfident_areas,
    get_underconfident_areas,
)


# v1.1: Sample-size thresholds for lesson generation
MIN_SAMPLE_FOR_STRONG_CLAIM = 5
MIN_SAMPLE_FOR_ANY_CLAIM = 2


def generate_accuracy_lessons(
    metrics: ReviewMetrics,
    insights: list[LearningInsight],
) -> list[Lesson]:
    """
    Generate lessons about overall accuracy.
    """
    lessons = []
    
    # Overall accuracy assessment
    if metrics.overall_accuracy >= 0.7:
        lessons.append(Lesson(
            lesson_text="System predictions are generally reliable (>70% accuracy)",
            supporting_patterns=["overall_accuracy"],
            priority="normal",
            actionable=False,
        ))
    elif metrics.overall_accuracy >= 0.5:
        lessons.append(Lesson(
            lesson_text="System predictions have moderate accuracy - room for improvement",
            supporting_patterns=["overall_accuracy"],
            priority="normal",
            actionable=True,
        ))
    else:
        lessons.append(Lesson(
            lesson_text="System predictions are below 50% accuracy - fundamental review needed",
            supporting_patterns=["overall_accuracy"],
            priority="high",
            actionable=True,
        ))
    
    # Bullish vs Bearish comparison
    if metrics.bullish_count >= 3 and metrics.bearish_count >= 3:
        diff = metrics.bullish_accuracy - metrics.bearish_accuracy
        if diff > 0.2:
            lessons.append(Lesson(
                lesson_text="Better at predicting bullish trends than bearish - consider bias in bearish signals",
                supporting_patterns=["direction_up", "direction_down"],
                priority="normal",
                actionable=True,
            ))
        elif diff < -0.2:
            lessons.append(Lesson(
                lesson_text="Better at predicting bearish trends - bullish predictions may be overoptimistic",
                supporting_patterns=["direction_up", "direction_down"],
                priority="normal",
                actionable=True,
            ))
    
    # Confidence calibration
    if metrics.calibration_error > 0.15:
        lessons.append(Lesson(
            lesson_text=f"Confidence scores are poorly calibrated (error: {metrics.calibration_error:.2f}) - adjust confidence algorithm",
            supporting_patterns=["calibration"],
            priority="high",
            actionable=True,
        ))
    elif metrics.calibration_error < 0.05:
        lessons.append(Lesson(
            lesson_text="Confidence scores are well-calibrated - can be trusted",
            supporting_patterns=["calibration"],
            priority="normal",
            actionable=False,
        ))
    
    return lessons


def generate_mechanism_lessons(insights: list[LearningInsight]) -> list[Lesson]:
    """
    Generate lessons about which mechanisms work.
    
    v1.1: Respects sample-size protection. Weak insights (n<5) get qualified language.
    """
    lessons = []
    
    mechanism_insights = [i for i in insights if i.category == "mechanism"]
    
    if not mechanism_insights:
        return lessons
    
    # Find best mechanisms (require at least MIN_SAMPLE_FOR_STRONG_CLAIM for strong claims)
    best = [i for i in mechanism_insights if i.success_rate >= 0.7 and i.sample_size >= MIN_SAMPLE_FOR_ANY_CLAIM]
    for insight in best[:3]:
        # v1.1: Qualify weak insights
        if insight.sample_size < MIN_SAMPLE_FOR_STRONG_CLAIM:
            text = f"[Weak] Mechanism '{insight.pattern}' shows promise ({insight.success_rate:.0%} accuracy, n={insight.sample_size}) - needs more data"
            priority = "low"
        else:
            text = f"Mechanism '{insight.pattern}' is reliable ({insight.success_rate:.0%} accuracy, n={insight.sample_size})"
            priority = "normal"
        
        lessons.append(create_lesson_with_stats(
            text=text,
            patterns=[f"mechanism_{insight.pattern}"],
            priority=priority,
            actionable=False,
            insight=insight,
        ))
    
    # Find worst mechanisms
    worst = [i for i in mechanism_insights if i.success_rate < 0.4 and i.sample_size >= MIN_SAMPLE_FOR_ANY_CLAIM]
    for insight in worst[:3]:
        # v1.1: Qualify weak insights
        if insight.sample_size < MIN_SAMPLE_FOR_STRONG_CLAIM:
            text = f"[Weak] Mechanism '{insight.pattern}' may underperform ({insight.success_rate:.0%} accuracy, n={insight.sample_size}) - needs more data"
            priority = "normal"
        else:
            text = f"Mechanism '{insight.pattern}' underperforms ({insight.success_rate:.0%} accuracy) - reduce confidence or improve signals"
            priority = "high"
        
        lessons.append(create_lesson_with_stats(
            text=text,
            patterns=[f"mechanism_{insight.pattern}"],
            priority=priority,
            actionable=True,
            insight=insight,
        ))
    
    # Special mechanism insights (only with sufficient data)
    for insight in mechanism_insights:
        if insight.sample_size < MIN_SAMPLE_FOR_STRONG_CLAIM:
            continue  # v1.1: Skip weak insights for specific claims
        
        if insight.pattern == "media_attention_spike" and insight.success_rate < 0.5:
            lessons.append(create_lesson_with_stats(
                text="Media attention spikes are noisy indicators - require additional validation",
                patterns=["mechanism_media_attention_spike"],
                priority="normal",
                actionable=True,
                insight=insight,
            ))
        
        if insight.pattern == "research_translation" and insight.success_rate >= 0.6:
            lessons.append(create_lesson_with_stats(
                text="Research-paper surges predict launches reliably - weight arxiv/paper signals higher",
                patterns=["mechanism_research_translation"],
                priority="normal",
                actionable=True,
                insight=insight,
            ))
        
        if "hiring" in insight.pattern.lower() and insight.success_rate < 0.5:
            lessons.append(create_lesson_with_stats(
                text="Hiring signals are noisy - longer lag between hiring and outcome",
                patterns=[f"mechanism_{insight.pattern}"],
                priority="normal",
                actionable=True,
                insight=insight,
            ))
    
    return lessons


def generate_entity_lessons(insights: list[LearningInsight]) -> list[Lesson]:
    """
    Generate lessons about entity type performance.
    """
    lessons = []
    
    entity_insights = [i for i in insights if i.category == "entity_type"]
    
    for insight in entity_insights:
        if insight.sample_size < 3:
            continue
        
        if insight.pattern == "hyperscaler":
            if insight.success_rate >= 0.6:
                lessons.append(Lesson(
                    lesson_text="Hyperscaler predictions are reliable - strong signal coverage",
                    supporting_patterns=["entity_type_hyperscaler"],
                    priority="normal",
                    actionable=False,
                ))
            else:
                lessons.append(Lesson(
                    lesson_text="Hyperscaler predictions underperform - may be too much noise in coverage",
                    supporting_patterns=["entity_type_hyperscaler"],
                    priority="normal",
                    actionable=True,
                ))
        
        if insight.pattern == "chip_company":
            if insight.success_rate < 0.5:
                lessons.append(Lesson(
                    lesson_text="Chip companies have longer prediction latency - consider extending timeframes",
                    supporting_patterns=["entity_type_chip_company"],
                    priority="normal",
                    actionable=True,
                ))
        
        if insight.pattern == "enterprise_saas":
            if insight.success_rate < 0.5:
                lessons.append(Lesson(
                    lesson_text="We are overconfident on enterprise SaaS - need better B2B signal sources",
                    supporting_patterns=["entity_type_enterprise_saas"],
                    priority="high",
                    actionable=True,
                ))
    
    return lessons


def generate_category_lessons(insights: list[LearningInsight]) -> list[Lesson]:
    """
    Generate lessons about signal category performance.
    """
    lessons = []
    
    category_insights = [i for i in insights if i.category == "signal_category"]
    
    source_map = {
        "media": "techmeme, news",
        "social": "twitter, reddit",
        "technical": "github, arxiv",
        "financial": "earnings, filings",
    }
    
    for insight in category_insights:
        if insight.sample_size < 3:
            continue
        
        source_hint = source_map.get(insight.pattern, insight.pattern)
        
        if insight.success_rate >= 0.7:
            lessons.append(Lesson(
                lesson_text=f"'{insight.pattern}' signals ({source_hint}) are reliable predictors",
                supporting_patterns=[f"category_{insight.pattern}"],
                priority="normal",
                actionable=False,
            ))
        elif insight.success_rate < 0.4:
            lessons.append(Lesson(
                lesson_text=f"'{insight.pattern}' signals ({source_hint}) need improvement or additional validation",
                supporting_patterns=[f"category_{insight.pattern}"],
                priority="normal",
                actionable=True,
            ))
    
    return lessons


def generate_calibration_lessons(insights: list[LearningInsight]) -> list[Lesson]:
    """
    Generate lessons about confidence calibration.
    """
    lessons = []
    
    overconfident = get_overconfident_areas(insights)
    underconfident = get_underconfident_areas(insights)
    
    for insight in overconfident:
        lessons.append(Lesson(
            lesson_text=f"Overconfident at {insight.pattern} confidence level - reduce confidence scores",
            supporting_patterns=[f"calibration_{insight.pattern}"],
            priority="high",
            actionable=True,
        ))
    
    for insight in underconfident:
        lessons.append(Lesson(
            lesson_text=f"Underconfident at {insight.pattern} confidence level - can increase confidence",
            supporting_patterns=[f"calibration_{insight.pattern}"],
            priority="normal",
            actionable=True,
        ))
    
    return lessons


def generate_timeframe_lessons(insights: list[LearningInsight]) -> list[Lesson]:
    """
    Generate lessons about prediction timeframe performance.
    """
    lessons = []
    
    timeframe_insights = [i for i in insights if i.category == "timeframe"]
    
    if len(timeframe_insights) < 2:
        return lessons
    
    # Compare timeframes
    short = next((i for i in timeframe_insights if i.pattern == "short_term"), None)
    medium = next((i for i in timeframe_insights if i.pattern == "medium_term"), None)
    long_term = next((i for i in timeframe_insights if i.pattern == "long_term"), None)
    
    if short and medium:
        if short.success_rate > medium.success_rate + 0.15:
            lessons.append(Lesson(
                lesson_text="Short-term predictions more accurate than medium-term - consider shortening default timeframes",
                supporting_patterns=["timeframe_short_term", "timeframe_medium_term"],
                priority="normal",
                actionable=True,
            ))
        elif medium.success_rate > short.success_rate + 0.15:
            lessons.append(Lesson(
                lesson_text="Medium-term predictions more accurate than short-term - signals may need time to manifest",
                supporting_patterns=["timeframe_short_term", "timeframe_medium_term"],
                priority="normal",
                actionable=True,
            ))
    
    if long_term and long_term.success_rate < 0.4:
        lessons.append(Lesson(
            lesson_text="Long-term predictions are unreliable - avoid predictions >14 days out",
            supporting_patterns=["timeframe_long_term"],
            priority="normal",
            actionable=True,
        ))
    
    return lessons


def synthesize_lessons(
    metrics: ReviewMetrics,
    insights: list[LearningInsight],
) -> list[Lesson]:
    """
    Synthesize all lessons from metrics and patterns.
    
    Main entry point for lesson synthesis.
    
    Args:
        metrics: Computed review metrics
        insights: Discovered patterns
    
    Returns:
        List of Lesson objects with actionable conclusions
    
    v1.1: Lessons now include sample_size, success_rate, insight_strength.
          Sorted by reliability (sample_size * |success_rate - 0.5|).
    """
    all_lessons = []
    
    # Gather lessons from all sources
    all_lessons.extend(generate_accuracy_lessons(metrics, insights))
    all_lessons.extend(generate_mechanism_lessons(insights))
    all_lessons.extend(generate_entity_lessons(insights))
    all_lessons.extend(generate_category_lessons(insights))
    all_lessons.extend(generate_calibration_lessons(insights))
    all_lessons.extend(generate_timeframe_lessons(insights))
    
    # Deduplicate by lesson text
    seen = set()
    unique_lessons = []
    for lesson in all_lessons:
        if lesson.lesson_text not in seen:
            seen.add(lesson.lesson_text)
            unique_lessons.append(lesson)
    
    # v1.1: Sort by priority first, then by reliability score
    priority_order = {"high": 0, "normal": 1, "low": 2}
    unique_lessons.sort(
        key=lambda x: (
            priority_order.get(x.priority, 1),
            not x.actionable,
            -(x.sample_size * abs(x.success_rate - 0.5)) if x.sample_size > 0 else 0,
        )
    )
    
    return unique_lessons


def create_lesson_with_stats(
    text: str,
    patterns: list[str],
    priority: str,
    actionable: bool,
    insight: LearningInsight = None,
    sample_size: int = 0,
    success_rate: float = 0.0,
) -> Lesson:
    """
    v1.1: Helper to create lessons with sample-size stats.
    """
    if insight:
        sample_size = insight.sample_size
        success_rate = insight.success_rate
        insight_strength = insight.insight_strength
    else:
        # Determine strength from sample_size
        if sample_size >= 10:
            insight_strength = "strong"
        elif sample_size >= 5:
            insight_strength = "moderate"
        else:
            insight_strength = "weak"
    
    return Lesson(
        lesson_text=text,
        supporting_patterns=patterns,
        priority=priority,
        actionable=actionable,
        sample_size=sample_size,
        success_rate=success_rate,
        insight_strength=insight_strength,
    )


def format_lessons_markdown(lessons: list[Lesson]) -> str:
    """
    Format lessons as markdown.
    """
    lines = ["## System Lessons", ""]
    
    # High priority
    high = [l for l in lessons if l.priority == "high"]
    if high:
        lines.append("### 🚨 High Priority")
        for lesson in high:
            action = "✅ Actionable" if lesson.actionable else "📊 Observation"
            lines.append(f"- {lesson.lesson_text} ({action})")
        lines.append("")
    
    # Normal priority
    normal = [l for l in lessons if l.priority == "normal"]
    if normal:
        lines.append("### 📝 Findings")
        for lesson in normal:
            action = "✅" if lesson.actionable else "📊"
            lines.append(f"- {action} {lesson.lesson_text}")
        lines.append("")
    
    return "\n".join(lines)
