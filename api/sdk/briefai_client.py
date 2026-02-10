"""
briefAI Python SDK

Professional Python client for the briefAI API.

Features:
- Async and sync API clients
- Automatic rate limiting and retry
- WebSocket streaming support
- Type hints throughout
- Query builder helpers
- Export utilities

Installation:
    pip install requests websocket-client

Usage:
    from briefai_client import BriefAIClient
    
    client = BriefAIClient(api_key="your_key")
    
    # Search entities
    entities = client.entities.search("openai")
    
    # Get signal history
    history = client.signals.history("openai", category="technical", days=30)
    
    # Stream real-time updates
    for update in client.stream.subscribe(entities=["openai", "anthropic"]):
        print(update)
"""

import json
import time
import threading
from datetime import datetime, timedelta
from typing import (
    Optional, Dict, Any, List, Iterator, Generator, 
    Callable, Union, TypeVar, Generic
)
from dataclasses import dataclass, field
from enum import Enum
from urllib.parse import urljoin, urlencode
import logging

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except ImportError:
    requests = None

try:
    import websocket
except ImportError:
    websocket = None

logger = logging.getLogger(__name__)


# =============================================================================
# Exceptions
# =============================================================================

class BriefAIError(Exception):
    """Base exception for briefAI SDK."""
    pass


class AuthenticationError(BriefAIError):
    """Authentication failed."""
    pass


class RateLimitError(BriefAIError):
    """Rate limit exceeded."""
    
    def __init__(self, message: str, retry_after: int = 60):
        super().__init__(message)
        self.retry_after = retry_after


class APIError(BriefAIError):
    """API returned an error."""
    
    def __init__(self, message: str, status_code: int, response: Optional[Dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class ValidationError(BriefAIError):
    """Request validation failed."""
    pass


# =============================================================================
# Response Models
# =============================================================================

@dataclass
class Pagination:
    """Pagination metadata."""
    total: int
    limit: int
    offset: int
    has_more: bool


@dataclass
class Entity:
    """Entity response."""
    id: str
    canonical_id: str
    name: str
    entity_type: str
    aliases: List[str] = field(default_factory=list)
    description: Optional[str] = None
    website: Optional[str] = None
    headquarters: Optional[str] = None
    founded_date: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None


@dataclass
class SignalScore:
    """Signal score response."""
    id: str
    entity_id: str
    category: str
    score: float
    percentile: Optional[float] = None
    score_delta_7d: Optional[float] = None
    score_delta_30d: Optional[float] = None
    created_at: str = ""


@dataclass
class Profile:
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
    composite_score: float = 0.0
    momentum_7d: Optional[float] = None
    momentum_30d: Optional[float] = None


@dataclass
class Divergence:
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
    detected_at: str = ""
    resolved_at: Optional[str] = None


@dataclass
class ExportJob:
    """Export job response."""
    job_id: str
    export_type: str
    format: str
    status: str
    created_at: str
    completed_at: Optional[str] = None
    row_count: Optional[int] = None
    file_size_bytes: Optional[int] = None
    download_url: Optional[str] = None
    error: Optional[str] = None


@dataclass  
class RateLimitInfo:
    """Rate limit information."""
    tier: str
    limit_per_minute: int
    remaining_minute: int
    reset_at: str


# =============================================================================
# Query Builder
# =============================================================================

class QueryBuilder:
    """
    Fluent query builder for complex queries.
    
    Example:
        query = (QueryBuilder("signals")
            .select("entity_id", "score", "category")
            .where("category", "=", "technical")
            .where("score", ">=", 70)
            .order_by("score", desc=True)
            .limit(100)
            .build())
    """
    
    def __init__(self, table: str):
        self.table = table
        self._select: List[str] = []
        self._where: Dict[str, Any] = {}
        self._and_conditions: List[Dict] = []
        self._or_conditions: List[Dict] = []
        self._not_conditions: List[Dict] = []
        self._order_by: Optional[str] = None
        self._order_desc: bool = False
        self._limit: int = 100
        self._offset: int = 0
        self._date_from: Optional[str] = None
        self._date_to: Optional[str] = None
        self._sector: Optional[str] = None
        self._min_confidence: Optional[float] = None
    
    def select(self, *fields: str) -> 'QueryBuilder':
        """Select specific fields."""
        self._select.extend(fields)
        return self
    
    def where(self, field: str, operator: str, value: Any) -> 'QueryBuilder':
        """Add AND condition."""
        self._and_conditions.append({
            "field": field,
            "operator": operator,
            "value": value,
        })
        return self
    
    def or_where(self, field: str, operator: str, value: Any) -> 'QueryBuilder':
        """Add OR condition."""
        self._or_conditions.append({
            "field": field,
            "operator": operator,
            "value": value,
        })
        return self
    
    def not_where(self, field: str, operator: str, value: Any) -> 'QueryBuilder':
        """Add NOT condition."""
        self._not_conditions.append({
            "field": field,
            "operator": operator,
            "value": value,
        })
        return self
    
    def date_range(self, from_date: str, to_date: str) -> 'QueryBuilder':
        """Filter by date range (YYYY-MM-DD)."""
        self._date_from = from_date
        self._date_to = to_date
        return self
    
    def sector(self, sector: str) -> 'QueryBuilder':
        """Filter by sector."""
        self._sector = sector
        return self
    
    def min_confidence(self, threshold: float) -> 'QueryBuilder':
        """Set minimum confidence threshold."""
        self._min_confidence = threshold
        return self
    
    def order_by(self, field: str, desc: bool = False) -> 'QueryBuilder':
        """Set ordering."""
        self._order_by = field
        self._order_desc = desc
        return self
    
    def limit(self, limit: int) -> 'QueryBuilder':
        """Set result limit."""
        self._limit = limit
        return self
    
    def offset(self, offset: int) -> 'QueryBuilder':
        """Set result offset."""
        self._offset = offset
        return self
    
    def build(self) -> Dict[str, Any]:
        """Build the query as a dictionary."""
        query = {
            "table": self.table,
            "limit": self._limit,
            "offset": self._offset,
        }
        
        if self._select:
            query["select"] = self._select
        if self._and_conditions:
            query["and_conditions"] = self._and_conditions
        if self._or_conditions:
            query["or_conditions"] = self._or_conditions
        if self._not_conditions:
            query["not_conditions"] = self._not_conditions
        if self._date_from:
            query["date_from"] = self._date_from
        if self._date_to:
            query["date_to"] = self._date_to
        if self._sector:
            query["sector"] = self._sector
        if self._min_confidence is not None:
            query["min_confidence"] = self._min_confidence
        if self._order_by:
            query["order_by"] = self._order_by
            query["order_desc"] = self._order_desc
        
        return query


# =============================================================================
# API Client Components
# =============================================================================

class EntitiesAPI:
    """Entity-related API endpoints."""
    
    def __init__(self, client: 'BriefAIClient'):
        self._client = client
    
    def search(
        self, 
        query: str, 
        entity_type: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[List[Entity], Pagination]:
        """
        Search for entities.
        
        Args:
            query: Search query string
            entity_type: Filter by type (company, technology, person, etc.)
            limit: Max results to return
            offset: Pagination offset
            
        Returns:
            Tuple of (entities, pagination)
        """
        params = {"q": query, "limit": limit, "offset": offset}
        if entity_type:
            params["entity_type"] = entity_type
        
        resp = self._client._get("/api/v1/entities/search", params=params)
        
        entities = [Entity(**e) for e in resp.get("results", [])]
        pagination = Pagination(**resp.get("pagination", {}))
        
        return entities, pagination
    
    def get(self, entity_id: str) -> Entity:
        """Get entity by ID."""
        resp = self._client._get(f"/api/v1/entities/{entity_id}")
        return Entity(**resp)
    
    def profile(self, entity_id: str) -> Profile:
        """Get entity's signal profile."""
        resp = self._client._get(f"/api/v1/entities/{entity_id}/profile")
        return Profile(**resp)


class SignalsAPI:
    """Signal-related API endpoints."""
    
    def __init__(self, client: 'BriefAIClient'):
        self._client = client
    
    def history(
        self,
        entity_id: str,
        category: Optional[str] = None,
        days: int = 30,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[List[SignalScore], Pagination]:
        """
        Get signal history for an entity.
        
        Args:
            entity_id: Entity ID
            category: Filter by category (technical, company, financial, product, media)
            days: Number of days of history
            limit: Max results
            offset: Pagination offset
            
        Returns:
            Tuple of (signals, pagination)
        """
        params = {"days": days, "limit": limit, "offset": offset}
        if category:
            params["category"] = category
        
        resp = self._client._get(f"/api/v1/signals/{entity_id}/history", params=params)
        
        signals = [SignalScore(**s) for s in resp.get("history", [])]
        pagination = Pagination(**resp.get("pagination", {}))
        
        return signals, pagination
    
    def categories(self) -> List[Dict[str, Any]]:
        """List available signal categories."""
        resp = self._client._get("/api/v1/signals/categories")
        return resp.get("categories", [])


class DivergencesAPI:
    """Divergence-related API endpoints."""
    
    def __init__(self, client: 'BriefAIClient'):
        self._client = client
    
    def active(
        self,
        interpretation: Optional[str] = None,
        entity_id: Optional[str] = None,
        min_magnitude: Optional[float] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[List[Divergence], Pagination]:
        """
        Get active divergences.
        
        Args:
            interpretation: Filter by interpretation (opportunity, risk, anomaly, neutral)
            entity_id: Filter by entity
            min_magnitude: Minimum divergence magnitude
            limit: Max results
            offset: Pagination offset
            
        Returns:
            Tuple of (divergences, pagination)
        """
        params = {"limit": limit, "offset": offset}
        if interpretation:
            params["interpretation"] = interpretation
        if entity_id:
            params["entity_id"] = entity_id
        if min_magnitude is not None:
            params["min_magnitude"] = min_magnitude
        
        resp = self._client._get("/api/v1/divergences/active", params=params)
        
        divergences = [Divergence(**d) for d in resp.get("divergences", [])]
        pagination = Pagination(**resp.get("pagination", {}))
        
        return divergences, pagination


class ExportAPI:
    """Export-related API endpoints."""
    
    def __init__(self, client: 'BriefAIClient'):
        self._client = client
    
    def signals(
        self,
        format: str = "json",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        entity_ids: Optional[List[str]] = None,
        categories: Optional[List[str]] = None,
        min_score: Optional[float] = None,
        limit: int = 10000,
    ) -> bytes:
        """
        Export signals.
        
        Args:
            format: Export format (json, csv, jsonl, parquet)
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            entity_ids: Filter by entity IDs
            categories: Filter by categories
            min_score: Minimum score
            limit: Max rows
            
        Returns:
            Raw export data as bytes
        """
        params = {"format": format, "limit": limit}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        if entity_ids:
            params["entity_ids"] = ",".join(entity_ids)
        if categories:
            params["categories"] = ",".join(categories)
        if min_score is not None:
            params["min_score"] = min_score
        
        return self._client._get_raw("/api/v1/export/signals", params=params)
    
    def create_job(
        self,
        export_type: str,
        format: str = "json",
        **kwargs,
    ) -> ExportJob:
        """
        Create an async export job.
        
        Args:
            export_type: Type to export (signals, entities, profiles, divergences)
            format: Export format
            **kwargs: Additional filters
            
        Returns:
            ExportJob with job_id for tracking
        """
        data = {
            "export_type": export_type,
            "format": format,
            **kwargs,
        }
        
        resp = self._client._post("/api/v1/export/jobs", json=data)
        return ExportJob(**resp)
    
    def get_job(self, job_id: str) -> ExportJob:
        """Get export job status."""
        resp = self._client._get(f"/api/v1/export/jobs/{job_id}")
        return ExportJob(**resp)
    
    def download_job(self, job_id: str) -> bytes:
        """Download completed export job."""
        return self._client._get_raw(f"/api/v1/export/jobs/{job_id}/download")
    
    def wait_for_job(
        self, 
        job_id: str, 
        timeout: int = 300,
        poll_interval: int = 2,
    ) -> ExportJob:
        """
        Wait for an export job to complete.
        
        Args:
            job_id: Job ID to wait for
            timeout: Max seconds to wait
            poll_interval: Seconds between polls
            
        Returns:
            Completed ExportJob
            
        Raises:
            TimeoutError: If job doesn't complete in time
            APIError: If job fails
        """
        start = time.time()
        
        while time.time() - start < timeout:
            job = self.get_job(job_id)
            
            if job.status == "completed":
                return job
            elif job.status == "failed":
                raise APIError(f"Export job failed: {job.error}", 500)
            
            time.sleep(poll_interval)
        
        raise TimeoutError(f"Export job {job_id} did not complete within {timeout}s")


class QueryAPI:
    """Query builder API endpoints (Premium)."""
    
    def __init__(self, client: 'BriefAIClient'):
        self._client = client
    
    def execute(self, query: Union[str, Dict, QueryBuilder]) -> Dict[str, Any]:
        """
        Execute a query.
        
        Args:
            query: SQL-like string, dict, or QueryBuilder
            
        Returns:
            Query result with rows, columns, and metadata
        """
        if isinstance(query, QueryBuilder):
            query = query.build()
        
        if isinstance(query, str):
            return self._client._post("/api/v1/query", params={"query": query})
        else:
            return self._client._post("/api/v1/query/boolean", json=query)
    
    def builder(self, table: str) -> QueryBuilder:
        """Create a new query builder."""
        return QueryBuilder(table)


class StreamAPI:
    """WebSocket streaming API."""
    
    def __init__(self, client: 'BriefAIClient'):
        self._client = client
        self._ws: Optional[Any] = None
        self._running = False
        self._subscriptions: List[Dict] = []
    
    def subscribe(
        self,
        entities: Optional[List[str]] = None,
        categories: Optional[List[str]] = None,
        divergences: bool = False,
        all_updates: bool = False,
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Subscribe to real-time updates.
        
        Args:
            entities: List of entity IDs to subscribe to
            categories: List of categories to subscribe to
            divergences: Subscribe to divergence alerts
            all_updates: Subscribe to all updates
            
        Yields:
            Update messages as they arrive
        """
        if websocket is None:
            raise ImportError("websocket-client required: pip install websocket-client")
        
        ws_url = self._client.base_url.replace("http://", "ws://").replace("https://", "wss://")
        ws_url = f"{ws_url}/ws?api_key={self._client.api_key}"
        
        self._ws = websocket.create_connection(ws_url)
        self._running = True
        
        # Wait for connection confirmation
        initial = json.loads(self._ws.recv())
        if initial.get("type") not in ("connected", "reconnected"):
            raise APIError("WebSocket connection failed", 500, initial)
        
        # Subscribe
        if all_updates:
            self._ws.send(json.dumps({"type": "subscribe", "subscription_type": "all"}))
        
        if entities:
            for entity_id in entities:
                self._ws.send(json.dumps({
                    "type": "subscribe",
                    "subscription_type": "entity",
                    "target": entity_id,
                }))
        
        if categories:
            for category in categories:
                self._ws.send(json.dumps({
                    "type": "subscribe",
                    "subscription_type": "category",
                    "target": category,
                }))
        
        if divergences:
            self._ws.send(json.dumps({"type": "subscribe", "subscription_type": "divergence"}))
        
        # Read messages
        try:
            while self._running:
                data = self._ws.recv()
                if data:
                    msg = json.loads(data)
                    
                    # Handle heartbeat
                    if msg.get("type") == "heartbeat":
                        self._ws.send(json.dumps({"type": "ping"}))
                        continue
                    
                    # Skip subscription confirmations
                    if msg.get("type") in ("subscribed", "unsubscribed", "pong"):
                        continue
                    
                    yield msg
        finally:
            self.close()
    
    def close(self):
        """Close the WebSocket connection."""
        self._running = False
        if self._ws:
            self._ws.close()
            self._ws = None


# =============================================================================
# Main Client
# =============================================================================

class BriefAIClient:
    """
    briefAI API Client.
    
    Usage:
        client = BriefAIClient(
            api_key="your_key",
            base_url="http://localhost:8000"  # Optional
        )
        
        # Search entities
        entities, pagination = client.entities.search("openai")
        
        # Get signal history
        signals, pagination = client.signals.history("openai", category="technical")
        
        # Export data
        data = client.export.signals(format="csv", start_date="2025-01-01")
        
        # Execute query (Premium)
        result = client.query.execute(
            client.query.builder("signals")
                .where("category", "=", "technical")
                .where("score", ">=", 70)
                .limit(100)
                .build()
        )
        
        # Stream updates
        for update in client.stream.subscribe(entities=["openai"]):
            print(update)
    """
    
    def __init__(
        self,
        api_key: str,
        base_url: str = "http://localhost:8000",
        timeout: int = 30,
        max_retries: int = 3,
        retry_on_rate_limit: bool = True,
    ):
        """
        Initialize the client.
        
        Args:
            api_key: Your briefAI API key
            base_url: API base URL
            timeout: Request timeout in seconds
            max_retries: Max retry attempts for failed requests
            retry_on_rate_limit: Automatically retry when rate limited
        """
        if requests is None:
            raise ImportError("requests library required: pip install requests")
        
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_on_rate_limit = retry_on_rate_limit
        
        # Setup session with retry
        self._session = requests.Session()
        
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self._session.mount("http://", adapter)
        self._session.mount("https://", adapter)
        
        # API components
        self.entities = EntitiesAPI(self)
        self.signals = SignalsAPI(self)
        self.divergences = DivergencesAPI(self)
        self.export = ExportAPI(self)
        self.query = QueryAPI(self)
        self.stream = StreamAPI(self)
        
        # Rate limit tracking
        self._rate_limit_info: Optional[RateLimitInfo] = None
    
    def _headers(self) -> Dict[str, str]:
        """Get request headers."""
        return {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "briefai-python-sdk/1.0.0",
        }
    
    def _handle_response(self, resp: requests.Response) -> Any:
        """Handle API response."""
        # Track rate limit info
        if "X-RateLimit-Remaining" in resp.headers:
            self._rate_limit_info = RateLimitInfo(
                tier=resp.headers.get("X-RateLimit-Tier", "unknown"),
                limit_per_minute=int(resp.headers.get("X-RateLimit-Limit", 0)),
                remaining_minute=int(resp.headers.get("X-RateLimit-Remaining", 0)),
                reset_at=resp.headers.get("X-RateLimit-Reset", ""),
            )
        
        if resp.status_code == 401:
            raise AuthenticationError("Invalid API key")
        
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 60))
            raise RateLimitError(
                "Rate limit exceeded",
                retry_after=retry_after,
            )
        
        if resp.status_code >= 400:
            try:
                error_data = resp.json()
            except Exception:
                error_data = {"message": resp.text}
            
            raise APIError(
                error_data.get("detail", {}).get("message", str(error_data)),
                resp.status_code,
                error_data,
            )
        
        return resp.json()
    
    def _get(self, path: str, params: Optional[Dict] = None) -> Any:
        """Make GET request."""
        url = urljoin(self.base_url, path)
        
        for attempt in range(self.max_retries + 1):
            try:
                resp = self._session.get(
                    url,
                    params=params,
                    headers=self._headers(),
                    timeout=self.timeout,
                )
                return self._handle_response(resp)
            
            except RateLimitError as e:
                if self.retry_on_rate_limit and attempt < self.max_retries:
                    time.sleep(e.retry_after)
                    continue
                raise
    
    def _get_raw(self, path: str, params: Optional[Dict] = None) -> bytes:
        """Make GET request and return raw bytes."""
        url = urljoin(self.base_url, path)
        
        resp = self._session.get(
            url,
            params=params,
            headers={**self._headers(), "Accept": "*/*"},
            timeout=self.timeout,
        )
        
        if resp.status_code >= 400:
            self._handle_response(resp)
        
        return resp.content
    
    def _post(
        self, 
        path: str, 
        params: Optional[Dict] = None,
        json: Optional[Dict] = None,
    ) -> Any:
        """Make POST request."""
        url = urljoin(self.base_url, path)
        
        for attempt in range(self.max_retries + 1):
            try:
                resp = self._session.post(
                    url,
                    params=params,
                    json=json,
                    headers=self._headers(),
                    timeout=self.timeout,
                )
                return self._handle_response(resp)
            
            except RateLimitError as e:
                if self.retry_on_rate_limit and attempt < self.max_retries:
                    time.sleep(e.retry_after)
                    continue
                raise
    
    @property
    def rate_limit(self) -> Optional[RateLimitInfo]:
        """Get last known rate limit info."""
        return self._rate_limit_info
    
    def health(self) -> Dict[str, Any]:
        """Check API health."""
        return self._get("/api/health")
    
    def info(self) -> Dict[str, Any]:
        """Get API info."""
        return self._get("/api/info")
    
    def stats(self) -> Dict[str, Any]:
        """Get API stats."""
        return self._get("/api/v1/stats")


# =============================================================================
# Convenience Functions
# =============================================================================

def create_client(api_key: str, **kwargs) -> BriefAIClient:
    """Create a briefAI client."""
    return BriefAIClient(api_key, **kwargs)


def query(table: str) -> QueryBuilder:
    """Create a query builder."""
    return QueryBuilder(table)


# =============================================================================
# Async Client (optional)
# =============================================================================

try:
    import aiohttp
    import asyncio
    
    class AsyncBriefAIClient:
        """
        Async briefAI API Client.
        
        Usage:
            async with AsyncBriefAIClient(api_key="your_key") as client:
                entities = await client.search_entities("openai")
        """
        
        def __init__(
            self,
            api_key: str,
            base_url: str = "http://localhost:8000",
            timeout: int = 30,
        ):
            self.api_key = api_key
            self.base_url = base_url.rstrip("/")
            self.timeout = aiohttp.ClientTimeout(total=timeout)
            self._session: Optional[aiohttp.ClientSession] = None
        
        async def __aenter__(self):
            self._session = aiohttp.ClientSession(
                timeout=self.timeout,
                headers={
                    "X-API-Key": self.api_key,
                    "Content-Type": "application/json",
                    "User-Agent": "briefai-python-sdk/1.0.0",
                }
            )
            return self
        
        async def __aexit__(self, *args):
            if self._session:
                await self._session.close()
        
        async def _get(self, path: str, params: Optional[Dict] = None) -> Any:
            url = f"{self.base_url}{path}"
            async with self._session.get(url, params=params) as resp:
                if resp.status >= 400:
                    text = await resp.text()
                    raise APIError(text, resp.status)
                return await resp.json()
        
        async def search_entities(self, query: str, **kwargs) -> List[Entity]:
            resp = await self._get("/api/v1/entities/search", params={"q": query, **kwargs})
            return [Entity(**e) for e in resp.get("results", [])]
        
        async def get_entity(self, entity_id: str) -> Entity:
            resp = await self._get(f"/api/v1/entities/{entity_id}")
            return Entity(**resp)
        
        async def get_signal_history(
            self, 
            entity_id: str, 
            **kwargs
        ) -> List[SignalScore]:
            resp = await self._get(f"/api/v1/signals/{entity_id}/history", params=kwargs)
            return [SignalScore(**s) for s in resp.get("history", [])]
        
        async def get_divergences(self, **kwargs) -> List[Divergence]:
            resp = await self._get("/api/v1/divergences/active", params=kwargs)
            return [Divergence(**d) for d in resp.get("divergences", [])]

except ImportError:
    AsyncBriefAIClient = None


# =============================================================================
# CLI Interface (optional)
# =============================================================================

def main():
    """CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="briefAI CLI")
    parser.add_argument("--api-key", "-k", help="API key", required=True)
    parser.add_argument("--base-url", "-u", default="http://localhost:8000")
    
    subparsers = parser.add_subparsers(dest="command")
    
    # Search command
    search = subparsers.add_parser("search", help="Search entities")
    search.add_argument("query", help="Search query")
    search.add_argument("--type", help="Entity type filter")
    
    # Export command
    export = subparsers.add_parser("export", help="Export data")
    export.add_argument("type", choices=["signals", "entities", "profiles", "divergences"])
    export.add_argument("--format", "-f", default="json")
    export.add_argument("--output", "-o", help="Output file")
    
    args = parser.parse_args()
    
    client = BriefAIClient(api_key=args.api_key, base_url=args.base_url)
    
    if args.command == "search":
        entities, _ = client.entities.search(args.query, entity_type=args.type)
        for e in entities:
            print(f"{e.id}: {e.name} ({e.entity_type})")
    
    elif args.command == "export":
        data = getattr(client.export, args.type)(format=args.format)
        if args.output:
            with open(args.output, "wb") as f:
                f.write(data)
            print(f"Exported to {args.output}")
        else:
            print(data.decode())
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
