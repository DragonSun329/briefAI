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


def run_scraper(name: str, scraper_func):
    """Run a scraper with error handling."""
    print(f"\n{'=' * 60}")
    print(f"{name}")
    print(f"{'=' * 60}")
    try:
        result = scraper_func()
        return result
    except Exception as e:
        print(f"  ERROR: {e}")
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
    
    # 8. China Tech
    def run_china():
        from scrapers.china_tech_scraper import ChinaTechScraper
        s = ChinaTechScraper()
        r = s.run()
        return len(r.get("ai_articles", []))
    results["china"] = run_scraper("CHINA TECH", run_china)
    
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
    
    # 12. TechMeme (NEW - top tech stories)
    def run_techmeme():
        from scrapers.techmeme_scraper import scrape_techmeme, save_signals
        r = scrape_techmeme()
        save_signals(r)
        return len(r.get("stories", []))
    results["techmeme"] = run_scraper("TECHMEME", run_techmeme)
    
    # 13. Twitter/X API (NEW - AI sentiment via AIsa)
    def run_twitter():
        from scrapers.twitter_api_scraper import scrape_ai_twitter_signals, save_signals
        r = scrape_ai_twitter_signals()
        save_signals(r)
        return len(r.get("trends", [])) + len(r.get("ai_mentions", []))
    results["twitter"] = run_scraper("TWITTER API", run_twitter)
    
    # 14. Yahoo Finance (NEW - AI stock prices)
    def run_yahoo():
        from scrapers.yahoo_finance_scraper import scrape_market_signals, save_signals
        r = scrape_market_signals()
        save_signals(r)
        return len(r.get("stocks", []))
    results["yahoo_finance"] = run_scraper("YAHOO FINANCE", run_yahoo)
    
    # 15. Insider Trading (OpenInsider)
    def run_insider():
        from scrapers.insider_trading_scraper import fetch_insider_trades
        r = fetch_insider_trades()
        return len(r) if r else 0
    results["insider"] = run_scraper("INSIDER TRADING", run_insider)
    
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
