"""Articles API endpoints for news/product/investing pipelines."""

from typing import List, Dict, Any, Optional
from pathlib import Path

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel

import sys
_app_dir = Path(__file__).parent.parent.parent
if str(_app_dir) not in sys.path:
    sys.path.insert(0, str(_app_dir))

from utils.cross_pipeline_analyzer import CrossPipelineAnalyzer


router = APIRouter(prefix="/api", tags=["articles"])

_analyzer: Optional[CrossPipelineAnalyzer] = None


def get_analyzer() -> CrossPipelineAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = CrossPipelineAnalyzer()
    return _analyzer


class SearchableEntities(BaseModel):
    companies: List[str] = []
    models: List[str] = []
    people: List[str] = []


class Article(BaseModel):
    id: str
    title: str
    url: str
    source: str
    source_id: str
    weighted_score: float
    content: Optional[str] = None
    paraphrased_content: Optional[str] = None
    published_date: Optional[str] = None
    focus_tags: List[str] = []
    searchable_entities: SearchableEntities = SearchableEntities()


class ArticlesResponse(BaseModel):
    pipeline_id: str
    pipeline_name: str
    date: str
    articles: List[Article]
    total: int


@router.get("/articles/{pipeline}", response_model=ArticlesResponse)
def get_articles(
    pipeline: str,
    date: str = Query(..., description="Date in YYYYMMDD format"),
):
    """Get articles for a specific pipeline."""
    if pipeline not in ["news", "product", "investing"]:
        raise HTTPException(status_code=400, detail="Invalid pipeline. Use: news, product, investing")

    analyzer = get_analyzer()
    pipelines = analyzer.load_pipelines_for_date(date)

    if pipeline not in pipelines:
        return ArticlesResponse(
            pipeline_id=pipeline,
            pipeline_name=pipeline.title(),
            date=date,
            articles=[],
            total=0,
        )

    pdata = pipelines[pipeline]

    articles = []
    for a in pdata.articles:
        entities = a.get("searchable_entities", {})
        articles.append(Article(
            id=a.get("id", ""),
            title=a.get("title", ""),
            url=a.get("url", ""),
            source=a.get("source", ""),
            source_id=a.get("source_id", ""),
            weighted_score=a.get("weighted_score", 0),
            content=a.get("content"),
            paraphrased_content=a.get("paraphrased_content"),
            published_date=a.get("published_date"),
            focus_tags=a.get("focus_tags", []),
            searchable_entities=SearchableEntities(
                companies=entities.get("companies", []),
                models=entities.get("models", []),
                people=entities.get("people", []),
            ),
        ))

    return ArticlesResponse(
        pipeline_id=pipeline,
        pipeline_name=pdata.pipeline_name,
        date=date,
        articles=articles,
        total=len(articles),
    )