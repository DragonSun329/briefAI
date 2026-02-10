"""Cleanup orphan companies with no observations."""
import sqlite3
from pathlib import Path
from datetime import datetime

DATA_DIR = Path(__file__).parent.parent / "data"

def cleanup_orphan_companies():
    """Remove companies that have no observations."""
    conn = sqlite3.connect(DATA_DIR / "trend_radar.db")
    cursor = conn.cursor()
    
    # Find orphans
    cursor.execute("""
        SELECT c.id, c.name FROM companies c 
        LEFT JOIN observations o ON c.id = o.company_id 
        WHERE o.id IS NULL
    """)
    orphans = cursor.fetchall()
    
    print(f"Found {len(orphans)} orphan companies")
    
    if orphans:
        # Delete them
        orphan_ids = [o[0] for o in orphans]
        cursor.execute(f"""
            DELETE FROM companies WHERE id IN ({','.join('?' * len(orphan_ids))})
        """, orphan_ids)
        conn.commit()
        print(f"Deleted {cursor.rowcount} orphan companies")
        
        # Show some examples
        print("\nDeleted examples:")
        for name in [o[1] for o in orphans[:5]]:
            print(f"  - {name}")
    
    conn.close()

def cleanup_duplicate_convictions():
    """Remove duplicate conviction scores, keeping highest."""
    conn = sqlite3.connect(DATA_DIR / "trend_radar.db")
    cursor = conn.cursor()
    
    # Find duplicates
    cursor.execute("""
        SELECT entity_name, COUNT(*) as cnt 
        FROM conviction_scores 
        GROUP BY entity_name 
        HAVING cnt > 1
    """)
    duplicates = cursor.fetchall()
    
    print(f"\nFound {len(duplicates)} entities with duplicate conviction scores")
    
    for entity_name, count in duplicates:
        # Keep the one with highest conviction_score, delete others
        cursor.execute("""
            DELETE FROM conviction_scores 
            WHERE entity_name = ? 
            AND id NOT IN (
                SELECT id FROM conviction_scores 
                WHERE entity_name = ? 
                ORDER BY conviction_score DESC 
                LIMIT 1
            )
        """, (entity_name, entity_name))
        print(f"  Cleaned up {entity_name}: removed {cursor.rowcount} duplicates")
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    print(f"Cleanup started at {datetime.now().isoformat()}")
    cleanup_orphan_companies()
    cleanup_duplicate_convictions()
    print("\nCleanup complete!")
