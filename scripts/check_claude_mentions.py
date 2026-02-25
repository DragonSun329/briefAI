import json
for src, path in [
    ('hn', 'data/alternative_signals/hackernews_2026-02-24.json'),
    ('reddit', 'data/alternative_signals/reddit_2026-02-24.json'),
    ('blogs', 'data/alternative_signals/blog_signals_2026-02-24.json'),
    ('techmeme', 'data/news_signals/tech_news_2026-02-24.json'),
    ('news', 'data/alternative_signals/news_search_2026-02-24.json'),
]:
    data = json.load(open(path, encoding='utf-8'))
    items = data if isinstance(data, list) else data.get('stories', data.get('articles', data.get('posts', [])))
    matches = [i for i in items if 'sonnet' in i.get('title','').lower() or 'claude' in i.get('title','').lower() and 'sonnet' not in i.get('title','').lower()]
    if matches:
        print(f"{src}: {len(matches)} Claude/Sonnet mentions")
        for m in matches[:3]:
            title = m.get('title', '?')[:70]
            print(f"  {title}")
