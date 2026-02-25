import asyncio, sys, json
sys.path.insert(0, '.')

async def main():
    from modules.daily_brief import DailyBriefGenerator
    gen = DailyBriefGenerator()
    
    result = await gen._gather_news(top_n=15)
    print(f"Total scraped: {result['total_scraped']}")
    print(f"Total included: {result['total_included']}")
    if 'delta_stats' in result:
        print(f"Delta: {result['delta_stats']}")
    
    print("\nFINAL SELECTED STORIES:")
    for cat, arts in result.get('articles_by_category', {}).items():
        print(f"\n  [{cat}]")
        for a in arts:
            src = a.get('_source_type', '?')
            score = a.get('_combined_score', a.get('weighted_score', 0))
            title = a.get('title', '?')[:70]
            print(f"    [{src}] score={score:.3f} | {title}")

asyncio.run(main())
