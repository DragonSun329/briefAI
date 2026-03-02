"""
Metaculus Scraper for AI Forecasting Questions

Scrapes AI-related forecasting questions from Metaculus to generate
high-quality prediction signals for the trend radar.

Metaculus is known for well-calibrated forecasters and detailed reasoning.
"""

import requests
import json
import time
import random
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional


class MetaculusScraper:
    """Scraper for Metaculus prediction questions."""

    BASE_URL = "https://www.metaculus.com/api2"

    # AI-related tags and keywords
    AI_TAGS = ["ai", "artificial-intelligence", "machine-learning", "agi"]

    AI_KEYWORDS = [
        'artificial intelligence', 'machine learning', 'deep learning',
        'neural network', 'agi', 'llm', 'language model',
        'openai', 'anthropic', 'deepmind', 'google ai', 'gpt',
        'chatgpt', 'claude', 'gemini', 'transformer',
        'ai safety', 'alignment', 'superintelligence',
    ]

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    }

    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or Path(__file__).parent.parent / "data" / "alternative_signals"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)

    def fetch_questions(self, search: str = None, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Fetch questions from Metaculus API."""
        url = f"{self.BASE_URL}/questions/"
        params = {
            "limit": limit,
            "offset": offset,
            "status": "open",  # Only active questions
            "order_by": "-activity",  # Most active first
        }
        if search:
            params["search"] = search

        try:
            resp = self.session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            return data.get("results", [])
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code in (403, 429):
                # Try Bright Data fallback
                from scrapers.bright_data_fetcher import fetch_json as bd_fetch_json
                full_url = f"{url}?{'&'.join(f'{k}={v}' for k,v in params.items())}"
                print(f"    Trying Bright Data fallback for Metaculus...")
                data = bd_fetch_json(full_url)
                if data:
                    results = data.get("results", [])
                    print(f"    Bright Data: got {len(results)} questions")
                    return results
            print(f"Error fetching questions: {e}")
            return []
        except Exception as e:
            print(f"Error fetching questions: {e}")
            return []

    def fetch_ai_questions(self) -> List[Dict[str, Any]]:
        """Fetch AI-related questions using multiple search terms."""
        all_questions = []
        seen_ids = set()

        # Search for AI-related terms
        search_terms = [
            "artificial intelligence",
            "AGI",
            "machine learning",
            "OpenAI",
            "Anthropic",
            "GPT",
            "AI safety",
            "language model",
        ]

        for i, term in enumerate(search_terms):
            if i > 0:
                time.sleep(random.uniform(1, 3))
            print(f"  Searching: {term}")
            questions = self.fetch_questions(search=term, limit=50)
            for q in questions:
                qid = q.get("id")
                if qid and qid not in seen_ids:
                    seen_ids.add(qid)
                    all_questions.append(q)

        return all_questions

    def is_ai_related(self, question: Dict[str, Any]) -> bool:
        """Check if a question is AI-related."""
        title = question.get("title", "").lower()
        description = question.get("description", "").lower()
        text = f"{title} {description}"

        for keyword in self.AI_KEYWORDS:
            if keyword in text:
                return True
        return False

    def extract_question_data(self, question: Dict[str, Any]) -> Dict[str, Any]:
        """Extract relevant fields from a question."""
        # Get community prediction
        prediction = question.get("community_prediction", {})
        if isinstance(prediction, dict):
            community_median = prediction.get("full", {}).get("q2")
        else:
            community_median = prediction

        # Get prediction count
        prediction_count = question.get("number_of_predictions", 0)

        return {
            "id": question.get("id"),
            "title": question.get("title"),
            "description": question.get("description", "")[:500],
            "url": f"https://www.metaculus.com/questions/{question.get('id')}/",
            "created_at": question.get("created_time"),
            "close_time": question.get("close_time"),
            "resolve_time": question.get("resolve_time"),
            "community_prediction": community_median,
            "prediction_count": prediction_count,
            "question_type": question.get("possibilities", {}).get("type", "binary"),
            "activity": question.get("activity", 0),
            "comment_count": question.get("comment_count", 0),
        }

    def categorize_question(self, question: Dict[str, Any]) -> Optional[str]:
        """Categorize a question into AI trend buckets."""
        title = question.get("title", "").lower()
        description = question.get("description", "").lower()
        text = f"{title} {description}"

        # Check if AI-related first
        if not self.is_ai_related(question):
            return None

        # Company-specific
        if any(x in text for x in ['openai', 'chatgpt', 'gpt-4', 'gpt-5']):
            return "llm-foundation"
        if any(x in text for x in ['anthropic', 'claude']):
            return "llm-foundation"
        if any(x in text for x in ['google', 'deepmind', 'gemini']):
            return "llm-foundation"

        # Concept-specific
        if any(x in text for x in ['agi', 'superintelligence', 'human-level']):
            return "ai-safety"
        if any(x in text for x in ['alignment', 'safety', 'existential', 'x-risk']):
            return "ai-safety"
        if any(x in text for x in ['regulation', 'law', 'policy', 'government']):
            return "ai-governance"
        if any(x in text for x in ['robot', 'humanoid', 'embodied']):
            return "robotics-embodied"
        if any(x in text for x in ['autonomous', 'self-driving', 'vehicle']):
            return "autonomous-vehicles"
        if any(x in text for x in ['chip', 'gpu', 'compute', 'hardware']):
            return "ai-chips"
        if any(x in text for x in ['open source', 'open-source', 'llama', 'mistral']):
            return "open-source-ai"

        return "ai-general"

    def compute_sentiment_signals(self, questions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Compute sentiment signals from forecasting questions.

        For Metaculus, higher predictions on positive outcomes = bullish.
        We weight by prediction count (more predictions = higher confidence).
        """
        bucket_signals = {}

        for q in questions:
            bucket = q.get("bucket")
            if not bucket:
                continue

            prediction = q.get("community_prediction")
            pred_count = q.get("prediction_count", 0)

            if prediction is None or pred_count == 0:
                continue

            if bucket not in bucket_signals:
                bucket_signals[bucket] = {
                    "question_count": 0,
                    "total_predictions": 0,
                    "weighted_prediction_sum": 0,
                    "questions": [],
                }

            bucket_signals[bucket]["question_count"] += 1
            bucket_signals[bucket]["total_predictions"] += pred_count
            bucket_signals[bucket]["weighted_prediction_sum"] += prediction * pred_count
            bucket_signals[bucket]["questions"].append({
                "title": q.get("title"),
                "prediction": prediction,
                "prediction_count": pred_count,
                "url": q.get("url"),
            })

        # Compute weighted averages
        for bucket, data in bucket_signals.items():
            if data["total_predictions"] > 0:
                data["weighted_avg_prediction"] = (
                    data["weighted_prediction_sum"] / data["total_predictions"]
                )
            else:
                data["weighted_avg_prediction"] = 0.5

            del data["weighted_prediction_sum"]

            # Interpret (assuming most questions are about positive AI outcomes)
            avg = data["weighted_avg_prediction"]
            if avg > 0.7:
                data["signal_interpretation"] = "High confidence in positive outcomes"
            elif avg > 0.5:
                data["signal_interpretation"] = "Moderately optimistic"
            elif avg > 0.3:
                data["signal_interpretation"] = "Uncertain/cautious"
            else:
                data["signal_interpretation"] = "Pessimistic outlook"

        return bucket_signals

    def run(self, save: bool = True) -> Dict[str, Any]:
        """Run the scraper and return results."""
        print("Fetching AI-related questions from Metaculus...")
        questions = self.fetch_ai_questions()
        print(f"  Retrieved {len(questions)} questions")

        # Filter and process
        processed = []
        for q in questions:
            if self.is_ai_related(q):
                data = self.extract_question_data(q)
                data["bucket"] = self.categorize_question(q)
                if data["bucket"]:
                    processed.append(data)

        print(f"  {len(processed)} AI-related questions after filtering")

        # Sort by activity
        processed.sort(key=lambda x: x.get("prediction_count", 0), reverse=True)

        # Compute signals
        signals = self.compute_sentiment_signals(processed)

        result = {
            "source": "metaculus",
            "scraped_at": datetime.now().isoformat(),
            "total_questions": len(processed),
            "questions": processed,
            "bucket_signals": signals,
        }

        if save:
            date_str = datetime.now().strftime("%Y-%m-%d")
            output_file = self.output_dir / f"metaculus_{date_str}.json"
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, default=str)
            print(f"Saved to {output_file}")

        return result


def main():
    """Main entry point."""
    scraper = MetaculusScraper()
    result = scraper.run()

    print("\n" + "=" * 60)
    print("METACULUS AI FORECASTS SUMMARY")
    print("=" * 60)
    print(f"AI-related questions found: {result['total_questions']}")

    print("\nTop 10 Questions by Prediction Count:")
    print("-" * 60)
    for i, q in enumerate(result['questions'][:10], 1):
        pred = q.get('community_prediction')
        pred_str = f"{pred*100:.0f}%" if pred else "N/A"
        print(f"{i}. {q['title'][:60]}...")
        print(f"   Prediction: {pred_str} | Forecasters: {q['prediction_count']}")
        print()

    print("\nSignals by Bucket:")
    print("-" * 60)
    for bucket, data in sorted(result['bucket_signals'].items(), key=lambda x: -x[1]['total_predictions']):
        avg = data.get('weighted_avg_prediction', 0)
        print(f"{bucket}:")
        print(f"   Questions: {data['question_count']} | Total predictions: {data['total_predictions']}")
        print(f"   Weighted avg: {avg*100:.1f}%")
        print(f"   Signal: {data['signal_interpretation']}")
        print()


if __name__ == "__main__":
    main()