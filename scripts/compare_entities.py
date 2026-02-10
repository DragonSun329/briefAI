#!/usr/bin/env python3
"""Compare scoring for different entities to understand bias."""

import sqlite3
from pathlib import Path

db = Path(__file__).parent.parent / "data" / "signals.db"
conn = sqlite3.connect(db)
c = conn.cursor()

entities_to_check = [
    "google", "alphabet", "deepmind",  # Google
    "openai",  # OpenAI
    "anthropic",  # Anthropic
    "meta",  # Meta
    "nvidia",  # NVIDIA
    "microsoft",  # Microsoft
]

print("=" * 90)
print(f"{'Entity':<20} {'Tech':>8} {'Company':>8} {'Media':>8} {'Composite':>10} {'Obs#':>6} {'Latest Obs':<12}")
print("=" * 90)

for search in entities_to_check:
    c.execute(
        "SELECT id, name FROM entities WHERE LOWER(name) LIKE ?",
        (f"%{search}%",)
    )
    rows = c.fetchall()
    
    for eid, name in rows[:1]:  # Take first match
        # Get profile
        c.execute("""
            SELECT technical_score, company_score, media_score, composite_score
            FROM signal_profiles WHERE entity_id = ?
        """, (eid,))
        p = c.fetchone()
        
        # Get observation count
        c.execute("""
            SELECT COUNT(*), MAX(observed_at)
            FROM signal_observations WHERE entity_id = ?
        """, (eid,))
        obs = c.fetchone()
        
        tech = f"{p[0]:.1f}" if p and p[0] else "None"
        company = f"{p[1]:.1f}" if p and p[1] else "None"
        media = f"{p[2]:.1f}" if p and p[2] else "None"
        composite = f"{p[3]:.1f}" if p and p[3] else "None"
        obs_count = obs[0] if obs else 0
        obs_latest = obs[1][:10] if obs and obs[1] else "None"
        
        print(f"{name:<20} {tech:>8} {company:>8} {media:>8} {composite:>10} {obs_count:>6} {obs_latest:<12}")

print("\n" + "=" * 90)
print("ANALYSIS: Why current scoring is broken")
print("=" * 90)

# Check what technical_score is based on
print("\n1. Technical Score Sources:")
c.execute("""
    SELECT ss.name, COUNT(*) as cnt
    FROM signal_observations so
    JOIN signal_sources ss ON so.source_id = ss.id
    WHERE so.category = 'technical'
    GROUP BY ss.name
    ORDER BY cnt DESC
    LIMIT 10
""")
for row in c.fetchall():
    print(f"   {row[0]}: {row[1]} observations")

print("\n2. Media Score Sources:")
c.execute("""
    SELECT ss.name, COUNT(*) as cnt
    FROM signal_observations so
    JOIN signal_sources ss ON so.source_id = ss.id
    WHERE so.category = 'media'
    GROUP BY ss.name
    ORDER BY cnt DESC
    LIMIT 10
""")
for row in c.fetchall():
    print(f"   {row[0]}: {row[1]} observations")

print("\n3. Recent Google/Gemini news (should be reflected!):")
c.execute("""
    SELECT e.name, ss.name as source, so.raw_value, so.observed_at
    FROM signal_observations so
    JOIN entities e ON so.entity_id = e.id
    JOIN signal_sources ss ON so.source_id = ss.id
    WHERE (LOWER(e.name) LIKE '%google%' OR LOWER(e.name) LIKE '%gemini%')
    ORDER BY so.observed_at DESC
    LIMIT 10
""")
for row in c.fetchall():
    print(f"   [{row[3][:10]}] {row[0]} via {row[1]}: sentiment={row[2]}")

conn.close()
