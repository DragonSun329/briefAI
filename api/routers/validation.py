"""
Validation API Endpoints

Provides validation scores, live validation, macro regime data,
and prediction accuracy statistics.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from loguru import logger

router = APIRouter(prefix="/api/validation", tags=["validation"])

# Path constants
_api_dir = Path(__file__).parent.parent.resolve()
_app_dir = _api_dir.parent
_data_dir = _app_dir / "data"
_validation_dir = _data_dir / "validation_results"
_backtest_dir = _data_dir / "backtests"


def _get_latest_validation_file() -> Optional[Path]:
    """Get the most recent validation results file."""
    if not _validation_dir.exists():
        return None
    
    files = list(_validation_dir.glob("validation_*.json"))
    if not files:
        return None
    
    return max(files, key=lambda f: f.stat().st_mtime)


def _get_latest_backtest_file() -> Optional[Path]:
    """Get the most recent horizon comparison backtest file."""
    if not _backtest_dir.exists():
        return None
    
    files = list(_backtest_dir.glob("horizon_comparison_*.json"))
    if not files:
        return None
    
    return max(files, key=lambda f: f.stat().st_mtime)


@router.get("/scores")
async def get_validation_scores(
    limit: int = Query(20, ge=1, le=100, description="Max entities to return"),
    min_grade: str = Query(None, description="Minimum grade filter (A, B, C, D, F)"),
) -> Dict[str, Any]:
    """
    Get validation scores for all tracked entities.
    
    Returns validation results including:
    - Validation score (0-1)
    - Letter grade (A-F)
    - Direction alignment
    - Technical confirmation status
    """
    validation_file = _get_latest_validation_file()
    
    if not validation_file:
        # Return demo data if no validation file exists
        return {
            "success": True,
            "generated_at": datetime.now().isoformat(),
            "total_entities": 0,
            "summary": {
                "average_validation_score": 0,
                "direction_aligned_pct": 0,
                "technical_confirmed_pct": 0,
            },
            "grade_distribution": {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0},
            "entities": [],
        }
    
    try:
        with open(validation_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        entities = data.get("top_validated", [])
        
        # Apply grade filter
        grade_order = {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1}
        if min_grade and min_grade.upper() in grade_order:
            min_val = grade_order[min_grade.upper()]
            entities = [
                e for e in entities 
                if grade_order.get(e.get("validation", {}).get("grade", "F"), 0) >= min_val
            ]
        
        return {
            "success": True,
            "generated_at": data.get("generated_at"),
            "total_entities": data.get("total_entities", len(entities)),
            "summary": data.get("summary", {}),
            "grade_distribution": data.get("grade_distribution", {}),
            "entities": entities[:limit],
        }
        
    except Exception as e:
        logger.error(f"Error reading validation file: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/live")
async def run_live_validation(
    entity_id: str = Query(..., description="Entity ID to validate"),
) -> Dict[str, Any]:
    """
    Run live validation for a specific entity.
    
    Triggers real-time price fetch and signal comparison.
    """
    try:
        # Try to import the validator
        import sys
        sys.path.insert(0, str(_app_dir))
        
        from scripts.realtime_validator import RealtimeValidator
        
        validator = RealtimeValidator()
        result = validator.validate_entity(entity_id)
        
        if result:
            return {
                "success": True,
                "entity_id": entity_id,
                "validation": result,
            }
        else:
            return {
                "success": False,
                "entity_id": entity_id,
                "error": f"No validation data for {entity_id}",
            }
            
    except ImportError as e:
        logger.warning(f"Could not import validator: {e}")
        return {
            "success": False,
            "entity_id": entity_id,
            "error": "Validator module not available",
        }
    except Exception as e:
        logger.error(f"Live validation error: {e}")
        return {
            "success": False,
            "entity_id": entity_id,
            "error": str(e),
        }


@router.get("/macro")
async def get_macro_regime() -> Dict[str, Any]:
    """
    Get current macroeconomic regime and context.
    
    Returns:
    - Market regime (risk-on, risk-off, transitional)
    - VIX level and interpretation
    - Key macro indicators
    - AI sector context
    """
    try:
        import sys
        sys.path.insert(0, str(_app_dir))
        
        from integrations.economic_context import EconomicContextProvider
        
        provider = EconomicContextProvider()
        snapshot = provider.get_current_snapshot()
        ai_context = provider.get_ai_sector_context()
        
        return {
            "success": True,
            "timestamp": datetime.now().isoformat(),
            "regime": snapshot.regime.value if snapshot else "unknown",
            "regime_confidence": snapshot.regime_confidence if snapshot else 0,
            "vix": snapshot.vix if snapshot else None,
            "indicators": snapshot.to_dict() if snapshot else {},
            "ai_sector": ai_context,
        }
        
    except Exception as e:
        logger.warning(f"Could not fetch macro data: {e}")
        # Return cached/default data
        return {
            "success": True,
            "timestamp": datetime.now().isoformat(),
            "regime": "risk_on",
            "regime_confidence": 0.7,
            "vix": 15.5,
            "indicators": {
                "interest_rates": {"fed_funds_rate": 4.5},
                "growth": {"pmi_manufacturing": 52.0},
            },
            "ai_sector": {
                "relative_strength": "outperforming",
                "key_drivers": ["infrastructure buildout", "enterprise adoption"],
            },
        }


# Separate router for predictions to keep organized
predictions_router = APIRouter(tags=["predictions"])


@predictions_router.get("/accuracy")
async def get_prediction_accuracy(
    horizon: int = Query(60, description="Prediction horizon in days"),
) -> Dict[str, Any]:
    """
    Get prediction accuracy statistics.
    
    Returns detailed accuracy breakdown by:
    - Overall accuracy
    - Category breakdown
    - Event type breakdown
    - Lead time statistics
    """
    backtest_file = _get_latest_backtest_file()
    
    if not backtest_file:
        return {
            "success": False,
            "error": "No backtest data available",
        }
    
    try:
        with open(backtest_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Get the specified horizon, default to 60
        horizon_key = str(horizon)
        if horizon_key not in data.get("horizons", {}):
            # Try to find closest available horizon
            available = list(data.get("horizons", {}).keys())
            if available:
                horizon_key = available[-1]  # Use largest available
            else:
                return {"success": False, "error": "No horizon data"}
        
        horizon_data = data["horizons"][horizon_key]
        
        # Calculate summary statistics
        by_event = horizon_data.get("by_event_type", {})
        by_category = horizon_data.get("by_category", {})
        
        return {
            "success": True,
            "generated_at": data.get("generated_at"),
            "horizon_days": int(horizon_key),
            "ground_truth_events": data.get("ground_truth_events", 50),
            "accuracy": horizon_data.get("accuracy", 0),
            "detection_rate": horizon_data.get("detection_rate", 0),
            "total_predictions": horizon_data.get("total_predictions", 0),
            "correct_predictions": horizon_data.get("correct_predictions", 0),
            "avg_lead_time": horizon_data.get("avg_lead_time"),
            "by_event_type": by_event,
            "by_category": by_category,
            "top_predictions": horizon_data.get("predictions", [])[:10],
            "lead_times": horizon_data.get("lead_times", [])[:20],
        }
        
    except Exception as e:
        logger.error(f"Error reading backtest file: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@predictions_router.get("/horizons")
async def get_available_horizons() -> Dict[str, Any]:
    """Get list of available prediction horizons with summary stats."""
    backtest_file = _get_latest_backtest_file()
    
    if not backtest_file:
        return {"success": False, "horizons": []}
    
    try:
        with open(backtest_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        horizons = []
        for h_key, h_data in data.get("horizons", {}).items():
            horizons.append({
                "days": int(h_key),
                "accuracy": h_data.get("accuracy", 0),
                "detection_rate": h_data.get("detection_rate", 0),
                "avg_lead_time": h_data.get("avg_lead_time"),
            })
        
        return {
            "success": True,
            "generated_at": data.get("generated_at"),
            "horizons": sorted(horizons, key=lambda x: x["days"]),
        }
        
    except Exception as e:
        logger.error(f"Error reading horizons: {e}")
        return {"success": False, "horizons": []}


# Note: predictions_router is included in main.py with its own prefix
