import json
pods = json.load(open('data/alternative_signals/podcasts_2026-02-24.json', encoding='utf-8'))
for p in pods:
    title = p.get('title', '?')[:60]
    score = p.get('credibility_score', '?')
    src = p.get('podcast_channel', '?')
    print(f"  {score}  [{src}]  {title}")
