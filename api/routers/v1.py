"""
briefAI API v1 - Enhanced REST API

Provides:
- Signal history and advanced querying
- Fuzzy entity search
- Event timeline
- SQL-like query builder
- Full pagination, filtering, sorting
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Query, HTTPException, Depends
from pydantic import BaseModel, Field

import sys
_app_dir = Path(__file__).parent.parent.parent
if str(_app_dir) not in sys.path:
    sys.path.insert(0, str(_app_dir))

from utils.signal_store import SignalStore
from utils.signal_models import EntityType, SignalCategory
from api.auth import verify_api_key, optional_api_key, APIKeyInfo, require_feature
from api.query_builder import execute_query, execute_boolean_query, QueryResult, QueryError, BooleanQuery


router = APIRouter(prefix="/api/v1", tags=["v1"])

_store: Optional[SignalStore] = None


def get_store() -> SignalStore:
    global _store
    if _store is None:
        _store = SignalStore()
    return _store


# =============================================================================
# Response Models
# =============================================================================

class PaginationMeta(BaseModel):
    """Pagination metadata."""
    total: int
    limit: int
    offset: int
    has_more: bool


class SignalScoreResponse(BaseModel):
    """Signal score response."""
    id: str
    entity_id: str
    source_id: str
    category: str
    score: float
    percentile: Optional[float] = None
    score_delta_7d: Optional[float] = None
    score_delta_30d: Optional[float] = None
    created_at: str


class SignalHistoryResponse(BaseModel):
    """Signal history for an entity."""
    entity_id: str
    entity_name: Optional[str] = None
    category: str
    history: List[SignalScoreResponse]
    pagination: PaginationMeta


class EntityResponse(BaseModel):
    """Entity response."""
    id: str
    canonical_id: str
    name: str
    entity_type: str
    aliases: List[str] = []
    description: Optional[str] = None
    website: Optional[str] = None
    headquarters: Optional[str] = None
    founded_date: Optional[str] = None
    created_at: str
    updated_at: str


class EntitySearchResponse(BaseModel):
    """Entity search results."""
    query: str
    results: List[EntityResponse]
    pagination: PaginationMeta


class ProfileResponse(BaseModel):
    """Signal profile response."""
    entity_id: str
    entity_name: str
    entity_type: str
    as_of: str
    technical_score: Optional[float] = None
    company_score: Optional[float] = None
    financial_score: Optional[float] = None
    product_score: Optional[float] = None
    media_score: Optional[float] = None
    composite_score: float
    momentum_7d: Optional[float] = None
    momentum_30d: Optional[float] = None


class DivergenceResponse(BaseModel):
    """Divergence response."""
    id: str
    entity_id: str
    entity_name: str
    divergence_type: str
    high_signal_category: str
    high_signal_score: float
    low_signal_category: str
    low_signal_score: float
    divergence_magnitude: float
    confidence: float
    interpretation: str
    interpretation_rationale: Optional[str] = None
    detected_at: str
    resolved_at: Optional[str] = None


class ActiveDivergencesResponse(BaseModel):
    """Active divergences list."""
    divergences: List[DivergenceResponse]
    pagination: PaginationMeta


class EventResponse(BaseModel):
    """Event in timeline."""
    id: str
    entity_id: str
    event_type: str
    timestamp: str
    title: str
    description: Optional[str] = None
    source: Optional[str] = None
    data: Dict[str, Any] = {}


class EventTimelineResponse(BaseModel):
    """Event timeline for an entity."""
    entity_id: str
    entity_name: Optional[str] = None
    events: List[EventResponse]
    pagination: PaginationMeta


# =============================================================================
# Signal Endpoints
# =============================================================================

@router.get("/signals/{entity_id}/history", response_model=SignalHistoryResponse)
async def get_signal_history(
    entity_id: str,
    category: Optional[str] = Query(None, description="Filter by signal category"),
    days: int = Query(30, ge=1, le=365, description="Number of days of history"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    key: Optional[APIKeyInfo] = Depends(optional_api_key),
):
    """
    Get full signal history for an entity.
    
    Parameters:
    - **entity_id**: Entity ID or canonical ID
    - **category**: Filter by category (technical, company, financial, product, media)
    - **days**: Number of days of history (1-365)
    - **limit/offset**: Pagination
    
    Example:
    ```
    GET /api/v1/signals/openai/history?category=technical&days=30
    ```
    """
    store = get_store()
    
    # Get entity name
    entity = store.get_entity(entity_id)
    entity_name = entity.name if entity else None
    
    conn = store._get_connection()
    cursor = conn.cursor()
    
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    
    # Build query
    query = """
        SELECT * FROM signal_scores
        WHERE entity_id = ? AND created_at >= ?
    """
    params = [entity_id, cutoff]
    
    if category:
        query += " AND category = ?"
        params.append(category)
    
    # Get total count
    count_query = query.replace("SELECT *", "SELECT COUNT(*)")
    cursor.execute(count_query, params)
    total = cursor.fetchone()[0]
    
    # Get paginated results
    query += f" ORDER BY created_at DESC LIMIT {limit} OFFSET {offset}"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    history = [
        SignalScoreResponse(
            id=row["id"],
            entity_id=row["entity_id"],
            source_id=row["source_id"],
            category=row["category"],
            score=row["score"],
            percentile=row["percentile"],
            score_delta_7d=row["score_delta_7d"],
            score_delta_30d=row["score_delta_30d"],
            created_at=row["created_at"],
        )
        for row in rows
    ]
    
    return SignalHistoryResponse(
        entity_id=entity_id,
        entity_name=entity_name,
        category=category or "all",
        history=history,
        pagination=PaginationMeta(
            total=total,
            limit=limit,
            offset=offset,
            has_more=total > offset + len(history),
        ),
    )


@router.get("/signals/categories")
async def list_signal_categories():
    """
    List available signal categories.
    
    Returns all signal category types with descriptions.
    """
    return {
        "categories": [
            {
                "id": "technical",
                "name": "Technical",
                "description": "Developer adoption, research momentum (GitHub, HuggingFace, Papers)",
            },
            {
                "id": "company",
                "name": "Company Presence",
                "description": "Market position, organizational strength (Crunchbase, LinkedIn)",
            },
            {
                "id": "financial",
                "name": "Financial",
                "description": "Capital flows, investor confidence (SEC, Funding rounds)",
            },
            {
                "id": "product",
                "name": "Product Traction",
                "description": "End-user demand, product-market fit (ProductHunt, App stores)",
            },
            {
                "id": "media",
                "name": "Media Sentiment",
                "description": "Public perception, narrative, hype (News pipeline)",
            },
        ],
    }


# =============================================================================
# Entity Endpoints
# =============================================================================

@router.get("/entities/search", response_model=EntitySearchResponse)
async def search_entities(
    q: str = Query(..., min_length=1, description="Search query"),
    entity_type: Optional[str] = Query(None, description="Filter by entity type"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    key: Optional[APIKeyInfo] = Depends(optional_api_key),
):
    """
    Fuzzy search for entities.
    
    Searches entity names, aliases, and descriptions.
    
    Parameters:
    - **q**: Search query (fuzzy matching)
    - **entity_type**: Filter by type (company, technology, concept, person)
    - **limit/offset**: Pagination
    
    Example:
    ```
    GET /api/v1/entities/search?q=openai&entity_type=company
    ```
    """
    store = get_store()
    conn = store._get_connection()
    cursor = conn.cursor()
    
    # Fuzzy search using LIKE
    search_term = f"%{q}%"
    
    query = """
        SELECT * FROM entities
        WHERE (
            name LIKE ? OR
            canonical_id LIKE ? OR
            description LIKE ? OR
            aliases LIKE ?
        )
    """
    params = [search_term, search_term, search_term, search_term]
    
    if entity_type:
        query += " AND entity_type = ?"
        params.append(entity_type)
    
    # Get total count
    count_query = query.replace("SELECT *", "SELECT COUNT(*)")
    cursor.execute(count_query, params)
    total = cursor.fetchone()[0]
    
    # Get paginated results
    query += f" ORDER BY name LIMIT {limit} OFFSET {offset}"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    import json
    
    results = [
        EntityResponse(
            id=row["id"],
            canonical_id=row["canonical_id"],
            name=row["name"],
            entity_type=row["entity_type"],
            aliases=json.loads(row["aliases"]) if row["aliases"] else [],
            description=row["description"],
            website=row["website"],
            headquarters=row["headquarters"],
            founded_date=row["founded_date"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]
    
    return EntitySearchResponse(
        query=q,
        results=results,
        pagination=PaginationMeta(
            total=total,
            limit=limit,
            offset=offset,
            has_more=total > offset + len(results),
        ),
    )


@router.get("/entities/{entity_id}", response_model=EntityResponse)
async def get_entity(
    entity_id: str,
    key: Optional[APIKeyInfo] = Depends(optional_api_key),
):
    """
    Get entity details by ID.
    
    Example:
    ```
    GET /api/v1/entities/openai
    ```
    """
    store = get_store()
    entity = store.get_entity(entity_id)
    
    if not entity:
        raise HTTPException(status_code=404, detail=f"Entity not found: {entity_id}")
    
    return EntityResponse(
        id=entity.id,
        canonical_id=entity.canonical_id,
        name=entity.name,
        entity_type=entity.entity_type.value,
        aliases=entity.aliases,
        description=entity.description,
        website=entity.website,
        headquarters=entity.headquarters,
        founded_date=entity.founded_date,
        created_at=entity.created_at.isoformat(),
        updated_at=entity.updated_at.isoformat(),
    )


@router.get("/entities/{entity_id}/profile", response_model=ProfileResponse)
async def get_entity_profile(
    entity_id: str,
    key: Optional[APIKeyInfo] = Depends(optional_api_key),
):
    """
    Get latest signal profile for an entity.
    
    Returns composite and per-category scores.
    
    Example:
    ```
    GET /api/v1/entities/openai/profile
    ```
    """
    store = get_store()
    
    profile = store.get_latest_profile(entity_id)
    
    if not profile:
        raise HTTPException(status_code=404, detail=f"No profile found for entity: {entity_id}")
    
    return ProfileResponse(
        entity_id=profile.entity_id,
        entity_name=profile.entity_name,
        entity_type=profile.entity_type.value,
        as_of=profile.as_of.isoformat(),
        technical_score=profile.technical_score,
        company_score=profile.company_score,
        financial_score=profile.financial_score,
        product_score=profile.product_score,
        media_score=profile.media_score,
        composite_score=profile.composite_score,
        momentum_7d=profile.momentum_7d,
        momentum_30d=profile.momentum_30d,
    )


# =============================================================================
# Divergence Endpoints
# =============================================================================

@router.get("/divergences/active", response_model=ActiveDivergencesResponse)
async def get_active_divergences(
    interpretation: Optional[str] = Query(None, description="Filter by interpretation"),
    entity_id: Optional[str] = Query(None, description="Filter by entity"),
    min_magnitude: Optional[float] = Query(None, ge=0, le=100),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    key: Optional[APIKeyInfo] = Depends(optional_api_key),
):
    """
    Get active (unresolved) signal divergences.
    
    Divergences indicate when signals disagree, revealing opportunities or risks.
    
    Parameters:
    - **interpretation**: Filter by interpretation (opportunity, risk, anomaly, neutral)
    - **entity_id**: Filter by specific entity
    - **min_magnitude**: Minimum divergence magnitude (0-100)
    - **limit/offset**: Pagination
    
    Example:
    ```
    GET /api/v1/divergences/active?interpretation=opportunity&min_magnitude=30
    ```
    """
    store = get_store()
    conn = store._get_connection()
    cursor = conn.cursor()
    
    query = "SELECT * FROM signal_divergences WHERE resolved_at IS NULL"
    params = []
    
    if interpretation:
        query += " AND interpretation = ?"
        params.append(interpretation)
    
    if entity_id:
        query += " AND entity_id = ?"
        params.append(entity_id)
    
    if min_magnitude is not None:
        query += " AND divergence_magnitude >= ?"
        params.append(min_magnitude)
    
    # Get total count
    count_query = query.replace("SELECT *", "SELECT COUNT(*)")
    cursor.execute(count_query, params)
    total = cursor.fetchone()[0]
    
    # Get paginated results
    query += f" ORDER BY divergence_magnitude DESC LIMIT {limit} OFFSET {offset}"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    divergences = [
        DivergenceResponse(
            id=row["id"],
            entity_id=row["entity_id"],
            entity_name=row["entity_name"],
            divergence_type=row["divergence_type"],
            high_signal_category=row["high_signal_category"],
            high_signal_score=row["high_signal_score"],
            low_signal_category=row["low_signal_category"],
            low_signal_score=row["low_signal_score"],
            divergence_magnitude=row["divergence_magnitude"],
            confidence=row["confidence"],
            interpretation=row["interpretation"],
            interpretation_rationale=row["interpretation_rationale"],
            detected_at=row["detected_at"],
            resolved_at=row["resolved_at"],
        )
        for row in rows
    ]
    
    return ActiveDivergencesResponse(
        divergences=divergences,
        pagination=PaginationMeta(
            total=total,
            limit=limit,
            offset=offset,
            has_more=total > offset + len(divergences),
        ),
    )


# =============================================================================
# Event Timeline Endpoints
# =============================================================================

@router.get("/events/{entity_id}", response_model=EventTimelineResponse)
async def get_entity_events(
    entity_id: str,
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    days: int = Query(90, ge=1, le=365),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    key: Optional[APIKeyInfo] = Depends(optional_api_key),
):
    """
    Get event timeline for an entity.
    
    Events include signal updates, divergence detections, profile changes, etc.
    
    Parameters:
    - **entity_id**: Entity ID
    - **event_type**: Filter by type (signal_update, divergence_detected, profile_updated)
    - **days**: Number of days of history
    - **limit/offset**: Pagination
    
    Example:
    ```
    GET /api/v1/events/openai?event_type=divergence_detected&days=30
    ```
    """
    store = get_store()
    
    # Get entity name
    entity = store.get_entity(entity_id)
    entity_name = entity.name if entity else None
    
    # Build events from various sources
    events = []
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    
    conn = store._get_connection()
    cursor = conn.cursor()
    
    # Add divergence events
    if not event_type or event_type == "divergence_detected":
        cursor.execute("""
            SELECT * FROM signal_divergences
            WHERE entity_id = ? AND detected_at >= ?
            ORDER BY detected_at DESC
        """, (entity_id, cutoff))
        
        for row in cursor.fetchall():
            events.append(EventResponse(
                id=f"div_{row['id']}",
                entity_id=entity_id,
                event_type="divergence_detected",
                timestamp=row["detected_at"],
                title=f"Divergence: {row['high_signal_category']} vs {row['low_signal_category']}",
                description=row["interpretation_rationale"],
                data={
                    "interpretation": row["interpretation"],
                    "magnitude": row["divergence_magnitude"],
                },
            ))
    
    # Add profile updates
    if not event_type or event_type == "profile_updated":
        cursor.execute("""
            SELECT * FROM signal_profiles
            WHERE entity_id = ? AND created_at >= ?
            ORDER BY created_at DESC
        """, (entity_id, cutoff))
        
        for row in cursor.fetchall():
            events.append(EventResponse(
                id=f"prof_{row['id']}",
                entity_id=entity_id,
                event_type="profile_updated",
                timestamp=row["created_at"],
                title=f"Profile Updated: Composite Score {row['composite_score']:.1f}",
                data={
                    "composite_score": row["composite_score"],
                    "momentum_7d": row["momentum_7d"],
                },
            ))
    
    conn.close()
    
    # Sort by timestamp
    events.sort(key=lambda e: e.timestamp, reverse=True)
    
    # Apply pagination
    total = len(events)
    events = events[offset:offset + limit]
    
    return EventTimelineResponse(
        entity_id=entity_id,
        entity_name=entity_name,
        events=events,
        pagination=PaginationMeta(
            total=total,
            limit=limit,
            offset=offset,
            has_more=total > offset + len(events),
        ),
    )


# =============================================================================
# Query Builder Endpoint
# =============================================================================

@router.post("/query", response_model=QueryResult)
async def execute_sql_query(
    query: str = Query(..., description="SQL-like query string"),
    key: APIKeyInfo = Depends(require_feature("query_builder_enabled")),
):
    """
    Execute a SQL-like query against the signal database.
    
    **Premium feature** - requires premium or enterprise tier.
    
    Allowed tables:
    - signals, entities, profiles, divergences, observations, scores
    
    Examples:
    ```
    SELECT * FROM signals WHERE entity_id='openai' AND category='technical' LIMIT 100
    SELECT entity_id, composite_score FROM profiles ORDER BY composite_score DESC LIMIT 50
    SELECT * FROM divergences WHERE interpretation='opportunity'
    ```
    
    Security:
    - Only SELECT queries allowed
    - Whitelisted columns only
    - Maximum 1000 rows per query
    """
    try:
        result = execute_query(query)
        return result
    except QueryError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query execution error: {str(e)}")


@router.post("/query/boolean", response_model=QueryResult)
async def execute_boolean_query_endpoint(
    query: BooleanQuery,
    key: APIKeyInfo = Depends(require_feature("query_builder_enabled")),
):
    """
    Execute a complex boolean query with AND/OR/NOT support.
    
    **Premium feature** - requires premium or enterprise tier.
    
    Bloomberg-quality query interface for professional data access.
    
    **Request Body:**
    ```json
    {
        "table": "signals",
        "select": ["entity_id", "entity_name", "score", "category"],
        "and_conditions": [
            {"field": "category", "operator": "=", "value": "technical"},
            {"field": "score", "operator": ">=", "value": 70}
        ],
        "or_conditions": [
            {"field": "entity_name", "operator": "LIKE", "value": "%OpenAI%"},
            {"field": "entity_name", "operator": "LIKE", "value": "%Anthropic%"}
        ],
        "date_from": "2025-01-01",
        "date_to": "2025-06-01",
        "sector": "ai_research",
        "min_confidence": 0.8,
        "order_by": "score",
        "order_desc": true,
        "limit": 50
    }
    ```
    
    **Available Tables:** signals, entities, profiles, divergences, observations, scores
    
    **Operators:** =, !=, >, >=, <, <=, LIKE, ILIKE, IN, NOT IN, BETWEEN
    
    **Features:**
    - Complex boolean logic (AND/OR/NOT)
    - Date range filtering
    - Sector/industry filtering
    - Minimum confidence threshold
    - GraphQL-style field selection
    """
    try:
        result = execute_boolean_query(query)
        return result
    except QueryError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query execution error: {str(e)}")


# =============================================================================
# Stats Endpoint
# =============================================================================

@router.get("/stats")
async def get_api_stats(
    key: Optional[APIKeyInfo] = Depends(optional_api_key),
):
    """
    Get API and data statistics.
    
    Returns counts of entities, signals, profiles, and divergences.
    """
    store = get_store()
    stats = store.get_stats()
    
    return {
        "data_stats": stats,
        "api_version": "v1",
        "timestamp": datetime.utcnow().isoformat(),
    }
