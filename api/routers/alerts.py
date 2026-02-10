"""
Alerts API Router

REST API endpoints for alert management:
- GET /alerts - List alerts
- GET /alerts/{id} - Get alert by ID
- POST /alerts/{id}/acknowledge - Acknowledge alert
- GET /alerts/stats - Alert statistics
- GET /rules - List rules
- POST /rules - Create rule
- PUT /rules/{id} - Update rule
- DELETE /rules/{id} - Delete rule
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel, Field

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.alert_engine import (
    AlertEngine, Alert, AlertType, AlertSeverity, AlertCategory
)
from utils.alert_rules import (
    AlertRulesEngine, AlertRule, Condition, ConditionGroup, 
    Operator, LogicOp
)


router = APIRouter(prefix="/alerts", tags=["alerts"])

# Initialize engines (singleton pattern)
_alert_engine: Optional[AlertEngine] = None
_rules_engine: Optional[AlertRulesEngine] = None


def get_alert_engine() -> AlertEngine:
    global _alert_engine
    if _alert_engine is None:
        _alert_engine = AlertEngine()
    return _alert_engine


def get_rules_engine() -> AlertRulesEngine:
    global _rules_engine
    if _rules_engine is None:
        _rules_engine = AlertRulesEngine(alert_engine=get_alert_engine())
    return _rules_engine


# =============================================================================
# Request/Response Models
# =============================================================================

class AlertResponse(BaseModel):
    """Alert response model."""
    id: str
    alert_type: str
    entity_id: str
    entity_name: str
    severity: str
    category: str
    title: str
    message: str
    data: Dict[str, Any]
    rule_id: Optional[str]
    source_signals: List[str]
    created_at: str
    acknowledged: bool
    acknowledged_at: Optional[str]
    acknowledged_by: Optional[str]
    expires_at: Optional[str]
    expired: bool


class AlertListResponse(BaseModel):
    """Alert list response."""
    alerts: List[AlertResponse]
    total: int
    page: int
    page_size: int


class AlertStatsResponse(BaseModel):
    """Alert statistics response."""
    total_alerts: int
    active_alerts: int
    acknowledged_alerts: int
    alerts_24h: int
    by_severity: Dict[str, int]
    by_type: Dict[str, int]
    by_category: Dict[str, int]
    top_entities: List[Dict[str, Any]]


class ConditionModel(BaseModel):
    """Condition model for rules."""
    signal: str
    operator: str = Field(..., description=">, >=, <, <=, ==, !=, between, not_between")
    value: Any


class ConditionGroupModel(BaseModel):
    """Condition group model."""
    logic: str = "AND"
    conditions: List[ConditionModel]


class RuleCreateRequest(BaseModel):
    """Request to create a rule."""
    name: str
    description: str = ""
    conditions: ConditionGroupModel
    alert_type: str = "threshold"
    severity: str = "medium"
    category: str = "watch"
    channels: List[str] = ["file"]
    entity_filter: Optional[str] = None
    entity_whitelist: List[str] = []
    entity_blacklist: List[str] = []
    enabled: bool = True
    priority: int = 50
    cooldown_hours: int = 24


class RuleUpdateRequest(BaseModel):
    """Request to update a rule."""
    name: Optional[str] = None
    description: Optional[str] = None
    conditions: Optional[ConditionGroupModel] = None
    alert_type: Optional[str] = None
    severity: Optional[str] = None
    category: Optional[str] = None
    channels: Optional[List[str]] = None
    entity_filter: Optional[str] = None
    entity_whitelist: Optional[List[str]] = None
    entity_blacklist: Optional[List[str]] = None
    enabled: Optional[bool] = None
    priority: Optional[int] = None
    cooldown_hours: Optional[int] = None


class RuleResponse(BaseModel):
    """Rule response model."""
    id: str
    name: str
    description: str
    conditions: Dict[str, Any]
    alert_type: str
    severity: str
    category: str
    channels: List[str]
    entity_filter: Optional[str]
    entity_whitelist: List[str]
    entity_blacklist: List[str]
    enabled: bool
    priority: int
    cooldown_hours: int
    times_triggered: int
    last_triggered: Optional[str]
    created_at: str
    updated_at: str


# =============================================================================
# Helper Functions
# =============================================================================

def alert_to_response(alert: Alert) -> AlertResponse:
    """Convert Alert to response model."""
    return AlertResponse(
        id=alert.id,
        alert_type=alert.alert_type.value,
        entity_id=alert.entity_id,
        entity_name=alert.entity_name,
        severity=alert.severity.value,
        category=alert.category.value,
        title=alert.title,
        message=alert.message,
        data=alert.data,
        rule_id=alert.rule_id,
        source_signals=alert.source_signals,
        created_at=alert.created_at.isoformat(),
        acknowledged=alert.acknowledged,
        acknowledged_at=alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
        acknowledged_by=alert.acknowledged_by,
        expires_at=alert.expires_at.isoformat() if alert.expires_at else None,
        expired=alert.expired,
    )


def rule_to_response(rule: AlertRule) -> RuleResponse:
    """Convert AlertRule to response model."""
    return RuleResponse(
        id=rule.id,
        name=rule.name,
        description=rule.description,
        conditions=rule.conditions.to_dict(),
        alert_type=rule.alert_type.value,
        severity=rule.severity.value,
        category=rule.category.value,
        channels=rule.channels,
        entity_filter=rule.entity_filter,
        entity_whitelist=rule.entity_whitelist,
        entity_blacklist=rule.entity_blacklist,
        enabled=rule.enabled,
        priority=rule.priority,
        cooldown_hours=rule.cooldown_hours,
        times_triggered=rule.times_triggered,
        last_triggered=rule.last_triggered.isoformat() if rule.last_triggered else None,
        created_at=rule.created_at.isoformat() if isinstance(rule.created_at, datetime) else rule.created_at,
        updated_at=rule.updated_at.isoformat() if isinstance(rule.updated_at, datetime) else rule.updated_at,
    )


def conditions_from_model(model: ConditionGroupModel) -> ConditionGroup:
    """Convert condition model to ConditionGroup."""
    conditions = []
    for c in model.conditions:
        conditions.append(Condition(
            signal=c.signal,
            operator=Operator(c.operator),
            value=c.value,
        ))
    
    return ConditionGroup(
        conditions=conditions,
        logic=LogicOp(model.logic.upper()),
    )


# =============================================================================
# Alert Endpoints
# =============================================================================

@router.get("", response_model=AlertListResponse)
async def list_alerts(
    entity_id: Optional[str] = Query(None, description="Filter by entity ID"),
    alert_type: Optional[str] = Query(None, description="Filter by alert type"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    category: Optional[str] = Query(None, description="Filter by category"),
    acknowledged: Optional[bool] = Query(None, description="Filter by acknowledged status"),
    hours: int = Query(24, description="Hours to look back"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """
    List alerts with filtering and pagination.
    """
    engine = get_alert_engine()
    
    # Get alerts based on filter
    if acknowledged is False:
        # Active alerts only
        alerts = engine.get_active_alerts(
            entity_id=entity_id,
            alert_type=AlertType(alert_type) if alert_type else None,
            severity=AlertSeverity(severity) if severity else None,
            category=AlertCategory(category) if category else None,
            limit=1000,
        )
    else:
        # Recent alerts including acknowledged
        alerts = engine.get_recent_alerts(hours=hours, limit=1000)
        
        # Apply filters
        if entity_id:
            alerts = [a for a in alerts if a.entity_id == entity_id]
        if alert_type:
            alerts = [a for a in alerts if a.alert_type.value == alert_type]
        if severity:
            alerts = [a for a in alerts if a.severity.value == severity]
        if category:
            alerts = [a for a in alerts if a.category.value == category]
        if acknowledged is not None:
            alerts = [a for a in alerts if a.acknowledged == acknowledged]
    
    # Paginate
    total = len(alerts)
    start = (page - 1) * page_size
    end = start + page_size
    page_alerts = alerts[start:end]
    
    return AlertListResponse(
        alerts=[alert_to_response(a) for a in page_alerts],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/stats", response_model=AlertStatsResponse)
async def get_alert_stats():
    """
    Get alert statistics.
    """
    engine = get_alert_engine()
    stats = engine.get_stats()
    
    return AlertStatsResponse(**stats)


@router.get("/{alert_id}", response_model=AlertResponse)
async def get_alert(alert_id: str):
    """
    Get a specific alert by ID.
    """
    engine = get_alert_engine()
    alert = engine.get_alert(alert_id)
    
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    return alert_to_response(alert)


@router.post("/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: str,
    by: str = Query("api", description="Who acknowledged the alert"),
):
    """
    Acknowledge an alert.
    """
    engine = get_alert_engine()
    
    if not engine.get_alert(alert_id):
        raise HTTPException(status_code=404, detail="Alert not found")
    
    success = engine.acknowledge_alert(alert_id, by=by)
    
    return {"success": success, "alert_id": alert_id}


@router.post("/acknowledge-all")
async def acknowledge_all_alerts(
    entity_id: Optional[str] = Query(None),
    alert_type: Optional[str] = Query(None),
    by: str = Query("api"),
):
    """
    Acknowledge all matching alerts.
    """
    engine = get_alert_engine()
    
    count = engine.acknowledge_all(
        entity_id=entity_id,
        alert_type=AlertType(alert_type) if alert_type else None,
        by=by,
    )
    
    return {"acknowledged": count}


@router.get("/{alert_id}/history")
async def get_alert_history(alert_id: str):
    """
    Get history/audit log for an alert.
    """
    engine = get_alert_engine()
    
    if not engine.get_alert(alert_id):
        raise HTTPException(status_code=404, detail="Alert not found")
    
    history = engine.get_alert_history(alert_id)
    
    return {"alert_id": alert_id, "history": history}


# =============================================================================
# Rules Endpoints
# =============================================================================

@router.get("/rules", response_model=List[RuleResponse])
async def list_rules(
    enabled_only: bool = Query(False, description="Only return enabled rules"),
):
    """
    List all alert rules.
    """
    engine = get_rules_engine()
    
    if enabled_only:
        rules = engine.get_enabled_rules()
    else:
        rules = list(engine.rules.values())
    
    return [rule_to_response(r) for r in rules]


@router.get("/rules/stats")
async def get_rules_stats():
    """
    Get rule statistics.
    """
    engine = get_rules_engine()
    return engine.get_stats()


@router.get("/rules/{rule_id}", response_model=RuleResponse)
async def get_rule(rule_id: str):
    """
    Get a specific rule by ID.
    """
    engine = get_rules_engine()
    rule = engine.get_rule(rule_id)
    
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    
    return rule_to_response(rule)


@router.post("/rules", response_model=RuleResponse, status_code=201)
async def create_rule(request: RuleCreateRequest):
    """
    Create a new alert rule.
    """
    engine = get_rules_engine()
    
    # Generate ID from name
    rule_id = request.name.lower().replace(" ", "_")[:20]
    
    # Check for duplicate
    if engine.get_rule(rule_id):
        raise HTTPException(status_code=409, detail="Rule with this ID already exists")
    
    # Create rule
    rule = AlertRule(
        id=rule_id,
        name=request.name,
        description=request.description,
        conditions=conditions_from_model(request.conditions),
        alert_type=AlertType(request.alert_type),
        severity=AlertSeverity(request.severity),
        category=AlertCategory(request.category),
        channels=request.channels,
        entity_filter=request.entity_filter,
        entity_whitelist=request.entity_whitelist,
        entity_blacklist=request.entity_blacklist,
        enabled=request.enabled,
        priority=request.priority,
        cooldown_hours=request.cooldown_hours,
    )
    
    engine.add_rule(rule)
    
    return rule_to_response(rule)


@router.put("/rules/{rule_id}", response_model=RuleResponse)
async def update_rule(rule_id: str, request: RuleUpdateRequest):
    """
    Update an existing rule.
    """
    engine = get_rules_engine()
    rule = engine.get_rule(rule_id)
    
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    
    # Update fields
    if request.name is not None:
        rule.name = request.name
    if request.description is not None:
        rule.description = request.description
    if request.conditions is not None:
        rule.conditions = conditions_from_model(request.conditions)
    if request.alert_type is not None:
        rule.alert_type = AlertType(request.alert_type)
    if request.severity is not None:
        rule.severity = AlertSeverity(request.severity)
    if request.category is not None:
        rule.category = AlertCategory(request.category)
    if request.channels is not None:
        rule.channels = request.channels
    if request.entity_filter is not None:
        rule.entity_filter = request.entity_filter
    if request.entity_whitelist is not None:
        rule.entity_whitelist = request.entity_whitelist
    if request.entity_blacklist is not None:
        rule.entity_blacklist = request.entity_blacklist
    if request.enabled is not None:
        rule.enabled = request.enabled
    if request.priority is not None:
        rule.priority = request.priority
    if request.cooldown_hours is not None:
        rule.cooldown_hours = request.cooldown_hours
    
    engine.update_rule(rule)
    
    return rule_to_response(rule)


@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: str):
    """
    Delete a rule.
    """
    engine = get_rules_engine()
    
    if not engine.get_rule(rule_id):
        raise HTTPException(status_code=404, detail="Rule not found")
    
    success = engine.delete_rule(rule_id)
    
    return {"success": success, "rule_id": rule_id}


@router.post("/rules/{rule_id}/test")
async def test_rule(
    rule_id: str,
    signals: Dict[str, float] = Body(..., description="Signal values to test"),
):
    """
    Test a rule against given signal values.
    """
    engine = get_rules_engine()
    rule = engine.get_rule(rule_id)
    
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    
    # Evaluate
    result = rule.conditions.evaluate(signals)
    
    return {
        "rule_id": rule_id,
        "would_trigger": result,
        "signals": signals,
        "conditions": rule.conditions.describe(),
    }


# =============================================================================
# Notification Channel Endpoints
# =============================================================================

@router.get("/channels")
async def list_channels():
    """
    List available notification channels.
    """
    from utils.notifications import NotificationManager
    
    manager = NotificationManager()
    
    return {
        "channels": manager.get_available_channels(),
        "status": manager.get_channel_status(),
    }
