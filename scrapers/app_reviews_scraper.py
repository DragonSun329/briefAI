# -*- coding: utf-8 -*-
"""
App Reviews Scraper with LLM Analysis

Scrapes app reviews and uses LLM to extract:
- Key features mentioned
- Pros and cons
- Common complaints
- Feature requests
- Sentiment trends
"""

import requests
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional
import json
import time
import os
from dataclasses import dataclass, asdict


@dataclass
class ReviewAnalysis:
    """LLM-extracted review analysis."""
    app_name: str
    app_id: str
    review_count: int
    avg_rating: float
    key_features: List[str]
    pros: List[str]
    cons: List[str]
    common_complaints: List[str]
    feature_requests: List[str]
    sentiment_summary: str
    analyzed_at: str


class AppReviewsScraper:
    """Scraper for app reviews with LLM analysis."""
    
    # AI apps to analyze (App Store IDs)
    AI_APPS = {
        "6448311069": {"name": "ChatGPT", "company": "OpenAI"},
        "6473753684": {"name": "Claude", "company": "Anthropic"},
        "6477489129": {"name": "Google Gemini", "company": "Google"},
        "6472538445": {"name": "Microsoft Copilot", "company": "Microsoft"},
        "1668000334": {"name": "Perplexity", "company": "Perplexity AI"},
        "1607772368": {"name": "Character.AI", "company": "Character Technologies"},
        "6451491050": {"name": "Poe", "company": "Quora"},
        "6499579167": {"name": "Grok", "company": "xAI"},
    }
    
    # iTunes API endpoints
    ITUNES_LOOKUP = "https://itunes.apple.com/lookup"
    ITUNES_REVIEWS = "https://itunes.apple.com/us/rss/customerreviews/id={app_id}/sortBy=mostRecent/json"
    
    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or Path(__file__).parent.parent / "data" / "review_signals"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # LLM client (OpenAI or Anthropic)
        self.llm_client = None
        self._init_llm()
    
    def _init_llm(self):
        """Initialize LLM client."""
        # Load from .env file
        env_path = Path(__file__).parent.parent / ".env"
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    if "=" in line and not line.startswith("#"):
                        key, value = line.strip().split("=", 1)
                        os.environ[key] = value
        
        # Try OpenRouter first (has many free models)
        openrouter_key = os.environ.get("OPENROUTER_API_KEY")
        if openrouter_key:
            try:
                import openai
                self.llm_client = openai.OpenAI(
                    api_key=openrouter_key,
                    base_url="https://openrouter.ai/api/v1"
                )
                self.llm_provider = "openrouter"
                self.llm_model = "google/gemini-2.0-flash-001"  # Fast and free
                print("Using OpenRouter (Gemini Flash) for analysis")
                return
            except ImportError:
                pass
        
        # Try Anthropic
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
        if anthropic_key:
            try:
                import anthropic
                self.llm_client = anthropic.Anthropic(api_key=anthropic_key)
                self.llm_provider = "anthropic"
                self.llm_model = "claude-3-5-haiku-20241022"
                print("Using Anthropic Claude for analysis")
                return
            except ImportError:
                pass
        
        # Fall back to OpenAI
        openai_key = os.environ.get("OPENAI_API_KEY")
        if openai_key:
            try:
                import openai
                self.llm_client = openai.OpenAI(api_key=openai_key)
                self.llm_provider = "openai"
                self.llm_model = "gpt-4o-mini"
                print("Using OpenAI for analysis")
                return
            except ImportError:
                pass
        
        print("Warning: No LLM API key found. Analysis will be skipped.")
        self.llm_provider = None
    
    def fetch_app_info(self, app_id: str) -> Optional[Dict[str, Any]]:
        """Fetch app metadata from iTunes."""
        try:
            resp = requests.get(self.ITUNES_LOOKUP, params={"id": app_id}, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("results"):
                    return data["results"][0]
        except Exception as e:
            print(f"    Error fetching app info: {e}")
        return None
    
    def fetch_reviews(self, app_id: str, pages: int = 3) -> List[Dict[str, Any]]:
        """Fetch recent reviews from iTunes RSS."""
        all_reviews = []
        
        for page in range(1, pages + 1):
            try:
                url = f"https://itunes.apple.com/us/rss/customerreviews/page={page}/id={app_id}/sortBy=mostRecent/json"
                resp = requests.get(url, timeout=15)
                
                if resp.status_code != 200:
                    continue
                
                data = resp.json()
                entries = data.get("feed", {}).get("entry", [])
                
                # Skip first entry (app metadata)
                for entry in entries[1:] if len(entries) > 1 else []:
                    review = {
                        "id": entry.get("id", {}).get("label", ""),
                        "title": entry.get("title", {}).get("label", ""),
                        "content": entry.get("content", {}).get("label", ""),
                        "rating": int(entry.get("im:rating", {}).get("label", 0)),
                        "author": entry.get("author", {}).get("name", {}).get("label", ""),
                        "version": entry.get("im:version", {}).get("label", ""),
                    }
                    all_reviews.append(review)
                
                time.sleep(0.3)
                
            except Exception as e:
                print(f"    Error fetching reviews page {page}: {e}")
        
        return all_reviews
    
    def analyze_reviews_with_llm(self, app_name: str, reviews: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Use LLM to analyze reviews and extract insights."""
        if not self.llm_client or not reviews:
            return {
                "key_features": [],
                "pros": [],
                "cons": [],
                "common_complaints": [],
                "feature_requests": [],
                "sentiment_summary": "Analysis skipped - no LLM available",
            }
        
        # Prepare review text (limit to avoid token limits)
        review_texts = []
        for r in reviews[:50]:  # Max 50 reviews
            rating = "★" * r["rating"]
            review_texts.append(f"[{rating}] {r['title']}\n{r['content'][:300]}")
        
        reviews_combined = "\n\n---\n\n".join(review_texts)
        
        prompt = f"""Analyze these app reviews for "{app_name}" and extract structured insights.

REVIEWS:
{reviews_combined}

Provide your analysis in the following JSON format:
{{
    "key_features": ["list of 5-8 main features users mention"],
    "pros": ["list of 5-8 things users love"],
    "cons": ["list of 5-8 things users dislike"],
    "common_complaints": ["list of 3-5 most frequent complaints"],
    "feature_requests": ["list of 3-5 features users want"],
    "sentiment_summary": "2-3 sentence summary of overall sentiment and trends"
}}

Return ONLY the JSON, no other text."""

        try:
            if self.llm_provider == "anthropic":
                response = self.llm_client.messages.create(
                    model=self.llm_model,
                    max_tokens=1500,
                    messages=[{"role": "user", "content": prompt}]
                )
                result_text = response.content[0].text
            else:  # openai or openrouter
                response = self.llm_client.chat.completions.create(
                    model=self.llm_model,
                    max_tokens=1500,
                    messages=[{"role": "user", "content": prompt}]
                )
                result_text = response.choices[0].message.content
            
            # Parse JSON response
            # Find JSON in response
            start = result_text.find("{")
            end = result_text.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(result_text[start:end])
            
        except Exception as e:
            print(f"    LLM analysis error: {e}")
        
        return {
            "key_features": [],
            "pros": [],
            "cons": [],
            "common_complaints": [],
            "feature_requests": [],
            "sentiment_summary": f"Analysis failed: {str(e)[:50]}",
        }
    
    def run(self) -> Dict[str, Any]:
        """Run review scraper with LLM analysis."""
        print("=" * 60)
        print("APP REVIEWS SCRAPER WITH LLM ANALYSIS")
        print("=" * 60)
        
        results = {
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "apps": [],
        }
        
        for app_id, app_info in self.AI_APPS.items():
            app_name = app_info["name"]
            print(f"\n{'─' * 60}")
            print(f"Processing: {app_name}")
            print(f"{'─' * 60}")
            
            # Fetch app metadata
            print("  Fetching app info...")
            metadata = self.fetch_app_info(app_id)
            
            # Fetch reviews
            print("  Fetching reviews...")
            reviews = self.fetch_reviews(app_id, pages=3)
            print(f"    Got {len(reviews)} reviews")
            
            if not reviews:
                continue
            
            # Calculate basic stats
            avg_rating = sum(r["rating"] for r in reviews) / len(reviews) if reviews else 0
            rating_dist = {i: sum(1 for r in reviews if r["rating"] == i) for i in range(1, 6)}
            
            # LLM analysis
            print("  Analyzing with LLM...")
            analysis = self.analyze_reviews_with_llm(app_name, reviews)
            
            # Compile results
            app_result = {
                "app_id": app_id,
                "app_name": app_name,
                "company": app_info["company"],
                "current_rating": metadata.get("averageUserRating", 0) if metadata else 0,
                "total_reviews": metadata.get("userRatingCount", 0) if metadata else 0,
                "reviews_analyzed": len(reviews),
                "avg_rating_sample": round(avg_rating, 2),
                "rating_distribution": rating_dist,
                "analysis": analysis,
                "sample_reviews": [
                    {"rating": r["rating"], "title": r["title"], "content": r["content"][:200]}
                    for r in reviews[:5]
                ],
            }
            
            results["apps"].append(app_result)
            
            # Print summary
            print(f"\n  Analysis Summary:")
            print(f"    Rating: {app_result['current_rating']:.1f}★ ({app_result['total_reviews']:,} total)")
            print(f"    Sample avg: {avg_rating:.1f}★ ({len(reviews)} reviews)")
            if analysis.get("pros"):
                print(f"    Top pros: {', '.join(analysis['pros'][:3])}")
            if analysis.get("cons"):
                print(f"    Top cons: {', '.join(analysis['cons'][:3])}")
            
            time.sleep(1)  # Rate limit
        
        # Save results
        output_file = self.output_dir / f"reviews_{datetime.now().strftime('%Y-%m-%d')}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"\n{'=' * 60}")
        print(f"Saved to {output_file}")
        print(f"{'=' * 60}")
        
        # Final summary
        print(f"\nApps analyzed: {len(results['apps'])}")
        for app in results["apps"]:
            print(f"  {app['app_name']}: {app['current_rating']:.1f}★")
            if app["analysis"].get("sentiment_summary"):
                print(f"    → {app['analysis']['sentiment_summary'][:80]}...")
        
        return results


if __name__ == "__main__":
    scraper = AppReviewsScraper()
    scraper.run()
