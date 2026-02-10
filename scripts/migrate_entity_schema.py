#!/usr/bin/env python3
"""
Entity Schema Migration

Adds new tables and columns for Bloomberg-grade entity resolution:
- entity_external_ids: External identifiers (Crunchbase, ticker, LEI, Wikidata)
- entity_aliases: Alias mappings with confidence scores
- entity_relationships: Parent/subsidiary and other relationships
- entity_merge_audit: Deduplication audit trail
- entity_resolution_overrides: Manual override mappings
- entity_resolution_log: Resolution decision logging

This is idempotent - safe to run multiple times.

Usage:
    python scripts/migrate_entity_schema.py
    python scripts/migrate_entity_schema.py --db-path custom/path/signals.db
"""

import argparse
import logging
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def get_default_db_path() -> str:
    """Get default database path."""
    return str(Path(__file__).parent.parent / "data" / "signals.db")


def table_exists(cursor: sqlite3.Cursor, table_name: str) -> bool:
    """Check if a table exists."""
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    )
    return cursor.fetchone() is not None


def column_exists(cursor: sqlite3.Cursor, table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table."""
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]
    return column_name in columns


def run_migration(db_path: str) -> dict:
    """
    Run all schema migrations.

    Returns dict with migration results.
    """
    logger.info(f"Running migrations on {db_path}")

    results = {
        "tables_created": [],
        "indices_created": [],
        "columns_added": [],
        "already_exists": [],
    }

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # =====================================================================
        # Table: entity_external_ids
        # =====================================================================
        if not table_exists(cursor, "entity_external_ids"):
            logger.info("Creating table: entity_external_ids")
            cursor.execute("""
                CREATE TABLE entity_external_ids (
                    entity_id TEXT PRIMARY KEY,
                    crunchbase_uuid TEXT,
                    crunchbase_permalink TEXT,
                    ticker_symbol TEXT,
                    exchange TEXT,
                    lei_code TEXT,
                    wikidata_id TEXT,
                    linkedin_id TEXT,
                    domain TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (entity_id) REFERENCES entities(id)
                )
            """)
            results["tables_created"].append("entity_external_ids")

            # Create indices
            indices = [
                ("idx_ext_crunchbase", "entity_external_ids(crunchbase_uuid)"),
                ("idx_ext_ticker", "entity_external_ids(ticker_symbol)"),
                ("idx_ext_lei", "entity_external_ids(lei_code)"),
                ("idx_ext_wikidata", "entity_external_ids(wikidata_id)"),
                ("idx_ext_domain", "entity_external_ids(domain)"),
            ]
            for idx_name, idx_def in indices:
                cursor.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {idx_def}")
                results["indices_created"].append(idx_name)
        else:
            results["already_exists"].append("entity_external_ids")

        # =====================================================================
        # Table: entity_aliases
        # =====================================================================
        if not table_exists(cursor, "entity_aliases"):
            logger.info("Creating table: entity_aliases")
            cursor.execute("""
                CREATE TABLE entity_aliases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    alias TEXT NOT NULL,
                    normalized_alias TEXT NOT NULL,
                    canonical_id TEXT NOT NULL,
                    confidence REAL DEFAULT 1.0,
                    source TEXT DEFAULT 'manual',
                    verified INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(normalized_alias, canonical_id)
                )
            """)
            results["tables_created"].append("entity_aliases")

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_alias_normalized ON entity_aliases(normalized_alias)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_alias_canonical ON entity_aliases(canonical_id)")
            results["indices_created"].extend(["idx_alias_normalized", "idx_alias_canonical"])
        else:
            results["already_exists"].append("entity_aliases")

        # =====================================================================
        # Table: entity_relationships
        # =====================================================================
        if not table_exists(cursor, "entity_relationships"):
            logger.info("Creating table: entity_relationships")
            cursor.execute("""
                CREATE TABLE entity_relationships (
                    id TEXT PRIMARY KEY,
                    source_entity_id TEXT NOT NULL,
                    target_entity_id TEXT NOT NULL,
                    relationship_type TEXT NOT NULL,
                    effective_date TIMESTAMP,
                    end_date TIMESTAMP,
                    metadata TEXT,
                    confidence REAL DEFAULT 1.0,
                    source TEXT DEFAULT 'manual',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (source_entity_id) REFERENCES entities(id),
                    FOREIGN KEY (target_entity_id) REFERENCES entities(id)
                )
            """)
            results["tables_created"].append("entity_relationships")

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_rel_source ON entity_relationships(source_entity_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_rel_target ON entity_relationships(target_entity_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_rel_type ON entity_relationships(relationship_type)")
            results["indices_created"].extend(["idx_rel_source", "idx_rel_target", "idx_rel_type"])
        else:
            results["already_exists"].append("entity_relationships")

        # =====================================================================
        # Table: entity_merge_audit
        # =====================================================================
        if not table_exists(cursor, "entity_merge_audit"):
            logger.info("Creating table: entity_merge_audit")
            cursor.execute("""
                CREATE TABLE entity_merge_audit (
                    id TEXT PRIMARY KEY,
                    merged_entity_id TEXT NOT NULL,
                    surviving_entity_id TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    confidence REAL,
                    reason TEXT,
                    merged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    merged_by TEXT DEFAULT 'system',
                    old_data_snapshot TEXT
                )
            """)
            results["tables_created"].append("entity_merge_audit")

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_merge_merged ON entity_merge_audit(merged_entity_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_merge_surviving ON entity_merge_audit(surviving_entity_id)")
            results["indices_created"].extend(["idx_merge_merged", "idx_merge_surviving"])
        else:
            results["already_exists"].append("entity_merge_audit")

        # =====================================================================
        # Table: entity_resolution_overrides
        # =====================================================================
        if not table_exists(cursor, "entity_resolution_overrides"):
            logger.info("Creating table: entity_resolution_overrides")
            cursor.execute("""
                CREATE TABLE entity_resolution_overrides (
                    alias TEXT PRIMARY KEY,
                    canonical_id TEXT NOT NULL,
                    reason TEXT,
                    created_by TEXT DEFAULT 'system',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            results["tables_created"].append("entity_resolution_overrides")
        else:
            results["already_exists"].append("entity_resolution_overrides")

        # =====================================================================
        # Table: entity_resolution_log
        # =====================================================================
        if not table_exists(cursor, "entity_resolution_log"):
            logger.info("Creating table: entity_resolution_log")
            cursor.execute("""
                CREATE TABLE entity_resolution_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    input_name TEXT NOT NULL,
                    resolved_to TEXT,
                    decision TEXT NOT NULL,
                    confidence REAL,
                    source TEXT,
                    context TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            results["tables_created"].append("entity_resolution_log")

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_reslog_input ON entity_resolution_log(input_name)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_reslog_resolved ON entity_resolution_log(resolved_to)")
            results["indices_created"].extend(["idx_reslog_input", "idx_reslog_resolved"])
        else:
            results["already_exists"].append("entity_resolution_log")

        # =====================================================================
        # Migrate existing aliases from entities table
        # =====================================================================
        logger.info("Checking for aliases to migrate from entities table...")

        cursor.execute("SELECT id, canonical_id, aliases FROM entities WHERE aliases IS NOT NULL AND aliases != '[]'")
        rows = cursor.fetchall()

        migrated_aliases = 0
        for entity_id, canonical_id, aliases_json in rows:
            try:
                import json
                aliases = json.loads(aliases_json) if aliases_json else []
                for alias in aliases:
                    if alias:
                        normalized = alias.lower().strip()
                        cursor.execute("""
                            INSERT OR IGNORE INTO entity_aliases
                            (alias, normalized_alias, canonical_id, confidence, source, verified)
                            VALUES (?, ?, ?, 1.0, 'migration', 1)
                        """, (alias, normalized, canonical_id))
                        if cursor.rowcount > 0:
                            migrated_aliases += 1
            except Exception as e:
                logger.warning(f"Failed to migrate aliases for {entity_id}: {e}")

        if migrated_aliases > 0:
            logger.info(f"Migrated {migrated_aliases} aliases from entities table")

        # Commit all changes
        conn.commit()
        logger.info("Migration complete!")

    except Exception as e:
        conn.rollback()
        logger.error(f"Migration failed: {e}")
        raise

    finally:
        conn.close()

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Run entity schema migrations"
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=get_default_db_path(),
        help="Path to SQLite database",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )

    args = parser.parse_args()

    if args.dry_run:
        logger.info(f"[DRY RUN] Would run migrations on {args.db_path}")
        return

    results = run_migration(args.db_path)

    # Print summary
    print("\n" + "="*60)
    print("Migration Summary")
    print("="*60)
    print(f"  Tables created: {len(results['tables_created'])}")
    for t in results["tables_created"]:
        print(f"    - {t}")
    print(f"  Indices created: {len(results['indices_created'])}")
    print(f"  Already existed: {len(results['already_exists'])}")
    for t in results["already_exists"]:
        print(f"    - {t}")


if __name__ == "__main__":
    main()
