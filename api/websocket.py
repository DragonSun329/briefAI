"""
Professional WebSocket Real-Time Feed for briefAI API.

Bloomberg-quality real-time data streaming:
- Subscribe to specific entities
- Subscribe to alert types (divergence, signal_update, event)
- Heartbeat/reconnection handling
- Message batching for high-throughput
- Backpressure management
- Connection quality monitoring
"""

import asyncio
import json
import hashlib
import time
from datetime import datetime
from typing import Dict, Set, Optional, Any, List
from dataclasses import dataclass, field
from enum import Enum
import logging
import uuid

from fastapi import WebSocket, WebSocketDisconnect, Query
from pydantic import BaseModel, Field

from api.auth import get_key_store, TIERS

logger = logging.getLogger(__name__)


# =============================================================================
# Message Types
# =============================================================================

class MessageType(str, Enum):
    """WebSocket message types."""
    # Client -> Server
    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"
    PING = "ping"
    CONFIGURE = "configure"
    
    # Server -> Client
    SIGNAL_UPDATE = "signal_update"
    DIVERGENCE_ALERT = "divergence_alert"
    EVENT = "event"
    ENTITY_UPDATE = "entity_update"
    PROFILE_UPDATE = "profile_update"
    BATCH = "batch"
    ERROR = "error"
    PONG = "pong"
    SUBSCRIBED = "subscribed"
    UNSUBSCRIBED = "unsubscribed"
    CONNECTED = "connected"
    RECONNECTED = "reconnected"
    HEARTBEAT = "heartbeat"
    CONFIG_ACK = "config_ack"


class SubscriptionType(str, Enum):
    """Types of subscriptions."""
    ENTITY = "entity"               # Subscribe to specific entity updates
    CATEGORY = "category"           # Subscribe to signal category updates
    DIVERGENCE = "divergence"       # Subscribe to divergence alerts
    SIGNAL_UPDATE = "signal_update" # Subscribe to signal score updates
    EVENT = "event"                 # Subscribe to events
    PROFILE = "profile"             # Subscribe to profile updates
    ALERT = "alert"                 # Subscribe to all alert types
    ALL = "all"                     # Subscribe to all updates


class AlertSeverity(str, Enum):
    """Alert severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# =============================================================================
# Models
# =============================================================================

@dataclass
class Subscription:
    """A single subscription."""
    type: SubscriptionType
    target: Optional[str] = None
    min_score: Optional[float] = None
    min_severity: Optional[AlertSeverity] = None
    filters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ClientConfig:
    """Client configuration for message delivery."""
    batch_enabled: bool = False
    batch_size: int = 10
    batch_interval_ms: int = 1000
    heartbeat_interval_sec: int = 30
    include_metadata: bool = True
    compression: bool = False


@dataclass
class ClientConnection:
    """Represents a connected WebSocket client."""
    id: str
    websocket: WebSocket
    api_key_hash: Optional[str] = None
    tier: str = "free"
    subscriptions: Dict[str, Subscription] = field(default_factory=dict)
    config: ClientConfig = field(default_factory=ClientConfig)
    connected_at: datetime = field(default_factory=datetime.utcnow)
    last_ping: datetime = field(default_factory=datetime.utcnow)
    last_pong: datetime = field(default_factory=datetime.utcnow)
    messages_sent: int = 0
    messages_received: int = 0
    bytes_sent: int = 0
    reconnect_count: int = 0
    pending_messages: List[Dict[str, Any]] = field(default_factory=list)
    
    def subscription_key(self, sub: Subscription) -> str:
        """Generate unique key for a subscription."""
        return f"{sub.type.value}:{sub.target or '*'}"


class ConnectionStats(BaseModel):
    """Connection statistics for monitoring."""
    connection_id: str
    tier: str
    connected_at: str
    uptime_seconds: float
    messages_sent: int
    messages_received: int
    bytes_sent: int
    subscription_count: int
    last_ping_ago_seconds: float


class WebSocketStats(BaseModel):
    """Overall WebSocket statistics."""
    total_connections: int
    connections_by_tier: Dict[str, int]
    total_subscriptions: int
    subscriptions_by_type: Dict[str, int]
    messages_sent_total: int
    messages_per_minute: float


# =============================================================================
# Connection Manager
# =============================================================================

class ConnectionManager:
    """
    Manages WebSocket connections and message broadcasting.
    
    Features:
    - Subscription-based message routing
    - Heartbeat management
    - Message batching
    - Connection quality monitoring
    - Automatic cleanup
    """
    
    def __init__(self):
        self._connections: Dict[str, ClientConnection] = {}
        
        # Subscription indexes for fast lookup
        self._entity_subscribers: Dict[str, Set[str]] = {}
        self._category_subscribers: Dict[str, Set[str]] = {}
        self._divergence_subscribers: Set[str] = set()
        self._signal_update_subscribers: Set[str] = set()
        self._event_subscribers: Set[str] = set()
        self._profile_subscribers: Set[str] = set()
        self._alert_subscribers: Set[str] = set()
        self._all_subscribers: Set[str] = set()
        
        self._lock = asyncio.Lock()
        
        # Metrics
        self._messages_sent_total = 0
        self._messages_timestamps: List[float] = []
        
        # Heartbeat task
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._running = False
    
    async def start(self):
        """Start the connection manager background tasks."""
        self._running = True
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
    
    async def stop(self):
        """Stop the connection manager."""
        self._running = False
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
    
    async def _heartbeat_loop(self):
        """Send periodic heartbeats to all connections."""
        while self._running:
            try:
                await asyncio.sleep(30)
                await self._send_heartbeats()
                await self._cleanup_stale_connections()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat loop error: {e}")
    
    async def _send_heartbeats(self):
        """Send heartbeat to all connections."""
        async with self._lock:
            connections = list(self._connections.values())
        
        heartbeat_msg = {
            "type": MessageType.HEARTBEAT.value,
            "timestamp": datetime.utcnow().isoformat(),
            "server_time": int(time.time() * 1000),
        }
        
        for conn in connections:
            try:
                await conn.websocket.send_json(heartbeat_msg)
            except Exception:
                pass  # Connection will be cleaned up
    
    async def _cleanup_stale_connections(self):
        """Remove connections that haven't responded to pings."""
        now = datetime.utcnow()
        stale_threshold = 120  # 2 minutes
        
        async with self._lock:
            stale = [
                conn_id for conn_id, conn in self._connections.items()
                if (now - conn.last_pong).total_seconds() > stale_threshold
            ]
        
        for conn_id in stale:
            logger.info(f"Cleaning up stale connection: {conn_id}")
            if conn_id in self._connections:
                try:
                    await self._connections[conn_id].websocket.close()
                except Exception:
                    pass
                await self._remove_connection(conn_id)
    
    async def connect(
        self, 
        websocket: WebSocket, 
        api_key: Optional[str] = None,
        reconnect_id: Optional[str] = None,
    ) -> ClientConnection:
        """Accept a new WebSocket connection."""
        await websocket.accept()
        
        # Generate or reuse connection ID
        conn_id = reconnect_id or str(uuid.uuid4())
        
        # Validate API key
        key_hash = None
        tier = "free"
        if api_key:
            store = get_key_store()
            key_info = store.validate_key(api_key)
            if key_info:
                key_hash = key_info.key_hash
                tier = key_info.tier
        
        # Check for reconnection
        is_reconnect = False
        if reconnect_id and reconnect_id in self._connections:
            old_conn = self._connections[reconnect_id]
            is_reconnect = True
        
        conn = ClientConnection(
            id=conn_id,
            websocket=websocket,
            api_key_hash=key_hash,
            tier=tier,
            reconnect_count=1 if is_reconnect else 0,
        )
        
        async with self._lock:
            self._connections[conn_id] = conn
        
        logger.info(f"WebSocket connected: {conn_id} (tier: {tier}, reconnect: {is_reconnect})")
        
        # Send connection confirmation
        await self.send_personal(websocket, {
            "type": MessageType.RECONNECTED.value if is_reconnect else MessageType.CONNECTED.value,
            "connection_id": conn_id,
            "tier": tier,
            "timestamp": datetime.utcnow().isoformat(),
            "heartbeat_interval": conn.config.heartbeat_interval_sec,
            "features": {
                "batch": tier != "free",
                "compression": tier == "enterprise",
                "max_subscriptions": 100 if tier == "enterprise" else (50 if tier == "premium" else 10),
            },
        })
        
        return conn
    
    async def disconnect(self, websocket: WebSocket):
        """Handle WebSocket disconnection."""
        conn_id = None
        
        async with self._lock:
            for cid, conn in self._connections.items():
                if conn.websocket == websocket:
                    conn_id = cid
                    break
        
        if conn_id:
            await self._remove_connection(conn_id)
            logger.info(f"WebSocket disconnected: {conn_id}")
    
    async def _remove_connection(self, conn_id: str):
        """Remove a connection and clean up subscriptions."""
        async with self._lock:
            if conn_id in self._connections:
                # Clean up subscription indexes
                self._all_subscribers.discard(conn_id)
                self._divergence_subscribers.discard(conn_id)
                self._signal_update_subscribers.discard(conn_id)
                self._event_subscribers.discard(conn_id)
                self._profile_subscribers.discard(conn_id)
                self._alert_subscribers.discard(conn_id)
                
                for subs in self._entity_subscribers.values():
                    subs.discard(conn_id)
                for subs in self._category_subscribers.values():
                    subs.discard(conn_id)
                
                del self._connections[conn_id]
    
    async def subscribe(
        self, 
        conn_id: str, 
        subscription: Subscription
    ) -> bool:
        """Add a subscription for a client."""
        async with self._lock:
            if conn_id not in self._connections:
                return False
            
            conn = self._connections[conn_id]
            sub_key = conn.subscription_key(subscription)
            
            # Check subscription limit
            tier_config = TIERS.get(conn.tier, TIERS["free"])
            max_subs = 100 if conn.tier == "enterprise" else (50 if conn.tier == "premium" else 10)
            
            if len(conn.subscriptions) >= max_subs and sub_key not in conn.subscriptions:
                return False
            
            conn.subscriptions[sub_key] = subscription
            
            # Update indexes
            if subscription.type == SubscriptionType.ALL:
                self._all_subscribers.add(conn_id)
            elif subscription.type == SubscriptionType.ENTITY:
                if subscription.target not in self._entity_subscribers:
                    self._entity_subscribers[subscription.target] = set()
                self._entity_subscribers[subscription.target].add(conn_id)
            elif subscription.type == SubscriptionType.CATEGORY:
                if subscription.target not in self._category_subscribers:
                    self._category_subscribers[subscription.target] = set()
                self._category_subscribers[subscription.target].add(conn_id)
            elif subscription.type == SubscriptionType.DIVERGENCE:
                self._divergence_subscribers.add(conn_id)
            elif subscription.type == SubscriptionType.SIGNAL_UPDATE:
                self._signal_update_subscribers.add(conn_id)
            elif subscription.type == SubscriptionType.EVENT:
                self._event_subscribers.add(conn_id)
            elif subscription.type == SubscriptionType.PROFILE:
                self._profile_subscribers.add(conn_id)
            elif subscription.type == SubscriptionType.ALERT:
                self._alert_subscribers.add(conn_id)
        
        return True
    
    async def unsubscribe(
        self, 
        conn_id: str, 
        subscription: Subscription
    ) -> bool:
        """Remove a subscription for a client."""
        async with self._lock:
            if conn_id not in self._connections:
                return False
            
            conn = self._connections[conn_id]
            sub_key = conn.subscription_key(subscription)
            
            if sub_key not in conn.subscriptions:
                return True
            
            del conn.subscriptions[sub_key]
            
            # Update indexes
            if subscription.type == SubscriptionType.ALL:
                self._all_subscribers.discard(conn_id)
            elif subscription.type == SubscriptionType.ENTITY:
                if subscription.target in self._entity_subscribers:
                    self._entity_subscribers[subscription.target].discard(conn_id)
            elif subscription.type == SubscriptionType.CATEGORY:
                if subscription.target in self._category_subscribers:
                    self._category_subscribers[subscription.target].discard(conn_id)
            elif subscription.type == SubscriptionType.DIVERGENCE:
                self._divergence_subscribers.discard(conn_id)
            elif subscription.type == SubscriptionType.SIGNAL_UPDATE:
                self._signal_update_subscribers.discard(conn_id)
            elif subscription.type == SubscriptionType.EVENT:
                self._event_subscribers.discard(conn_id)
            elif subscription.type == SubscriptionType.PROFILE:
                self._profile_subscribers.discard(conn_id)
            elif subscription.type == SubscriptionType.ALERT:
                self._alert_subscribers.discard(conn_id)
        
        return True
    
    async def configure(self, conn_id: str, config: Dict[str, Any]) -> bool:
        """Update client configuration."""
        async with self._lock:
            if conn_id not in self._connections:
                return False
            
            conn = self._connections[conn_id]
            
            # Only premium+ can enable batching
            if config.get("batch_enabled") and conn.tier == "free":
                return False
            
            if "batch_enabled" in config:
                conn.config.batch_enabled = config["batch_enabled"]
            if "batch_size" in config:
                conn.config.batch_size = min(config["batch_size"], 100)
            if "batch_interval_ms" in config:
                conn.config.batch_interval_ms = max(config["batch_interval_ms"], 100)
            if "include_metadata" in config:
                conn.config.include_metadata = config["include_metadata"]
        
        return True
    
    async def send_personal(self, websocket: WebSocket, message: Dict[str, Any]):
        """Send a message to a specific client."""
        try:
            data = json.dumps(message, default=str)
            await websocket.send_text(data)
            self._messages_sent_total += 1
            self._messages_timestamps.append(time.time())
        except Exception as e:
            logger.error(f"Error sending message: {e}")
    
    async def broadcast_signal_update(
        self,
        entity_id: str,
        category: str,
        data: Dict[str, Any],
    ):
        """Broadcast a signal update to relevant subscribers."""
        message = {
            "type": MessageType.SIGNAL_UPDATE.value,
            "entity_id": entity_id,
            "category": category,
            "data": data,
            "timestamp": datetime.utcnow().isoformat(),
        }
        
        conn_ids = await self._get_subscribers_for_signal(entity_id, category)
        await self._broadcast_to_connections(conn_ids, message)
    
    async def broadcast_divergence_alert(
        self,
        entity_id: str,
        entity_name: str,
        divergence_data: Dict[str, Any],
        severity: AlertSeverity = AlertSeverity.MEDIUM,
    ):
        """Broadcast a divergence alert."""
        message = {
            "type": MessageType.DIVERGENCE_ALERT.value,
            "entity_id": entity_id,
            "entity_name": entity_name,
            "severity": severity.value,
            "data": divergence_data,
            "timestamp": datetime.utcnow().isoformat(),
        }
        
        conn_ids = await self._get_subscribers_for_alert(entity_id, severity)
        await self._broadcast_to_connections(conn_ids, message)
    
    async def broadcast_event(
        self,
        event_type: str,
        entity_id: Optional[str],
        data: Dict[str, Any],
    ):
        """Broadcast an event notification."""
        message = {
            "type": MessageType.EVENT.value,
            "event_type": event_type,
            "entity_id": entity_id,
            "data": data,
            "timestamp": datetime.utcnow().isoformat(),
        }
        
        conn_ids = set()
        async with self._lock:
            conn_ids.update(self._all_subscribers)
            conn_ids.update(self._event_subscribers)
            if entity_id and entity_id in self._entity_subscribers:
                conn_ids.update(self._entity_subscribers[entity_id])
        
        await self._broadcast_to_connections(conn_ids, message)
    
    async def broadcast_profile_update(
        self,
        entity_id: str,
        entity_name: str,
        profile_data: Dict[str, Any],
    ):
        """Broadcast a profile update."""
        message = {
            "type": MessageType.PROFILE_UPDATE.value,
            "entity_id": entity_id,
            "entity_name": entity_name,
            "data": profile_data,
            "timestamp": datetime.utcnow().isoformat(),
        }
        
        conn_ids = set()
        async with self._lock:
            conn_ids.update(self._all_subscribers)
            conn_ids.update(self._profile_subscribers)
            if entity_id in self._entity_subscribers:
                conn_ids.update(self._entity_subscribers[entity_id])
        
        await self._broadcast_to_connections(conn_ids, message)
    
    async def _get_subscribers_for_signal(
        self, 
        entity_id: str, 
        category: str
    ) -> Set[str]:
        """Get all subscribers interested in a signal update."""
        conn_ids = set()
        
        async with self._lock:
            conn_ids.update(self._all_subscribers)
            conn_ids.update(self._signal_update_subscribers)
            
            if entity_id in self._entity_subscribers:
                conn_ids.update(self._entity_subscribers[entity_id])
            
            if category in self._category_subscribers:
                conn_ids.update(self._category_subscribers[category])
        
        return conn_ids
    
    async def _get_subscribers_for_alert(
        self, 
        entity_id: str,
        severity: AlertSeverity
    ) -> Set[str]:
        """Get all subscribers interested in an alert."""
        conn_ids = set()
        
        async with self._lock:
            conn_ids.update(self._all_subscribers)
            conn_ids.update(self._divergence_subscribers)
            conn_ids.update(self._alert_subscribers)
            
            if entity_id in self._entity_subscribers:
                conn_ids.update(self._entity_subscribers[entity_id])
            
            # Filter by severity
            filtered = set()
            for conn_id in conn_ids:
                if conn_id in self._connections:
                    conn = self._connections[conn_id]
                    for sub in conn.subscriptions.values():
                        if sub.min_severity:
                            severity_order = [AlertSeverity.LOW, AlertSeverity.MEDIUM, 
                                            AlertSeverity.HIGH, AlertSeverity.CRITICAL]
                            if severity_order.index(severity) >= severity_order.index(sub.min_severity):
                                filtered.add(conn_id)
                                break
                        else:
                            filtered.add(conn_id)
                            break
            
            conn_ids = filtered
        
        return conn_ids
    
    async def _broadcast_to_connections(
        self,
        conn_ids: Set[str],
        message: Dict[str, Any],
    ):
        """Broadcast message to a set of connections."""
        async with self._lock:
            connections = [
                self._connections[cid]
                for cid in conn_ids
                if cid in self._connections
            ]
        
        for conn in connections:
            try:
                # Handle batching
                if conn.config.batch_enabled:
                    conn.pending_messages.append(message)
                    if len(conn.pending_messages) >= conn.config.batch_size:
                        batch_msg = {
                            "type": MessageType.BATCH.value,
                            "messages": conn.pending_messages,
                            "count": len(conn.pending_messages),
                            "timestamp": datetime.utcnow().isoformat(),
                        }
                        await conn.websocket.send_json(batch_msg)
                        conn.messages_sent += len(conn.pending_messages)
                        conn.pending_messages = []
                else:
                    await conn.websocket.send_json(message)
                    conn.messages_sent += 1
                
                self._messages_sent_total += 1
                self._messages_timestamps.append(time.time())
            except Exception as e:
                logger.error(f"Error broadcasting to {conn.id}: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get connection statistics."""
        now = time.time()
        recent = [ts for ts in self._messages_timestamps if now - ts < 60]
        self._messages_timestamps = recent
        
        connections_by_tier = {}
        subscriptions_by_type = {}
        
        for conn in self._connections.values():
            connections_by_tier[conn.tier] = connections_by_tier.get(conn.tier, 0) + 1
            for sub in conn.subscriptions.values():
                subscriptions_by_type[sub.type.value] = subscriptions_by_type.get(sub.type.value, 0) + 1
        
        return {
            "total_connections": len(self._connections),
            "connections_by_tier": connections_by_tier,
            "total_subscriptions": sum(len(c.subscriptions) for c in self._connections.values()),
            "subscriptions_by_type": subscriptions_by_type,
            "messages_sent_total": self._messages_sent_total,
            "messages_per_minute": len(recent),
            "all_subscribers": len(self._all_subscribers),
            "entity_subscribers": sum(len(s) for s in self._entity_subscribers.values()),
            "category_subscribers": sum(len(s) for s in self._category_subscribers.values()),
            "divergence_subscribers": len(self._divergence_subscribers),
        }
    
    def get_connection_stats(self, conn_id: str) -> Optional[ConnectionStats]:
        """Get stats for a specific connection."""
        if conn_id not in self._connections:
            return None
        
        conn = self._connections[conn_id]
        now = datetime.utcnow()
        
        return ConnectionStats(
            connection_id=conn_id,
            tier=conn.tier,
            connected_at=conn.connected_at.isoformat(),
            uptime_seconds=(now - conn.connected_at).total_seconds(),
            messages_sent=conn.messages_sent,
            messages_received=conn.messages_received,
            bytes_sent=conn.bytes_sent,
            subscription_count=len(conn.subscriptions),
            last_ping_ago_seconds=(now - conn.last_ping).total_seconds(),
        )


# =============================================================================
# Global manager instance
# =============================================================================

manager = ConnectionManager()


# =============================================================================
# WebSocket Endpoint Handler
# =============================================================================

async def websocket_endpoint(
    websocket: WebSocket,
    api_key: Optional[str] = Query(None),
    reconnect_id: Optional[str] = Query(None),
):
    """
    Main WebSocket endpoint handler.
    
    ## Connection
    
    ```
    ws://localhost:8000/ws?api_key=your_key
    ```
    
    For reconnection, include the connection_id from previous session:
    ```
    ws://localhost:8000/ws?api_key=your_key&reconnect_id=abc123
    ```
    
    ## Protocol
    
    ### Client -> Server Messages
    
    **Subscribe to entity:**
    ```json
    {
        "type": "subscribe",
        "subscription_type": "entity",
        "target": "openai",
        "filters": {"min_score": 50}
    }
    ```
    
    **Subscribe to divergence alerts:**
    ```json
    {
        "type": "subscribe",
        "subscription_type": "divergence",
        "min_severity": "high"
    }
    ```
    
    **Subscribe to all updates:**
    ```json
    {"type": "subscribe", "subscription_type": "all"}
    ```
    
    **Unsubscribe:**
    ```json
    {"type": "unsubscribe", "subscription_type": "entity", "target": "openai"}
    ```
    
    **Ping (keepalive):**
    ```json
    {"type": "ping"}
    ```
    
    **Configure (premium):**
    ```json
    {
        "type": "configure",
        "batch_enabled": true,
        "batch_size": 10
    }
    ```
    
    ### Server -> Client Messages
    
    **Signal update:**
    ```json
    {
        "type": "signal_update",
        "entity_id": "openai",
        "category": "technical",
        "data": {...},
        "timestamp": "2025-01-01T12:00:00Z"
    }
    ```
    
    **Divergence alert:**
    ```json
    {
        "type": "divergence_alert",
        "entity_id": "openai",
        "entity_name": "OpenAI",
        "severity": "high",
        "data": {...},
        "timestamp": "2025-01-01T12:00:00Z"
    }
    ```
    
    **Heartbeat (server sends every 30s):**
    ```json
    {
        "type": "heartbeat",
        "timestamp": "2025-01-01T12:00:00Z",
        "server_time": 1704067200000
    }
    ```
    
    ## Subscription Types
    
    - `all`: Receive all updates
    - `entity`: Updates for specific entity
    - `category`: Updates for signal category (technical, financial, etc.)
    - `divergence`: Divergence alerts only
    - `signal_update`: Signal score updates
    - `event`: Event notifications
    - `profile`: Profile updates
    - `alert`: All alert types
    """
    conn = await manager.connect(websocket, api_key, reconnect_id)
    
    # Check if tier allows websocket
    tier_config = TIERS.get(conn.tier, TIERS["free"])
    if not tier_config.websocket_enabled:
        await manager.send_personal(websocket, {
            "type": MessageType.ERROR.value,
            "code": "TIER_NOT_ALLOWED",
            "error": "WebSocket access not available for your tier.",
        })
        await websocket.close()
        return
    
    try:
        while True:
            data = await websocket.receive_json()
            conn.messages_received += 1
            
            msg_type = data.get("type", "").lower()
            
            if msg_type == MessageType.PING.value:
                conn.last_ping = datetime.utcnow()
                conn.last_pong = datetime.utcnow()
                await manager.send_personal(websocket, {
                    "type": MessageType.PONG.value,
                    "timestamp": datetime.utcnow().isoformat(),
                    "server_time": int(time.time() * 1000),
                })
            
            elif msg_type == MessageType.SUBSCRIBE.value:
                sub_type_str = data.get("subscription_type", "all")
                target = data.get("target")
                filters = data.get("filters", {})
                min_severity_str = data.get("min_severity")
                
                try:
                    sub_type = SubscriptionType(sub_type_str)
                except ValueError:
                    await manager.send_personal(websocket, {
                        "type": MessageType.ERROR.value,
                        "code": "INVALID_SUBSCRIPTION",
                        "error": f"Invalid subscription type: {sub_type_str}",
                        "valid_types": [st.value for st in SubscriptionType],
                    })
                    continue
                
                min_severity = None
                if min_severity_str:
                    try:
                        min_severity = AlertSeverity(min_severity_str)
                    except ValueError:
                        pass
                
                subscription = Subscription(
                    type=sub_type,
                    target=target,
                    min_score=filters.get("min_score"),
                    min_severity=min_severity,
                    filters=filters,
                )
                
                success = await manager.subscribe(conn.id, subscription)
                
                if success:
                    await manager.send_personal(websocket, {
                        "type": MessageType.SUBSCRIBED.value,
                        "subscription_type": sub_type_str,
                        "target": target,
                        "subscription_count": len(conn.subscriptions),
                    })
                else:
                    await manager.send_personal(websocket, {
                        "type": MessageType.ERROR.value,
                        "code": "SUBSCRIPTION_LIMIT",
                        "error": "Subscription limit reached for your tier.",
                    })
            
            elif msg_type == MessageType.UNSUBSCRIBE.value:
                sub_type_str = data.get("subscription_type", "all")
                target = data.get("target")
                
                try:
                    sub_type = SubscriptionType(sub_type_str)
                except ValueError:
                    continue
                
                subscription = Subscription(type=sub_type, target=target)
                await manager.unsubscribe(conn.id, subscription)
                
                await manager.send_personal(websocket, {
                    "type": MessageType.UNSUBSCRIBED.value,
                    "subscription_type": sub_type_str,
                    "target": target,
                    "subscription_count": len(conn.subscriptions),
                })
            
            elif msg_type == MessageType.CONFIGURE.value:
                config = {k: v for k, v in data.items() if k != "type"}
                success = await manager.configure(conn.id, config)
                
                await manager.send_personal(websocket, {
                    "type": MessageType.CONFIG_ACK.value,
                    "success": success,
                    "config": {
                        "batch_enabled": conn.config.batch_enabled,
                        "batch_size": conn.config.batch_size,
                        "batch_interval_ms": conn.config.batch_interval_ms,
                    },
                })
            
            else:
                await manager.send_personal(websocket, {
                    "type": MessageType.ERROR.value,
                    "code": "UNKNOWN_MESSAGE",
                    "error": f"Unknown message type: {msg_type}",
                })
    
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error for {conn.id}: {e}")
        await manager.disconnect(websocket)


# =============================================================================
# Helper Functions for Broadcasting
# =============================================================================

async def notify_signal_update(entity_id: str, category: str, data: Dict[str, Any]):
    """Notify subscribers of a signal update."""
    await manager.broadcast_signal_update(entity_id, category, data)


async def notify_divergence(
    entity_id: str, 
    entity_name: str, 
    divergence: Dict[str, Any],
    severity: str = "medium"
):
    """Notify subscribers of a new divergence."""
    try:
        sev = AlertSeverity(severity)
    except ValueError:
        sev = AlertSeverity.MEDIUM
    
    await manager.broadcast_divergence_alert(entity_id, entity_name, divergence, sev)


async def notify_event(event_type: str, entity_id: Optional[str], data: Dict[str, Any]):
    """Notify subscribers of an event."""
    await manager.broadcast_event(event_type, entity_id, data)


async def notify_profile_update(entity_id: str, entity_name: str, profile_data: Dict[str, Any]):
    """Notify subscribers of a profile update."""
    await manager.broadcast_profile_update(entity_id, entity_name, profile_data)
