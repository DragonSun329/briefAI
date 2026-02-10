"""
Package Downloads Scraper for AI Framework Adoption

Tracks download statistics from PyPI and npm to monitor
AI framework adoption and growth trends.

APIs used:
- PyPI: pypistats.org (free, no API key)
- npm: api.npmjs.org (free, no API key)
"""

import requests
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional
import time


class PackageDownloadsScraper:
    """Scraper for PyPI and npm package download statistics."""

    PYPI_API = "https://pypistats.org/api"
    NPM_API = "https://api.npmjs.org/downloads"

    # AI/ML packages to track on PyPI
    PYPI_PACKAGES = [
        # Core ML/DL frameworks
        "torch",
        "tensorflow",
        "keras",
        "jax",
        "flax",
        # LLM/NLP
        "transformers",
        "openai",
        "anthropic",
        "langchain",
        "langchain-core",
        "llama-index",
        "sentence-transformers",
        "tiktoken",
        "tokenizers",
        # Agent frameworks
        "autogen",
        "crewai",
        "guidance",
        # Vector DBs / RAG
        "chromadb",
        "pinecone-client",
        "weaviate-client",
        "qdrant-client",
        "faiss-cpu",
        # ML tools
        "scikit-learn",
        "xgboost",
        "lightgbm",
        "catboost",
        "optuna",
        # Computer vision
        "opencv-python",
        "ultralytics",
        "timm",
        # Data/Utils
        "numpy",
        "pandas",
        "huggingface-hub",
        "datasets",
    ]

    # AI packages to track on npm
    NPM_PACKAGES = [
        # OpenAI / LLM clients
        "openai",
        "@anthropic-ai/sdk",
        "langchain",
        "@langchain/core",
        "@langchain/openai",
        "llamaindex",
        # ML libraries
        "@tensorflow/tfjs",
        "@tensorflow/tfjs-node",
        "brain.js",
        "ml5",
        "onnxruntime-node",
        "onnxruntime-web",
        # Vector DBs
        "@pinecone-database/pinecone",
        "chromadb",
        # Utils
        "gpt-3-encoder",
        "tiktoken",
        "ai",  # Vercel AI SDK
    ]

    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or Path(__file__).parent.parent / "data" / "alternative_signals"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "BriefAI/1.0",
            "Accept": "application/json",
        })

    def get_pypi_downloads(self, package: str) -> Dict[str, Any]:
        """Get download stats for a PyPI package."""
        url = f"{self.PYPI_API}/packages/{package}/recent"
        
        try:
            resp = self.session.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            
            return {
                "package": package,
                "platform": "pypi",
                "downloads_last_day": data.get("data", {}).get("last_day", 0),
                "downloads_last_week": data.get("data", {}).get("last_week", 0),
                "downloads_last_month": data.get("data", {}).get("last_month", 0),
            }
        except Exception as e:
            print(f"  Error fetching PyPI stats for {package}: {e}")
            return {
                "package": package,
                "platform": "pypi",
                "downloads_last_day": 0,
                "downloads_last_week": 0,
                "downloads_last_month": 0,
                "error": str(e),
            }

    def get_npm_downloads(self, package: str) -> Dict[str, Any]:
        """Get download stats for an npm package."""
        # Get last week downloads
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)
        
        url_week = f"{self.NPM_API}/point/{start_date.strftime('%Y-%m-%d')}:{end_date.strftime('%Y-%m-%d')}/{package}"
        
        # Get last month downloads
        start_month = end_date - timedelta(days=30)
        url_month = f"{self.NPM_API}/point/{start_month.strftime('%Y-%m-%d')}:{end_date.strftime('%Y-%m-%d')}/{package}"
        
        try:
            resp_week = self.session.get(url_week, timeout=15)
            week_data = resp_week.json() if resp_week.status_code == 200 else {}
            
            resp_month = self.session.get(url_month, timeout=15)
            month_data = resp_month.json() if resp_month.status_code == 200 else {}
            
            week_downloads = week_data.get("downloads", 0)
            month_downloads = month_data.get("downloads", 0)
            
            return {
                "package": package,
                "platform": "npm",
                "downloads_last_day": week_downloads // 7 if week_downloads else 0,
                "downloads_last_week": week_downloads,
                "downloads_last_month": month_downloads,
            }
        except Exception as e:
            print(f"  Error fetching npm stats for {package}: {e}")
            return {
                "package": package,
                "platform": "npm",
                "downloads_last_day": 0,
                "downloads_last_week": 0,
                "downloads_last_month": 0,
                "error": str(e),
            }

    def fetch_all_stats(self) -> List[Dict[str, Any]]:
        """Fetch download stats for all tracked packages."""
        all_stats = []

        # PyPI packages
        print("  Fetching PyPI package stats...")
        for package in self.PYPI_PACKAGES:
            stats = self.get_pypi_downloads(package)
            stats["bucket"] = self.categorize_package(package, "pypi")
            all_stats.append(stats)
            time.sleep(0.2)  # Rate limit courtesy

        # npm packages
        print("  Fetching npm package stats...")
        for package in self.NPM_PACKAGES:
            stats = self.get_npm_downloads(package)
            stats["bucket"] = self.categorize_package(package, "npm")
            all_stats.append(stats)
            time.sleep(0.1)

        return all_stats

    def categorize_package(self, package: str, platform: str) -> str:
        """Categorize a package into AI trend buckets."""
        package_lower = package.lower()

        # LLM / Foundation
        if any(x in package_lower for x in ["openai", "anthropic", "transformers", "tiktoken", "tokenizers"]):
            return "llm-foundation"

        # Agent frameworks
        if any(x in package_lower for x in ["langchain", "llama-index", "llamaindex", "autogen", "crewai", "guidance"]):
            return "ai-agents"

        # Vector DBs / RAG
        if any(x in package_lower for x in ["chroma", "pinecone", "weaviate", "qdrant", "faiss"]):
            return "ai-infrastructure"

        # Deep learning frameworks
        if any(x in package_lower for x in ["torch", "tensorflow", "keras", "jax", "flax"]):
            return "llm-foundation"

        # Computer vision
        if any(x in package_lower for x in ["opencv", "ultralytics", "timm", "yolo"]):
            return "computer-vision"

        # Classic ML
        if any(x in package_lower for x in ["scikit", "xgboost", "lightgbm", "catboost", "optuna"]):
            return "ai-general"

        # NLP specific
        if any(x in package_lower for x in ["sentence-transformer", "huggingface"]):
            return "llm-foundation"

        return "ai-general"

    def calculate_growth_rates(self, stats: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Calculate week-over-week growth rates."""
        for item in stats:
            week = item.get("downloads_last_week", 0)
            month = item.get("downloads_last_month", 0)
            
            # Estimate previous week from monthly average
            if month > 0 and week > 0:
                prev_week_estimate = (month - week) / 3  # Rough estimate
                if prev_week_estimate > 0:
                    growth_rate = (week - prev_week_estimate) / prev_week_estimate
                    item["wow_growth_rate"] = round(growth_rate, 4)
                else:
                    item["wow_growth_rate"] = 0
            else:
                item["wow_growth_rate"] = 0
                
            # Daily average
            item["daily_avg"] = week // 7 if week else 0
            
        return stats

    def compute_signals(self, stats: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Compute trend signals from package download data."""
        bucket_signals = {}
        platform_totals = {"pypi": 0, "npm": 0}

        for item in stats:
            bucket = item.get("bucket", "ai-general")
            platform = item.get("platform")
            downloads = item.get("downloads_last_week", 0)
            growth = item.get("wow_growth_rate", 0)

            platform_totals[platform] = platform_totals.get(platform, 0) + downloads

            if bucket not in bucket_signals:
                bucket_signals[bucket] = {
                    "total_weekly_downloads": 0,
                    "package_count": 0,
                    "avg_growth_rate": 0,
                    "growth_rates": [],
                    "top_packages": [],
                }

            bucket_signals[bucket]["total_weekly_downloads"] += downloads
            bucket_signals[bucket]["package_count"] += 1
            bucket_signals[bucket]["growth_rates"].append(growth)
            
            # Track top packages
            bucket_signals[bucket]["top_packages"].append({
                "package": item["package"],
                "platform": platform,
                "weekly_downloads": downloads,
                "growth_rate": growth,
            })

        # Calculate averages and sort
        for bucket, data in bucket_signals.items():
            rates = data.pop("growth_rates", [])
            data["avg_growth_rate"] = sum(rates) / len(rates) if rates else 0
            
            # Sort and limit top packages
            data["top_packages"] = sorted(
                data["top_packages"],
                key=lambda x: x["weekly_downloads"],
                reverse=True
            )[:5]

            # Interpretation
            growth = data["avg_growth_rate"]
            if growth > 0.15:
                data["signal_interpretation"] = "Explosive growth - strong adoption momentum"
            elif growth > 0.05:
                data["signal_interpretation"] = "Solid growth - healthy adoption"
            elif growth > 0:
                data["signal_interpretation"] = "Stable growth - steady adoption"
            elif growth > -0.05:
                data["signal_interpretation"] = "Flat - mature/saturated"
            else:
                data["signal_interpretation"] = "Declining - potential shift away"

        return {
            "bucket_signals": bucket_signals,
            "platform_totals": platform_totals,
        }

    def run(self, save: bool = True) -> Dict[str, Any]:
        """Run the scraper and return results."""
        print("Fetching package download statistics...")
        
        # Fetch all stats
        stats = self.fetch_all_stats()
        print(f"  Retrieved stats for {len(stats)} packages")

        # Calculate growth rates
        stats = self.calculate_growth_rates(stats)

        # Sort by weekly downloads
        stats.sort(key=lambda x: x.get("downloads_last_week", 0), reverse=True)

        # Compute signals
        signals = self.compute_signals(stats)

        result = {
            "source": "package_downloads",
            "scraped_at": datetime.now().isoformat(),
            "total_packages": len(stats),
            "packages": stats,
            "signals": signals,
            "bucket_signals": signals.get("bucket_signals", {}),
        }

        if save:
            date_str = datetime.now().strftime("%Y-%m-%d")
            output_file = self.output_dir / f"package_downloads_{date_str}.json"
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, default=str)
            print(f"Saved to {output_file}")

        return result


def main():
    """Main entry point."""
    scraper = PackageDownloadsScraper()
    result = scraper.run()

    print("\n" + "=" * 60)
    print("PACKAGE DOWNLOADS SUMMARY")
    print("=" * 60)
    print(f"Total packages tracked: {result['total_packages']}")

    print("\nTop 15 Packages by Weekly Downloads:")
    print("-" * 60)
    for i, pkg in enumerate(result['packages'][:15], 1):
        growth_str = f"{pkg['wow_growth_rate']*100:+.1f}%" if pkg.get('wow_growth_rate') else "N/A"
        print(f"{i}. {pkg['package']} ({pkg['platform']})")
        print(f"   Weekly: {pkg['downloads_last_week']:,} | Growth: {growth_str} | Bucket: {pkg['bucket']}")
        print()

    print("\nSignals by Bucket:")
    print("-" * 60)
    for bucket, data in sorted(result['bucket_signals'].items(),
                               key=lambda x: -x[1]['total_weekly_downloads']):
        print(f"{bucket}:")
        print(f"   Packages: {data['package_count']} | Weekly downloads: {data['total_weekly_downloads']:,}")
        print(f"   Avg growth: {data['avg_growth_rate']*100:+.1f}%")
        print(f"   Signal: {data['signal_interpretation']}")
        print()


if __name__ == "__main__":
    main()
