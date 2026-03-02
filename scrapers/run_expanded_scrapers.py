# -*- coding: utf-8 -*-
"""
Run Expanded Scrapers

Runs all new scrapers and imports signals into briefAI with deduplication.
"""

import sys
from pathlib import Path
from datetime import datetime, timezone
import uuid
import traceback

sys.path.insert(0, str(Path(__file__).parent.parent))

# Set global socket timeout (fixes feedparser hangs)
from scrapers.scraper_timeout import run_with_timeout  # noqa: E402

SCRAPER_TIMEOUT = 120

from utils.signal_store import SignalStore
from utils.signal_models import (
    Entity, EntityType, SignalCategory, SignalObservation, SignalScore
)


def import_signals_to_briefai(observations: list, source_name: str):
    """Import signal observations into briefAI database."""
    store = SignalStore()
    
    added = 0
    skipped = 0
    
    for obs_data in observations:
        try:
            # Get or create entity
            entity = store.get_or_create_entity(
                name=obs_data["entity_name"],
                entity_type=EntityType.COMPANY,
            )
            
            # Create observation
            category = SignalCategory.MEDIA_SENTIMENT
            if obs_data.get("category") == "product":
                category = SignalCategory.PRODUCT_TRACTION
            elif obs_data.get("category") == "financial":
                category = SignalCategory.FINANCIAL
            elif obs_data.get("category") == "technical":
                category = SignalCategory.TECHNICAL
            
            obs = SignalObservation(
                id=str(uuid.uuid4()),
                entity_id=entity.id,
                source_id=obs_data["source_id"],
                category=category,
                observed_at=datetime.now(timezone.utc),
                data_timestamp=datetime.now(timezone.utc),
                raw_value=obs_data["raw_value"],
                raw_value_unit="relevance_score",
                raw_data=obs_data["raw_data"],
                confidence=obs_data.get("confidence", 0.7),
            )
            
            # Add with dedup check
            result = store.add_observation(obs)
            
            if result:
                added += 1
                # Add score
                score = SignalScore(
                    id=str(uuid.uuid4()),
                    observation_id=obs.id,
                    entity_id=entity.id,
                    source_id=obs_data["source_id"],
                    category=category,
                    score=obs_data["raw_value"] * 10,
                    percentile=None,
                    score_delta_7d=None,
                    score_delta_30d=None,
                )
                store.add_score(score)
            else:
                skipped += 1
                
        except Exception as e:
            print(f"  Error importing signal: {e}")
            continue
    
    return added, skipped


def run_tech_news_scraper():
    """Run tech news RSS scraper."""
    print("\n" + "=" * 60)
    print("1. TECH NEWS RSS SCRAPER")
    print("=" * 60)
    
    try:
        from scrapers.tech_news_rss_scraper import TechNewsRSSScraper
        
        scraper = TechNewsRSSScraper()
        articles = scraper.scrape_all_feeds(min_relevance=0.3)
        
        if articles:
            scraper.save_results(articles)
            signals = scraper.to_signal_observations(articles[:50])
            
            added, skipped = import_signals_to_briefai(signals, "tech_news_rss")
            print(f"\n  Imported: {added} signals, Skipped (dedup): {skipped}")
            
            return len(articles)
    except Exception as e:
        print(f"  Error: {e}")
    
    return 0


def run_newsletter_scraper():
    """Run newsletter scraper."""
    print("\n" + "=" * 60)
    print("2. NEWSLETTER & BLOG SCRAPER")
    print("=" * 60)
    
    try:
        from scrapers.newsletter_scraper import NewsletterScraper
        
        scraper = NewsletterScraper()
        posts = scraper.scrape_all(days_back=7)
        
        if posts:
            scraper.save_results(posts)
            signals = scraper.to_signal_observations(posts)
            
            added, skipped = import_signals_to_briefai(signals, "newsletter")
            print(f"\n  Imported: {added} signals, Skipped (dedup): {skipped}")
            
            return len(posts)
    except Exception as e:
        print(f"  Error: {e}")
    
    return 0


def run_reddit_scraper():
    """Run expanded Reddit scraper."""
    print("\n" + "=" * 60)
    print("3. REDDIT SCRAPER (EXPANDED)")
    print("=" * 60)
    
    try:
        from scrapers.reddit_scraper import RedditScraper
        
        scraper = RedditScraper()
        posts = scraper.fetch_all_ai_subreddits(limit_per_sub=15)
        
        print(f"  Fetched {len(posts)} posts from {len(scraper.AI_SUBREDDITS)} subreddits")
        
        # Convert to signals
        signals = []
        for post in posts:
            if post.get("score", 0) < 10:  # Skip low-engagement posts
                continue
                
            data = scraper.extract_post_data(post)
            
            signals.append({
                "entity_name": f"r/{data['subreddit']}",
                "source_id": "reddit_expanded",
                "category": "media",
                "raw_value": min(5.0 + (data["score"] / 100), 9.0),
                "raw_data": {
                    "source": "Reddit",
                    "headline": data["title"][:200],
                    "url": data["url"],
                    "subreddit": data["subreddit"],
                    "score": data["score"],
                    "num_comments": data["num_comments"],
                    "signal_type": "community_sentiment",
                },
                "confidence": 0.6,
            })
        
        if signals:
            added, skipped = import_signals_to_briefai(signals[:100], "reddit")
            print(f"\n  Imported: {added} signals, Skipped (dedup): {skipped}")
        
        return len(posts)
    except Exception as e:
        print(f"  Error: {e}")
    
    return 0


def run_financial_scraper():
    """Run SEC filings scraper."""
    print("\n" + "-" * 60)
    print("FINANCIAL DATA (SEC FILINGS)")
    print("-" * 60)
    
    try:
        from scrapers.financial_data_scraper import FinancialDataScraper
        
        scraper = FinancialDataScraper()
        results = scraper.run()
        
        filings = results.get("sec_filings", [])
        
        # Convert to signals for import
        signals = []
        for f in filings:
            signals.append({
                "entity_name": f["entity"],
                "source_id": "sec_edgar",
                "category": "financial",
                "raw_value": 7.0 if f["filing_type"] in ["10-K", "10-Q"] else 5.0,
                "raw_data": {
                    "source": "SEC EDGAR",
                    "headline": f["title"],
                    "url": f["url"],
                    "filing_type": f["filing_type"],
                    "ticker": f["ticker"],
                    "signal_type": "sec_filing",
                },
                "confidence": 0.95,
            })
        
        if signals:
            added, skipped = import_signals_to_briefai(signals, "sec_filings")
            print(f"\n  Imported: {added} signals, Skipped (dedup): {skipped}")
        
        return len(filings)
    except Exception as e:
        print(f"  Error: {e}")
        import traceback
        traceback.print_exc()
    
    return 0


def run_news_search_v2():
    """Run Tavily + SearXNG news search (replaces old news_search_scraper)."""
    print("\n" + "=" * 60)
    print("NEWS SEARCH v2 (Tavily + SearXNG)")
    print("=" * 60)

    try:
        from scrapers.news_search_scraper_v2 import NewsSearchScraperV2

        scraper = NewsSearchScraperV2()
        result = scraper.run()
        return result.get("article_count", 0)
    except Exception as e:
        print(f"  Error: {e}")
    return 0


def run_blog_rss_scraper():
    """Run HN top blogs RSS scraper (opinion leader layer)."""
    print("\n" + "=" * 60)
    print("BLOG RSS (HN Top Blogs)")
    print("=" * 60)

    try:
        from scrapers.blog_rss_scraper import BlogRSSScraper

        scraper = BlogRSSScraper()
        result = scraper.run()
        return result.get("post_count", 0)
    except Exception as e:
        print(f"  Error: {e}")
    return 0


def run_techmeme_scraper():
    """Run TechMeme scraper."""
    print("\n" + "=" * 60)
    print("TECHMEME SCRAPER")
    print("=" * 60)

    try:
        from scrapers.techmeme_scraper import main as techmeme_main

        result = techmeme_main()
        count = result.get("total_stories", 0) if result else 0
        print(f"  Scraped {count} stories from TechMeme")
        return count
    except Exception as e:
        print(f"  Error: {e}")
    return 0


def main():
    """Run all expanded scrapers."""
    print("=" * 60)
    print("BRIEFAI EXPANDED SCRAPER RUN")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    def _safe_run(name, func):
        try:
            print(f"\nStarting {name}...")
            result = run_with_timeout(func, timeout=SCRAPER_TIMEOUT, name=name)
            print(f"  SUCCESS: {name} completed")
            return result
        except TimeoutError as e:
            print(f"  TIMEOUT in {name}: {e}")
            print(f"  Continuing with next scraper...")
            return 0
        except Exception as e:
            print(f"  ERROR in {name}: {e}")
            print(f"  Continuing with next scraper...")
            traceback.print_exc()
            return 0

    results = {
        "tech_news": _safe_run("tech_news", run_tech_news_scraper),
        "news_search_v2": _safe_run("news_search_v2", run_news_search_v2),
        "blog_rss": _safe_run("blog_rss", run_blog_rss_scraper),
        "newsletters": _safe_run("newsletters", run_newsletter_scraper),
        "reddit": _safe_run("reddit", run_reddit_scraper),
        "financial": _safe_run("financial", run_financial_scraper),
        "techmeme": _safe_run("techmeme", run_techmeme_scraper),
    }
    
    print("\n" + "=" * 60)
    print("EXPANDED SCRAPERS SUMMARY")
    print("=" * 60)
    
    failed_count = 0
    success_count = 0
    for source, count in results.items():
        if count == 0:
            failed_count += 1
            status = "FAILED/TIMEOUT"
        else:
            success_count += 1
            status = "SUCCESS"
        print(f"  {source:15} {count:>6} items  [{status}]")
    
    total = sum(results.values())
    print(f"\n  {'TOTAL':15} {total:>6} items")
    print(f"  Success: {success_count}, Failed: {failed_count}")
    
    # Always exit 0 - failures are non-fatal for the pipeline
    print(f"\nExpanded scrapers completed. Failures are non-fatal.")
    print("Run `python scripts/rebuild_profiles.py` to update signal radar.")
    
    return 0  # Always return success for pipeline resilience


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        # Prevent sys.exit() from crashing the pipeline
        print("Expanded scrapers completed with exit call")
    except Exception as e:
        print(f"FATAL ERROR in expanded scrapers: {e}")
        import traceback
        traceback.print_exc()
        print("Exiting with success code to avoid pipeline failure")
