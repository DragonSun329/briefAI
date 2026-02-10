"""
Alert Store Module

SQLite-based persistent storage for alerts with cooldown enforcement
and severity tracking.
"""

import sqlite3
import json
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional
from enum import Enum


class AlertSeverity(str, Enum):
    """Alert severity levels."""
    INFO = "info"
    WARN = "warn"
    CRIT = "crit"


class AlertType(str, Enum):
    """Types of divergence alerts."""
    ALPHA_ZONE = "alpha_zone"           # TMS high, CCS low (hidden gem)
    HYPE_ZONE = "hype_zone"             # CCS high, TMS low (vaporware)
    ENTERPRISE_PULL = "enterprise_pull"  # EIS rising with TMS support
    DISRUPTION_PRESSURE = "disruption_pressure"  # EIS defensive high
    ROTATION = "rotation"                # Market maturation signal


class AlertInterpretation(str, Enum):
    """How to interpret the alert."""
    OPPORTUNITY = "opportunity"
    RISK = "risk"
    SIGNAL = "signal"
    NEUTRAL = "neutral"


# Default cooldown periods by severity (days)
DEFAULT_COOLDOWNS = {
    AlertSeverity.INFO: 3,
    AlertSeverity.WARN: 7,
    AlertSeverity.CRIT: 14,
}


@dataclass
class StoredAlert:
    """Alert record for database storage."""
    alert_id: str
    bucket_id: str
    bucket_name: str
    alert_type: str
    severity: str
    interpretation: str

    # Timing
    first_detected: str       # ISO date
    last_updated: str         # ISO datetime
    last_shown: Optional[str] = None  # When shown to user
    cooldown_expires: Optional[str] = None
    expired_at: Optional[str] = None
    expired_reason: Optional[str] = None

    # Persistence tracking
    weeks_persistent: int = 1

    # Score data
    trigger_scores: Dict[str, float] = None
    divergence_magnitude: float = 0.0
    z_score: Optional[float] = None

    # Evidence
    evidence_payload: Dict[str, Any] = None
    rationale: str = ""

    # User actions
    dismissed_by_user: bool = False
    dismissed_at: Optional[str] = None
    watching: bool = False

    def is_active(self) -> bool:
        """Check if alert is currently active (not expired)."""
        return self.expired_at is None

    def is_in_cooldown(self) -> bool:
        """Check if alert is in cooldown period."""
        if not self.cooldown_expires:
            return False
        cooldown_date = datetime.fromisoformat(self.cooldown_expires)
        return datetime.now() < cooldown_date

    def should_show(self) -> bool:
        """Check if alert should be shown (active and not in cooldown)."""
        if not self.is_active():
            return False
        if self.dismissed_by_user and not self._cooldown_since_dismiss_expired():
            return False
        return not self.is_in_cooldown()

    def _cooldown_since_dismiss_expired(self) -> bool:
        """Check if cooldown since user dismiss has expired."""
        if not self.dismissed_at:
            return True
        dismissed = datetime.fromisoformat(self.dismissed_at)
        # 7-day cooldown after user dismissal
        return datetime.now() > dismissed + timedelta(days=7)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "alert_id": self.alert_id,
            "bucket_id": self.bucket_id,
            "bucket_name": self.bucket_name,
            "alert_type": self.alert_type,
            "severity": self.severity,
            "interpretation": self.interpretation,
            "first_detected": self.first_detected,
            "last_updated": self.last_updated,
            "last_shown": self.last_shown,
            "cooldown_expires": self.cooldown_expires,
            "expired_at": self.expired_at,
            "expired_reason": self.expired_reason,
            "weeks_persistent": self.weeks_persistent,
            "trigger_scores": self.trigger_scores,
            "divergence_magnitude": self.divergence_magnitude,
            "z_score": self.z_score,
            "evidence_payload": self.evidence_payload,
            "rationale": self.rationale,
            "dismissed_by_user": self.dismissed_by_user,
            "dismissed_at": self.dismissed_at,
            "watching": self.watching,
            "is_active": self.is_active(),
            "is_in_cooldown": self.is_in_cooldown(),
            "should_show": self.should_show(),
        }


class AlertStore:
    """
    SQLite-based persistent storage for alerts.

    Provides:
    - Alert CRUD operations
    - Cooldown enforcement
    - Severity escalation tracking
    - User action persistence (dismiss, watch)
    """

    def __init__(self, db_path: Path = None):
        """
        Initialize alert store.

        Args:
            db_path: Path to SQLite database
        """
        self.db_path = db_path or Path("data/alerts.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self) -> None:
        """Create database tables if they don't exist."""
        cursor = self.conn.cursor()

        # Main alerts table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                alert_id TEXT PRIMARY KEY,
                bucket_id TEXT NOT NULL,
                bucket_name TEXT NOT NULL,
                alert_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                interpretation TEXT NOT NULL,

                first_detected TEXT NOT NULL,
                last_updated TEXT NOT NULL,
                last_shown TEXT,
                cooldown_expires TEXT,
                expired_at TEXT,
                expired_reason TEXT,

                weeks_persistent INTEGER DEFAULT 1,

                trigger_scores TEXT,
                divergence_magnitude REAL DEFAULT 0,
                z_score REAL,

                evidence_payload TEXT,
                rationale TEXT,

                dismissed_by_user INTEGER DEFAULT 0,
                dismissed_at TEXT,
                watching INTEGER DEFAULT 0,

                UNIQUE(bucket_id, alert_type)
            )
        """)

        # Alert history for analytics
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS alert_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                event_data TEXT,
                occurred_at TEXT NOT NULL
            )
        """)

        # Indexes for common queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_alerts_bucket
            ON alerts(bucket_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_alerts_active
            ON alerts(expired_at)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_alerts_severity
            ON alerts(severity)
        """)

        self.conn.commit()

    def save_alert(self, alert: StoredAlert) -> str:
        """
        Save or update an alert.

        If alert exists for bucket+type, updates it.
        Otherwise creates new alert.

        Args:
            alert: Alert to save

        Returns:
            Alert ID
        """
        cursor = self.conn.cursor()

        # Check if exists
        cursor.execute("""
            SELECT alert_id, severity, weeks_persistent
            FROM alerts
            WHERE bucket_id = ? AND alert_type = ? AND expired_at IS NULL
        """, (alert.bucket_id, alert.alert_type))

        existing = cursor.fetchone()

        if existing:
            # Update existing alert
            old_severity = existing["severity"]
            old_weeks = existing["weeks_persistent"]
            alert.alert_id = existing["alert_id"]
            alert.weeks_persistent = old_weeks + 1

            # Check for severity escalation
            if self._severity_escalated(old_severity, alert.severity):
                # Reset cooldown on escalation
                alert.cooldown_expires = None
                self._log_history(alert.alert_id, "severity_escalated", {
                    "old": old_severity,
                    "new": alert.severity
                })

            cursor.execute("""
                UPDATE alerts SET
                    severity = ?,
                    last_updated = ?,
                    weeks_persistent = ?,
                    trigger_scores = ?,
                    divergence_magnitude = ?,
                    z_score = ?,
                    evidence_payload = ?,
                    rationale = ?
                WHERE alert_id = ?
            """, (
                alert.severity,
                alert.last_updated,
                alert.weeks_persistent,
                json.dumps(alert.trigger_scores) if alert.trigger_scores else None,
                alert.divergence_magnitude,
                alert.z_score,
                json.dumps(alert.evidence_payload) if alert.evidence_payload else None,
                alert.rationale,
                alert.alert_id,
            ))

            self._log_history(alert.alert_id, "updated", {"weeks": alert.weeks_persistent})

        else:
            # Create new alert
            if not alert.alert_id:
                alert.alert_id = str(uuid.uuid4())[:8]

            cursor.execute("""
                INSERT INTO alerts (
                    alert_id, bucket_id, bucket_name, alert_type, severity, interpretation,
                    first_detected, last_updated, weeks_persistent,
                    trigger_scores, divergence_magnitude, z_score,
                    evidence_payload, rationale
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                alert.alert_id,
                alert.bucket_id,
                alert.bucket_name,
                alert.alert_type,
                alert.severity,
                alert.interpretation,
                alert.first_detected,
                alert.last_updated,
                alert.weeks_persistent,
                json.dumps(alert.trigger_scores) if alert.trigger_scores else None,
                alert.divergence_magnitude,
                alert.z_score,
                json.dumps(alert.evidence_payload) if alert.evidence_payload else None,
                alert.rationale,
            ))

            self._log_history(alert.alert_id, "created", {})

        self.conn.commit()
        return alert.alert_id

    def _severity_escalated(self, old: str, new: str) -> bool:
        """Check if severity escalated."""
        order = {"info": 0, "warn": 1, "crit": 2}
        return order.get(new, 0) > order.get(old, 0)

    def _log_history(self, alert_id: str, event_type: str, data: Dict) -> None:
        """Log alert event to history table."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO alert_history (alert_id, event_type, event_data, occurred_at)
            VALUES (?, ?, ?, ?)
        """, (
            alert_id,
            event_type,
            json.dumps(data),
            datetime.now().isoformat(),
        ))

    def get_alert(self, alert_id: str) -> Optional[StoredAlert]:
        """Get alert by ID."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM alerts WHERE alert_id = ?", (alert_id,))
        row = cursor.fetchone()
        return self._row_to_alert(row) if row else None

    def get_active_alerts(self, bucket_id: str = None,
                          severity: str = None) -> List[StoredAlert]:
        """
        Get active (non-expired) alerts.

        Args:
            bucket_id: Optional filter by bucket
            severity: Optional filter by severity

        Returns:
            List of active alerts
        """
        cursor = self.conn.cursor()

        query = "SELECT * FROM alerts WHERE expired_at IS NULL"
        params = []

        if bucket_id:
            query += " AND bucket_id = ?"
            params.append(bucket_id)

        if severity:
            query += " AND severity = ?"
            params.append(severity)

        query += " ORDER BY CASE severity WHEN 'crit' THEN 0 WHEN 'warn' THEN 1 ELSE 2 END"

        cursor.execute(query, params)
        return [self._row_to_alert(row) for row in cursor.fetchall()]

    def get_showable_alerts(self, bucket_id: str = None) -> List[StoredAlert]:
        """
        Get alerts that should be shown (active and not in cooldown).

        Args:
            bucket_id: Optional filter by bucket

        Returns:
            List of showable alerts
        """
        alerts = self.get_active_alerts(bucket_id)
        return [a for a in alerts if a.should_show()]

    def check_cooldown(self, bucket_id: str, alert_type: str) -> bool:
        """
        Check if an alert is in cooldown.

        Args:
            bucket_id: Bucket identifier
            alert_type: Alert type

        Returns:
            True if in cooldown (don't show), False otherwise
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT cooldown_expires FROM alerts
            WHERE bucket_id = ? AND alert_type = ? AND expired_at IS NULL
        """, (bucket_id, alert_type))

        row = cursor.fetchone()
        if not row or not row["cooldown_expires"]:
            return False

        cooldown_date = datetime.fromisoformat(row["cooldown_expires"])
        return datetime.now() < cooldown_date

    def mark_shown(self, alert_id: str, cooldown_days: int = None) -> None:
        """
        Mark alert as shown and start cooldown.

        Args:
            alert_id: Alert identifier
            cooldown_days: Cooldown period (uses default if not specified)
        """
        alert = self.get_alert(alert_id)
        if not alert:
            return

        if cooldown_days is None:
            cooldown_days = DEFAULT_COOLDOWNS.get(
                AlertSeverity(alert.severity),
                DEFAULT_COOLDOWNS[AlertSeverity.INFO]
            )

        now = datetime.now()
        cooldown_expires = now + timedelta(days=cooldown_days)

        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE alerts SET
                last_shown = ?,
                cooldown_expires = ?
            WHERE alert_id = ?
        """, (
            now.isoformat(),
            cooldown_expires.isoformat(),
            alert_id,
        ))

        self._log_history(alert_id, "shown", {"cooldown_days": cooldown_days})
        self.conn.commit()

    def dismiss_alert(self, alert_id: str, by_user: bool = True) -> None:
        """
        Dismiss an alert.

        Args:
            alert_id: Alert identifier
            by_user: Whether dismissed by user action
        """
        cursor = self.conn.cursor()

        if by_user:
            cursor.execute("""
                UPDATE alerts SET
                    dismissed_by_user = 1,
                    dismissed_at = ?
                WHERE alert_id = ?
            """, (datetime.now().isoformat(), alert_id))
            self._log_history(alert_id, "dismissed_by_user", {})
        else:
            cursor.execute("""
                UPDATE alerts SET
                    dismissed_by_user = 0,
                    dismissed_at = NULL
                WHERE alert_id = ?
            """, (alert_id,))

        self.conn.commit()

    def watch_alert(self, alert_id: str, watching: bool = True) -> None:
        """
        Toggle watch status for an alert.

        Args:
            alert_id: Alert identifier
            watching: Whether to watch
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE alerts SET watching = ? WHERE alert_id = ?
        """, (1 if watching else 0, alert_id))

        self._log_history(alert_id, "watch_toggled", {"watching": watching})
        self.conn.commit()

    def expire_alert(self, alert_id: str, reason: str) -> None:
        """
        Mark alert as expired.

        Args:
            alert_id: Alert identifier
            reason: Why alert expired (e.g., "conditions_no_longer_met")
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE alerts SET
                expired_at = ?,
                expired_reason = ?
            WHERE alert_id = ?
        """, (datetime.now().isoformat(), reason, alert_id))

        self._log_history(alert_id, "expired", {"reason": reason})
        self.conn.commit()

    def expire_stale_alerts(self, max_age_weeks: int = 8) -> int:
        """
        Expire alerts that haven't been updated recently.

        Args:
            max_age_weeks: Maximum age before expiration

        Returns:
            Number of alerts expired
        """
        cutoff = (datetime.now() - timedelta(weeks=max_age_weeks)).isoformat()

        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT alert_id FROM alerts
            WHERE expired_at IS NULL AND last_updated < ?
        """, (cutoff,))

        alert_ids = [row["alert_id"] for row in cursor.fetchall()]

        for alert_id in alert_ids:
            self.expire_alert(alert_id, "stale")

        return len(alert_ids)

    def get_alert_history(self, alert_id: str) -> List[Dict[str, Any]]:
        """Get event history for an alert."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM alert_history
            WHERE alert_id = ?
            ORDER BY occurred_at DESC
        """, (alert_id,))

        return [
            {
                "event_type": row["event_type"],
                "event_data": json.loads(row["event_data"]) if row["event_data"] else {},
                "occurred_at": row["occurred_at"],
            }
            for row in cursor.fetchall()
        ]

    def get_alert_stats(self) -> Dict[str, Any]:
        """Get aggregate statistics about alerts."""
        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN expired_at IS NULL THEN 1 ELSE 0 END) as active,
                SUM(CASE WHEN severity = 'crit' AND expired_at IS NULL THEN 1 ELSE 0 END) as critical,
                SUM(CASE WHEN severity = 'warn' AND expired_at IS NULL THEN 1 ELSE 0 END) as warning,
                SUM(CASE WHEN severity = 'info' AND expired_at IS NULL THEN 1 ELSE 0 END) as info,
                SUM(CASE WHEN interpretation = 'opportunity' AND expired_at IS NULL THEN 1 ELSE 0 END) as opportunities,
                SUM(CASE WHEN interpretation = 'risk' AND expired_at IS NULL THEN 1 ELSE 0 END) as risks,
                AVG(weeks_persistent) as avg_persistence
            FROM alerts
        """)

        row = cursor.fetchone()
        return {
            "total_alerts": row["total"] or 0,
            "active_alerts": row["active"] or 0,
            "critical": row["critical"] or 0,
            "warning": row["warning"] or 0,
            "info": row["info"] or 0,
            "opportunities": row["opportunities"] or 0,
            "risks": row["risks"] or 0,
            "avg_persistence_weeks": round(row["avg_persistence"] or 0, 1),
        }

    def _row_to_alert(self, row: sqlite3.Row) -> StoredAlert:
        """Convert database row to StoredAlert."""
        return StoredAlert(
            alert_id=row["alert_id"],
            bucket_id=row["bucket_id"],
            bucket_name=row["bucket_name"],
            alert_type=row["alert_type"],
            severity=row["severity"],
            interpretation=row["interpretation"],
            first_detected=row["first_detected"],
            last_updated=row["last_updated"],
            last_shown=row["last_shown"],
            cooldown_expires=row["cooldown_expires"],
            expired_at=row["expired_at"],
            expired_reason=row["expired_reason"],
            weeks_persistent=row["weeks_persistent"],
            trigger_scores=json.loads(row["trigger_scores"]) if row["trigger_scores"] else None,
            divergence_magnitude=row["divergence_magnitude"] or 0,
            z_score=row["z_score"],
            evidence_payload=json.loads(row["evidence_payload"]) if row["evidence_payload"] else None,
            rationale=row["rationale"] or "",
            dismissed_by_user=bool(row["dismissed_by_user"]),
            dismissed_at=row["dismissed_at"],
            watching=bool(row["watching"]),
        )

    def close(self) -> None:
        """Close database connection."""
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()