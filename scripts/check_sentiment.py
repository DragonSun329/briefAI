#!/usr/bin/env python3
"""Check current sentiment data in signals.db"""
import sqlite3
from pathlib import Path
import json

db_path = Path(__file__).parent.parent / "data" / "signals.db"
conn = sqlite3.connect(db_path)
c = conn.cursor()

# Get recent observations for META and Google specifically
print("Recent observations for META:")
print("-" * 80)
c.execute("""
    SELECT e.name, ss.name as source, so.category, so.observed_at, so.raw_value, so.raw_data
    FROM signal_observations so
    JOIN entities e ON so.entity_id = e.id
    JOIN signal_sources ss ON so.source_id = ss.id
    WHERE LOWER(e.name) LIKE '%meta%' OR LOWER(e.name) LIKE '%facebook%'
    ORDER BY so.observed_at DESC
    LIMIT 10
""")
for r in c.fetchall():
    ts = r[3][:16] if r[3] else 'N/A'
    title = ''
    if r[5]:
        try:
            data = json.loads(r[5])
            title = data.get('title', data.get('headline', ''))[:40]
        except:
            pass
    print(f"[{ts}] {r[0]:<12} | {r[1]:<18} | val={r[4]:.1f} | {title}")

print("\n\nRecent observations for GOOGLE:")
print("-" * 80)
c.execute("""
    SELECT e.name, ss.name as source, so.category, so.observed_at, so.raw_value, so.raw_data
    FROM signal_observations so
    JOIN entities e ON so.entity_id = e.id
    JOIN signal_sources ss ON so.source_id = ss.id
    WHERE LOWER(e.name) LIKE '%google%' OR LOWER(e.name) LIKE '%alphabet%'
    ORDER BY so.observed_at DESC
    LIMIT 10
""")
for r in c.fetchall():
    ts = r[3][:16] if r[3] else 'N/A'
    title = ''
    if r[5]:
        try:
            data = json.loads(r[5])
            title = data.get('title', data.get('headline', ''))[:40]
        except:
            pass
    print(f"[{ts}] {r[0]:<12} | {r[1]:<18} | val={r[4]:.1f} | {title}")

# Check signal_profiles schema and data
print("\n\nsignal_profiles schema:")
c.execute("PRAGMA table_info(signal_profiles)")
cols = [r[1] for r in c.fetchall()]
print(cols)

print("\nAll signal_profiles:")
c.execute("SELECT * FROM signal_profiles LIMIT 10")
for r in c.fetchall():
    print(r)

# Now let's see what the validator is actually reading
print("\n\nChecking realtime_validator data source...")
# Read the validator code to find where it gets sentiment
validator_path = Path(__file__).parent / "realtime_validator.py"
if validator_path.exists():
    with open(validator_path, 'r') as f:
        content = f.read()
    # Find get_briefai_sentiment method
    if 'get_briefai_sentiment' in content:
        start = content.find('def get_briefai_sentiment')
        end = content.find('\n    def ', start + 1)
        print("Validator sentiment method:")
        print(content[start:end][:800] if end > start else content[start:start+800])

conn.close()
