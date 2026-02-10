"""
Vertical Dynamic Scorer

Computes vertical scores by aggregating signals from tagged entities.
Replaces static heuristics with measured data:

- tech_momentum_score: From GitHub stars velocity, HF downloads, arXiv papers
- hype_score: From news volume, social mentions, Google Trends
- investment_score: From funding rounds, SEC filings, hiring trends
- maturity: From lifecycle state distribution of entities
- hype_phase: Derived from tech/hype divergence patterns

This creates Bloomberg-quality signal aggregation at the vertical level.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict
import sqlite3
import statistics

from .vertical_tagger import get_vertical_tagger, VerticalTagger


class VerticalScorer:
    """
    Computes dynamic vertical scores from entity-level signals.
    
    Usage:
        scorer = VerticalScorer()
        profiles = scorer.compute_all_profiles()
    """
    
    def __init__(
        self,
        signals_db_path: Optional[str] = None,
        trend_db_path: Optional[str] = None,
        buckets_db_path: Optional[str] = None,
    ):
        """
        Initialize scorer with database connections.
        
        Args:
            signals_db_path: Path to signals.db (entity signals)
            trend_db_path: Path to trend_radar.db (bucket data)
            buckets_db_path: Path to bucket profiles JSON
        """
        base_path = Path(__file__).parent.parent
        
        self.signals_db = signals_db_path or str(base_path / "data" / "signals.db")
        self.trend_db = trend_db_path or str(base_path / ".worktrees" / "trend-radar" / "data" / "trend_radar.db")
        # Try multiple locations for bucket profiles
        cache_path = base_path / "data" / "cache" / "bucket_profiles.json"
        if not cache_path.exists():
            # Try trend_aggregate location
            cache_path = base_path / "data" / "cache" / "trend_aggregate" / "bucket_profiles.json"
        self.buckets_cache = buckets_db_path or str(cache_path)
        
        self.tagger = get_vertical_tagger()
        
        # Signal weights for aggregation
        self.tech_weights = {
            "github_stars_velocity": 0.25,
            "github_forks_velocity": 0.10,
            "hf_downloads_velocity": 0.25,
            "arxiv_papers": 0.15,
            "pypi_downloads": 0.10,
            "job_postings": 0.15,
        }
        
        self.hype_weights = {
            "news_volume": 0.30,
            "twitter_mentions": 0.20,
            "google_trends": 0.25,
            "reddit_mentions": 0.15,
            "producthunt_score": 0.10,
        }
        
        self.investment_weights = {
            "funding_amount": 0.35,
            "deal_count": 0.25,
            "sec_mentions": 0.15,
            "hiring_velocity": 0.15,
            "patent_filings": 0.10,
        }
    
    def _get_signals_connection(self) -> Optional[sqlite3.Connection]:
        """Get connection to signals database."""
        if not Path(self.signals_db).exists():
            return None
        conn = sqlite3.connect(self.signals_db)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _get_trend_connection(self) -> Optional[sqlite3.Connection]:
        """Get connection to trend radar database."""
        if not Path(self.trend_db).exists():
            return None
        conn = sqlite3.connect(self.trend_db)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _load_bucket_profiles(self) -> Dict[str, Any]:
        """Load bucket profiles from cache or API."""
        # Try to load from cache
        cache_path = Path(self.buckets_cache)
        if cache_path.exists():
            with open(cache_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        
        # Fallback: try to load from data dir
        alt_path = Path(__file__).parent.parent / "data" / "bucket_profiles.json"
        if alt_path.exists():
            with open(alt_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        
        return {}
    
    def get_entity_signals(
        self,
        entity_name: str,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Get aggregated signals for an entity.
        
        Returns dict with tech_score, hype_score, investment_score, etc.
        """
        conn = self._get_signals_connection()
        if not conn:
            return {}
        
        try:
            cursor = conn.cursor()
            cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
            
            # Query signal scores for this entity
            cursor.execute("""
                SELECT category, AVG(score) as avg_score, COUNT(*) as obs_count
                FROM signal_scores
                WHERE entity_id LIKE ? AND created_at >= ?
                GROUP BY category
            """, (f"%{entity_name}%", cutoff))
            
            rows = cursor.fetchall()
            
            signals = {
                "technical": 50.0,
                "company": 50.0,
                "financial": 50.0,
                "product": 50.0,
                "media": 50.0,
            }
            
            for row in rows:
                category = row["category"]
                if category in signals:
                    signals[category] = row["avg_score"]
            
            return signals
            
        finally:
            conn.close()
    
    def get_bucket_signals(self, bucket_id: str) -> Dict[str, float]:
        """
        Get signals from a bucket profile.
        
        Maps bucket scores to vertical-relevant signals.
        """
        profiles = self._load_bucket_profiles()
        
        for profile in profiles.get("profiles", []):
            if profile.get("bucket_id") == bucket_id:
                return {
                    "tms": profile.get("tms", 50.0),
                    "ccs": profile.get("ccs", 50.0),
                    "nas": profile.get("nas", 50.0),
                    "heat_score": profile.get("heat_score", 50.0),
                    "entity_count": profile.get("entity_count", 0),
                    "github_repos": profile.get("github_repos", 0),
                    "hf_models": profile.get("hf_models", 0),
                    "article_count": profile.get("article_count", 0),
                }
        
        return {}
    
    def compute_vertical_profile(
        self,
        vertical_id: str,
    ) -> Dict[str, Any]:
        """
        Compute dynamic profile for a vertical by aggregating:
        1. Signals from tagged companies
        2. Signals from related buckets
        3. News/funding activity
        
        Returns:
            Vertical profile with computed scores
        """
        vertical = self.tagger.verticals.get(vertical_id)
        if not vertical:
            return {}
        
        # Collect signals from companies (only include if they have real data, not defaults)
        company_signals = []
        companies_with_data = 0
        for company in vertical.companies:
            signals = self.get_entity_signals(company)
            if signals:
                # Check if any signal is non-default (not 50.0)
                has_real_data = any(
                    v != 50.0 for v in signals.values() if isinstance(v, (int, float))
                )
                if has_real_data:
                    company_signals.append(signals)
                    companies_with_data += 1
        
        # Collect signals from related buckets (these are our primary signal source)
        bucket_signals = []
        for bucket_id in vertical.related_buckets:
            signals = self.get_bucket_signals(bucket_id)
            if signals:
                bucket_signals.append(signals)
        
        # Weighting strategy:
        # - If we have bucket signals, weight them heavily (they have real data)
        # - Only mix in company signals if they have non-default values
        # - Bucket signals get 3x weight to avoid dilution by empty company data
        
        # Aggregate tech momentum score (filter None values)
        tech_scores = []
        for signals in company_signals:
            val = signals.get("technical")
            if val is not None and val != 50.0:
                tech_scores.append(val)
        for signals in bucket_signals:
            val = signals.get("tms")
            if val is not None:
                # Weight bucket signals 3x
                tech_scores.extend([val, val, val])
        
        tech_momentum = statistics.mean(tech_scores) if tech_scores else 50.0
        
        # Aggregate hype score (filter None values)
        hype_scores = []
        for signals in company_signals:
            val = signals.get("media")
            if val is not None and val != 50.0:
                hype_scores.append(val)
        for signals in bucket_signals:
            val = signals.get("nas")
            if val is not None:
                # Weight bucket signals 3x
                hype_scores.extend([val, val, val])
        
        hype_score = statistics.mean(hype_scores) if hype_scores else 50.0
        
        # Aggregate investment score (filter None values)
        investment_scores = []
        for signals in company_signals:
            val = signals.get("financial")
            if val is not None and val != 50.0:
                investment_scores.append(val)
        for signals in bucket_signals:
            val = signals.get("ccs")
            if val is not None:
                # Weight bucket signals 3x
                investment_scores.extend([val, val, val])
        
        investment_score = statistics.mean(investment_scores) if investment_scores else 50.0
        
        # Compute derived metrics
        maturity = self._compute_maturity(tech_momentum, investment_score)
        hype_phase = self._compute_hype_phase(tech_momentum, hype_score, investment_score)
        divergence = self._compute_divergence(tech_momentum, hype_score)
        
        # Aggregate entity counts
        total_entities = len(vertical.companies)
        for signals in bucket_signals:
            total_entities += signals.get("entity_count", 0)
        
        return {
            "vertical_id": vertical_id,
            "name": vertical.name,
            "tech_momentum_score": round(tech_momentum, 1),
            "hype_score": round(hype_score, 1),
            "investment_score": round(investment_score, 1),
            "maturity": round(maturity, 2),
            "hype_phase": hype_phase,
            "divergence_signal": divergence,
            "companies": vertical.companies[:6],  # Top 6 for display
            "related_buckets": vertical.related_buckets,
            "entity_count": total_entities,
            "data_sources": {
                "company_count": len(company_signals),
                "bucket_count": len(bucket_signals),
            },
            "computed_at": datetime.utcnow().isoformat(),
        }
    
    def _compute_maturity(self, tech_score: float, investment_score: float) -> float:
        """
        Compute maturity from tech + investment scores.
        
        High tech + high investment = mature (0.7-1.0)
        High tech + low investment = emerging (0.3-0.5)
        Low tech + high investment = speculative (0.4-0.6)
        Low tech + low investment = nascent (0.1-0.3)
        """
        # Normalize to 0-1
        tech_norm = tech_score / 100.0
        inv_norm = investment_score / 100.0
        
        # Weighted combination favoring tech
        maturity = 0.6 * tech_norm + 0.4 * inv_norm
        
        return maturity
    
    def _compute_hype_phase(
        self,
        tech_score: float,
        hype_score: float,
        investment_score: float
    ) -> str:
        """
        Compute Gartner hype cycle phase from signal patterns.
        
        innovation_trigger: low tech, low hype, some investment
        peak_expectations: medium tech, very high hype
        trough_disillusionment: medium tech, low hype, declining investment
        slope_enlightenment: high tech, moderate hype, steady investment
        plateau_productivity: high tech, low hype, strong investment
        """
        # Thresholds
        if hype_score > 80 and tech_score < 50:
            return "peak_expectations"
        elif tech_score > 70 and hype_score < 40 and investment_score > 60:
            return "plateau_productivity"
        elif tech_score > 60 and hype_score >= 40 and hype_score <= 70:
            return "slope_enlightenment"
        elif tech_score < 40 and hype_score < 40:
            return "innovation_trigger"
        elif tech_score >= 40 and tech_score <= 60 and hype_score < 40:
            return "trough_disillusionment"
        elif tech_score >= 50 and investment_score > 60:
            return "establishing"
        else:
            return "validating"
    
    def _compute_divergence(self, tech_score: float, hype_score: float) -> Dict[str, Any]:
        """
        Compute divergence signal between tech and hype.
        
        High tech + low hype = alpha opportunity
        Low tech + high hype = bubble warning
        """
        divergence = tech_score - hype_score
        
        if divergence > 25:
            return {
                "type": "alpha_opportunity",
                "magnitude": divergence,
                "description": f"Undervalued: strong tech ({tech_score:.0f}), low hype ({hype_score:.0f})"
            }
        elif divergence < -25:
            return {
                "type": "bubble_warning",
                "magnitude": abs(divergence),
                "description": f"Potential bubble: weak tech ({tech_score:.0f}), high hype ({hype_score:.0f})"
            }
        else:
            return {
                "type": "balanced",
                "magnitude": abs(divergence),
                "description": "Tech and hype aligned"
            }
    
    def compute_all_profiles(self) -> Dict[str, Any]:
        """
        Compute profiles for all verticals.
        
        Returns:
            Dict with 'verticals' list and metadata
        """
        profiles = []
        
        for vertical_id in self.tagger.verticals.keys():
            profile = self.compute_vertical_profile(vertical_id)
            if profile:
                profiles.append(profile)
        
        # Sort by heat score (tech + hype + investment)
        profiles.sort(
            key=lambda p: (
                p.get("tech_momentum_score", 0) + 
                p.get("hype_score", 0) + 
                p.get("investment_score", 0)
            ) / 3,
            reverse=True
        )
        
        # Compute summary stats
        summary = self._compute_summary(profiles)
        
        return {
            "computed_at": datetime.utcnow().isoformat(),
            "vertical_count": len(profiles),
            "summary": summary,
            "verticals": profiles,
        }
    
    def _compute_summary(self, profiles: List[Dict]) -> Dict[str, Any]:
        """Compute summary statistics across all verticals."""
        by_phase = defaultdict(int)
        by_divergence = defaultdict(int)
        
        for p in profiles:
            phase = p.get("hype_phase", "unknown")
            by_phase[phase] += 1
            
            div_type = p.get("divergence_signal", {}).get("type", "balanced")
            by_divergence[div_type] += 1
        
        return {
            "by_phase": dict(by_phase),
            "by_divergence": dict(by_divergence),
            "total_entities": sum(p.get("entity_count", 0) for p in profiles),
        }
    
    def compute_quadrant_data(self, profiles: List[Dict]) -> List[Dict]:
        """
        Compute 2x2 quadrant positions for verticals.
        
        X-axis: Tech Momentum (0-100)
        Y-axis: Hype Score (0-100)
        
        Quadrants:
        - hot: high tech + high hype (>50, >50)
        - hyped: low tech + high hype (<50, >50)
        - mature: high tech + low hype (>50, <50)
        - emerging: low tech + low hype (<50, <50)
        """
        quadrant_data = []
        
        for p in profiles:
            tech = p.get("tech_momentum_score", 50)
            hype = p.get("hype_score", 50)
            
            if tech > 50 and hype > 50:
                quadrant = "hot"
            elif tech <= 50 and hype > 50:
                quadrant = "hyped"
            elif tech > 50 and hype <= 50:
                quadrant = "mature"
            else:
                quadrant = "emerging"
            
            quadrant_data.append({
                "id": p["vertical_id"],
                "name": p["name"],
                "x": tech,
                "y": hype,
                "size": min(p.get("entity_count", 10), 30),
                "phase": p.get("hype_phase", "unknown"),
                "quadrant": quadrant,
            })
        
        return quadrant_data
    
    def compute_hype_cycle_data(self, profiles: List[Dict]) -> List[Dict]:
        """
        Compute Gartner hype cycle positions for verticals.
        
        Maps phase to X position on curve, tech score to Y jitter.
        """
        phase_x_positions = {
            "innovation_trigger": 10,
            "peak_expectations": 30,
            "trough_disillusionment": 50,
            "validating": 40,
            "slope_enlightenment": 70,
            "establishing": 65,
            "plateau_productivity": 90,
        }
        
        hype_cycle_data = []
        
        for p in profiles:
            phase = p.get("hype_phase", "validating")
            base_x = phase_x_positions.get(phase, 50)
            
            # Add some jitter based on maturity
            maturity = p.get("maturity", 0.5)
            x = base_x + (maturity - 0.5) * 10
            
            # Y from hype cycle curve formula
            y = (
                30 +
                60 * (2.718 ** (-((x - 30) ** 2) / 200)) -
                20 * (2.718 ** (-((x - 50) ** 2) / 100)) +
                30 * (1 / (1 + 2.718 ** (-(x - 70) / 10)))
            )
            
            hype_cycle_data.append({
                "id": p["vertical_id"],
                "name": p["name"],
                "x": round(x, 0),
                "y": round(y, 1),
                "phase": phase,
                "maturity": maturity,
                "companies": p.get("companies", [])[:5],
            })
        
        return hype_cycle_data
    
    def compute_profiles_with_momentum(self, days: int = 7) -> Dict[str, Any]:
        """
        Compute profiles with momentum data from history.
        
        Args:
            days: Number of days for momentum calculation
        
        Returns:
            Dict with profiles including momentum_7d and momentum_30d
        """
        # Get base profiles
        result = self.compute_all_profiles()
        profiles = result.get("verticals", [])
        
        # Try to add momentum from history
        try:
            from utils.vertical_history import get_vertical_history
            history = get_vertical_history()
            
            for profile in profiles:
                vid = profile["vertical_id"]
                
                # 7-day momentum
                mom_7d = history.get_momentum(vid, days=7, metric="tech_momentum_score")
                if mom_7d:
                    profile["tech_momentum_7d"] = mom_7d["change"]
                    profile["tech_momentum_7d_pct"] = mom_7d["percent_change"]
                
                # 30-day momentum
                mom_30d = history.get_momentum(vid, days=30, metric="tech_momentum_score")
                if mom_30d:
                    profile["tech_momentum_30d"] = mom_30d["change"]
                    profile["tech_momentum_30d_pct"] = mom_30d["percent_change"]
                
                # Hype momentum
                hype_mom = history.get_momentum(vid, days=7, metric="hype_score")
                if hype_mom:
                    profile["hype_momentum_7d"] = hype_mom["change"]
                
        except ImportError:
            pass  # History module not available
        
        result["verticals"] = profiles
        return result


# Singleton instance
_scorer: Optional[VerticalScorer] = None


def get_vertical_scorer() -> VerticalScorer:
    """Get singleton VerticalScorer instance."""
    global _scorer
    if _scorer is None:
        _scorer = VerticalScorer()
    return _scorer


def compute_vertical_profiles() -> Dict[str, Any]:
    """Convenience function to compute all vertical profiles."""
    return get_vertical_scorer().compute_all_profiles()
