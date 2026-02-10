#!/usr/bin/env python3
"""Debug signal scores to understand ranking."""

import sys
sys.path.insert(0, str(__file__).replace('\\', '/').rsplit('/', 2)[0])

from utils.signal_store import SignalStore

store = SignalStore()

# Get top entities
profiles = store.get_top_profiles(limit=10)

print("=" * 80)
print("TOP ENTITIES BY COMPOSITE SCORE")
print("=" * 80)

for i, p in enumerate(profiles, 1):
    print(f"\n#{i} {p.entity_name} ({p.entity_type})")
    print(f"    Composite Score: {p.composite_score:.1f}")
    
    # Get individual scores
    scores = store.get_scores_for_entity(p.entity_id)
    for s in scores:
        print(f"    - {s.category}: {s.score:.1f}")
    
    # Check signal_profiles table for more details
    conn = store._get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT technical_score, company_score, financial_score, product_score, media_score,
               technical_confidence, company_confidence, financial_confidence, product_confidence, media_confidence,
               as_of, data_freshness
        FROM signal_profiles
        WHERE entity_id = ?
    """, (p.entity_id,))
    row = c.fetchone()
    if row:
        print(f"    [Profile Details]")
        print(f"    technical={row[0]}, company={row[1]}, financial={row[2]}, product={row[3]}, media={row[4]}")
        print(f"    as_of={row[10]}")
        if row[11]:
            print(f"    freshness={row[11]}")
    conn.close()

# Now check Meta specifically
print("\n" + "=" * 80)
print("META ANALYSIS")
print("=" * 80)

conn = store._get_connection()
c = conn.cursor()

# Find Meta entity
c.execute("SELECT id, name FROM entities WHERE LOWER(name) LIKE '%meta%'")
meta = c.fetchone()
if meta:
    print(f"\nEntity: {meta['name']} (id: {meta['id']})")
    
    # Get observations
    c.execute("""
        SELECT ss.name as source, so.category, so.raw_value, so.observed_at, so.raw_data
        FROM signal_observations so
        JOIN signal_sources ss ON so.source_id = ss.id
        WHERE so.entity_id = ?
        ORDER BY so.observed_at DESC
        LIMIT 20
    """, (meta['id'],))
    
    print("\nRecent observations:")
    for row in c.fetchall():
        import json
        raw = json.loads(row['raw_data']) if row['raw_data'] else {}
        title = raw.get('title', '')[:50]
        print(f"  [{row['observed_at'][:10]}] {row['source']}: {row['raw_value']} | {title}")

conn.close()
