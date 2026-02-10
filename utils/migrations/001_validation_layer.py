"""
Migration 001: Add validation layer tables and columns.

Adds:
- Citation tracing fields to signal_observations
- source_reliability table for tracking historical accuracy
- audit_log table for provenance tracking
- claim_registry table for cross-source verification
"""

import sqlite3
from datetime import datetime
from pathlib import Path


def get_db_path() -> str:
    """Get default database path."""
    return str(Path(__file__).parent.parent.parent / "data" / "signals.db")


def migrate(db_path: str = None):
    """Run migration to add validation layer schema."""
    if db_path is None:
        db_path = get_db_path()
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Track migration version
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS _migrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Check if already applied
    cursor.execute("SELECT 1 FROM _migrations WHERE name = '001_validation_layer'")
    if cursor.fetchone():
        print("Migration 001_validation_layer already applied")
        conn.close()
        return False
    
    print("Applying migration 001_validation_layer...")
    
    # =========================================================================
    # 1. Add citation tracing fields to signal_observations
    # =========================================================================
    
    # Check which columns exist
    cursor.execute("PRAGMA table_info(signal_observations)")
    existing_cols = {row[1] for row in cursor.fetchall()}
    
    new_cols = [
        ("first_reported_by", "TEXT"),          # Source ID that first reported this claim
        ("first_reported_at", "TIMESTAMP"),     # When first reported
        ("confirmed_by", "TEXT"),               # JSON array of source IDs that confirmed
        ("claim_hash", "TEXT"),                 # Hash of the normalized claim for dedup
        ("validation_status", "TEXT DEFAULT 'pending'"),  # pending/validated/conflict/rejected
        ("validation_score", "REAL"),           # 0-1 cross-source validation score
        ("conflict_details", "TEXT"),           # JSON with conflicting claims if any
    ]
    
    for col_name, col_type in new_cols:
        if col_name not in existing_cols:
            cursor.execute(f"ALTER TABLE signal_observations ADD COLUMN {col_name} {col_type}")
            print(f"  Added column: signal_observations.{col_name}")
    
    # Create index for claim lookups
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_observations_claim_hash ON signal_observations(claim_hash)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_observations_validation ON signal_observations(validation_status)")
    
    # =========================================================================
    # 2. Source reliability tracking table
    # =========================================================================
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS source_reliability (
            id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL UNIQUE,
            
            -- Overall reliability metrics
            reliability_score REAL DEFAULT 0.7,      -- Dynamic reliability (0-1)
            base_reliability REAL DEFAULT 0.7,       -- Initial/configured reliability
            total_claims INTEGER DEFAULT 0,          -- Total claims from this source
            verified_claims INTEGER DEFAULT 0,       -- Claims confirmed by other sources
            contradicted_claims INTEGER DEFAULT 0,   -- Claims contradicted by other sources
            
            -- Accuracy by category
            accuracy_by_category TEXT,               -- JSON: {"funding": 0.95, "valuation": 0.8}
            
            -- Temporal metrics
            avg_reporting_delay_hours REAL,          -- How late is this source typically?
            first_to_report_count INTEGER DEFAULT 0, -- Times this source was first
            
            -- Reliability decay tracking
            last_verified_at TIMESTAMP,              -- Last time a claim was verified
            reliability_decay_applied_at TIMESTAMP,  -- Last decay calculation
            
            -- Historical snapshots
            reliability_history TEXT,                -- JSON array of {date, score}
            
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_source_reliability_score ON source_reliability(reliability_score)")
    print("  Created table: source_reliability")
    
    # =========================================================================
    # 3. Audit log for provenance tracking
    # =========================================================================
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id TEXT PRIMARY KEY,
            
            -- What changed
            table_name TEXT NOT NULL,               -- Table that was modified
            record_id TEXT NOT NULL,                -- ID of the modified record
            operation TEXT NOT NULL,                -- INSERT, UPDATE, DELETE
            
            -- Who/what made the change
            source_id TEXT,                         -- Source that triggered change (if applicable)
            actor TEXT DEFAULT 'system',            -- system, pipeline:xyz, manual:user
            
            -- Change details
            field_name TEXT,                        -- Specific field that changed (for UPDATE)
            old_value TEXT,                         -- Previous value (JSON for complex types)
            new_value TEXT,                         -- New value
            
            -- Context
            change_reason TEXT,                     -- Why the change was made
            related_observation_id TEXT,            -- Link to observation that triggered change
            
            -- Timestamps
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            
            -- For querying
            entity_id TEXT                          -- Denormalized for faster entity history queries
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_record ON audit_log(table_name, record_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_entity ON audit_log(entity_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp ON audit_log(timestamp)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_source ON audit_log(source_id)")
    print("  Created table: audit_log")
    
    # =========================================================================
    # 4. Claim registry for cross-source verification
    # =========================================================================
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS claim_registry (
            id TEXT PRIMARY KEY,
            
            -- Claim identification
            claim_hash TEXT NOT NULL UNIQUE,        -- Normalized hash for deduplication
            claim_type TEXT NOT NULL,               -- funding_amount, valuation, employee_count, etc.
            entity_id TEXT NOT NULL,                -- Which entity this claim is about
            
            -- Claim value
            claim_value TEXT NOT NULL,              -- Normalized value (JSON for complex)
            claim_value_numeric REAL,               -- Numeric value if applicable (for comparison)
            claim_unit TEXT,                        -- usd, employees, percent, etc.
            claim_date TEXT,                        -- Date the claim refers to (e.g., "2024-Q4")
            
            -- Source tracking
            first_source_id TEXT NOT NULL,          -- Who reported first
            first_observed_at TIMESTAMP NOT NULL,   -- When first seen
            confirming_sources TEXT,                -- JSON array of {source_id, observed_at, confidence}
            conflicting_sources TEXT,               -- JSON array of {source_id, value, observed_at}
            
            -- Validation status
            source_count INTEGER DEFAULT 1,         -- Number of sources reporting this
            agreement_score REAL,                   -- How much sources agree (0-1)
            validation_status TEXT DEFAULT 'single_source',  -- single_source, corroborated, conflict
            requires_review INTEGER DEFAULT 0,      -- Flag for manual review
            
            -- Computed confidence
            confidence_score REAL,                  -- Weighted by source reliability
            
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_claim_registry_entity ON claim_registry(entity_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_claim_registry_type ON claim_registry(claim_type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_claim_registry_status ON claim_registry(validation_status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_claim_registry_hash ON claim_registry(claim_hash)")
    print("  Created table: claim_registry")
    
    # =========================================================================
    # 5. Record migration
    # =========================================================================
    
    cursor.execute(
        "INSERT INTO _migrations (name, applied_at) VALUES (?, ?)",
        ("001_validation_layer", datetime.utcnow().isoformat())
    )
    
    conn.commit()
    conn.close()
    
    print("Migration 001_validation_layer completed successfully")
    return True


def rollback(db_path: str = None):
    """Rollback migration (for testing)."""
    if db_path is None:
        db_path = get_db_path()
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Drop new tables
    cursor.execute("DROP TABLE IF EXISTS source_reliability")
    cursor.execute("DROP TABLE IF EXISTS audit_log")
    cursor.execute("DROP TABLE IF EXISTS claim_registry")
    
    # Remove migration record
    cursor.execute("DELETE FROM _migrations WHERE name = '001_validation_layer'")
    
    conn.commit()
    conn.close()
    
    print("Rollback 001_validation_layer completed")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        rollback()
    else:
        migrate()
