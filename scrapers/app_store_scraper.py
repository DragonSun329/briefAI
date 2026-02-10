"""
App Store Rankings Scraper for AI Apps

Tracks AI app rankings on iOS App Store and Google Play Store
to monitor consumer AI adoption and app popularity.

Uses:
- iTunes Search API (free, no key)
- Google Play unofficial scraping
"""

import requests
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
import time


class AppStoreScraper:
    """Scraper for AI app rankings on mobile app stores."""

    # iTunes Search API
    ITUNES_SEARCH_URL = "https://itunes.apple.com/search"
    ITUNES_LOOKUP_URL = "https://itunes.apple.com/lookup"
    
    # AI apps to track (App Store IDs)
    TRACKED_IOS_APPS = {
        "chatgpt": "6448311069",
        "perplexity": "1668000334",
        "character_ai": "1607772904",
        "claude": "6473753684",
        "copilot": "6472538445",  # Microsoft Copilot
        "gemini": "1514817865",  # Google Gemini (formerly Bard)
        "bing": "345323231",  # Bing with AI
        "poe": "1640745955",  # Poe by Quora
        "replika": "1158555867",
        "jasper": "6443920334",
        "notion_ai": "1232780281",  # Notion
        "grammarly": "1158877342",
        "dall_e": "6448311069",  # Part of ChatGPT
        "lensa": "1436732536",
        "remini": "1470373330",
        "photomath": "919087726",
        "socratic": "1014164514",  # Google Socratic
        "duolingo": "570060128",  # AI-powered learning
    }

    # AI-related search terms
    AI_SEARCH_TERMS = [
        "chatgpt",
        "ai assistant",
        "ai chat",
        "artificial intelligence",
        "ai image generator",
        "ai writing",
        "ai photo",
        "chatbot",
        "gpt",
    ]

    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or Path(__file__).parent.parent / "data" / "alternative_signals"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "BriefAI/1.0",
            "Accept": "application/json",
        })

    def lookup_ios_app(self, app_id: str, country: str = "us") -> Optional[Dict[str, Any]]:
        """Look up an iOS app by ID."""
        params = {
            "id": app_id,
            "country": country,
            "entity": "software",
        }
        
        try:
            resp = self.session.get(self.ITUNES_LOOKUP_URL, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])
            return results[0] if results else None
        except Exception as e:
            print(f"  Error looking up app {app_id}: {e}")
            return None

    def search_ios_apps(self, term: str, limit: int = 25, country: str = "us") -> List[Dict[str, Any]]:
        """Search iOS apps by term."""
        params = {
            "term": term,
            "country": country,
            "entity": "software",
            "limit": limit,
        }
        
        try:
            resp = self.session.get(self.ITUNES_SEARCH_URL, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            return data.get("results", [])
        except Exception as e:
            print(f"  Error searching for '{term}': {e}")
            return []

    def fetch_tracked_apps(self) -> List[Dict[str, Any]]:
        """Fetch data for all tracked AI apps."""
        apps = []
        
        print("  Fetching tracked iOS apps...")
        for name, app_id in self.TRACKED_IOS_APPS.items():
            app_data = self.lookup_ios_app(app_id)
            if app_data:
                app_data["tracked_name"] = name
                apps.append(app_data)
            time.sleep(0.2)  # Rate limit
        
        return apps

    def search_ai_apps(self) -> List[Dict[str, Any]]:
        """Search for AI-related apps."""
        all_apps = []
        seen_ids = set()
        
        print("  Searching AI apps...")
        for term in self.AI_SEARCH_TERMS:
            print(f"    Searching: {term}")
            results = self.search_ios_apps(term, limit=20)
            
            for app in results:
                app_id = app.get("trackId")
                if app_id and app_id not in seen_ids:
                    seen_ids.add(app_id)
                    all_apps.append(app)
            
            time.sleep(0.3)
        
        return all_apps

    def extract_app_data(self, app: Dict[str, Any]) -> Dict[str, Any]:
        """Extract relevant fields from app data."""
        return {
            "id": app.get("trackId"),
            "name": app.get("trackName", ""),
            "tracked_name": app.get("tracked_name"),
            "bundle_id": app.get("bundleId", ""),
            "developer": app.get("artistName", ""),
            "developer_id": app.get("artistId"),
            "description": app.get("description", "")[:500] if app.get("description") else "",
            "price": app.get("price", 0),
            "currency": app.get("currency", "USD"),
            "rating": app.get("averageUserRating", 0),
            "rating_count": app.get("userRatingCount", 0),
            "rating_count_current": app.get("userRatingCountForCurrentVersion", 0),
            "version": app.get("version", ""),
            "release_date": app.get("releaseDate", ""),
            "current_release_date": app.get("currentVersionReleaseDate", ""),
            "content_rating": app.get("contentAdvisoryRating", ""),
            "genres": app.get("genres", []),
            "primary_genre": app.get("primaryGenreName", ""),
            "app_store_url": app.get("trackViewUrl", ""),
            "icon_url": app.get("artworkUrl100", ""),
            "file_size_bytes": app.get("fileSizeBytes", 0),
        }

    def categorize_app(self, app: Dict[str, Any]) -> str:
        """Categorize an app into AI trend buckets."""
        name = (app.get("name") or "").lower()
        description = (app.get("description") or "").lower()
        genres = [g.lower() for g in app.get("genres", [])]
        combined = f"{name} {description} {' '.join(genres)}"

        # Chat / LLM assistants
        if any(x in combined for x in ["chatgpt", "claude", "gpt", "copilot", "gemini", "poe", "chat"]):
            return "llm-foundation"

        # AI search / knowledge
        if any(x in combined for x in ["perplexity", "search", "knowledge", "research"]):
            return "ai-agents"

        # Image generation
        if any(x in combined for x in ["image generat", "ai art", "dall-e", "lensa", "remini", "photo"]):
            return "ai-image-generation"

        # Writing / content
        if any(x in combined for x in ["writing", "grammarly", "jasper", "content", "copywriting"]):
            return "ai-coding"

        # Character AI / social
        if any(x in combined for x in ["character", "replika", "companion", "roleplay"]):
            return "ai-general"

        # Education
        if any(x in combined for x in ["learn", "education", "study", "tutor", "math", "language"]):
            return "ai-general"

        return "ai-general"

    def calculate_rankings(self, apps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Calculate rankings based on rating count (proxy for downloads)."""
        # Sort by rating count as proxy for popularity
        sorted_apps = sorted(
            apps,
            key=lambda x: x.get("rating_count", 0),
            reverse=True
        )
        
        for i, app in enumerate(sorted_apps, 1):
            app["estimated_rank"] = i
        
        return sorted_apps

    def compute_signals(self, apps: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Compute trend signals from app store data."""
        bucket_signals = {}
        total_ratings = 0
        free_count = 0
        paid_count = 0

        for app in apps:
            bucket = app.get("bucket", "ai-general")
            rating_count = app.get("rating_count", 0)
            price = app.get("price", 0)
            rating = app.get("rating", 0)

            if bucket not in bucket_signals:
                bucket_signals[bucket] = {
                    "app_count": 0,
                    "total_ratings": 0,
                    "avg_rating": 0,
                    "ratings_list": [],
                    "top_apps": [],
                }

            bucket_signals[bucket]["app_count"] += 1
            bucket_signals[bucket]["total_ratings"] += rating_count
            bucket_signals[bucket]["ratings_list"].append(rating)
            total_ratings += rating_count
            
            if price == 0:
                free_count += 1
            else:
                paid_count += 1

            # Top apps
            if len(bucket_signals[bucket]["top_apps"]) < 5:
                bucket_signals[bucket]["top_apps"].append({
                    "name": app.get("name"),
                    "developer": app.get("developer"),
                    "rating": rating,
                    "rating_count": rating_count,
                    "estimated_rank": app.get("estimated_rank"),
                })

        # Calculate averages and interpretations
        for bucket, data in bucket_signals.items():
            ratings = data.pop("ratings_list", [])
            data["avg_rating"] = sum(ratings) / len(ratings) if ratings else 0
            
            if total_ratings > 0:
                data["ratings_share"] = data["total_ratings"] / total_ratings
            else:
                data["ratings_share"] = 0

            # Interpretation based on total engagement
            ratings = data["total_ratings"]
            if ratings > 1000000:
                data["signal_interpretation"] = "Dominant - massive consumer adoption"
            elif ratings > 100000:
                data["signal_interpretation"] = "Strong - significant consumer traction"
            elif ratings > 10000:
                data["signal_interpretation"] = "Growing - notable consumer interest"
            else:
                data["signal_interpretation"] = "Emerging - early stage adoption"

        return {
            "bucket_signals": bucket_signals,
            "total_apps": len(apps),
            "total_ratings": total_ratings,
            "free_apps": free_count,
            "paid_apps": paid_count,
        }

    def run(self, save: bool = True) -> Dict[str, Any]:
        """Run the scraper and return results."""
        print("Fetching AI app rankings from App Store...")
        
        # Fetch tracked apps
        tracked = self.fetch_tracked_apps()
        print(f"  Retrieved {len(tracked)} tracked apps")
        
        # Search for more AI apps
        searched = self.search_ai_apps()
        print(f"  Found {len(searched)} apps via search")
        
        # Combine and dedupe
        seen_ids = set()
        all_apps = []
        
        for app in tracked + searched:
            app_id = app.get("trackId")
            if app_id and app_id not in seen_ids:
                seen_ids.add(app_id)
                all_apps.append(app)

        # Process apps
        processed = []
        for app in all_apps:
            data = self.extract_app_data(app)
            data["bucket"] = self.categorize_app(app)
            processed.append(data)

        # Calculate rankings
        processed = self.calculate_rankings(processed)

        # Compute signals
        signals = self.compute_signals(processed)

        result = {
            "source": "app_store",
            "scraped_at": datetime.now().isoformat(),
            "total_apps": len(processed),
            "apps": processed[:50],  # Limit stored apps
            "signals": signals,
            "bucket_signals": signals.get("bucket_signals", {}),
        }

        if save:
            date_str = datetime.now().strftime("%Y-%m-%d")
            output_file = self.output_dir / f"app_store_{date_str}.json"
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, default=str)
            print(f"Saved to {output_file}")

        return result


def main():
    """Main entry point."""
    scraper = AppStoreScraper()
    result = scraper.run()

    print("\n" + "=" * 60)
    print("APP STORE AI RANKINGS SUMMARY")
    print("=" * 60)
    print(f"Total AI apps: {result['total_apps']}")
    print(f"Total ratings: {result['signals']['total_ratings']:,}")

    print("\nTop 15 AI Apps by Rating Count:")
    print("-" * 60)
    for i, app in enumerate(result['apps'][:15], 1):
        rating_str = f"⭐{app['rating']:.1f}" if app.get('rating') else "N/A"
        print(f"{i}. {app['name']}")
        print(f"   Developer: {app['developer']} | {rating_str} ({app['rating_count']:,} ratings)")
        print(f"   Bucket: {app['bucket']}")
        print()

    print("\nSignals by Bucket:")
    print("-" * 60)
    for bucket, data in sorted(result['bucket_signals'].items(),
                               key=lambda x: -x[1]['total_ratings']):
        print(f"{bucket}:")
        print(f"   Apps: {data['app_count']} | Total ratings: {data['total_ratings']:,}")
        print(f"   Avg rating: {data['avg_rating']:.2f}⭐")
        print(f"   Signal: {data['signal_interpretation']}")
        print()


if __name__ == "__main__":
    main()
