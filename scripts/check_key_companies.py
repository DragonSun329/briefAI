#!/usr/bin/env python3
"""Check scoring breakdown for key companies."""

import sys
sys.path.insert(0, str(__file__).replace('\\', '/').rsplit('/', 2)[0])

from scripts.rebuild_profiles_v2 import *

conn = get_db()

# Check specific companies
targets = ['OpenAI', 'Google/Alphabet', 'Microsoft', 'Meta', 'NVIDIA', 'AMD', 'Anthropic', 'Google DeepMind']

print('Detailed breakdown for key companies:')
print('=' * 100)

for name in targets:
    c = conn.cursor()
    c.execute("SELECT id, name FROM entities WHERE name LIKE ?", (f'%{name}%',))
    row = c.fetchone()
    if not row:
        print(f'{name}: NOT FOUND')
        continue
    
    eid = row['id']
    actual_name = row['name']
    
    # Get scores
    c.execute("SELECT technical_score, company_score FROM signal_profiles WHERE entity_id = ?", (eid,))
    profile = c.fetchone()
    
    activity = get_recent_activity_score(conn, eid)
    media = aggregate_media_observations(conn, eid, exclude_newsrooms=True)
    research = aggregate_research_observations(conn, eid)
    
    tech_raw = profile['technical_score'] if profile else None
    tech = tech_raw * activity if tech_raw else None
    company = profile['company_score'] if profile else None
    media_count = media['mention_count'] if media else 0
    media_score = MediaScorer().score(media) if media else None
    research_score = research['score'] if research else None
    newsroom_count = research['newsroom_count'] if research else 0
    research_mentions = research['research_mentions'] if research else 0
    
    print(f'{actual_name}:')
    if tech_raw:
        print(f'  tech: {tech:.1f} (raw={tech_raw:.1f}, activity={activity:.2f})')
    else:
        print(f'  tech: None')
    print(f'  company: {company}')
    media_str = f"{media_score:.1f}" if media_score else "None"
    research_str = f"{research_score:.1f}" if research_score else "None"
    print(f'  media: {media_str} ({media_count} articles)')
    print(f'  research: {research_str} ({newsroom_count} newsroom, {research_mentions} research mentions)')
    print()

conn.close()
