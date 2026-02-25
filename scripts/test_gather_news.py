"""Test the updated _gather_news with all sources."""
import asyncio
import sys
sys.path.insert(0, '.')

async def main():
    from modules.daily_brief import DailyBriefGenerator
    gen = DailyBriefGenerator()
    
    # Test loading all sources
    from pathlib import Path
    articles = gen._load_all_sources(Path("data"))
    print(f"Total articles loaded: {len(articles)}")
    
    # Count by source type
    from collections import Counter
    src_counts = Counter(a.get('_source_type', '?') for a in articles)
    for src, count in src_counts.most_common():
        print(f"  {src}: {count}")
    
    # Test cross-source boost
    boost = gen._compute_cross_source_boost(articles)
    boosted = [(i, b) for i, b in boost.items() if b > 0]
    print(f"\nArticles with cross-source boost: {len(boosted)}")
    # Show top boosted
    boosted.sort(key=lambda x: x[1], reverse=True)
    for i, b in boosted[:10]:
        print(f"  boost={b:.2f} [{articles[i].get('_source_type')}] {articles[i].get('title', '?')[:70]}")
    
    # Test full gather (without LLM to save API calls)
    gen.llm_client = None  # disable LLM for test
    result = await gen._gather_news(top_n=15)
    print(f"\nGather result: scraped={result['total_scraped']}, included={result['total_included']}")
    for cat, arts in result.get('articles_by_category', {}).items():
        print(f"  {cat}: {len(arts)} articles")
        for a in arts[:3]:
            print(f"    [{a.get('_source_type')}] {a.get('title', '?')[:65]}  score={a.get('_combined_score', 0):.3f}")

asyncio.run(main())
