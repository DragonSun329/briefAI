"""
Hype-Man Agent (The Bull)

Identifies breakout velocity and adoption signals for trending AI entities.
Focus on raw popularity metrics and growth acceleration.
"""

import json
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from loguru import logger


@dataclass
class MomentumSignal:
    """A single momentum signal with value and trend."""
    signal: str
    value: float
    velocity: Optional[str] = None
    trend: Optional[str] = None
    sentiment: Optional[str] = None


@dataclass
class HypeManOutput:
    """Output schema for Hype-Man agent."""
    entity: str
    bull_thesis: str
    momentum_signals: List[Dict[str, Any]]
    technical_velocity_score: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


HYPEMAN_SYSTEM_PROMPT = """You are a "Growth Analyst" identifying breakout trends in AI. Your job is to make the strongest possible BULL CASE for why this entity is gaining traction.

Focus on ADOPTION VELOCITY - not quality, not fundamentals. Your metrics:
- Raw popularity (stars, downloads, mentions)
- Growth rate (week-over-week acceleration)
- Community engagement (forks, issues, discussions)

## Scoring Rubric (0-100)
- 90-100: Viral (exponential growth, top trending)
- 70-89: Strong momentum (consistent growth)
- 50-69: Moderate interest (steady but not breakout)
- 0-49: Low signal (limited adoption)

## Response Format
Return a JSON object with this exact structure:
{
  "entity": "<entity name>",
  "bull_thesis": "<2-3 sentence compelling case for why this entity is breaking out>",
  "momentum_signals": [
    {"signal": "<metric name>", "value": <number>, "velocity": "<change rate>", "trend": "<pattern>"},
    ...
  ],
  "technical_velocity_score": <0-100>
}

Be optimistic but grounded in data. Cite specific numbers where available."""


class HypeManAgent:
    """
    The Bull - identifies breakout velocity and adoption signals.

    Input Data Sources:
    - GitHub stars/forks from github_enhanced_scraper
    - HuggingFace downloads/likes from huggingface_scraper
    - News volume from news pipeline
    - Social buzz from reddit/hackernews_scraper
    - Product Hunt upvotes from product_review_scraper
    """

    def __init__(self, llm_client=None, use_fallback: bool = True):
        """
        Initialize Hype-Man agent.

        Args:
            llm_client: LLM client instance (uses default if not provided)
            use_fallback: Use ProviderSwitcher with free model fallback (default True)
        """
        self.llm_client = llm_client
        self.use_fallback = use_fallback
        self.provider_switcher = None
        self.system_prompt = HYPEMAN_SYSTEM_PROMPT

    def _get_provider_switcher(self):
        """Lazy load provider switcher with free model fallback."""
        if self.provider_switcher is None:
            from utils.provider_switcher import ProviderSwitcher
            self.provider_switcher = ProviderSwitcher()
        return self.provider_switcher

    def _get_llm_client(self):
        """Lazy load LLM client (legacy, used when fallback disabled)."""
        if self.llm_client is None:
            from utils.llm_client import LLMClient
            self.llm_client = LLMClient(enable_caching=True)
        return self.llm_client

    def gather_signals(self, entity_name: str) -> Dict[str, Any]:
        """
        Gather momentum signals for an entity from various data sources.

        Args:
            entity_name: Name of the entity to analyze

        Returns:
            Dictionary of signals from different sources
        """
        signals = {
            "entity": entity_name,
            "github": {},
            "huggingface": {},
            "news": {},
            "social": {},
            "product_hunt": {}
        }

        # Load GitHub data
        try:
            from pathlib import Path
            import glob

            github_files = sorted(
                Path("data/alternative_signals").glob("github_*.json"),
                reverse=True
            )
            if github_files:
                with open(github_files[0], 'r') as f:
                    github_data = json.load(f)
                    for repo in github_data.get("repositories", []):
                        if entity_name.lower() in repo.get("name", "").lower():
                            signals["github"] = {
                                "stars": repo.get("stars", 0),
                                "forks": repo.get("forks", 0),
                                "stars_week": repo.get("stars_this_week", 0),
                                "issues_open": repo.get("open_issues", 0)
                            }
                            break
        except Exception as e:
            logger.debug(f"Could not load GitHub signals: {e}")

        # Load HuggingFace data
        try:
            hf_files = sorted(
                Path("data/alternative_signals").glob("huggingface_*.json"),
                reverse=True
            )
            if hf_files:
                with open(hf_files[0], 'r') as f:
                    hf_data = json.load(f)
                    for model in hf_data.get("models", []):
                        if entity_name.lower() in model.get("id", "").lower():
                            signals["huggingface"] = {
                                "downloads": model.get("downloads", 0),
                                "likes": model.get("likes", 0)
                            }
                            break
        except Exception as e:
            logger.debug(f"Could not load HuggingFace signals: {e}")

        # Load news mentions from trend_radar.db
        try:
            import sqlite3
            conn = sqlite3.connect("data/trend_radar.db")
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) as mentions, AVG(relevance_score) as avg_score
                FROM entity_mentions
                WHERE entity_name LIKE ?
                AND mentioned_at > datetime('now', '-7 days')
            """, (f"%{entity_name}%",))
            row = cursor.fetchone()
            if row and row[0]:
                signals["news"] = {
                    "mentions_7d": row[0],
                    "avg_relevance": round(row[1] or 0, 2)
                }
            conn.close()
        except Exception as e:
            logger.debug(f"Could not load news signals: {e}")

        # Load social signals (Reddit/HackerNews)
        try:
            reddit_files = sorted(
                Path("data/alternative_signals").glob("reddit_*.json"),
                reverse=True
            )
            if reddit_files:
                with open(reddit_files[0], 'r') as f:
                    reddit_data = json.load(f)
                    total_upvotes = 0
                    total_comments = 0
                    for post in reddit_data.get("posts", []):
                        if entity_name.lower() in post.get("title", "").lower():
                            total_upvotes += post.get("score", 0)
                            total_comments += post.get("num_comments", 0)
                    if total_upvotes > 0:
                        signals["social"]["reddit_upvotes"] = total_upvotes
                        signals["social"]["reddit_comments"] = total_comments
        except Exception as e:
            logger.debug(f"Could not load social signals: {e}")

        return signals

    def analyze(self, entity_name: str, signals: Optional[Dict[str, Any]] = None) -> HypeManOutput:
        """
        Run Hype-Man analysis on an entity.

        Args:
            entity_name: Name of the entity to analyze
            signals: Pre-gathered signals (will gather if not provided)

        Returns:
            HypeManOutput with bull thesis and scores
        """
        if signals is None:
            signals = self.gather_signals(entity_name)

        # Build user message with available signals
        user_message = f"""Analyze the following AI entity for adoption momentum:

Entity: {entity_name}

Available Signals:
{json.dumps(signals, indent=2)}

Based on these signals, provide your bull case analysis."""

        logger.info(f"HypeMan analyzing: {entity_name}")

        try:
            if self.use_fallback:
                # Use provider switcher with free model fallback
                switcher = self._get_provider_switcher()
                response_text = switcher.query(
                    prompt=user_message,
                    system_prompt=self.system_prompt + "\n\nIMPORTANT: Return your response as valid JSON format.",
                    max_tokens=4096,
                    temperature=0.3
                )
                # Parse JSON from response
                response = self._parse_json_response(response_text)
            else:
                # Legacy: direct LLM client
                client = self._get_llm_client()
                response = client.chat_structured(
                    system_prompt=self.system_prompt,
                    user_message=user_message,
                    temperature=0.3
                )

            return HypeManOutput(
                entity=response.get("entity", entity_name),
                bull_thesis=response.get("bull_thesis", ""),
                momentum_signals=response.get("momentum_signals", []),
                technical_velocity_score=response.get("technical_velocity_score", 50)
            )

        except Exception as e:
            logger.error(f"HypeMan analysis failed: {e}")
            # Return minimal output on error
            return HypeManOutput(
                entity=entity_name,
                bull_thesis=f"Analysis failed: {e}",
                momentum_signals=[],
                technical_velocity_score=0
            )

    def _parse_json_response(self, response_text: str) -> Dict[str, Any]:
        """Parse JSON from LLM response text."""
        import json
        try:
            # Look for JSON in code blocks
            if "```json" in response_text:
                json_start = response_text.find("```json") + 7
                json_end = response_text.find("```", json_start)
                json_text = response_text[json_start:json_end].strip()
            elif "```" in response_text:
                json_start = response_text.find("```") + 3
                json_end = response_text.find("```", json_start)
                json_text = response_text[json_start:json_end].strip()
            else:
                json_text = response_text.strip()

            return json.loads(json_text)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON: {e}")
            return {}


if __name__ == "__main__":
    # Test the Hype-Man agent
    agent = HypeManAgent()

    # Test with a known entity
    result = agent.analyze("DeepSeek")
    print(json.dumps(result.to_dict(), indent=2))
