"""Companies/Shortlist API endpoints."""

import os
import re
from datetime import datetime
from typing import List, Optional
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

import sys
_api_dir = Path(__file__).parent.parent
_app_dir = _api_dir.parent
_trend_radar_path = _app_dir / ".worktrees" / "trend-radar"
_db_path = _trend_radar_path / "data" / "trend_radar.db"

os.environ["TREND_RADAR_DB_URL"] = f"sqlite:///{_db_path.as_posix()}"

if str(_app_dir) not in sys.path:
    sys.path.insert(0, str(_app_dir))
if str(_trend_radar_path) not in sys.path:
    sys.path.append(str(_trend_radar_path))

from trend_radar.models import get_session
from trend_radar.shortlist import generate_shortlist


router = APIRouter(prefix="/api", tags=["companies"])


class CompanyEntry(BaseModel):
    id: int
    name: str
    category: str
    category_zh: str
    funding_stage: str
    funding_stage_zh: str
    description: Optional[str] = None
    sources: List[str]
    source_count: int
    rising_score: Optional[float] = None
    first_seen: Optional[str] = None
    website: Optional[str] = None
    total_funding: Optional[float] = None
    employee_count: Optional[str] = None
    cb_rank: Optional[int] = None
    estimated_revenue: Optional[str] = None
    founded_year: Optional[int] = None
    # Computed for frontend sorting
    funding_millions: float = 0
    revenue_millions: float = 0


class FiltersResponse(BaseModel):
    categories: List[dict]
    stages: List[dict]


class CompaniesResponse(BaseModel):
    companies: List[CompanyEntry]
    total: int
    categories_available: List[str]
    stages_available: List[str]
    generated_at: str


def parse_revenue_to_millions(revenue_str: Optional[str]) -> float:
    """Parse revenue string like '$10M to $50M' to numeric (upper bound in millions)."""
    if not revenue_str or revenue_str == '-':
        return 0
    matches = re.findall(r'\$?([\d.]+)\s*([BMK])?', revenue_str.upper())
    if not matches:
        return 0
    amount, multiplier = matches[-1]
    amount = float(amount)
    if multiplier == 'B':
        return amount * 1000
    elif multiplier == 'M':
        return amount
    elif multiplier == 'K':
        return amount / 1000
    return amount / 1_000_000


@router.get("/companies", response_model=CompaniesResponse)
def get_companies():
    """Get all companies for the shortlist table."""
    session = get_session()
    try:
        result = generate_shortlist(session, limit=1000)

        companies = []
        for entry in result.entries:
            first_seen_str = entry.first_seen.isoformat() if entry.first_seen else None
            funding_m = round(entry.total_funding / 1_000_000) if entry.total_funding else 0
            revenue_m = round(parse_revenue_to_millions(entry.estimated_revenue))

            companies.append(CompanyEntry(
                id=entry.id,
                name=entry.name,
                category=entry.category,
                category_zh=entry.category_zh,
                funding_stage=entry.funding_stage,
                funding_stage_zh=entry.funding_stage_zh,
                description=entry.description,
                sources=entry.sources,
                source_count=entry.source_count,
                rising_score=entry.rising_score,
                first_seen=first_seen_str,
                website=entry.website,
                total_funding=entry.total_funding,
                employee_count=entry.employee_count,
                cb_rank=entry.cb_rank,
                estimated_revenue=entry.estimated_revenue,
                founded_year=entry.founded_year,
                funding_millions=funding_m,
                revenue_millions=revenue_m,
            ))

        return CompaniesResponse(
            companies=companies,
            total=len(companies),
            categories_available=result.categories_available,
            stages_available=result.stages_available,
            generated_at=result.generated_at,
        )
    finally:
        session.close()


@router.get("/companies/filters", response_model=FiltersResponse)
def get_company_filters():
    """Get available filter options for companies."""
    from trend_radar.taxonomy import load_taxonomy

    taxonomy = load_taxonomy()

    return FiltersResponse(
        categories=[
            {"id": c["id"], "name_zh": c["name_zh"]}
            for c in taxonomy["categories"]
        ],
        stages=[
            {"id": s["id"], "name_zh": s["name_zh"]}
            for s in taxonomy["funding_stages"]
        ],
    )