"""Test the ACTUAL _gather_news from the module."""
import asyncio, sys, importlib
sys.path.insert(0, '.')

async def main():
    from modules.daily_brief import DailyBriefGenerator
    gen = DailyBriefGenerator()
    gen.llm_client = None  # skip LLM for speed
    
    result = await gen._gather_news(top_n=20)
    print(f"Scraped: {result['total_scraped']}, Included: {result['total_included']}")
    if 'delta_stats' in result:
        print(f"Delta: {result['delta_stats']}")
    
    print("\nTOP STORIES:")
    for cat, arts in result.get('articles_by_category', {}).items():
        print(f"\n  [{cat}]")
        for a in arts:
            src = a.get('_source_type', '?')
            score = a.get('_combined_score', 0)
            cross = a.get('_cross_source_boost', 0)
            title = a.get('title', '?')[:70]
            print(f"    {score:.3f} cross={cross:.2f} [{src:12s}] {title}")

asyncio.run(main())
