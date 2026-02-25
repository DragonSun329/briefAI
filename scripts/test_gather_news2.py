"""Check scoring distribution across sources."""
import asyncio, sys
sys.path.insert(0, '.')

async def main():
    from modules.daily_brief import DailyBriefGenerator
    from pathlib import Path
    gen = DailyBriefGenerator()
    articles = gen._load_all_sources(Path("data"))
    boost = gen._compute_cross_source_boost(articles)
    
    from datetime import datetime as dt
    now = dt.now()
    
    for i, art in enumerate(articles):
        relevance = art.get('_raw_score', 0.5)
        quality = art.get('_source_quality', 0.5)
        pub_date = art.get('published_at', '')
        try:
            if pub_date:
                if isinstance(pub_date, (int, float)):
                    parsed = dt.fromtimestamp(pub_date)
                else:
                    parsed = dt.fromisoformat(str(pub_date).replace("Z", "+00:00").replace("+00:00", ""))
                    parsed = parsed.replace(tzinfo=None)
                hours_old = max(0, (now - parsed).total_seconds() / 3600)
                recency = max(0, 1 - (hours_old / 72))
            else:
                recency = 0.3
        except:
            recency = 0.3
        
        cross = boost.get(i, 0.0)
        combined = relevance * quality * 0.4 + recency * 0.2 + quality * 0.15 + cross
        art['_combined_score'] = combined
        art['_cross'] = cross
    
    articles.sort(key=lambda x: x['_combined_score'], reverse=True)
    
    # Show top 30
    print("TOP 30 STORIES (all sources):")
    for j, a in enumerate(articles[:30]):
        src = a.get('_source_type', '?')
        score = a['_combined_score']
        cross = a.get('_cross', 0)
        title = a.get('title', '?')[:65]
        print(f"{j+1:2d}. [{src:12s}] score={score:.3f} cross={cross:.2f} | {title}")
    
    # Show top by source
    for src_type in ['hackernews', 'blogs', 'newsletters', 'reddit']:
        subset = [a for a in articles if a.get('_source_type') == src_type][:5]
        print(f"\nTop {src_type}:")
        for a in subset:
            print(f"  score={a['_combined_score']:.3f} | {a.get('title','?')[:70]}")

asyncio.run(main())
