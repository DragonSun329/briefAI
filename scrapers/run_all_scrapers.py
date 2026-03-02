"""
Unified Alternative Data Scraper Runner

Runs all alternative data scrapers and aggregates signals
for the AI trend radar.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List
import traceback
import sys

# Set global socket timeout BEFORE importing scrapers (fixes feedparser hangs)
from scraper_timeout import run_with_timeout  # noqa: E402 - also sets socket default timeout

# Per-scraper hard timeout in seconds
SCRAPER_TIMEOUT = 120

# Per-scraper timeout overrides (seconds)
SCRAPER_TIMEOUT_OVERRIDES = {
    "us_tech_news": 300,  # Scrapes 15 companies sequentially
}

# Import all scrapers
from polymarket_scraper import PolymarketScraper
from metaculus_scraper import MetaculusScraper
from manifold_scraper import ManifoldScraper
from huggingface_scraper import HuggingFaceScraper
from hackernews_scraper import HackerNewsScraper
from reddit_scraper import RedditScraper
from github_scraper import GitHubScraper
from arxiv_scraper import ArxivScraper
from google_trends_scraper import GoogleTrendsScraper
from paperswithcode_scraper import PapersWithCodeScraper
from openbook_vc_scraper import OpenBookVCScraper
from us_tech_news_scraper import USTechNewsScraper
# New alternative data scrapers
from patent_scraper import PatentScraper
from package_downloads_scraper import PackageDownloadsScraper
from stackoverflow_scraper import StackOverflowScraper
from yc_scraper import YCScraper
from app_store_scraper import AppStoreScraper
from earnings_scraper import EarningsScraper
from blog_rss_scraper import BlogRSSScraper


class AlternativeDataRunner:
    """Run all alternative data scrapers and aggregate signals."""

    SCRAPERS = {
        "polymarket": PolymarketScraper,
        "metaculus": MetaculusScraper,
        "manifold": ManifoldScraper,
        "huggingface": HuggingFaceScraper,
        "hackernews": HackerNewsScraper,
        "reddit": RedditScraper,
        "github": GitHubScraper,
        "arxiv": ArxivScraper,
        "google_trends": GoogleTrendsScraper,
        "paperswithcode": PapersWithCodeScraper,
        "openbook_vc": OpenBookVCScraper,
        "us_tech_news": USTechNewsScraper,
        # New alternative data scrapers
        "patents": PatentScraper,
        "package_downloads": PackageDownloadsScraper,
        "stackoverflow": StackOverflowScraper,
        "yc_companies": YCScraper,
        "app_store": AppStoreScraper,
        "earnings": EarningsScraper,
        "blog_signals": BlogRSSScraper,
    }

    def __init__(self, output_dir: Path = None):
        self.output_dir = output_dir or Path(__file__).parent.parent / "data" / "alternative_signals"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def run_scraper(self, name: str, scraper_class) -> Dict[str, Any]:
        """Run a single scraper and return results."""
        print(f"\n{'='*60}")
        print(f"RUNNING: {name.upper()}")
        print(f"{'='*60}")

        def _execute():
            try:
                # Handle scrapers with different constructor signatures
                if name == "huggingface":
                    scraper = scraper_class()
                elif name == "us_tech_news":
                    scraper = scraper_class(output_dir=self.output_dir)
                    return scraper.run(save=True, days_back=7)
                else:
                    scraper = scraper_class(output_dir=self.output_dir)
                return scraper.run(save=True)
            except Exception as e:
                print(f"  SCRAPER INTERNAL ERROR in {name}: {e}")
                traceback.print_exc()
                raise e

        try:
            timeout = SCRAPER_TIMEOUT_OVERRIDES.get(name, SCRAPER_TIMEOUT)
            result = run_with_timeout(_execute, timeout=timeout, name=name)
            print(f"  SUCCESS: {name} completed")
            return {
                "status": "success",
                "source": name,
                "data": result,
            }
        except TimeoutError as e:
            print(f"  TIMEOUT in {name}: {e}")
            print(f"  Continuing with next scraper...")
            return {
                "status": "timeout",
                "source": name,
                "error": str(e),
            }
        except Exception as e:
            print(f"  ERROR in {name}: {e}")
            print(f"  Continuing with next scraper...")
            traceback.print_exc()
            return {
                "status": "error",
                "source": name,
                "error": str(e),
            }

    def run_all(self, sources: List[str] = None) -> Dict[str, Any]:
        """Run all scrapers or specified subset."""
        if sources is None:
            sources = list(self.SCRAPERS.keys())

        results = {}
        successful = 0
        failed = 0

        for name in sources:
            if name not in self.SCRAPERS:
                print(f"Unknown scraper: {name}")
                continue

            result = self.run_scraper(name, self.SCRAPERS[name])
            results[name] = result

            if result["status"] == "success":
                successful += 1
            else:
                failed += 1

        # Aggregate signals
        aggregated = self.aggregate_signals(results)

        summary = {
            "run_at": datetime.now().isoformat(),
            "scrapers_run": len(results),
            "successful": successful,
            "failed": failed,
            "results": results,
            "aggregated_signals": aggregated,
        }

        # Save summary
        date_str = datetime.now().strftime("%Y-%m-%d")
        summary_file = self.output_dir / f"scraper_summary_{date_str}.json"
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, default=str)
        print(f"\nSummary saved to {summary_file}")

        return summary

    def aggregate_signals(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Aggregate signals from all scrapers by bucket."""
        bucket_signals = {}

        # Weight factors for different signal types
        weights = {
            "polymarket": 1.5,    # Real money = high signal
            "manifold": 1.0,     # Play money but high volume
            "metaculus": 1.2,    # Calibrated forecasters
            "hackernews": 0.8,   # Tech sentiment
            "reddit": 0.6,       # Community sentiment
            "github": 1.0,       # Developer adoption
            "huggingface": 1.0,  # Model adoption
            "arxiv": 0.7,        # Research direction
            "paperswithcode": 0.8,
            "google_trends": 0.5,  # General interest
            "us_tech_news": 1.2,  # US tech company news (high signal for market sentiment)
            # New alternative data sources
            "patents": 1.0,       # R&D investment signal
            "package_downloads": 1.2,  # Developer adoption signal
            "stackoverflow": 0.8,  # Developer interest signal
            "yc_companies": 1.3,   # Startup ecosystem signal
            "app_store": 0.9,      # Consumer adoption signal
            "earnings": 1.4,       # Corporate AI commitment (high signal)
        }

        for source, result in results.items():
            if result.get("status") != "success":
                continue

            data = result.get("data", {})
            # Handle different data formats - some scrapers return lists, others dicts
            if isinstance(data, list):
                continue  # Skip list-format data (raw items, not bucket signals)
            signals_data = data.get("signals", {})
            if isinstance(signals_data, list):
                continue  # Skip if signals is a list
            source_signals = data.get("bucket_signals", signals_data.get("bucket_signals", {}) if isinstance(signals_data, dict) else {})
            weight = weights.get(source, 1.0)

            for bucket, signals in source_signals.items():
                if bucket not in bucket_signals:
                    bucket_signals[bucket] = {
                        "sources": [],
                        "weighted_sentiment": 0,
                        "total_weight": 0,
                        "signal_count": 0,
                    }

                # Extract sentiment/score from different signal formats
                sentiment = 0
                if "weighted_sentiment" in signals:
                    sentiment = signals["weighted_sentiment"]
                elif "sentiment_score" in signals:
                    sentiment = signals["sentiment_score"]
                elif "weighted_avg_prediction" in signals:
                    # Convert prediction (0-1) to sentiment (-1 to 1)
                    sentiment = (signals["weighted_avg_prediction"] - 0.5) * 2

                bucket_signals[bucket]["sources"].append(source)
                bucket_signals[bucket]["weighted_sentiment"] += sentiment * weight
                bucket_signals[bucket]["total_weight"] += weight
                bucket_signals[bucket]["signal_count"] += 1

        # Normalize
        for bucket, data in bucket_signals.items():
            if data["total_weight"] > 0:
                data["final_sentiment"] = data["weighted_sentiment"] / data["total_weight"]
            else:
                data["final_sentiment"] = 0

            # Interpret
            sent = data["final_sentiment"]
            if sent > 0.3:
                data["consensus"] = "Strong bullish signal"
            elif sent > 0.1:
                data["consensus"] = "Mild bullish signal"
            elif sent < -0.3:
                data["consensus"] = "Strong bearish signal"
            elif sent < -0.1:
                data["consensus"] = "Mild bearish signal"
            else:
                data["consensus"] = "Neutral/mixed signals"

        return bucket_signals


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Run alternative data scrapers")
    parser.add_argument(
        "--sources",
        nargs="+",
        choices=list(AlternativeDataRunner.SCRAPERS.keys()),
        help="Specific scrapers to run (default: all)",
    )
    args = parser.parse_args()

    try:
        runner = AlternativeDataRunner()
        summary = runner.run_all(sources=args.sources)

        print("\n" + "=" * 60)
        print("ALTERNATIVE DATA SCRAPING COMPLETE")
        print("=" * 60)
        print(f"Scrapers run: {summary['scrapers_run']}")
        print(f"Successful: {summary['successful']}")
        print(f"Failed: {summary['failed']}")

        print("\nAggregated Signals by Bucket:")
        print("-" * 60)
        for bucket, data in sorted(summary['aggregated_signals'].items(),
                                   key=lambda x: -x[1]['signal_count']):
            print(f"{bucket}:")
            print(f"   Sources: {', '.join(data['sources'])}")
            print(f"   Sentiment: {data['final_sentiment']:+.2f}")
            print(f"   Consensus: {data['consensus']}")
            print()
            
        # Always exit with success for pipeline resilience
        return 0
        
    except Exception as e:
        print(f"\nFATAL ERROR in scraper runner: {e}")
        import traceback
        traceback.print_exc()
        # Still exit 0 to avoid crashing pipeline
        print("\nExiting with success code to avoid pipeline failure")
        return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit as e:
        # Allow normal sys.exit() but log it
        print(f"Alternative data scrapers exiting with code: {e.code}")
        sys.exit(0)  # Always exit 0 for pipeline resilience
    except Exception as e:
        print(f"FATAL ERROR in alternative data scrapers: {e}")
        import traceback
        traceback.print_exc()
        print("Exiting with success code to avoid pipeline failure")
        sys.exit(0)