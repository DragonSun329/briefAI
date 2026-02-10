"""
Professional Authentication and Rate Limiting for briefAI API.

Bloomberg-quality access control:
- API key authentication with secure hashing
- Tiered rate limiting (free: 10/min, pro: 100/min, enterprise: 1000/min)
- Usage tracking and analytics in SQLite
- Feature flags per tier
- Token bucket rate limiting with burst allowance
"""

import time
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from pathlib import Path
import sqlite3
import json
from collections import defaultdict
import threading
import asyncio

from fastapi import HTTPException, Security, Request, Depends
from fastapi.security import APIKeyHeader, APIKeyQuery
from pydantic import BaseModel, Field


# =============================================================================
# API Key Extraction
# =============================================================================

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
API_KEY_QUERY = APIKeyQuery(name="api_key", auto_error=False)


# =============================================================================
# Models
# =============================================================================

class APIKeyTier(BaseModel):
    """API key tier configuration."""
    name: str
    display_name: str
    requests_per_minute: int
    requests_per_day: int
    burst_size: int = 10
    export_enabled: bool = True
    websocket_enabled: bool = True
    query_builder_enabled: bool = False
    streaming_enabled: bool = False
    excel_export_enabled: bool = False
    max_export_rows: int = 10000
    max_websocket_subscriptions: int = 10
    priority_support: bool = False
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "premium",
                "display_name": "Premium",
                "requests_per_minute": 100,
                "requests_per_day": 50000,
                "burst_size": 20,
                "export_enabled": True,
                "websocket_enabled": True,
                "query_builder_enabled": True,
            }
        }


# Tier definitions - Bloomberg-style tiering
TIERS: Dict[str, APIKeyTier] = {
    "free": APIKeyTier(
        name="free",
        display_name="Free",
        requests_per_minute=10,
        requests_per_day=1000,
        burst_size=5,
        export_enabled=True,
        websocket_enabled=True,
        query_builder_enabled=False,
        streaming_enabled=False,
        excel_export_enabled=False,
        max_export_rows=1000,
        max_websocket_subscriptions=5,
        priority_support=False,
    ),
    "pro": APIKeyTier(
        name="pro",
        display_name="Professional",
        requests_per_minute=100,
        requests_per_day=50000,
        burst_size=20,
        export_enabled=True,
        websocket_enabled=True,
        query_builder_enabled=True,
        streaming_enabled=True,
        excel_export_enabled=True,
        max_export_rows=100000,
        max_websocket_subscriptions=50,
        priority_support=False,
    ),
    "premium": APIKeyTier(
        name="premium",
        display_name="Premium",
        requests_per_minute=500,
        requests_per_day=200000,
        burst_size=50,
        export_enabled=True,
        websocket_enabled=True,
        query_builder_enabled=True,
        streaming_enabled=True,
        excel_export_enabled=True,
        max_export_rows=500000,
        max_websocket_subscriptions=100,
        priority_support=True,
    ),
    "enterprise": APIKeyTier(
        name="enterprise",
        display_name="Enterprise",
        requests_per_minute=1000,
        requests_per_day=1000000,
        burst_size=100,
        export_enabled=True,
        websocket_enabled=True,
        query_builder_enabled=True,
        streaming_enabled=True,
        excel_export_enabled=True,
        max_export_rows=1000000,
        max_websocket_subscriptions=500,
        priority_support=True,
    ),
}


class APIKeyInfo(BaseModel):
    """API key information."""
    key_hash: str
    name: str
    tier: str
    owner_email: Optional[str] = None
    created_at: datetime
    expires_at: Optional[datetime] = None
    enabled: bool = True
    metadata: Dict[str, Any] = {}
    last_used_at: Optional[datetime] = None
    total_requests: int = 0


class APIKeyCreate(BaseModel):
    """Request to create a new API key."""
    name: str = Field(..., min_length=1, max_length=100)
    tier: str = Field("free", description="Tier: free, pro, premium, enterprise")
    owner_email: Optional[str] = None
    expires_days: Optional[int] = Field(None, ge=1, le=365)
    metadata: Dict[str, Any] = {}
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "My Application",
                "tier": "pro",
                "owner_email": "dev@example.com",
                "expires_days": 365
            }
        }


class UsageRecord(BaseModel):
    """Usage tracking record."""
    key_hash: str
    endpoint: str
    method: str
    timestamp: datetime
    response_time_ms: float
    status_code: int
    request_size_bytes: Optional[int] = None
    response_size_bytes: Optional[int] = None


class UsageStats(BaseModel):
    """Usage statistics for an API key."""
    key_hash: str
    period_start: str
    period_end: str
    total_requests: int
    successful_requests: int
    failed_requests: int
    avg_response_time_ms: float
    p95_response_time_ms: Optional[float] = None
    total_request_bytes: int
    total_response_bytes: int
    requests_by_endpoint: Dict[str, int]
    requests_by_status: Dict[int, int]
    daily_breakdown: List[Dict[str, Any]]


class RateLimitInfo(BaseModel):
    """Rate limit status information."""
    tier: str
    limit_per_minute: int
    limit_per_day: int
    remaining_minute: int
    remaining_day: int
    reset_at: str
    burst_remaining: int


# =============================================================================
# Token Bucket Rate Limiter
# =============================================================================

class TokenBucket:
    """Token bucket for rate limiting with burst support."""
    
    def __init__(self, rate: float, capacity: int):
        self.rate = rate  # tokens per second
        self.capacity = capacity
        self.tokens = capacity
        self.last_update = time.time()
        self._lock = threading.Lock()
    
    def consume(self, tokens: int = 1) -> tuple[bool, int]:
        """
        Try to consume tokens.
        Returns (allowed, remaining_tokens).
        """
        with self._lock:
            now = time.time()
            elapsed = now - self.last_update
            
            # Add tokens based on elapsed time
            self.tokens = min(
                self.capacity,
                self.tokens + elapsed * self.rate
            )
            self.last_update = now
            
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True, int(self.tokens)
            
            return False, 0
    
    def get_remaining(self) -> int:
        """Get remaining tokens without consuming."""
        with self._lock:
            now = time.time()
            elapsed = now - self.last_update
            return min(
                self.capacity,
                int(self.tokens + elapsed * self.rate)
            )


class RateLimiter:
    """Rate limiter using token buckets per API key."""
    
    def __init__(self):
        self._minute_buckets: Dict[str, TokenBucket] = {}
        self._day_buckets: Dict[str, TokenBucket] = {}
        self._day_counts: Dict[str, Dict[str, int]] = defaultdict(dict)
        self._lock = threading.Lock()
    
    def check_rate_limit(
        self, 
        key_hash: str, 
        tier: APIKeyTier
    ) -> tuple[bool, RateLimitInfo]:
        """
        Check if request is within rate limits.
        
        Returns:
            (allowed, rate_limit_info)
        """
        with self._lock:
            # Initialize buckets if needed
            if key_hash not in self._minute_buckets:
                self._minute_buckets[key_hash] = TokenBucket(
                    rate=tier.requests_per_minute / 60.0,
                    capacity=tier.burst_size,
                )
            
            # Check minute limit
            minute_allowed, minute_remaining = self._minute_buckets[key_hash].consume()
            
            # Check daily limit
            today = datetime.utcnow().strftime("%Y-%m-%d")
            if today not in self._day_counts[key_hash]:
                self._day_counts[key_hash] = {today: 0}
            
            day_count = self._day_counts[key_hash].get(today, 0)
            day_allowed = day_count < tier.requests_per_day
            
            if minute_allowed and day_allowed:
                self._day_counts[key_hash][today] = day_count + 1
            
            # Calculate reset time
            reset_at = datetime.utcnow().replace(
                second=0, microsecond=0
            ) + timedelta(minutes=1)
            
            info = RateLimitInfo(
                tier=tier.name,
                limit_per_minute=tier.requests_per_minute,
                limit_per_day=tier.requests_per_day,
                remaining_minute=minute_remaining,
                remaining_day=max(0, tier.requests_per_day - day_count - 1),
                reset_at=reset_at.isoformat(),
                burst_remaining=minute_remaining,
            )
            
            return minute_allowed and day_allowed, info
    
    def get_usage_stats(self, key_hash: str, tier: APIKeyTier) -> RateLimitInfo:
        """Get current rate limit stats without consuming."""
        with self._lock:
            minute_remaining = 0
            if key_hash in self._minute_buckets:
                minute_remaining = self._minute_buckets[key_hash].get_remaining()
            else:
                minute_remaining = tier.burst_size
            
            today = datetime.utcnow().strftime("%Y-%m-%d")
            day_count = self._day_counts.get(key_hash, {}).get(today, 0)
            
            reset_at = datetime.utcnow().replace(
                second=0, microsecond=0
            ) + timedelta(minutes=1)
            
            return RateLimitInfo(
                tier=tier.name,
                limit_per_minute=tier.requests_per_minute,
                limit_per_day=tier.requests_per_day,
                remaining_minute=minute_remaining,
                remaining_day=max(0, tier.requests_per_day - day_count),
                reset_at=reset_at.isoformat(),
                burst_remaining=minute_remaining,
            )


# =============================================================================
# API Key Store
# =============================================================================

class APIKeyStore:
    """SQLite-based API key storage and usage tracking."""
    
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = str(Path(__file__).parent.parent / "data" / "api_keys.db")
        
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._ensure_tables()
    
    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _ensure_tables(self):
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # API keys table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                key_hash TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                tier TEXT NOT NULL DEFAULT 'free',
                owner_email TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                enabled INTEGER DEFAULT 1,
                metadata TEXT DEFAULT '{}',
                last_used_at TIMESTAMP,
                total_requests INTEGER DEFAULT 0
            )
        """)
        
        # Usage tracking table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key_hash TEXT NOT NULL,
                endpoint TEXT NOT NULL,
                method TEXT NOT NULL DEFAULT 'GET',
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                response_time_ms REAL,
                status_code INTEGER,
                request_size_bytes INTEGER,
                response_size_bytes INTEGER,
                user_agent TEXT,
                ip_address TEXT,
                FOREIGN KEY (key_hash) REFERENCES api_keys(key_hash)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_usage_key ON api_usage(key_hash)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_usage_timestamp ON api_usage(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_usage_endpoint ON api_usage(endpoint)")
        
        # Daily usage aggregates (for faster queries)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_usage_daily (
                key_hash TEXT NOT NULL,
                date TEXT NOT NULL,
                request_count INTEGER DEFAULT 0,
                successful_count INTEGER DEFAULT 0,
                error_count INTEGER DEFAULT 0,
                total_response_time_ms REAL DEFAULT 0,
                total_request_bytes INTEGER DEFAULT 0,
                total_response_bytes INTEGER DEFAULT 0,
                PRIMARY KEY (key_hash, date)
            )
        """)
        
        # Hourly usage for detailed analytics
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_usage_hourly (
                key_hash TEXT NOT NULL,
                date_hour TEXT NOT NULL,
                endpoint TEXT NOT NULL,
                request_count INTEGER DEFAULT 0,
                avg_response_time_ms REAL,
                PRIMARY KEY (key_hash, date_hour, endpoint)
            )
        """)
        
        conn.commit()
        conn.close()
    
    def generate_api_key(
        self, 
        name: str, 
        tier: str = "free", 
        owner_email: Optional[str] = None,
        expires_days: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generate a new API key."""
        # Generate secure random key with tier prefix
        prefix = {
            "free": "bai_f",
            "pro": "bai_p", 
            "premium": "bai_m",
            "enterprise": "bai_e",
        }.get(tier, "bai_f")
        
        key = f"{prefix}_{secrets.token_urlsafe(32)}"
        key_hash = hashlib.sha256(key.encode()).hexdigest()
        
        expires_at = None
        if expires_days:
            expires_at = (datetime.utcnow() + timedelta(days=expires_days)).isoformat()
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO api_keys (key_hash, name, tier, owner_email, expires_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            key_hash, 
            name, 
            tier, 
            owner_email,
            expires_at, 
            json.dumps(metadata or {})
        ))
        
        conn.commit()
        conn.close()
        
        return key
    
    def validate_key(self, api_key: str) -> Optional[APIKeyInfo]:
        """Validate an API key and return its info."""
        if not api_key:
            return None
        
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM api_keys WHERE key_hash = ?", (key_hash,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        # Check if expired
        if row["expires_at"]:
            expires_at = datetime.fromisoformat(row["expires_at"])
            if datetime.utcnow() > expires_at:
                return None
        
        # Check if enabled
        if not row["enabled"]:
            return None
        
        return APIKeyInfo(
            key_hash=row["key_hash"],
            name=row["name"],
            tier=row["tier"],
            owner_email=row["owner_email"],
            created_at=datetime.fromisoformat(row["created_at"]),
            expires_at=datetime.fromisoformat(row["expires_at"]) if row["expires_at"] else None,
            enabled=bool(row["enabled"]),
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            last_used_at=datetime.fromisoformat(row["last_used_at"]) if row["last_used_at"] else None,
            total_requests=row["total_requests"] or 0,
        )
    
    def record_usage(
        self, 
        key_hash: str, 
        endpoint: str, 
        method: str,
        response_time_ms: float, 
        status_code: int,
        request_size: Optional[int] = None,
        response_size: Optional[int] = None,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ):
        """Record API usage."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Insert detailed record
        cursor.execute("""
            INSERT INTO api_usage (
                key_hash, endpoint, method, response_time_ms, status_code,
                request_size_bytes, response_size_bytes, user_agent, ip_address
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            key_hash, endpoint, method, response_time_ms, status_code,
            request_size, response_size, user_agent, ip_address
        ))
        
        # Update daily aggregate
        today = datetime.utcnow().strftime("%Y-%m-%d")
        is_success = 1 if status_code < 400 else 0
        is_error = 1 if status_code >= 400 else 0
        
        cursor.execute("""
            INSERT INTO api_usage_daily (
                key_hash, date, request_count, successful_count, error_count,
                total_response_time_ms, total_request_bytes, total_response_bytes
            )
            VALUES (?, ?, 1, ?, ?, ?, ?, ?)
            ON CONFLICT(key_hash, date) DO UPDATE SET
                request_count = request_count + 1,
                successful_count = successful_count + ?,
                error_count = error_count + ?,
                total_response_time_ms = total_response_time_ms + ?,
                total_request_bytes = total_request_bytes + ?,
                total_response_bytes = total_response_bytes + ?
        """, (
            key_hash, today, is_success, is_error, response_time_ms,
            request_size or 0, response_size or 0,
            is_success, is_error, response_time_ms,
            request_size or 0, response_size or 0
        ))
        
        # Update hourly aggregate
        date_hour = datetime.utcnow().strftime("%Y-%m-%d %H:00")
        cursor.execute("""
            INSERT INTO api_usage_hourly (key_hash, date_hour, endpoint, request_count, avg_response_time_ms)
            VALUES (?, ?, ?, 1, ?)
            ON CONFLICT(key_hash, date_hour, endpoint) DO UPDATE SET
                request_count = request_count + 1,
                avg_response_time_ms = (avg_response_time_ms * request_count + ?) / (request_count + 1)
        """, (key_hash, date_hour, endpoint, response_time_ms, response_time_ms))
        
        # Update last_used_at and total_requests
        cursor.execute("""
            UPDATE api_keys 
            SET last_used_at = CURRENT_TIMESTAMP, 
                total_requests = total_requests + 1
            WHERE key_hash = ?
        """, (key_hash,))
        
        conn.commit()
        conn.close()
    
    def get_usage_stats(
        self, 
        key_hash: str, 
        days: int = 30
    ) -> UsageStats:
        """Get usage statistics for a key."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
        now = datetime.utcnow().strftime("%Y-%m-%d")
        
        # Get aggregated stats
        cursor.execute("""
            SELECT 
                SUM(request_count) as total_requests,
                SUM(successful_count) as successful,
                SUM(error_count) as errors,
                SUM(total_response_time_ms) / SUM(request_count) as avg_response_time,
                SUM(total_request_bytes) as total_request_bytes,
                SUM(total_response_bytes) as total_response_bytes
            FROM api_usage_daily
            WHERE key_hash = ? AND date >= ?
        """, (key_hash, cutoff))
        
        agg_row = cursor.fetchone()
        
        # Get daily breakdown
        cursor.execute("""
            SELECT date, request_count, successful_count, error_count,
                   total_response_time_ms / request_count as avg_response_time
            FROM api_usage_daily
            WHERE key_hash = ? AND date >= ?
            ORDER BY date DESC
        """, (key_hash, cutoff))
        
        daily = [dict(r) for r in cursor.fetchall()]
        
        # Get requests by endpoint
        cursor.execute("""
            SELECT endpoint, SUM(request_count) as count
            FROM api_usage_hourly
            WHERE key_hash = ? AND date_hour >= ?
            GROUP BY endpoint
            ORDER BY count DESC
        """, (key_hash, cutoff + " 00:00"))
        
        by_endpoint = {row["endpoint"]: row["count"] for row in cursor.fetchall()}
        
        # Get requests by status code
        cursor.execute("""
            SELECT status_code, COUNT(*) as count
            FROM api_usage
            WHERE key_hash = ? AND timestamp >= ?
            GROUP BY status_code
        """, (key_hash, cutoff))
        
        by_status = {row["status_code"]: row["count"] for row in cursor.fetchall()}
        
        conn.close()
        
        return UsageStats(
            key_hash=key_hash,
            period_start=cutoff,
            period_end=now,
            total_requests=agg_row["total_requests"] or 0,
            successful_requests=agg_row["successful"] or 0,
            failed_requests=agg_row["errors"] or 0,
            avg_response_time_ms=agg_row["avg_response_time"] or 0,
            total_request_bytes=agg_row["total_request_bytes"] or 0,
            total_response_bytes=agg_row["total_response_bytes"] or 0,
            requests_by_endpoint=by_endpoint,
            requests_by_status=by_status,
            daily_breakdown=daily,
        )
    
    def list_keys(self, include_disabled: bool = False) -> List[APIKeyInfo]:
        """List all API keys (admin function)."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        query = "SELECT * FROM api_keys"
        if not include_disabled:
            query += " WHERE enabled = 1"
        query += " ORDER BY created_at DESC"
        
        cursor.execute(query)
        rows = cursor.fetchall()
        conn.close()
        
        return [
            APIKeyInfo(
                key_hash=row["key_hash"],
                name=row["name"],
                tier=row["tier"],
                owner_email=row["owner_email"],
                created_at=datetime.fromisoformat(row["created_at"]),
                expires_at=datetime.fromisoformat(row["expires_at"]) if row["expires_at"] else None,
                enabled=bool(row["enabled"]),
                metadata=json.loads(row["metadata"]) if row["metadata"] else {},
                last_used_at=datetime.fromisoformat(row["last_used_at"]) if row["last_used_at"] else None,
                total_requests=row["total_requests"] or 0,
            )
            for row in rows
        ]
    
    def update_key(
        self, 
        key_hash: str, 
        tier: Optional[str] = None,
        enabled: Optional[bool] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Update an API key."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        updates = []
        params = []
        
        if tier is not None:
            updates.append("tier = ?")
            params.append(tier)
        if enabled is not None:
            updates.append("enabled = ?")
            params.append(1 if enabled else 0)
        if metadata is not None:
            updates.append("metadata = ?")
            params.append(json.dumps(metadata))
        
        if updates:
            params.append(key_hash)
            cursor.execute(
                f"UPDATE api_keys SET {', '.join(updates)} WHERE key_hash = ?",
                params
            )
            conn.commit()
        
        conn.close()
    
    def revoke_key(self, key_hash: str):
        """Revoke an API key."""
        self.update_key(key_hash, enabled=False)
    
    def delete_key(self, key_hash: str):
        """Permanently delete an API key and its usage data."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM api_usage WHERE key_hash = ?", (key_hash,))
        cursor.execute("DELETE FROM api_usage_daily WHERE key_hash = ?", (key_hash,))
        cursor.execute("DELETE FROM api_usage_hourly WHERE key_hash = ?", (key_hash,))
        cursor.execute("DELETE FROM api_keys WHERE key_hash = ?", (key_hash,))
        
        conn.commit()
        conn.close()


# =============================================================================
# Global Instances
# =============================================================================

_key_store: Optional[APIKeyStore] = None
_rate_limiter = RateLimiter()


def get_key_store() -> APIKeyStore:
    global _key_store
    if _key_store is None:
        _key_store = APIKeyStore()
    return _key_store


# =============================================================================
# FastAPI Dependencies
# =============================================================================

async def get_api_key(
    api_key_header: str = Security(API_KEY_HEADER),
    api_key_query: str = Security(API_KEY_QUERY),
) -> Optional[str]:
    """Extract API key from header or query param."""
    return api_key_header or api_key_query


async def verify_api_key(
    request: Request,
    api_key: str = Depends(get_api_key),
) -> APIKeyInfo:
    """
    Verify API key and check rate limits.
    
    Raises HTTPException if invalid or rate limited.
    """
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "authentication_required",
                "message": "API key required. Pass via X-API-Key header or api_key query param.",
                "docs": "/api/docs#section/Authentication",
            },
            headers={"WWW-Authenticate": "ApiKey"},
        )
    
    store = get_key_store()
    key_info = store.validate_key(api_key)
    
    if not key_info:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "invalid_api_key",
                "message": "Invalid or expired API key.",
            },
        )
    
    # Check rate limit
    tier = TIERS.get(key_info.tier, TIERS["free"])
    allowed, rate_info = _rate_limiter.check_rate_limit(key_info.key_hash, tier)
    
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "rate_limit_exceeded",
                "message": f"Rate limit exceeded. Limit: {tier.requests_per_minute}/min for {tier.display_name} tier.",
                "tier": tier.name,
                "upgrade_url": "/api/v1/account/upgrade",
            },
            headers={
                "X-RateLimit-Limit": str(tier.requests_per_minute),
                "X-RateLimit-Remaining": str(rate_info.remaining_minute),
                "X-RateLimit-Reset": rate_info.reset_at,
                "Retry-After": "60",
            },
        )
    
    # Add rate limit info to request state
    request.state.rate_limit_remaining = rate_info.remaining_minute
    request.state.rate_limit_limit = tier.requests_per_minute
    request.state.rate_limit_info = rate_info
    request.state.api_key_info = key_info
    
    return key_info


async def optional_api_key(
    api_key: str = Depends(get_api_key),
) -> Optional[APIKeyInfo]:
    """
    Optional API key verification.
    Returns None if no key provided, otherwise validates.
    """
    if not api_key:
        return None
    
    store = get_key_store()
    return store.validate_key(api_key)


def require_tier(required_tier: str):
    """
    Dependency that requires a specific tier or higher.
    
    Usage:
        @router.get("/premium-endpoint")
        async def premium_endpoint(key: APIKeyInfo = Depends(require_tier("premium"))):
            ...
    """
    tier_order = ["free", "pro", "premium", "enterprise"]
    required_level = tier_order.index(required_tier) if required_tier in tier_order else 0
    
    async def tier_check(key_info: APIKeyInfo = Depends(verify_api_key)) -> APIKeyInfo:
        key_level = tier_order.index(key_info.tier) if key_info.tier in tier_order else 0
        
        if key_level < required_level:
            tier_config = TIERS.get(required_tier, TIERS["free"])
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "insufficient_tier",
                    "message": f"This endpoint requires {tier_config.display_name} tier or higher. Current tier: {key_info.tier}",
                    "required_tier": required_tier,
                    "current_tier": key_info.tier,
                    "upgrade_url": "/api/v1/account/upgrade",
                },
            )
        
        return key_info
    
    return tier_check


def require_feature(feature: str):
    """
    Dependency that requires a specific feature to be enabled.
    
    Features: export_enabled, websocket_enabled, query_builder_enabled, 
              streaming_enabled, excel_export_enabled
    """
    async def feature_check(key_info: APIKeyInfo = Depends(verify_api_key)) -> APIKeyInfo:
        tier = TIERS.get(key_info.tier, TIERS["free"])
        
        if not getattr(tier, feature, False):
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "feature_not_available",
                    "message": f"Feature '{feature}' not available for {tier.display_name} tier.",
                    "feature": feature,
                    "current_tier": key_info.tier,
                    "upgrade_url": "/api/v1/account/upgrade",
                },
            )
        
        return key_info
    
    return feature_check


# =============================================================================
# Usage Tracking Middleware Helper
# =============================================================================

async def track_usage(
    request: Request,
    response_time_ms: float,
    status_code: int,
    response_size: Optional[int] = None,
):
    """Track API usage after request completion."""
    if hasattr(request.state, "api_key_info"):
        key_info: APIKeyInfo = request.state.api_key_info
        store = get_key_store()
        
        store.record_usage(
            key_hash=key_info.key_hash,
            endpoint=str(request.url.path),
            method=request.method,
            response_time_ms=response_time_ms,
            status_code=status_code,
            request_size=request.headers.get("content-length"),
            response_size=response_size,
            user_agent=request.headers.get("user-agent"),
            ip_address=request.client.host if request.client else None,
        )
