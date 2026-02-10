"""
Signal Integrator

Loads and integrates data from existing sources into the signal framework:
- Crunchbase: Company presence signals
- GitHub Trending: Technical signals (repos)
- HuggingFace: Technical signals (models/spaces)
- SEC EDGAR: Financial signals (IPO filings)
- OpenBook VC: Investor/funding signals (VC portfolios)
- News Pipeline: Media sentiment signals
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, date
from collections import defaultdict

from .signal_models import (
    Entity, EntityType, SignalCategory, SignalObservation, SignalScore,
    SignalProfile, normalize_entity_id, detect_entity_type
)
from .signal_scorers import (
    TechnicalScorer, CompanyScorer, FinancialScorer,
    ProductScorer, MediaScorer, PodcastScorer
)
from .signal_aggregator import SignalAggregator
from .signal_store import SignalStore


class SignalIntegrator:
    """
    Integrates data from various sources into the signal analysis framework.

    Responsibilities:
    - Load data from existing JSON files and databases
    - Create Entity records with canonical IDs
    - Generate SignalObservations from raw data
    - Score observations and create SignalScores
    - Build unified SignalProfiles
    """

    def __init__(
        self,
        data_dir: Optional[Path] = None,
        db_path: Optional[Path] = None
    ):
        """
        Initialize integrator.

        Args:
            data_dir: Base data directory. Defaults to project's data folder.
            db_path: SQLite database path. Defaults to data/signals.db
        """
        self.data_dir = data_dir or Path(__file__).parent.parent / "data"
        self.db_path = db_path or self.data_dir / "signals.db"

        # Initialize scorers
        self.scorers = {
            SignalCategory.TECHNICAL: TechnicalScorer(),
            SignalCategory.COMPANY_PRESENCE: CompanyScorer(),
            SignalCategory.FINANCIAL: FinancialScorer(),
            SignalCategory.PRODUCT_TRACTION: ProductScorer(),
            SignalCategory.MEDIA_SENTIMENT: MediaScorer(),
        }

        # Initialize aggregator
        self.aggregator = SignalAggregator()

        # Store for database operations
        self.store = SignalStore(self.db_path)

        # Entity cache to avoid duplicates
        self._entity_cache: Dict[str, Entity] = {}

    def load_all_sources(
        self,
        include_crunchbase: bool = True,
        include_github: bool = True,
        include_huggingface: bool = True,
        include_sec: bool = True,
        include_openbook_vc: bool = True,
        include_chinese_vc: bool = True,
        include_news: bool = False,  # Requires separate integration
        include_podcasts: bool = True,
    ) -> Dict[str, Any]:
        """
        Load data from all configured sources.

        Returns:
            Summary dict with counts per source
        """
        results = {
            "entities_created": 0,
            "observations_created": 0,
            "scores_created": 0,
            "profiles_created": 0,
            "by_source": {},
        }

        if include_crunchbase:
            cb_results = self.load_crunchbase_data()
            results["by_source"]["crunchbase"] = cb_results
            results["entities_created"] += cb_results.get("entities", 0)
            results["observations_created"] += cb_results.get("observations", 0)
            results["scores_created"] += cb_results.get("scores", 0)

        if include_github:
            gh_results = self.load_github_trending()
            results["by_source"]["github"] = gh_results
            results["entities_created"] += gh_results.get("entities", 0)
            results["observations_created"] += gh_results.get("observations", 0)
            results["scores_created"] += gh_results.get("scores", 0)

        if include_huggingface:
            hf_results = self.load_huggingface_data()
            results["by_source"]["huggingface"] = hf_results
            results["entities_created"] += hf_results.get("entities", 0)
            results["observations_created"] += hf_results.get("observations", 0)
            results["scores_created"] += hf_results.get("scores", 0)

        if include_sec:
            sec_results = self.load_sec_filings()
            results["by_source"]["sec_edgar"] = sec_results
            results["entities_created"] += sec_results.get("entities", 0)
            results["observations_created"] += sec_results.get("observations", 0)
            results["scores_created"] += sec_results.get("scores", 0)

        if include_openbook_vc:
            vc_results = self.load_openbook_vc_data()
            results["by_source"]["openbook_vc"] = vc_results
            results["entities_created"] += vc_results.get("entities", 0)
            results["observations_created"] += vc_results.get("observations", 0)
            results["scores_created"] += vc_results.get("scores", 0)

        if include_chinese_vc:
            chinese_results = self.load_chinese_vc_data()
            results["by_source"]["chinese_vc"] = chinese_results
            results["entities_created"] += chinese_results.get("entities", 0)
            results["observations_created"] += chinese_results.get("observations", 0)
            results["scores_created"] += chinese_results.get("scores", 0)

        if include_podcasts:
            podcast_results = self.load_podcast_data()
            results["by_source"]["podcasts"] = podcast_results
            results["entities_created"] += podcast_results.get("entities", 0)
            results["observations_created"] += podcast_results.get("observations", 0)
            results["scores_created"] += podcast_results.get("scores", 0)

        # Always load financial market data (enriches existing entities)
        market_results = self.load_financial_market_data()
        results["by_source"]["financial_market"] = market_results
        results["observations_created"] += market_results.get("observations", 0)
        results["scores_created"] += market_results.get("scores", 0)

        # Build profiles for all entities
        profiles = self.build_all_profiles()
        results["profiles_created"] = len(profiles)

        return results

    def load_crunchbase_data(self) -> Dict[str, int]:
        """
        Load Crunchbase company data.

        Expected file: data/crunchbase/ai_companies_*.json
        Or: .worktrees/trend-radar/data/crunchbase/ai_companies_*.json
        """
        # Try multiple locations
        possible_paths = [
            self.data_dir / "crunchbase",
            self.data_dir.parent / ".worktrees" / "trend-radar" / "data" / "crunchbase",
        ]

        cb_file = None
        for path in possible_paths:
            files = list(path.glob("ai_companies_*.json")) if path.exists() else []
            if files:
                cb_file = max(files)  # Most recent
                break

        if not cb_file:
            print("No Crunchbase data file found")
            return {"entities": 0, "observations": 0, "scores": 0}

        with open(cb_file, encoding="utf-8") as f:
            companies = json.load(f)

        entities_created = 0
        observations_created = 0
        scores_created = 0

        for idx, company in enumerate(companies):
            name = company.get("name", "").strip()
            if not name:
                continue

            # Create or get entity
            entity = self._get_or_create_entity(
                name=name,
                entity_type=EntityType.COMPANY,
                source_category=SignalCategory.COMPANY_PRESENCE,
            )
            if entity:
                entities_created += 1

            # Create observation
            # CB Rank is inferred from position in list (top 1000 by significance)
            cb_rank = idx + 1

            raw_data = {
                "source": "crunchbase",
                "cb_rank": cb_rank,
                "name": name,
            }

            observation = SignalObservation(
                entity_id=entity.id,
                source_id="crunchbase_top1000",
                category=SignalCategory.COMPANY_PRESENCE,
                raw_value=cb_rank,
                raw_value_unit="rank",
                raw_data=raw_data,
                confidence=0.9,
            )

            self.store.add_observation(observation)
            observations_created += 1

            # Score the observation
            scorer = self.scorers[SignalCategory.COMPANY_PRESENCE]
            score_value = scorer.score(raw_data)
            confidence = scorer.get_confidence(raw_data)

            score = SignalScore(
                observation_id=observation.id,
                entity_id=entity.id,
                source_id="crunchbase_top1000",
                category=SignalCategory.COMPANY_PRESENCE,
                score=score_value,
            )

            self.store.add_score(score)
            scores_created += 1

        print(f"Loaded {entities_created} companies from Crunchbase")
        return {
            "entities": entities_created,
            "observations": observations_created,
            "scores": scores_created,
        }

    def load_github_trending(self) -> Dict[str, int]:
        """
        Load GitHub trending repository data.

        Expected file: data/alternative_signals/github_trending_*.json

        Also enriches company entities with technical scores when the org
        name matches a known company (e.g., openai/whisper -> OpenAI).
        """
        possible_paths = [
            self.data_dir / "alternative_signals",
            self.data_dir.parent / ".worktrees" / "trend-radar" / "data" / "alternative_signals",
        ]

        gh_file = None
        for path in possible_paths:
            files = list(path.glob("github_trending_*.json")) if path.exists() else []
            if files:
                gh_file = max(files)
                break

        if not gh_file:
            print("No GitHub trending data file found")
            return {"entities": 0, "observations": 0, "scores": 0}

        with open(gh_file, encoding="utf-8") as f:
            repos = json.load(f)

        entities_created = 0
        observations_created = 0
        scores_created = 0

        # Track org -> aggregated metrics for company enrichment
        org_metrics: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            "total_stars": 0,
            "total_repos": 0,
            "max_stars": 0,
        })

        for repo in repos:
            name = repo.get("name", "").strip()
            if not name:
                continue

            metrics = repo.get("metrics", {})
            stars = metrics.get("stars", 0)

            # Extract org name from URL for company linking
            # URL format: https://github.com/org/repo
            url = repo.get("url", "")
            org_name = None
            if "github.com/" in url:
                parts = url.split("github.com/")[1].split("/")
                if len(parts) >= 1:
                    org_name = parts[0].strip()
                    org_metrics[org_name]["total_stars"] += stars
                    org_metrics[org_name]["total_repos"] += 1
                    org_metrics[org_name]["max_stars"] = max(
                        org_metrics[org_name]["max_stars"], stars
                    )

            # Create entity for the repository
            entity = self._get_or_create_entity(
                name=name,
                entity_type=EntityType.TECHNOLOGY,
                source_category=SignalCategory.TECHNICAL,
                description=repo.get("description"),
                website=repo.get("url"),
            )
            if entity:
                entities_created += 1

            # Create observation
            raw_data = {
                "source": "github",
                "stars": stars,
                "stars_week": metrics.get("stars_today", 0) * 7,  # Estimate weekly
                "language": metrics.get("language"),
                "url": repo.get("url"),
            }

            observation = SignalObservation(
                entity_id=entity.id,
                source_id="github_trending",
                category=SignalCategory.TECHNICAL,
                raw_value=stars,
                raw_value_unit="count",
                raw_data=raw_data,
                confidence=0.85,
            )

            self.store.add_observation(observation)
            observations_created += 1

            # Score the observation
            scorer = self.scorers[SignalCategory.TECHNICAL]
            score_value = scorer.score(raw_data)

            score = SignalScore(
                observation_id=observation.id,
                entity_id=entity.id,
                source_id="github_trending",
                category=SignalCategory.TECHNICAL,
                score=score_value,
            )

            self.store.add_score(score)
            scores_created += 1

        # Enrich existing company entities with aggregated tech signals
        company_enrichments = self._enrich_companies_with_github_data(org_metrics)
        scores_created += company_enrichments

        print(f"Loaded {entities_created} repos from GitHub trending")
        print(f"  Enriched {company_enrichments} companies with technical scores")
        return {
            "entities": entities_created,
            "observations": observations_created,
            "scores": scores_created,
        }

    def _enrich_companies_with_github_data(
        self,
        org_metrics: Dict[str, Dict[str, Any]]
    ) -> int:
        """
        Add technical scores to company entities based on GitHub org metrics.

        Matches org names (e.g., 'openai') to company entities (e.g., 'OpenAI')
        and adds aggregated technical scores.

        Returns:
            Number of companies enriched
        """
        enriched = 0
        scorer = self.scorers[SignalCategory.TECHNICAL]

        # Common GitHub org -> company name mappings
        org_to_company = {
            "openai": "openai",
            "google": "google",
            "microsoft": "microsoft",
            "meta": "meta",
            "facebook": "meta",
            "facebookresearch": "meta",
            "nvidia": "nvidia",
            "anthropic": "anthropic",
            "huggingface": "huggingface",
            "google-deepmind": "google",
            "deepmind": "google",
            "apple": "apple",
            "amazon": "amazon",
            "aws": "amazon",
            "ibm": "ibm",
            "intel": "intel",
            "salesforce": "salesforce",
            "alibaba": "alibaba",
            "tencent": "tencent",
            "baidu": "baidu",
            "twitter": "x-formerly-twitter",
            "x": "x-formerly-twitter",
            "langchain-ai": "langchain",
            "langgenius": "langgenius",
            "home-assistant": "home-assistant",
            "vercel": "vercel",
            "supabase": "supabase",
            "modular": "modular",
        }

        for org_name, metrics in org_metrics.items():
            # Skip orgs with very few stars (likely not notable)
            if metrics["total_stars"] < 100:
                continue

            # Map org name to company canonical ID
            org_lower = org_name.lower()
            canonical_company = org_to_company.get(org_lower, org_lower)
            canonical_org = normalize_entity_id(canonical_company)

            # Check if we have a company entity with this ID
            if canonical_org not in self._entity_cache:
                continue

            company_entity = self._entity_cache[canonical_org]

            # Only enrich company entities
            if company_entity.entity_type != EntityType.COMPANY:
                continue

            # Create observation for company's GitHub presence
            raw_data = {
                "source": "github_org",
                "stars": metrics["total_stars"],
                "repos": metrics["total_repos"],
                "max_repo_stars": metrics["max_stars"],
            }

            observation = SignalObservation(
                entity_id=company_entity.id,
                source_id="github_org_aggregate",
                category=SignalCategory.TECHNICAL,
                raw_value=metrics["total_stars"],
                raw_value_unit="count",
                raw_data=raw_data,
                confidence=0.75,  # Slightly lower - aggregated data
            )

            self.store.add_observation(observation)

            # Score based on aggregated metrics
            score_value = scorer.score(raw_data)

            score = SignalScore(
                observation_id=observation.id,
                entity_id=company_entity.id,
                source_id="github_org_aggregate",
                category=SignalCategory.TECHNICAL,
                score=score_value,
            )

            self.store.add_score(score)
            enriched += 1

        return enriched

    def load_huggingface_data(self) -> Dict[str, int]:
        """
        Load HuggingFace trending models and spaces.

        Expected file: data/alternative_signals/huggingface_trending_*.json

        Also enriches company entities with technical scores when the org
        name matches a known company (e.g., meta-llama -> Meta).
        """
        hf_dir = self.data_dir / "alternative_signals"
        hf_files = list(hf_dir.glob("huggingface_trending_*.json")) if hf_dir.exists() else []

        if not hf_files:
            print("No HuggingFace data file found")
            return {"entities": 0, "observations": 0, "scores": 0}

        hf_file = max(hf_files)

        with open(hf_file, encoding="utf-8") as f:
            signals = json.load(f)

        entities_created = 0
        observations_created = 0
        scores_created = 0

        # Track org -> aggregated metrics for company enrichment
        org_metrics: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            "total_downloads": 0,
            "total_likes": 0,
            "total_models": 0,
        })

        for signal in signals:
            name = signal.get("name", "").strip()
            if not name:
                continue

            metrics = signal.get("metrics", {})
            signal_type = signal.get("signal_type", "")
            downloads = metrics.get("downloads", 0) or 0
            likes = metrics.get("likes", 0) or 0

            # Extract org name for company linking
            if "/" in name:
                org_name = name.split("/")[0].strip()
                org_metrics[org_name]["total_downloads"] += downloads
                org_metrics[org_name]["total_likes"] += likes
                org_metrics[org_name]["total_models"] += 1

            # Create entity
            entity = self._get_or_create_entity(
                name=name,
                entity_type=EntityType.TECHNOLOGY,
                source_category=SignalCategory.TECHNICAL,
                description=signal.get("description"),
                website=signal.get("url"),
            )
            if entity:
                entities_created += 1

            # Determine source type
            if "model" in signal_type:
                source = "huggingface_model"
            else:
                source = "huggingface_space"

            # Create observation
            raw_data = {
                "source": source,
                "downloads": downloads,
                "downloads_month": metrics.get("downloads_month", 0),
                "likes": likes,
                "task": metrics.get("task"),
                "sdk": metrics.get("sdk"),
                "hardware": metrics.get("hardware"),
                "tags": metrics.get("tags", []),
            }

            observation = SignalObservation(
                entity_id=entity.id,
                source_id=source,
                category=SignalCategory.TECHNICAL,
                raw_value=downloads or likes,
                raw_value_unit="count",
                raw_data=raw_data,
                confidence=0.85,
            )

            self.store.add_observation(observation)
            observations_created += 1

            # Score the observation
            scorer = self.scorers[SignalCategory.TECHNICAL]
            score_value = scorer.score(raw_data)

            score = SignalScore(
                observation_id=observation.id,
                entity_id=entity.id,
                source_id=source,
                category=SignalCategory.TECHNICAL,
                score=score_value,
            )

            self.store.add_score(score)
            scores_created += 1

        # Enrich existing company entities with aggregated HuggingFace signals
        company_enrichments = self._enrich_companies_with_hf_data(org_metrics)
        scores_created += company_enrichments

        print(f"Loaded {entities_created} items from HuggingFace")
        print(f"  Enriched {company_enrichments} companies with HF technical scores")
        return {
            "entities": entities_created,
            "observations": observations_created,
            "scores": scores_created,
        }

    def _enrich_companies_with_hf_data(
        self,
        org_metrics: Dict[str, Dict[str, Any]]
    ) -> int:
        """
        Add technical scores to company entities based on HuggingFace org metrics.

        Uses a mapping to normalize org names (e.g., 'meta-llama' -> 'meta').

        Returns:
            Number of companies enriched
        """
        enriched = 0
        scorer = self.scorers[SignalCategory.TECHNICAL]

        # Common HuggingFace org -> company name mappings
        org_to_company = {
            "meta-llama": "meta",
            "openai": "openai",
            "google": "google",
            "microsoft": "microsoft",
            "facebook": "meta",
            "facebookresearch": "meta",
            "facebookai": "meta",
            "google-bert": "google",
            "huggingface": "huggingface",
            "anthropic": "anthropic",
            "nvidia": "nvidia",
            "intel": "intel",
            "amazon": "amazon",
            "apple": "apple",
            "ibm": "ibm",
            "salesforce": "salesforce",
            "alibaba": "alibaba",
            "tencent": "tencent",
            "baidu": "baidu",
            "bytedance": "bytedance",
            "deepmind": "google",
            "google-deepmind": "google",
        }

        for org_name, metrics in org_metrics.items():
            # Skip orgs with very few downloads (likely not notable)
            if metrics["total_downloads"] < 1000 and metrics["total_likes"] < 10:
                continue

            # Map org name to company canonical ID
            org_lower = org_name.lower()
            canonical_company = org_to_company.get(org_lower, org_lower)
            canonical_company = normalize_entity_id(canonical_company)

            # Check if we have a company entity with this ID
            if canonical_company not in self._entity_cache:
                continue

            company_entity = self._entity_cache[canonical_company]

            # Only enrich company entities
            if company_entity.entity_type != EntityType.COMPANY:
                continue

            # Create observation for company's HuggingFace presence
            raw_data = {
                "source": "huggingface_org",
                "downloads": metrics["total_downloads"],
                "likes": metrics["total_likes"],
                "models": metrics["total_models"],
            }

            observation = SignalObservation(
                entity_id=company_entity.id,
                source_id="huggingface_org_aggregate",
                category=SignalCategory.TECHNICAL,
                raw_value=metrics["total_downloads"],
                raw_value_unit="count",
                raw_data=raw_data,
                confidence=0.75,
            )

            self.store.add_observation(observation)

            # Score based on aggregated metrics
            score_value = scorer.score(raw_data)

            score = SignalScore(
                observation_id=observation.id,
                entity_id=company_entity.id,
                source_id="huggingface_org_aggregate",
                category=SignalCategory.TECHNICAL,
                score=score_value,
            )

            self.store.add_score(score)
            enriched += 1

        return enriched

    def load_sec_filings(self) -> Dict[str, int]:
        """
        Load SEC EDGAR filing data.

        Expected file: data/alternative_signals/sec_filings_*.json
        """
        sec_dir = self.data_dir / "alternative_signals"
        sec_files = list(sec_dir.glob("sec_*.json")) if sec_dir.exists() else []

        # Also check worktrees
        worktree_dir = self.data_dir.parent / ".worktrees" / "trend-radar" / "data" / "alternative_signals"
        if worktree_dir.exists():
            sec_files.extend(worktree_dir.glob("sec_*.json"))

        if not sec_files:
            print("No SEC filing data found")
            return {"entities": 0, "observations": 0, "scores": 0}

        entities_created = 0
        observations_created = 0
        scores_created = 0

        for sec_file in sec_files:
            try:
                with open(sec_file, encoding="utf-8") as f:
                    filings = json.load(f)
            except:
                continue

            for filing in filings:
                name = filing.get("company_name", filing.get("name", "")).strip()
                if not name:
                    continue

                # Create entity
                entity = self._get_or_create_entity(
                    name=name,
                    entity_type=EntityType.COMPANY,
                    source_category=SignalCategory.FINANCIAL,
                )
                if entity:
                    entities_created += 1

                # Create observation
                raw_data = {
                    "source": "sec_edgar",
                    "filing_type": filing.get("filing_type", filing.get("form_type", "")),
                    "filing_date": filing.get("filing_date", filing.get("date", "")),
                    "description": filing.get("description", ""),
                }

                observation = SignalObservation(
                    entity_id=entity.id,
                    source_id="sec_edgar",
                    category=SignalCategory.FINANCIAL,
                    raw_data=raw_data,
                    confidence=0.95,  # Official filings are high confidence
                )

                self.store.add_observation(observation)
                observations_created += 1

                # Score the observation
                scorer = self.scorers[SignalCategory.FINANCIAL]
                score_value = scorer.score(raw_data)

                score = SignalScore(
                    observation_id=observation.id,
                    entity_id=entity.id,
                    source_id="sec_edgar",
                    category=SignalCategory.FINANCIAL,
                    score=score_value,
                )

                self.store.add_score(score)
                scores_created += 1

        print(f"Loaded {entities_created} companies from SEC filings")
        return {
            "entities": entities_created,
            "observations": observations_created,
            "scores": scores_created,
        }

    def load_financial_market_data(self) -> Dict[str, int]:
        """
        Load financial market data (stock prices) and enrich existing company entities.

        Uses financial_signals JSON files (generated by utils/financial_signals.py)
        and maps stock tickers to company entities for FINANCIAL scores.

        Expected file: data/alternative_signals/financial_signals_YYYY-MM-DD.json
        """
        from .config_loader import load_ticker_to_company

        # Find most recent financial signals file
        alt_dir = self.data_dir / "alternative_signals"
        signal_files = list(alt_dir.glob("financial_signals_2*.json")) if alt_dir.exists() else []
        signal_files = [f for f in signal_files if "_cn_" not in f.name]

        if not signal_files:
            print("No financial market data found")
            return {"observations": 0, "scores": 0}

        signal_files.sort(key=lambda f: f.name, reverse=True)
        latest_file = signal_files[0]

        with open(latest_file, encoding="utf-8") as f:
            data = json.load(f)

        observations_created = 0
        scores_created = 0

        # Get ticker-to-company mapping
        ticker_to_company = load_ticker_to_company()

        # Process equities
        equities = data.get("raw", {}).get("equities", [])
        scorer = self.scorers[SignalCategory.FINANCIAL]

        for equity in equities:
            ticker = equity.get("ticker", "")
            if not ticker:
                continue

            # Check if we have a company mapping for this ticker
            canonical_id = ticker_to_company.get(ticker)
            if not canonical_id:
                continue

            # Check if company entity exists in cache
            if canonical_id not in self._entity_cache:
                continue

            company_entity = self._entity_cache[canonical_id]

            # Create raw data for scoring
            change_7d = equity.get("change_7d_pct", 0)
            change_30d = equity.get("change_30d_pct", 0)
            volume_ratio = equity.get("volume_ratio", 1.0)

            raw_data = {
                "source": "market_data",
                "ticker": ticker,
                "price": equity.get("price", 0),
                "change_1d_pct": equity.get("change_1d_pct", 0),
                "change_7d_pct": change_7d,
                "change_30d_pct": change_30d,
                "volume_ratio": volume_ratio,
            }

            # Score: Convert market performance to a 0-100 score
            # Positive momentum = higher score
            # Base score of 50, add/subtract based on performance
            base_score = 50.0
            # Weekly change contributes up to ±25 points
            weekly_contrib = min(25, max(-25, change_7d * 2.5))
            # Monthly change contributes up to ±15 points
            monthly_contrib = min(15, max(-15, change_30d * 0.5))
            # Volume above average is bullish signal (up to 10 points)
            volume_contrib = min(10, max(0, (volume_ratio - 1) * 10))

            score_value = base_score + weekly_contrib + monthly_contrib + volume_contrib
            score_value = min(100, max(0, score_value))

            observation = SignalObservation(
                entity_id=company_entity.id,
                source_id="yahoo_finance",
                category=SignalCategory.FINANCIAL,
                raw_value=equity.get("price", 0),
                raw_value_unit="usd",
                raw_data=raw_data,
                confidence=0.85,  # Market data is reliable
            )

            self.store.add_observation(observation)
            observations_created += 1

            score = SignalScore(
                observation_id=observation.id,
                entity_id=company_entity.id,
                source_id="yahoo_finance",
                category=SignalCategory.FINANCIAL,
                score=score_value,
            )

            self.store.add_score(score)
            scores_created += 1

        print(f"Enriched {scores_created} companies with financial market data from {latest_file.name}")
        return {
            "observations": observations_created,
            "scores": scores_created,
        }

    def load_openbook_vc_data(self) -> Dict[str, int]:
        """
        Load OpenBook VC portfolio data (VC firms + their investments from Kaggle).

        Expected file: data/alternative_signals/openbook_vc_portfolios.json
        Also loads: data/alternative_signals/openbook_vc_*.json for VC firm details
        """
        alt_dir = self.data_dir / "alternative_signals"

        # Load enriched portfolio data (VCs + investments)
        portfolio_file = alt_dir / "openbook_vc_portfolios.json"
        if not portfolio_file.exists():
            print("No OpenBook VC portfolio data found")
            return {"entities": 0, "observations": 0, "scores": 0}

        with open(portfolio_file, encoding="utf-8") as f:
            portfolio_data = json.load(f)

        # Also try to load raw OpenBook data for team/contact info
        openbook_files = list(alt_dir.glob("openbook_vc_2*.json")) if alt_dir.exists() else []
        vc_details = {}
        if openbook_files:
            openbook_file = max(openbook_files)
            with open(openbook_file, encoding="utf-8") as f:
                raw_data = json.load(f)
            # Index by firm name for quick lookup
            for firm in raw_data.get("vc_firms", []):
                vc_details[firm.get("name", "").lower()] = firm
            # Index investors by firm
            vc_investors = defaultdict(list)
            for inv in raw_data.get("investors", []):
                firm_name = inv.get("firm_name", "").lower()
                if firm_name:
                    vc_investors[firm_name].append(inv)

        entities_created = 0
        observations_created = 0
        scores_created = 0

        # Build reverse index: company -> list of VCs that invested
        company_investors: Dict[str, List[Dict]] = defaultdict(list)

        for vc in portfolio_data.get("vc_portfolios", []):
            vc_name = vc.get("name", "").strip()
            if not vc_name:
                continue

            # Create entity for the VC firm itself
            vc_entity = self._get_or_create_entity(
                name=vc_name,
                entity_type=EntityType.COMPANY,
                source_category=SignalCategory.FINANCIAL,
                website=vc.get("url"),
            )
            if vc_entity:
                entities_created += 1

            # Get additional details from raw OpenBook data
            detail = vc_details.get(vc_name.lower(), {})

            # Create observation for the VC firm
            raw_data = {
                "source": "openbook_vc",
                "vc_name": vc_name,
                "portfolio_count": vc.get("portfolio_count", 0),
                "team_count": vc.get("team_count", 0),
                "ai_focus": vc.get("ai_focus", False),
                "url": vc.get("url", ""),
            }

            observation = SignalObservation(
                entity_id=vc_entity.id,
                source_id="openbook_vc",
                category=SignalCategory.FINANCIAL,
                raw_value=vc.get("portfolio_count", 0),
                raw_value_unit="investments",
                raw_data=raw_data,
                confidence=0.8,
            )

            self.store.add_observation(observation)
            observations_created += 1

            # Score the VC firm
            scorer = self.scorers[SignalCategory.FINANCIAL]
            # Score based on portfolio size and AI focus
            portfolio_count = vc.get("portfolio_count", 0)
            base_score = min(portfolio_count / 100, 1.0) * 0.7  # Max 0.7 from portfolio
            if vc.get("ai_focus"):
                base_score += 0.2  # Bonus for AI focus
            score_value = min(base_score, 1.0)

            score = SignalScore(
                observation_id=observation.id,
                entity_id=vc_entity.id,
                source_id="openbook_vc",
                category=SignalCategory.FINANCIAL,
                score=score_value,
            )

            self.store.add_score(score)
            scores_created += 1

            # Index portfolio companies for later enrichment
            for investment in vc.get("portfolio_companies", []):
                company_name = investment.get("company", "").strip()
                if company_name:
                    company_investors[company_name.lower()].append({
                        "vc_name": vc_name,
                        "round_type": investment.get("round_type", ""),
                        "amount_usd": investment.get("amount_usd", ""),
                        "funded_at": investment.get("funded_at", ""),
                        "ai_focus_vc": vc.get("ai_focus", False),
                    })

        # Store company->investors mapping for enrichment
        self._vc_investments = company_investors

        print(f"Loaded {entities_created} VC firms from OpenBook")
        print(f"  Portfolio companies indexed: {len(company_investors)}")
        return {
            "entities": entities_created,
            "observations": observations_created,
            "scores": scores_created,
            "portfolio_companies": len(company_investors),
        }

    def load_chinese_vc_data(self) -> Dict[str, int]:
        """
        Load Chinese VC portfolio companies from trend_radar.db.

        Sources:
        - HongShan (红杉中国): ~150 companies
        - Matrix China: ~150 companies
        - ZhenFund (真格基金): ~60 companies
        - Qiming (启明创投): ~50 companies
        - 5Y Capital (五源资本): ~35 companies
        - Baidu Ventures (百度风投): ~35 companies
        - Sinovation (创新工场): ~25 companies
        """
        import sqlite3

        # Chinese VC source IDs in trend_radar.db
        chinese_vc_sources = [
            ('sinovation_ventures', 'Sinovation Ventures', 0.85),
            ('qiming_ventures', 'Qiming Venture Partners', 0.85),
            ('zhenfund', 'ZhenFund', 0.80),
            ('matrix_china', 'Matrix Partners China', 0.90),
            ('5y_capital', '5Y Capital', 0.80),
            ('baidu_ventures', 'Baidu Ventures', 0.85),
            ('hongshan_china', 'HongShan', 0.95),
            ('sourcecode_capital', 'Source Code Capital', 0.80),
        ]

        # Find trend_radar.db
        possible_paths = [
            self.data_dir.parent / ".worktrees" / "trend-radar" / "data" / "trend_radar.db",
            self.data_dir / "trend_radar.db",
        ]

        db_path = None
        for path in possible_paths:
            if path.exists():
                db_path = path
                break

        if not db_path:
            print("No trend_radar.db found for Chinese VC data")
            return {"entities": 0, "observations": 0, "scores": 0}

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        source_ids = [s[0] for s in chinese_vc_sources]
        placeholders = ','.join(['?' for _ in source_ids])

        # Get companies with their VC backers
        cursor.execute(f'''
            SELECT
                c.id,
                c.name,
                c.normalized_name,
                c.source_count,
                GROUP_CONCAT(o.source_id) as sources
            FROM companies c
            JOIN observations o ON c.id = o.company_id
            WHERE o.source_id IN ({placeholders})
            GROUP BY c.id
            ORDER BY c.source_count DESC
        ''', source_ids)

        rows = cursor.fetchall()
        conn.close()

        entities_created = 0
        observations_created = 0
        scores_created = 0

        for row in rows:
            company_id, name, normalized_name, source_count, sources_str = row
            name = name.strip() if name else ""

            if not name or len(name) < 2:
                continue

            # Skip navigation/UI elements
            skip_names = ['companies', 'portfolio', 'home', 'about', 'team', 'news', 'menu', 'all', 'founded']
            if name.lower() in skip_names:
                continue

            vc_sources = sources_str.split(',') if sources_str else []

            # Create entity
            entity = self._get_or_create_entity(
                name=name,
                entity_type=EntityType.COMPANY,
                source_category=SignalCategory.COMPANY_PRESENCE,
            )
            if entity:
                entities_created += 1

            # Calculate score based on VC coverage
            num_vcs = len(vc_sources)

            # Higher score for more VC coverage and top-tier VCs
            base_score = min(num_vcs * 20, 60)  # Up to 60 for 3+ VCs

            # Bonus for top-tier VCs
            tier1_vcs = ['hongshan_china', 'matrix_china', 'qiming_ventures']
            has_tier1 = any(vc in tier1_vcs for vc in vc_sources)
            if has_tier1:
                base_score += 20

            # Bonus for AI-focused VCs
            ai_vcs = ['baidu_ventures', 'sinovation_ventures']
            has_ai_vc = any(vc in ai_vcs for vc in vc_sources)
            if has_ai_vc:
                base_score += 10

            score_value = min(base_score, 100)

            raw_data = {
                'source': 'chinese_vc_portfolio',
                'vc_count': num_vcs,
                'vc_sources': vc_sources,
            }

            observation = SignalObservation(
                entity_id=entity.id,
                source_id='chinese_vc_aggregate',
                category=SignalCategory.COMPANY_PRESENCE,
                raw_value=num_vcs,
                raw_value_unit='vc_count',
                raw_data=raw_data,
                confidence=0.85,
            )
            self.store.add_observation(observation)
            observations_created += 1

            score = SignalScore(
                observation_id=observation.id,
                entity_id=entity.id,
                source_id='chinese_vc_aggregate',
                category=SignalCategory.COMPANY_PRESENCE,
                score=score_value,
            )
            self.store.add_score(score)
            scores_created += 1

        print(f"Loaded {entities_created} companies from Chinese VCs")
        return {
            "entities": entities_created,
            "observations": observations_created,
            "scores": scores_created,
        }

    def load_podcast_data(self) -> Dict[str, int]:
        """
        Load podcast transcript data and extract entity signals.

        Expected file: data/cache/podcasts_*.json

        Podcasts provide expert signals through mentions and discussions
        of companies, technologies, and trends.
        """
        cache_dir = self.data_dir / "cache"
        podcast_files = list(cache_dir.glob("podcasts_*.json")) if cache_dir.exists() else []

        if not podcast_files:
            print("No podcast data files found")
            return {"entities": 0, "observations": 0, "scores": 0}

        # Get most recent file
        podcast_file = max(podcast_files)

        with open(podcast_file, encoding="utf-8") as f:
            episodes = json.load(f)

        print(f"Loading {len(episodes)} podcast episodes from {podcast_file.name}")

        entities_created = 0
        observations_created = 0
        scores_created = 0

        # Initialize podcast scorer
        podcast_scorer = PodcastScorer()

        # Aggregate entity mentions across all episodes
        entity_mentions: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            "mention_count": 0,
            "shows": [],
            "episode_count": 0,
            "max_credibility": 7,
            "total_duration": 0,
            "episodes": [],
            "is_main_topic": False,
        })

        for episode in episodes:
            entities = episode.get("entities", [])
            podcast_channel = episode.get("podcast_channel", "Unknown")
            credibility = episode.get("credibility_score", 7)
            duration = episode.get("duration_min", 0)
            title = episode.get("title", "")
            content = episode.get("content", "")

            for entity_name in entities:
                if not entity_name or len(entity_name) < 2:
                    continue

                # Skip generic terms
                skip_terms = ['ai', 'ml', 'data', 'technology', 'the', 'and', 'or']
                if entity_name.lower() in skip_terms:
                    continue

                # Count mentions in content
                mention_count = content.lower().count(entity_name.lower())
                mention_count = max(1, mention_count)  # At least 1 if in entities list

                agg = entity_mentions[entity_name.lower()]
                agg["mention_count"] += mention_count
                agg["shows"].append(podcast_channel)
                agg["episode_count"] += 1
                agg["max_credibility"] = max(agg["max_credibility"], credibility)
                agg["total_duration"] += duration
                agg["episodes"].append({
                    "title": title,
                    "channel": podcast_channel,
                    "credibility": credibility,
                })

                # Check if entity is main topic (in title)
                if entity_name.lower() in title.lower():
                    agg["is_main_topic"] = True

        # Create signals for entities with significant mentions
        for entity_name, agg in entity_mentions.items():
            # Skip entities with only 1 mention from 1 show (low signal)
            if agg["episode_count"] == 1 and agg["mention_count"] < 3:
                continue

            # Create or get entity
            # Detect entity type - most podcast mentions are companies/people
            entity = self._get_or_create_entity(
                name=entity_name.title(),  # Capitalize properly
                entity_type=EntityType.COMPANY,  # Default to company
                source_category=SignalCategory.MEDIA_SENTIMENT,
            )
            if entity:
                entities_created += 1

            # Prepare raw data for scorer
            raw_data = {
                "source": "podcast",
                "host_credibility": agg["max_credibility"],
                "mention_count": agg["mention_count"],
                "duration_min": agg["total_duration"],
                "is_main_topic": agg["is_main_topic"],
                "episode_count": agg["episode_count"],
                "shows": agg["shows"],
            }

            # Create observation
            observation = SignalObservation(
                entity_id=entity.id,
                source_id="podcast_transcripts",
                category=SignalCategory.MEDIA_SENTIMENT,
                raw_value=agg["mention_count"],
                raw_value_unit="mentions",
                raw_data=raw_data,
                confidence=podcast_scorer.get_confidence(raw_data),
            )

            self.store.add_observation(observation)
            observations_created += 1

            # Score the observation
            score_value = podcast_scorer.score(raw_data)

            score = SignalScore(
                observation_id=observation.id,
                entity_id=entity.id,
                source_id="podcast_transcripts",
                category=SignalCategory.MEDIA_SENTIMENT,
                score=score_value,
            )

            self.store.add_score(score)
            scores_created += 1

        # Log multi-show entities (high signal value)
        multi_show = [
            (name, agg) for name, agg in entity_mentions.items()
            if len(set(agg["shows"])) >= 2
        ]
        if multi_show:
            print(f"  Multi-show entities (high signal): {len(multi_show)}")
            for name, agg in sorted(multi_show, key=lambda x: -len(set(x[1]['shows'])))[:5]:
                shows = list(set(agg['shows']))
                print(f"    - {name.title()}: {len(shows)} shows, {agg['mention_count']} mentions")

        print(f"Loaded {entities_created} entities from podcasts")
        return {
            "entities": entities_created,
            "observations": observations_created,
            "scores": scores_created,
            "episodes_processed": len(episodes),
        }

    def enrich_entity_with_vc_data(self, entity_name: str) -> Optional[Dict[str, Any]]:
        """
        Get VC investment data for a company entity.

        Args:
            entity_name: Company name to look up

        Returns:
            Dict with investor info or None if not found
        """
        if not hasattr(self, "_vc_investments"):
            return None

        investors = self._vc_investments.get(entity_name.lower(), [])
        if not investors:
            return None

        # Calculate total raised
        total_raised = 0
        for inv in investors:
            try:
                amount = float(inv.get("amount_usd", 0) or 0)
                total_raised += amount
            except (ValueError, TypeError):
                pass

        return {
            "investor_count": len(investors),
            "investors": investors,
            "total_raised_usd": total_raised,
            "has_ai_focused_investor": any(inv.get("ai_focus_vc") for inv in investors),
            "funding_rounds": list(set(inv.get("round_type") for inv in investors if inv.get("round_type"))),
        }

    def build_all_profiles(self) -> List[SignalProfile]:
        """
        Build SignalProfiles for all entities in the store.

        Returns:
            List of SignalProfile objects
        """
        # Get all entities
        entities = list(self._entity_cache.values())

        # Get all scores
        all_scores = []
        for entity in entities:
            scores = self.store.get_scores_for_entity(entity.id)
            all_scores.extend(scores)

        # Build profiles
        profiles = self.aggregator.build_profiles_batch(entities, all_scores)

        # Save profiles to store
        for profile in profiles:
            self.store.save_profile(profile)

        print(f"Built {len(profiles)} signal profiles")
        return profiles

    def _get_or_create_entity(
        self,
        name: str,
        entity_type: EntityType,
        source_category: Optional[SignalCategory] = None,
        description: Optional[str] = None,
        website: Optional[str] = None,
    ) -> Entity:
        """
        Get existing entity or create new one.

        Uses canonical_id for deduplication.
        """
        canonical_id = normalize_entity_id(name)

        if canonical_id in self._entity_cache:
            return self._entity_cache[canonical_id]

        # Detect entity type if not provided
        if entity_type is None:
            entity_type = detect_entity_type(name, source_category)

        entity = Entity(
            canonical_id=canonical_id,
            name=name,
            entity_type=entity_type,
            description=description,
            website=website,
        )

        # Save to store and cache
        self.store.upsert_entity(entity)
        self._entity_cache[canonical_id] = entity

        return entity

    def get_summary(self) -> Dict[str, Any]:
        """Get summary of integrated data."""
        entities = list(self._entity_cache.values())

        by_type = defaultdict(int)
        for entity in entities:
            by_type[entity.entity_type.value] += 1

        return {
            "total_entities": len(entities),
            "by_entity_type": dict(by_type),
            "database_path": str(self.db_path),
        }


def integrate_all_data(
    data_dir: Optional[Path] = None,
    db_path: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Convenience function to run full data integration.

    Args:
        data_dir: Base data directory
        db_path: Database path

    Returns:
        Integration results summary
    """
    integrator = SignalIntegrator(data_dir=data_dir, db_path=db_path)
    results = integrator.load_all_sources()
    results["summary"] = integrator.get_summary()
    return results


if __name__ == "__main__":
    print("=" * 60)
    print("SIGNAL DATA INTEGRATION")
    print("=" * 60)
    print()

    results = integrate_all_data()

    print()
    print("=" * 60)
    print("INTEGRATION SUMMARY")
    print("=" * 60)
    print(f"Total entities: {results['summary']['total_entities']}")
    print(f"By type: {results['summary']['by_entity_type']}")
    print()
    print(f"Entities created: {results['entities_created']}")
    print(f"Observations: {results['observations_created']}")
    print(f"Scores: {results['scores_created']}")
    print(f"Profiles: {results['profiles_created']}")
    print()
    print(f"Database: {results['summary']['database_path']}")
