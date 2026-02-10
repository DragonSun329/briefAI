# -*- coding: utf-8 -*-
import sqlite3
import json

conn = sqlite3.connect('data/signals.db')
c = conn.cursor()
c.execute('''
    SELECT e.name, so.category, so.raw_value, so.raw_data 
    FROM signal_observations so 
    JOIN entities e ON so.entity_id = e.id 
    WHERE so.source_id = 'x_twitter_manual'
    ORDER BY so.observed_at DESC
''')
print("X/Twitter Signals in Database:")
print("=" * 60)
for row in c.fetchall():
    data = json.loads(row[3])
    headline = data.get("headline", "")[:50]
    print(f"{row[0]}: {row[1]} ({row[2]}) - {headline}")
