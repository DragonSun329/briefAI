"""
Event Store - SQLite Storage for Business Events

Provides:
- CRUD operations for BusinessEvent
- Querying by entity, type, date range
- Timeline generation
- Event linking and deduplication
"""

import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from loguru import logger

from utils.event_models import (
    BusinessEvent, BusinessEventType, EventConfidence, EventSource,
    FundingDetails, FundingStage, AcquisitionDetails, ProductLaunchDetails,
    LeadershipChangeDetails, PartnershipDetails, LayoffDetails,
    EventTimeline
)


class BusinessEventStore:
    """
    SQLite storage for business events.
    
    Handles persistence, querying, and deduplication of events.
    """
    
    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize event store.
        
        Args:
            db_path: Path to SQLite database. Defaults to data/business_events.db
        """
        if db_path is None:
            db_path = str(Path(__file__).parent.parent / "data" / "business_events.db")
        
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        
        self._ensure_tables()
        logger.info(f"BusinessEventStore initialized at {db_path}")
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection with row factory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _ensure_tables(self) -> None:
        """Create tables if they don't exist."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Main events table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS business_events (
                event_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                entity_name TEXT NOT NULL,
                related_entity_ids TEXT,
                related_entity_names TEXT,
                event_date TEXT,
                headline TEXT NOT NULL,
                summary TEXT,
                
                -- Type-specific details (JSON)
                funding_details TEXT,
                acquisition_details TEXT,
                product_details TEXT,
                leadership_details TEXT,
                partnership_details TEXT,
                layoff_details TEXT,
                details TEXT,
                
                -- Sources and confidence
                sources TEXT,
                confidence TEXT NOT NULL,
                confidence_score REAL NOT NULL,
                
                -- Deduplication
                content_hash TEXT NOT NULL,
                merged_from TEXT,
                
                -- Event linking
                parent_event_id TEXT,
                related_event_ids TEXT,
                
                -- Timestamps
                first_reported TEXT NOT NULL,
                last_updated TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        
        # Indexes for common queries
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_entity ON business_events(entity_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON business_events(event_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_date ON business_events(event_date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_hash ON business_events(content_hash)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_reported ON business_events(first_reported)")
        
        # Event sources table (for querying by source)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS event_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL,
                source_id TEXT NOT NULL,
                source_name TEXT NOT NULL,
                source_url TEXT,
                source_credibility REAL,
                published_at TEXT,
                excerpt TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (event_id) REFERENCES business_events(event_id)
            )
        """)
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sources_event ON event_sources(event_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sources_source ON event_sources(source_id)")
        
        # Event links table (for causal chains)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS event_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_event_id TEXT NOT NULL,
                to_event_id TEXT NOT NULL,
                link_type TEXT NOT NULL,  -- 'causes', 'related', 'supersedes'
                confidence REAL DEFAULT 0.5,
                created_at TEXT NOT NULL,
                FOREIGN KEY (from_event_id) REFERENCES business_events(event_id),
                FOREIGN KEY (to_event_id) REFERENCES business_events(event_id),
                UNIQUE(from_event_id, to_event_id, link_type)
            )
        """)
        
        conn.commit()
        conn.close()
    
    # =========================================================================
    # CRUD Operations
    # =========================================================================
    
    def save_event(self, event: BusinessEvent) -> str:
        """
        Save or update an event.
        
        If event with same content_hash exists, merges sources.
        
        Args:
            event: BusinessEvent to save
        
        Returns:
            Event ID (may be existing if merged)
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Check for existing event by content hash
        cursor.execute(
            "SELECT event_id FROM business_events WHERE content_hash = ?",
            (event.content_hash,)
        )
        existing = cursor.fetchone()
        
        if existing:
            # Merge with existing event
            existing_id = existing["event_id"]
            existing_event = self.get_event(existing_id)
            
            if existing_event:
                existing_event.merge_with(event)
                self._update_event(cursor, existing_event)
                
                # Save new sources
                for source in event.sources:
                    self._save_source(cursor, existing_id, source)
                
                conn.commit()
                conn.close()
                
                logger.debug(f"Merged event into {existing_id}")
                return existing_id
        
        # Insert new event
        cursor.execute("""
            INSERT INTO business_events (
                event_id, event_type, entity_id, entity_name,
                related_entity_ids, related_entity_names,
                event_date, headline, summary,
                funding_details, acquisition_details, product_details,
                leadership_details, partnership_details, layoff_details, details,
                sources, confidence, confidence_score,
                content_hash, merged_from,
                parent_event_id, related_event_ids,
                first_reported, last_updated, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            event.event_id,
            event.event_type.value,
            event.entity_id,
            event.entity_name,
            json.dumps(event.related_entity_ids),
            json.dumps(event.related_entity_names),
            event.event_date.isoformat() if event.event_date else None,
            event.headline,
            event.summary,
            json.dumps(event.funding_details.to_dict()) if event.funding_details else None,
            json.dumps(event.acquisition_details.to_dict()) if event.acquisition_details else None,
            json.dumps(event.product_details.to_dict()) if event.product_details else None,
            json.dumps(event.leadership_details.to_dict()) if event.leadership_details else None,
            json.dumps(event.partnership_details.to_dict()) if event.partnership_details else None,
            json.dumps(event.layoff_details.to_dict()) if event.layoff_details else None,
            json.dumps(event.details),
            json.dumps([s.to_dict() for s in event.sources]),
            event.confidence.value,
            event.confidence_score,
            event.content_hash,
            json.dumps(event.merged_from),
            event.parent_event_id,
            json.dumps(event.related_event_ids),
            event.first_reported.isoformat(),
            event.last_updated.isoformat(),
            event.created_at.isoformat(),
        ))
        
        # Save sources to separate table
        for source in event.sources:
            self._save_source(cursor, event.event_id, source)
        
        conn.commit()
        conn.close()
        
        logger.debug(f"Saved new event {event.event_id}: {event.headline[:50]}")
        return event.event_id
    
    def _update_event(self, cursor: sqlite3.Cursor, event: BusinessEvent) -> None:
        """Update an existing event."""
        cursor.execute("""
            UPDATE business_events SET
                sources = ?,
                confidence = ?,
                confidence_score = ?,
                merged_from = ?,
                related_event_ids = ?,
                last_updated = ?
            WHERE event_id = ?
        """, (
            json.dumps([s.to_dict() for s in event.sources]),
            event.confidence.value,
            event.confidence_score,
            json.dumps(event.merged_from),
            json.dumps(event.related_event_ids),
            datetime.utcnow().isoformat(),
            event.event_id,
        ))
    
    def _save_source(
        self, 
        cursor: sqlite3.Cursor, 
        event_id: str, 
        source: EventSource
    ) -> None:
        """Save event source to sources table."""
        # Check for duplicate
        cursor.execute(
            "SELECT id FROM event_sources WHERE event_id = ? AND source_url = ?",
            (event_id, source.source_url)
        )
        if cursor.fetchone():
            return
        
        cursor.execute("""
            INSERT INTO event_sources (
                event_id, source_id, source_name, source_url,
                source_credibility, published_at, excerpt, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            event_id,
            source.source_id,
            source.source_name,
            source.source_url,
            source.source_credibility,
            source.published_at.isoformat() if source.published_at else None,
            source.excerpt,
            datetime.utcnow().isoformat(),
        ))
    
    def get_event(self, event_id: str) -> Optional[BusinessEvent]:
        """Get event by ID."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT * FROM business_events WHERE event_id = ?",
            (event_id,)
        )
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return self._row_to_event(row)
        return None
    
    def delete_event(self, event_id: str) -> bool:
        """Delete an event and its sources."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM event_sources WHERE event_id = ?", (event_id,))
        cursor.execute("DELETE FROM event_links WHERE from_event_id = ? OR to_event_id = ?", 
                       (event_id, event_id))
        cursor.execute("DELETE FROM business_events WHERE event_id = ?", (event_id,))
        
        deleted = cursor.rowcount > 0
        conn.commit()
        conn.close()
        
        return deleted
    
    # =========================================================================
    # Query Operations
    # =========================================================================
    
    def get_events_by_entity(
        self,
        entity_id: str,
        event_type: Optional[BusinessEventType] = None,
        limit: int = 50
    ) -> List[BusinessEvent]:
        """
        Get events for an entity.
        
        Args:
            entity_id: Entity identifier
            event_type: Optional filter by event type
            limit: Maximum events to return
        
        Returns:
            List of events sorted by date (newest first)
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        query = """
            SELECT * FROM business_events 
            WHERE entity_id = ? OR related_entity_ids LIKE ?
        """
        params = [entity_id, f'%"{entity_id}"%']
        
        if event_type:
            query += " AND event_type = ?"
            params.append(event_type.value)
        
        query += " ORDER BY COALESCE(event_date, first_reported) DESC LIMIT ?"
        params.append(limit)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        return [self._row_to_event(row) for row in rows]
    
    def get_events_by_type(
        self,
        event_type: BusinessEventType,
        days: int = 30,
        limit: int = 100
    ) -> List[BusinessEvent]:
        """
        Get events of a specific type within time range.
        
        Args:
            event_type: Type of events to get
            days: Number of days to look back
            limit: Maximum events to return
        
        Returns:
            List of events sorted by date
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        
        cursor.execute("""
            SELECT * FROM business_events
            WHERE event_type = ? AND first_reported >= ?
            ORDER BY COALESCE(event_date, first_reported) DESC
            LIMIT ?
        """, (event_type.value, cutoff, limit))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [self._row_to_event(row) for row in rows]
    
    def get_events_in_range(
        self,
        start_date: datetime,
        end_date: datetime,
        event_types: Optional[List[BusinessEventType]] = None,
        entity_id: Optional[str] = None,
        limit: int = 500
    ) -> List[BusinessEvent]:
        """
        Get events within a date range.
        
        Args:
            start_date: Start of range
            end_date: End of range
            event_types: Optional filter by event types
            entity_id: Optional filter by entity
            limit: Maximum events
        
        Returns:
            List of events
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        query = """
            SELECT * FROM business_events
            WHERE COALESCE(event_date, first_reported) >= ?
            AND COALESCE(event_date, first_reported) <= ?
        """
        params = [start_date.isoformat(), end_date.isoformat()]
        
        if event_types:
            placeholders = ",".join("?" * len(event_types))
            query += f" AND event_type IN ({placeholders})"
            params.extend([t.value for t in event_types])
        
        if entity_id:
            query += " AND (entity_id = ? OR related_entity_ids LIKE ?)"
            params.extend([entity_id, f'%"{entity_id}"%'])
        
        query += " ORDER BY COALESCE(event_date, first_reported) DESC LIMIT ?"
        params.append(limit)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        return [self._row_to_event(row) for row in rows]
    
    def get_recent_events(
        self,
        days: int = 7,
        confidence_threshold: float = 0.3,
        limit: int = 100
    ) -> List[BusinessEvent]:
        """
        Get recent high-confidence events.
        
        Args:
            days: Number of days to look back
            confidence_threshold: Minimum confidence score
            limit: Maximum events
        
        Returns:
            List of events
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        
        cursor.execute("""
            SELECT * FROM business_events
            WHERE first_reported >= ?
            AND confidence_score >= ?
            ORDER BY first_reported DESC
            LIMIT ?
        """, (cutoff, confidence_threshold, limit))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [self._row_to_event(row) for row in rows]
    
    def find_by_content_hash(self, content_hash: str) -> Optional[BusinessEvent]:
        """Find event by content hash."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT * FROM business_events WHERE content_hash = ?",
            (content_hash,)
        )
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return self._row_to_event(row)
        return None
    
    def search_events(
        self,
        query: str,
        limit: int = 50
    ) -> List[BusinessEvent]:
        """
        Search events by headline or summary.
        
        Args:
            query: Search query
            limit: Maximum results
        
        Returns:
            List of matching events
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        search_pattern = f"%{query}%"
        
        cursor.execute("""
            SELECT * FROM business_events
            WHERE headline LIKE ? OR summary LIKE ? OR entity_name LIKE ?
            ORDER BY first_reported DESC
            LIMIT ?
        """, (search_pattern, search_pattern, search_pattern, limit))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [self._row_to_event(row) for row in rows]
    
    # =========================================================================
    # Timeline Operations
    # =========================================================================
    
    def get_entity_timeline(
        self,
        entity_id: str,
        days: int = 365
    ) -> EventTimeline:
        """
        Get event timeline for an entity.
        
        Args:
            entity_id: Entity identifier
            days: Number of days to include
        
        Returns:
            EventTimeline object
        """
        events = self.get_events_by_entity(entity_id, limit=100)
        
        # Get entity name from first event
        entity_name = events[0].entity_name if events else entity_id
        
        timeline = EventTimeline(
            entity_id=entity_id,
            entity_name=entity_name,
        )
        
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        for event in events:
            event_date = event.event_date or event.first_reported
            if event_date >= cutoff:
                timeline.add_event(event)
        
        return timeline
    
    # =========================================================================
    # Event Linking
    # =========================================================================
    
    def link_events(
        self,
        from_event_id: str,
        to_event_id: str,
        link_type: str = "related",
        confidence: float = 0.5
    ) -> None:
        """
        Create a link between two events.
        
        Args:
            from_event_id: Source event ID
            to_event_id: Target event ID
            link_type: Type of link (causes, related, supersedes)
            confidence: Confidence in the link
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO event_links 
                (from_event_id, to_event_id, link_type, confidence, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (from_event_id, to_event_id, link_type, confidence, 
                  datetime.utcnow().isoformat()))
            conn.commit()
        except Exception as e:
            logger.error(f"Failed to link events: {e}")
        finally:
            conn.close()
    
    def get_linked_events(
        self,
        event_id: str,
        link_type: Optional[str] = None
    ) -> List[Tuple[str, BusinessEvent]]:
        """
        Get events linked to a given event.
        
        Args:
            event_id: Event to get links for
            link_type: Optional filter by link type
        
        Returns:
            List of (link_type, event) tuples
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        query = """
            SELECT el.link_type, be.* FROM event_links el
            JOIN business_events be ON el.to_event_id = be.event_id
            WHERE el.from_event_id = ?
        """
        params = [event_id]
        
        if link_type:
            query += " AND el.link_type = ?"
            params.append(link_type)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        return [(row["link_type"], self._row_to_event(row)) for row in rows]
    
    def detect_causal_chains(self, entity_id: str) -> List[List[BusinessEvent]]:
        """
        Detect and link causal chains for an entity.
        
        Uses timeline to find potential cause-effect relationships.
        
        Args:
            entity_id: Entity to analyze
        
        Returns:
            List of causal chains (each chain is a list of events)
        """
        timeline = self.get_entity_timeline(entity_id)
        chains = timeline.detect_causal_chains()
        
        # Create links for detected chains
        for chain in chains:
            if len(chain) >= 2:
                cause = chain[0]
                effect = chain[1]
                self.link_events(cause.event_id, effect.event_id, "causes", 0.6)
        
        return chains
    
    # =========================================================================
    # Statistics
    # =========================================================================
    
    def get_stats(self) -> Dict[str, Any]:
        """Get event store statistics."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        stats = {}
        
        cursor.execute("SELECT COUNT(*) FROM business_events")
        stats["total_events"] = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT event_type, COUNT(*) 
            FROM business_events 
            GROUP BY event_type
        """)
        stats["by_type"] = {row[0]: row[1] for row in cursor.fetchall()}
        
        cursor.execute("""
            SELECT confidence, COUNT(*) 
            FROM business_events 
            GROUP BY confidence
        """)
        stats["by_confidence"] = {row[0]: row[1] for row in cursor.fetchall()}
        
        cursor.execute("""
            SELECT COUNT(DISTINCT entity_id) 
            FROM business_events
        """)
        stats["unique_entities"] = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM event_sources")
        stats["total_sources"] = cursor.fetchone()[0]
        
        # Recent activity
        week_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()
        cursor.execute(
            "SELECT COUNT(*) FROM business_events WHERE first_reported >= ?",
            (week_ago,)
        )
        stats["events_last_7_days"] = cursor.fetchone()[0]
        
        conn.close()
        return stats
    
    # =========================================================================
    # Helpers
    # =========================================================================
    
    def _row_to_event(self, row: sqlite3.Row) -> BusinessEvent:
        """Convert database row to BusinessEvent."""
        event = BusinessEvent(
            event_id=row["event_id"],
            event_type=BusinessEventType(row["event_type"]),
            entity_id=row["entity_id"],
            entity_name=row["entity_name"],
            related_entity_ids=json.loads(row["related_entity_ids"]) if row["related_entity_ids"] else [],
            related_entity_names=json.loads(row["related_entity_names"]) if row["related_entity_names"] else [],
            headline=row["headline"],
            summary=row["summary"] or "",
            details=json.loads(row["details"]) if row["details"] else {},
            confidence=EventConfidence(row["confidence"]),
            confidence_score=row["confidence_score"],
            content_hash=row["content_hash"],
            merged_from=json.loads(row["merged_from"]) if row["merged_from"] else [],
            parent_event_id=row["parent_event_id"],
            related_event_ids=json.loads(row["related_event_ids"]) if row["related_event_ids"] else [],
        )
        
        # Parse dates
        if row["event_date"]:
            event.event_date = datetime.fromisoformat(row["event_date"])
        event.first_reported = datetime.fromisoformat(row["first_reported"])
        event.last_updated = datetime.fromisoformat(row["last_updated"])
        event.created_at = datetime.fromisoformat(row["created_at"])
        
        # Parse sources
        if row["sources"]:
            event.sources = [EventSource.from_dict(s) for s in json.loads(row["sources"])]
        
        # Parse type-specific details
        if row["funding_details"]:
            event.funding_details = FundingDetails.from_dict(json.loads(row["funding_details"]))
        if row["acquisition_details"]:
            event.acquisition_details = AcquisitionDetails.from_dict(json.loads(row["acquisition_details"]))
        if row["product_details"]:
            event.product_details = ProductLaunchDetails.from_dict(json.loads(row["product_details"]))
        if row["leadership_details"]:
            event.leadership_details = LeadershipChangeDetails.from_dict(json.loads(row["leadership_details"]))
        if row["partnership_details"]:
            event.partnership_details = PartnershipDetails.from_dict(json.loads(row["partnership_details"]))
        if row["layoff_details"]:
            event.layoff_details = LayoffDetails.from_dict(json.loads(row["layoff_details"]))
        
        return event
    
    def save_events_batch(self, events: List[BusinessEvent]) -> int:
        """
        Save multiple events efficiently.
        
        Args:
            events: List of events to save
        
        Returns:
            Number of events saved (including merges)
        """
        saved = 0
        for event in events:
            self.save_event(event)
            saved += 1
        
        return saved
    
    def close(self) -> None:
        """Close any persistent connections (no-op for SQLite)."""
        pass
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
