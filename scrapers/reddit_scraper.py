"""
Reddit Scraper for AI Community Sentiment

Scrapes AI-related subreddits for sentiment and trending topics.
Uses Reddit's public JSON API (no OAuth required).
"""

import requests
import json
import time
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional
from urllib.parse import quote


class RedditScraper:
    """Scraper for Reddit AI communities."""

    # AI-related subreddits to monitor (expanded Jan 2026)
    AI_SUBREDDITS = [
        # Core AI/ML
        "MachineLearning",
        "artificial",
        # "ArtificialIntelligence",  # Removed: subreddit returns 404 as of Feb 2026
        "deeplearning",
        "learnmachinelearning",  # Replacement for r/ArtificialIntelligence
        
        # LLMs & Chatbots
        "LocalLLaMA",
        "ChatGPT",
        "OpenAI",
        "ClaudeAI",
        "Anthropic",
        "Ollama",
        "LLMDevs",
        
        # AI Applications
        "StableDiffusion",
        "singularity",
        "agi",
        "AutoGPT",
        "perplexity_ai",
        
        # Developer/Tools
        "LangChain",
        "PromptEngineering",
        "MLOps",
        "DataEngineering",
        "datascience",
        
        # Specialized
        "computervision",
        "reinforcementlearning",
    ]

    AI_KEYWORDS = [
        'ai', 'artificial intelligence', 'machine learning', 'deep learning',
        'llm', 'gpt', 'chatgpt', 'claude', 'gemini', 'llama',
        'openai', 'anthropic', 'deepmind', 'transformer', 'neural',
    ]

    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or Path(__file__).parent.parent / "data" / "alternative_signals"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        })

    def fetch_subreddit_posts(self, subreddit: str, sort: str = "hot",
                              limit: int = 25, time_filter: str = "week") -> List[Dict[str, Any]]:
        """Fetch posts from a subreddit."""
        url = f"https://www.reddit.com/r/{subreddit}/{sort}.json"
        params = {
            "limit": limit,
            "t": time_filter,  # hour, day, week, month, year, all
        }

        try:
            resp = self.session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            posts = data.get("data", {}).get("children", [])
            return [p.get("data", {}) for p in posts]
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code in (403, 429):
                # Try Bright Data fallback
                from bright_data_fetcher import fetch_url as bd_fetch
                import json as _json
                full_url = f"{url}?{'&'.join(f'{k}={v}' for k,v in params.items())}"
                print(f"    Trying Bright Data fallback for r/{subreddit}...")
                html = bd_fetch(full_url)
                if html:
                    try:
                        data = _json.loads(html)
                        posts = data.get("data", {}).get("children", [])
                        print(f"    Bright Data: got {len(posts)} posts")
                        return [p.get("data", {}) for p in posts]
                    except _json.JSONDecodeError:
                        pass
            print(f"  Error fetching r/{subreddit}: {e}")
            return []
        except Exception as e:
            print(f"  Error fetching r/{subreddit}: {e}")
            return []

    def fetch_all_ai_subreddits(self, limit_per_sub: int = 25, use_rss: bool = True) -> List[Dict[str, Any]]:
        """Fetch posts from all AI subreddits.
        
        Args:
            use_rss: If True (default), use RSS feeds since JSON API returns 403.
                     Set to False to try JSON API (likely broken as of March 2026).
        """
        if use_rss:
            return self._fetch_via_rss()

        # Legacy JSON path (kept for reference, but JSON API is dead as of ~Feb 2026)
        all_posts = []
        seen_ids = set()

        for i, subreddit in enumerate(self.AI_SUBREDDITS):
            if i > 0:
                time.sleep(random.uniform(1, 3))
            print(f"  Fetching r/{subreddit}...")
            posts = self.fetch_subreddit_posts(subreddit, limit=limit_per_sub)

            for post in posts:
                post_id = post.get("id")
                if post_id and post_id not in seen_ids:
                    seen_ids.add(post_id)
                    post["source_subreddit"] = subreddit
                    all_posts.append(post)

        return all_posts

    def _fetch_via_rss(self) -> List[Dict[str, Any]]:
        """Fetch all subreddits via RSS feeds (primary method since March 2026)."""
        from reddit_rss_fetcher import RedditRSSFetcher
        fetcher = RedditRSSFetcher()
        rss_posts = fetcher.fetch_multiple_subreddits(self.AI_SUBREDDITS, include_top=True)
        
        # Convert RSS format to match what extract_post_data expects
        # RSS posts already have our standard fields, but the JSON path expects
        # raw Reddit API fields. RSS posts are already extracted, so we tag them.
        for post in rss_posts:
            post["_from_rss"] = True
        
        print(f"  RSS: Retrieved {len(rss_posts)} posts from {len(self.AI_SUBREDDITS)} subreddits")
        return rss_posts

    def extract_post_data(self, post: Dict[str, Any]) -> Dict[str, Any]:
        """Extract relevant fields from a post."""
        # RSS posts are already in extracted format
        if post.get("_from_rss"):
            return {k: v for k, v in post.items() if k != "_from_rss"}
        
        return {
            "id": post.get("id"),
            "title": post.get("title"),
            "subreddit": post.get("subreddit"),
            "url": f"https://reddit.com{post.get('permalink', '')}",
            "score": post.get("score", 0),
            "upvote_ratio": post.get("upvote_ratio", 0),
            "num_comments": post.get("num_comments", 0),
            "created_utc": post.get("created_utc"),
            "author": post.get("author"),
            "is_self": post.get("is_self", False),
            "selftext": post.get("selftext", "")[:500] if post.get("selftext") else "",
            "link_flair_text": post.get("link_flair_text"),
        }

    def categorize_post(self, post: Dict[str, Any]) -> Optional[str]:
        """Categorize a post into AI trend buckets."""
        title = post.get("title", "").lower()
        text = post.get("selftext", "").lower() if post.get("selftext") else ""
        subreddit = post.get("subreddit", "").lower()
        combined = f"{title} {text}"

        # Subreddit-based categorization
        if subreddit in ["localllama"]:
            return "open-source-ai"
        if subreddit in ["stablediffusion", "midjourney"]:
            return "ai-image-generation"
        if subreddit in ["singularity", "agi"]:
            return "ai-safety"

        # Keyword-based
        if any(x in combined for x in ['openai', 'chatgpt', 'gpt-4', 'gpt-5']):
            return "llm-foundation"
        if any(x in combined for x in ['anthropic', 'claude']):
            return "llm-foundation"
        if any(x in combined for x in ['google', 'gemini', 'deepmind']):
            return "llm-foundation"
        if any(x in combined for x in ['llama', 'mistral', 'open source', 'local']):
            return "open-source-ai"
        if any(x in combined for x in ['stable diffusion', 'midjourney', 'dall-e', 'image']):
            return "ai-image-generation"
        if any(x in combined for x in ['agi', 'superintelligence', 'alignment', 'safety']):
            return "ai-safety"
        if any(x in combined for x in ['regulation', 'law', 'ban', 'congress']):
            return "ai-governance"
        if any(x in combined for x in ['nvidia', 'gpu', 'chip', 'hardware']):
            return "ai-chips"
        if any(x in combined for x in ['robot', 'humanoid', 'embodied']):
            return "robotics-embodied"
        if any(x in combined for x in ['copilot', 'cursor', 'coding', 'code']):
            return "ai-coding"

        return "ai-general"

    def analyze_sentiment(self, post: Dict[str, Any]) -> str:
        """Simple sentiment analysis based on title and content."""
        title = post.get("title", "").lower()
        text = post.get("selftext", "").lower() if post.get("selftext") else ""
        combined = f"{title} {text}"

        positive_words = [
            'amazing', 'awesome', 'breakthrough', 'impressive', 'love',
            'great', 'best', 'incredible', 'fantastic', 'exciting',
            'game changer', 'revolutionary', 'mind blowing',
        ]
        negative_words = [
            'terrible', 'awful', 'bad', 'worst', 'hate', 'disappointing',
            'broken', 'useless', 'garbage', 'trash', 'scam', 'overhyped',
            'concerning', 'dangerous', 'scary', 'worried',
        ]

        pos = sum(1 for w in positive_words if w in combined)
        neg = sum(1 for w in negative_words if w in combined)

        # Also consider upvote ratio
        ratio = post.get("upvote_ratio", 0.5)
        if ratio > 0.9:
            pos += 1
        elif ratio < 0.5:
            neg += 1

        if pos > neg:
            return "positive"
        elif neg > pos:
            return "negative"
        return "neutral"

    def compute_sentiment_signals(self, posts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Compute sentiment signals from Reddit posts."""
        bucket_signals = {}

        for post in posts:
            bucket = post.get("bucket")
            if not bucket:
                continue

            score = post.get("score", 0)
            comments = post.get("num_comments", 0)
            sentiment = post.get("sentiment", "neutral")

            # Engagement score
            engagement = score + (comments * 3)  # Comments weighted higher

            if bucket not in bucket_signals:
                bucket_signals[bucket] = {
                    "post_count": 0,
                    "total_score": 0,
                    "total_comments": 0,
                    "total_engagement": 0,
                    "sentiment_counts": {"positive": 0, "negative": 0, "neutral": 0},
                    "subreddits": {},
                    "top_posts": [],
                }

            bucket_signals[bucket]["post_count"] += 1
            bucket_signals[bucket]["total_score"] += score
            bucket_signals[bucket]["total_comments"] += comments
            bucket_signals[bucket]["total_engagement"] += engagement
            bucket_signals[bucket]["sentiment_counts"][sentiment] += 1

            # Track subreddit distribution
            sub = post.get("subreddit", "unknown")
            bucket_signals[bucket]["subreddits"][sub] = (
                bucket_signals[bucket]["subreddits"].get(sub, 0) + 1
            )

            if len(bucket_signals[bucket]["top_posts"]) < 3:
                bucket_signals[bucket]["top_posts"].append({
                    "title": post.get("title"),
                    "score": score,
                    "subreddit": sub,
                    "url": post.get("url"),
                })

        # Compute sentiment scores
        for bucket, data in bucket_signals.items():
            counts = data["sentiment_counts"]
            total = sum(counts.values())
            if total > 0:
                data["sentiment_score"] = (counts["positive"] - counts["negative"]) / total
            else:
                data["sentiment_score"] = 0

            if data["post_count"] > 0:
                data["avg_engagement"] = data["total_engagement"] / data["post_count"]
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

    def run(self, save: bool = True) -> Dict[str, Any]:
        """Run the scraper and return results."""
        print("Fetching posts from AI subreddits...")
        posts = self.fetch_all_ai_subreddits(limit_per_sub=25)
        print(f"  Retrieved {len(posts)} posts")

        # Process posts
        processed = []
        for post in posts:
            data = self.extract_post_data(post)
            data["bucket"] = self.categorize_post(post)
            data["sentiment"] = self.analyze_sentiment(post)
            if data["bucket"]:
                processed.append(data)

        print(f"  {len(processed)} posts after processing")

        # Sort by score
        processed.sort(key=lambda x: x.get("score", 0), reverse=True)

        # Compute signals
        signals = self.compute_sentiment_signals(processed)

        result = {
            "source": "reddit",
            "scraped_at": datetime.now().isoformat(),
            "subreddits_scraped": self.AI_SUBREDDITS,
            "total_posts": len(processed),
            "posts": processed,
            "bucket_signals": signals,
        }

        if save:
            date_str = datetime.now().strftime("%Y-%m-%d")
            output_file = self.output_dir / f"reddit_{date_str}.json"
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, default=str)
            print(f"Saved to {output_file}")

        return result


def main():
    """Main entry point."""
    scraper = RedditScraper()
    result = scraper.run()

    print("\n" + "=" * 60)
    print("REDDIT AI SENTIMENT SUMMARY")
    print("=" * 60)
    print(f"Subreddits scraped: {len(result['subreddits_scraped'])}")
    print(f"Total posts: {result['total_posts']}")

    print("\nTop 10 Posts by Score:")
    print("-" * 60)
    for i, post in enumerate(result['posts'][:10], 1):
        print(f"{i}. [{post['subreddit']}] {post['title'][:50]}...")
        print(f"   Score: {post['score']} | Comments: {post['num_comments']} | Sentiment: {post['sentiment']}")
        print()

    print("\nSignals by Bucket:")
    print("-" * 60)
    for bucket, data in sorted(result['bucket_signals'].items(),
                               key=lambda x: -x[1]['total_engagement']):
        print(f"{bucket}:")
        print(f"   Posts: {data['post_count']} | Engagement: {data['total_engagement']:,}")
        print(f"   Sentiment: {data['sentiment_score']:+.2f}")
        print(f"   Signal: {data['signal_interpretation']}")
        print()


if __name__ == "__main__":
    main()