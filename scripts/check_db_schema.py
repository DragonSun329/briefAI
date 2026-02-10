"""Quick DB schema and data check."""
import sqlite3
from datetime import datetime, timedelta

def fmt(v, decimals=1):
    """Format value or return N/A if None."""
    if v is None:
        return "N/A"
    return f"{v:.{decimals}f}"

conn = sqlite3.connect('data/signals.db')
cur = conn.cursor()

print("="*60)
print("KEY ENTITIES - SIGNAL PROFILES")
print("="*60)

entities = ['nvidia', 'meta', 'microsoft', 'google', 'amd', 'openai', 'anthropic']

for entity in entities:
    cur.execute("""
        SELECT p.entity_id, p.entity_name, p.technical_score, p.financial_score, 
               p.media_score, p.composite_score, p.momentum_7d, p.as_of
        FROM signal_profiles p
        WHERE LOWER(p.entity_name) LIKE ?
        ORDER BY p.as_of DESC
        LIMIT 1
    """, (f'%{entity}%',))
    row = cur.fetchone()
    if row:
        print(f"\n{entity.upper()}: id={row[0][:8]}..., name={row[1]}")
        print(f"  tech={fmt(row[2])}, fin={fmt(row[3])}, media={fmt(row[4])}, composite={fmt(row[5])}")
        print(f"  momentum_7d={row[6]}, as_of={row[7][:16] if row[7] else 'N/A'}")
    else:
        print(f"\n{entity.upper()}: (no profile)")

print("\n" + "="*60)
print("RECENT OBSERVATIONS BY SOURCE")
print("="*60)

cur.execute("""
    SELECT source_id, COUNT(*) as cnt, MAX(observed_at) as latest
    FROM signal_observations
    GROUP BY source_id
    ORDER BY latest DESC
    LIMIT 15
""")
for row in cur.fetchall():
    print(f"  {row[0]:25} | n={row[1]:4} | last={row[2][:16] if row[2] else 'N/A'}")

print("\n" + "="*60)
print("FRESHNESS CHECK - OBSERVATIONS < 7 DAYS OLD")
print("="*60)

cur.execute("""
    SELECT COUNT(*) FROM signal_observations 
    WHERE observed_at > datetime('now', '-7 days')
""")
recent = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM signal_observations")
total = cur.fetchone()[0]
print(f"  Recent (<7 days): {recent}/{total} observations ({100*recent/total:.1f}%)")

print("\n" + "="*60)
print("SAMPLE OBSERVATIONS FOR NVIDIA")
print("="*60)

# Get nvidia entity id
cur.execute("SELECT id FROM entities WHERE LOWER(name) LIKE '%nvidia%' LIMIT 1")
nvidia_id = cur.fetchone()
if nvidia_id:
    nvidia_id = nvidia_id[0]
    cur.execute("""
        SELECT source_id, category, raw_value, confidence, observed_at
        FROM signal_observations
        WHERE entity_id = ?
        ORDER BY observed_at DESC
        LIMIT 10
    """, (nvidia_id,))
    for row in cur.fetchall():
        rv = str(row[2])[:25] if row[2] else 'N/A'
        conf = fmt(row[3], 2) if row[3] else 'N/A'
        print(f"  {row[0]:20} | cat={row[1]:15} | val={rv:25} | conf={conf} | {row[4][:16] if row[4] else 'N/A'}")
else:
    print("  NVIDIA entity not found")

conn.close()
