import sqlite3
conn = sqlite3.connect('data/predictions.db')

# Schema
for row in conn.execute("SELECT sql FROM sqlite_master WHERE type='table'").fetchall():
    print(row[0])
    print()

# Count distinct confidences
print("Distinct confidence values:")
for row in conn.execute("SELECT DISTINCT confidence FROM predictions ORDER BY confidence DESC").fetchall():
    print(f"  {row[0]}")

# Total count
print(f"\nTotal predictions: {conn.execute('SELECT COUNT(*) FROM predictions').fetchone()[0]}")
print(f"Pending: {conn.execute('SELECT COUNT(*) FROM predictions WHERE status=?', ('pending',)).fetchone()[0]}")
