"""
Alert Rules Engine

User-defined rule system for generating alerts.
Rules are stored in config/alert_rules.json and support:
- AND/OR logic for complex conditions
- Multiple signal comparisons
- Custom actions and notification channels
- Priority and scheduling
"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, time as dt_time
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable, Union
from enum import Enum
from loguru import logger

from utils.alert_engine import (
    AlertEngine, Alert, AlertType, AlertSeverity, AlertCategory,
    generate_threshold_alert, generate_divergence_alert,
    generate_momentum_alert, generate_anomaly_alert
)


class Operator(str, Enum):
    """Comparison operators."""
    GT = ">"
    GTE = ">="
    LT = "<"
    LTE = "<="
    EQ = "=="
    NEQ = "!="
    BETWEEN = "between"
    NOT_BETWEEN = "not_between"


class LogicOp(str, Enum):
    """Logical operators for combining conditions."""
    AND = "AND"
    OR = "OR"


@dataclass
class Condition:
    """
    Single condition in a rule.
    
    Examples:
        - signal: "tms", operator: ">", value: 80
        - signal: "momentum_7d", operator: "between", value: [10, 50]
    """
    signal: str
    operator: Operator
    value: Union[float, List[float]]
    
    def evaluate(self, signals: Dict[str, float]) -> bool:
        """
        Evaluate condition against signal values.
        
        Args:
            signals: Dict mapping signal names to values
        
        Returns:
            True if condition is met
        """
        if self.signal not in signals:
            return False
        
        actual = signals[self.signal]
        
        if self.operator == Operator.GT:
            return actual > self.value
        elif self.operator == Operator.GTE:
            return actual >= self.value
        elif self.operator == Operator.LT:
            return actual < self.value
        elif self.operator == Operator.LTE:
            return actual <= self.value
        elif self.operator == Operator.EQ:
            return actual == self.value
        elif self.operator == Operator.NEQ:
            return actual != self.value
        elif self.operator == Operator.BETWEEN:
            if not isinstance(self.value, list) or len(self.value) != 2:
                return False
            return self.value[0] <= actual <= self.value[1]
        elif self.operator == Operator.NOT_BETWEEN:
            if not isinstance(self.value, list) or len(self.value) != 2:
                return False
            return actual < self.value[0] or actual > self.value[1]
        
        return False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal": self.signal,
            "operator": self.operator.value if isinstance(self.operator, Operator) else self.operator,
            "value": self.value,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Condition":
        return cls(
            signal=data["signal"],
            operator=Operator(data["operator"]),
            value=data["value"],
        )
    
    def describe(self) -> str:
        """Human-readable description."""
        if self.operator == Operator.BETWEEN:
            return f"{self.signal} between {self.value[0]} and {self.value[1]}"
        elif self.operator == Operator.NOT_BETWEEN:
            return f"{self.signal} outside {self.value[0]}-{self.value[1]}"
        return f"{self.signal} {self.operator.value} {self.value}"


@dataclass
class ConditionGroup:
    """
    Group of conditions combined with AND/OR logic.
    
    Supports nested groups for complex logic:
        (A AND B) OR (C AND D)
    """
    conditions: List[Union[Condition, "ConditionGroup"]]
    logic: LogicOp = LogicOp.AND
    
    def evaluate(self, signals: Dict[str, float]) -> bool:
        """Evaluate all conditions with specified logic."""
        if not self.conditions:
            return False
        
        results = []
        for cond in self.conditions:
            if isinstance(cond, Condition):
                results.append(cond.evaluate(signals))
            elif isinstance(cond, ConditionGroup):
                results.append(cond.evaluate(signals))
        
        if self.logic == LogicOp.AND:
            return all(results)
        else:  # OR
            return any(results)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "logic": self.logic.value,
            "conditions": [
                c.to_dict() if isinstance(c, (Condition, ConditionGroup)) else c
                for c in self.conditions
            ],
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConditionGroup":
        conditions = []
        for c in data.get("conditions", []):
            if "logic" in c:
                conditions.append(cls.from_dict(c))
            else:
                conditions.append(Condition.from_dict(c))
        
        return cls(
            conditions=conditions,
            logic=LogicOp(data.get("logic", "AND")),
        )
    
    def describe(self) -> str:
        """Human-readable description."""
        parts = []
        for cond in self.conditions:
            if isinstance(cond, Condition):
                parts.append(cond.describe())
            else:
                parts.append(f"({cond.describe()})")
        
        return f" {self.logic.value} ".join(parts)


@dataclass
class AlertRule:
    """
    Complete alert rule definition.
    
    Combines conditions with alert configuration and notification settings.
    """
    id: str
    name: str
    description: str
    conditions: ConditionGroup
    
    # Alert settings
    alert_type: AlertType = AlertType.THRESHOLD
    severity: AlertSeverity = AlertSeverity.MEDIUM
    category: AlertCategory = AlertCategory.WATCH
    
    # Notification channels
    channels: List[str] = field(default_factory=lambda: ["file"])
    
    # Targeting
    entity_filter: Optional[str] = None  # Regex pattern for entity IDs
    entity_whitelist: List[str] = field(default_factory=list)  # Only these entities
    entity_blacklist: List[str] = field(default_factory=list)  # Exclude these
    
    # Scheduling
    enabled: bool = True
    priority: int = 50  # 0-100, higher = more important
    cooldown_hours: int = 24
    active_hours: Optional[tuple] = None  # (start_hour, end_hour) or None for always
    
    # Custom message templates
    title_template: Optional[str] = None
    message_template: Optional[str] = None
    
    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    created_by: str = "system"
    
    # Stats
    times_triggered: int = 0
    last_triggered: Optional[datetime] = None
    
    def evaluate(
        self, 
        entity_id: str, 
        entity_name: str, 
        signals: Dict[str, float]
    ) -> bool:
        """
        Evaluate if rule should trigger for entity with given signals.
        
        Args:
            entity_id: Entity identifier
            entity_name: Display name
            signals: Signal values
        
        Returns:
            True if rule should trigger
        """
        # Check if enabled
        if not self.enabled:
            return False
        
        # Check entity filtering
        if not self._matches_entity(entity_id):
            return False
        
        # Check active hours
        if not self._is_active_time():
            return False
        
        # Evaluate conditions
        return self.conditions.evaluate(signals)
    
    def _matches_entity(self, entity_id: str) -> bool:
        """Check if entity matches filtering rules."""
        # Blacklist takes priority
        if entity_id in self.entity_blacklist:
            return False
        
        # If whitelist specified, must be in it
        if self.entity_whitelist:
            return entity_id in self.entity_whitelist
        
        # Check regex pattern
        if self.entity_filter:
            import re
            return bool(re.match(self.entity_filter, entity_id))
        
        # Default: match all
        return True
    
    def _is_active_time(self) -> bool:
        """Check if current time is within active hours."""
        if not self.active_hours:
            return True
        
        start, end = self.active_hours
        current_hour = datetime.now().hour
        
        if start <= end:
            return start <= current_hour < end
        else:  # Wraps around midnight
            return current_hour >= start or current_hour < end
    
    def format_title(self, entity_name: str, signals: Dict[str, float]) -> str:
        """Generate alert title from template or default."""
        if self.title_template:
            try:
                return self.title_template.format(
                    entity_name=entity_name,
                    rule_name=self.name,
                    **signals
                )
            except KeyError:
                pass
        
        return f"{entity_name}: {self.name}"
    
    def format_message(self, entity_name: str, signals: Dict[str, float]) -> str:
        """Generate alert message from template or default."""
        if self.message_template:
            try:
                return self.message_template.format(
                    entity_name=entity_name,
                    rule_name=self.name,
                    rule_description=self.description,
                    conditions=self.conditions.describe(),
                    **signals
                )
            except KeyError:
                pass
        
        return f"{self.description}. Conditions: {self.conditions.describe()}"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "conditions": self.conditions.to_dict(),
            "alert_type": self.alert_type.value,
            "severity": self.severity.value,
            "category": self.category.value,
            "channels": self.channels,
            "entity_filter": self.entity_filter,
            "entity_whitelist": self.entity_whitelist,
            "entity_blacklist": self.entity_blacklist,
            "enabled": self.enabled,
            "priority": self.priority,
            "cooldown_hours": self.cooldown_hours,
            "active_hours": self.active_hours,
            "title_template": self.title_template,
            "message_template": self.message_template,
            "created_at": self.created_at.isoformat() if isinstance(self.created_at, datetime) else self.created_at,
            "updated_at": self.updated_at.isoformat() if isinstance(self.updated_at, datetime) else self.updated_at,
            "created_by": self.created_by,
            "times_triggered": self.times_triggered,
            "last_triggered": self.last_triggered.isoformat() if self.last_triggered else None,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AlertRule":
        return cls(
            id=data.get("id", str(uuid.uuid4())[:8]),
            name=data["name"],
            description=data.get("description", ""),
            conditions=ConditionGroup.from_dict(data["conditions"]),
            alert_type=AlertType(data.get("alert_type", "threshold")),
            severity=AlertSeverity(data.get("severity", "medium")),
            category=AlertCategory(data.get("category", "watch")),
            channels=data.get("channels", ["file"]),
            entity_filter=data.get("entity_filter"),
            entity_whitelist=data.get("entity_whitelist", []),
            entity_blacklist=data.get("entity_blacklist", []),
            enabled=data.get("enabled", True),
            priority=data.get("priority", 50),
            cooldown_hours=data.get("cooldown_hours", 24),
            active_hours=tuple(data["active_hours"]) if data.get("active_hours") else None,
            title_template=data.get("title_template"),
            message_template=data.get("message_template"),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else datetime.now(),
            created_by=data.get("created_by", "system"),
            times_triggered=data.get("times_triggered", 0),
            last_triggered=datetime.fromisoformat(data["last_triggered"]) if data.get("last_triggered") else None,
        )


class AlertRulesEngine:
    """
    Engine for managing and evaluating alert rules.
    
    Loads rules from config file and evaluates them against signal data.
    """
    
    def __init__(
        self, 
        rules_path: Optional[Path] = None,
        alert_engine: Optional[AlertEngine] = None,
    ):
        """
        Initialize rules engine.
        
        Args:
            rules_path: Path to rules JSON file
            alert_engine: AlertEngine instance for creating alerts
        """
        self.rules_path = rules_path or Path("config/alert_rules.json")
        self.alert_engine = alert_engine or AlertEngine()
        self.rules: Dict[str, AlertRule] = {}
        
        self._load_rules()
        logger.info(f"AlertRulesEngine initialized with {len(self.rules)} rules")
    
    def _load_rules(self) -> None:
        """Load rules from config file."""
        if not self.rules_path.exists():
            logger.warning(f"Rules file not found: {self.rules_path}")
            self._create_default_rules()
            return
        
        try:
            with open(self.rules_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            for rule_data in data.get("rules", []):
                try:
                    rule = AlertRule.from_dict(rule_data)
                    self.rules[rule.id] = rule
                except Exception as e:
                    logger.error(f"Failed to load rule {rule_data.get('id', 'unknown')}: {e}")
        
        except Exception as e:
            logger.error(f"Failed to load rules file: {e}")
            self._create_default_rules()
    
    def _create_default_rules(self) -> None:
        """Create default rule set."""
        default_rules = [
            AlertRule(
                id="alpha_zone",
                name="Alpha Zone (Hidden Gem)",
                description="High technical momentum but low capital conviction - potential opportunity",
                conditions=ConditionGroup(
                    conditions=[
                        Condition("tms", Operator.GTE, 85),
                        Condition("ccs", Operator.LTE, 35),
                    ],
                    logic=LogicOp.AND,
                ),
                alert_type=AlertType.DIVERGENCE,
                severity=AlertSeverity.HIGH,
                category=AlertCategory.OPPORTUNITY,
                channels=["discord", "file"],
            ),
            AlertRule(
                id="hype_zone",
                name="Hype Zone Warning",
                description="High narrative attention but weak technical fundamentals",
                conditions=ConditionGroup(
                    conditions=[
                        Condition("nas", Operator.GTE, 80),
                        Condition("tms", Operator.LTE, 40),
                    ],
                    logic=LogicOp.AND,
                ),
                alert_type=AlertType.DIVERGENCE,
                severity=AlertSeverity.HIGH,
                category=AlertCategory.RISK,
                channels=["discord", "file"],
            ),
            AlertRule(
                id="momentum_surge",
                name="Momentum Surge",
                description="Significant positive momentum detected",
                conditions=ConditionGroup(
                    conditions=[
                        Condition("momentum_7d", Operator.GTE, 30),
                    ],
                    logic=LogicOp.AND,
                ),
                alert_type=AlertType.MOMENTUM,
                severity=AlertSeverity.MEDIUM,
                category=AlertCategory.OPPORTUNITY,
                channels=["file"],
            ),
            AlertRule(
                id="momentum_crash",
                name="Momentum Crash",
                description="Significant negative momentum detected",
                conditions=ConditionGroup(
                    conditions=[
                        Condition("momentum_7d", Operator.LTE, -30),
                    ],
                    logic=LogicOp.AND,
                ),
                alert_type=AlertType.MOMENTUM,
                severity=AlertSeverity.HIGH,
                category=AlertCategory.RISK,
                channels=["discord", "file"],
            ),
            AlertRule(
                id="enterprise_breakout",
                name="Enterprise Breakout",
                description="Enterprise adoption surge with strong fundamentals",
                conditions=ConditionGroup(
                    conditions=[
                        Condition("eis", Operator.GTE, 75),
                        Condition("tms", Operator.GTE, 65),
                    ],
                    logic=LogicOp.AND,
                ),
                alert_type=AlertType.DIVERGENCE,
                severity=AlertSeverity.CRITICAL,
                category=AlertCategory.OPPORTUNITY,
                channels=["discord", "email", "file"],
            ),
            AlertRule(
                id="high_divergence",
                name="High Signal Divergence",
                description="Large divergence between any signal pairs",
                conditions=ConditionGroup(
                    conditions=[
                        Condition("divergence_score", Operator.GTE, 0.5),
                    ],
                    logic=LogicOp.AND,
                ),
                alert_type=AlertType.DIVERGENCE,
                severity=AlertSeverity.MEDIUM,
                category=AlertCategory.WATCH,
                channels=["file"],
            ),
        ]
        
        for rule in default_rules:
            self.rules[rule.id] = rule
        
        self.save_rules()
        logger.info(f"Created {len(default_rules)} default rules")
    
    def save_rules(self) -> None:
        """Save rules to config file."""
        self.rules_path.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "version": "1.0",
            "updated_at": datetime.now().isoformat(),
            "rules": [rule.to_dict() for rule in self.rules.values()],
        }
        
        with open(self.rules_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved {len(self.rules)} rules to {self.rules_path}")
    
    def add_rule(self, rule: AlertRule) -> None:
        """Add a new rule."""
        rule.created_at = datetime.now()
        rule.updated_at = datetime.now()
        self.rules[rule.id] = rule
        self.save_rules()
        logger.info(f"Added rule: {rule.name} ({rule.id})")
    
    def update_rule(self, rule: AlertRule) -> None:
        """Update an existing rule."""
        rule.updated_at = datetime.now()
        self.rules[rule.id] = rule
        self.save_rules()
        logger.info(f"Updated rule: {rule.name} ({rule.id})")
    
    def delete_rule(self, rule_id: str) -> bool:
        """Delete a rule by ID."""
        if rule_id in self.rules:
            del self.rules[rule_id]
            self.save_rules()
            logger.info(f"Deleted rule: {rule_id}")
            return True
        return False
    
    def get_rule(self, rule_id: str) -> Optional[AlertRule]:
        """Get rule by ID."""
        return self.rules.get(rule_id)
    
    def get_enabled_rules(self) -> List[AlertRule]:
        """Get all enabled rules sorted by priority."""
        return sorted(
            [r for r in self.rules.values() if r.enabled],
            key=lambda r: -r.priority  # Higher priority first
        )
    
    def evaluate_entity(
        self,
        entity_id: str,
        entity_name: str,
        signals: Dict[str, float],
    ) -> List[Alert]:
        """
        Evaluate all rules against an entity's signals.
        
        Args:
            entity_id: Entity identifier
            entity_name: Display name
            signals: Signal values dict
        
        Returns:
            List of generated alerts
        """
        alerts = []
        
        for rule in self.get_enabled_rules():
            if rule.evaluate(entity_id, entity_name, signals):
                alert = self._generate_alert_from_rule(
                    rule, entity_id, entity_name, signals
                )
                if alert:
                    alerts.append(alert)
                    
                    # Update rule stats
                    rule.times_triggered += 1
                    rule.last_triggered = datetime.now()
        
        # Save updated stats
        if alerts:
            self.save_rules()
        
        return alerts
    
    def _generate_alert_from_rule(
        self,
        rule: AlertRule,
        entity_id: str,
        entity_name: str,
        signals: Dict[str, float],
    ) -> Optional[Alert]:
        """Generate alert from triggered rule."""
        title = rule.format_title(entity_name, signals)
        message = rule.format_message(entity_name, signals)
        
        # Extract relevant signal values
        signal_names = self._extract_signal_names(rule.conditions)
        relevant_signals = {k: v for k, v in signals.items() if k in signal_names}
        
        return self.alert_engine.create_alert(
            alert_type=rule.alert_type,
            entity_id=entity_id,
            entity_name=entity_name,
            severity=rule.severity,
            title=title,
            message=message,
            data={
                "rule_name": rule.name,
                "signals": relevant_signals,
                "conditions": rule.conditions.describe(),
            },
            category=rule.category,
            rule_id=rule.id,
            source_signals=list(relevant_signals.keys()),
        )
    
    def _extract_signal_names(
        self, 
        conditions: Union[Condition, ConditionGroup]
    ) -> List[str]:
        """Extract all signal names from conditions."""
        names = []
        
        if isinstance(conditions, Condition):
            names.append(conditions.signal)
        elif isinstance(conditions, ConditionGroup):
            for cond in conditions.conditions:
                names.extend(self._extract_signal_names(cond))
        
        return names
    
    def evaluate_batch(
        self,
        entities: List[Dict[str, Any]],
    ) -> Dict[str, List[Alert]]:
        """
        Evaluate rules for multiple entities.
        
        Args:
            entities: List of dicts with entity_id, entity_name, and signal values
        
        Returns:
            Dict mapping entity_id to list of alerts
        """
        results = {}
        
        for entity in entities:
            entity_id = entity.get("entity_id", entity.get("id"))
            entity_name = entity.get("entity_name", entity.get("name", entity_id))
            
            # Collect all signal values
            signals = {}
            for key, value in entity.items():
                if key not in ("entity_id", "entity_name", "id", "name") and isinstance(value, (int, float)):
                    signals[key] = float(value)
            
            alerts = self.evaluate_entity(entity_id, entity_name, signals)
            if alerts:
                results[entity_id] = alerts
        
        return results
    
    def get_stats(self) -> Dict[str, Any]:
        """Get rule statistics."""
        enabled_rules = self.get_enabled_rules()
        
        return {
            "total_rules": len(self.rules),
            "enabled_rules": len(enabled_rules),
            "rules_by_severity": {
                sev.value: len([r for r in self.rules.values() if r.severity == sev])
                for sev in AlertSeverity
            },
            "rules_by_type": {
                typ.value: len([r for r in self.rules.values() if r.alert_type == typ])
                for typ in AlertType
            },
            "total_triggers": sum(r.times_triggered for r in self.rules.values()),
            "most_triggered": sorted(
                [{"id": r.id, "name": r.name, "count": r.times_triggered} 
                 for r in self.rules.values()],
                key=lambda x: -x["count"]
            )[:5],
        }


def create_rule_from_natural_language(description: str) -> Optional[AlertRule]:
    """
    Parse natural language rule description into AlertRule.
    
    Examples:
        "Alert when NVDA media_score > 8 AND momentum_7d > 20%"
        "Alert when any entity has divergence_score > 0.5"
    
    This is a simple parser - for complex rules, use the structured API.
    """
    import re
    
    description = description.lower()
    
    # Extract conditions
    conditions = []
    
    # Pattern: signal_name operator value
    pattern = r'(\w+)\s*(>|>=|<|<=|==|!=)\s*([\d.]+)%?'
    matches = re.findall(pattern, description)
    
    for signal, op, value in matches:
        op_map = {
            ">": Operator.GT,
            ">=": Operator.GTE,
            "<": Operator.LT,
            "<=": Operator.LTE,
            "==": Operator.EQ,
            "!=": Operator.NEQ,
        }
        conditions.append(Condition(
            signal=signal,
            operator=op_map.get(op, Operator.GT),
            value=float(value),
        ))
    
    if not conditions:
        return None
    
    # Determine logic
    logic = LogicOp.AND if " and " in description else LogicOp.OR
    
    # Determine severity
    if "critical" in description:
        severity = AlertSeverity.CRITICAL
    elif "high" in description or "urgent" in description:
        severity = AlertSeverity.HIGH
    elif "low" in description:
        severity = AlertSeverity.LOW
    else:
        severity = AlertSeverity.MEDIUM
    
    # Determine category
    if "risk" in description or "warning" in description:
        category = AlertCategory.RISK
    elif "opportunity" in description:
        category = AlertCategory.OPPORTUNITY
    else:
        category = AlertCategory.WATCH
    
    return AlertRule(
        id=str(uuid.uuid4())[:8],
        name=f"Custom Rule: {description[:50]}",
        description=description,
        conditions=ConditionGroup(conditions=conditions, logic=logic),
        severity=severity,
        category=category,
        created_by="user",
    )


if __name__ == "__main__":
    # Test the rules engine
    engine = AlertRulesEngine()
    
    print(f"Loaded {len(engine.rules)} rules")
    
    # Test evaluation
    test_signals = {
        "tms": 90,
        "ccs": 30,
        "nas": 85,
        "eis": 60,
        "momentum_7d": 35,
        "divergence_score": 0.6,
    }
    
    alerts = engine.evaluate_entity(
        entity_id="test-company",
        entity_name="Test Company",
        signals=test_signals,
    )
    
    print(f"\nGenerated {len(alerts)} alerts:")
    for alert in alerts:
        print(f"  [{alert.severity.value}] {alert.title}")
    
    print(f"\nStats: {engine.get_stats()}")
