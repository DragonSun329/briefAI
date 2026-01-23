"""
Skeptic Agent (The Bear)

Forensic analysis of commercial maturity, code health, and risk factors.
Classification-aware scoring: OSS projects aren't penalized for "missing pricing."
"""

import json
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from enum import Enum
from loguru import logger


class EntityType(Enum):
    """Classification of entity type."""
    OSS_PROJECT = "OSS_PROJECT"
    COMMERCIAL_SAAS = "COMMERCIAL_SAAS"
    UNKNOWN = "UNKNOWN"


class RiskSeverity(Enum):
    """Severity levels for red flags."""
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass
class RedFlag:
    """A risk signal with severity."""
    signal: str
    severity: str


@dataclass
class RiskAssessment:
    """Risk scores from Skeptic analysis."""
    commercial_maturity_score: int
    brand_safety_score: int


@dataclass
class SkepticVerdict:
    """The bear thesis and risk factors."""
    bear_thesis: str
    primary_risk_factor: str
    red_flags: List[Dict[str, str]]


@dataclass
class SkepticOutput:
    """Output schema for Skeptic agent."""
    entity_type: str
    risk_assessment: Dict[str, int]
    skeptic_verdict: Dict[str, Any]
    missing_critical_signals: List[str]
    confidence_in_assessment: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


SKEPTIC_SYSTEM_PROMPT = """You are the "Risk Officer" for an AI intelligence engine. Your goal is to identify **Structural Risks**, **Vaporware**, and **Commercial Weaknesses** in trending AI entities.

You act as the counterbalance to "Hype" (Twitter buzz/GitHub stars). You do not "hate" trends; you "stress-test" them.

## PHASE 1: CLASSIFICATION (Crucial)
Before scoring, determine what you are analyzing. This sets the grading curve.

1. **Open Source Project (OSS):** A library, framework, or model (e.g., AutoGPT, Llama-3).
   * *Success Metric:* Maintainer activity, community health, documentation.
   * *Forgivable:* No revenue, no pricing, no sales team.

2. **Commercial Product (SaaS):** A platform, API, or app (e.g., Jasper, Perplexity).
   * *Success Metric:* Revenue, enterprise logos, pricing tiers, compliance.
   * *Unforgivable:* No pricing, broken links, anonymous team.

## PHASE 2: FORENSIC ANALYSIS

### 1. The "Vaporware" Test (Code & Product)
* **OSS Risk:** Is the `last_commit_date` > 90 days? Is the README just a manifesto with no install instructions? Are issues piling up without answers?
* **SaaS Risk:** Is the "Get Started" button just a waitlist form? Is there a documentation portal, or just a landing page?

### 2. The "Sustainability" Test (Financial)
* **Burn Rate Risk:** If they raised funding >12 months ago with no new announcements, flag as "Zombie Unicorn" risk.
* **Business Model Risk:** If SaaS, is the pricing purely "Contact Sales" (Enterprise only) or is there Self-Serve? (Total opacity = high risk).
* **Audit Trail:** Do the founders have a track record, or are they anonymous avatars?

### 3. "Silence as Signal" (Context-Aware)
Interpret *missing* data based on the Classification:
* *Missing Pricing:* Fatal for SaaS. Irrelevant for OSS.
* *Missing Team Page:* Suspicious for SaaS (Scam risk). Acceptable for niche OSS.
* *Missing Case Studies:* High risk for "Enterprise" tools. Normal for "Developer" tools.

## PHASE 3: SCORING RUBRIC (0-100)

**Commercial Maturity Score:**
* 0-20: Hype only. No product, no company, just a repo/landing page.
* 21-50: Early Beta. Product exists, but unproven (no customers/revenue).
* 51-80: Growth. Verified funding, active users, some logos.
* 81-100: Established. Public pricing, case studies, compliance certifications (SOC2).

**Brand Safety Score:**
* Deduct points for: Security breaches (-30), Lawsuits (-20), Layoffs (-15), Founder drama (-10).

## Response Format
Return a JSON object with this exact structure:
{
  "entity_type": "OSS_PROJECT" | "COMMERCIAL_SAAS",
  "risk_assessment": {
    "commercial_maturity_score": <0-100>,
    "brand_safety_score": <0-100>
  },
  "skeptic_verdict": {
    "bear_thesis": "<2-3 sentence case for why this entity has structural risks>",
    "primary_risk_factor": "<one of: VAPORWARE, MAINTENANCE_DEBT, BURN_RATE, REGULATORY, COMPETITION, UNKNOWN_TEAM>",
    "red_flags": [
      {"signal": "<description>", "severity": "HIGH|MEDIUM|LOW"},
      ...
    ]
  },
  "missing_critical_signals": ["<signal1>", "<signal2>", ...],
  "confidence_in_assessment": "HIGH|MEDIUM|LOW"
}

Be skeptical but fair. Ground your concerns in evidence, not speculation."""


class SkepticAgent:
    """
    The Bear - forensic analysis of commercial maturity and risk factors.

    Input Data Sources:
    - Funding data from funding_enricher, cn_ai_funding_lookup
    - SEC filings from financial_scorer
    - G2/Capterra reviews from product_review_scraper
    - Investor quality from openbook_vc_scraper
    - Last commit date from github_scraper
    - Issue closure ratio from github_scraper
    - News sentiment from news pipeline
    """

    def __init__(self, llm_client=None, use_fallback: bool = True):
        """
        Initialize Skeptic agent.

        Args:
            llm_client: LLM client instance (uses default if not provided)
            use_fallback: Use ProviderSwitcher with free model fallback (default True)
        """
        self.llm_client = llm_client
        self.use_fallback = use_fallback
        self.provider_switcher = None
        self.system_prompt = SKEPTIC_SYSTEM_PROMPT

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
        Gather risk signals for an entity from various data sources.

        Args:
            entity_name: Name of the entity to analyze

        Returns:
            Dictionary of risk signals from different sources
        """
        signals = {
            "entity": entity_name,
            "funding": {},
            "code_health": {},
            "reviews": {},
            "news_sentiment": {},
            "company_info": {}
        }

        # Load funding data from trend_radar.db
        try:
            import sqlite3
            conn = sqlite3.connect("data/trend_radar.db")
            cursor = conn.cursor()
            cursor.execute("""
                SELECT total_funding, funding_stage, funding_updated_at, country
                FROM companies
                WHERE name LIKE ? OR normalized_name LIKE ?
            """, (f"%{entity_name}%", f"%{entity_name.lower()}%"))
            row = cursor.fetchone()
            if row:
                signals["funding"] = {
                    "total_funding_usd": row[0],
                    "stage": row[1],
                    "last_updated": row[2],
                    "country": row[3]
                }
            conn.close()
        except Exception as e:
            logger.debug(f"Could not load funding signals: {e}")

        # Load code health from GitHub data
        try:
            from pathlib import Path
            github_files = sorted(
                Path("data/alternative_signals").glob("github_*.json"),
                reverse=True
            )
            if github_files:
                with open(github_files[0], 'r') as f:
                    github_data = json.load(f)
                    for repo in github_data.get("repositories", []):
                        if entity_name.lower() in repo.get("name", "").lower():
                            signals["code_health"] = {
                                "last_commit": repo.get("pushed_at"),
                                "open_issues": repo.get("open_issues", 0),
                                "has_license": repo.get("license") is not None,
                                "has_wiki": repo.get("has_wiki", False)
                            }
                            break
        except Exception as e:
            logger.debug(f"Could not load code health signals: {e}")

        # Load product reviews from product_review_scraper output
        try:
            from pathlib import Path
            review_files = sorted(
                Path("data/alternative_signals").glob("product_reviews_*.json"),
                reverse=True
            )
            if review_files:
                with open(review_files[0], 'r') as f:
                    review_data = json.load(f)
                    for company, reviews in review_data.get("companies", {}).items():
                        if entity_name.lower() in company.lower():
                            signals["reviews"] = {
                                "g2_rating": reviews.get("g2", {}).get("rating"),
                                "capterra_rating": reviews.get("capterra", {}).get("rating"),
                                "product_hunt_upvotes": reviews.get("product_hunt", {}).get("upvotes")
                            }
                            break
        except Exception as e:
            logger.debug(f"Could not load review signals: {e}")

        # Load news sentiment
        try:
            import sqlite3
            conn = sqlite3.connect("data/trend_radar.db")
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    AVG(CASE WHEN sentiment > 0 THEN 1 WHEN sentiment < 0 THEN -1 ELSE 0 END) as avg_sentiment,
                    COUNT(*) as article_count
                FROM entity_mentions em
                JOIN articles a ON em.article_id = a.id
                WHERE em.entity_name LIKE ?
                AND em.mentioned_at > datetime('now', '-30 days')
            """, (f"%{entity_name}%",))
            row = cursor.fetchone()
            if row and row[1]:
                signals["news_sentiment"] = {
                    "avg_sentiment": round(row[0] or 0, 2),
                    "article_count_30d": row[1]
                }
            conn.close()
        except Exception as e:
            logger.debug(f"Could not load sentiment signals: {e}")

        return signals

    def classify_entity(self, entity_name: str, signals: Dict[str, Any]) -> EntityType:
        """
        Classify entity as OSS project or commercial SaaS.

        Args:
            entity_name: Name of the entity
            signals: Gathered signals

        Returns:
            EntityType classification
        """
        # Heuristics for classification
        oss_indicators = 0
        saas_indicators = 0

        # Check for GitHub presence (strong OSS indicator)
        if signals.get("code_health", {}).get("last_commit"):
            oss_indicators += 2

        # Check for reviews on enterprise platforms (SaaS indicator)
        reviews = signals.get("reviews", {})
        if reviews.get("g2_rating") or reviews.get("capterra_rating"):
            saas_indicators += 2

        # Check for significant funding (SaaS indicator)
        funding = signals.get("funding", {}).get("total_funding_usd", 0)
        if funding and funding > 10_000_000:
            saas_indicators += 1

        # Known OSS keywords
        oss_keywords = ["llama", "whisper", "stable", "diffusion", "gpt-", "bert", "model"]
        if any(kw in entity_name.lower() for kw in oss_keywords):
            oss_indicators += 1

        if oss_indicators > saas_indicators:
            return EntityType.OSS_PROJECT
        elif saas_indicators > oss_indicators:
            return EntityType.COMMERCIAL_SAAS
        else:
            return EntityType.UNKNOWN

    def analyze(self, entity_name: str, signals: Optional[Dict[str, Any]] = None) -> SkepticOutput:
        """
        Run Skeptic analysis on an entity.

        Args:
            entity_name: Name of the entity to analyze
            signals: Pre-gathered signals (will gather if not provided)

        Returns:
            SkepticOutput with bear thesis and risk scores
        """
        if signals is None:
            signals = self.gather_signals(entity_name)

        # Pre-classify for context
        entity_type = self.classify_entity(entity_name, signals)
        signals["preliminary_classification"] = entity_type.value

        # Build user message with available signals
        user_message = f"""Analyze the following AI entity for structural risks and commercial maturity:

Entity: {entity_name}

Available Signals:
{json.dumps(signals, indent=2, default=str)}

Based on these signals and your classification framework, provide your bear case analysis."""

        logger.info(f"Skeptic analyzing: {entity_name}")

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

            return SkepticOutput(
                entity_type=response.get("entity_type", entity_type.value),
                risk_assessment=response.get("risk_assessment", {
                    "commercial_maturity_score": 50,
                    "brand_safety_score": 80
                }),
                skeptic_verdict=response.get("skeptic_verdict", {
                    "bear_thesis": "",
                    "primary_risk_factor": "UNKNOWN",
                    "red_flags": []
                }),
                missing_critical_signals=response.get("missing_critical_signals", []),
                confidence_in_assessment=response.get("confidence_in_assessment", "LOW")
            )

        except Exception as e:
            logger.error(f"Skeptic analysis failed: {e}")
            # Return minimal output on error
            return SkepticOutput(
                entity_type=entity_type.value,
                risk_assessment={
                    "commercial_maturity_score": 0,
                    "brand_safety_score": 0
                },
                skeptic_verdict={
                    "bear_thesis": f"Analysis failed: {e}",
                    "primary_risk_factor": "UNKNOWN",
                    "red_flags": []
                },
                missing_critical_signals=["Analysis failed"],
                confidence_in_assessment="LOW"
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
    # Test the Skeptic agent
    agent = SkepticAgent()

    # Test with a known entity
    result = agent.analyze("DeepSeek")
    print(json.dumps(result.to_dict(), indent=2))
