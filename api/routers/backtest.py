"""Backtest API endpoints for shadow mode."""

from datetime import date
from typing import List, Optional
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

import sys
_app_dir = Path(__file__).parent.parent.parent
if str(_app_dir) not in sys.path:
    sys.path.insert(0, str(_app_dir))

from utils.backtest_engine import BacktestEngine
from utils.scorecard_generator import ScorecardGenerator


router = APIRouter(prefix="/api/backtest", tags=["backtest"])


class PredictionOut(BaseModel):
    entity_id: str
    entity_name: str
    entity_type: str
    momentum_score: float
    validation_score: float
    validation_status: str
    rank: int


class BacktestRunOut(BaseModel):
    run_id: str
    prediction_date: str
    validation_date: str
    predictions: List[PredictionOut]
    created_at: str


class OutcomeOut(BaseModel):
    entity_id: str
    entity_name: str
    predicted_rank: int
    momentum_score: float
    hit: bool
    lead_time_weeks: Optional[float]
    mainstream_date: Optional[str]
    mainstream_source: Optional[str]


class ScorecardOut(BaseModel):
    run_id: str
    prediction_date: str
    validation_date: str
    precision_at_k: float
    recall: float
    avg_lead_time_weeks: float
    miss_rate: float
    total_predictions: int
    total_hits: int
    total_misses: int
    total_false_positives: int
    hits: List[OutcomeOut]
    misses: List[OutcomeOut]
    false_positives: List[OutcomeOut]


@router.get("/runs", response_model=List[str])
def list_backtest_runs():
    """List all saved backtest runs."""
    engine = BacktestEngine()
    return engine.list_runs()


@router.get("/runs/{run_id}", response_model=BacktestRunOut)
def get_backtest_run(run_id: str):
    """Get a specific backtest run."""
    engine = BacktestEngine()
    run = engine.load_run(run_id)

    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    return BacktestRunOut(
        run_id=run.run_id,
        prediction_date=run.prediction_date,
        validation_date=run.validation_date,
        predictions=[
            PredictionOut(
                entity_id=p.entity_id,
                entity_name=p.entity_name,
                entity_type=p.entity_type,
                momentum_score=p.momentum_score,
                validation_score=p.validation_score,
                validation_status=p.validation_status,
                rank=p.rank,
            )
            for p in run.predictions
        ],
        created_at=run.created_at,
    )


@router.post("/runs", response_model=BacktestRunOut)
def create_backtest_run(
    prediction_date: str = Query(..., description="Date to predict from (YYYY-MM-DD)"),
    validation_date: str = Query(..., description="Date to validate against (YYYY-MM-DD)"),
    top_k: int = Query(20, description="Number of top predictions"),
):
    """Create a new backtest run."""
    try:
        pred_date = date.fromisoformat(prediction_date)
        val_date = date.fromisoformat(validation_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    if pred_date >= val_date:
        raise HTTPException(status_code=400, detail="Prediction date must be before validation date")

    engine = BacktestEngine()
    run = engine.run_backtest(pred_date, val_date, top_k)

    return BacktestRunOut(
        run_id=run.run_id,
        prediction_date=run.prediction_date,
        validation_date=run.validation_date,
        predictions=[
            PredictionOut(
                entity_id=p.entity_id,
                entity_name=p.entity_name,
                entity_type=p.entity_type,
                momentum_score=p.momentum_score,
                validation_score=p.validation_score,
                validation_status=p.validation_status,
                rank=p.rank,
            )
            for p in run.predictions
        ],
        created_at=run.created_at,
    )


@router.get("/runs/{run_id}/scorecard", response_model=ScorecardOut)
def get_scorecard(run_id: str):
    """Generate scorecard for a backtest run."""
    engine = BacktestEngine()
    run = engine.load_run(run_id)

    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    generator = ScorecardGenerator()
    scorecard = generator.generate_scorecard(run)

    return ScorecardOut(
        run_id=scorecard.run_id,
        prediction_date=scorecard.prediction_date,
        validation_date=scorecard.validation_date,
        precision_at_k=scorecard.precision_at_k,
        recall=scorecard.recall,
        avg_lead_time_weeks=scorecard.avg_lead_time_weeks,
        miss_rate=scorecard.miss_rate,
        total_predictions=scorecard.total_predictions,
        total_hits=scorecard.total_hits,
        total_misses=scorecard.total_misses,
        total_false_positives=scorecard.total_false_positives,
        hits=[
            OutcomeOut(
                entity_id=h.entity_id,
                entity_name=h.entity_name,
                predicted_rank=h.predicted_rank,
                momentum_score=h.momentum_score,
                hit=h.hit,
                lead_time_weeks=h.lead_time_weeks,
                mainstream_date=h.mainstream_date,
                mainstream_source=h.mainstream_source,
            )
            for h in scorecard.hits
        ],
        misses=[
            OutcomeOut(
                entity_id=m.entity_id,
                entity_name=m.entity_name,
                predicted_rank=m.predicted_rank,
                momentum_score=m.momentum_score,
                hit=m.hit,
                lead_time_weeks=m.lead_time_weeks,
                mainstream_date=m.mainstream_date,
                mainstream_source=m.mainstream_source,
            )
            for m in scorecard.misses
        ],
        false_positives=[
            OutcomeOut(
                entity_id=f.entity_id,
                entity_name=f.entity_name,
                predicted_rank=f.predicted_rank,
                momentum_score=f.momentum_score,
                hit=f.hit,
                lead_time_weeks=f.lead_time_weeks,
                mainstream_date=f.mainstream_date,
                mainstream_source=f.mainstream_source,
            )
            for f in scorecard.false_positives
        ],
    )