"""Temporary script to check database for duplicates."""
import sqlite3

conn = sqlite3.connect('data/trend_radar.db')
c = conn.cursor()

# List all tables
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
print("=== TABLES ===")
for r in c.fetchall():
    print(f"  {r[0]}")

# Check for duplicates in different tables
print("\n=== CONVICTION_SCORES ===")
c.execute('SELECT entity_name, COUNT(*) as cnt FROM conviction_scores GROUP BY entity_name HAVING cnt > 1')
for r in c.fetchall():
    print(f"  DUPLICATE: {r[0]} ({r[1]} entries)")

# Check entity_signals for duplicates
print("\n=== ENTITY_SIGNALS ===")
try:
    c.execute('SELECT entity_id, COUNT(*) as cnt FROM entity_signals GROUP BY entity_id HAVING cnt > 1 LIMIT 10')
    for r in c.fetchall():
        print(f"  DUPLICATE: {r[0]} ({r[1]} entries)")
except Exception as e:
    print(f"  Error: {e}")

# Check for case variations
print("\n=== CASE VARIATIONS IN CONVICTION_SCORES ===")
c.execute('''
    SELECT LOWER(entity_name) as lname, COUNT(*) as cnt, GROUP_CONCAT(entity_name, ' | ')
    FROM conviction_scores
    GROUP BY LOWER(entity_name)
    HAVING cnt > 1
''')
for r in c.fetchall():
    print(f"  {r[0]}: {r[1]} entries -> {r[2]}")

# Check signal_profiles for duplicates
print("\n=== SIGNAL_PROFILES ===")
try:
    c.execute('SELECT entity_id, COUNT(*) as cnt FROM signal_profiles GROUP BY entity_id HAVING cnt > 1 LIMIT 10')
    for r in c.fetchall():
        print(f"  DUPLICATE: {r[0]} ({r[1]} entries)")
except Exception as e:
    print(f"  Error: {e}")

conn.close()
print("\nDone.")
