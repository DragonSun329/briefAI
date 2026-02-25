import json, glob

today = '2026-02-24'
sources = {
    'hackernews': f'data/alternative_signals/hackernews_{today}.json',
    'blog_signals': f'data/alternative_signals/blog_signals_{today}.json',
    'news_search': f'data/alternative_signals/news_search_{today}.json',
    'reddit': f'data/alternative_signals/reddit_{today}.json',
    'us_tech_news': f'data/alternative_signals/us_tech_news_{today}.json',
    'tech_news': f'data/news_signals/tech_news_{today}.json',
    'techmeme': f'data/news_signals/tech_news_{today}.json',
    'podcasts': f'data/alternative_signals/podcasts_{today}.json',
    'newsletters': f'data/newsletter_signals/newsletters_{today}.json',
    'arxiv': f'data/alternative_signals/arxiv_{today}.json',
}

for name, path in sources.items():
    try:
        data = json.load(open(path, encoding='utf-8'))
    except FileNotFoundError:
        print(f"\n=== {name}: FILE NOT FOUND ({path}) ===")
        continue
    except:
        print(f"\n=== {name}: PARSE ERROR ===")
        continue
    
    print(f"\n=== {name} ===")
    if isinstance(data, list):
        print(f"  Type: list, len={len(data)}")
        if data:
            item = data[0]
            print(f"  Keys: {list(item.keys())[:15]}")
            print(f"  Title field: {item.get('title', item.get('headline', item.get('name', 'NONE')))[:60]}")
            # Score fields
            for sf in ['score', 'relevance_score', 'ai_relevance_score', 'llm_score', 'points', 'upvotes']:
                if sf in item:
                    print(f"  Score field '{sf}': {item[sf]}")
    elif isinstance(data, dict):
        print(f"  Type: dict, keys={list(data.keys())[:10]}")
        for key in ['articles', 'stories', 'items', 'posts', 'signals', 'results', 'data', 'episodes', 'channels']:
            if key in data:
                items = data[key]
                if isinstance(items, list) and items:
                    print(f"  '{key}': {len(items)} items")
                    item = items[0]
                    print(f"  Keys: {list(item.keys())[:15]}")
                    print(f"  Title: {item.get('title', item.get('headline', item.get('name', 'NONE')))[:60]}")
                    for sf in ['score', 'relevance_score', 'ai_relevance_score', 'llm_score', 'points', 'upvotes', 'relevance']:
                        if sf in item:
                            print(f"  Score '{sf}': {item[sf]}")
                    break
