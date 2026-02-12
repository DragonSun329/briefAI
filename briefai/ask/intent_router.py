"""
Intent Router - Classify queries and generate tool plans.

Reduces "tool thrash" by:
1. Classifying query intent (trend_explain, entity_status, etc.)
2. Generating a focused tool plan based on intent
3. Setting appropriate max iterations

All routing is deterministic (keyword + regex, no LLM).
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from loguru import logger


# =============================================================================
# INTENT TYPES
# =============================================================================

class Intent:
    """Intent type constants."""
    TREND_EXPLAIN = "trend_explain"      # Explain a trend/concept
    ENTITY_STATUS = "entity_status"      # Status of a specific entity
    BULL_BEAR_CASE = "bull_bear_case"    # Bull/bear analysis
    COMPARE = "compare"                  # Compare entities/trends
    WHAT_CHANGED = "what_changed"        # Recent changes/diffs
    DAILY_CHANGE = "daily_change"        # v1.2: What changed today/yesterday
    FORECAST_CHECK = "forecast_check"    # Check predictions/forecasts
    GENERAL = "general"                  # General research


# =============================================================================
# INTENT PLAN
# =============================================================================

@dataclass
class IntentPlan:
    """
    Routing result with tool plan.
    
    Contains:
    - Classified intent
    - Default tools to run
    - Required tools (must run at least once)
    - Max iterations for this intent
    - Routing confidence
    """
    intent: str
    default_tools: List[str] = field(default_factory=list)
    required_tools: List[str] = field(default_factory=list)
    max_iterations: int = 5
    confidence: float = 1.0
    match_reason: str = ""
    
    def to_dict(self) -> dict:
        return {
            "intent": self.intent,
            "default_tools": self.default_tools,
            "required_tools": self.required_tools,
            "max_iterations": self.max_iterations,
            "confidence": self.confidence,
            "match_reason": self.match_reason,
        }


# =============================================================================
# ROUTING PATTERNS
# =============================================================================

# Pattern: (regex, intent, confidence)
INTENT_PATTERNS: List[Tuple[re.Pattern, str, float]] = [
    # Bull/bear case (highest priority)
    (re.compile(r"\b(bull|bear)\s*(and|&|/)?\s*(bull|bear)?\s*case\b", re.I), Intent.BULL_BEAR_CASE, 0.95),
    (re.compile(r"\blong\s*(and|&|/)?\s*short\s*(thesis|case)\b", re.I), Intent.BULL_BEAR_CASE, 0.90),
    (re.compile(r"\b(investment|trading)\s*thesis\b", re.I), Intent.BULL_BEAR_CASE, 0.85),
    (re.compile(r"\b(bullish|bearish)\s*on\b", re.I), Intent.BULL_BEAR_CASE, 0.80),
    
    # v1.2: Daily change (prioritized over general what_changed)
    (re.compile(r"\bwhat\s*(changed|happened|is\s*new)\s*(in\s+\w+\s+)?today\b", re.I), Intent.DAILY_CHANGE, 0.95),
    (re.compile(r"\btoday('s|\s+)?\s*(changes?|updates?|difference)\b", re.I), Intent.DAILY_CHANGE, 0.95),
    (re.compile(r"\bwhat's\s*new\s*(today|in\s+AI)\b", re.I), Intent.DAILY_CHANGE, 0.90),
    (re.compile(r"\bdaily\s*(update|change|diff)\b", re.I), Intent.DAILY_CHANGE, 0.90),
    (re.compile(r"\bsince\s*yesterday\b", re.I), Intent.DAILY_CHANGE, 0.85),
    
    # What changed (time-based queries - more general)
    (re.compile(r"\bwhat\s*(has\s+)?(changed|happened)\b", re.I), Intent.WHAT_CHANGED, 0.90),
    (re.compile(r"\b(today|yesterday|this\s*week|last\s*week)\s*vs\b", re.I), Intent.WHAT_CHANGED, 0.90),
    (re.compile(r"\b(recent|latest|new)\s*(changes?|updates?|developments?)\b", re.I), Intent.WHAT_CHANGED, 0.85),
    (re.compile(r"\bsince\s*(last\s*week|monday)\b", re.I), Intent.WHAT_CHANGED, 0.80),
    
    # Compare (comparison queries)
    (re.compile(r"\bcompare\b|\bvs\.?\b|\bversus\b", re.I), Intent.COMPARE, 0.90),
    (re.compile(r"\bdifference\s*between\b", re.I), Intent.COMPARE, 0.85),
    (re.compile(r"\b(better|worse)\s*than\b", re.I), Intent.COMPARE, 0.80),
    (re.compile(r"\b(\w+)\s+or\s+(\w+)\s*\?", re.I), Intent.COMPARE, 0.70),
    
    # Trend explain (concept/trend queries)
    (re.compile(r"\bexplain\s*(the|this)?\s*trend\b", re.I), Intent.TREND_EXPLAIN, 0.95),
    (re.compile(r"\b(what|why)\s*is\s*(\w+\s+){0,3}(trend|trending|emerging)\b", re.I), Intent.TREND_EXPLAIN, 0.85),
    (re.compile(r"\bwhat\s*does\s*(\w+\s+){0,3}(trend|signal|concept)\s*mean\b", re.I), Intent.TREND_EXPLAIN, 0.85),
    (re.compile(r"\b(meta[-\s]?signal|concept|emerging\s*trend)\b", re.I), Intent.TREND_EXPLAIN, 0.75),
    
    # Forecast check (prediction queries)
    (re.compile(r"\b(forecast|prediction|hypothesis)\b", re.I), Intent.FORECAST_CHECK, 0.85),
    (re.compile(r"\b(check|verify|validate)\s*(the\s+)?(forecast|prediction)\b", re.I), Intent.FORECAST_CHECK, 0.90),
    (re.compile(r"\bhow\s*(did|is)\s*(\w+\s+){0,3}(prediction|forecast)\b", re.I), Intent.FORECAST_CHECK, 0.80),
    
    # Entity status (entity-focused queries)
    (re.compile(r"\b(status|state|situation)\s*(of|for)\b", re.I), Intent.ENTITY_STATUS, 0.85),
    (re.compile(r"\bwhat('s|\s*is)\s*(happening|going\s*on)\s*(with|at)\b", re.I), Intent.ENTITY_STATUS, 0.80),
    (re.compile(r"\bhow\s*is\s+[A-Z][a-zA-Z]+\s*(doing|performing)\b", re.I), Intent.ENTITY_STATUS, 0.80),
    (re.compile(r"\btell\s*me\s*about\s+[A-Z]", re.I), Intent.ENTITY_STATUS, 0.70),
]

# Entity detection pattern (for entity_status routing)
ENTITY_PATTERN = re.compile(
    r"\b(OpenAI|Anthropic|Google|Meta|Microsoft|NVIDIA|Nvda|Apple|Amazon|AWS|"
    r"DeepMind|Cohere|Mistral|Hugging\s*Face|Tesla|ByteDance|Deepseek|xAI|"
    r"LangChain|LlamaIndex|Vercel|Supabase|Cursor|[A-Z][a-z]+AI)\b",
    re.I
)


# =============================================================================
# TOOL PLANS BY INTENT
# =============================================================================

INTENT_TOOL_PLANS = {
    Intent.TREND_EXPLAIN: IntentPlan(
        intent=Intent.TREND_EXPLAIN,
        default_tools=["search_meta_signals", "search_signals", "summarize_daily_brief"],
        required_tools=["search_meta_signals"],
        max_iterations=4,
    ),
    Intent.ENTITY_STATUS: IntentPlan(
        intent=Intent.ENTITY_STATUS,
        default_tools=["get_entity_profile", "search_signals", "search_meta_signals"],
        required_tools=["get_entity_profile"],
        max_iterations=4,
    ),
    Intent.BULL_BEAR_CASE: IntentPlan(
        intent=Intent.BULL_BEAR_CASE,
        default_tools=["get_entity_profile", "search_meta_signals", "search_signals", "retrieve_evidence"],
        required_tools=["get_entity_profile", "search_meta_signals"],
        max_iterations=6,
    ),
    Intent.COMPARE: IntentPlan(
        intent=Intent.COMPARE,
        default_tools=["get_entity_profile", "search_signals", "search_meta_signals"],
        required_tools=["get_entity_profile"],
        max_iterations=5,
    ),
    Intent.WHAT_CHANGED: IntentPlan(
        intent=Intent.WHAT_CHANGED,
        default_tools=["summarize_daily_brief", "search_meta_signals", "search_signals"],
        required_tools=["summarize_daily_brief"],
        max_iterations=4,
    ),
    # v1.2: Daily change uses diff_tool as primary
    Intent.DAILY_CHANGE: IntentPlan(
        intent=Intent.DAILY_CHANGE,
        default_tools=["get_daily_diff", "search_meta_signals", "summarize_daily_brief"],
        required_tools=["get_daily_diff"],
        max_iterations=4,
    ),
    Intent.FORECAST_CHECK: IntentPlan(
        intent=Intent.FORECAST_CHECK,
        default_tools=["get_forecast_snapshot", "list_hypotheses", "retrieve_evidence"],
        required_tools=["get_forecast_snapshot"],
        max_iterations=4,
    ),
    Intent.GENERAL: IntentPlan(
        intent=Intent.GENERAL,
        default_tools=["search_meta_signals", "search_signals", "get_entity_profile", "summarize_daily_brief"],
        required_tools=["search_meta_signals"],
        max_iterations=6,
    ),
}


# =============================================================================
# MAIN ROUTER
# =============================================================================

def route_intent(query: str) -> IntentPlan:
    """
    Classify query intent and return a tool plan.
    
    Uses deterministic keyword + regex matching (no LLM).
    
    Args:
        query: User's question
    
    Returns:
        IntentPlan with classified intent and tool configuration
    """
    query_clean = query.strip()
    best_match: Optional[Tuple[str, float, str]] = None
    
    # Try each pattern
    for pattern, intent, confidence in INTENT_PATTERNS:
        match = pattern.search(query_clean)
        if match:
            if best_match is None or confidence > best_match[1]:
                best_match = (intent, confidence, f"Pattern: {pattern.pattern[:50]}")
    
    # If no pattern matched, check for entity mentions → entity_status
    if best_match is None:
        entity_match = ENTITY_PATTERN.search(query_clean)
        if entity_match:
            best_match = (Intent.ENTITY_STATUS, 0.60, f"Entity detected: {entity_match.group()}")
    
    # Default to general
    if best_match is None:
        best_match = (Intent.GENERAL, 0.50, "Default fallback")
    
    intent, confidence, reason = best_match
    
    # Get the plan template and customize
    plan = IntentPlan(
        intent=intent,
        default_tools=list(INTENT_TOOL_PLANS[intent].default_tools),
        required_tools=list(INTENT_TOOL_PLANS[intent].required_tools),
        max_iterations=INTENT_TOOL_PLANS[intent].max_iterations,
        confidence=confidence,
        match_reason=reason,
    )
    
    logger.debug(f"Intent routing: '{query[:50]}...' → {intent} (conf={confidence:.2f})")
    
    return plan


def get_intent_description(intent: str) -> str:
    """Get human-readable description of an intent."""
    descriptions = {
        Intent.TREND_EXPLAIN: "Explain a trend or concept",
        Intent.ENTITY_STATUS: "Get status of a specific entity",
        Intent.BULL_BEAR_CASE: "Analyze bull and bear cases",
        Intent.COMPARE: "Compare entities or trends",
        Intent.WHAT_CHANGED: "Identify recent changes",
        Intent.FORECAST_CHECK: "Check predictions and forecasts",
        Intent.GENERAL: "General research query",
    }
    return descriptions.get(intent, "Unknown intent")


def list_intents() -> List[dict]:
    """List all supported intents with their tool plans."""
    return [
        {
            "intent": intent,
            "description": get_intent_description(intent),
            "default_tools": plan.default_tools,
            "max_iterations": plan.max_iterations,
        }
        for intent, plan in INTENT_TOOL_PLANS.items()
    ]
