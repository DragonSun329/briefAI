"""Bucket Radar API endpoints."""

import json
from typing import List, Optional, Dict, Any
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import sys
_app_dir = Path(__file__).parent.parent.parent
if str(_app_dir) not in sys.path:
    sys.path.insert(0, str(_app_dir))


router = APIRouter(prefix="/api/buckets", tags=["buckets"])

BUCKET_CACHE_PATH = Path(__file__).parent.parent.parent / "data" / "cache" / "bucket_profiles.json"


class BucketProfileOut(BaseModel):
    bucket_id: str
    bucket_name: str
    week_start: str
    tms: float
    ccs: float
    eis_offensive: Optional[float] = None
    eis_defensive: Optional[float] = None
    nas: float
    pms: Optional[float] = None
    css: Optional[float] = None
    heat_score: float
    lifecycle_state: str
    hype_cycle_phase: str
    top_technical_entities: List[str] = []
    top_capital_entities: List[str] = []
    entity_count: int = 0
    github_repos: int = 0
    hf_models: int = 0
    article_count: int = 0


class BucketAlertOut(BaseModel):
    bucket_id: str
    bucket_name: str
    alert_type: str
    severity: str
    message: str
    tms: float
    ccs: float


class BucketsResponse(BaseModel):
    profiles: List[BucketProfileOut]
    generated_at: str
    week_start: str


def load_bucket_data() -> Dict[str, Any]:
    """Load bucket profiles from cache."""
    if not BUCKET_CACHE_PATH.exists():
        return {}

    try:
        with open(BUCKET_CACHE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except Exception:
        return {}


@router.get("", response_model=BucketsResponse)
def get_all_buckets():
    """Get all bucket profiles for the radar chart."""
    data = load_bucket_data()

    if not data:
        return BucketsResponse(profiles=[], generated_at="", week_start="")

    profiles = []
    for p in data.get("profiles", []):
        try:
            profiles.append(BucketProfileOut(
                bucket_id=p.get("bucket_id", ""),
                bucket_name=p.get("bucket_name", ""),
                week_start=p.get("week_start", ""),
                tms=p.get("tms") if p.get("tms") is not None else 50.0,
                ccs=p.get("ccs") if p.get("ccs") is not None else 50.0,
                eis_offensive=p.get("eis_offensive"),
                eis_defensive=p.get("eis_defensive"),
                nas=p.get("nas") if p.get("nas") is not None else 50.0,
                pms=p.get("pms"),
                css=p.get("css"),
                heat_score=p.get("heat_score", 0),
                lifecycle_state=p.get("lifecycle_state", "unknown"),
                hype_cycle_phase=p.get("hype_cycle_phase", "unknown"),
                top_technical_entities=p.get("top_technical_entities", []),
                top_capital_entities=p.get("top_capital_entities", []),
                entity_count=p.get("entity_count", 0),
                github_repos=p.get("github_repos", 0),
                hf_models=p.get("hf_models", 0),
                article_count=p.get("article_count", 0),
            ))
        except Exception:
            continue

    return BucketsResponse(
        profiles=profiles,
        generated_at=data.get("generated_at", ""),
        week_start=data.get("week_start", ""),
    )


@router.get("/alerts/active", response_model=List[BucketAlertOut])
def get_bucket_alerts():
    """Get active bucket alerts based on divergences."""
    data = load_bucket_data()

    if not data:
        return []

    alerts = []
    for p in data.get("profiles", []):
        try:
            tms = p.get("tms") if p.get("tms") is not None else 50.0
            ccs = p.get("ccs") if p.get("ccs") is not None else 50.0

            # Generate alerts based on TMS vs CCS divergence
            if tms > 70 and ccs < 30:
                alerts.append(BucketAlertOut(
                    bucket_id=p.get("bucket_id", ""),
                    bucket_name=p.get("bucket_name", ""),
                    alert_type="Alpha Zone",
                    severity="high",
                    message=f"High technical momentum ({tms:.0f}) with low capital consensus ({ccs:.0f})",
                    tms=tms,
                    ccs=ccs,
                ))
            elif ccs > 70 and tms < 30:
                alerts.append(BucketAlertOut(
                    bucket_id=p.get("bucket_id", ""),
                    bucket_name=p.get("bucket_name", ""),
                    alert_type="Hype Zone",
                    severity="medium",
                    message=f"High capital consensus ({ccs:.0f}) with low technical momentum ({tms:.0f})",
                    tms=tms,
                    ccs=ccs,
                ))
        except Exception:
            continue

    return alerts


@router.get("/{bucket_id}", response_model=BucketProfileOut)
def get_bucket(bucket_id: str):
    """Get a single bucket by ID."""
    data = load_bucket_data()

    for p in data.get("profiles", []):
        if p.get("bucket_id") == bucket_id:
            return BucketProfileOut(
                bucket_id=p.get("bucket_id", ""),
                bucket_name=p.get("bucket_name", ""),
                week_start=p.get("week_start", ""),
                tms=p.get("tms") if p.get("tms") is not None else 50.0,
                ccs=p.get("ccs") if p.get("ccs") is not None else 50.0,
                eis_offensive=p.get("eis_offensive"),
                eis_defensive=p.get("eis_defensive"),
                nas=p.get("nas") if p.get("nas") is not None else 50.0,
                pms=p.get("pms"),
                css=p.get("css"),
                heat_score=p.get("heat_score", 0),
                lifecycle_state=p.get("lifecycle_state", "unknown"),
                hype_cycle_phase=p.get("hype_cycle_phase", "unknown"),
                top_technical_entities=p.get("top_technical_entities", []),
                top_capital_entities=p.get("top_capital_entities", []),
                entity_count=p.get("entity_count", 0),
                github_repos=p.get("github_repos", 0),
                hf_models=p.get("hf_models", 0),
                article_count=p.get("article_count", 0),
            )

    raise HTTPException(status_code=404, detail=f"Bucket {bucket_id} not found")