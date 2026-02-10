"""Check recent observations in database."""
import sqlite3
from datetime import datetime
conn = sqlite3.connect('data/signals.db')
cur = conn.cursor()

# Check recent observations from today
cur.execute("""
    SELECT source_id, COUNT(*), MAX(observed_at) as latest
    FROM signal_observations
    WHERE observed_at > datetime('now', '-1 day')
    GROUP BY source_id
    ORDER BY latest DESC
""")

print('Observations from last 24h:')
for row in cur.fetchall():
    latest = row[2][:16] if row[2] else 'N/A'
    print(f'  {row[0]:30} | n={row[1]:4} | latest={latest}')

# Check today specifically
cur.execute("""
    SELECT COUNT(*) FROM signal_observations
    WHERE date(observed_at) = date('now')
""")
today_count = cur.fetchone()[0]
print(f'\nTotal today: {today_count}')

conn.close()
