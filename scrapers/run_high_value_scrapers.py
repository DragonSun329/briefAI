# -*- coding: utf-8 -*-
"""
Run High-Value Scrapers

All new scrapers added Jan 28, 2026:
- Patents, Jobs, Earnings, Product Hunt
- Package Stats, App Rankings, App Reviews
- Research Papers, Policy, China Tech
- Glassdoor, Salary Data, AI Verticals
"""

import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

# Set global socket timeout (fixes feedparser hangs)
from scrapers.scraper_timeout import run_with_timeout  # noqa: E402


SCRAPER_TIMEOUT = 120


def run_scraper(name: str, scraper_func):
    """Run a scraper with error handling and hard timeout."""
    print(f"\n{'=' * 60}")
    print(f"{name}")
    print(f"{'=' * 60}")
    try:
        result = run_with_timeout(scraper_func, timeout=SCRAPER_TIMEOUT, name=name)
        print(f"  SUCCESS: {name} completed")
        return result
    except TimeoutError as e:
        print(f"  TIMEOUT in {name}: {e}")
        print(f"  Continuing with next scraper...")
        return 0
    except Exception as e:
        print(f"  ERROR in {name}: {e}")
        print(f"  Continuing with next scraper...")
        import traceback
        traceback.print_exc()
        return 0


def main():
    """Run all high-value scrapers."""
    print("=" * 70)
    print("BRIEFAI HIGH-VALUE SCRAPERS")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    results = {}
    
    # 1. Job Postings (Greenhouse, Lever)
    def run_jobs():
        from scrapers.job_postings_scraper import JobPostingsScraper
        s = JobPostingsScraper()
        r = s.run()
        return len(r.get("jobs", []))
    results["jobs"] = run_scraper("JOB POSTINGS", run_jobs)
    
    # 2. Earnings News
    def run_earnings():
        from scrapers.earnings_scraper import EarningsScraper
        s = EarningsScraper()
        r = s.run()
        return len(r.get("earnings_news", []))
    results["earnings"] = run_scraper("EARNINGS", run_earnings)
    
    # 3. Product Hunt
    def run_ph():
        from scrapers.product_hunt_scraper import ProductHuntScraper
        s = ProductHuntScraper()
        r = s.run()
        return len(r.get("ai_products", []))
    results["product_hunt"] = run_scraper("PRODUCT HUNT", run_ph)
    
    # 4. Package Stats (PyPI/npm)
    def run_packages():
        from scrapers.package_stats_scraper import PackageStatsScraper
        s = PackageStatsScraper()
        r = s.run()
        return len(r.get("pypi", [])) + len(r.get("npm", []))
    results["packages"] = run_scraper("PACKAGE STATS", run_packages)
    
    # 5. App Rankings
    def run_apps():
        from scrapers.app_rankings_scraper import AppRankingsScraper
        s = AppRankingsScraper()
        r = s.run()
        return len(r.get("tracked_apps", []))
    results["apps"] = run_scraper("APP RANKINGS", run_apps)
    
    # 6. Research Papers (ArXiv)
    def run_papers():
        from scrapers.conference_papers_scraper import ConferencePapersScraper
        s = ConferencePapersScraper()
        r = s.run()
        return sum(len(v) for v in r.get("papers_by_category", {}).values())
    results["papers"] = run_scraper("RESEARCH PAPERS", run_papers)
    
    # 7. Government Policy
    def run_policy():
        from scrapers.policy_scraper import PolicyScraper
        s = PolicyScraper()
        r = s.run()
        return len(r.get("federal_register", []))
    results["policy"] = run_scraper("GOV POLICY", run_policy)
    
    # 8. China Tech - REMOVED (unreliable, hangs on feeds from CN)
    
    # 9. Glassdoor (cached data)
    def run_glassdoor():
        from scrapers.glassdoor_scraper import GlassdoorScraper
        s = GlassdoorScraper()
        r = s.run()
        return len(r.get("companies", []))
    results["glassdoor"] = run_scraper("GLASSDOOR", run_glassdoor)
    
    # 10. Salary Data
    def run_salary():
        from scrapers.salary_scraper import SalaryScraper
        s = SalaryScraper()
        r = s.run()
        return len(r.get("companies", []))
    results["salary"] = run_scraper("SALARY DATA", run_salary)
    
    # 11. AI Verticals
    def run_verticals():
        from scrapers.ai_verticals_scraper import AIVerticalsScraper
        s = AIVerticalsScraper()
        r = s.run()
        return len(r.get("verticals", {}))
    results["verticals"] = run_scraper("AI VERTICALS", run_verticals)
    
    # 12. Market Data: Finnhub (primary, reliable from China) — run early so prices are available
    def run_market_data():
        from scrapers.finnhub_scraper import run as finnhub_run
        r = finnhub_run()
        return len(r.get("stocks", []))
    results["market_data"] = run_scraper("MARKET DATA (Finnhub)", run_market_data)
    
    # 13. TechMeme (top tech stories)
    def run_techmeme():
        from scrapers.techmeme_scraper import scrape_techmeme, save_signals
        r = scrape_techmeme()
        save_signals(r)
        return len(r.get("stories", []))
    results["techmeme"] = run_scraper("TECHMEME", run_techmeme)
    
    # 14. Twitter/X API (AI sentiment via AIsa)
    def run_twitter():
        from scrapers.twitter_api_scraper import scrape_ai_twitter_signals, save_signals
        r = scrape_ai_twitter_signals()
        save_signals(r)
        return len(r.get("trends", [])) + len(r.get("ai_mentions", []))
    results["twitter"] = run_scraper("TWITTER API", run_twitter)
    
    # 15. Podcasts (YouTube transcripts from top AI/tech podcasts)
    def run_podcasts():
        from scrapers.podcast_scraper import scrape_podcasts
        r = scrape_podcasts(max_per_channel=2, days_back=3)
        return len(r)
    results["podcasts"] = run_scraper("PODCASTS", run_podcasts)
    
    # 16. Insider Trading (OpenInsider)
    def run_insider():
        from scrapers.insider_trading_scraper import fetch_insider_trades
        r = fetch_insider_trades()
        return len(r) if r else 0
    results["insider"] = run_scraper("INSIDER TRADING", run_insider)
    
    # 16. CellCog Deep Research
    def run_cellcog():
        from scrapers.cellcog_research import run_daily_research
        r = run_daily_research()
        return r.get('count', 0) if isinstance(r, dict) else 0
    results["cellcog"] = run_scraper("CELLCOG DEEP RESEARCH", run_cellcog)
    
    # 17. Yahoo Finance Market Data
    def run_yahoo_finance():
        from scrapers.yahoo_finance_scraper import scrape_market_signals
        r = scrape_market_signals()
        return len(r.get("stocks", []))
    results["yahoo_finance"] = run_scraper("YAHOO FINANCE", run_yahoo_finance)
    
    # 18. Financial Data (SEC Filings, Earnings)
    def run_financial_data():
        from scrapers.financial_data_scraper import FinancialDataScraper
        s = FinancialDataScraper()
        r = s.run()
        return len(r.get("sec_filings", [])) + len(r.get("upcoming_earnings", []))
    results["financial_data"] = run_scraper("FINANCIAL DATA", run_financial_data)
    
    # 19. Hiring Signals
    def run_hiring_signals():
        from scrapers.hiring_signals_scraper import run
        r = run()
        return len(r.get("company_signals", []))
    results["hiring_signals"] = run_scraper("HIRING SIGNALS", run_hiring_signals)
    
    # 20. Private Company Tracker
    def run_private_companies():
        import asyncio
        from scrapers.private_company_tracker import main as private_main
        r = asyncio.run(private_main())
        return 0  # main() doesn't return count, but saves data
    results["private_companies"] = run_scraper("PRIVATE COMPANIES", run_private_companies)
    
    # Summary
    print("\n" + "=" * 70)
    print("FINAL SUMMARY")
    print("=" * 70)
    
    total = 0
    for source, count in results.items():
        count = count or 0
        print(f"  {source:20} {count:>6} items")
        total += count
    
    print(f"\n  {'TOTAL':20} {total:>6} items")
    print("=" * 70)
    
    return results


if __name__ == "__main__":
    main()
