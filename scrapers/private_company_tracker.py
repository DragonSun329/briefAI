"""
Private Company Tracker for briefAI

Tracks private AI companies through alternative signals:
- Funding rounds (Crunchbase, PitchBook)
- GitHub activity (stars, commits, contributors)
- HuggingFace model downloads
- Job postings (LinkedIn, Greenhouse)
- Product launches and partnerships
- App store rankings
- arXiv paper publications
"""

import json
import os
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path
import asyncio
import aiohttp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
DATA_DIR = Path(__file__).parent.parent / "data"
CONFIG_DIR = Path(__file__).parent.parent / "config"


@dataclass
class PrivateCompanySignals:
    """Signals for tracking private company health and momentum."""
    
    entity_id: str
    entity_name: str
    
    # Funding signals
    last_funding_date: Optional[str] = None
    last_funding_amount: Optional[float] = None
    last_funding_round: Optional[str] = None
    total_funding: Optional[float] = None
    valuation_estimate: Optional[float] = None
    investors: list = field(default_factory=list)
    
    # GitHub signals
    github_stars: Optional[int] = None
    github_stars_30d_delta: Optional[int] = None
    github_forks: Optional[int] = None
    github_contributors: Optional[int] = None
    github_commits_30d: Optional[int] = None
    
    # HuggingFace signals
    hf_model_downloads_30d: Optional[int] = None
    hf_total_models: Optional[int] = None
    hf_trending_rank: Optional[int] = None
    
    # Employment signals
    employee_count_estimate: Optional[int] = None
    open_job_postings: Optional[int] = None
    job_growth_30d: Optional[int] = None
    key_hires: list = field(default_factory=list)
    key_departures: list = field(default_factory=list)
    
    # Product signals
    recent_product_launches: list = field(default_factory=list)
    api_traffic_trend: Optional[str] = None  # "up", "down", "stable"
    app_store_rank: Optional[int] = None
    
    # Partnership signals
    recent_partnerships: list = field(default_factory=list)
    enterprise_customers: list = field(default_factory=list)
    
    # Sentiment signals
    news_sentiment_7d: Optional[float] = None  # -1 to 1
    social_mentions_7d: Optional[int] = None
    arxiv_papers_30d: Optional[int] = None
    
    # Computed scores
    momentum_score: Optional[float] = None  # 0-100
    health_score: Optional[float] = None  # 0-100
    
    last_updated: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    
    def compute_momentum_score(self) -> float:
        """Compute overall momentum score from available signals."""
        score = 50.0  # Base score
        
        # GitHub momentum
        if self.github_stars_30d_delta:
            if self.github_stars_30d_delta > 10000:
                score += 15
            elif self.github_stars_30d_delta > 1000:
                score += 10
            elif self.github_stars_30d_delta > 100:
                score += 5
        
        # HuggingFace momentum
        if self.hf_model_downloads_30d:
            if self.hf_model_downloads_30d > 10_000_000:
                score += 15
            elif self.hf_model_downloads_30d > 1_000_000:
                score += 10
            elif self.hf_model_downloads_30d > 100_000:
                score += 5
        
        # Funding momentum
        if self.last_funding_date:
            days_since_funding = (datetime.utcnow() - datetime.fromisoformat(self.last_funding_date.replace('Z', '+00:00').replace('+00:00', ''))).days
            if days_since_funding < 90:
                score += 10
            elif days_since_funding < 180:
                score += 5
        
        # Job growth
        if self.job_growth_30d and self.job_growth_30d > 0:
            score += min(10, self.job_growth_30d // 10)
        
        # News sentiment
        if self.news_sentiment_7d:
            score += self.news_sentiment_7d * 10
        
        self.momentum_score = max(0, min(100, score))
        return self.momentum_score
    
    def compute_health_score(self) -> float:
        """Compute overall health score."""
        score = 50.0
        
        # Runway (funding / burn rate proxy)
        if self.total_funding and self.total_funding > 500_000_000:
            score += 15
        elif self.total_funding and self.total_funding > 100_000_000:
            score += 10
        
        # Team stability
        if self.key_departures:
            score -= len(self.key_departures) * 5
        if self.key_hires:
            score += min(10, len(self.key_hires) * 2)
        
        # Enterprise traction
        if self.enterprise_customers:
            score += min(15, len(self.enterprise_customers) * 3)
        
        # Product activity
        if self.recent_product_launches:
            score += min(10, len(self.recent_product_launches) * 3)
        
        self.health_score = max(0, min(100, score))
        return self.health_score


class GitHubTracker:
    """Track GitHub activity for AI companies."""
    
    def __init__(self, token: Optional[str] = None):
        self.token = token or os.environ.get("GITHUB_TOKEN")
        self.headers = {"Authorization": f"token {self.token}"} if self.token else {}
        
    async def get_org_stats(self, org_name: str) -> dict:
        """Get aggregated stats for a GitHub organization."""
        async with aiohttp.ClientSession() as session:
            # Get org repos
            url = f"https://api.github.com/orgs/{org_name}/repos?per_page=100"
            async with session.get(url, headers=self.headers) as resp:
                if resp.status != 200:
                    logger.warning(f"GitHub API error for {org_name}: {resp.status}")
                    return {}
                repos = await resp.json()
            
            total_stars = sum(r.get("stargazers_count", 0) for r in repos)
            total_forks = sum(r.get("forks_count", 0) for r in repos)
            
            return {
                "total_stars": total_stars,
                "total_forks": total_forks,
                "repo_count": len(repos),
                "top_repos": sorted(repos, key=lambda x: x.get("stargazers_count", 0), reverse=True)[:5]
            }


class HuggingFaceTracker:
    """Track HuggingFace activity for AI companies."""
    
    async def get_namespace_stats(self, namespace: str) -> dict:
        """Get stats for a HuggingFace namespace (org or user)."""
        async with aiohttp.ClientSession() as session:
            url = f"https://huggingface.co/api/models?author={namespace}&limit=100"
            async with session.get(url) as resp:
                if resp.status != 200:
                    logger.warning(f"HuggingFace API error for {namespace}: {resp.status}")
                    return {}
                models = await resp.json()
            
            total_downloads = sum(m.get("downloads", 0) for m in models)
            
            return {
                "total_models": len(models),
                "total_downloads": total_downloads,
                "top_models": sorted(models, key=lambda x: x.get("downloads", 0), reverse=True)[:5]
            }


class PrivateCompanyAggregator:
    """Aggregate signals for private AI companies."""
    
    def __init__(self):
        self.github = GitHubTracker()
        self.hf = HuggingFaceTracker()
        self._load_entity_registry()
        
    def _load_entity_registry(self):
        """Load entity registry for company metadata."""
        registry_path = CONFIG_DIR / "entity_registry.json"
        with open(registry_path) as f:
            self.registry = json.load(f)
    
    async def collect_signals(self, entity_id: str) -> Optional[PrivateCompanySignals]:
        """Collect all available signals for an entity."""
        if entity_id not in self.registry or entity_id == "_meta":
            logger.warning(f"Unknown entity: {entity_id}")
            return None
        
        entity = self.registry[entity_id]
        signals = PrivateCompanySignals(
            entity_id=entity_id,
            entity_name=entity.get("canonical_name", entity_id)
        )
        
        # GitHub signals
        github_orgs = entity.get("github_orgs", [])
        if github_orgs:
            for org in github_orgs[:1]:  # Primary org only
                try:
                    stats = await self.github.get_org_stats(org)
                    signals.github_stars = stats.get("total_stars", 0)
                    signals.github_forks = stats.get("total_forks", 0)
                except Exception as e:
                    logger.error(f"GitHub error for {org}: {e}")
        
        # HuggingFace signals
        hf_namespaces = entity.get("hf_namespaces", [])
        if hf_namespaces:
            for ns in hf_namespaces[:1]:
                try:
                    stats = await self.hf.get_namespace_stats(ns)
                    signals.hf_total_models = stats.get("total_models", 0)
                    signals.hf_model_downloads_30d = stats.get("total_downloads", 0)
                except Exception as e:
                    logger.error(f"HuggingFace error for {ns}: {e}")
        
        # Compute scores
        signals.compute_momentum_score()
        signals.compute_health_score()
        
        return signals
    
    async def collect_all_private_companies(self) -> dict:
        """Collect signals for all private companies in registry."""
        # Load asset mapping to identify private companies
        asset_path = DATA_DIR / "asset_mapping.json"
        with open(asset_path) as f:
            assets = json.load(f)
        
        private_entities = [
            eid for eid, data in assets.get("entities", {}).items()
            if data.get("status") == "private"
        ]
        
        results = {}
        for entity_id in private_entities:
            signals = await self.collect_signals(entity_id)
            if signals:
                results[entity_id] = {
                    "entity_name": signals.entity_name,
                    "github_stars": signals.github_stars,
                    "github_forks": signals.github_forks,
                    "hf_models": signals.hf_total_models,
                    "hf_downloads_30d": signals.hf_model_downloads_30d,
                    "momentum_score": signals.momentum_score,
                    "health_score": signals.health_score,
                    "last_updated": signals.last_updated
                }
            # Rate limiting
            await asyncio.sleep(0.5)
        
        return results
    
    def save_signals(self, signals: dict, filename: str = "private_company_signals.json"):
        """Save collected signals to file."""
        output_path = DATA_DIR / filename
        with open(output_path, 'w') as f:
            json.dump({
                "generated_at": datetime.utcnow().isoformat(),
                "entity_count": len(signals),
                "signals": signals
            }, f, indent=2)
        logger.info(f"Saved signals to {output_path}")


async def main():
    """Run private company tracking."""
    aggregator = PrivateCompanyAggregator()
    
    # Collect signals for all private companies
    logger.info("Collecting signals for private AI companies...")
    signals = await aggregator.collect_all_private_companies()
    
    # Save results
    aggregator.save_signals(signals)
    
    # Print summary
    print("\n=== Private Company Tracking Summary ===")
    print(f"Companies tracked: {len(signals)}")
    
    # Top by momentum
    by_momentum = sorted(signals.items(), key=lambda x: x[1].get("momentum_score", 0), reverse=True)
    print("\nTop 10 by Momentum Score:")
    for entity_id, data in by_momentum[:10]:
        print(f"  {data['entity_name']}: {data.get('momentum_score', 0):.1f}")
    
    # Top by GitHub stars
    by_stars = sorted(signals.items(), key=lambda x: x[1].get("github_stars") or 0, reverse=True)
    print("\nTop 10 by GitHub Stars:")
    for entity_id, data in by_stars[:10]:
        stars = data.get("github_stars", 0) or 0
        print(f"  {data['entity_name']}: {stars:,}")


if __name__ == "__main__":
    asyncio.run(main())
