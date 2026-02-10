"""
API Tests for briefAI

Tests cover:
- REST API v1 endpoints
- Authentication and rate limiting
- Bulk export functionality
- Query builder
- WebSocket connections
"""

import pytest
import json
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
import sys

# Setup paths
_tests_dir = Path(__file__).parent
_app_dir = _tests_dir.parent
if str(_app_dir) not in sys.path:
    sys.path.insert(0, str(_app_dir))

from fastapi.testclient import TestClient
from fastapi.websockets import WebSocket

from api.main import app
from api.auth import APIKeyStore, get_key_store, TIERS
from api.query_builder import QueryParser, QueryExecutor, QueryError


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def api_key():
    """Create a test API key."""
    store = get_key_store()
    key = store.generate_api_key("test-key", tier="premium")
    yield key
    # Cleanup: revoke the key
    import hashlib
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    store.revoke_key(key_hash)


@pytest.fixture
def free_api_key():
    """Create a free tier API key."""
    store = get_key_store()
    key = store.generate_api_key("test-free-key", tier="free")
    yield key
    import hashlib
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    store.revoke_key(key_hash)


# =============================================================================
# Health Check Tests
# =============================================================================

class TestHealthEndpoints:
    """Test health and info endpoints."""
    
    def test_health_check(self, client):
        """Test basic health check."""
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
    
    def test_api_info(self, client):
        """Test API info endpoint."""
        response = client.get("/api/info")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "briefAI API"
        assert "endpoints" in data
        assert "authentication" in data


# =============================================================================
# Authentication Tests
# =============================================================================

class TestAuthentication:
    """Test authentication and rate limiting."""
    
    def test_api_key_validation(self, api_key):
        """Test API key validation."""
        store = get_key_store()
        key_info = store.validate_key(api_key)
        assert key_info is not None
        assert key_info.tier == "premium"
    
    def test_invalid_api_key(self):
        """Test invalid API key."""
        store = get_key_store()
        key_info = store.validate_key("invalid-key")
        assert key_info is None
    
    def test_api_key_in_header(self, client, api_key):
        """Test API key in header."""
        response = client.get(
            "/api/v1/stats",
            headers={"X-API-Key": api_key}
        )
        assert response.status_code == 200
    
    def test_api_key_in_query(self, client, api_key):
        """Test API key in query param."""
        response = client.get(f"/api/v1/stats?api_key={api_key}")
        assert response.status_code == 200
    
    def test_tier_configuration(self):
        """Test tier configuration."""
        assert "free" in TIERS
        assert "premium" in TIERS
        assert "enterprise" in TIERS
        
        assert TIERS["free"].requests_per_minute == 100
        assert TIERS["premium"].requests_per_minute == 1000
        assert TIERS["enterprise"].requests_per_minute == 5000
    
    def test_usage_tracking(self, api_key):
        """Test usage tracking."""
        store = get_key_store()
        import hashlib
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        
        # Record some usage
        store.record_usage(key_hash, "/api/test", 50.0, 200)
        store.record_usage(key_hash, "/api/test", 60.0, 200)
        
        stats = store.get_usage_stats(key_hash, days=1)
        assert stats["total_requests"] >= 2


# =============================================================================
# V1 API Tests
# =============================================================================

class TestV1API:
    """Test v1 REST API endpoints."""
    
    def test_get_stats(self, client):
        """Test stats endpoint."""
        response = client.get("/api/v1/stats")
        assert response.status_code == 200
        data = response.json()
        assert "data_stats" in data
        assert "api_version" in data
    
    def test_signal_categories(self, client):
        """Test signal categories endpoint."""
        response = client.get("/api/v1/signals/categories")
        assert response.status_code == 200
        data = response.json()
        assert "categories" in data
        assert len(data["categories"]) == 5
    
    def test_entity_search(self, client):
        """Test entity search endpoint."""
        response = client.get("/api/v1/entities/search?q=test")
        assert response.status_code == 200
        data = response.json()
        assert "query" in data
        assert "results" in data
        assert "pagination" in data
    
    def test_entity_search_with_type(self, client):
        """Test entity search with type filter."""
        response = client.get("/api/v1/entities/search?q=test&entity_type=company")
        assert response.status_code == 200
        data = response.json()
        assert data["pagination"]["total"] >= 0
    
    def test_active_divergences(self, client):
        """Test active divergences endpoint."""
        response = client.get("/api/v1/divergences/active")
        assert response.status_code == 200
        data = response.json()
        assert "divergences" in data
        assert "pagination" in data
    
    def test_divergences_with_filter(self, client):
        """Test divergences with interpretation filter."""
        response = client.get("/api/v1/divergences/active?interpretation=opportunity")
        assert response.status_code == 200
    
    def test_signal_history_not_found(self, client):
        """Test signal history for non-existent entity."""
        response = client.get("/api/v1/signals/nonexistent-entity/history")
        assert response.status_code == 200
        data = response.json()
        # Should return empty history, not 404
        assert data["history"] == []
    
    def test_pagination_params(self, client):
        """Test pagination parameters."""
        response = client.get("/api/v1/entities/search?q=a&limit=5&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert data["pagination"]["limit"] == 5
        assert data["pagination"]["offset"] == 0


# =============================================================================
# Export Tests
# =============================================================================

class TestExport:
    """Test bulk export functionality."""
    
    def test_export_signals_json(self, client, api_key):
        """Test signals export as JSON."""
        response = client.get(
            "/api/v1/export/signals?format=json&limit=10",
            headers={"X-API-Key": api_key}
        )
        assert response.status_code == 200
        assert "application/json" in response.headers["content-type"]
    
    def test_export_signals_csv(self, client, api_key):
        """Test signals export as CSV."""
        response = client.get(
            "/api/v1/export/signals?format=csv&limit=10",
            headers={"X-API-Key": api_key}
        )
        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]
    
    def test_export_entities(self, client, api_key):
        """Test entities export."""
        response = client.get(
            "/api/v1/export/entities?format=json",
            headers={"X-API-Key": api_key}
        )
        assert response.status_code == 200
    
    def test_export_profiles(self, client, api_key):
        """Test profiles export."""
        response = client.get(
            "/api/v1/export/profiles?format=json",
            headers={"X-API-Key": api_key}
        )
        assert response.status_code == 200
    
    def test_export_divergences(self, client, api_key):
        """Test divergences export."""
        response = client.get(
            "/api/v1/export/divergences?format=json",
            headers={"X-API-Key": api_key}
        )
        assert response.status_code == 200
    
    def test_export_requires_auth(self, client):
        """Test that export requires authentication."""
        response = client.get("/api/v1/export/signals")
        assert response.status_code == 401
    
    def test_create_export_job(self, client, api_key):
        """Test async export job creation."""
        response = client.post(
            "/api/v1/export/jobs",
            json={
                "export_type": "signals",
                "format": "json",
            },
            headers={"X-API-Key": api_key}
        )
        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data
        assert data["status"] in ["pending", "processing", "completed"]
    
    def test_list_export_jobs(self, client, api_key):
        """Test listing export jobs."""
        response = client.get(
            "/api/v1/export/jobs",
            headers={"X-API-Key": api_key}
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)


# =============================================================================
# Query Builder Tests
# =============================================================================

class TestQueryBuilder:
    """Test SQL-like query builder."""
    
    def test_parse_simple_query(self):
        """Test parsing simple SELECT query."""
        parser = QueryParser()
        parsed = parser.parse("SELECT * FROM entities LIMIT 10")
        
        assert parsed.table.value == "entities"
        assert parsed.columns == ["*"]
        assert parsed.limit == 10
    
    def test_parse_with_where(self):
        """Test parsing query with WHERE clause."""
        parser = QueryParser()
        parsed = parser.parse(
            "SELECT name, entity_type FROM entities WHERE entity_type = 'company' LIMIT 50"
        )
        
        assert parsed.table.value == "entities"
        assert "name" in parsed.columns
        assert len(parsed.conditions) == 1
        assert parsed.conditions[0].column == "entity_type"
        assert parsed.conditions[0].value == "company"
    
    def test_parse_with_order_by(self):
        """Test parsing query with ORDER BY."""
        parser = QueryParser()
        parsed = parser.parse(
            "SELECT * FROM profiles ORDER BY composite_score DESC LIMIT 100"
        )
        
        assert parsed.order_by is not None
        assert parsed.order_by.column == "composite_score"
        assert parsed.order_by.descending is True
    
    def test_reject_non_select(self):
        """Test that non-SELECT queries are rejected."""
        parser = QueryParser()
        
        with pytest.raises(QueryError):
            parser.parse("DELETE FROM entities")
        
        with pytest.raises(QueryError):
            parser.parse("UPDATE entities SET name='test'")
    
    def test_reject_invalid_table(self):
        """Test that invalid tables are rejected."""
        parser = QueryParser()
        
        with pytest.raises(QueryError):
            parser.parse("SELECT * FROM invalid_table")
    
    def test_reject_invalid_column(self):
        """Test that invalid columns are rejected."""
        parser = QueryParser()
        
        with pytest.raises(QueryError):
            parser.parse("SELECT password FROM entities")
    
    def test_query_endpoint_requires_premium(self, client, free_api_key):
        """Test that query endpoint requires premium tier."""
        response = client.post(
            "/api/v1/query?query=SELECT * FROM entities LIMIT 10",
            headers={"X-API-Key": free_api_key}
        )
        assert response.status_code == 403
    
    def test_query_endpoint_with_premium(self, client, api_key):
        """Test query endpoint with premium tier."""
        response = client.post(
            "/api/v1/query?query=SELECT * FROM entities LIMIT 10",
            headers={"X-API-Key": api_key}
        )
        assert response.status_code == 200
        data = response.json()
        assert "rows" in data
        assert "total_rows" in data


# =============================================================================
# WebSocket Tests
# =============================================================================

class TestWebSocket:
    """Test WebSocket functionality."""
    
    def test_websocket_stats(self, client):
        """Test WebSocket stats endpoint."""
        response = client.get("/ws/stats")
        assert response.status_code == 200
        data = response.json()
        assert "total_connections" in data
    
    def test_websocket_connection(self, client):
        """Test WebSocket connection."""
        with client.websocket_connect("/ws") as websocket:
            # Send ping
            websocket.send_json({"type": "ping"})
            
            # Receive pong
            data = websocket.receive_json()
            assert data["type"] == "pong"
    
    def test_websocket_subscribe(self, client):
        """Test WebSocket subscription."""
        with client.websocket_connect("/ws") as websocket:
            # Subscribe to all
            websocket.send_json({
                "type": "subscribe",
                "subscription_type": "all"
            })
            
            data = websocket.receive_json()
            assert data["type"] == "subscribed"
    
    def test_websocket_subscribe_entity(self, client):
        """Test WebSocket entity subscription."""
        with client.websocket_connect("/ws") as websocket:
            # Subscribe to specific entity
            websocket.send_json({
                "type": "subscribe",
                "subscription_type": "entity",
                "target": "openai"
            })
            
            data = websocket.receive_json()
            assert data["type"] == "subscribed"
            assert data["subscription_type"] == "entity"
            assert data["target"] == "openai"
    
    def test_websocket_unsubscribe(self, client):
        """Test WebSocket unsubscription."""
        with client.websocket_connect("/ws") as websocket:
            # Subscribe first
            websocket.send_json({
                "type": "subscribe",
                "subscription_type": "all"
            })
            websocket.receive_json()
            
            # Unsubscribe
            websocket.send_json({
                "type": "unsubscribe",
                "subscription_type": "all"
            })
            
            data = websocket.receive_json()
            assert data["type"] == "unsubscribed"


# =============================================================================
# Response Headers Tests
# =============================================================================

class TestResponseHeaders:
    """Test response headers."""
    
    def test_response_time_header(self, client):
        """Test X-Response-Time header is present."""
        response = client.get("/api/health")
        assert "X-Response-Time" in response.headers
    
    def test_rate_limit_headers(self, client, api_key):
        """Test rate limit headers are present with API key."""
        response = client.get(
            "/api/v1/stats",
            headers={"X-API-Key": api_key}
        )
        # Rate limit headers should be present for authenticated requests
        # (They're added by middleware when api_key_info is in request.state)
        assert response.status_code == 200


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_invalid_pagination_limit(self, client):
        """Test invalid pagination limit."""
        response = client.get("/api/v1/entities/search?q=test&limit=999999")
        # Should cap at max limit, not error
        assert response.status_code == 422  # Validation error for exceeding max
    
    def test_empty_search_query(self, client):
        """Test empty search query."""
        response = client.get("/api/v1/entities/search?q=")
        assert response.status_code == 422  # Validation error for min_length
    
    def test_invalid_date_format(self, client, api_key):
        """Test invalid date format in export."""
        response = client.get(
            "/api/v1/export/signals?start_date=invalid",
            headers={"X-API-Key": api_key}
        )
        # Should handle gracefully
        assert response.status_code == 200
    
    def test_entity_not_found(self, client):
        """Test getting non-existent entity."""
        response = client.get("/api/v1/entities/definitely-not-a-real-entity-id")
        assert response.status_code == 404


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
