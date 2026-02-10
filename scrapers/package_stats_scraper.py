# -*- coding: utf-8 -*-
"""
Package Stats Scraper

Scrapes download statistics from PyPI and npm for AI packages.
Tracks developer adoption trends.
"""

import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional
import json
import time


class PackageStatsScraper:
    """Scraper for PyPI and npm package statistics."""
    
    # AI-related PyPI packages to track
    PYPI_PACKAGES = [
        # Core ML
        "torch", "tensorflow", "jax", "numpy", "scipy",
        # LLM/NLP
        "transformers", "openai", "anthropic", "langchain", "llama-index",
        "sentence-transformers", "tiktoken", "tokenizers",
        # ML Tools
        "scikit-learn", "xgboost", "lightgbm", "catboost",
        "pandas", "polars", "dask",
        # Deep Learning
        "keras", "pytorch-lightning", "fastai",
        # MLOps
        "mlflow", "wandb", "optuna", "ray",
        # Computer Vision
        "opencv-python", "pillow", "torchvision",
        # Vector DBs
        "chromadb", "pinecone-client", "weaviate-client", "qdrant-client",
        # Agents
        "autogen", "crewai", "dspy-ai",
        # Inference
        "vllm", "text-generation-inference", "ollama",
    ]
    
    # AI-related npm packages
    NPM_PACKAGES = [
        "openai", "@anthropic-ai/sdk", "langchain",
        "@huggingface/inference", "transformers",
        "ai", "llamaindex", "@xenova/transformers",
        "tensorflow", "@tensorflow/tfjs",
        "ml5", "brain.js",
        "vectordb", "chromadb",
    ]
    
    # PyPI stats API (pypistats.org)
    PYPI_STATS_API = "https://pypistats.org/api/packages"
    
    # npm API
    NPM_API = "https://api.npmjs.org/downloads/point/last-week"
    
    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or Path(__file__).parent.parent / "data" / "package_signals"
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def fetch_pypi_stats(self, package: str) -> Optional[Dict[str, Any]]:
        """Fetch PyPI download stats for a package."""
        try:
            # Get recent downloads
            url = f"{self.PYPI_STATS_API}/{package}/recent"
            resp = requests.get(url, timeout=10)
            
            if resp.status_code != 200:
                return None
            
            data = resp.json().get("data", {})
            
            return {
                "package": package,
                "source": "pypi",
                "downloads_last_day": data.get("last_day", 0),
                "downloads_last_week": data.get("last_week", 0),
                "downloads_last_month": data.get("last_month", 0),
            }
            
        except Exception as e:
            return None
    
    def fetch_npm_stats(self, package: str) -> Optional[Dict[str, Any]]:
        """Fetch npm download stats for a package."""
        try:
            url = f"{self.NPM_API}/{package}"
            resp = requests.get(url, timeout=10)
            
            if resp.status_code != 200:
                return None
            
            data = resp.json()
            
            return {
                "package": package,
                "source": "npm",
                "downloads_last_week": data.get("downloads", 0),
            }
            
        except Exception as e:
            return None
    
    def run(self) -> Dict[str, Any]:
        """Run package stats scraper."""
        print("=" * 60)
        print("PACKAGE STATS SCRAPER")
        print("=" * 60)
        
        results = {
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "pypi": [],
            "npm": [],
        }
        
        # Fetch PyPI stats
        print("\nFetching PyPI stats...")
        for package in self.PYPI_PACKAGES:
            stats = self.fetch_pypi_stats(package)
            if stats:
                results["pypi"].append(stats)
                downloads = stats.get("downloads_last_week", 0)
                if downloads > 1000000:
                    print(f"  {package}: {downloads:,}/week")
            time.sleep(0.2)  # Rate limit
        
        print(f"  Got stats for {len(results['pypi'])} packages")
        
        # Fetch npm stats
        print("\nFetching npm stats...")
        for package in self.NPM_PACKAGES:
            stats = self.fetch_npm_stats(package)
            if stats:
                results["npm"].append(stats)
            time.sleep(0.1)
        
        print(f"  Got stats for {len(results['npm'])} packages")
        
        # Sort by downloads
        results["pypi"] = sorted(results["pypi"], key=lambda x: -x.get("downloads_last_week", 0))
        results["npm"] = sorted(results["npm"], key=lambda x: -x.get("downloads_last_week", 0))
        
        # Save
        output_file = self.output_dir / f"packages_{datetime.now().strftime('%Y-%m-%d')}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"\nSaved to {output_file}")
        
        # Summary
        print(f"\n{'=' * 60}")
        print("TOP PYPI PACKAGES (by weekly downloads)")
        print(f"{'=' * 60}")
        for p in results["pypi"][:15]:
            print(f"  {p['package']:25} {p['downloads_last_week']:>12,}/week")
        
        print(f"\n{'=' * 60}")
        print("TOP NPM PACKAGES (by weekly downloads)")
        print(f"{'=' * 60}")
        for p in results["npm"][:10]:
            print(f"  {p['package']:25} {p['downloads_last_week']:>12,}/week")
        
        return results


if __name__ == "__main__":
    scraper = PackageStatsScraper()
    scraper.run()
