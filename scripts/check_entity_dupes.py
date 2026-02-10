"""Check entities table for actual name duplicates."""
import sqlite3

conn = sqlite3.connect('data/signals.db')
c = conn.cursor()

# Check for name duplicates (case-insensitive)
print("=== NAME DUPLICATES (CASE-INSENSITIVE) ===")
c.execute('''
    SELECT LOWER(name) as lname, COUNT(*) as cnt, GROUP_CONCAT(name, ' | ') as names, GROUP_CONCAT(id, ' | ') as ids
    FROM entities
    GROUP BY LOWER(name)
    HAVING cnt > 1
    ORDER BY cnt DESC
    LIMIT 20
''')
for r in c.fetchall():
    print(f"  '{r[0]}': {r[1]} entries -> [{r[2]}]")
    print(f"    IDs: {r[3]}")

# Check for canonical_id duplicates
print("\n=== CANONICAL_ID DUPLICATES ===")
c.execute('''
    SELECT canonical_id, COUNT(*) as cnt, GROUP_CONCAT(name, ' | ') as names
    FROM entities
    GROUP BY canonical_id
    HAVING cnt > 1
    ORDER BY cnt DESC
    LIMIT 20
''')
for r in c.fetchall():
    print(f"  '{r[0]}': {r[1]} entries -> [{r[2]}]")

# Check for deepseek specifically
print("\n=== DEEPSEEK ENTRIES ===")
c.execute('''
    SELECT id, canonical_id, name, entity_type
    FROM entities
    WHERE LOWER(name) LIKE '%deepseek%' OR LOWER(canonical_id) LIKE '%deepseek%'
''')
for r in c.fetchall():
    print(f"  {r[0][:12]}... | {r[1]} | {r[2]} | {r[3]}")

conn.close()
