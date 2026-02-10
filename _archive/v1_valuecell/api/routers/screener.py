"""
Screener API Router

REST API endpoints for running and managing custom screeners.

Endpoints:
- POST /api/v1/screener/run - Run a screener
- POST /api/v1/screener/query - Run a DSL query
- GET /api/v1/screener/presets - List preset screeners
- GET /api/v1/screener/presets/{name} - Get preset details
- POST /api/v1/screener/save - Save a custom screener
- GET /api/v1/screener/list - List all screeners
- GET /api/v1/screener/{name} - Get screener definition
- DELETE /api/v1/screener/{name} - Delete a screener
- POST /api/v1/screener/validate - Validate DSL query
- GET /api/v1/screener/fields - Get available fields
"""

from typing import List, Optional, Dict, Any, Union
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Depends, Body
from pydantic import BaseModel, Field
from loguru import logger

import sys
_app_dir = Path(__file__).parent.parent.parent
if str(_app_dir) not in sys.path:
    sys.path.insert(0, str(_app_dir))

from utils.screener_engine import (
    ScreenerEngine, Criterion, CriteriaGroup, Screener, ScreenerResult,
    FilterOperator, CriterionType, LogicalOperator, SCREENABLE_FIELDS
)
from utils.screener_dsl import (
    parse_query, validate_query, explain_query, to_sql_where, DSLParseError
)


# =============================================================================
# Router Setup
# =============================================================================

router = APIRouter(prefix="/api/v1/screener", tags=["screener"])

_engine: Optional[ScreenerEngine] = None


def get_engine() -> ScreenerEngine:
    """Get or create the screener engine."""
    global _engine
    if _engine is None:
        _engine = ScreenerEngine()
    return _engine


# =============================================================================
# Request/Response Models
# =============================================================================

class CriterionRequest(BaseModel):
    """Single criterion in a request."""
    field: str
    operator: str  # e.g., ">", ">=", "=", "in"
    value: Any
    compare_field: Optional[str] = None
    type: Optional[str] = "score"  # score, momentum, category, signal, date, comparison


class ScreenerRunRequest(BaseModel):
    """Request to run a screener."""
    criteria: List[CriterionRequest]
    limit: int = Field(default=100, ge=1, le=1000)
    sort_by: str = "composite_score"
    sort_order: str = Field(default="desc", pattern="^(asc|desc)$")


class DSLQueryRequest(BaseModel):
    """Request to run a DSL query."""
    query: str
    limit: int = Field(default=100, ge=1, le=1000)
    sort_by: str = "composite_score"
    sort_order: str = Field(default="desc", pattern="^(asc|desc)$")


class SaveScreenerRequest(BaseModel):
    """Request to save a screener."""
    name: str
    description: Optional[str] = None
    criteria: List[CriterionRequest]
    sort_by: str = "composite_score"
    sort_order: str = "desc"
    limit: int = 100
    tags: List[str] = Field(default_factory=list)
    category: Optional[str] = None


class ScreenerResponse(BaseModel):
    """Standard screener response."""
    screener_name: str
    total_entities: int
    matching_entities: int
    results: List[Dict[str, Any]]
    execution_time_ms: float
    criteria_summary: str
    run_at: str


class ScreenerInfoResponse(BaseModel):
    """Screener metadata response."""
    name: str
    description: Optional[str]
    is_preset: bool
    criteria_count: int
    sort_by: Optional[str]
    sort_order: str
    limit: int
    category: Optional[str]
    tags: List[str]
    created_at: Optional[str]
    last_run_at: Optional[str]
    last_match_count: Optional[int]


class ScreenerListResponse(BaseModel):
    """List of screeners response."""
    screeners: List[ScreenerInfoResponse]
    total: int


class ValidationResponse(BaseModel):
    """Query validation response."""
    valid: bool
    query: str
    error: Optional[str] = None
    sql: Optional[str] = None
    explanation: Optional[Dict[str, Any]] = None


class FieldInfoResponse(BaseModel):
    """Field information response."""
    fields: Dict[str, Dict[str, Any]]
    categories: List[str]


# =============================================================================
# Endpoints
# =============================================================================

@router.post("/run", response_model=ScreenerResponse)
async def run_screener(
    request: ScreenerRunRequest,
    engine: ScreenerEngine = Depends(get_engine)
):
    """
    Run a screener with specified criteria.
    
    Example:
    ```json
    {
        "criteria": [
            {"field": "media_score", "operator": ">", "value": 7},
            {"field": "momentum_7d", "operator": ">", "value": 10}
        ],
        "limit": 50,
        "sort_by": "composite_score",
        "sort_order": "desc"
    }
    ```
    """
    try:
        # Convert request criteria to engine format
        criteria = _convert_criteria(request.criteria)
        
        # Run screener
        result = engine.screen(
            criteria=criteria,
            limit=request.limit,
            sort_by=request.sort_by,
            sort_order=request.sort_order
        )
        
        return ScreenerResponse(
            screener_name=result.screener_name,
            total_entities=result.total_entities,
            matching_entities=result.matching_entities,
            results=result.results,
            execution_time_ms=result.execution_time_ms,
            criteria_summary=result.criteria_summary,
            run_at=result.run_at.isoformat()
        )
        
    except Exception as e:
        logger.error(f"Error running screener: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/query", response_model=ScreenerResponse)
async def run_dsl_query(
    request: DSLQueryRequest,
    engine: ScreenerEngine = Depends(get_engine)
):
    """
    Run a screener using DSL query syntax.
    
    Example queries:
    - `media_score > 7 AND momentum_7d > 10%`
    - `sector IN ("ai-foundation", "ai-infrastructure")`
    - `media_score > technical_score`
    - `has_divergence = true AND divergence_strength > 0.5`
    """
    try:
        # Parse DSL query
        group = parse_query(request.query)
        
        # Run screener
        result = engine.screen_with_group(
            criteria_group=group,
            limit=request.limit,
            sort_by=request.sort_by,
            sort_order=request.sort_order
        )
        
        return ScreenerResponse(
            screener_name=f"dsl_query",
            total_entities=result.total_entities,
            matching_entities=result.matching_entities,
            results=result.results,
            execution_time_ms=result.execution_time_ms,
            criteria_summary=request.query,
            run_at=result.run_at.isoformat()
        )
        
    except DSLParseError as e:
        raise HTTPException(status_code=400, detail=f"Query parse error: {e}")
    except Exception as e:
        logger.error(f"Error running DSL query: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/presets", response_model=ScreenerListResponse)
async def list_presets(
    category: Optional[str] = Query(None, description="Filter by category"),
    engine: ScreenerEngine = Depends(get_engine)
):
    """List all preset screeners."""
    presets = engine.get_preset_screeners()
    
    # Filter by category if specified
    if category:
        presets = [p for p in presets if p.category and p.category.lower() == category.lower()]
    
    screener_infos = [
        ScreenerInfoResponse(
            name=p.name,
            description=p.description,
            is_preset=True,
            criteria_count=len(p.criteria),
            sort_by=p.sort_by,
            sort_order=p.sort_order,
            limit=p.limit,
            category=p.category,
            tags=p.tags,
            created_at=None,
            last_run_at=p.last_run_at.isoformat() if p.last_run_at else None,
            last_match_count=p.last_match_count
        )
        for p in presets
    ]
    
    return ScreenerListResponse(
        screeners=screener_infos,
        total=len(screener_infos)
    )


@router.get("/presets/{name}")
async def get_preset(
    name: str,
    engine: ScreenerEngine = Depends(get_engine)
):
    """Get a preset screener definition."""
    preset = engine.get_preset_screener(name)
    
    if not preset:
        raise HTTPException(status_code=404, detail=f"Preset '{name}' not found")
    
    return {
        "name": preset.name,
        "description": preset.description,
        "criteria": [c.dict() for c in preset.criteria],
        "sort_by": preset.sort_by,
        "sort_order": preset.sort_order,
        "limit": preset.limit,
        "category": preset.category,
        "tags": preset.tags
    }


@router.post("/presets/{name}/run", response_model=ScreenerResponse)
async def run_preset(
    name: str,
    limit: int = Query(default=100, ge=1, le=1000),
    engine: ScreenerEngine = Depends(get_engine)
):
    """Run a preset screener by name."""
    try:
        result = engine.run_screener(name)
        
        return ScreenerResponse(
            screener_name=result.screener_name,
            total_entities=result.total_entities,
            matching_entities=result.matching_entities,
            results=result.results[:limit],
            execution_time_ms=result.execution_time_ms,
            criteria_summary=result.criteria_summary,
            run_at=result.run_at.isoformat()
        )
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error running preset: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/save", response_model=ScreenerInfoResponse)
async def save_screener(
    request: SaveScreenerRequest,
    engine: ScreenerEngine = Depends(get_engine)
):
    """Save a custom screener."""
    try:
        # Convert criteria
        criteria = _convert_criteria(request.criteria)
        
        # Create screener
        screener = Screener(
            name=request.name,
            description=request.description,
            criteria=criteria,
            sort_by=request.sort_by,
            sort_order=request.sort_order,
            limit=request.limit,
            tags=request.tags,
            category=request.category,
            is_preset=False
        )
        
        # Save
        saved = engine.save_screener(request.name, criteria, screener)
        
        return ScreenerInfoResponse(
            name=saved.name,
            description=saved.description,
            is_preset=False,
            criteria_count=len(saved.criteria),
            sort_by=saved.sort_by,
            sort_order=saved.sort_order,
            limit=saved.limit,
            category=saved.category,
            tags=saved.tags,
            created_at=saved.created_at.isoformat(),
            last_run_at=None,
            last_match_count=None
        )
        
    except Exception as e:
        logger.error(f"Error saving screener: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/list", response_model=ScreenerListResponse)
async def list_screeners(
    include_presets: bool = Query(default=True),
    category: Optional[str] = Query(None),
    engine: ScreenerEngine = Depends(get_engine)
):
    """List all screeners (custom and presets)."""
    screeners = engine.list_screeners(include_presets=include_presets)
    
    # Filter by category if specified
    if category:
        screeners = [s for s in screeners if s.get("category", "").lower() == category.lower()]
    
    screener_infos = [
        ScreenerInfoResponse(
            name=s["name"],
            description=s.get("description"),
            is_preset=s.get("is_preset", False),
            criteria_count=s.get("criteria_count", 0),
            sort_by=s.get("sort_by"),
            sort_order=s.get("sort_order", "desc"),
            limit=s.get("limit", 100),
            category=s.get("category"),
            tags=s.get("tags", []),
            created_at=s.get("created_at"),
            last_run_at=s.get("last_run_at"),
            last_match_count=s.get("last_match_count")
        )
        for s in screeners
    ]
    
    return ScreenerListResponse(
        screeners=screener_infos,
        total=len(screener_infos)
    )


@router.get("/{name}")
async def get_screener(
    name: str,
    engine: ScreenerEngine = Depends(get_engine)
):
    """Get a screener definition by name."""
    screener = engine.load_screener(name)
    
    if not screener:
        raise HTTPException(status_code=404, detail=f"Screener '{name}' not found")
    
    return {
        "name": screener.name,
        "description": screener.description,
        "criteria": [c.dict() for c in screener.criteria],
        "criteria_group": screener.criteria_group.dict() if screener.criteria_group else None,
        "sort_by": screener.sort_by,
        "sort_order": screener.sort_order,
        "limit": screener.limit,
        "is_preset": screener.is_preset,
        "category": screener.category,
        "tags": screener.tags,
        "created_at": screener.created_at.isoformat() if screener.created_at else None,
        "updated_at": screener.updated_at.isoformat() if screener.updated_at else None
    }


@router.delete("/{name}")
async def delete_screener(
    name: str,
    engine: ScreenerEngine = Depends(get_engine)
):
    """Delete a custom screener."""
    success = engine.delete_screener(name)
    
    if not success:
        raise HTTPException(status_code=404, detail=f"Screener '{name}' not found or cannot be deleted")
    
    return {"message": f"Screener '{name}' deleted successfully"}


@router.post("/{name}/run", response_model=ScreenerResponse)
async def run_saved_screener(
    name: str,
    limit: Optional[int] = Query(None, ge=1, le=1000),
    engine: ScreenerEngine = Depends(get_engine)
):
    """Run a saved screener by name."""
    try:
        result = engine.run_screener(name)
        
        results = result.results
        if limit:
            results = results[:limit]
        
        return ScreenerResponse(
            screener_name=result.screener_name,
            total_entities=result.total_entities,
            matching_entities=result.matching_entities,
            results=results,
            execution_time_ms=result.execution_time_ms,
            criteria_summary=result.criteria_summary,
            run_at=result.run_at.isoformat()
        )
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error running screener: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/validate", response_model=ValidationResponse)
async def validate_dsl(
    query: str = Body(..., embed=True)
):
    """Validate a DSL query and optionally convert to SQL."""
    is_valid, error = validate_query(query)
    
    response = ValidationResponse(
        valid=is_valid,
        query=query,
        error=error
    )
    
    if is_valid:
        try:
            response.sql = to_sql_where(query)
            response.explanation = explain_query(query)
        except:
            pass
    
    return response


@router.get("/fields", response_model=FieldInfoResponse)
async def get_fields():
    """Get all available screening fields with metadata."""
    categories = list(set(f.get("category", "other") for f in SCREENABLE_FIELDS.values()))
    
    return FieldInfoResponse(
        fields=SCREENABLE_FIELDS,
        categories=sorted(categories)
    )


@router.post("/preview")
async def preview_screener(
    request: ScreenerRunRequest,
    engine: ScreenerEngine = Depends(get_engine)
):
    """Preview screener results (quick count + sample)."""
    try:
        criteria = _convert_criteria(request.criteria)
        preview = engine.preview(criteria, limit=5)
        
        return {
            "total_entities": preview["total_entities"],
            "matching_count": preview["matching_count"],
            "sample_count": len(preview["sample"]),
            "sample": preview["sample"],
            "criteria_summary": preview["criteria_summary"]
        }
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# =============================================================================
# Helper Functions
# =============================================================================

def _convert_criteria(criteria_requests: List[CriterionRequest]) -> List[Criterion]:
    """Convert API request criteria to engine criteria."""
    criteria = []
    
    for req in criteria_requests:
        # Map operator string to enum
        op_map = {
            ">": FilterOperator.GT,
            ">=": FilterOperator.GTE,
            "<": FilterOperator.LT,
            "<=": FilterOperator.LTE,
            "=": FilterOperator.EQ,
            "==": FilterOperator.EQ,
            "!=": FilterOperator.NEQ,
            "in": FilterOperator.IN,
            "not_in": FilterOperator.NOT_IN,
            "contains": FilterOperator.CONTAINS,
            "between": FilterOperator.BETWEEN,
            "field_gt": FilterOperator.FIELD_GT,
            "field_lt": FilterOperator.FIELD_LT,
            "field_gte": FilterOperator.FIELD_GTE,
            "field_lte": FilterOperator.FIELD_LTE,
        }
        
        operator = op_map.get(req.operator.lower(), FilterOperator.EQ)
        
        # Map type string to enum
        type_map = {
            "score": CriterionType.SCORE,
            "momentum": CriterionType.MOMENTUM,
            "category": CriterionType.CATEGORY,
            "signal": CriterionType.SIGNAL,
            "date": CriterionType.DATE,
            "comparison": CriterionType.COMPARISON,
        }
        
        criterion_type = type_map.get(req.type, CriterionType.SCORE)
        
        # Handle field comparison
        if req.compare_field:
            criterion_type = CriterionType.COMPARISON
            if operator in [FilterOperator.GT, FilterOperator.GTE, FilterOperator.LT, FilterOperator.LTE]:
                op_field_map = {
                    FilterOperator.GT: FilterOperator.FIELD_GT,
                    FilterOperator.GTE: FilterOperator.FIELD_GTE,
                    FilterOperator.LT: FilterOperator.FIELD_LT,
                    FilterOperator.LTE: FilterOperator.FIELD_LTE,
                }
                operator = op_field_map.get(operator, operator)
        
        criterion = Criterion(
            field=req.field,
            operator=operator,
            value=req.value,
            compare_field=req.compare_field,
            criterion_type=criterion_type
        )
        
        criteria.append(criterion)
    
    return criteria


# =============================================================================
# Scheduled Screener Endpoints
# =============================================================================

@router.post("/schedule")
async def schedule_screener(
    name: str = Body(...),
    schedule: str = Body(..., description="Cron expression, e.g., '0 9 * * *'"),
    notify: bool = Body(default=True),
    engine: ScreenerEngine = Depends(get_engine)
):
    """
    Schedule a screener to run periodically.
    
    Note: This endpoint registers the schedule but requires a scheduler
    (like APScheduler or cron) to actually execute.
    """
    screener = engine.load_screener(name)
    
    if not screener:
        raise HTTPException(status_code=404, detail=f"Screener '{name}' not found")
    
    # TODO: Integrate with actual scheduler
    # For now, return schedule info for external scheduler integration
    
    return {
        "screener": name,
        "schedule": schedule,
        "notify": notify,
        "message": "Schedule registered. Configure external scheduler to call POST /api/v1/screener/{name}/run",
        "endpoint": f"/api/v1/screener/{name}/run"
    }


@router.get("/alerts")
async def get_screener_alerts(
    screener_name: Optional[str] = Query(None),
    since_hours: int = Query(default=24, ge=1, le=168),
    engine: ScreenerEngine = Depends(get_engine)
):
    """
    Get recent screener alerts (new entities matching criteria).
    
    Tracks which entities newly matched screeners since last run.
    """
    # TODO: Implement alert tracking
    # This would require storing previous results and comparing
    
    return {
        "alerts": [],
        "message": "Alert tracking requires historical result storage (coming soon)",
        "screener_name": screener_name,
        "since_hours": since_hours
    }
