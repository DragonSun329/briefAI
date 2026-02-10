"""
HackerNews Scraper for AI Sentiment

Scrapes AI-related discussions from HackerNews using the Algolia API
to track developer and tech community sentiment.
"""

import requests
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional
from collections import Counter


class HackerNewsScraper:
    """Scraper for HackerNews AI discussions."""

    # Algolia HN Search API
    BASE_URL = "https://hn.algolia.com/api/v1"

    AI_SEARCH_TERMS = [
        "artificial intelligence",
        "machine learning",
        "GPT",
        "OpenAI",
        "Anthropic",
        "Claude AI",
        "LLM",
        "ChatGPT",
        "Gemini AI",
        "AI model",
        "deep learning",
        "neural network",
        "AGI",
        "AI safety",
    ]

    AI_KEYWORDS = [
        'ai', 'artificial intelligence', 'machine learning', 'ml', 'deep learning',
        'neural network', 'llm', 'large language model', 'gpt', 'chatgpt',
        'openai', 'anthropic', 'claude', 'gemini', 'deepmind',
        'agi', 'alignment', 'transformer',
    ]

    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or Path(__file__).parent.parent / "data" / "alternative_signals"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def search_stories(self, query: str, tags: str = "story",
                       num_days: int = 7, hits_per_page: int = 50) -> List[Dict[str, Any]]:
        """Search HN stories via Algolia API."""
        url = f"{self.BASE_URL}/search"

        # Calculate timestamp for date filter
        timestamp = int((datetime.now() - timedelta(days=num_days)).timestamp())

        params = {
            "query": query,
            "tags": tags,
            "numericFilters": f"created_at_i>{timestamp}",
            "hitsPerPage": hits_per_page,
        }

        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            return data.get("hits", [])
        except Exception as e:
            print(f"Error searching HN for '{query}': {e}")
            return []

    def fetch_ai_stories(self, num_days: int = 7) -> List[Dict[str, Any]]:
        """Fetch AI-related stories from the past N days."""
        all_stories = []
        seen_ids = set()

        for term in self.AI_SEARCH_TERMS:
            print(f"  Searching: {term}")
            stories = self.search_stories(term, num_days=num_days, hits_per_page=30)
            for story in stories:
                story_id = story.get("objectID")
                if story_id and story_id not in seen_ids:
                    seen_ids.add(story_id)
                    all_stories.append(story)

        return all_stories

    def is_ai_related(self, story: Dict[str, Any]) -> bool:
        """Verify a story is actually AI-related."""
        title = story.get("title", "").lower()
        text = story.get("story_text", "").lower() if story.get("story_text") else ""
        combined = f"{title} {text}"

        for keyword in self.AI_KEYWORDS:
            if keyword in combined:
                return True
        return False

    def extract_story_data(self, story: Dict[str, Any]) -> Dict[str, Any]:
        """Extract relevant fields from a story."""
        return {
            "id": story.get("objectID"),
            "title": story.get("title"),
            "url": story.get("url"),
            "hn_url": f"https://news.ycombinator.com/item?id={story.get('objectID')}",
            "points": story.get("points", 0),
            "num_comments": story.get("num_comments", 0),
            "author": story.get("author"),
            "created_at": story.get("created_at"),
            "created_at_i": story.get("created_at_i"),
        }

    def categorize_story(self, story: Dict[str, Any]) -> Optional[str]:
        """Categorize a story into AI trend buckets."""
        title = story.get("title", "").lower()

        if not self.is_ai_related(story):
            return None

        # Company-specific
        if any(x in title for x in ['openai', 'chatgpt', 'gpt-4', 'gpt-5', 'sam altman']):
            return "llm-foundation"
        if any(x in title for x in ['anthropic', 'claude']):
            return "llm-foundation"
        if any(x in title for x in ['google', 'deepmind', 'gemini']):
            return "llm-foundation"
        if any(x in title for x in ['xai', 'grok', 'elon']):
            return "llm-foundation"
        if any(x in title for x in ['meta ai', 'llama']):
            return "open-source-ai"
        if any(x in title for x in ['mistral', 'deepseek', 'open source', 'hugging']):
            return "open-source-ai"

        # Concept-specific
        if any(x in title for x in ['agi', 'superintelligence', 'singularity']):
            return "ai-safety"
        if any(x in title for x in ['alignment', 'safety', 'risk', 'existential']):
            return "ai-safety"
        if any(x in title for x in ['regulation', 'law', 'ban', 'congress', 'eu ai act']):
            return "ai-governance"
        if any(x in title for x in ['robot', 'humanoid', 'boston dynamics', 'figure']):
            return "robotics-embodied"
        if any(x in title for x in ['self-driving', 'autonomous', 'waymo', 'tesla fsd']):
            return "autonomous-vehicles"
        if any(x in title for x in ['nvidia', 'gpu', 'chip', 'h100', 'compute']):
            return "ai-chips"
        if any(x in title for x in ['stable diffusion', 'midjourney', 'dall-e', 'image generation']):
            return "ai-image-generation"
        if any(x in title for x in ['copilot', 'cursor', 'coding', 'programming']):
            return "ai-coding"

        return "ai-general"

    def analyze_sentiment(self, story: Dict[str, Any]) -> str:
        """Simple sentiment analysis based on title keywords."""
        title = story.get("title", "").lower()

        positive_words = ['breakthrough', 'amazing', 'impressive', 'launch', 'release',
                         'success', 'beats', 'better', 'faster', 'open source', 'free']
        negative_words = ['concern', 'risk', 'danger', 'ban', 'fail', 'problem',
                         'lawsuit', 'layoff', 'warning', 'threat', 'slow', 'worse']

        pos_count = sum(1 for w in positive_words if w in title)
        neg_count = sum(1 for w in negative_words if w in title)

        if pos_count > neg_count:
            return "positive"
        elif neg_count > pos_count:
            return "negative"
        return "neutral"

    def compute_sentiment_signals(self, stories: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Compute sentiment signals from HN stories."""
        bucket_signals = {}

        for story in stories:
            bucket = story.get("bucket")
            if not bucket:
                continue

            points = story.get("points", 0)
            comments = story.get("num_comments", 0)
            sentiment = story.get("sentiment", "neutral")

            # Engagement score
            engagement = points + (comments * 2)  # Comments weighted higher

            if bucket not in bucket_signals:
                bucket_signals[bucket] = {
                    "story_count": 0,
                    "total_points": 0,
                    "total_comments": 0,
                    "total_engagement": 0,
                    "sentiment_counts": {"positive": 0, "negative": 0, "neutral": 0},
                    "top_stories": [],
                }

            bucket_signals[bucket]["story_count"] += 1
            bucket_signals[bucket]["total_points"] += points
            bucket_signals[bucket]["total_comments"] += comments
            bucket_signals[bucket]["total_engagement"] += engagement
            bucket_signals[bucket]["sentiment_counts"][sentiment] += 1

            if len(bucket_signals[bucket]["top_stories"]) < 5:
                bucket_signals[bucket]["top_stories"].append({
                    "title": story.get("title"),
                    "points": points,
                    "comments": comments,
                    "hn_url": story.get("hn_url"),
                })

        # Compute sentiment scores
        for bucket, data in bucket_signals.items():
            counts = data["sentiment_counts"]
            total = sum(counts.values())
            if total > 0:
                # Sentiment score: -1 (all negative) to +1 (all positive)
                data["sentiment_score"] = (counts["positive"] - counts["negative"]) / total
            else:
                data["sentiment_score"] = 0

            # Average engagement
            if data["story_count"] > 0:
                data["avg_engagement"] = data["total_engagement"] / data["story_count"]
            else:
                data["avg_engagement"] = 0

            # Interpret
            score = data["sentiment_score"]
            if score > 0.3:
                data["signal_interpretation"] = "Strong positive sentiment"
            elif score > 0.1:
                data["signal_interpretation"] = "Mildly positive sentiment"
            elif score < -0.3:
                data["signal_interpretation"] = "Strong negative sentiment"
            elif score < -0.1:
                data["signal_interpretation"] = "Mildly negative sentiment"
            else:
                data["signal_interpretation"] = "Neutral/mixed sentiment"

        return bucket_signals

    def run(self, num_days: int = 7, save: bool = True) -> Dict[str, Any]:
        """Run the scraper and return results."""
        print(f"Fetching AI stories from HackerNews (past {num_days} days)...")
        stories = self.fetch_ai_stories(num_days=num_days)
        print(f"  Retrieved {len(stories)} stories")

        # Filter and process
        processed = []
        for story in stories:
            if self.is_ai_related(story):
                data = self.extract_story_data(story)
                data["bucket"] = self.categorize_story(story)
                data["sentiment"] = self.analyze_sentiment(story)
                if data["bucket"]:
                    processed.append(data)

        print(f"  {len(processed)} AI stories after filtering")

        # Sort by points
        processed.sort(key=lambda x: x.get("points", 0), reverse=True)

        # Compute signals
        signals = self.compute_sentiment_signals(processed)

        result = {
            "source": "hackernews",
            "scraped_at": datetime.now().isoformat(),
            "period_days": num_days,
            "total_stories": len(processed),
            "stories": processed,
            "bucket_signals": signals,
        }

        if save:
            date_str = datetime.now().strftime("%Y-%m-%d")
            output_file = self.output_dir / f"hackernews_{date_str}.json"
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, default=str)
            print(f"Saved to {output_file}")

        return result


def main():
    """Main entry point."""
    scraper = HackerNewsScraper()
    result = scraper.run(num_days=7)

    print("\n" + "=" * 60)
    print("HACKERNEWS AI SENTIMENT SUMMARY")
    print("=" * 60)
    print(f"AI stories found (past 7 days): {result['total_stories']}")

    print("\nTop 10 Stories by Points:")
    print("-" * 60)
    for i, story in enumerate(result['stories'][:10], 1):
        print(f"{i}. {story['title'][:55]}...")
        print(f"   Points: {story['points']} | Comments: {story['num_comments']} | Sentiment: {story['sentiment']}")
        print()

    print("\nSignals by Bucket:")
    print("-" * 60)
    for bucket, data in sorted(result['bucket_signals'].items(),
                               key=lambda x: -x[1]['total_engagement']):
        print(f"{bucket}:")
        print(f"   Stories: {data['story_count']} | Engagement: {data['total_engagement']:,}")
        print(f"   Sentiment: {data['sentiment_score']:+.2f}")
        print(f"   Signal: {data['signal_interpretation']}")
        print()


if __name__ == "__main__":
    main()