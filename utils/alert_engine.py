"""
Alert Engine

Comprehensive alert system for briefAI that detects and manages alerts
across multiple signal dimensions.

Alert Types:
- threshold: When entity scores cross user-defined thresholds
- divergence: When technical vs fundamental signals diverge
- momentum: When 7d/30d momentum exceeds thresholds
- event: New funding, product launch, partnership detected
- anomaly: Unusual signal patterns (z-score based)
"""

import sqlite3
import json
import uuid
import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable, Tuple
from enum import Enum
from loguru import logger


class AlertType(str, Enum):
    """Types of alerts the system can generate."""
    THRESHOLD = "threshold"       # Score crosses threshold
    DIVERGENCE = "divergence"     # Signal types disagree
    MOMENTUM = "momentum"         # Significant momentum change
    EVENT = "event"               # Business event detected
    ANOMALY = "anomaly"          # Statistical anomaly
    PRICE_FUNDAMENTAL = "price_fundamental"  # Price vs news divergence
    # v2: Intelligence-focused alert types
    TREND_EMERGENCE = "trend_emergence"        # New cross-source pattern detected
    NARRATIVE_INFLECTION = "narrative_inflection"  # Narrative momentum changed direction
    PREDICTION_TRIGGER = "prediction_trigger"  # Prediction confidence crossed threshold
    SOURCE_DIVERGENCE = "source_divergence"    # Sources disagree (news positive, Reddit negative)
    STEALTH_SIGNAL = "stealth_signal"          # Non-news signals without news coverage


class AlertSeverity(str, Enum):
    """Alert severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertCategory(str, Enum):
    """What kind of signal this alert represents."""
    OPPORTUNITY = "opportunity"
    RISK = "risk"
    WATCH = "watch"
    INFORMATIONAL = "informational"


@dataclass
class Alert:
    """
    Core alert data structure.
    
    Captures all information needed to display, route, and track alerts.
    """
    id: str
    alert_type: AlertType
    entity_id: str
    entity_name: str
    severity: AlertSeverity
    title: str
    message: str
    data: Dict[str, Any]
    created_at: datetime
    acknowledged: bool = False
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    
    # Additional metadata
    category: AlertCategory = AlertCategory.INFORMATIONAL
    rule_id: Optional[str] = None  # Which rule triggered this
    source_signals: List[str] = field(default_factory=list)
    
    # Expiration
    expires_at: Optional[datetime] = None
    expired: bool = False
    
    # Notification tracking
    notification_sent: Dict[str, datetime] = field(default_factory=dict)
    
    # Deduplication
    content_hash: str = ""
    
    def __post_init__(self):
        """Compute content hash for deduplication."""
        if not self.content_hash:
            hash_content = f"{self.alert_type}:{self.entity_id}:{self.title}:{json.dumps(self.data, sort_keys=True)}"
            self.content_hash = hashlib.md5(hash_content.encode()).hexdigest()[:12]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage/serialization."""
        return {
            "id": self.id,
            "alert_type": self.alert_type.value if isinstance(self.alert_type, AlertType) else self.alert_type,
            "entity_id": self.entity_id,
            "entity_name": self.entity_name,
            "severity": self.severity.value if isinstance(self.severity, AlertSeverity) else self.severity,
            "title": self.title,
            "message": self.message,
            "data": self.data,
            "created_at": self.created_at.isoformat() if isinstance(self.created_at, datetime) else self.created_at,
            "acknowledged": self.acknowledged,
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            "acknowledged_by": self.acknowledged_by,
            "category": self.category.value if isinstance(self.category, AlertCategory) else self.category,
            "rule_id": self.rule_id,
            "source_signals": self.source_signals,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "expired": self.expired,
            "notification_sent": {k: v.isoformat() for k, v in self.notification_sent.items()},
            "content_hash": self.content_hash,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Alert":
        """Create Alert from dictionary."""
        # Convert enum strings back to enums
        alert_type = AlertType(data["alert_type"]) if isinstance(data["alert_type"], str) else data["alert_type"]
        severity = AlertSeverity(data["severity"]) if isinstance(data["severity"], str) else data["severity"]
        category = AlertCategory(data.get("category", "informational")) if isinstance(data.get("category"), str) else data.get("category", AlertCategory.INFORMATIONAL)
        
        # Parse datetimes
        created_at = datetime.fromisoformat(data["created_at"]) if isinstance(data["created_at"], str) else data["created_at"]
        acknowledged_at = datetime.fromisoformat(data["acknowledged_at"]) if data.get("acknowledged_at") else None
        expires_at = datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else None
        
        # Parse notification_sent
        notification_sent = {}
        for k, v in data.get("notification_sent", {}).items():
            notification_sent[k] = datetime.fromisoformat(v) if isinstance(v, str) else v
        
        return cls(
            id=data["id"],
            alert_type=alert_type,
            entity_id=data["entity_id"],
            entity_name=data["entity_name"],
            severity=severity,
            title=data["title"],
            message=data["message"],
            data=data.get("data", {}),
            created_at=created_at,
            acknowledged=data.get("acknowledged", False),
            acknowledged_at=acknowledged_at,
            acknowledged_by=data.get("acknowledged_by"),
            category=category,
            rule_id=data.get("rule_id"),
            source_signals=data.get("source_signals", []),
            expires_at=expires_at,
            expired=data.get("expired", False),
            notification_sent=notification_sent,
            content_hash=data.get("content_hash", ""),
        )


class AlertEngine:
    """
    Central engine for generating and managing alerts.
    
    Responsibilities:
    - Evaluate signal data against rules
    - Generate alerts when conditions are met
    - Store alerts in SQLite
    - Handle deduplication and cooldowns
    - Track notification delivery
    """
    
    # Cooldown periods by severity (hours)
    COOLDOWN_HOURS = {
        AlertSeverity.LOW: 24,
        AlertSeverity.MEDIUM: 48,
        AlertSeverity.HIGH: 72,
        AlertSeverity.CRITICAL: 168,  # 1 week
    }
    
    def __init__(self, db_path: Optional[Path] = None):
        """
        Initialize alert engine.
        
        Args:
            db_path: Path to alerts database. Defaults to data/entity_alerts.db
        """
        # Use entity_alerts.db to avoid conflict with existing bucket alerts
        self.db_path = db_path or Path("data/entity_alerts.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        logger.info(f"AlertEngine initialized with db: {self.db_path}")
    
    def _init_db(self) -> None:
        """Initialize SQLite database tables."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        # Main alerts table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id TEXT PRIMARY KEY,
                alert_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                entity_name TEXT NOT NULL,
                severity TEXT NOT NULL,
                category TEXT DEFAULT 'informational',
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                data TEXT,
                rule_id TEXT,
                source_signals TEXT,
                content_hash TEXT,
                
                created_at TEXT NOT NULL,
                expires_at TEXT,
                expired INTEGER DEFAULT 0,
                
                acknowledged INTEGER DEFAULT 0,
                acknowledged_at TEXT,
                acknowledged_by TEXT,
                
                notification_sent TEXT
            )
        """)
        
        # Indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_alerts_entity ON alerts(entity_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_alerts_type ON alerts(alert_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_alerts_severity ON alerts(severity)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_alerts_created ON alerts(created_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_alerts_hash ON alerts(content_hash)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_alerts_acknowledged ON alerts(acknowledged)")
        
        # Cooldown tracking table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS alert_cooldowns (
                entity_id TEXT NOT NULL,
                alert_type TEXT NOT NULL,
                rule_id TEXT,
                last_alert_at TEXT NOT NULL,
                cooldown_expires TEXT NOT NULL,
                PRIMARY KEY (entity_id, alert_type, rule_id)
            )
        """)
        
        # Alert history/audit log
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS alert_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_id TEXT NOT NULL,
                action TEXT NOT NULL,
                action_data TEXT,
                occurred_at TEXT NOT NULL
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_alert ON alert_history(alert_id)")
        
        conn.commit()
        conn.close()
    
    def create_alert(
        self,
        alert_type: AlertType,
        entity_id: str,
        entity_name: str,
        severity: AlertSeverity,
        title: str,
        message: str,
        data: Dict[str, Any],
        category: AlertCategory = AlertCategory.INFORMATIONAL,
        rule_id: Optional[str] = None,
        source_signals: Optional[List[str]] = None,
        expires_hours: Optional[int] = None,
        skip_cooldown: bool = False,
        skip_dedup: bool = False,
    ) -> Optional[Alert]:
        """
        Create a new alert if conditions allow.
        
        Args:
            alert_type: Type of alert
            entity_id: Entity identifier
            entity_name: Display name
            severity: Alert severity
            title: Alert title
            message: Detailed message
            data: Associated data
            category: Alert category
            rule_id: ID of rule that triggered this
            source_signals: List of signal IDs that contributed
            expires_hours: Hours until alert expires (None = never)
            skip_cooldown: Skip cooldown check
            skip_dedup: Skip deduplication check
        
        Returns:
            Alert if created, None if blocked by cooldown/dedup
        """
        # Check cooldown
        if not skip_cooldown:
            if self._is_in_cooldown(entity_id, alert_type, rule_id):
                logger.debug(f"Alert blocked by cooldown: {entity_id}/{alert_type}")
                return None
        
        # Create alert object
        alert = Alert(
            id=str(uuid.uuid4())[:12],
            alert_type=alert_type,
            entity_id=entity_id,
            entity_name=entity_name,
            severity=severity,
            title=title,
            message=message,
            data=data,
            created_at=datetime.now(),
            category=category,
            rule_id=rule_id,
            source_signals=source_signals or [],
            expires_at=datetime.now() + timedelta(hours=expires_hours) if expires_hours else None,
        )
        
        # Check deduplication
        if not skip_dedup:
            if self._is_duplicate(alert):
                logger.debug(f"Alert blocked by dedup: {alert.content_hash}")
                return None
        
        # Save to database
        self._save_alert(alert)
        
        # Set cooldown
        self._set_cooldown(entity_id, alert_type, rule_id, severity)
        
        # Log to history
        self._log_history(alert.id, "created", {
            "severity": severity.value,
            "rule_id": rule_id,
        })
        
        logger.info(f"Alert created: [{severity.value}] {title} for {entity_name}")
        
        return alert
    
    def _save_alert(self, alert: Alert) -> None:
        """Save alert to database."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO alerts (
                id, alert_type, entity_id, entity_name, severity, category,
                title, message, data, rule_id, source_signals, content_hash,
                created_at, expires_at, expired, acknowledged, acknowledged_at,
                acknowledged_by, notification_sent
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            alert.id,
            alert.alert_type.value,
            alert.entity_id,
            alert.entity_name,
            alert.severity.value,
            alert.category.value,
            alert.title,
            alert.message,
            json.dumps(alert.data),
            alert.rule_id,
            json.dumps(alert.source_signals),
            alert.content_hash,
            alert.created_at.isoformat(),
            alert.expires_at.isoformat() if alert.expires_at else None,
            1 if alert.expired else 0,
            1 if alert.acknowledged else 0,
            alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
            alert.acknowledged_by,
            json.dumps({k: v.isoformat() for k, v in alert.notification_sent.items()}),
        ))
        
        conn.commit()
        conn.close()
    
    def _is_in_cooldown(
        self, 
        entity_id: str, 
        alert_type: AlertType, 
        rule_id: Optional[str]
    ) -> bool:
        """Check if alert is in cooldown period."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT cooldown_expires FROM alert_cooldowns
            WHERE entity_id = ? AND alert_type = ? AND (rule_id = ? OR rule_id IS NULL)
        """, (entity_id, alert_type.value, rule_id))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return False
        
        cooldown_expires = datetime.fromisoformat(row[0])
        return datetime.now() < cooldown_expires
    
    def _set_cooldown(
        self, 
        entity_id: str, 
        alert_type: AlertType, 
        rule_id: Optional[str],
        severity: AlertSeverity
    ) -> None:
        """Set cooldown for entity/type/rule combination."""
        cooldown_hours = self.COOLDOWN_HOURS.get(severity, 24)
        expires = datetime.now() + timedelta(hours=cooldown_hours)
        
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO alert_cooldowns (
                entity_id, alert_type, rule_id, last_alert_at, cooldown_expires
            ) VALUES (?, ?, ?, ?, ?)
        """, (
            entity_id,
            alert_type.value,
            rule_id,
            datetime.now().isoformat(),
            expires.isoformat(),
        ))
        
        conn.commit()
        conn.close()
    
    def _is_duplicate(self, alert: Alert) -> bool:
        """Check if similar alert exists within dedup window (24h)."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
        
        cursor.execute("""
            SELECT id FROM alerts
            WHERE content_hash = ? AND created_at > ?
        """, (alert.content_hash, cutoff))
        
        row = cursor.fetchone()
        conn.close()
        
        return row is not None
    
    def _log_history(self, alert_id: str, action: str, data: Dict) -> None:
        """Log action to history."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO alert_history (alert_id, action, action_data, occurred_at)
            VALUES (?, ?, ?, ?)
        """, (alert_id, action, json.dumps(data), datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
    
    # =========================================================================
    # Alert Retrieval
    # =========================================================================
    
    def get_alert(self, alert_id: str) -> Optional[Alert]:
        """Get alert by ID."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM alerts WHERE id = ?", (alert_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return self._row_to_alert(row)
        return None
    
    def get_active_alerts(
        self,
        entity_id: Optional[str] = None,
        alert_type: Optional[AlertType] = None,
        severity: Optional[AlertSeverity] = None,
        category: Optional[AlertCategory] = None,
        limit: int = 100,
    ) -> List[Alert]:
        """
        Get active (unacknowledged, unexpired) alerts.
        
        Args:
            entity_id: Filter by entity
            alert_type: Filter by type
            severity: Filter by severity
            category: Filter by category
            limit: Max results
        
        Returns:
            List of alerts sorted by severity then created_at
        """
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        query = "SELECT * FROM alerts WHERE acknowledged = 0 AND expired = 0"
        params = []
        
        if entity_id:
            query += " AND entity_id = ?"
            params.append(entity_id)
        
        if alert_type:
            query += " AND alert_type = ?"
            params.append(alert_type.value)
        
        if severity:
            query += " AND severity = ?"
            params.append(severity.value)
        
        if category:
            query += " AND category = ?"
            params.append(category.value)
        
        # Order by severity (critical first) then created_at
        query += """
            ORDER BY
                CASE severity
                    WHEN 'critical' THEN 0
                    WHEN 'high' THEN 1
                    WHEN 'medium' THEN 2
                    ELSE 3
                END,
                created_at DESC
            LIMIT ?
        """
        params.append(limit)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        return [self._row_to_alert(row) for row in rows]
    
    def get_alerts_for_entity(
        self, 
        entity_id: str, 
        include_acknowledged: bool = False,
        days: int = 30,
    ) -> List[Alert]:
        """Get all alerts for an entity within time window."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        
        query = "SELECT * FROM alerts WHERE entity_id = ? AND created_at > ?"
        params = [entity_id, cutoff]
        
        if not include_acknowledged:
            query += " AND acknowledged = 0"
        
        query += " ORDER BY created_at DESC"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        return [self._row_to_alert(row) for row in rows]
    
    def get_recent_alerts(self, hours: int = 24, limit: int = 50) -> List[Alert]:
        """Get alerts from the last N hours."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        
        cursor.execute("""
            SELECT * FROM alerts
            WHERE created_at > ?
            ORDER BY created_at DESC
            LIMIT ?
        """, (cutoff, limit))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [self._row_to_alert(row) for row in rows]
    
    def _row_to_alert(self, row: sqlite3.Row) -> Alert:
        """Convert database row to Alert object."""
        notification_sent = {}
        if row["notification_sent"]:
            raw = json.loads(row["notification_sent"])
            for k, v in raw.items():
                notification_sent[k] = datetime.fromisoformat(v) if isinstance(v, str) else v
        
        return Alert(
            id=row["id"],
            alert_type=AlertType(row["alert_type"]),
            entity_id=row["entity_id"],
            entity_name=row["entity_name"],
            severity=AlertSeverity(row["severity"]),
            title=row["title"],
            message=row["message"],
            data=json.loads(row["data"]) if row["data"] else {},
            created_at=datetime.fromisoformat(row["created_at"]),
            acknowledged=bool(row["acknowledged"]),
            acknowledged_at=datetime.fromisoformat(row["acknowledged_at"]) if row["acknowledged_at"] else None,
            acknowledged_by=row["acknowledged_by"],
            category=AlertCategory(row["category"]) if row["category"] else AlertCategory.INFORMATIONAL,
            rule_id=row["rule_id"],
            source_signals=json.loads(row["source_signals"]) if row["source_signals"] else [],
            expires_at=datetime.fromisoformat(row["expires_at"]) if row["expires_at"] else None,
            expired=bool(row["expired"]),
            notification_sent=notification_sent,
            content_hash=row["content_hash"] or "",
        )
    
    # =========================================================================
    # Alert Actions
    # =========================================================================
    
    def acknowledge_alert(self, alert_id: str, by: str = "user") -> bool:
        """Mark alert as acknowledged."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        
        cursor.execute("""
            UPDATE alerts SET
                acknowledged = 1,
                acknowledged_at = ?,
                acknowledged_by = ?
            WHERE id = ?
        """, (now, by, alert_id))
        
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        
        if affected:
            self._log_history(alert_id, "acknowledged", {"by": by})
            logger.info(f"Alert {alert_id} acknowledged by {by}")
        
        return affected > 0
    
    def acknowledge_all(
        self, 
        entity_id: Optional[str] = None,
        alert_type: Optional[AlertType] = None,
        by: str = "user"
    ) -> int:
        """Acknowledge multiple alerts."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        query = "UPDATE alerts SET acknowledged = 1, acknowledged_at = ?, acknowledged_by = ? WHERE acknowledged = 0"
        params = [now, by]
        
        if entity_id:
            query += " AND entity_id = ?"
            params.append(entity_id)
        
        if alert_type:
            query += " AND alert_type = ?"
            params.append(alert_type.value)
        
        cursor.execute(query, params)
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        
        logger.info(f"Acknowledged {affected} alerts")
        return affected
    
    def mark_notification_sent(
        self, 
        alert_id: str, 
        channel: str
    ) -> None:
        """Record that notification was sent via a channel."""
        alert = self.get_alert(alert_id)
        if not alert:
            return
        
        alert.notification_sent[channel] = datetime.now()
        
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE alerts SET notification_sent = ? WHERE id = ?
        """, (
            json.dumps({k: v.isoformat() for k, v in alert.notification_sent.items()}),
            alert_id
        ))
        
        conn.commit()
        conn.close()
        
        self._log_history(alert_id, "notification_sent", {"channel": channel})
    
    def expire_old_alerts(self) -> int:
        """Mark expired alerts as expired."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        
        cursor.execute("""
            UPDATE alerts SET expired = 1
            WHERE expired = 0 AND expires_at IS NOT NULL AND expires_at < ?
        """, (now,))
        
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        
        if affected:
            logger.info(f"Expired {affected} old alerts")
        
        return affected
    
    def clear_cooldown(
        self, 
        entity_id: str, 
        alert_type: Optional[AlertType] = None
    ) -> int:
        """Clear cooldowns for an entity."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        if alert_type:
            cursor.execute("""
                DELETE FROM alert_cooldowns
                WHERE entity_id = ? AND alert_type = ?
            """, (entity_id, alert_type.value))
        else:
            cursor.execute("""
                DELETE FROM alert_cooldowns WHERE entity_id = ?
            """, (entity_id,))
        
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        
        return affected
    
    # =========================================================================
    # Statistics
    # =========================================================================
    
    def get_stats(self) -> Dict[str, Any]:
        """Get alert statistics."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        stats = {}
        
        # Total counts
        cursor.execute("SELECT COUNT(*) FROM alerts")
        stats["total_alerts"] = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM alerts WHERE acknowledged = 0 AND expired = 0")
        stats["active_alerts"] = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM alerts WHERE acknowledged = 1")
        stats["acknowledged_alerts"] = cursor.fetchone()[0]
        
        # By severity
        cursor.execute("""
            SELECT severity, COUNT(*) FROM alerts
            WHERE acknowledged = 0 AND expired = 0
            GROUP BY severity
        """)
        stats["by_severity"] = {row[0]: row[1] for row in cursor.fetchall()}
        
        # By type
        cursor.execute("""
            SELECT alert_type, COUNT(*) FROM alerts
            WHERE acknowledged = 0 AND expired = 0
            GROUP BY alert_type
        """)
        stats["by_type"] = {row[0]: row[1] for row in cursor.fetchall()}
        
        # By category
        cursor.execute("""
            SELECT category, COUNT(*) FROM alerts
            WHERE acknowledged = 0 AND expired = 0
            GROUP BY category
        """)
        stats["by_category"] = {row[0]: row[1] for row in cursor.fetchall()}
        
        # Recent (24h)
        cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
        cursor.execute("SELECT COUNT(*) FROM alerts WHERE created_at > ?", (cutoff,))
        stats["alerts_24h"] = cursor.fetchone()[0]
        
        # Top entities
        cursor.execute("""
            SELECT entity_name, COUNT(*) as cnt FROM alerts
            WHERE acknowledged = 0 AND expired = 0
            GROUP BY entity_id
            ORDER BY cnt DESC
            LIMIT 10
        """)
        stats["top_entities"] = [{"entity": row[0], "count": row[1]} for row in cursor.fetchall()]
        
        conn.close()
        return stats
    
    def get_alert_history(self, alert_id: str) -> List[Dict[str, Any]]:
        """Get history for an alert."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM alert_history
            WHERE alert_id = ?
            ORDER BY occurred_at DESC
        """, (alert_id,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [
            {
                "action": row["action"],
                "data": json.loads(row["action_data"]) if row["action_data"] else {},
                "occurred_at": row["occurred_at"],
            }
            for row in rows
        ]


# =============================================================================
# Alert Generator Functions
# =============================================================================

def generate_threshold_alert(
    engine: AlertEngine,
    entity_id: str,
    entity_name: str,
    signal_name: str,
    signal_value: float,
    threshold: float,
    operator: str,  # >, <, >=, <=
    rule_id: Optional[str] = None,
) -> Optional[Alert]:
    """Generate alert when signal crosses threshold."""
    # Determine severity based on how far over threshold
    diff = abs(signal_value - threshold)
    if diff > 30:
        severity = AlertSeverity.CRITICAL
    elif diff > 20:
        severity = AlertSeverity.HIGH
    elif diff > 10:
        severity = AlertSeverity.MEDIUM
    else:
        severity = AlertSeverity.LOW
    
    direction = "above" if operator in [">", ">="] else "below"
    
    title = f"{entity_name}: {signal_name} {direction} threshold"
    message = f"{signal_name} score is {signal_value:.1f}, which is {direction} the threshold of {threshold:.1f}"
    
    return engine.create_alert(
        alert_type=AlertType.THRESHOLD,
        entity_id=entity_id,
        entity_name=entity_name,
        severity=severity,
        title=title,
        message=message,
        data={
            "signal_name": signal_name,
            "signal_value": signal_value,
            "threshold": threshold,
            "operator": operator,
            "difference": signal_value - threshold,
        },
        category=AlertCategory.WATCH,
        rule_id=rule_id,
        source_signals=[signal_name],
    )


def generate_divergence_alert(
    engine: AlertEngine,
    entity_id: str,
    entity_name: str,
    high_signal: str,
    high_value: float,
    low_signal: str,
    low_value: float,
    interpretation: str,
    rule_id: Optional[str] = None,
) -> Optional[Alert]:
    """Generate alert for signal divergence."""
    magnitude = high_value - low_value
    
    if magnitude > 50:
        severity = AlertSeverity.CRITICAL
    elif magnitude > 35:
        severity = AlertSeverity.HIGH
    elif magnitude > 25:
        severity = AlertSeverity.MEDIUM
    else:
        severity = AlertSeverity.LOW
    
    # Determine category
    if "opportunity" in interpretation.lower():
        category = AlertCategory.OPPORTUNITY
    elif "risk" in interpretation.lower() or "caution" in interpretation.lower():
        category = AlertCategory.RISK
    else:
        category = AlertCategory.WATCH
    
    title = f"{entity_name}: Signal Divergence Detected"
    message = f"{high_signal} ({high_value:.1f}) diverges from {low_signal} ({low_value:.1f}). {interpretation}"
    
    return engine.create_alert(
        alert_type=AlertType.DIVERGENCE,
        entity_id=entity_id,
        entity_name=entity_name,
        severity=severity,
        title=title,
        message=message,
        data={
            "high_signal": high_signal,
            "high_value": high_value,
            "low_signal": low_signal,
            "low_value": low_value,
            "magnitude": magnitude,
            "interpretation": interpretation,
        },
        category=category,
        rule_id=rule_id,
        source_signals=[high_signal, low_signal],
    )


def generate_momentum_alert(
    engine: AlertEngine,
    entity_id: str,
    entity_name: str,
    momentum_7d: float,
    momentum_30d: Optional[float] = None,
    rule_id: Optional[str] = None,
) -> Optional[Alert]:
    """Generate alert for significant momentum change."""
    abs_momentum = abs(momentum_7d)
    
    if abs_momentum > 50:
        severity = AlertSeverity.CRITICAL
    elif abs_momentum > 30:
        severity = AlertSeverity.HIGH
    elif abs_momentum > 20:
        severity = AlertSeverity.MEDIUM
    else:
        severity = AlertSeverity.LOW
    
    direction = "surging" if momentum_7d > 0 else "declining"
    category = AlertCategory.OPPORTUNITY if momentum_7d > 0 else AlertCategory.RISK
    
    title = f"{entity_name}: Momentum {direction.title()}"
    message = f"7-day momentum is {momentum_7d:+.1f}%"
    if momentum_30d is not None:
        message += f" (30-day: {momentum_30d:+.1f}%)"
    
    return engine.create_alert(
        alert_type=AlertType.MOMENTUM,
        entity_id=entity_id,
        entity_name=entity_name,
        severity=severity,
        title=title,
        message=message,
        data={
            "momentum_7d": momentum_7d,
            "momentum_30d": momentum_30d,
            "direction": direction,
        },
        category=category,
        rule_id=rule_id,
    )


def generate_event_alert(
    engine: AlertEngine,
    entity_id: str,
    entity_name: str,
    event_type: str,
    event_title: str,
    event_details: Dict[str, Any],
    rule_id: Optional[str] = None,
) -> Optional[Alert]:
    """Generate alert for business event detection."""
    # Severity based on event type
    severity_map = {
        "funding_round": AlertSeverity.HIGH,
        "acquisition": AlertSeverity.CRITICAL,
        "product_launch": AlertSeverity.MEDIUM,
        "partnership": AlertSeverity.MEDIUM,
        "leadership_change": AlertSeverity.HIGH,
        "layoff": AlertSeverity.HIGH,
        "ipo": AlertSeverity.CRITICAL,
    }
    severity = severity_map.get(event_type.lower(), AlertSeverity.MEDIUM)
    
    title = f"{entity_name}: {event_type.replace('_', ' ').title()}"
    message = event_title
    
    # Add amount if funding
    if event_type == "funding_round" and event_details.get("amount_usd"):
        amount = event_details["amount_usd"]
        if amount >= 1e9:
            amount_str = f"${amount/1e9:.1f}B"
        elif amount >= 1e6:
            amount_str = f"${amount/1e6:.1f}M"
        else:
            amount_str = f"${amount:,.0f}"
        message += f" ({amount_str})"
    
    return engine.create_alert(
        alert_type=AlertType.EVENT,
        entity_id=entity_id,
        entity_name=entity_name,
        severity=severity,
        title=title,
        message=message,
        data={
            "event_type": event_type,
            "event_title": event_title,
            **event_details,
        },
        category=AlertCategory.INFORMATIONAL,
        rule_id=rule_id,
    )


def generate_anomaly_alert(
    engine: AlertEngine,
    entity_id: str,
    entity_name: str,
    signal_name: str,
    current_value: float,
    z_score: float,
    baseline_mean: float,
    baseline_std: float,
    rule_id: Optional[str] = None,
) -> Optional[Alert]:
    """Generate alert for statistical anomaly."""
    abs_z = abs(z_score)
    
    if abs_z > 3.0:
        severity = AlertSeverity.CRITICAL
    elif abs_z > 2.5:
        severity = AlertSeverity.HIGH
    elif abs_z > 2.0:
        severity = AlertSeverity.MEDIUM
    else:
        severity = AlertSeverity.LOW
    
    direction = "above" if z_score > 0 else "below"
    category = AlertCategory.OPPORTUNITY if z_score > 0 else AlertCategory.RISK
    
    title = f"{entity_name}: Anomalous {signal_name}"
    message = f"{signal_name} is {current_value:.1f} ({z_score:+.2f}σ {direction} baseline)"
    
    return engine.create_alert(
        alert_type=AlertType.ANOMALY,
        entity_id=entity_id,
        entity_name=entity_name,
        severity=severity,
        title=title,
        message=message,
        data={
            "signal_name": signal_name,
            "current_value": current_value,
            "z_score": z_score,
            "baseline_mean": baseline_mean,
            "baseline_std": baseline_std,
            "direction": direction,
        },
        category=category,
        rule_id=rule_id,
        source_signals=[signal_name],
    )


if __name__ == "__main__":
    # Quick test
    engine = AlertEngine(db_path=Path("data/alerts_test.db"))
    
    # Create test alert
    alert = engine.create_alert(
        alert_type=AlertType.THRESHOLD,
        entity_id="openai",
        entity_name="OpenAI",
        severity=AlertSeverity.HIGH,
        title="OpenAI: TMS above threshold",
        message="Technical Momentum Signal is 92, above threshold of 80",
        data={"signal": "tms", "value": 92, "threshold": 80},
        category=AlertCategory.OPPORTUNITY,
    )
    
    if alert:
        print(f"Created alert: {alert.id}")
        print(f"Stats: {engine.get_stats()}")
