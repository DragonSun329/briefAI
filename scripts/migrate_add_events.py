"""
Database Migration: Add Business Events Tables

Run this script to create the business_events tables in an existing briefAI database.

Usage:
    python scripts/migrate_add_events.py
"""

import sqlite3
from pathlib import Path
from datetime import datetime


def migrate_events_tables(db_path: str = None) -> None:
    """
    Create business_events tables if they don't exist.
    
    This migration is safe to run multiple times - it uses
    CREATE TABLE IF NOT EXISTS.
    """
    if db_path is None:
        db_path = str(Path(__file__).parent.parent / "data" / "business_events.db")
    
    print(f"Migrating database: {db_path}")
    
    # Ensure data directory exists
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Main events table
    print("Creating business_events table...")
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
    
    # Indexes
    print("Creating indexes...")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_entity ON business_events(entity_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON business_events(event_type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_date ON business_events(event_date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_hash ON business_events(content_hash)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_reported ON business_events(first_reported)")
    
    # Event sources table
    print("Creating event_sources table...")
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
    
    # Event links table
    print("Creating event_links table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS event_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_event_id TEXT NOT NULL,
            to_event_id TEXT NOT NULL,
            link_type TEXT NOT NULL,
            confidence REAL DEFAULT 0.5,
            created_at TEXT NOT NULL,
            FOREIGN KEY (from_event_id) REFERENCES business_events(event_id),
            FOREIGN KEY (to_event_id) REFERENCES business_events(event_id),
            UNIQUE(from_event_id, to_event_id, link_type)
        )
    """)
    
    # Migration metadata
    print("Recording migration...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS migrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            applied_at TEXT NOT NULL
        )
    """)
    
    cursor.execute("""
        INSERT OR IGNORE INTO migrations (name, applied_at)
        VALUES ('add_business_events', ?)
    """, (datetime.utcnow().isoformat(),))
    
    conn.commit()
    conn.close()
    
    print("Migration complete!")


def check_migration_status(db_path: str = None) -> bool:
    """Check if migration has been applied."""
    if db_path is None:
        db_path = str(Path(__file__).parent.parent / "data" / "business_events.db")
    
    if not Path(db_path).exists():
        return False
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT 1 FROM business_events LIMIT 1")
        return True
    except sqlite3.OperationalError:
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    import sys
    
    # Check if custom path provided
    db_path = sys.argv[1] if len(sys.argv) > 1 else None
    
    if check_migration_status(db_path):
        print("Migration already applied. Tables exist.")
    else:
        migrate_events_tables(db_path)
