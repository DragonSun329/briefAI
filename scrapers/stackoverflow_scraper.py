"""
Stack Overflow Trends Scraper

Tracks question volume and trends for AI-related tags on Stack Overflow
to monitor developer interest and adoption patterns.

Stack Exchange API: https://api.stackexchange.com
- Free tier: 300 requests/day without key, 10000/day with key
"""

import requests
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional
import time


class StackOverflowScraper:
    """Scraper for Stack Overflow AI question trends."""

    BASE_URL = "https://api.stackexchange.com/2.3"

    # AI-related tags to track
    AI_TAGS = [
        # LLMs and Chatbots
        "chatgpt",
        "openai-api",
        "gpt-4",
        "gpt-3",
        "langchain",
        "llm",
        "large-language-model",
        # ML Frameworks
        "pytorch",
        "tensorflow",
        "keras",
        "huggingface-transformers",
        "transformers",
        "scikit-learn",
        # Specific technologies
        "machine-learning",
        "deep-learning",
        "neural-network",
        "natural-language-processing",
        "nlp",
        "computer-vision",
        "opencv",
        # Vector DBs / RAG
        "pinecone",
        "chromadb",
        "vector-database",
        "embeddings",
        "sentence-transformers",
        # AI Agents
        "autogpt",
        "langchain-agents",
        # Image generation
        "stable-diffusion",
        "dall-e",
        "midjourney",
        # Other
        "reinforcement-learning",
        "generative-ai",
        "artificial-intelligence",
    ]

    def __init__(self, api_key: Optional[str] = None, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or Path(__file__).parent.parent / "data" / "alternative_signals"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "BriefAI/1.0",
            "Accept": "application/json",
        })

    def get_tag_info(self, tags: List[str]) -> List[Dict[str, Any]]:
        """Get info for multiple tags."""
        # Stack Exchange API allows up to 20 tags per request
        tag_str = ";".join(tags[:20])
        url = f"{self.BASE_URL}/tags/{tag_str}/info"
        
        params = {
            "site": "stackoverflow",
            "filter": "default",
        }
        if self.api_key:
            params["key"] = self.api_key
        
        try:
            resp = self.session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            return data.get("items", [])
        except Exception as e:
            print(f"  Error fetching tag info: {e}")
            return []

    def get_recent_questions(self, tag: str, days_back: int = 7) -> Dict[str, Any]:
        """Get recent question count for a tag."""
        url = f"{self.BASE_URL}/questions"
        
        # Calculate date range
        end_date = int(datetime.now().timestamp())
        start_date = int((datetime.now() - timedelta(days=days_back)).timestamp())
        
        params = {
            "site": "stackoverflow",
            "tagged": tag,
            "fromdate": start_date,
            "todate": end_date,
            "filter": "total",
        }
        if self.api_key:
            params["key"] = self.api_key
        
        try:
            resp = self.session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            return {
                "tag": tag,
                "questions_last_week": data.get("total", 0),
            }
        except Exception as e:
            print(f"  Error fetching questions for {tag}: {e}")
            return {
                "tag": tag,
                "questions_last_week": 0,
                "error": str(e),
            }

    def get_trending_questions(self, tag: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Get trending/hot questions for a tag."""
        url = f"{self.BASE_URL}/questions"
        
        params = {
            "site": "stackoverflow",
            "tagged": tag,
            "sort": "activity",
            "order": "desc",
            "pagesize": limit,
        }
        if self.api_key:
            params["key"] = self.api_key
        
        try:
            resp = self.session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            return data.get("items", [])
        except Exception as e:
            print(f"  Error fetching trending for {tag}: {e}")
            return []

    def fetch_all_tag_stats(self) -> List[Dict[str, Any]]:
        """Fetch statistics for all tracked tags."""
        all_stats = []
        
        # Get tag info in batches
        print("  Fetching tag info...")
        for i in range(0, len(self.AI_TAGS), 20):
            batch = self.AI_TAGS[i:i+20]
            tag_infos = self.get_tag_info(batch)
            
            for info in tag_infos:
                tag_name = info.get("name", "")
                all_stats.append({
                    "tag": tag_name,
                    "total_questions": info.get("count", 0),
                    "is_moderator_only": info.get("is_moderator_only", False),
                    "is_required": info.get("is_required", False),
                })
            
            time.sleep(0.5)  # Rate limit
        
        # Get recent question counts
        print("  Fetching recent question counts...")
        for stat in all_stats:
            tag = stat["tag"]
            recent = self.get_recent_questions(tag, days_back=7)
            stat["questions_last_week"] = recent.get("questions_last_week", 0)
            
            # Also get previous week for growth calculation
            recent_prev = self.get_recent_questions(tag, days_back=14)
            prev_week = recent_prev.get("questions_last_week", 0) - stat["questions_last_week"]
            stat["questions_prev_week"] = max(0, prev_week)
            
            time.sleep(0.3)  # Rate limit
        
        return all_stats

    def calculate_growth_rates(self, stats: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Calculate week-over-week growth rates."""
        for item in stats:
            curr_week = item.get("questions_last_week", 0)
            prev_week = item.get("questions_prev_week", 0)
            
            if prev_week > 0:
                growth_rate = (curr_week - prev_week) / prev_week
                item["wow_growth_rate"] = round(growth_rate, 4)
            elif curr_week > 0:
                item["wow_growth_rate"] = 1.0  # New activity
            else:
                item["wow_growth_rate"] = 0
            
            # Categorize
            item["bucket"] = self.categorize_tag(item["tag"])
        
        return stats

    def categorize_tag(self, tag: str) -> str:
        """Categorize a tag into AI trend buckets."""
        tag_lower = tag.lower()

        # LLM / ChatGPT
        if any(x in tag_lower for x in ["chatgpt", "gpt-", "openai", "llm", "large-language"]):
            return "llm-foundation"

        # Agent frameworks
        if any(x in tag_lower for x in ["langchain", "autogpt", "agent"]):
            return "ai-agents"

        # Deep learning frameworks
        if any(x in tag_lower for x in ["pytorch", "tensorflow", "keras", "transformers", "huggingface"]):
            return "llm-foundation"

        # Computer vision
        if any(x in tag_lower for x in ["opencv", "computer-vision", "yolo", "image"]):
            return "computer-vision"

        # NLP
        if any(x in tag_lower for x in ["nlp", "natural-language", "sentence-transformer"]):
            return "llm-foundation"

        # Vector DBs / Embeddings
        if any(x in tag_lower for x in ["pinecone", "chroma", "vector", "embedding"]):
            return "ai-infrastructure"

        # Image generation
        if any(x in tag_lower for x in ["stable-diffusion", "dall-e", "midjourney"]):
            return "ai-image-generation"

        # General
        if any(x in tag_lower for x in ["machine-learning", "deep-learning", "neural"]):
            return "ai-general"

        return "ai-general"

    def compute_signals(self, stats: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Compute trend signals from Stack Overflow data."""
        bucket_signals = {}

        for item in stats:
            bucket = item.get("bucket", "ai-general")
            questions = item.get("questions_last_week", 0)
            growth = item.get("wow_growth_rate", 0)

            if bucket not in bucket_signals:
                bucket_signals[bucket] = {
                    "total_weekly_questions": 0,
                    "tag_count": 0,
                    "avg_growth_rate": 0,
                    "growth_rates": [],
                    "top_tags": [],
                }

            bucket_signals[bucket]["total_weekly_questions"] += questions
            bucket_signals[bucket]["tag_count"] += 1
            bucket_signals[bucket]["growth_rates"].append(growth)
            bucket_signals[bucket]["top_tags"].append({
                "tag": item["tag"],
                "weekly_questions": questions,
                "total_questions": item.get("total_questions", 0),
                "growth_rate": growth,
            })

        # Calculate averages and interpretations
        for bucket, data in bucket_signals.items():
            rates = data.pop("growth_rates", [])
            data["avg_growth_rate"] = sum(rates) / len(rates) if rates else 0
            
            # Sort top tags by weekly questions
            data["top_tags"] = sorted(
                data["top_tags"],
                key=lambda x: x["weekly_questions"],
                reverse=True
            )[:5]

            # Weighted sentiment based on activity and growth
            activity = data["total_weekly_questions"]
            growth = data["avg_growth_rate"]
            
            # Sentiment: combination of absolute activity and growth
            if activity > 500 and growth > 0.1:
                data["weighted_sentiment"] = 0.8
                data["signal_interpretation"] = "Hot topic - explosive developer interest"
            elif activity > 200 or growth > 0.2:
                data["weighted_sentiment"] = 0.5
                data["signal_interpretation"] = "Growing topic - strong momentum"
            elif activity > 50 and growth > 0:
                data["weighted_sentiment"] = 0.2
                data["signal_interpretation"] = "Active topic - steady interest"
            elif growth < -0.1:
                data["weighted_sentiment"] = -0.3
                data["signal_interpretation"] = "Declining topic - waning interest"
            else:
                data["weighted_sentiment"] = 0
                data["signal_interpretation"] = "Stable topic - mature adoption"

        return {
            "bucket_signals": bucket_signals,
        }

    def run(self, save: bool = True) -> Dict[str, Any]:
        """Run the scraper and return results."""
        print("Fetching Stack Overflow AI tag trends...")
        
        # Fetch all stats
        stats = self.fetch_all_tag_stats()
        print(f"  Retrieved stats for {len(stats)} tags")

        # Calculate growth rates
        stats = self.calculate_growth_rates(stats)

        # Sort by weekly questions
        stats.sort(key=lambda x: x.get("questions_last_week", 0), reverse=True)

        # Compute signals
        signals = self.compute_signals(stats)

        result = {
            "source": "stackoverflow",
            "scraped_at": datetime.now().isoformat(),
            "total_tags": len(stats),
            "tags": stats,
            "signals": signals,
            "bucket_signals": signals.get("bucket_signals", {}),
        }

        if save:
            date_str = datetime.now().strftime("%Y-%m-%d")
            output_file = self.output_dir / f"stackoverflow_{date_str}.json"
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, default=str)
            print(f"Saved to {output_file}")

        return result


def main():
    """Main entry point."""
    import os
    api_key = os.environ.get("STACKEXCHANGE_API_KEY")
    
    scraper = StackOverflowScraper(api_key=api_key)
    result = scraper.run()

    print("\n" + "=" * 60)
    print("STACK OVERFLOW AI TRENDS SUMMARY")
    print("=" * 60)
    print(f"Total tags tracked: {result['total_tags']}")

    print("\nTop 15 Tags by Weekly Questions:")
    print("-" * 60)
    for i, tag in enumerate(result['tags'][:15], 1):
        growth_str = f"{tag['wow_growth_rate']*100:+.1f}%" if tag.get('wow_growth_rate') else "N/A"
        print(f"{i}. [{tag['tag']}]")
        print(f"   Weekly: {tag['questions_last_week']} | Total: {tag['total_questions']:,} | Growth: {growth_str}")
        print()

    print("\nSignals by Bucket:")
    print("-" * 60)
    for bucket, data in sorted(result['bucket_signals'].items(),
                               key=lambda x: -x[1]['total_weekly_questions']):
        print(f"{bucket}:")
        print(f"   Tags: {data['tag_count']} | Weekly questions: {data['total_weekly_questions']}")
        print(f"   Avg growth: {data['avg_growth_rate']*100:+.1f}%")
        print(f"   Sentiment: {data['weighted_sentiment']:+.2f}")
        print(f"   Signal: {data['signal_interpretation']}")
        print()


if __name__ == "__main__":
    main()
