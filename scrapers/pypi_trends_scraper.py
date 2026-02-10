#!/usr/bin/env python3
"""
PyPI Trends Scraper for briefAI.

Tracks download trends for AI/ML Python packages.
Uses pypistats.org API (free, no auth required).
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List
import requests
from loguru import logger

class PyPITrendsScraper:
    """Scrapes PyPI download statistics for AI packages."""
    
    def __init__(self):
        self.output_dir = Path("data/alternative_signals")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Key AI/ML packages to track
        self.packages = [
            # Core ML frameworks
            "torch", "tensorflow", "jax",
            # LLM/NLP
            "transformers", "openai", "anthropic", "langchain", "llama-index",
            "sentence-transformers", "tiktoken", "tokenizers",
            # Vector DBs
            "chromadb", "pinecone-client", "weaviate-client", "qdrant-client",
            # ML tools
            "scikit-learn", "xgboost", "lightgbm", "catboost",
            # Data
            "pandas", "numpy", "polars",
            # AI agents
            "autogen", "crewai", "langsmith",
            # Image/Audio
            "diffusers", "stability-sdk", "elevenlabs",
            # Fine-tuning
            "peft", "trl", "accelerate", "bitsandbytes"
        ]
        
        self.base_url = "https://pypistats.org/api"
    
    def get_package_downloads(self, package: str, period: str = "last-week") -> Dict:
        """Get download stats for a package."""
        url = f"{self.base_url}/packages/{package}/recent"
        
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "package": package,
                    "downloads_last_day": data.get("data", {}).get("last_day", 0),
                    "downloads_last_week": data.get("data", {}).get("last_week", 0),
                    "downloads_last_month": data.get("data", {}).get("last_month", 0),
                }
            else:
                return {"package": package, "error": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"package": package, "error": str(e)}
    
    def calculate_growth(self, weekly: int, monthly: int) -> float:
        """Calculate weekly growth rate."""
        if monthly == 0:
            return 0
        # Approximate: compare weekly to weekly average from monthly
        weekly_avg = monthly / 4
        if weekly_avg == 0:
            return 0
        return round((weekly - weekly_avg) / weekly_avg * 100, 2)
    
    def run(self) -> Dict:
        """Run the PyPI trends scraper."""
        logger.info(f"Scraping PyPI stats for {len(self.packages)} packages")
        
        results = []
        for package in self.packages:
            stats = self.get_package_downloads(package)
            
            if "error" not in stats:
                weekly = stats.get("downloads_last_week", 0)
                monthly = stats.get("downloads_last_month", 0)
                growth = self.calculate_growth(weekly, monthly)
                
                stats["growth_rate"] = growth
                stats["momentum"] = (
                    "surging" if growth > 20 else
                    "growing" if growth > 5 else
                    "stable" if growth > -5 else
                    "declining"
                )
                
                logger.info(f"{package}: {weekly:,} weekly ({growth:+.1f}%)")
            
            results.append(stats)
        
        # Sort by weekly downloads
        results.sort(key=lambda x: x.get("downloads_last_week", 0), reverse=True)
        
        # Calculate scores (normalized 0-10)
        max_downloads = max(r.get("downloads_last_week", 1) for r in results)
        for r in results:
            weekly = r.get("downloads_last_week", 0)
            r["adoption_score"] = round((weekly / max_downloads) * 10, 2) if max_downloads > 0 else 0
        
        output = {
            "source": "pypi_trends",
            "timestamp": datetime.now().isoformat(),
            "packages": results,
            "summary": {
                "total_packages": len(results),
                "surging": len([r for r in results if r.get("momentum") == "surging"]),
                "growing": len([r for r in results if r.get("momentum") == "growing"]),
                "declining": len([r for r in results if r.get("momentum") == "declining"]),
                "top_5": [r["package"] for r in results[:5] if "error" not in r]
            }
        }
        
        # Save
        output_file = self.output_dir / f"pypi_trends_{datetime.now().strftime('%Y-%m-%d')}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2)
        
        logger.info(f"Saved PyPI trends to {output_file}")
        return output


def run() -> Dict:
    """Entry point for run_all_scrapers.py"""
    scraper = PyPITrendsScraper()
    return scraper.run()


if __name__ == "__main__":
    result = run()
    print(json.dumps(result.get("summary", {}), indent=2))
