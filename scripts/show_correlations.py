import json, sys
with open(sys.argv[1], encoding='utf-8') as f:
    d = json.load(f)
print(json.dumps(d['summary'], indent=2))
print()
for c in d['correlations']:
    sign = '+' if c['price_change_pct'] > 0 else ''
    print(f"{c['ticker']} {sign}{c['price_change_pct']:.1f}% | {c['explanation_strength']} | {c['article_matches']} articles")
    for a in c.get('top_articles', [])[:3]:
        title = a['title'][:90].encode('ascii', errors='replace').decode()
        print(f"  -> [{a['source']}] {title}")
        print(f"     score={a['match_score']} sentiment={a['sentiment']}")
