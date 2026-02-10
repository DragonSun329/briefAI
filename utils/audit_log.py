"""
Audit Log for Bloomberg Terminal-Grade Provenance Tracking.

Tracks every data mutation with:
- Timestamp, source, actor
- Previous and new values
- Reason for change
- Full entity history queries
"""

import json
import logging
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


@dataclass
class AuditEntry:
    """A single audit log entry."""
    id: str
    table_name: str
    record_id: str
    operation: str  # INSERT, UPDATE, DELETE
    source_id: Optional[str]
    actor: str
    field_name: Optional[str]
    old_value: Any
    new_value: Any
    change_reason: Optional[str]
    related_observation_id: Optional[str]
    entity_id: Optional[str]
    timestamp: datetime


@dataclass
class EntityHistory:
    """Complete history for an entity."""
    entity_id: str
    entity_name: Optional[str]
    total_changes: int
    first_seen: datetime
    last_modified: datetime
    changes_by_source: Dict[str, int]
    changes_by_field: Dict[str, int]
    entries: List[AuditEntry] = field(default_factory=list)


class AuditLogger:
    """
    Provenance tracking for all data mutations.
    
    Features:
    - Automatic logging of all INSERT/UPDATE/DELETE operations
    - Full history queries per entity
    - Source attribution tracking
    - Change diffing and rollback support
    """
    
    def __init__(self, db_path: Optional[str] = None):
        """Initialize audit logger."""
        if db_path is None:
            db_path = str(Path(__file__).parent.parent / "data" / "signals.db")
        self.db_path = db_path
        self._ensure_tables()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _ensure_tables(self):
        """Ensure audit tables exist."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id TEXT PRIMARY KEY,
                table_name TEXT NOT NULL,
                record_id TEXT NOT NULL,
                operation TEXT NOT NULL,
                source_id TEXT,
                actor TEXT DEFAULT 'system',
                field_name TEXT,
                old_value TEXT,
                new_value TEXT,
                change_reason TEXT,
                related_observation_id TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                entity_id TEXT
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_record ON audit_log(table_name, record_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_entity ON audit_log(entity_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp ON audit_log(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_source ON audit_log(source_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_operation ON audit_log(operation)")
        
        conn.commit()
        conn.close()
    
    def log(
        self,
        table_name: str,
        record_id: str,
        operation: str,
        source_id: Optional[str] = None,
        actor: str = "system",
        field_name: Optional[str] = None,
        old_value: Any = None,
        new_value: Any = None,
        change_reason: Optional[str] = None,
        related_observation_id: Optional[str] = None,
        entity_id: Optional[str] = None,
    ) -> str:
        """
        Log a data mutation.
        
        Args:
            table_name: Table that was modified
            record_id: ID of the record
            operation: INSERT, UPDATE, or DELETE
            source_id: Data source that triggered the change
            actor: Who/what made the change (system, pipeline:xyz, manual:user)
            field_name: Specific field that changed (for UPDATE)
            old_value: Previous value
            new_value: New value
            change_reason: Why the change was made
            related_observation_id: Link to observation that triggered change
            entity_id: Entity ID for faster queries
        
        Returns:
            Audit entry ID
        """
        entry_id = str(uuid.uuid4())
        
        # Serialize values to JSON if complex
        old_json = self._serialize_value(old_value)
        new_json = self._serialize_value(new_value)
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO audit_log (
                id, table_name, record_id, operation, source_id, actor,
                field_name, old_value, new_value, change_reason,
                related_observation_id, entity_id, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            entry_id, table_name, record_id, operation, source_id, actor,
            field_name, old_json, new_json, change_reason,
            related_observation_id, entity_id,
            datetime.utcnow().isoformat()
        ))
        
        conn.commit()
        conn.close()
        
        logger.debug(
            f"Audit: {operation} {table_name}.{record_id} "
            f"field={field_name} by={actor} source={source_id}"
        )
        
        return entry_id
    
    def log_insert(
        self,
        table_name: str,
        record_id: str,
        data: Dict[str, Any],
        source_id: Optional[str] = None,
        actor: str = "system",
        entity_id: Optional[str] = None,
        change_reason: Optional[str] = None,
    ) -> str:
        """Log an INSERT operation."""
        return self.log(
            table_name=table_name,
            record_id=record_id,
            operation="INSERT",
            source_id=source_id,
            actor=actor,
            new_value=data,
            entity_id=entity_id,
            change_reason=change_reason or "record_created",
        )
    
    def log_update(
        self,
        table_name: str,
        record_id: str,
        field_name: str,
        old_value: Any,
        new_value: Any,
        source_id: Optional[str] = None,
        actor: str = "system",
        entity_id: Optional[str] = None,
        change_reason: Optional[str] = None,
        related_observation_id: Optional[str] = None,
    ) -> str:
        """Log an UPDATE operation."""
        return self.log(
            table_name=table_name,
            record_id=record_id,
            operation="UPDATE",
            source_id=source_id,
            actor=actor,
            field_name=field_name,
            old_value=old_value,
            new_value=new_value,
            entity_id=entity_id,
            change_reason=change_reason or "field_updated",
            related_observation_id=related_observation_id,
        )
    
    def log_delete(
        self,
        table_name: str,
        record_id: str,
        data: Dict[str, Any],
        source_id: Optional[str] = None,
        actor: str = "system",
        entity_id: Optional[str] = None,
        change_reason: Optional[str] = None,
    ) -> str:
        """Log a DELETE operation."""
        return self.log(
            table_name=table_name,
            record_id=record_id,
            operation="DELETE",
            source_id=source_id,
            actor=actor,
            old_value=data,
            entity_id=entity_id,
            change_reason=change_reason or "record_deleted",
        )
    
    def log_multi_field_update(
        self,
        table_name: str,
        record_id: str,
        changes: Dict[str, tuple],  # {field: (old_value, new_value)}
        source_id: Optional[str] = None,
        actor: str = "system",
        entity_id: Optional[str] = None,
        change_reason: Optional[str] = None,
        related_observation_id: Optional[str] = None,
    ) -> List[str]:
        """Log multiple field changes in one batch."""
        entry_ids = []
        for field_name, (old_val, new_val) in changes.items():
            entry_id = self.log_update(
                table_name=table_name,
                record_id=record_id,
                field_name=field_name,
                old_value=old_val,
                new_value=new_val,
                source_id=source_id,
                actor=actor,
                entity_id=entity_id,
                change_reason=change_reason,
                related_observation_id=related_observation_id,
            )
            entry_ids.append(entry_id)
        return entry_ids
    
    def _serialize_value(self, value: Any) -> Optional[str]:
        """Serialize a value to JSON string."""
        if value is None:
            return None
        if isinstance(value, (str, int, float, bool)):
            return json.dumps(value)
        if isinstance(value, datetime):
            return json.dumps(value.isoformat())
        try:
            return json.dumps(value)
        except (TypeError, ValueError):
            return str(value)
    
    def _deserialize_value(self, json_str: Optional[str]) -> Any:
        """Deserialize a JSON string to value."""
        if json_str is None:
            return None
        try:
            return json.loads(json_str)
        except (json.JSONDecodeError, TypeError):
            return json_str
    
    def _row_to_entry(self, row: sqlite3.Row) -> AuditEntry:
        """Convert database row to AuditEntry."""
        return AuditEntry(
            id=row["id"],
            table_name=row["table_name"],
            record_id=row["record_id"],
            operation=row["operation"],
            source_id=row["source_id"],
            actor=row["actor"],
            field_name=row["field_name"],
            old_value=self._deserialize_value(row["old_value"]),
            new_value=self._deserialize_value(row["new_value"]),
            change_reason=row["change_reason"],
            related_observation_id=row["related_observation_id"],
            entity_id=row["entity_id"],
            timestamp=datetime.fromisoformat(row["timestamp"]) if row["timestamp"] else datetime.utcnow(),
        )
    
    # =========================================================================
    # Query Methods
    # =========================================================================
    
    def get_record_history(
        self,
        table_name: str,
        record_id: str,
        limit: int = 100
    ) -> List[AuditEntry]:
        """Get full history for a specific record."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM audit_log
            WHERE table_name = ? AND record_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
        """, (table_name, record_id, limit))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [self._row_to_entry(row) for row in rows]
    
    def get_entity_history(
        self,
        entity_id: str,
        include_related: bool = True,
        limit: int = 500
    ) -> EntityHistory:
        """
        Get complete history for an entity across all tables.
        
        Args:
            entity_id: Entity ID
            include_related: Include related records (observations, scores)
            limit: Maximum entries to return
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Get all entries for this entity
        cursor.execute("""
            SELECT * FROM audit_log
            WHERE entity_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
        """, (entity_id, limit))
        
        rows = cursor.fetchall()
        entries = [self._row_to_entry(row) for row in rows]
        
        # Get entity name if available
        entity_name = None
        try:
            cursor.execute("SELECT name FROM entities WHERE id = ? OR canonical_id = ?", (entity_id, entity_id))
            row = cursor.fetchone()
            if row:
                entity_name = row["name"]
        except sqlite3.OperationalError:
            # entities table may not exist in test environments
            pass
        
        conn.close()
        
        if not entries:
            return EntityHistory(
                entity_id=entity_id,
                entity_name=entity_name,
                total_changes=0,
                first_seen=datetime.utcnow(),
                last_modified=datetime.utcnow(),
                changes_by_source={},
                changes_by_field={},
                entries=[]
            )
        
        # Compute statistics
        changes_by_source: Dict[str, int] = {}
        changes_by_field: Dict[str, int] = {}
        
        for entry in entries:
            source = entry.source_id or "unknown"
            changes_by_source[source] = changes_by_source.get(source, 0) + 1
            
            if entry.field_name:
                changes_by_field[entry.field_name] = changes_by_field.get(entry.field_name, 0) + 1
        
        return EntityHistory(
            entity_id=entity_id,
            entity_name=entity_name,
            total_changes=len(entries),
            first_seen=entries[-1].timestamp,  # Oldest entry
            last_modified=entries[0].timestamp,  # Most recent
            changes_by_source=changes_by_source,
            changes_by_field=changes_by_field,
            entries=entries,
        )
    
    def get_changes_by_source(
        self,
        source_id: str,
        since: Optional[datetime] = None,
        limit: int = 100
    ) -> List[AuditEntry]:
        """Get all changes made by a specific source."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        if since:
            cursor.execute("""
                SELECT * FROM audit_log
                WHERE source_id = ? AND timestamp >= ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (source_id, since.isoformat(), limit))
        else:
            cursor.execute("""
                SELECT * FROM audit_log
                WHERE source_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (source_id, limit))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [self._row_to_entry(row) for row in rows]
    
    def get_recent_changes(
        self,
        table_name: Optional[str] = None,
        operation: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 100
    ) -> List[AuditEntry]:
        """Get recent changes with optional filters."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        query = "SELECT * FROM audit_log WHERE 1=1"
        params = []
        
        if table_name:
            query += " AND table_name = ?"
            params.append(table_name)
        
        if operation:
            query += " AND operation = ?"
            params.append(operation)
        
        if since:
            query += " AND timestamp >= ?"
            params.append(since.isoformat())
        
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        return [self._row_to_entry(row) for row in rows]
    
    def get_field_history(
        self,
        table_name: str,
        record_id: str,
        field_name: str,
        limit: int = 50
    ) -> List[AuditEntry]:
        """Get history for a specific field on a record."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM audit_log
            WHERE table_name = ? AND record_id = ? AND field_name = ?
            ORDER BY timestamp DESC
            LIMIT ?
        """, (table_name, record_id, field_name, limit))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [self._row_to_entry(row) for row in rows]
    
    def get_value_at_time(
        self,
        table_name: str,
        record_id: str,
        field_name: str,
        at_time: datetime
    ) -> Any:
        """
        Get the value of a field at a specific point in time.
        
        Reconstructs historical state by walking back from current value.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Get all changes to this field after the target time
        cursor.execute("""
            SELECT old_value, new_value, timestamp FROM audit_log
            WHERE table_name = ? AND record_id = ? AND field_name = ?
              AND timestamp > ?
            ORDER BY timestamp ASC
        """, (table_name, record_id, field_name, at_time.isoformat()))
        
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            # No changes after target time, return current value
            # (would need to query the actual table for this)
            return None
        
        # The old_value of the first change after target time is what we want
        return self._deserialize_value(rows[0]["old_value"])
    
    # =========================================================================
    # Statistics
    # =========================================================================
    
    def get_statistics(
        self,
        since: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get audit log statistics."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        time_filter = ""
        params = []
        if since:
            time_filter = "WHERE timestamp >= ?"
            params.append(since.isoformat())
        
        # Total entries
        cursor.execute(f"SELECT COUNT(*) FROM audit_log {time_filter}", params)
        total = cursor.fetchone()[0]
        
        # By operation
        cursor.execute(f"""
            SELECT operation, COUNT(*) FROM audit_log {time_filter}
            GROUP BY operation
        """, params)
        by_operation = {row[0]: row[1] for row in cursor.fetchall()}
        
        # By table
        cursor.execute(f"""
            SELECT table_name, COUNT(*) FROM audit_log {time_filter}
            GROUP BY table_name
        """, params)
        by_table = {row[0]: row[1] for row in cursor.fetchall()}
        
        # Top sources
        cursor.execute(f"""
            SELECT source_id, COUNT(*) as cnt FROM audit_log {time_filter}
            GROUP BY source_id
            ORDER BY cnt DESC
            LIMIT 10
        """, params)
        top_sources = {row[0] or "unknown": row[1] for row in cursor.fetchall()}
        
        # Most active entities
        cursor.execute(f"""
            SELECT entity_id, COUNT(*) as cnt FROM audit_log 
            {time_filter + ' AND' if time_filter else 'WHERE'} entity_id IS NOT NULL
            GROUP BY entity_id
            ORDER BY cnt DESC
            LIMIT 10
        """, params if since else [])
        top_entities = {row[0]: row[1] for row in cursor.fetchall()}
        
        conn.close()
        
        return {
            "total_entries": total,
            "by_operation": by_operation,
            "by_table": by_table,
            "top_sources": top_sources,
            "top_entities": top_entities,
            "since": since.isoformat() if since else None,
        }
    
    def cleanup_old_entries(
        self,
        older_than_days: int = 365,
        keep_important: bool = True
    ) -> int:
        """
        Clean up old audit entries.
        
        Args:
            older_than_days: Delete entries older than this
            keep_important: Keep DELETE operations and high-value changes
        
        Returns:
            Number of entries deleted
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cutoff = (datetime.utcnow() - timedelta(days=older_than_days)).isoformat()
        
        if keep_important:
            cursor.execute("""
                DELETE FROM audit_log
                WHERE timestamp < ?
                  AND operation != 'DELETE'
                  AND (change_reason IS NULL OR change_reason NOT LIKE '%important%')
            """, (cutoff,))
        else:
            cursor.execute("DELETE FROM audit_log WHERE timestamp < ?", (cutoff,))
        
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        
        logger.info(f"Audit log cleanup: deleted {deleted} entries older than {older_than_days} days")
        return deleted
