import json
data = json.load(open('data/news_signals/tech_news_2026-02-24.json', encoding='utf-8'))
# Show some 1.0 scored articles
print("=== SCORE 1.0 ARTICLES (sample) ===")
ones = [a for a in data['articles'] if a.get('ai_relevance_score', 0) >= 0.95]
for a in ones[:10]:
    print(f"  {a['ai_relevance_score']:.2f} | {a['title'][:70]}")

print("\n=== LOW SCORE ARTICLES ===")
lows = [a for a in data['articles'] if a.get('ai_relevance_score', 0) <= 0.4]
for a in lows[:10]:
    print(f"  {a['ai_relevance_score']:.2f} | {a['title'][:70]}")

# Wait - the scraper saves ai_relevance (from score_ai_relevance) 
# but the output file has ai_relevance_score. Check if they're different
print("\n=== CHECK FIELD NAMES ===")
a = data['articles'][0]
for k in sorted(a.keys()):
    if 'relev' in k.lower() or 'score' in k.lower():
        print(f"  {k}: {a[k]}")
