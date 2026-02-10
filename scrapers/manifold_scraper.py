"""
Manifold Markets Scraper for AI Prediction Markets

Scrapes AI-related prediction markets from Manifold Markets.
While play money, Manifold has high liquidity and active AI community.
"""

import requests
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional


class ManifoldScraper:
    """Scraper for Manifold Markets predictions."""

    BASE_URL = "https://api.manifold.markets/v0"

    AI_KEYWORDS = [
        'ai', 'artificial intelligence', 'machine learning', 'deep learning',
        'openai', 'anthropic', 'deepmind', 'google ai',
        'gpt', 'chatgpt', 'claude', 'gemini', 'llama', 'grok',
        'llm', 'language model', 'agi', 'alignment', 'ai safety',
    ]

    AI_GROUPS = [
        "ai",
        "artificial-intelligence",
        "machine-learning",
        "openai",
        "anthropic",
    ]

    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or Path(__file__).parent.parent / "data" / "alternative_signals"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def fetch_markets(self, limit: int = 500) -> List[Dict[str, Any]]:
        """Fetch markets from Manifold API."""
        url = f"{self.BASE_URL}/markets"
        params = {"limit": limit}

        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"Error fetching markets: {e}")
            return []

    def search_markets(self, term: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Search markets by term."""
        url = f"{self.BASE_URL}/search-markets"
        params = {"term": term, "limit": limit}

        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"Error searching markets for '{term}': {e}")
            return []

    def fetch_ai_markets(self) -> List[Dict[str, Any]]:
        """Fetch AI-related markets using search."""
        all_markets = []
        seen_ids = set()

        search_terms = [
            "AI", "artificial intelligence", "GPT", "OpenAI",
            "Anthropic", "Claude", "LLM", "AGI", "machine learning",
            "Gemini", "DeepMind", "AI safety",
        ]

        for term in search_terms:
            print(f"  Searching: {term}")
            markets = self.search_markets(term, limit=50)
            for m in markets:
                mid = m.get("id")
                if mid and mid not in seen_ids:
                    seen_ids.add(mid)
                    all_markets.append(m)

        return all_markets

    def is_ai_related(self, market: Dict[str, Any]) -> bool:
        """Check if a market is AI-related."""
        question = market.get("question", "").lower()
        description = market.get("description", "").lower()
        text = f"{question} {description}"

        for keyword in self.AI_KEYWORDS:
            if keyword in text:
                return True
        return False

    def extract_market_data(self, market: Dict[str, Any]) -> Dict[str, Any]:
        """Extract relevant fields from a market."""
        return {
            "id": market.get("id"),
            "question": market.get("question"),
            "description": market.get("description", "")[:500] if market.get("description") else "",
            "url": market.get("url"),
            "probability": market.get("probability"),
            "volume": market.get("volume", 0),
            "volume_24h": market.get("volume24Hours", 0),
            "liquidity": market.get("totalLiquidity", 0),
            "unique_bettors": market.get("uniqueBettorCount", 0),
            "created_at": market.get("createdTime"),
            "close_time": market.get("closeTime"),
            "is_resolved": market.get("isResolved", False),
            "outcome_type": market.get("outcomeType"),
            "creator": market.get("creatorUsername"),
        }

    def categorize_market(self, market: Dict[str, Any]) -> Optional[str]:
        """Categorize a market into AI trend buckets."""
        question = market.get("question", "").lower()
        description = market.get("description", "").lower() if market.get("description") else ""
        text = f"{question} {description}"

        # Check if AI-related
        if not self.is_ai_related(market):
            return None

        # Company-specific
        if any(x in text for x in ['openai', 'chatgpt', 'gpt-4', 'gpt-5', 'sam altman']):
            return "llm-foundation"
        if any(x in text for x in ['anthropic', 'claude', 'dario']):
            return "llm-foundation"
        if any(x in text for x in ['google', 'deepmind', 'gemini']):
            return "llm-foundation"
        if any(x in text for x in ['xai', 'grok', 'elon']):
            return "llm-foundation"

        # Concept-specific
        if any(x in text for x in ['agi', 'superintelligence', 'human-level', 'singularity']):
            return "ai-safety"
        if any(x in text for x in ['alignment', 'safety', 'x-risk', 'existential']):
            return "ai-safety"
        if any(x in text for x in ['regulation', 'law', 'ban', 'policy', 'congress']):
            return "ai-governance"
        if any(x in text for x in ['robot', 'humanoid', 'boston dynamics', 'figure']):
            return "robotics-embodied"
        if any(x in text for x in ['self-driving', 'autonomous', 'tesla fsd', 'waymo']):
            return "autonomous-vehicles"
        if any(x in text for x in ['nvidia', 'gpu', 'chip', 'tpu', 'compute']):
            return "ai-chips"
        if any(x in text for x in ['llama', 'mistral', 'open source', 'open-source', 'hugging']):
            return "open-source-ai"

        return "ai-general"

    def compute_sentiment_signals(self, markets: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Compute sentiment signals from prediction markets."""
        bucket_signals = {}

        for market in markets:
            bucket = market.get("bucket")
            if not bucket:
                continue

            prob = market.get("probability")
            volume = market.get("volume", 0)
            bettors = market.get("unique_bettors", 0)

            if prob is None:
                continue

            # Confidence = volume * distance from 50%
            distance = abs(prob - 0.5) * 2  # 0 to 1
            confidence = volume * distance

            if bucket not in bucket_signals:
                bucket_signals[bucket] = {
                    "market_count": 0,
                    "total_volume": 0,
                    "total_bettors": 0,
                    "total_confidence": 0,
                    "bullish_confidence": 0,
                    "bearish_confidence": 0,
                    "weighted_prob_sum": 0,
                    "markets": [],
                }

            bucket_signals[bucket]["market_count"] += 1
            bucket_signals[bucket]["total_volume"] += volume
            bucket_signals[bucket]["total_bettors"] += bettors
            bucket_signals[bucket]["total_confidence"] += confidence

            if prob > 0.5:
                bucket_signals[bucket]["bullish_confidence"] += confidence
                bucket_signals[bucket]["weighted_prob_sum"] += confidence
            else:
                bucket_signals[bucket]["bearish_confidence"] += confidence
                bucket_signals[bucket]["weighted_prob_sum"] -= confidence

            bucket_signals[bucket]["markets"].append({
                "question": market.get("question"),
                "probability": prob,
                "volume": volume,
                "url": market.get("url"),
            })

        # Compute final metrics
        for bucket, data in bucket_signals.items():
            if data["total_confidence"] > 0:
                data["weighted_sentiment"] = data["weighted_prob_sum"] / data["total_confidence"]
            else:
                data["weighted_sentiment"] = 0

            del data["weighted_prob_sum"]

            # Interpret
            sent = data["weighted_sentiment"]
            if sent > 0.3:
                data["signal_interpretation"] = "Strong bullish consensus"
            elif sent > 0.1:
                data["signal_interpretation"] = "Mild bullish lean"
            elif sent < -0.3:
                data["signal_interpretation"] = "Strong bearish consensus"
            elif sent < -0.1:
                data["signal_interpretation"] = "Mild bearish lean"
            else:
                data["signal_interpretation"] = "Neutral/mixed signals"

        return bucket_signals

    def run(self, save: bool = True) -> Dict[str, Any]:
        """Run the scraper and return results."""
        print("Fetching AI-related markets from Manifold...")
        markets = self.fetch_ai_markets()
        print(f"  Retrieved {len(markets)} markets")

        # Filter and process
        processed = []
        for m in markets:
            if self.is_ai_related(m) and not m.get("isResolved"):
                data = self.extract_market_data(m)
                data["bucket"] = self.categorize_market(m)
                if data["bucket"]:
                    processed.append(data)

        print(f"  {len(processed)} active AI markets after filtering")

        # Sort by volume
        processed.sort(key=lambda x: x.get("volume", 0), reverse=True)

        # Compute signals
        signals = self.compute_sentiment_signals(processed)

        result = {
            "source": "manifold",
            "scraped_at": datetime.now().isoformat(),
            "total_markets": len(processed),
            "markets": processed,
            "bucket_signals": signals,
        }

        if save:
            date_str = datetime.now().strftime("%Y-%m-%d")
            output_file = self.output_dir / f"manifold_{date_str}.json"
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, default=str)
            print(f"Saved to {output_file}")

        return result


def main():
    """Main entry point."""
    scraper = ManifoldScraper()
    result = scraper.run()

    print("\n" + "=" * 60)
    print("MANIFOLD AI MARKETS SUMMARY")
    print("=" * 60)
    print(f"AI-related markets found: {result['total_markets']}")

    print("\nTop 10 Markets by Volume:")
    print("-" * 60)
    for i, m in enumerate(result['markets'][:10], 1):
        prob = m.get('probability')
        prob_str = f"{prob*100:.0f}%" if prob else "N/A"
        print(f"{i}. {m['question'][:55]}...")
        print(f"   Probability: {prob_str} | Volume: M${m['volume']:,.0f} | Bettors: {m['unique_bettors']}")
        print()

    print("\nSignals by Bucket:")
    print("-" * 60)
    for bucket, data in sorted(result['bucket_signals'].items(), key=lambda x: -x[1]['total_volume']):
        print(f"{bucket}:")
        print(f"   Markets: {data['market_count']} | Volume: M${data['total_volume']:,.0f}")
        print(f"   Sentiment: {data['weighted_sentiment']:+.2f}")
        print(f"   Signal: {data['signal_interpretation']}")
        print()


if __name__ == "__main__":
    main()