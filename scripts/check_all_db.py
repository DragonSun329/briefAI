"""Check all databases for entity duplicates."""
import sqlite3
import os

databases = [
    'data/signals.db',
    'data/briefai.db',
    'data/trend_radar.db',
]

for db_path in databases:
    if not os.path.exists(db_path):
        continue
    print(f"\n{'='*60}")
    print(f"DATABASE: {db_path}")
    print('='*60)
    
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    # List all tables
    c.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in c.fetchall()]
    print(f"Tables: {', '.join(tables)}")
    
    # Check each table for entity-like columns
    for table in tables:
        c.execute(f"PRAGMA table_info({table})")
        cols = [r[1] for r in c.fetchall()]
        entity_cols = [col for col in cols if 'entity' in col.lower() or 'name' in col.lower()]
        
        for col in entity_cols:
            try:
                c.execute(f'''
                    SELECT LOWER({col}) as lname, COUNT(*) as cnt
                    FROM {table}
                    GROUP BY LOWER({col})
                    HAVING cnt > 1
                    LIMIT 5
                ''')
                dupes = c.fetchall()
                if dupes:
                    print(f"\n  {table}.{col} DUPLICATES:")
                    for r in dupes:
                        print(f"    {r[0]}: {r[1]} entries")
            except Exception as e:
                pass
    
    conn.close()

print("\n\nDone.")
