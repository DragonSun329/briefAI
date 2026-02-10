"""Perplexity Sonar API client for search-grounded research.

Uses Perplexity's Sonar models for real-time web search with AI synthesis.
Budget-conscious: tracks usage and provides cost estimates.
"""

import os
import json
from typing import Dict, List, Any, Optional
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

# Load .env file
load_dotenv()


class PerplexityResearch:
    """Research client using Perplexity Sonar API."""

    def __init__(self):
        self.api_key = os.environ.get("PERPLEXITY_API_KEY")
        self.api_url = "https://api.perplexity.ai/chat/completions"
        self.cache_dir = Path("data/cache/research")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Pricing per million tokens (USD)
        self.pricing = {
            "sonar": {"input": 1, "output": 1, "per_request": 0.005},
            "sonar-pro": {"input": 3, "output": 15, "per_request": 0.005},
        }

        # Usage tracking
        self.usage_file = Path("data/cache/perplexity_usage.json")
        self.usage = self._load_usage()

    def _load_usage(self) -> Dict:
        """Load usage tracking data."""
        if self.usage_file.exists():
            with open(self.usage_file, "r") as f:
                return json.load(f)
        return {"total_requests": 0, "total_cost_usd": 0.0, "requests": []}

    def _save_usage(self):
        """Save usage tracking data."""
        self.usage_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.usage_file, "w") as f:
            json.dump(self.usage, f, indent=2)

    def _estimate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Estimate cost for a request."""
        pricing = self.pricing.get(model, self.pricing["sonar"])
        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
        return input_cost + output_cost + pricing["per_request"]

    def get_budget_status(self, budget_usd: float = 5.0) -> Dict:
        """Get current budget status."""
        return {
            "budget_usd": budget_usd,
            "spent_usd": self.usage["total_cost_usd"],
            "remaining_usd": budget_usd - self.usage["total_cost_usd"],
            "total_requests": self.usage["total_requests"],
            "avg_cost_per_request": (
                self.usage["total_cost_usd"] / self.usage["total_requests"]
                if self.usage["total_requests"] > 0 else 0
            )
        }

    def research(
        self,
        query: str,
        model: str = "sonar",
        system_prompt: Optional[str] = None,
        search_domain_filter: Optional[List[str]] = None,
        search_recency_filter: Optional[str] = None,  # "day", "week", "month", "year"
        return_citations: bool = True,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Perform search-grounded research using Perplexity Sonar.

        Args:
            query: Research question or topic
            model: "sonar" (fast/cheap) or "sonar-pro" (better quality)
            system_prompt: Custom system prompt for research focus
            search_domain_filter: List of domains to restrict search
            search_recency_filter: Time filter for search results
            return_citations: Include source citations
            dry_run: If True, return estimated cost without making API call

        Returns:
            Dict with research results, citations, and usage info
        """
        if not self.api_key:
            return {"error": "PERPLEXITY_API_KEY not set in environment"}

        # Check cache first
        cache_key = f"{model}_{hash(query + str(search_domain_filter) + str(search_recency_filter))}"
        cache_file = self.cache_dir / f"{cache_key}.json"

        if cache_file.exists():
            with open(cache_file, "r", encoding="utf-8") as f:
                cached = json.load(f)
                cached["from_cache"] = True
                return cached

        # Estimate cost
        estimated_input_tokens = len(query.split()) * 2  # rough estimate
        estimated_output_tokens = 500  # typical response
        estimated_cost = self._estimate_cost(model, estimated_input_tokens, estimated_output_tokens)

        if dry_run:
            return {
                "dry_run": True,
                "estimated_cost_usd": estimated_cost,
                "model": model,
                "query": query,
                "budget_status": self.get_budget_status()
            }

        # Build request
        default_system = (
            "You are a research assistant providing accurate, well-sourced information. "
            "Focus on recent developments and provide specific facts, numbers, and dates. "
            "Always cite your sources."
        )

        messages = [
            {"role": "system", "content": system_prompt or default_system},
            {"role": "user", "content": query}
        ]

        payload = {
            "model": model,
            "messages": messages,
            "return_citations": return_citations,
        }

        if search_domain_filter:
            payload["search_domain_filter"] = search_domain_filter
        if search_recency_filter:
            payload["search_recency_filter"] = search_recency_filter

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        try:
            response = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=60
            )
            response.raise_for_status()
            data = response.json()

            # Extract response
            result = {
                "query": query,
                "model": model,
                "content": data["choices"][0]["message"]["content"],
                "citations": data.get("citations", []),
                "usage": data.get("usage", {}),
                "timestamp": datetime.now().isoformat(),
                "from_cache": False
            }

            # Calculate actual cost
            usage = data.get("usage", {})
            actual_cost = self._estimate_cost(
                model,
                usage.get("prompt_tokens", estimated_input_tokens),
                usage.get("completion_tokens", estimated_output_tokens)
            )
            result["cost_usd"] = actual_cost

            # Update usage tracking
            self.usage["total_requests"] += 1
            self.usage["total_cost_usd"] += actual_cost
            self.usage["requests"].append({
                "timestamp": result["timestamp"],
                "query": query[:100],
                "model": model,
                "cost_usd": actual_cost
            })
            self._save_usage()

            result["budget_status"] = self.get_budget_status()

            # Cache result
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

            return result

        except requests.exceptions.RequestException as e:
            return {"error": str(e), "query": query}

    def research_company(
        self,
        company_name: str,
        focus: str = "recent news and developments",
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Research a specific company.

        Args:
            company_name: Name of the company to research
            focus: Specific aspect to focus on
            dry_run: If True, return estimated cost without API call
        """
        query = f"""
        Research {company_name} with focus on {focus}.

        Please provide:
        1. Recent news and announcements (last 30 days)
        2. Key metrics (funding, valuation, revenue if public)
        3. Product updates or launches
        4. Leadership changes
        5. Competitive positioning

        Be specific with dates, numbers, and sources.
        """

        return self.research(
            query=query,
            model="sonar",
            search_recency_filter="month",
            dry_run=dry_run
        )

    def research_topic(
        self,
        topic: str,
        context: str = "AI industry",
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Research a topic in depth.

        Args:
            topic: Topic to research
            context: Industry or domain context
            dry_run: If True, return estimated cost without API call
        """
        query = f"""
        Provide a comprehensive analysis of "{topic}" in the context of {context}.

        Include:
        1. Current state and recent developments
        2. Key players and their positions
        3. Market trends and forecasts
        4. Challenges and opportunities
        5. Expert opinions and predictions

        Focus on facts and cite sources.
        """

        return self.research(
            query=query,
            model="sonar",
            search_recency_filter="week",
            dry_run=dry_run
        )


# Singleton instance
_researcher: Optional[PerplexityResearch] = None


def get_researcher() -> PerplexityResearch:
    """Get or create the Perplexity researcher instance."""
    global _researcher
    if _researcher is None:
        _researcher = PerplexityResearch()
    return _researcher


if __name__ == "__main__":
    # Budget check only - no API calls
    researcher = get_researcher()
    print("Perplexity Research - Budget Status")
    print("=" * 40)
    status = researcher.get_budget_status()
    print(f"Budget: ${status['budget_usd']:.2f}")
    print(f"Spent:  ${status['spent_usd']:.2f}")
    print(f"Remaining: ${status['remaining_usd']:.2f}")
    print(f"Total requests: {status['total_requests']}")

    # Dry run example
    print("\n" + "=" * 40)
    print("Dry run estimate for company research:")
    result = researcher.research_company("OpenAI", dry_run=True)
    if "error" in result:
        print(f"Error: {result['error']}")
    else:
        print(f"Estimated cost: ${result['estimated_cost_usd']:.4f}")
