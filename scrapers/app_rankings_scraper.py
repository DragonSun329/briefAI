# -*- coding: utf-8 -*-
"""
App Rankings Scraper

Scrapes AI app rankings from App Store and Play Store.
Tracks consumer AI adoption.
"""

import requests
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional
import json
import time
import re


class AppRankingsScraper:
    """Scraper for AI app store rankings."""
    
    # Known AI apps to track (bundle IDs / package names)
    AI_APPS = {
        # iOS bundle IDs
        "ios": {
            "com.openai.chat": "ChatGPT",
            "com.anthropic.claude": "Claude",
            "com.google.Gemini": "Google Gemini",
            "com.microsoft.copilot": "Microsoft Copilot",
            "ai.perplexity.app.ios": "Perplexity",
            "com.character.characterai": "Character.AI",
            "com.midjourney.ios": "Midjourney",
            "com.poe.ios": "Poe",
            "com.jasper.ios": "Jasper",
            "com.bing": "Bing",
        },
        # Android package names  
        "android": {
            "com.openai.chatgpt": "ChatGPT",
            "com.anthropic.claude": "Claude",
            "com.google.android.apps.bard": "Google Gemini",
            "com.microsoft.copilot": "Microsoft Copilot",
            "ai.perplexity.app.android": "Perplexity",
            "ai.character.app": "Character.AI",
            "com.zhiliaoapp.musically.go": "TikTok (AI features)",
        }
    }
    
    # iTunes API for iOS app lookup
    ITUNES_API = "https://itunes.apple.com/lookup"
    
    # App categories with AI relevance
    AI_CATEGORIES = ["Productivity", "Utilities", "Education", "Business", "Entertainment"]
    
    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or Path(__file__).parent.parent / "data" / "app_signals"
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def fetch_ios_app_info(self, bundle_id: str, app_name: str) -> Optional[Dict[str, Any]]:
        """Fetch iOS app info from iTunes API."""
        try:
            params = {"bundleId": bundle_id, "country": "us"}
            resp = requests.get(self.ITUNES_API, params=params, timeout=10)
            
            if resp.status_code != 200:
                return None
            
            data = resp.json()
            results = data.get("results", [])
            
            if not results:
                return None
            
            app = results[0]
            
            return {
                "id": bundle_id,
                "name": app.get("trackName", app_name),
                "developer": app.get("artistName", ""),
                "rating": app.get("averageUserRating", 0),
                "rating_count": app.get("userRatingCount", 0),
                "price": app.get("price", 0),
                "category": app.get("primaryGenreName", ""),
                "url": app.get("trackViewUrl", ""),
                "version": app.get("version", ""),
                "updated": app.get("currentVersionReleaseDate", ""),
                "platform": "ios",
            }
            
        except Exception as e:
            print(f"    Error fetching {app_name}: {e}")
            return None
    
    def search_ios_ai_apps(self, term: str = "AI assistant", limit: int = 25) -> List[Dict[str, Any]]:
        """Search for AI apps on iOS App Store."""
        try:
            url = "https://itunes.apple.com/search"
            params = {
                "term": term,
                "country": "us",
                "media": "software",
                "limit": limit,
            }
            
            resp = requests.get(url, params=params, timeout=15)
            
            if resp.status_code != 200:
                return []
            
            data = resp.json()
            results = data.get("results", [])
            
            apps = []
            for app in results:
                apps.append({
                    "id": app.get("bundleId", ""),
                    "name": app.get("trackName", ""),
                    "developer": app.get("artistName", ""),
                    "rating": app.get("averageUserRating", 0),
                    "rating_count": app.get("userRatingCount", 0),
                    "price": app.get("price", 0),
                    "category": app.get("primaryGenreName", ""),
                    "url": app.get("trackViewUrl", ""),
                    "platform": "ios",
                    "search_term": term,
                })
            
            return apps
            
        except Exception as e:
            print(f"    Error searching '{term}': {e}")
            return []
    
    def run(self) -> Dict[str, Any]:
        """Run app rankings scraper."""
        print("=" * 60)
        print("APP RANKINGS SCRAPER")
        print("=" * 60)
        
        results = {
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "tracked_apps": [],
            "search_results": [],
        }
        
        # Fetch known AI apps
        print("\nFetching tracked AI apps...")
        for bundle_id, app_name in self.AI_APPS["ios"].items():
            print(f"  {app_name}...")
            info = self.fetch_ios_app_info(bundle_id, app_name)
            if info:
                results["tracked_apps"].append(info)
                print(f"    Rating: {info['rating']:.1f} ({info['rating_count']:,} reviews)")
            time.sleep(0.3)
        
        # Search for AI apps
        print("\nSearching for AI apps...")
        search_terms = ["AI assistant", "ChatGPT", "AI chat", "AI writing", "AI image"]
        
        for term in search_terms:
            print(f"  Searching '{term}'...")
            apps = self.search_ios_ai_apps(term, limit=15)
            results["search_results"].extend(apps)
            time.sleep(0.5)
        
        # Dedupe search results
        seen = set()
        unique = []
        for app in results["search_results"]:
            if app["id"] not in seen:
                seen.add(app["id"])
                unique.append(app)
        results["search_results"] = unique
        
        print(f"  Found {len(unique)} unique apps")
        
        # Sort by rating count (popularity proxy)
        results["tracked_apps"] = sorted(
            results["tracked_apps"], 
            key=lambda x: -x.get("rating_count", 0)
        )
        results["search_results"] = sorted(
            results["search_results"],
            key=lambda x: -x.get("rating_count", 0)
        )
        
        # Save
        output_file = self.output_dir / f"apps_{datetime.now().strftime('%Y-%m-%d')}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"\nSaved to {output_file}")
        
        # Summary
        print(f"\n{'=' * 60}")
        print("TOP TRACKED AI APPS (by review count)")
        print(f"{'=' * 60}")
        for app in results["tracked_apps"][:10]:
            print(f"  {app['name']:25} {app['rating']:.1f}★ ({app['rating_count']:>10,} reviews)")
        
        print(f"\n{'=' * 60}")
        print("TOP SEARCH RESULTS (by review count)")
        print(f"{'=' * 60}")
        for app in results["search_results"][:10]:
            print(f"  {app['name'][:25]:25} {app['rating']:.1f}★ ({app['rating_count']:>10,} reviews)")
        
        return results


if __name__ == "__main__":
    scraper = AppRankingsScraper()
    scraper.run()
