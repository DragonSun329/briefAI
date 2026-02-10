# -*- coding: utf-8 -*-
"""
Signal Deduplication Module

Prevents the same news event from being counted multiple times across
different sources or observation timestamps.

Strategies:
1. Event fingerprinting - hash of (entity, event_type, date)
2. Headline similarity - fuzzy match on headlines
3. Time window - observations within 24h window are merged
"""

import hashlib
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from collections import defaultdict
import sqlite3
from pathlib import Path

try:
    from rapidfuzz import fuzz
    FUZZY_AVAILABLE = True
except ImportError:
    FUZZY_AVAILABLE = False


@dataclass
class SignalFingerprint:
    """Fingerprint for deduplication."""
    entity_id: str
    event_type: str
    event_date: str  # YYYY-MM-DD
    headline_hash: str
    full_hash: str


class SignalDeduplicator:
    """Deduplicates signals to prevent double-counting news events."""
    
    HEADLINE_SIMILARITY_THRESHOLD = 0.85  # 85% = very similar headlines
    TIME_WINDOW_HOURS = 24  # Observations within 24h are candidates for merge
    
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = str(Path(__file__).parent.parent / "data" / "signals.db")
        self.db_path = db_path
        self._ensure_dedup_table()
    
    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _ensure_dedup_table(self):
        """Create deduplication tracking table."""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS signal_fingerprints (
                id TEXT PRIMARY KEY,
                entity_id TEXT NOT NULL,
                event_type TEXT,
                event_date TEXT,
                headline TEXT,
                headline_hash TEXT,
                full_hash TEXT UNIQUE,
                first_observation_id TEXT,
                observation_count INTEGER DEFAULT 1,
                sources TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_fp_entity ON signal_fingerprints(entity_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_fp_hash ON signal_fingerprints(full_hash)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_fp_date ON signal_fingerprints(event_date)")
        
        # Add headline column if missing (for existing tables)
        try:
            cursor.execute("ALTER TABLE signal_fingerprints ADD COLUMN headline TEXT")
        except:
            pass  # Column already exists
        
        conn.commit()
        conn.close()
    
    def compute_fingerprint(
        self,
        entity_id: str,
        raw_data: Dict[str, Any],
        observed_at: datetime
    ) -> SignalFingerprint:
        """Compute fingerprint for a signal observation."""
        
        # Extract key fields
        headline = raw_data.get("headline", "")
        event_type = raw_data.get("signal_type") or raw_data.get("event_type", "unknown")
        event_date = observed_at.strftime("%Y-%m-%d")
        
        # Normalize headline for hashing
        headline_normalized = headline.lower().strip()
        headline_hash = hashlib.md5(headline_normalized.encode()).hexdigest()[:16]
        
        # Full hash includes entity + date + headline
        full_content = f"{entity_id}|{event_date}|{headline_normalized}"
        full_hash = hashlib.sha256(full_content.encode()).hexdigest()[:32]
        
        return SignalFingerprint(
            entity_id=entity_id,
            event_type=event_type,
            event_date=event_date,
            headline_hash=headline_hash,
            full_hash=full_hash,
        )
    
    def is_duplicate(
        self,
        entity_id: str,
        raw_data: Dict[str, Any],
        observed_at: datetime,
        source_id: str = "unknown"
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if observation is a duplicate of existing signal.
        
        Returns:
            (is_duplicate, existing_fingerprint_id)
        """
        fp = self.compute_fingerprint(entity_id, raw_data, observed_at)
        
        conn = self._get_conn()
        cursor = conn.cursor()
        
        # Check 1: Exact hash match
        cursor.execute(
            "SELECT id, sources FROM signal_fingerprints WHERE full_hash = ?",
            (fp.full_hash,)
        )
        row = cursor.fetchone()
        if row:
            # Update observation count and sources
            existing_sources = json.loads(row["sources"]) if row["sources"] else []
            if source_id not in existing_sources:
                existing_sources.append(source_id)
                cursor.execute(
                    """UPDATE signal_fingerprints 
                       SET observation_count = observation_count + 1,
                           sources = ?,
                           updated_at = CURRENT_TIMESTAMP
                       WHERE id = ?""",
                    (json.dumps(existing_sources), row["id"])
                )
                conn.commit()
            conn.close()
            return (True, row["id"])
        
        # Check 2: Fuzzy headline match within time window
        if FUZZY_AVAILABLE:
            headline = raw_data.get("headline", "")
            if headline:
                window_start = (observed_at - timedelta(hours=self.TIME_WINDOW_HOURS)).strftime("%Y-%m-%d")
                window_end = (observed_at + timedelta(hours=self.TIME_WINDOW_HOURS)).strftime("%Y-%m-%d")
                
                cursor.execute(
                    """SELECT id, headline FROM signal_fingerprints 
                       WHERE entity_id = ? AND event_date BETWEEN ? AND ?""",
                    (entity_id, window_start, window_end)
                )
                
                for existing in cursor.fetchall():
                    existing_headline = existing["headline"] or ""
                    
                    if existing_headline:
                        similarity = fuzz.ratio(headline.lower(), existing_headline.lower()) / 100.0
                        if similarity >= self.HEADLINE_SIMILARITY_THRESHOLD:
                            # Update observation count
                            cursor.execute(
                                """UPDATE signal_fingerprints 
                                   SET observation_count = observation_count + 1,
                                       updated_at = CURRENT_TIMESTAMP
                                   WHERE id = ?""",
                                (existing["id"],)
                            )
                            conn.commit()
                            conn.close()
                            return (True, existing["id"])
        
        conn.close()
        return (False, None)
    
    def register_signal(
        self,
        observation_id: str,
        entity_id: str,
        raw_data: Dict[str, Any],
        observed_at: datetime,
        source_id: str = "unknown"
    ) -> str:
        """Register a new signal fingerprint."""
        
        fp = self.compute_fingerprint(entity_id, raw_data, observed_at)
        headline = raw_data.get("headline", "")
        
        conn = self._get_conn()
        cursor = conn.cursor()
        
        import uuid
        fp_id = str(uuid.uuid4())
        
        cursor.execute(
            """INSERT OR IGNORE INTO signal_fingerprints 
               (id, entity_id, event_type, event_date, headline, headline_hash, full_hash, 
                first_observation_id, sources)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (fp_id, fp.entity_id, fp.event_type, fp.event_date, headline,
             fp.headline_hash, fp.full_hash, observation_id, json.dumps([source_id]))
        )
        
        conn.commit()
        conn.close()
        
        return fp_id
    
    def get_dedup_stats(self) -> Dict[str, Any]:
        """Get deduplication statistics."""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM signal_fingerprints")
        total_fingerprints = cursor.fetchone()[0]
        
        cursor.execute("SELECT SUM(observation_count) FROM signal_fingerprints")
        total_observations = cursor.fetchone()[0] or 0
        
        cursor.execute(
            "SELECT COUNT(*) FROM signal_fingerprints WHERE observation_count > 1"
        )
        duplicated_events = cursor.fetchone()[0]
        
        cursor.execute(
            "SELECT SUM(observation_count - 1) FROM signal_fingerprints WHERE observation_count > 1"
        )
        blocked_duplicates = cursor.fetchone()[0] or 0
        
        conn.close()
        
        return {
            "unique_events": total_fingerprints,
            "total_observations": total_observations,
            "duplicated_events": duplicated_events,
            "blocked_duplicates": blocked_duplicates,
            "dedup_ratio": blocked_duplicates / max(total_observations, 1),
        }


def deduplicate_existing_signals():
    """Run deduplication on existing signals in database."""
    from utils.signal_store import SignalStore
    
    store = SignalStore()
    dedup = SignalDeduplicator()
    
    conn = sqlite3.connect(store.db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get all observations
    cursor.execute("""
        SELECT id, entity_id, source_id, observed_at, raw_data 
        FROM signal_observations 
        ORDER BY observed_at ASC
    """)
    
    duplicates_found = 0
    unique_signals = 0
    
    for row in cursor.fetchall():
        raw_data = json.loads(row["raw_data"]) if row["raw_data"] else {}
        observed_at = datetime.fromisoformat(row["observed_at"])
        
        is_dup, existing_id = dedup.is_duplicate(
            row["entity_id"], raw_data, observed_at, row["source_id"]
        )
        
        if is_dup:
            duplicates_found += 1
        else:
            dedup.register_signal(
                row["id"], row["entity_id"], raw_data, observed_at, row["source_id"]
            )
            unique_signals += 1
    
    conn.close()
    
    print(f"Deduplication complete:")
    print(f"  Unique signals: {unique_signals}")
    print(f"  Duplicates found: {duplicates_found}")
    
    stats = dedup.get_dedup_stats()
    print(f"  Dedup ratio: {stats['dedup_ratio']:.1%}")
    
    return stats


if __name__ == "__main__":
    deduplicate_existing_signals()
