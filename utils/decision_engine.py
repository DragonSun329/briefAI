"""
Decision Engine v1.0 - Map Beliefs to Actions.

Part of briefAI Phase 2: Add Decision Intelligence.

This module answers: "What should I do?"
Not "What is happening?" — that's already answered by beliefs.

The job is to map beliefs → actions using rule-based logic (no LLM).

Example mappings:
    Signal                   Decision
    infra_scaling ↑          Buy semiconductor suppliers
    enterprise_adoption ↑    B2B SaaS expansion
    pricing_compression ↑    Avoid foundation model startups
    distribution_shift ↑     Invest in application layer

This is a rule-based system first. LLM enhancement can come later.
"""

import json
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

from loguru import logger


# =============================================================================
# CONSTANTS
# =============================================================================

DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config" / "decision_rules.json"

# Minimum confidence to trigger an action
MIN_ACTION_CONFIDENCE = 0.65

# Confidence change threshold to consider "rising" or "falling"
DIRECTION_THRESHOLD = 0.03


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class ActionRecommendation:
    """A recommended action based on beliefs."""
    
    action_id: str
    action_type: str  # buy, sell, avoid, monitor, expand, reduce
    description: str
    confidence: float
    
    # Supporting beliefs
    supporting_beliefs: List[Dict[str, Any]]
    
    # Metadata
    sector: str = ""
    timeframe: str = "medium_term"  # short, medium, long
    risk_level: str = "moderate"    # low, moderate, high
    
    # Reasoning
    primary_mechanism: str = ""
    reasoning: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @property
    def is_actionable(self) -> bool:
        """True if confidence meets threshold."""
        return self.confidence >= MIN_ACTION_CONFIDENCE


# =============================================================================
# DECISION RULES
# =============================================================================

# Default decision rules when config not available
DEFAULT_RULES = {
    # Infrastructure scaling
    "infra_scaling": {
        "rising": {
            "action_type": "buy",
            "description": "Positive exposure to AI infrastructure providers",
            "sector": "semiconductors",
            "reasoning": "Infrastructure scaling signals increased compute demand",
            "examples": ["NVIDIA", "AMD", "ASML", "datacenter REITs"],
        },
        "falling": {
            "action_type": "reduce",
            "description": "Reduce infrastructure overweight",
            "sector": "semiconductors",
            "reasoning": "Declining infrastructure signals may indicate demand plateau",
        },
    },
    
    # Enterprise adoption
    "enterprise_adoption": {
        "rising": {
            "action_type": "buy",
            "description": "Increase B2B SaaS and enterprise AI exposure",
            "sector": "enterprise_software",
            "reasoning": "Enterprise adoption drives recurring revenue growth",
            "examples": ["Salesforce", "ServiceNow", "Palantir", "enterprise AI startups"],
        },
        "falling": {
            "action_type": "avoid",
            "description": "Avoid new enterprise AI positions",
            "sector": "enterprise_software",
            "reasoning": "Slowing adoption reduces growth runway",
        },
    },
    
    # Pricing compression
    "pricing_compression": {
        "rising": {
            "action_type": "avoid",
            "description": "Avoid foundation model companies without distribution",
            "sector": "ai_models",
            "reasoning": "Commoditization pressure reduces margins for pure-play model providers",
            "examples": ["Anthropic competitors", "open-weight model providers"],
        },
        "falling": {
            "action_type": "monitor",
            "description": "Monitor for pricing power recovery",
            "sector": "ai_models",
            "reasoning": "Reduced price pressure may indicate differentiation",
        },
    },
    
    # Distribution shift
    "distribution_shift": {
        "rising": {
            "action_type": "buy",
            "description": "Invest in application layer over infrastructure",
            "sector": "ai_applications",
            "reasoning": "Value accruing to applications with distribution moats",
            "examples": ["Vertical AI SaaS", "consumer AI apps", "embedded AI"],
        },
        "falling": {
            "action_type": "reduce",
            "description": "Reduce application layer tilt",
            "sector": "ai_applications",
            "reasoning": "Distribution less valuable if shifting back to infra",
        },
    },
    
    # Competitive pressure
    "competitive_pressure": {
        "rising": {
            "action_type": "avoid",
            "description": "Avoid undifferentiated AI pure-plays",
            "sector": "ai_general",
            "reasoning": "Intensifying competition compresses multiples",
        },
        "falling": {
            "action_type": "buy",
            "description": "Consider quality AI names with reduced competition",
            "sector": "ai_general",
            "reasoning": "Reduced competition supports margin expansion",
        },
    },
    
    # Regulatory shift
    "regulatory_shift": {
        "rising": {
            "action_type": "monitor",
            "description": "Monitor regulatory exposure across positions",
            "sector": "all",
            "risk_level": "high",
            "reasoning": "Regulatory uncertainty increases headline risk",
        },
        "falling": {
            "action_type": "buy",
            "description": "Reduced regulatory overhang supports risk-on",
            "sector": "all",
            "reasoning": "Regulatory clarity de-risks sector",
        },
    },
    
    # Talent migration
    "talent_migration": {
        "rising": {
            "action_type": "buy",
            "description": "Follow talent concentration to emerging leaders",
            "sector": "ai_general",
            "reasoning": "Talent flows precede product differentiation",
        },
        "falling": {
            "action_type": "monitor",
            "description": "Monitor talent retention at portfolio companies",
            "sector": "ai_general",
            "reasoning": "Talent exodus signals potential issues",
        },
    },
    
    # Capex acceleration
    "capex_acceleration": {
        "rising": {
            "action_type": "buy",
            "description": "Long hyperscaler capex beneficiaries",
            "sector": "datacenter_infrastructure",
            "reasoning": "Capex commits create multi-year tailwinds",
            "examples": ["Vertiv", "Eaton", "cooling companies", "power infrastructure"],
        },
        "falling": {
            "action_type": "reduce",
            "description": "Trim capex-sensitive names",
            "sector": "datacenter_infrastructure",
            "reasoning": "Capex slowdown reduces order visibility",
        },
    },
    
    # Open source momentum
    "open_source_momentum": {
        "rising": {
            "action_type": "avoid",
            "description": "Avoid closed-source AI without strong moats",
            "sector": "ai_models",
            "reasoning": "Open source commoditizes model layer",
        },
        "falling": {
            "action_type": "buy",
            "description": "Consider differentiated closed-source leaders",
            "sector": "ai_models",
            "reasoning": "Reduced open source pressure supports premium providers",
        },
    },
}


# =============================================================================
# DECISION ENGINE
# =============================================================================

class DecisionEngine:
    """
    Maps beliefs to actionable recommendations.
    
    Uses rule-based logic to generate investment/strategy recommendations
    based on hypothesis beliefs and their trajectories.
    """
    
    def __init__(self, rules: Dict = None, config_path: Path = None):
        """
        Initialize decision engine.
        
        Args:
            rules: Decision rules dict (overrides config file)
            config_path: Path to decision_rules.json
        """
        if rules:
            self.rules = rules
        elif config_path and config_path.exists():
            self.rules = self._load_rules(config_path)
        else:
            self.rules = DEFAULT_RULES
        
        logger.debug(f"DecisionEngine initialized with {len(self.rules)} mechanisms")
    
    def _load_rules(self, path: Path) -> Dict:
        """Load rules from config file."""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            return config.get('rules', DEFAULT_RULES)
        except Exception as e:
            logger.warning(f"Failed to load decision rules: {e}")
            return DEFAULT_RULES
    
    def get_belief_direction(self, belief: Dict) -> str:
        """
        Determine belief direction (rising, falling, stable).
        
        Args:
            belief: Belief state dict
        
        Returns:
            Direction string: 'rising', 'falling', or 'stable'
        """
        prior = belief.get('prior_confidence', 0.5)
        posterior = belief.get('posterior_confidence', prior)
        
        change = posterior - prior
        
        if change > DIRECTION_THRESHOLD:
            return 'rising'
        elif change < -DIRECTION_THRESHOLD:
            return 'falling'
        else:
            return 'stable'
    
    def generate_action(
        self,
        mechanism: str,
        direction: str,
        belief: Dict,
        hypothesis: Dict = None,
    ) -> Optional[ActionRecommendation]:
        """
        Generate an action recommendation for a belief.
        
        Args:
            mechanism: Hypothesis mechanism (e.g., 'infra_scaling')
            direction: Belief direction ('rising', 'falling', 'stable')
            belief: Belief state dict
            hypothesis: Optional hypothesis dict for context
        
        Returns:
            ActionRecommendation or None if no rule matches
        """
        # Look up rule
        mechanism_rules = self.rules.get(mechanism, {})
        rule = mechanism_rules.get(direction)
        
        if not rule:
            return None
        
        # Get confidence
        confidence = belief.get('posterior_confidence', 0.5)
        
        # Build action ID
        action_id = f"action_{mechanism}_{direction}_{datetime.now().strftime('%Y%m%d')}"
        
        # Build supporting beliefs
        supporting = [{
            'hypothesis_id': belief.get('hypothesis_id', ''),
            'mechanism': mechanism,
            'confidence': confidence,
            'direction': direction,
            'prior': belief.get('prior_confidence', 0.5),
            'posterior': confidence,
        }]
        
        return ActionRecommendation(
            action_id=action_id,
            action_type=rule.get('action_type', 'monitor'),
            description=rule.get('description', ''),
            confidence=confidence,
            supporting_beliefs=supporting,
            sector=rule.get('sector', 'general'),
            timeframe=rule.get('timeframe', 'medium_term'),
            risk_level=rule.get('risk_level', 'moderate'),
            primary_mechanism=mechanism,
            reasoning=rule.get('reasoning', ''),
        )
    
    def generate_recommendations(
        self,
        beliefs: Dict[str, Dict],
        hypotheses: List[Dict] = None,
        min_confidence: float = MIN_ACTION_CONFIDENCE,
    ) -> List[ActionRecommendation]:
        """
        Generate all recommendations from current beliefs.
        
        Args:
            beliefs: Dict of belief states by hypothesis_id
            hypotheses: Optional list of hypothesis dicts
            min_confidence: Minimum confidence for recommendations
        
        Returns:
            List of ActionRecommendation sorted by confidence
        """
        # Build hypothesis lookup
        hyp_lookup = {}
        if hypotheses:
            for hyp in hypotheses:
                hyp_lookup[hyp.get('hypothesis_id', '')] = hyp
        
        recommendations = []
        
        for hyp_id, belief in beliefs.items():
            # Get hypothesis info
            hyp = hyp_lookup.get(hyp_id, {})
            mechanism = hyp.get('mechanism', self._infer_mechanism(hyp_id, belief))
            
            if not mechanism:
                continue
            
            # Get direction
            direction = self.get_belief_direction(belief)
            
            if direction == 'stable':
                continue  # No action for stable beliefs
            
            # Generate action
            action = self.generate_action(mechanism, direction, belief, hyp)
            
            if action and action.confidence >= min_confidence:
                recommendations.append(action)
        
        # Sort by confidence
        recommendations.sort(key=lambda x: x.confidence, reverse=True)
        
        return recommendations
    
    def _infer_mechanism(self, hyp_id: str, belief: Dict) -> Optional[str]:
        """Infer mechanism from hypothesis ID or belief context."""
        # Try to extract from ID
        for mechanism in self.rules.keys():
            if mechanism in hyp_id.lower():
                return mechanism
        
        return None
    
    def consolidate_recommendations(
        self,
        recommendations: List[ActionRecommendation],
    ) -> List[ActionRecommendation]:
        """
        Consolidate multiple recommendations into coherent actions.
        
        Merges recommendations for the same sector/action_type.
        
        Args:
            recommendations: List of recommendations
        
        Returns:
            Consolidated list of recommendations
        """
        # Group by sector + action_type
        groups: Dict[str, List[ActionRecommendation]] = {}
        
        for rec in recommendations:
            key = f"{rec.sector}_{rec.action_type}"
            if key not in groups:
                groups[key] = []
            groups[key].append(rec)
        
        # Merge each group
        consolidated = []
        
        for key, recs in groups.items():
            if len(recs) == 1:
                consolidated.append(recs[0])
            else:
                # Merge: average confidence, combine beliefs
                avg_conf = sum(r.confidence for r in recs) / len(recs)
                all_beliefs = []
                for r in recs:
                    all_beliefs.extend(r.supporting_beliefs)
                
                # Use highest confidence rec as base
                base = max(recs, key=lambda r: r.confidence)
                
                merged = ActionRecommendation(
                    action_id=f"merged_{key}_{datetime.now().strftime('%Y%m%d')}",
                    action_type=base.action_type,
                    description=base.description,
                    confidence=avg_conf,
                    supporting_beliefs=all_beliefs,
                    sector=base.sector,
                    timeframe=base.timeframe,
                    risk_level=base.risk_level,
                    primary_mechanism=base.primary_mechanism,
                    reasoning=f"Consolidated from {len(recs)} supporting signals",
                )
                
                consolidated.append(merged)
        
        # Sort by confidence
        consolidated.sort(key=lambda x: x.confidence, reverse=True)
        
        return consolidated


# =============================================================================
# BRIEF SECTION GENERATOR
# =============================================================================

def generate_actions_section(
    recommendations: List[ActionRecommendation],
    max_actions: int = 5,
) -> str:
    """
    Generate the Recommended Actions section for analyst brief.
    
    Args:
        recommendations: List of action recommendations
        max_actions: Maximum actions to show
    
    Returns:
        Formatted markdown section
    """
    lines = []
    lines.append("## 5. Recommended Actions")
    lines.append("")
    
    if not recommendations:
        lines.append("*No actionable recommendations at this time.*")
        lines.append("")
        return "\n".join(lines)
    
    # Filter to actionable only
    actionable = [r for r in recommendations if r.is_actionable][:max_actions]
    
    if not actionable:
        lines.append("*No recommendations meet the confidence threshold.*")
        lines.append("")
        return "\n".join(lines)
    
    for rec in actionable:
        # Action type emoji
        type_emoji = {
            'buy': '📈',
            'sell': '📉',
            'avoid': '⛔',
            'reduce': '📉',
            'monitor': '👀',
            'expand': '📈',
        }.get(rec.action_type, '•')
        
        lines.append(f"### {type_emoji} {rec.description}")
        lines.append("")
        lines.append(f"**Confidence:** {rec.confidence:.0%}")
        lines.append(f"**Sector:** {rec.sector}")
        lines.append(f"**Timeframe:** {rec.timeframe.replace('_', ' ')}")
        lines.append("")
        
        # Supporting beliefs
        if rec.supporting_beliefs:
            lines.append("**Supporting signals:**")
            for belief in rec.supporting_beliefs[:3]:
                mechanism = belief.get('mechanism', '?')
                direction = belief.get('direction', '?')
                arrow = '↑' if direction == 'rising' else '↓' if direction == 'falling' else '→'
                lines.append(f"- {mechanism.replace('_', ' ')} {arrow}")
            lines.append("")
        
        # Reasoning
        if rec.reasoning:
            lines.append(f"**Rationale:** {rec.reasoning}")
            lines.append("")
    
    return "\n".join(lines)


# =============================================================================
# TESTS
# =============================================================================

def _test_direction():
    """Test belief direction detection."""
    engine = DecisionEngine()
    
    rising = {'prior_confidence': 0.60, 'posterior_confidence': 0.75}
    assert engine.get_belief_direction(rising) == 'rising'
    
    falling = {'prior_confidence': 0.70, 'posterior_confidence': 0.55}
    assert engine.get_belief_direction(falling) == 'falling'
    
    stable = {'prior_confidence': 0.60, 'posterior_confidence': 0.62}
    assert engine.get_belief_direction(stable) == 'stable'
    
    print("[PASS] _test_direction")


def _test_action_generation():
    """Test action generation from beliefs."""
    engine = DecisionEngine()
    
    belief = {
        'hypothesis_id': 'hyp_infra_001',
        'prior_confidence': 0.60,
        'posterior_confidence': 0.80,
    }
    
    action = engine.generate_action('infra_scaling', 'rising', belief)
    
    assert action is not None
    assert action.action_type == 'buy'
    assert 'infrastructure' in action.description.lower()
    assert action.confidence == 0.80
    
    print("[PASS] _test_action_generation")


def _test_recommendations():
    """Test recommendation generation."""
    engine = DecisionEngine()
    
    beliefs = {
        'hyp_infra_001': {
            'hypothesis_id': 'hyp_infra_001',
            'prior_confidence': 0.60,
            'posterior_confidence': 0.80,
        },
        'hyp_pricing_001': {
            'hypothesis_id': 'hyp_pricing_001',
            'prior_confidence': 0.70,
            'posterior_confidence': 0.50,
        },
    }
    
    hypotheses = [
        {'hypothesis_id': 'hyp_infra_001', 'mechanism': 'infra_scaling'},
        {'hypothesis_id': 'hyp_pricing_001', 'mechanism': 'pricing_compression'},
    ]
    
    recs = engine.generate_recommendations(beliefs, hypotheses, min_confidence=0.0)
    
    assert len(recs) == 2
    # Should be sorted by confidence (infra first at 0.80, then pricing at 0.50)
    assert recs[0].primary_mechanism == 'infra_scaling'
    
    print("[PASS] _test_recommendations")


def run_tests():
    """Run all decision engine tests."""
    print("\n=== DECISION ENGINE TESTS ===\n")
    
    _test_direction()
    _test_action_generation()
    _test_recommendations()
    
    print("\n=== ALL TESTS PASSED ===")


if __name__ == "__main__":
    run_tests()
