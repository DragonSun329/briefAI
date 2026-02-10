"""Check which entities have media observations."""
import sqlite3
conn = sqlite3.connect('data/signals.db')
cur = conn.cursor()

# Find entities with 'media' category observations
print('Entities with media observations (last 7 days):')
cur.execute("""
    SELECT e.id, e.name, COUNT(*) as cnt, AVG(so.raw_value) as avg_sent
    FROM signal_observations so
    JOIN entities e ON so.entity_id = e.id
    WHERE so.category = 'media'
      AND so.raw_value >= 0 AND so.raw_value <= 10
      AND so.observed_at > datetime('now', '-7 days')
    GROUP BY e.id, e.name
    ORDER BY cnt DESC
    LIMIT 25
""")
for row in cur.fetchall():
    print(f'  {row[1]:35} | n={row[2]:3} | avg={row[3]:.2f} | {row[0][:8]}...')

print('\n' + '='*60)
print('Checking scraper-created entities vs canonical:')

# Check if there are duplicate entities
for name in ['Meta', 'Microsoft', 'Google', 'AMD', 'NVIDIA', 'Amazon', 'Apple', 'Tesla']:
    cur.execute("SELECT id, name FROM entities WHERE LOWER(name) LIKE ?", (f'%{name.lower()}%',))
    rows = cur.fetchall()
    if len(rows) > 1:
        print(f'\n{name} - MULTIPLE ENTITIES:')
        for r in rows:
            # Count observations for this entity
            cur.execute("SELECT COUNT(*) FROM signal_observations WHERE entity_id = ?", (r[0],))
            obs_cnt = cur.fetchone()[0]
            print(f'  {r[1]:35} | {r[0][:8]}... | {obs_cnt} observations')

conn.close()
