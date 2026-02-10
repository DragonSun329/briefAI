"""
Signal Diagnostic Script
Analyzes why NVDA and GOOGL have low validation scores
"""

import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "signals.db"

def run_diagnostics():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    print("=" * 60)
    print("SIGNAL DIAGNOSTIC REPORT")
    print("=" * 60)

    # 1. List all entities
    print("\n=== ENTITIES ===")
    c.execute('SELECT id, canonical_id, name, entity_type FROM entities ORDER BY name')
    entities = c.fetchall()
    for row in entities:
        print(f"  {row['name']} ({row['canonical_id']}) - {row['entity_type']}")

    # 2. Signal observations stats
    print("\n=== SIGNAL OBSERVATIONS STATS ===")
    c.execute('SELECT COUNT(*) as cnt FROM signal_observations')
    print(f"  Total observations: {c.fetchone()['cnt']}")

    c.execute('SELECT category, COUNT(*) as cnt FROM signal_observations GROUP BY category ORDER BY cnt DESC')
    for row in c.fetchall():
        print(f"  {row['category']}: {row['cnt']}")

    # 3. Analyze specific entities
    target_entities = ['nvda', 'nvidia', 'googl', 'google', 'meta', 'amd', 'msft', 'microsoft']
    
    print("\n=== OBSERVATIONS BY ENTITY ===")
    c.execute('''
        SELECT entity_id, category, source_id, observed_at, raw_value, confidence, raw_data
        FROM signal_observations 
        ORDER BY observed_at DESC
    ''')
    all_obs = c.fetchall()
    
    by_entity = {}
    for obs in all_obs:
        eid = obs['entity_id']
        if eid not in by_entity:
            by_entity[eid] = []
        by_entity[eid].append(dict(obs))
    
    for eid, observations in sorted(by_entity.items()):
        print(f"\n  [{eid}] - {len(observations)} observations")
        for obs in observations[:5]:  # Show first 5
            print(f"    - {obs['category']}: {obs['raw_value']} @ {obs['observed_at'][:10]} (conf: {obs['confidence']})")
            if obs['raw_data']:
                try:
                    data = json.loads(obs['raw_data'])
                    if 'sentiment' in data:
                        print(f"      sentiment: {data['sentiment']}")
                    if 'sources' in data:
                        print(f"      sources: {len(data['sources'])} items")
                except:
                    pass

    # 4. Scores by entity
    print("\n=== LATEST SCORES BY ENTITY ===")
    c.execute('''
        SELECT s.entity_id, s.category, s.score, s.source_id, s.created_at
        FROM signal_scores s
        INNER JOIN (
            SELECT entity_id, category, MAX(created_at) as max_created
            FROM signal_scores
            GROUP BY entity_id, category
        ) latest ON s.entity_id = latest.entity_id 
               AND s.category = latest.category 
               AND s.created_at = latest.max_created
        ORDER BY s.entity_id, s.category
    ''')
    
    current_entity = None
    for row in c.fetchall():
        if row['entity_id'] != current_entity:
            current_entity = row['entity_id']
            print(f"\n  [{current_entity}]")
        print(f"    {row['category']}: {row['score']:.2f} (source: {row['source_id']}, created: {row['created_at'][:10]})")

    # 5. Signal Profiles
    print("\n=== LATEST SIGNAL PROFILES ===")
    c.execute('''
        SELECT entity_id, entity_name, composite_score, 
               technical_score, company_score, financial_score, product_score, media_score,
               momentum_7d, data_freshness, as_of
        FROM signal_profiles p1
        WHERE as_of = (
            SELECT MAX(as_of) FROM signal_profiles p2 WHERE p2.entity_id = p1.entity_id
        )
        ORDER BY composite_score DESC
    ''')
    
    for row in c.fetchall():
        print(f"\n  {row['entity_name']} ({row['entity_id']})")
        print(f"    Composite: {row['composite_score']:.2f}")
        print(f"    Technical: {row['technical_score']}, Company: {row['company_score']}")
        print(f"    Financial: {row['financial_score']}, Product: {row['product_score']}, Media: {row['media_score']}")
        print(f"    Momentum 7D: {row['momentum_7d']}")
        print(f"    As of: {row['as_of']}")
        if row['data_freshness']:
            try:
                freshness = json.loads(row['data_freshness'])
                print(f"    Freshness: {freshness}")
            except:
                pass

    # 6. Check signal freshness issues
    print("\n=== SIGNAL FRESHNESS ANALYSIS ===")
    now = datetime.utcnow()
    c.execute('SELECT entity_id, category, source_id, observed_at, data_timestamp FROM signal_observations')
    
    stale_signals = []
    for row in c.fetchall():
        obs_time = datetime.fromisoformat(row['observed_at'].replace('Z', '+00:00').replace('+00:00', ''))
        age_hours = (now - obs_time).total_seconds() / 3600
        if age_hours > 48:  # Older than 48 hours
            stale_signals.append({
                'entity': row['entity_id'],
                'category': row['category'],
                'source': row['source_id'],
                'age_hours': round(age_hours, 1)
            })
    
    if stale_signals:
        print(f"  Found {len(stale_signals)} stale signals (>48h old):")
        for s in stale_signals[:10]:
            print(f"    {s['entity']} / {s['category']}: {s['age_hours']}h old (source: {s['source']})")
    else:
        print("  No stale signals found")

    conn.close()

if __name__ == "__main__":
    run_diagnostics()
