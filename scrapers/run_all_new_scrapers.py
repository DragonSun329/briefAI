# -*- coding: utf-8 -*-
"""
Run All New Scrapers

Master script to run all newly added high-value scrapers.
"""

import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))


def run_patents():
    """Run patent scraper."""
    print("\n" + "=" * 70)
    print("1. PATENTS")
    print("=" * 70)
    try:
        from scrapers.patent_scraper import PatentScraper
        scraper = PatentScraper()
        results = scraper.run()
        return len(results.get("patents_by_company", [])) + len(results.get("patents_by_term", []))
    except Exception as e:
        print(f"Error: {e}")
        return 0


def run_jobs():
    """Run job postings scraper."""
    print("\n" + "=" * 70)
    print("2. JOB POSTINGS")
    print("=" * 70)
    try:
        from scrapers.job_postings_scraper import JobPostingsScraper
        scraper = JobPostingsScraper()
        results = scraper.run()
        return len(results.get("jobs", []))
    except Exception as e:
        print(f"Error: {e}")
        return 0


def run_earnings():
    """Run earnings scraper."""
    print("\n" + "=" * 70)
    print("3. EARNINGS")
    print("=" * 70)
    try:
        from scrapers.earnings_scraper import EarningsScraper
        scraper = EarningsScraper()
        results = scraper.run()
        return len(results.get("earnings_news", []))
    except Exception as e:
        print(f"Error: {e}")
        return 0


def run_product_hunt():
    """Run Product Hunt scraper."""
    print("\n" + "=" * 70)
    print("4. PRODUCT HUNT")
    print("=" * 70)
    try:
        from scrapers.product_hunt_scraper import ProductHuntScraper
        scraper = ProductHuntScraper()
        results = scraper.run()
        return len(results.get("ai_products", []))
    except Exception as e:
        print(f"Error: {e}")
        return 0


def run_packages():
    """Run package stats scraper."""
    print("\n" + "=" * 70)
    print("5. PACKAGE STATS (PyPI/npm)")
    print("=" * 70)
    try:
        from scrapers.package_stats_scraper import PackageStatsScraper
        scraper = PackageStatsScraper()
        results = scraper.run()
        return len(results.get("pypi", [])) + len(results.get("npm", []))
    except Exception as e:
        print(f"Error: {e}")
        return 0


def run_apps():
    """Run app rankings scraper."""
    print("\n" + "=" * 70)
    print("6. APP RANKINGS")
    print("=" * 70)
    try:
        from scrapers.app_rankings_scraper import AppRankingsScraper
        scraper = AppRankingsScraper()
        results = scraper.run()
        return len(results.get("tracked_apps", []))
    except Exception as e:
        print(f"Error: {e}")
        return 0


def run_papers():
    """Run conference papers scraper."""
    print("\n" + "=" * 70)
    print("7. RESEARCH PAPERS (ArXiv)")
    print("=" * 70)
    try:
        from scrapers.conference_papers_scraper import ConferencePapersScraper
        scraper = ConferencePapersScraper()
        results = scraper.run()
        return sum(len(v) for v in results.get("papers_by_category", {}).values())
    except Exception as e:
        print(f"Error: {e}")
        return 0


def run_policy():
    """Run policy scraper."""
    print("\n" + "=" * 70)
    print("8. GOVERNMENT POLICY")
    print("=" * 70)
    try:
        from scrapers.policy_scraper import PolicyScraper
        scraper = PolicyScraper()
        results = scraper.run()
        return len(results.get("federal_register", []))
    except Exception as e:
        print(f"Error: {e}")
        return 0


def run_china():
    """Run China tech scraper."""
    print("\n" + "=" * 70)
    print("9. CHINA TECH")
    print("=" * 70)
    try:
        from scrapers.china_tech_scraper import ChinaTechScraper
        scraper = ChinaTechScraper()
        results = scraper.run()
        return len(results.get("ai_articles", []))
    except Exception as e:
        print(f"Error: {e}")
        return 0


def main():
    """Run all new scrapers."""
    print("=" * 70)
    print("BRIEFAI - ALL NEW SCRAPERS")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    results = {
        "patents": run_patents(),
        "jobs": run_jobs(),
        "earnings": run_earnings(),
        "product_hunt": run_product_hunt(),
        "packages": run_packages(),
        "apps": run_apps(),
        "papers": run_papers(),
        "policy": run_policy(),
        "china_tech": run_china(),
    }
    
    print("\n" + "=" * 70)
    print("FINAL SUMMARY")
    print("=" * 70)
    
    total = 0
    for source, count in results.items():
        print(f"  {source:20} {count:>6} items")
        total += count
    
    print(f"\n  {'TOTAL':20} {total:>6} items")
    print("=" * 70)


if __name__ == "__main__":
    main()
