"""Signal Radar API endpoints."""

from typing import List, Optional, Dict
from pathlib import Path

from fastapi import APIRouter, Query
from pydantic import BaseModel

import sys
_app_dir = Path(__file__).parent.parent.parent
if str(_app_dir) not in sys.path:
    sys.path.insert(0, str(_app_dir))

from utils.signal_store import SignalStore


router = APIRouter(prefix="/api/signals", tags=["signals"])

_store: Optional[SignalStore] = None


def get_store() -> SignalStore:
    global _store
    if _store is None:
        _store = SignalStore()
    return _store


class SignalScore(BaseModel):
    category: str
    value: float
    confidence: float


class EntityProfile(BaseModel):
    entity_id: str
    name: str
    entity_type: str
    composite_score: float
    scores: List[SignalScore]


class DivergenceAlert(BaseModel):
    entity_id: str
    entity_name: str
    signal_a: str
    signal_b: str
    divergence_score: float
    interpretation: str
    detected_at: str


class SignalsStatsResponse(BaseModel):
    total_entities: int
    entities_by_type: Dict[str, int]
    total_observations: int
    active_divergences: int


@router.get("/entities", response_model=List[EntityProfile])
def get_top_entities(limit: int = Query(default=50, le=100)):
    """Get top entities by composite signal score."""
    store = get_store()

    try:
        profiles = store.get_top_profiles(limit=limit)
    except Exception:
        return []

    result = []
    for p in profiles:
        try:
            scores = store.get_scores_for_entity(p.entity_id)
            result.append(EntityProfile(
                entity_id=p.entity_id,
                name=p.entity_name,
                entity_type=p.entity_type.value if hasattr(p.entity_type, 'value') else str(p.entity_type),
                composite_score=p.composite_score,
                scores=[
                    SignalScore(
                        category=s.category.value if hasattr(s.category, 'value') else str(s.category),
                        value=s.score,
                        confidence=getattr(s, 'confidence', 1.0) if hasattr(s, 'confidence') else 1.0,
                    )
                    for s in scores
                ],
            ))
        except Exception:
            continue

    return result


@router.get("/divergence", response_model=List[DivergenceAlert])
def get_divergences():
    """Get active signal divergences (opportunities/risks)."""
    store = get_store()

    try:
        divergences = store.get_active_divergences()
    except Exception:
        return []

    result = []
    for d in divergences:
        try:
            result.append(DivergenceAlert(
                entity_id=d.entity_id,
                entity_name=d.entity_name,
                signal_a=d.high_signal_category.value if hasattr(d.high_signal_category, 'value') else str(d.high_signal_category),
                signal_b=d.low_signal_category.value if hasattr(d.low_signal_category, 'value') else str(d.low_signal_category),
                divergence_score=d.divergence_magnitude,
                interpretation=d.interpretation.value if hasattr(d.interpretation, 'value') else str(d.interpretation),
                detected_at=d.detected_at.isoformat() if d.detected_at else "",
            ))
        except Exception:
            continue

    return result


@router.get("/stats", response_model=SignalsStatsResponse)
def get_signals_stats():
    """Get signal store statistics."""
    store = get_store()

    try:
        stats = store.get_stats()
        return SignalsStatsResponse(
            total_entities=stats.get("total_entities", 0),
            entities_by_type=stats.get("entities_by_type", {}),
            total_observations=stats.get("total_observations", 0),
            active_divergences=stats.get("active_divergences", 0),
        )
    except Exception:
        return SignalsStatsResponse(
            total_entities=0,
            entities_by_type={},
            total_observations=0,
            active_divergences=0,
        )