# -*- coding: utf-8 -*-
"""
API Router for AI Verticals

Serves AI vertical data for Gartner Hype Cycle and Quadrant Radar visualizations.

Now supports two modes:
1. Static: Load from scraped vertical_signals files (legacy)
2. Dynamic: Compute from entity-level signals in real-time (Bloomberg-level)

Use ?mode=dynamic to get real-time computed scores.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime
import json
import sys

# Add parent to path for imports
_api_dir = Path(__file__).parent.parent
_app_dir = _api_dir.parent
if str(_app_dir) not in sys.path:
    sys.path.insert(0, str(_app_dir))

# Import dynamic scorer
try:
    from utils.vertical_scorer import get_vertical_scorer, VerticalScorer
    from utils.vertical_tagger import get_vertical_tagger
    DYNAMIC_SCORING_AVAILABLE = True
except ImportError as e:
    DYNAMIC_SCORING_AVAILABLE = False
    print(f"[verticals] Dynamic scoring not available: {e}")

router = APIRouter(prefix="/api/verticals", tags=["verticals"])

DATA_DIR = Path(__file__).parent.parent.parent / "data" / "vertical_signals"


def get_latest_verticals_file() -> Optional[Path]:
    """Get the most recent verticals data file."""
    if not DATA_DIR.exists():
        return None
    
    files = sorted(DATA_DIR.glob("verticals_*.json"), reverse=True)
    return files[0] if files else None


def load_verticals_data() -> Dict[str, Any]:
    """Load verticals data from file (static mode)."""
    file_path = get_latest_verticals_file()
    
    if not file_path:
        return {"verticals": {}, "hype_cycle": [], "quadrant_data": []}
    
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_dynamic_data() -> Dict[str, Any]:
    """Compute verticals data dynamically from entity signals."""
    if not DYNAMIC_SCORING_AVAILABLE:
        return load_verticals_data()
    
    scorer = get_vertical_scorer()
    result = scorer.compute_all_profiles()
    
    # Convert to legacy format for compatibility
    verticals_dict = {}
    hype_cycle = []
    quadrant_data = []
    
    for v in result.get("verticals", []):
        v_id = v["vertical_id"]
        verticals_dict[v_id] = {
            "vertical_id": v_id,
            "name": v["name"],
            "maturity": v.get("maturity", 0.5),
            "hype_phase": v.get("hype_phase", "validating"),
            "tech_momentum_score": v.get("tech_momentum_score", 50),
            "hype_score": v.get("hype_score", 50),
            "investment_score": v.get("investment_score", 50),
            "companies": v.get("companies", []),
            "divergence_signal": v.get("divergence_signal", {}),
            "data_sources": v.get("data_sources", {}),
        }
        
        # Hype cycle data
        phase = v.get("hype_phase", "validating")
        phase_x = {
            "innovation_trigger": 10,
            "peak_expectations": 30,
            "trough_disillusionment": 50,
            "validating": 40,
            "slope_enlightenment": 70,
            "establishing": 65,
            "plateau_productivity": 90,
        }.get(phase, 50)
        
        maturity = v.get("maturity", 0.5)
        x = phase_x + (maturity - 0.5) * 10
        y = (
            30 +
            60 * (2.718 ** (-((x - 30) ** 2) / 200)) -
            20 * (2.718 ** (-((x - 50) ** 2) / 100)) +
            30 * (1 / (1 + 2.718 ** (-(x - 70) / 10)))
        )
        
        hype_cycle.append({
            "id": v_id,
            "name": v["name"],
            "x": round(x, 0),
            "y": round(y, 1),
            "phase": phase,
            "phase_name": phase.replace("_", " ").title(),
            "maturity": maturity,
            "companies": v.get("companies", [])[:5],
        })
        
        # Quadrant data
        tech = v.get("tech_momentum_score", 50)
        hype = v.get("hype_score", 50)
        
        if tech > 50 and hype > 50:
            quadrant = "hot"
        elif tech <= 50 and hype > 50:
            quadrant = "hyped"
        elif tech > 50 and hype <= 50:
            quadrant = "mature"
        else:
            quadrant = "emerging"
        
        quadrant_data.append({
            "id": v_id,
            "name": v["name"],
            "x": tech,
            "y": hype,
            "size": min(v.get("entity_count", 10), 30),
            "phase": phase,
            "quadrant": quadrant,
        })
    
    return {
        "scraped_at": result.get("computed_at"),
        "computed_at": result.get("computed_at"),
        "mode": "dynamic",
        "verticals": verticals_dict,
        "hype_cycle": hype_cycle,
        "quadrant_data": quadrant_data,
        "summary": result.get("summary", {}),
    }


@router.get("")
async def get_verticals_overview(
    mode: str = Query("static", description="Data mode: 'static' (from files) or 'dynamic' (computed)")
):
    """
    Get overview of all AI verticals.
    
    Query params:
    - mode: 'static' (default) or 'dynamic'
      - static: Load from scraped vertical_signals files
      - dynamic: Compute from entity-level signals in real-time
    """
    if mode == "dynamic" and DYNAMIC_SCORING_AVAILABLE:
        data = get_dynamic_data()
    else:
        data = load_verticals_data()
    
    return {
        "scraped_at": data.get("scraped_at") or data.get("computed_at"),
        "mode": data.get("mode", "static"),
        "total_verticals": len(data.get("verticals", {})),
        "summary": data.get("summary", {}),
        "verticals": list(data.get("verticals", {}).values()),
    }


@router.get("/hype-cycle")
async def get_hype_cycle_data(
    mode: str = Query("static", description="Data mode: 'static' or 'dynamic'")
):
    """Get data for Gartner Hype Cycle visualization."""
    if mode == "dynamic" and DYNAMIC_SCORING_AVAILABLE:
        data = get_dynamic_data()
    else:
        data = load_verticals_data()
    
    # Generate the curve points
    curve_data = []
    for x in range(0, 101, 2):
        y = (
            30 +
            60 * (2.718 ** (-((x - 30) ** 2) / 200)) -
            20 * (2.718 ** (-((x - 50) ** 2) / 100)) +
            30 * (1 / (1 + 2.718 ** (-(x - 70) / 10)))
        )
        curve_data.append({"x": x, "y": y})
    
    # Phase definitions
    phases = {
        "innovation_trigger": {"label": "Innovation Trigger", "x": 10, "color": "#3498db"},
        "peak_expectations": {"label": "Peak of Inflated Expectations", "x": 30, "color": "#e74c3c"},
        "trough_disillusionment": {"label": "Trough of Disillusionment", "x": 50, "color": "#95a5a6"},
        "slope_enlightenment": {"label": "Slope of Enlightenment", "x": 70, "color": "#f39c12"},
        "plateau_productivity": {"label": "Plateau of Productivity", "x": 90, "color": "#27ae60"},
        "validating": {"label": "Validating", "x": 40, "color": "#9b59b6"},
        "establishing": {"label": "Establishing", "x": 65, "color": "#1abc9c"},
    }
    
    return {
        "curve": curve_data,
        "phases": phases,
        "verticals": data.get("hype_cycle", []),
        "mode": data.get("mode", "static"),
    }


@router.get("/quadrant")
async def get_quadrant_data(
    mode: str = Query("static", description="Data mode: 'static' or 'dynamic'")
):
    """Get data for Quadrant Radar visualization."""
    if mode == "dynamic" and DYNAMIC_SCORING_AVAILABLE:
        data = get_dynamic_data()
    else:
        data = load_verticals_data()
    
    return {
        "verticals": data.get("quadrant_data", []),
        "quadrants": {
            "hot": {"name": "Hot Zone", "description": "High tech + High hype - Competitive"},
            "mature": {"name": "Mature", "description": "High tech + Low hype - Stable"},
            "hyped": {"name": "Hype Zone", "description": "Low tech + High hype - Risky"},
            "emerging": {"name": "Emerging", "description": "Low tech + Low hype - Early"},
        },
        "mode": data.get("mode", "static"),
    }


@router.get("/profiles")
async def get_vertical_profiles(
    mode: str = Query("static", description="Data mode: 'static' or 'dynamic'")
):
    """Get detailed profiles for all verticals (compatible with BucketRadar format)."""
    if mode == "dynamic" and DYNAMIC_SCORING_AVAILABLE:
        data = get_dynamic_data()
    else:
        data = load_verticals_data()
    
    profiles = []
    for v_id, vertical in data.get("verticals", {}).items():
        # Map to bucket-compatible format
        tech = vertical.get("tech_momentum_score", 50)
        hype = vertical.get("hype_score", 50)
        investment = vertical.get("investment_score", 50)
        
        profile = {
            "bucket_id": v_id,
            "bucket_name": vertical.get("name", v_id),
            "tms": tech,
            "ccs": investment,  # CCS maps to investment in verticals
            "nas": hype,        # NAS maps to hype in verticals
            "eis": 50,          # Enterprise interest score
            "heat_score": (tech + hype + investment) / 3,
            "lifecycle_state": vertical.get("hype_phase", "validating").upper().replace("_", " ").title(),
            "hype_cycle_phase": vertical.get("hype_phase", "validating"),
            "entity_count": len(vertical.get("companies", [])),
            "article_count": 0,
            "maturity": vertical.get("maturity", 0.5),
            "divergence_signal": vertical.get("divergence_signal", {}),
            "data_sources": vertical.get("data_sources", {}),
        }
        profiles.append(profile)
    
    return {
        "profiles": profiles,
        "scraped_at": data.get("scraped_at") or data.get("computed_at"),
        "mode": data.get("mode", "static"),
    }


@router.get("/divergences")
async def get_vertical_divergences():
    """
    Get divergence signals across all verticals.
    
    Divergences indicate opportunities or risks:
    - alpha_opportunity: High tech + Low hype (undervalued)
    - bubble_warning: Low tech + High hype (overvalued)
    - smart_money: High investment + Low hype (accumulation)
    """
    if not DYNAMIC_SCORING_AVAILABLE:
        raise HTTPException(
            status_code=501,
            detail="Dynamic scoring not available. Install required dependencies."
        )
    
    data = get_dynamic_data()
    
    divergences = []
    for v_id, vertical in data.get("verticals", {}).items():
        div_signal = vertical.get("divergence_signal", {})
        if div_signal.get("type") != "balanced":
            divergences.append({
                "vertical_id": v_id,
                "vertical_name": vertical.get("name"),
                "divergence_type": div_signal.get("type"),
                "magnitude": div_signal.get("magnitude"),
                "description": div_signal.get("description"),
                "tech_score": vertical.get("tech_momentum_score"),
                "hype_score": vertical.get("hype_score"),
                "investment_score": vertical.get("investment_score"),
            })
    
    # Sort by magnitude (strongest signals first)
    divergences.sort(key=lambda x: x.get("magnitude", 0), reverse=True)
    
    return {
        "divergences": divergences,
        "total": len(divergences),
        "computed_at": data.get("computed_at"),
    }


@router.get("/alerts/active")
async def get_vertical_alerts(
    mode: str = Query("static", description="Data mode: 'static' or 'dynamic'")
):
    """Get active alerts for verticals."""
    if mode == "dynamic" and DYNAMIC_SCORING_AVAILABLE:
        data = get_dynamic_data()
    else:
        data = load_verticals_data()
    
    alerts = []
    for v_id, vertical in data.get("verticals", {}).items():
        tech = vertical.get("tech_momentum_score", 50)
        hype = vertical.get("hype_score", 50)
        investment = vertical.get("investment_score", 50)
        
        # Alpha opportunity: high tech, low hype
        if tech > 70 and hype < 40:
            alerts.append({
                "vertical_id": v_id,
                "bucket_name": vertical.get("name"),
                "alert_type": "alpha_opportunity",
                "severity": "medium",
                "message": f"Undervalued opportunity - strong tech ({tech:.0f}), low hype ({hype:.0f})",
                "tms": tech,
                "ccs": investment,
                "nas": hype,
            })
        
        # Hype warning: low tech, high hype
        if tech < 30 and hype > 70:
            alerts.append({
                "vertical_id": v_id,
                "bucket_name": vertical.get("name"),
                "alert_type": "hype_warning",
                "severity": "high",
                "message": f"Potential bubble - weak tech ({tech:.0f}), high hype ({hype:.0f})",
                "tms": tech,
                "ccs": investment,
                "nas": hype,
            })
        
        # Smart money: high investment, lower hype
        if investment > 70 and hype < 50 and tech > 50:
            alerts.append({
                "vertical_id": v_id,
                "bucket_name": vertical.get("name"),
                "alert_type": "smart_money_accumulating",
                "severity": "low",
                "message": f"Smart money signal - high investment ({investment:.0f}), moderate visibility",
                "tms": tech,
                "ccs": investment,
                "nas": hype,
            })
    
    return {
        "alerts": alerts,
        "total": len(alerts),
        "mode": data.get("mode", "static"),
    }


@router.get("/momentum")
async def get_vertical_momentum(
    days: int = Query(7, ge=1, le=90, description="Days for momentum calculation"),
    min_change: float = Query(5.0, ge=0, description="Minimum change to include"),
):
    """
    Get momentum (change) for all verticals over N days.
    
    Shows which verticals are gaining or losing momentum in tech, hype, investment.
    Requires historical data from daily snapshots.
    """
    try:
        from utils.vertical_history import get_vertical_history
        history = get_vertical_history()
        
        momentum = history.get_all_momentum(days=days, min_change=min_change)
        
        return {
            "momentum": momentum,
            "total": len(momentum),
            "days": days,
            "min_change": min_change,
        }
    except ImportError:
        raise HTTPException(status_code=501, detail="History module not available")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/{vertical_id}")
async def get_vertical_history_endpoint(
    vertical_id: str,
    days: int = Query(30, ge=1, le=365, description="Days of history"),
):
    """
    Get historical snapshots for a vertical.
    
    Returns daily scores for trend analysis.
    """
    try:
        from utils.vertical_history import get_vertical_history
        history = get_vertical_history()
        
        snapshots = history.get_history(vertical_id, days=days)
        
        if not snapshots:
            return {
                "vertical_id": vertical_id,
                "snapshots": [],
                "message": "No history available. Run snapshot_verticals.py to collect data.",
            }
        
        # Also get momentum
        momentum_7d = history.get_momentum(vertical_id, days=7, metric="tech_momentum_score")
        momentum_30d = history.get_momentum(vertical_id, days=30, metric="tech_momentum_score")
        
        return {
            "vertical_id": vertical_id,
            "snapshots": snapshots,
            "momentum_7d": momentum_7d,
            "momentum_30d": momentum_30d,
            "total_snapshots": len(snapshots),
        }
    except ImportError:
        raise HTTPException(status_code=501, detail="History module not available")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/predictions/accuracy")
async def get_prediction_accuracy(
    days: int = Query(90, ge=1, le=365, description="Days to analyze"),
):
    """
    Get prediction accuracy statistics.
    
    Shows how accurate our divergence signals have been.
    """
    try:
        from utils.vertical_history import get_vertical_history
        history = get_vertical_history()
        
        accuracy = history.get_prediction_accuracy(days=days)
        
        return accuracy
    except ImportError:
        raise HTTPException(status_code=501, detail="History module not available")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/validation/summary")
async def get_validation_summary(
    days: int = Query(90, ge=1, le=365, description="Days to analyze"),
):
    """
    Get detailed validation summary with accuracy by type and vertical.
    
    Shows which predictions have been validated against market performance.
    """
    try:
        from utils.vertical_validator import get_vertical_validator
        validator = get_vertical_validator()
        
        summary = validator.get_validation_summary(days=days)
        
        return summary
    except ImportError:
        raise HTTPException(status_code=501, detail="Validator module not available")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/performance/{vertical_id}")
async def get_vertical_stock_performance(
    vertical_id: str,
    days: int = Query(30, ge=1, le=365, description="Days of performance"),
):
    """
    Get stock market performance for a vertical's associated tickers.
    
    Fetches real stock prices and computes weighted average performance.
    Requires yfinance package.
    """
    try:
        from utils.vertical_validator import get_vertical_validator
        from datetime import date, timedelta
        
        validator = get_vertical_validator()
        
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        
        perf = validator.compute_vertical_performance(
            vertical_id, start_date, end_date
        )
        
        return perf
    except ImportError as e:
        raise HTTPException(
            status_code=501, 
            detail=f"Required module not available: {e}"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/validate/run")
async def run_validation(
    min_age_days: int = Query(30, ge=7, le=180, description="Minimum prediction age to validate"),
):
    """
    Run validation on pending predictions.
    
    Validates predictions against actual market performance and updates accuracy scores.
    Should be run periodically (weekly recommended).
    """
    try:
        from utils.vertical_validator import get_vertical_validator
        validator = get_vertical_validator()
        
        results = validator.validate_all_pending(min_age_days)
        
        return results
    except ImportError as e:
        raise HTTPException(
            status_code=501,
            detail=f"Required module not available: {e}"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/entity/{entity_name}")
async def get_entity_verticals(entity_name: str):
    """
    Get all verticals an entity belongs to.
    
    Useful for understanding cross-vertical presence of companies like
    OpenAI (creative, customer service, science, education).
    """
    if not DYNAMIC_SCORING_AVAILABLE:
        raise HTTPException(
            status_code=501,
            detail="Dynamic scoring not available."
        )
    
    tagger = get_vertical_tagger()
    matches = tagger.tag_entity(name=entity_name)
    
    return {
        "entity": entity_name,
        "verticals": [
            {
                "vertical_id": m.vertical_id,
                "vertical_name": m.vertical_name,
                "confidence": m.confidence,
                "match_reason": m.match_reason,
                "matched_terms": m.matched_terms,
            }
            for m in matches
        ],
        "total": len(matches),
    }


@router.get("/{vertical_id}")
async def get_vertical_detail(
    vertical_id: str,
    mode: str = Query("static", description="Data mode: 'static' or 'dynamic'")
):
    """Get detailed information for a specific vertical."""
    if mode == "dynamic" and DYNAMIC_SCORING_AVAILABLE:
        data = get_dynamic_data()
    else:
        data = load_verticals_data()
    
    verticals = data.get("verticals", {})
    if vertical_id not in verticals:
        raise HTTPException(status_code=404, detail=f"Vertical {vertical_id} not found")
    
    vertical = verticals[vertical_id]
    
    # Find hype cycle position
    hype_entry = next(
        (h for h in data.get("hype_cycle", []) if h.get("id") == vertical_id),
        None
    )
    
    # Find quadrant position
    quadrant_entry = next(
        (q for q in data.get("quadrant_data", []) if q.get("id") == vertical_id),
        None
    )
    
    return {
        "vertical": vertical,
        "hype_cycle_position": hype_entry,
        "quadrant_position": quadrant_entry,
        "mode": data.get("mode", "static"),
    }
