"""
Correlation Analysis API Endpoints

REST API for cross-entity correlation analysis:
- GET /api/v1/correlations/matrix - Full correlation matrix
- GET /api/v1/correlations/entity/{id} - Correlations for one entity
- GET /api/v1/correlations/lead-lag - Lead-lag relationships
- GET /api/v1/correlations/sectors - Sector correlation heatmap
- GET /api/v1/correlations/rolling - Rolling correlation history
- POST /api/v1/correlations/propagation - Simulate signal propagation
- GET /api/v1/correlations/warnings - Active early warning signals
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, date
import json

from utils.correlation_analysis import (
    CorrelationAnalyzer,
    EntityCorrelation,
    SignalCorrelation,
    LeadLagRelationship,
    SECTOR_DEFINITIONS,
    run_full_correlation_analysis
)
from utils.rolling_correlations import (
    RollingCorrelationTracker,
    CorrelationRegimeChange,
    CorrelationDivergenceAlert,
    run_rolling_correlation_scan
)
from utils.signal_propagation import (
    SignalPropagationEngine,
    PropagationPrediction,
    EarlyWarningSignal,
    simulate_propagation
)


router = APIRouter(prefix="/api/v1/correlations", tags=["correlations"])


# =============================================================================
# Request/Response Models
# =============================================================================

class CorrelationMatrixResponse(BaseModel):
    """Response for correlation matrix endpoint."""
    signal_type: str
    entities: List[str]
    matrix: Dict[str, Dict[str, float]]
    generated_at: str


class EntityCorrelationResponse(BaseModel):
    """Response for entity correlations."""
    entity_id: str
    signal_type: str
    correlations: List[Dict[str, Any]]
    lead_lag: Dict[str, List[Dict[str, Any]]]


class LeadLagResponse(BaseModel):
    """Response for lead-lag relationships."""
    relationships: List[Dict[str, Any]]
    total_count: int


class SectorHeatmapResponse(BaseModel):
    """Response for sector correlations."""
    sectors: List[str]
    matrix: Dict[str, Dict[str, float]]
    sector_definitions: Dict[str, Dict[str, Any]]


class RollingCorrelationResponse(BaseModel):
    """Response for rolling correlation history."""
    entity_a: str
    entity_b: str
    signal_type: str
    window_days: int
    history: List[Dict[str, Any]]


class PropagationRequest(BaseModel):
    """Request for signal propagation simulation."""
    trigger_entity: str = Field(..., description="Entity showing the signal move")
    trigger_direction: str = Field("positive", description="Direction of move: 'positive' or 'negative'")
    trigger_magnitude: float = Field(0.5, ge=0, le=1, description="Normalized magnitude 0-1")
    signal_type: str = Field("composite", description="Signal type to propagate")
    max_depth: int = Field(3, ge=1, le=5, description="Maximum propagation depth")


class PropagationResponse(BaseModel):
    """Response for signal propagation."""
    trigger: Dict[str, Any]
    affected_count: int
    top_affected: List[Dict[str, Any]]
    sector_impacts: Dict[str, float]
    generated_at: str


class AlertsResponse(BaseModel):
    """Response for divergence alerts and warnings."""
    divergence_alerts: List[Dict[str, Any]]
    early_warnings: List[Dict[str, Any]]
    regime_changes: List[Dict[str, Any]]


class AnalysisRunResponse(BaseModel):
    """Response for running correlation analysis."""
    status: str
    entities_analyzed: int
    signal_types: List[str]
    lead_lag_count: int
    sector_correlations_computed: bool
    message: str


# =============================================================================
# Endpoints
# =============================================================================

@router.get("/matrix", response_model=CorrelationMatrixResponse)
async def get_correlation_matrix(
    signal_type: str = Query("composite", description="Signal type: composite, media, technical, financial, product"),
    min_correlation: float = Query(0.0, ge=-1.0, le=1.0, description="Minimum absolute correlation to include")
):
    """
    Get the full entity correlation matrix.
    
    Returns correlation matrix for all tracked entities.
    Use min_correlation to filter weak correlations.
    """
    try:
        analyzer = CorrelationAnalyzer()
        matrix = analyzer.get_full_correlation_matrix(signal_type)
        
        if matrix.empty:
            raise HTTPException(
                status_code=404,
                detail="No correlation data available. Run correlation analysis first."
            )
        
        # Filter by minimum correlation if specified
        if min_correlation > 0:
            for i in range(len(matrix.index)):
                for j in range(len(matrix.columns)):
                    if abs(matrix.iloc[i, j]) < min_correlation and i != j:
                        matrix.iloc[i, j] = 0.0
        
        return CorrelationMatrixResponse(
            signal_type=signal_type,
            entities=matrix.index.tolist(),
            matrix=matrix.to_dict(),
            generated_at=datetime.utcnow().isoformat()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/entity/{entity_id}", response_model=EntityCorrelationResponse)
async def get_entity_correlations(
    entity_id: str,
    signal_type: str = Query("composite", description="Signal type"),
    min_correlation: float = Query(0.3, ge=0.0, le=1.0, description="Minimum absolute correlation")
):
    """
    Get all correlations for a specific entity.
    
    Returns entities correlated with the specified entity,
    plus lead-lag relationships.
    """
    try:
        analyzer = CorrelationAnalyzer()
        
        # Get correlations
        correlations = analyzer.get_entity_correlations(
            entity_id.lower(),
            signal_type,
            min_correlation
        )
        
        # Get lead-lag relationships
        lead_lag = analyzer.get_lead_lag_for_entity(entity_id.lower())
        
        return EntityCorrelationResponse(
            entity_id=entity_id,
            signal_type=signal_type,
            correlations=[c.to_dict() for c in correlations],
            lead_lag={
                "as_leader": [r.to_dict() for r in lead_lag.get("as_leader", [])],
                "as_follower": [r.to_dict() for r in lead_lag.get("as_follower", [])]
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/lead-lag", response_model=LeadLagResponse)
async def get_lead_lag_relationships(
    min_predictive_power: float = Query(0.1, ge=0.0, le=1.0, description="Minimum predictive power"),
    min_confidence: str = Query("low", description="Minimum confidence: low, medium, high"),
    limit: int = Query(50, ge=1, le=200, description="Maximum results")
):
    """
    Get all significant lead-lag relationships.
    
    Returns pairs where one entity's signals consistently lead another's.
    Useful for identifying early warning indicators.
    """
    try:
        analyzer = CorrelationAnalyzer()
        
        relationships = analyzer.get_all_lead_lag_relationships(
            min_predictive_power=min_predictive_power,
            min_confidence=min_confidence
        )
        
        return LeadLagResponse(
            relationships=[r.to_dict() for r in relationships[:limit]],
            total_count=len(relationships)
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sectors", response_model=SectorHeatmapResponse)
async def get_sector_correlations():
    """
    Get sector-level correlation heatmap.
    
    Shows how different AI sectors (infrastructure, applications, etc.)
    correlate with each other.
    """
    try:
        analyzer = CorrelationAnalyzer()
        matrix = analyzer.get_sector_heatmap()
        
        if matrix.empty:
            # Try computing if not available
            matrix = analyzer.sector_heatmap()
        
        if matrix.empty:
            raise HTTPException(
                status_code=404,
                detail="No sector correlation data available."
            )
        
        # Add sector definitions to response
        sector_info = {
            k: {
                "description": v["description"],
                "entity_count": len(v["entities"])
            }
            for k, v in SECTOR_DEFINITIONS.items()
        }
        
        return SectorHeatmapResponse(
            sectors=matrix.index.tolist(),
            matrix=matrix.to_dict(),
            sector_definitions=sector_info
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rolling")
async def get_rolling_correlations(
    entity_a: str = Query(..., description="First entity"),
    entity_b: str = Query(..., description="Second entity"),
    signal_type: str = Query("composite", description="Signal type"),
    window_days: int = Query(30, ge=7, le=180, description="Rolling window size"),
    history_days: int = Query(90, ge=30, le=365, description="History to return")
) -> RollingCorrelationResponse:
    """
    Get rolling correlation history between two entities.
    
    Shows how the correlation has changed over time.
    Useful for detecting regime changes and correlation breakdowns.
    """
    try:
        tracker = RollingCorrelationTracker()
        
        # Try to get from database first
        df = tracker.get_rolling_correlation_history(
            entity_a.lower(), entity_b.lower(),
            signal_type, window_days, history_days
        )
        
        if df.empty:
            # Calculate if not available
            correlations = tracker.calculate_rolling_correlation_series(
                entity_a.lower(), entity_b.lower(),
                signal_type, window_days, history_days
            )
            history = [{"date": c.date.isoformat(), "correlation": c.correlation} for c in correlations]
        else:
            history = [
                {"date": dt.strftime("%Y-%m-%d"), "correlation": row["correlation"]}
                for dt, row in df.iterrows()
            ]
        
        return RollingCorrelationResponse(
            entity_a=entity_a,
            entity_b=entity_b,
            signal_type=signal_type,
            window_days=window_days,
            history=history
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/propagation", response_model=PropagationResponse)
async def simulate_signal_propagation(request: PropagationRequest):
    """
    Simulate signal propagation from an entity move.
    
    When an entity's signals move, predict which other entities
    will be affected, with expected timing and magnitude.
    """
    try:
        result = simulate_propagation(
            trigger_entity=request.trigger_entity,
            trigger_direction=request.trigger_direction,
            trigger_magnitude=request.trigger_magnitude
        )
        
        return PropagationResponse(**result)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/warnings", response_model=AlertsResponse)
async def get_correlation_alerts(
    target_entity: Optional[str] = Query(None, description="Filter by target entity"),
    alert_level: Optional[str] = Query(None, description="Filter by level: warning, critical"),
    days: int = Query(7, ge=1, le=30, description="Lookback days for regime changes")
):
    """
    Get active correlation alerts and warnings.
    
    Returns:
    - Divergence alerts: When correlations are breaking down
    - Early warnings: When leading indicators are signaling
    - Regime changes: Recent correlation regime shifts
    """
    try:
        tracker = RollingCorrelationTracker()
        engine = SignalPropagationEngine()
        
        # Get divergence alerts
        divergence_alerts = tracker.get_active_divergence_alerts(alert_level)
        
        # Get early warnings
        early_warnings = engine.get_active_warnings(target_entity)
        
        # Get recent regime changes
        regime_changes = tracker.get_recent_regime_changes(days)
        
        return AlertsResponse(
            divergence_alerts=[a.to_dict() for a in divergence_alerts],
            early_warnings=[w.to_dict() for w in early_warnings],
            regime_changes=[r.to_dict() for r in regime_changes]
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dependencies/{entity_id}")
async def get_entity_dependencies(entity_id: str):
    """
    Get dependency information for an entity.
    
    Shows which entities this one affects (leads) and is affected by (follows).
    """
    try:
        engine = SignalPropagationEngine()
        deps = engine.get_entity_dependencies(entity_id)
        return deps
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze", response_model=AnalysisRunResponse)
async def run_correlation_analysis(
    entities: Optional[List[str]] = Query(None, description="Entities to analyze (None = all)"),
    signal_types: Optional[List[str]] = Query(None, description="Signal types to analyze")
):
    """
    Run full correlation analysis.
    
    Calculates correlation matrices, lead-lag relationships, and sector correlations.
    This is a long-running operation for many entities.
    """
    try:
        result = run_full_correlation_analysis(
            entities=entities,
            signal_types=signal_types
        )
        
        return AnalysisRunResponse(
            status="completed",
            entities_analyzed=result["entities_analyzed"],
            signal_types=result["signal_types"],
            lead_lag_count=result["lead_lag_count"],
            sector_correlations_computed=result["sector_correlations_computed"],
            message=f"Analysis complete for {result['entities_analyzed']} entities"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ScanRequest(BaseModel):
    """Request for rolling correlation scan."""
    entity_pairs: List[List[str]] = Field(..., description="Entity pairs as [[a,b], [c,d]]")
    signal_types: Optional[List[str]] = Field(None, description="Signal types")


@router.post("/scan")
async def run_rolling_scan(request: ScanRequest):
    """
    Run rolling correlation scan for specific entity pairs.
    
    Detects regime changes and divergence alerts.
    """
    try:
        # Convert to tuple pairs
        pairs = [(p[0].lower(), p[1].lower()) for p in request.entity_pairs if len(p) == 2]
        
        if not pairs:
            raise HTTPException(
                status_code=400,
                detail="No valid entity pairs provided"
            )
        
        result = run_rolling_correlation_scan(pairs, request.signal_types)
        
        return {
            "status": "completed",
            "pairs_scanned": result["pairs_scanned"],
            "regime_changes_found": len(result["regime_changes"]),
            "divergence_alerts_found": len(result["divergence_alerts"]),
            "regime_changes": result["regime_changes"],
            "divergence_alerts": result["divergence_alerts"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
