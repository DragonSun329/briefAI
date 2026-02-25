import json, glob, os

today = '2026-02-24'
data_dir = 'data/alternative_signals'

# Search for "openclaw" across all today's data
print("=== SEARCHING 'openclaw' ACROSS ALL DATA ===")
for root, dirs, files in os.walk('data'):
    for f in files:
        if today not in f and 'brief' not in f:
            continue
        fp = os.path.join(root, f)
        try:
            content = open(fp, encoding='utf-8').read().lower()
            if 'openclaw' in content or 'open claw' in content or 'open-claw' in content:
                count = content.count('openclaw') + content.count('open claw') + content.count('open-claw')
                print(f"  FOUND in {fp} ({count} mentions)")
        except:
            pass

# Check what topics the scrapers actually found
print("\n=== TOP STORIES BY SOURCE ===")
sources = {
    'hackernews': 'hackernews',
    'us_tech_news': 'us_tech_news', 
    'news_search': 'news_search',
    'blog_signals': 'blog_signals',
    'techmeme': 'tech_news',
}

for label, prefix in sources.items():
    pattern = f'data/alternative_signals/{prefix}_{today}.json'
    files = glob.glob(pattern)
    if not files:
        # try news_signals
        pattern2 = f'data/news_signals/{prefix}_{today}.json'
        files = glob.glob(pattern2)
    if not files:
        print(f"\n{label}: NO FILE")
        continue
    
    data = json.load(open(files[0], encoding='utf-8'))
    
    # Different structures
    items = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        for key in ['articles', 'stories', 'items', 'posts', 'signals', 'results']:
            if key in data:
                items = data[key]
                break
        if not items and 'data' in data:
            items = data['data'] if isinstance(data['data'], list) else []
    
    print(f"\n{label}: {len(items)} items")
    # Show top 5 by score or just first 5
    shown = 0
    for item in items[:8]:
        title = item.get('title', item.get('headline', item.get('name', '?')))[:80]
        score = item.get('score', item.get('relevance_score', item.get('llm_score', item.get('ai_relevance_score', ''))))
        source = item.get('source', item.get('blog', ''))
        print(f"  [{score}] {title}")
        if source:
            print(f"       src: {source}")

# Check brief's story selection logic
print("\n=== BRIEF TOP STORIES (what made it) ===")
brief = open(f'data/reports/daily_brief_{today}.md', encoding='utf-8').read()
in_stories = False
for line in brief.split('\n'):
    if '## Top Stories' in line:
        in_stories = True
    elif in_stories and line.startswith('## '):
        break
    elif in_stories and line.strip():
        print(f"  {line.strip()[:100]}")
