"""
Polymarket Scraper for AI Prediction Markets

Scrapes AI-related prediction markets from Polymarket to generate
CSS (Crypto Sentiment Signal) for the trend radar.

Data includes:
- Market questions and outcomes
- Current probability prices
- Trading volume and liquidity
- Market resolution dates
"""

import requests
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
import re


class PolymarketScraper:
    """Scraper for Polymarket prediction markets."""

    BASE_URL = "https://gamma-api.polymarket.com"

    # Keywords to identify AI-related markets (stricter matching)
    AI_KEYWORDS = [
        # Companies (AI-focused)
        'openai', 'anthropic', 'deepmind', 'xai',
        # Products (explicit AI products)
        'gpt-4', 'gpt-5', 'chatgpt', 'claude', 'gemini', 'grok', 'llama',
        'deepseek', 'copilot', 'midjourney', 'stable diffusion', 'dall-e',
        # Explicit AI concepts
        'artificial intelligence', 'agi', 'llm', 'language model',
        'ai model', 'best ai', 'top ai',
    ]

    # Patterns that require "AI" to be a standalone word (not part of another word)
    AI_PATTERNS = [
        r'\bai\b',  # "AI" as standalone word
        r'\bai model',
        r'\bai company',
        r'ai regulation',
        r'ai safety',
    ]

    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or Path(__file__).parent.parent / "data" / "alternative_signals"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # Known AI-related event slugs to fetch directly
    AI_EVENT_SLUGS = [
        "which-company-has-the-best-ai-model-end-of-january",
        "which-company-has-the-best-ai-model-end-of-march",
        "which-company-has-the-top-ai-model-end-of-january-style",
        "ipos-before-2027",  # Includes AI companies like Cerebras
        "openai",
        "chatgpt",
    ]

    def fetch_markets(self, limit: int = 500, closed: bool = False) -> List[Dict[str, Any]]:
        """Fetch markets from Polymarket API."""
        url = f"{self.BASE_URL}/markets"
        params = {
            "closed": str(closed).lower(),
            "limit": limit,
        }

        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"Error fetching markets: {e}")
            return []

    def fetch_ai_events(self) -> List[Dict[str, Any]]:
        """Fetch AI-related events directly by slug."""
        all_markets = []
        seen_ids = set()

        for slug in self.AI_EVENT_SLUGS:
            try:
                url = f"{self.BASE_URL}/events"
                resp = requests.get(url, params={"slug": slug}, timeout=20)
                if resp.status_code == 200:
                    events = resp.json()
                    for event in events:
                        for market in event.get("markets", []):
                            market_id = market.get("id")
                            if market_id and market_id not in seen_ids:
                                seen_ids.add(market_id)
                                # Add event context
                                market["event_title"] = event.get("title")
                                market["event_slug"] = event.get("slug")
                                all_markets.append(market)
            except Exception as e:
                print(f"  Error fetching event {slug}: {e}")

        return all_markets

    def is_ai_related(self, market: Dict[str, Any]) -> bool:
        """Check if a market is AI-related based on keywords and patterns."""
        question = market.get("question", "").lower()
        description = market.get("description", "").lower()

        text = f"{question} {description}"

        # Check explicit keywords
        for keyword in self.AI_KEYWORDS:
            if keyword.lower() in text:
                return True

        # Check regex patterns for standalone "AI"
        for pattern in self.AI_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return True

        return False

    def filter_ai_markets(self, markets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter markets to only AI-related ones."""
        return [m for m in markets if self.is_ai_related(m)]

    def extract_market_data(self, market: Dict[str, Any]) -> Dict[str, Any]:
        """Extract relevant fields from a market."""
        outcomes = market.get("outcomes", [])
        prices = market.get("outcomePrices", [])

        # Parse JSON strings if needed
        if isinstance(outcomes, str):
            try:
                outcomes = json.loads(outcomes)
            except:
                outcomes = []
        if isinstance(prices, str):
            try:
                prices = json.loads(prices)
            except:
                prices = []

        # Parse outcome probabilities
        outcome_probs = {}
        for i, outcome in enumerate(outcomes):
            if i < len(prices):
                try:
                    outcome_probs[outcome] = float(prices[i]) * 100
                except (ValueError, TypeError):
                    outcome_probs[outcome] = 0.0

        return {
            "id": market.get("id"),
            "question": market.get("question"),
            "description": market.get("description", "")[:500],  # Truncate
            "outcomes": outcomes,
            "outcome_probabilities": outcome_probs,
            "volume": float(market.get("volume", 0) or 0),
            "volume_24h": float(market.get("volume24hr", 0) or 0),
            "liquidity": float(market.get("liquidity", 0) or 0),
            "start_date": market.get("startDate"),
            "end_date": market.get("endDate"),
            "slug": market.get("slug"),
            "active": market.get("active", False),
            "spread": float(market.get("spread", 0) or 0),
        }

    def categorize_market(self, market: Dict[str, Any]) -> Optional[str]:
        """
        Categorize a market into AI trend buckets.
        Returns None if the market is not AI-related.
        """
        question = market.get("question", "").lower()
        description = market.get("description", "").lower()
        text = question + " " + description

        # Must contain AI-related keywords to be categorized
        ai_indicators = [
            'ai model', 'artificial intelligence', 'machine learning',
            'llm', 'language model', 'neural', 'deep learning',
            'openai', 'anthropic', 'deepmind', 'chatgpt', 'claude', 'gemini',
            'gpt-', 'grok', 'llama', 'deepseek', 'mistral', 'best ai',
        ]

        if not any(ind in text for ind in ai_indicators):
            return None  # Not AI-related

        # Company-specific
        if any(x in question for x in ['openai', 'chatgpt', 'gpt-']):
            return "llm-foundation"
        if any(x in question for x in ['anthropic', 'claude']):
            return "llm-foundation"
        if any(x in question for x in ['google', 'gemini', 'deepmind']):
            return "llm-foundation"
        if any(x in question for x in ['xai', 'grok']):
            return "llm-foundation"
        if any(x in question for x in ['meta', 'llama']):
            return "open-source-ai"
        if any(x in question for x in ['deepseek']):
            return "open-source-ai"

        # Concept-specific
        if any(x in question for x in ['agi', 'superintelligence']):
            return "ai-safety"
        if any(x in question for x in ['regulation', 'ban', 'law']):
            return "ai-governance"
        if any(x in question for x in ['robot', 'humanoid', 'tesla bot']):
            return "robotics-embodied"
        if any(x in question for x in ['self-driving', 'autonomous', 'fsd']):
            return "autonomous-vehicles"
        if any(x in question for x in ['chip', 'gpu', 'nvidia', 'semiconductor']):
            return "ai-chips"

        return "ai-general"

    def compute_market_sentiment(self, market: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compute confidence-weighted sentiment for a single market.

        Formula: confidence = volume × |probability - 50| / 50

        - High volume + probability far from 50% = strong conviction
        - Probability > 50% = bullish (market expects it to happen)
        - Probability < 50% = bearish (market expects it NOT to happen)
        """
        volume = market.get("volume", 0)
        outcome_probs = market.get("outcome_probabilities", {})

        # Get the "Yes" probability (first outcome is usually Yes)
        yes_prob = 50.0  # Default neutral
        for outcome, prob in outcome_probs.items():
            if outcome.lower() in ["yes", "true", "1"]:
                yes_prob = prob
                break
            # For named outcomes (like company names), use the probability directly
            yes_prob = prob
            break

        # Confidence score: how far from 50% × volume
        # Normalized so 100% certainty with $1M volume = 1M confidence
        distance_from_neutral = abs(yes_prob - 50) / 50  # 0 to 1
        confidence_score = volume * distance_from_neutral

        # Direction: bullish if >50%, bearish if <50%
        if yes_prob > 50:
            direction = "bullish"
            sentiment_score = (yes_prob - 50) / 50  # 0 to 1
        else:
            direction = "bearish"
            sentiment_score = (50 - yes_prob) / 50  # 0 to 1

        return {
            "yes_probability": yes_prob,
            "direction": direction,
            "sentiment_score": sentiment_score,  # 0-1, strength of direction
            "confidence_score": confidence_score,  # volume-weighted confidence
            "volume": volume,
        }

    def compute_sentiment_signals(self, markets: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Compute sentiment signals from prediction markets.

        Returns aggregated signals by bucket with confidence-weighted metrics.

        Key metrics per bucket:
        - weighted_sentiment: Volume-weighted average sentiment (-1 to 1)
        - total_confidence: Sum of confidence scores (higher = more market attention)
        - bullish_confidence: Confidence in bullish markets
        - bearish_confidence: Confidence in bearish markets
        """
        bucket_signals = {}

        for market in markets:
            bucket = self.categorize_market(market)
            if bucket is None:
                continue  # Skip non-AI markets
            sentiment = self.compute_market_sentiment(market)

            if bucket not in bucket_signals:
                bucket_signals[bucket] = {
                    "market_count": 0,
                    "total_volume": 0,
                    "total_liquidity": 0,
                    "total_confidence": 0,
                    "bullish_confidence": 0,
                    "bearish_confidence": 0,
                    "weighted_sentiment_sum": 0,
                    "markets": [],
                }

            bucket_signals[bucket]["market_count"] += 1
            bucket_signals[bucket]["total_volume"] += market.get("volume", 0)
            bucket_signals[bucket]["total_liquidity"] += market.get("liquidity", 0)
            bucket_signals[bucket]["total_confidence"] += sentiment["confidence_score"]

            # Track directional confidence
            if sentiment["direction"] == "bullish":
                bucket_signals[bucket]["bullish_confidence"] += sentiment["confidence_score"]
                bucket_signals[bucket]["weighted_sentiment_sum"] += sentiment["confidence_score"]
            else:
                bucket_signals[bucket]["bearish_confidence"] += sentiment["confidence_score"]
                bucket_signals[bucket]["weighted_sentiment_sum"] -= sentiment["confidence_score"]

            bucket_signals[bucket]["markets"].append({
                "question": market.get("question"),
                "volume": market.get("volume", 0),
                "outcome_probabilities": market.get("outcome_probabilities", {}),
                "sentiment": sentiment,
            })

        # Compute final weighted sentiment per bucket
        for bucket, data in bucket_signals.items():
            if data["total_confidence"] > 0:
                # Normalize to -1 to 1 range
                data["weighted_sentiment"] = data["weighted_sentiment_sum"] / data["total_confidence"]
            else:
                data["weighted_sentiment"] = 0

            # Clean up intermediate field
            del data["weighted_sentiment_sum"]

            # Add interpretation
            if data["weighted_sentiment"] > 0.3:
                data["signal_interpretation"] = "Strong bullish consensus"
            elif data["weighted_sentiment"] > 0.1:
                data["signal_interpretation"] = "Mild bullish lean"
            elif data["weighted_sentiment"] < -0.3:
                data["signal_interpretation"] = "Strong bearish consensus"
            elif data["weighted_sentiment"] < -0.1:
                data["signal_interpretation"] = "Mild bearish lean"
            else:
                data["signal_interpretation"] = "Neutral/mixed signals"

        return bucket_signals

    def run(self, save: bool = True) -> Dict[str, Any]:
        """Run the scraper and return results."""
        # Method 1: Fetch known AI event slugs directly
        print("Fetching AI events by slug...")
        event_markets = self.fetch_ai_events()
        print(f"  Retrieved {len(event_markets)} markets from AI events")

        # Method 2: Also scan general markets for AI keywords
        print("Fetching general markets...")
        all_markets = self.fetch_markets(limit=500)
        print(f"  Retrieved {len(all_markets)} total markets")

        print("Filtering AI-related markets...")
        keyword_ai_markets = self.filter_ai_markets(all_markets)
        print(f"  Found {len(keyword_ai_markets)} AI-related by keywords")

        # Combine and dedupe
        seen_ids = {m.get("id") for m in event_markets}
        for m in keyword_ai_markets:
            if m.get("id") not in seen_ids:
                event_markets.append(m)
                seen_ids.add(m.get("id"))

        ai_markets = event_markets
        print(f"  Total unique AI markets: {len(ai_markets)}")

        # Extract and process data (filter non-AI markets from event slugs)
        processed = []
        for m in ai_markets:
            bucket = self.categorize_market(m)
            if bucket is None:
                continue  # Skip non-AI markets that came from mixed event slugs
            data = self.extract_market_data(m)
            data["bucket"] = bucket
            processed.append(data)

        # Sort by volume
        processed.sort(key=lambda x: x.get("volume", 0), reverse=True)

        # Compute aggregate signals
        signals = self.compute_sentiment_signals(processed)

        result = {
            "scraped_at": datetime.now().isoformat(),
            "total_markets": len(all_markets),
            "ai_markets": len(ai_markets),
            "markets": processed,
            "bucket_signals": signals,
        }

        if save:
            date_str = datetime.now().strftime("%Y-%m-%d")
            output_file = self.output_dir / f"polymarket_{date_str}.json"
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, default=str)
            print(f"Saved to {output_file}")

        return result


def main():
    """Main entry point."""
    scraper = PolymarketScraper()
    result = scraper.run()

    print("\n" + "="*60)
    print("POLYMARKET AI MARKETS SUMMARY")
    print("="*60)
    print(f"Total markets scanned: {result['total_markets']}")
    print(f"AI-related markets found: {result['ai_markets']}")

    print("\nTop 10 AI Markets by Volume:")
    print("-" * 60)
    for i, m in enumerate(result['markets'][:10], 1):
        print(f"{i}. {m['question'][:55]}...")
        print(f"   Volume: ${m['volume']:,.0f} | Liquidity: ${m['liquidity']:,.0f}")
        if m['outcome_probabilities']:
            probs = ", ".join(f"{k}: {v:.0f}%" for k, v in list(m['outcome_probabilities'].items())[:3])
            print(f"   Outcomes: {probs}")
        print()

    print("\nSentiment Signals by Bucket:")
    print("-" * 60)
    for bucket, data in sorted(result['bucket_signals'].items(), key=lambda x: -x[1]['total_confidence']):
        sentiment_bar = "#" * int(abs(data['weighted_sentiment']) * 10)
        direction = "+" if data['weighted_sentiment'] > 0 else "-" if data['weighted_sentiment'] < 0 else "="
        print(f"{bucket}:")
        print(f"   Markets: {data['market_count']} | Volume: ${data['total_volume']:,.0f}")
        print(f"   Confidence: ${data['total_confidence']:,.0f} (Bull: ${data['bullish_confidence']:,.0f} / Bear: ${data['bearish_confidence']:,.0f})")
        print(f"   Sentiment: {direction} {data['weighted_sentiment']:+.2f} {sentiment_bar}")
        print(f"   Signal: {data['signal_interpretation']}")
        print()


if __name__ == "__main__":
    main()
