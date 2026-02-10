"""
Bucket-Level Velocity Scorers

Compute velocity-based scores for trend buckets using:
- VELOCITY (not totals) - week-over-week changes
- PERCENTILES (not raw scores) - normalized across all buckets

Four instruments:
1. TMS (Technical Momentum Score) - GitHub star velocity + HF download velocity
2. CCS (Capital Conviction Score) - Deal velocity + smart money presence
3. EIS (Enterprise Institutional Signal) - SEC mention velocity (offensive vs defensive)
4. NAS (Narrative/Attention Score) - News article velocity
"""

from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict
import math

from .bucket_models import (
    BucketObservation, BucketScore, BucketProfile,
    LifecycleState, compute_percentile, get_week_bounds,
    HypeCyclePhase, FiveTScore, ConfidenceInterval, DataCoverage, CoverageBadge
)
from .bucket_tagger import BucketTagger, BucketMatch

# Optional financial signals integration
try:
    from .financial_signals import get_bucket_financial_signals
    FINANCIAL_SIGNALS_AVAILABLE = True
except ImportError:
    FINANCIAL_SIGNALS_AVAILABLE = False

# Load configuration files
import json
from pathlib import Path


def _dedupe_entities(entities: List[str], max_count: int = 10) -> List[str]:
    """
    Deduplicate entity list, case-insensitive.
    Preserves original casing of first occurrence.
    """
    seen = set()
    result = []
    for entity in entities:
        if not entity:
            continue
        key = entity.lower().strip()
        if key not in seen:
            seen.add(key)
            result.append(entity)
        if len(result) >= max_count:
            break
    return result


def _load_config(config_name: str) -> Dict[str, Any]:
    """Load a configuration file from the config directory."""
    config_path = Path(__file__).parent.parent / "config" / config_name
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


# =============================================================================
# Source Credibility Weighter
# =============================================================================

class SourceCredibilityWeighter:
    """
    Applies source credibility weights to signal computations.

    Aligns with business analyst due diligence standards by weighting
    institutional sources higher than social media/blogs.
    """

    def __init__(self, config_path: str = "source_credibility.json"):
        self.config = _load_config(config_path)
        self._build_source_lookup()

    def _build_source_lookup(self):
        """Build a flat lookup dict from source name to weight."""
        self.source_weights = {}

        for tier_name, tier_data in self.config.get("tiers", {}).items():
            weight = tier_data.get("weight", 0.5)
            for source_category, sources in tier_data.get("sources", {}).items():
                for source in sources:
                    self.source_weights[source.lower()] = weight

        self.default_weight = self.config.get("default_weight", 0.5)

    def get_source_weight(self, source_name: str) -> float:
        """Get credibility weight for a source (0.4-1.0)."""
        if not source_name:
            return self.default_weight
        return self.source_weights.get(source_name.lower(), self.default_weight)

    def get_signal_weight(self, signal_name: str, source_name: str = None) -> float:
        """Get credibility weight for a signal source."""
        mappings = self.config.get("signal_source_mappings", {})
        signal_config = mappings.get(signal_name, {})

        if source_name:
            source_tier = signal_config.get("sources", {}).get(source_name.lower())
            if source_tier:
                tier_data = self.config.get("tiers", {}).get(source_tier, {})
                return tier_data.get("weight", self.default_weight)

        # Return default tier weight for this signal
        default_tier = signal_config.get("default_tier", "tier_3")
        tier_data = self.config.get("tiers", {}).get(default_tier, {})
        return tier_data.get("weight", self.default_weight)

    def weight_entities(
        self,
        entities: List[Dict[str, Any]],
        source_key: str = "source",
    ) -> List[Tuple[Dict[str, Any], float]]:
        """
        Return entities with their credibility weights.

        Higher-credibility sources contribute more to bucket scores.
        """
        weighted_entities = []
        for entity in entities:
            source = entity.get(source_key, "")
            weight = self.get_source_weight(source)
            weighted_entities.append((entity, weight))
        return weighted_entities

    def compute_weighted_velocity(
        self,
        velocities_by_source: Dict[str, float],
    ) -> Tuple[float, Dict[str, float]]:
        """
        Compute credibility-weighted velocity.

        Returns:
            (weighted_velocity, source_contributions)
        """
        total_weighted = 0.0
        total_weight = 0.0
        contributions = {}

        for source, velocity in velocities_by_source.items():
            weight = self.get_source_weight(source)
            weighted_value = velocity * weight
            total_weighted += weighted_value
            total_weight += weight
            contributions[source] = weighted_value

        if total_weight > 0:
            return total_weighted / total_weight, contributions
        return 0.0, contributions


# =============================================================================
# Investment Thesis (5T) Scorer
# =============================================================================

class FiveTScorer:
    """
    Computes 5T investment thesis scores for buckets.

    Uses existing data sources to estimate:
    - Team: Founder quality signals from news + Crunchbase
    - Technology: TMS components
    - Market: NAS + sizing proxies
    - Timing: Velocity vectors + lifecycle
    - Traction: CCS + EIS + adoption
    """

    def __init__(self, config_path: str = "five_t_scoring.json"):
        self.config = _load_config(config_path)
        self.default_score = self.config.get("output", {}).get("default_score", 50)

    def compute_team_score(
        self,
        companies: List[Dict[str, Any]],
        articles: List[Dict[str, Any]] = None,
    ) -> Tuple[float, float, List[str]]:
        """
        Compute Team score from company and news data.

        Returns:
            (score, confidence, evidence_list)
        """
        team_config = self.config.get("team", {})
        exec_keywords = team_config.get("exec_keywords", ["CEO", "founder"])
        key_hire_keywords = team_config.get("key_hire_keywords", ["hires", "joins"])
        rank_thresholds = team_config.get("rank_thresholds", {"excellent": 100, "good": 500})

        score = self.default_score
        evidence = []
        data_points = 0

        # Score from Crunchbase rank
        if companies:
            top_ranks = []
            for company in companies[:10]:  # Top 10 companies
                cb_rank = company.get("cb_rank", company.get("rank", 5000))
                if cb_rank and cb_rank < 5000:
                    top_ranks.append(cb_rank)
                    if cb_rank <= rank_thresholds.get("excellent", 100):
                        evidence.append(f"{company.get('name', 'Unknown')}: CB Rank {cb_rank} (excellent)")
                    elif cb_rank <= rank_thresholds.get("good", 500):
                        evidence.append(f"{company.get('name', 'Unknown')}: CB Rank {cb_rank} (good)")

            if top_ranks:
                # Higher score for better ranks (lower rank = better)
                avg_rank = sum(top_ranks) / len(top_ranks)
                if avg_rank <= 100:
                    score = 85 + (100 - avg_rank) / 10  # 85-95
                elif avg_rank <= 500:
                    score = 70 + (500 - avg_rank) / 30  # 70-85
                elif avg_rank <= 2000:
                    score = 50 + (2000 - avg_rank) / 100  # 50-70
                else:
                    score = 40

                data_points += len(top_ranks)

        # Score boost from exec mentions in articles
        if articles:
            exec_mentions = 0
            key_hire_mentions = 0

            for article in articles:
                content = (article.get("content", "") + article.get("title", "")).lower()
                for kw in exec_keywords:
                    if kw.lower() in content:
                        exec_mentions += 1
                        break
                for kw in key_hire_keywords:
                    if kw.lower() in content:
                        key_hire_mentions += 1
                        evidence.append(f"Key hire mention in: {article.get('title', '')[:50]}")
                        break

            # Boost score for exec coverage
            if exec_mentions > 5:
                score = min(100, score + 10)
            elif exec_mentions > 2:
                score = min(100, score + 5)

            data_points += exec_mentions + key_hire_mentions

        # Calculate confidence based on data availability
        confidence = min(1.0, 0.3 + data_points * 0.1)

        return min(100, max(0, score)), confidence, evidence[:5]

    def compute_technology_score(
        self,
        tms: Optional[float],
        github_repos: int = 0,
        hf_models: int = 0,
        star_velocity: float = 0,
    ) -> Tuple[float, float, List[str]]:
        """
        Compute Technology score from technical signals.

        Primary: TMS percentile
        Boosters: GitHub star velocity, model download growth
        """
        tech_config = self.config.get("technology", {})
        tms_weight = tech_config.get("tms_weight", 0.5)

        evidence = []
        score = self.default_score

        if tms is not None:
            score = tms * tms_weight + self.default_score * (1 - tms_weight)
            evidence.append(f"TMS: {tms:.0f}th percentile")

        # Boost for entity count
        entity_count = github_repos + hf_models
        if entity_count > 20:
            score = min(100, score + 10)
            evidence.append(f"{entity_count} repos/models")
        elif entity_count > 10:
            score = min(100, score + 5)
            evidence.append(f"{entity_count} repos/models")

        # Boost for star velocity
        if star_velocity > 1000:
            score = min(100, score + 10)
            evidence.append(f"High star velocity: {star_velocity:.0f}/week")
        elif star_velocity > 100:
            score = min(100, score + 5)
            evidence.append(f"Star velocity: {star_velocity:.0f}/week")

        # Confidence based on data availability
        confidence = 0.5
        if tms is not None:
            confidence += 0.3
        if entity_count > 0:
            confidence += 0.1
        if star_velocity > 0:
            confidence += 0.1

        return min(100, max(0, score)), min(1.0, confidence), evidence[:5]

    def compute_market_score(
        self,
        nas: Optional[float],
        article_count: int = 0,
        articles: List[Dict[str, Any]] = None,
    ) -> Tuple[float, float, List[str]]:
        """
        Compute Market score (TAM/SAM proxy).

        Uses NAS + keyword extraction for market sizing language.
        """
        market_config = self.config.get("market", {})
        nas_weight = market_config.get("nas_weight", 0.4)
        market_keywords = market_config.get("market_keywords", ["billion", "TAM"])

        evidence = []
        score = self.default_score

        if nas is not None:
            score = nas * nas_weight + self.default_score * (1 - nas_weight)
            evidence.append(f"NAS: {nas:.0f}th percentile")

        # Article volume boost
        if article_count > 50:
            score = min(100, score + 10)
            evidence.append(f"{article_count} articles (high coverage)")
        elif article_count > 20:
            score = min(100, score + 5)
            evidence.append(f"{article_count} articles")

        # Market keyword detection
        if articles:
            market_mentions = 0
            for article in articles[:20]:
                content = (article.get("content", "") + article.get("title", "")).lower()
                for kw in market_keywords:
                    if kw.lower() in content:
                        market_mentions += 1
                        if len(evidence) < 5:
                            evidence.append(f"TAM mention: '{kw}' found")
                        break

            if market_mentions > 5:
                score = min(100, score + 15)
            elif market_mentions > 2:
                score = min(100, score + 8)

        confidence = 0.5
        if nas is not None:
            confidence += 0.25
        if article_count > 0:
            confidence += 0.15
        if articles:
            confidence += 0.1

        return min(100, max(0, score)), min(1.0, confidence), evidence[:5]

    def compute_timing_score(
        self,
        lifecycle_state: LifecycleState,
        hype_cycle_phase: HypeCyclePhase,
        tms_delta_4w: Optional[float] = None,
        ccs_delta_4w: Optional[float] = None,
        velocity_accelerating: bool = False,
    ) -> Tuple[float, float, List[str]]:
        """
        Compute Timing score based on momentum.

        Best timing: Emerging/Validating + positive acceleration
        Worst timing: Peak expectations + decelerating
        """
        timing_config = self.config.get("timing", {})
        lifecycle_scores = timing_config.get("lifecycle_scores", {
            "emerging": 90, "validating": 80, "establishing": 60, "mainstream": 40
        })
        hype_modifiers = timing_config.get("hype_cycle_modifiers", {})
        velocity_bonus = timing_config.get("velocity_bonus", {})

        evidence = []

        # Base score from lifecycle
        base_score = lifecycle_scores.get(lifecycle_state.value, 50)
        evidence.append(f"Lifecycle: {lifecycle_state.value} ({base_score} base)")

        # Apply hype cycle modifier
        hype_modifier = hype_modifiers.get(hype_cycle_phase.value, 1.0)
        score = base_score * hype_modifier
        if hype_modifier != 1.0:
            evidence.append(f"Hype cycle: {hype_cycle_phase.value} ({hype_modifier}x)")

        # Velocity bonus
        if velocity_accelerating:
            bonus = velocity_bonus.get("accelerating", 10)
            score = min(100, score + bonus)
            evidence.append("Momentum accelerating (+10)")
        elif tms_delta_4w is not None and tms_delta_4w < -5:
            penalty = velocity_bonus.get("decelerating", -5)
            score = max(0, score + penalty)
            evidence.append("Momentum decelerating (-5)")

        # Rising CCS is good timing signal
        if ccs_delta_4w is not None and ccs_delta_4w > 10:
            score = min(100, score + 5)
            evidence.append(f"CCS rising: +{ccs_delta_4w:.0f}")

        confidence = 0.7  # Timing is inherently subjective
        if tms_delta_4w is not None or ccs_delta_4w is not None:
            confidence += 0.1

        return min(100, max(0, score)), min(1.0, confidence), evidence[:5]

    def compute_traction_score(
        self,
        ccs: Optional[float],
        eis_offensive: Optional[float],
        pms: Optional[float] = None,
        articles: List[Dict[str, Any]] = None,
    ) -> Tuple[float, float, List[str]]:
        """
        Compute Traction score from adoption signals.

        Revenue proxies: CCS (funding), EIS (enterprise adoption), PMS (public validation)
        """
        traction_config = self.config.get("traction", {})
        ccs_weight = traction_config.get("ccs_weight", 0.35)
        eis_weight = traction_config.get("eis_weight", 0.35)
        pms_weight = traction_config.get("pms_weight", 0.20)
        customer_keywords = traction_config.get("customer_keywords", ["customer", "enterprise"])

        evidence = []
        components = []
        total_weight = 0

        if ccs is not None:
            components.append(ccs * ccs_weight)
            total_weight += ccs_weight
            evidence.append(f"CCS: {ccs:.0f}th percentile")

        if eis_offensive is not None:
            components.append(eis_offensive * eis_weight)
            total_weight += eis_weight
            evidence.append(f"EIS: {eis_offensive:.0f}th percentile")

        if pms is not None:
            components.append(pms * pms_weight)
            total_weight += pms_weight
            evidence.append(f"PMS: {pms:.0f}th percentile")

        if total_weight > 0:
            score = sum(components) / total_weight
        else:
            score = self.default_score

        # Customer mention boost
        if articles:
            customer_mentions = 0
            for article in articles[:20]:
                content = (article.get("content", "") + article.get("title", "")).lower()
                for kw in customer_keywords:
                    if kw.lower() in content:
                        customer_mentions += 1
                        break

            if customer_mentions > 10:
                score = min(100, score + 10)
                evidence.append(f"{customer_mentions} customer mentions")
            elif customer_mentions > 5:
                score = min(100, score + 5)
                evidence.append(f"{customer_mentions} customer mentions")

        confidence = min(1.0, 0.3 + total_weight)

        return min(100, max(0, score)), confidence, evidence[:5]

    def compute_five_t(
        self,
        bucket_id: str,
        tms: Optional[float] = None,
        ccs: Optional[float] = None,
        nas: Optional[float] = None,
        eis_offensive: Optional[float] = None,
        pms: Optional[float] = None,
        lifecycle_state: LifecycleState = LifecycleState.EMERGING,
        hype_cycle_phase: HypeCyclePhase = HypeCyclePhase.UNKNOWN,
        companies: List[Dict[str, Any]] = None,
        articles: List[Dict[str, Any]] = None,
        github_repos: int = 0,
        hf_models: int = 0,
        star_velocity: float = 0,
        tms_delta_4w: Optional[float] = None,
        ccs_delta_4w: Optional[float] = None,
        velocity_accelerating: bool = False,
    ) -> FiveTScore:
        """
        Compute complete 5T score for a bucket.
        """
        # Compute each dimension
        team_score, team_conf, team_evidence = self.compute_team_score(
            companies or [], articles
        )

        tech_score, tech_conf, tech_evidence = self.compute_technology_score(
            tms, github_repos, hf_models, star_velocity
        )

        market_score, market_conf, market_evidence = self.compute_market_score(
            nas, len(articles) if articles else 0, articles
        )

        timing_score, timing_conf, timing_evidence = self.compute_timing_score(
            lifecycle_state, hype_cycle_phase, tms_delta_4w, ccs_delta_4w, velocity_accelerating
        )

        traction_score, traction_conf, traction_evidence = self.compute_traction_score(
            ccs, eis_offensive, pms, articles
        )

        return FiveTScore(
            team=team_score,
            technology=tech_score,
            market=market_score,
            timing=timing_score,
            traction=traction_score,
            team_confidence=team_conf,
            technology_confidence=tech_conf,
            market_confidence=market_conf,
            timing_confidence=timing_conf,
            traction_confidence=traction_conf,
            team_evidence=team_evidence,
            technology_evidence=tech_evidence,
            market_evidence=market_evidence,
            timing_evidence=timing_evidence,
            traction_evidence=traction_evidence,
        )


# =============================================================================
# Hype Cycle Detection
# =============================================================================

def determine_hype_cycle_phase(
    tms: Optional[float],
    ccs: Optional[float],
    nas: Optional[float],
    eis_offensive: Optional[float],
    tms_delta_4w: Optional[float] = None,
    ccs_delta_4w: Optional[float] = None,
    nas_delta_4w: Optional[float] = None,
    config: Dict[str, Any] = None,
) -> Tuple[HypeCyclePhase, float, str]:
    """
    Determine Gartner Hype Cycle phase from signal patterns.

    Returns:
        (phase, confidence, rationale)
    """
    if config is None:
        config = _load_config("trend_detection.json").get("hype_cycle", {})

    # Default to unknown if insufficient data
    if tms is None and ccs is None:
        return HypeCyclePhase.UNKNOWN, 0.3, "Insufficient signal data"

    # Get thresholds
    innovation = config.get("innovation_trigger", {})
    peak = config.get("peak_expectations", {})
    trough = config.get("trough_disillusionment", {})
    slope = config.get("slope_enlightenment", {})
    plateau = config.get("plateau_productivity", {})

    tms_val = tms or 50
    ccs_val = ccs or 50
    nas_val = nas or 50
    eis_val = eis_offensive or 50

    # Phase detection logic
    # 1. Innovation Trigger: High TMS, very low CCS, no EIS
    if (tms_val > innovation.get("tms_min", 80) and
        ccs_val < innovation.get("ccs_max", 20) and
        (eis_offensive is None or eis_val < innovation.get("eis_max", 10))):
        return (
            HypeCyclePhase.INNOVATION_TRIGGER,
            0.8,
            f"High TMS ({tms_val:.0f}), low CCS ({ccs_val:.0f}) - early technical adoption"
        )

    # 2. Peak of Inflated Expectations: High NAS, high CCS, TMS plateauing
    if (nas_val > peak.get("nas_min", 80) and
        ccs_val > peak.get("ccs_min", 70)):
        tms_delta = tms_delta_4w or 0
        if tms_delta <= peak.get("tms_delta_max", 0):
            return (
                HypeCyclePhase.PEAK_EXPECTATIONS,
                0.75,
                f"High hype (NAS={nas_val:.0f}), capital flooding (CCS={ccs_val:.0f}), tech plateauing"
            )

    # 3. Trough of Disillusionment: NAS and CCS declining
    nas_delta = nas_delta_4w or 0
    ccs_delta = ccs_delta_4w or 0
    if (nas_delta < trough.get("nas_delta_min", -20) or
        ccs_delta < trough.get("ccs_delta_min", -10)):
        return (
            HypeCyclePhase.TROUGH_DISILLUSIONMENT,
            0.7,
            f"Declining attention (NAS Δ={nas_delta:.0f}) and capital (CCS Δ={ccs_delta:.0f})"
        )

    # 4. Slope of Enlightenment: EIS rising, TMS recovering
    if eis_offensive is not None:
        eis_delta = 0  # Would need historical data
        tms_delta = tms_delta_4w or 0
        if (eis_val > 50 and tms_delta >= slope.get("tms_delta_min", 0)):
            return (
                HypeCyclePhase.SLOPE_ENLIGHTENMENT,
                0.7,
                f"Enterprise adoption (EIS={eis_val:.0f}), practical applications emerging"
            )

    # 5. Plateau of Productivity: All signals stable, EIS high
    all_stable = (
        abs(tms_delta_4w or 0) < plateau.get("stability_threshold", 10) and
        abs(ccs_delta_4w or 0) < plateau.get("stability_threshold", 10)
    )
    if all_stable and eis_val > plateau.get("eis_off_min", 60):
        return (
            HypeCyclePhase.PLATEAU_PRODUCTIVITY,
            0.75,
            f"Stable signals, mainstream adoption (EIS={eis_val:.0f})"
        )

    # Default: infer from signal patterns with relaxed thresholds
    # These are more permissive fallbacks based on typical patterns

    # Innovation Trigger: Strong technical signal, weak capital
    if tms_val > 70 and ccs_val < 50:
        return HypeCyclePhase.INNOVATION_TRIGGER, 0.6, f"High tech momentum (TMS={tms_val:.0f}), limited capital (CCS={ccs_val:.0f})"

    # Peak Expectations: High hype (NAS) + high capital, regardless of TMS
    if nas_val > 75 and ccs_val > 70:
        return HypeCyclePhase.PEAK_EXPECTATIONS, 0.65, f"High attention (NAS={nas_val:.0f}) + capital flooding (CCS={ccs_val:.0f})"

    # Also Peak if both TMS and CCS are high (validating becomes peak)
    if tms_val > 70 and ccs_val > 70:
        return HypeCyclePhase.PEAK_EXPECTATIONS, 0.6, f"Strong signals across tech (TMS={tms_val:.0f}) and capital (CCS={ccs_val:.0f})"

    # Slope of Enlightenment: Moderate TMS + moderate-high CCS + EIS present
    if tms_val > 40 and ccs_val > 50 and eis_val > 40:
        return HypeCyclePhase.SLOPE_ENLIGHTENMENT, 0.55, f"Balanced adoption: TMS={tms_val:.0f}, CCS={ccs_val:.0f}, EIS={eis_val:.0f}"

    # Plateau: High CCS, moderate TMS (mature market)
    if ccs_val > 60 and tms_val < 50:
        return HypeCyclePhase.PLATEAU_PRODUCTIVITY, 0.55, f"Mature market: high capital (CCS={ccs_val:.0f}), stabilizing tech (TMS={tms_val:.0f})"

    # Trough: Low everything or declining
    if tms_val < 30 and ccs_val < 40 and nas_val < 40:
        return HypeCyclePhase.TROUGH_DISILLUSIONMENT, 0.5, f"Low signals across board: TMS={tms_val:.0f}, CCS={ccs_val:.0f}, NAS={nas_val:.0f}"

    # If we have good TMS but moderate CCS, still early stage
    if tms_val > 60 and ccs_val > 30 and ccs_val < 70:
        return HypeCyclePhase.INNOVATION_TRIGGER, 0.5, f"Technical momentum (TMS={tms_val:.0f}) ahead of capital (CCS={ccs_val:.0f})"

    # Fallback based on dominant signal
    if nas_val > 70:
        return HypeCyclePhase.PEAK_EXPECTATIONS, 0.45, f"High narrative attention (NAS={nas_val:.0f}) suggests peak hype"
    if ccs_val > 60:
        return HypeCyclePhase.SLOPE_ENLIGHTENMENT, 0.45, f"Capital conviction (CCS={ccs_val:.0f}) suggests maturing"
    if tms_val > 50:
        return HypeCyclePhase.INNOVATION_TRIGGER, 0.45, f"Technical momentum (TMS={tms_val:.0f}) suggests early stage"

    return HypeCyclePhase.UNKNOWN, 0.3, f"Weak signals: TMS={tms_val:.0f}, CCS={ccs_val:.0f}, NAS={nas_val:.0f}"


# =============================================================================
# Confidence Interval Computation
# =============================================================================

def compute_confidence_interval(
    observed_value: float,
    entity_count: int,
    expected_baseline: int = 10,
    source_values: List[float] = None,
    historical_values: List[float] = None,
    z_score: float = 1.96,
) -> ConfidenceInterval:
    """
    Compute confidence interval for a percentile score.

    Uses three variance components:
    1. Coverage: entity_count / expected_baseline
    2. Source: std(source_values) if multiple sources
    3. Temporal: std(historical_values) / sqrt(weeks)
    """
    import numpy as np

    # Coverage variance (higher variance with fewer entities)
    coverage_ratio = min(entity_count / expected_baseline, 1.0) if expected_baseline > 0 else 0.5
    coverage_variance = (1 - coverage_ratio) * 15  # Max 15 points variance

    # Source variance
    if source_values and len(source_values) >= 2:
        source_variance = float(np.std(source_values))
    else:
        source_variance = 10.0  # Default variance if single source

    # Temporal variance (week-over-week stability)
    if historical_values and len(historical_values) >= 2:
        temporal_variance = float(np.std(historical_values)) / np.sqrt(len(historical_values))
    else:
        temporal_variance = 12.0  # Default for new/sparse buckets

    # Combined variance (root sum of squares)
    total_variance = np.sqrt(
        coverage_variance**2 +
        source_variance**2 +
        temporal_variance**2
    )

    # Cap variance at reasonable level
    total_variance = min(total_variance, 25.0)

    # Compute interval
    margin = z_score * total_variance / 2  # Divide by 2 to get half-width
    low = max(0, observed_value - margin)
    high = min(100, observed_value + margin)

    return ConfidenceInterval(
        low=round(low, 1),
        mid=round(observed_value, 1),
        high=round(high, 1),
        variance=round(total_variance, 2),
        coverage_variance=round(coverage_variance, 2),
        source_variance=round(source_variance, 2),
        temporal_variance=round(temporal_variance, 2),
    )


class TechnicalMomentumScorer:
    """
    Computes TMS (Technical Momentum Score) for buckets.

    Sources: GitHub Trending, HuggingFace Trending
    Metrics:
    - Star velocity (new stars / week)
    - Fork velocity
    - Contributor velocity (if available)
    - Download velocity (HuggingFace)
    """

    # Weights for combining metrics
    WEIGHTS = {
        "star_velocity": 0.35,
        "fork_velocity": 0.15,
        "download_velocity": 0.30,
        "like_velocity": 0.10,
        "new_entity_count": 0.10,  # New repos/models appearing
    }

    def compute_bucket_velocity(
        self,
        bucket_id: str,
        entities: List[Dict[str, Any]],
        week_start: date
    ) -> Dict[str, Any]:
        """
        Compute technical velocity metrics for a bucket.

        Args:
            bucket_id: The trend bucket ID
            entities: List of entities (repos, models) mapped to this bucket
            week_start: Start of the observation week

        Returns:
            Dict with velocity metrics
        """
        star_velocity = 0
        fork_velocity = 0
        download_velocity = 0
        like_velocity = 0
        contributing_entities = []

        for entity in entities:
            metrics = entity.get("metrics", {})
            entity_name = entity.get("name", "")

            # GitHub metrics
            stars_today = metrics.get("stars_today", 0)
            star_velocity += stars_today * 7  # Estimate weekly from daily

            forks = metrics.get("forks", 0)
            # Estimate fork velocity as 10% of current forks (rough proxy)
            fork_velocity += forks * 0.1

            # HuggingFace metrics
            downloads = metrics.get("downloads_month", metrics.get("downloads", 0))
            # Monthly to weekly
            download_velocity += downloads / 4

            likes = metrics.get("likes", 0)
            like_velocity += likes * 0.1  # Rough weekly estimate

            if star_velocity > 0 or download_velocity > 0:
                contributing_entities.append(entity_name)

        return {
            "star_velocity": star_velocity,
            "fork_velocity": fork_velocity,
            "download_velocity": download_velocity,
            "like_velocity": like_velocity,
            "new_entity_count": len(entities),
            "contributing_entities": _dedupe_entities(contributing_entities, 10),
        }

    def compute_primary_velocity(self, metrics: Dict[str, Any]) -> float:
        """
        Compute primary velocity score from metrics.

        Uses log-scale weighted combination.
        """
        components = []

        for metric_name, weight in self.WEIGHTS.items():
            value = metrics.get(metric_name, 0)
            if value > 0:
                # Log scale to handle power-law distributions
                log_value = math.log10(value + 1)
                components.append(log_value * weight)

        return sum(components)


class CapitalConvictionScorer:
    """
    Computes CCS (Capital Conviction Score) for buckets.

    Sources: Crunchbase, VC portfolio tracking
    Metrics:
    - Deal velocity (new funding rounds / week)
    - Smart money presence (tier-1 VC count)
    - New company formation velocity
    - Stage progression (seed -> A time)
    """

    # Top-tier VCs (simplified list)
    TIER1_VCS = {
        "sequoia", "a16z", "andreessen horowitz", "benchmark",
        "accel", "greylock", "founders fund", "tiger global",
        "softbank", "lightspeed", "general catalyst", "index ventures",
    }

    WEIGHTS = {
        "deal_velocity": 0.35,
        "smart_money_count": 0.25,
        "new_company_count": 0.20,
        "total_funding_velocity": 0.20,
    }

    def compute_bucket_velocity(
        self,
        bucket_id: str,
        companies: List[Dict[str, Any]],
        week_start: date
    ) -> Dict[str, Any]:
        """
        Compute capital velocity metrics for a bucket.

        Args:
            bucket_id: The trend bucket ID
            companies: Companies mapped to this bucket (from Crunchbase)
            week_start: Start of observation week

        Returns:
            Dict with velocity metrics
        """
        # For now, use company count and rank as proxies
        # In production, this would track actual funding rounds
        deal_velocity = 0
        smart_money_count = 0
        new_company_count = len(companies)
        total_funding = 0
        contributing_entities = []

        for company in companies:
            name = company.get("name", "")
            # Use CB rank as quality signal (lower = better)
            cb_rank = company.get("cb_rank", company.get("rank", 1000))

            # Proxy: companies in top 500 by CB rank count as "hot"
            if cb_rank <= 500:
                deal_velocity += 1

            # Check for smart money (would need investor data)
            investors = company.get("investors", [])
            for inv in investors:
                inv_name = inv.lower() if isinstance(inv, str) else inv.get("name", "").lower()
                if any(t1 in inv_name for t1 in self.TIER1_VCS):
                    smart_money_count += 1
                    break

            contributing_entities.append(name)

        return {
            "deal_velocity": deal_velocity,
            "smart_money_count": smart_money_count,
            "new_company_count": new_company_count,
            "total_funding_velocity": total_funding,
            "contributing_entities": _dedupe_entities(contributing_entities, 10),
        }

    def compute_primary_velocity(self, metrics: Dict[str, Any]) -> float:
        """Compute primary velocity score."""
        components = []

        for metric_name, weight in self.WEIGHTS.items():
            value = metrics.get(metric_name, 0)
            if value > 0:
                log_value = math.log10(value + 1)
                components.append(log_value * weight)

        return sum(components)


class EnterpriseInstitutionalScorer:
    """
    Computes EIS (Enterprise Institutional Signal) for buckets.

    Sources: SEC EDGAR filings (10-K, 10-Q, 8-K)
    Metrics:
    - Offensive mentions (growth strategy, investment, platform)
    - Defensive mentions (risk factors, competition, disruption)
    - Filing velocity (new mentions / quarter)
    """

    # Keywords for offensive vs defensive classification
    OFFENSIVE_KEYWORDS = [
        "strategic investment", "platform expansion", "ai initiative",
        "digital transformation", "growth opportunity", "competitive advantage",
        "innovation", "partnership", "acquisition", "adoption",
    ]

    DEFENSIVE_KEYWORDS = [
        "risk factor", "competition", "disruption", "threat",
        "regulatory", "compliance", "uncertainty", "challenge",
        "cybersecurity", "data privacy", "market risk",
    ]

    def compute_bucket_velocity(
        self,
        bucket_id: str,
        filings: List[Dict[str, Any]],
        week_start: date
    ) -> Dict[str, Any]:
        """
        Compute enterprise signal metrics for a bucket.

        Args:
            bucket_id: The trend bucket ID
            filings: SEC filings mentioning entities in this bucket
            week_start: Start of observation week

        Returns:
            Dict with metrics including offensive vs defensive split
        """
        offensive_mentions = 0
        defensive_mentions = 0
        filing_count = len(filings)
        contributing_entities = []

        for filing in filings:
            # Classify filing context as offensive or defensive
            context = filing.get("context", filing.get("description", "")).lower()
            filing_type = filing.get("filing_type", "").lower()

            # S-1 filings are inherently offensive (growth/IPO)
            if "s-1" in filing_type:
                offensive_mentions += 2
            elif "10-k" in filing_type:
                # Check context for offensive vs defensive
                off_score = sum(1 for kw in self.OFFENSIVE_KEYWORDS if kw in context)
                def_score = sum(1 for kw in self.DEFENSIVE_KEYWORDS if kw in context)
                offensive_mentions += off_score
                defensive_mentions += def_score

            company = filing.get("company_name", filing.get("name", ""))
            contributing_entities.append(company)

        return {
            "offensive_mentions": offensive_mentions,
            "defensive_mentions": defensive_mentions,
            "filing_count": filing_count,
            "contributing_entities": _dedupe_entities(contributing_entities, 10),
        }

    def compute_primary_velocity(
        self,
        metrics: Dict[str, Any],
        signal_type: str = "offensive"
    ) -> float:
        """
        Compute primary velocity score.

        Args:
            metrics: Raw metrics
            signal_type: "offensive" or "defensive"
        """
        if signal_type == "offensive":
            value = metrics.get("offensive_mentions", 0)
        else:
            value = metrics.get("defensive_mentions", 0)

        if value > 0:
            return math.log10(value + 1)
        return 0.0


class NarrativeAttentionScorer:
    """
    Computes NAS (Narrative/Attention Score) for buckets.

    Sources: News pipeline, social media (future)
    Metrics:
    - Article velocity (new articles / week)
    - Average sentiment
    - Mention velocity
    """

    def compute_bucket_velocity(
        self,
        bucket_id: str,
        articles: List[Dict[str, Any]],
        week_start: date
    ) -> Dict[str, Any]:
        """
        Compute narrative/attention metrics for a bucket.

        Args:
            bucket_id: The trend bucket ID
            articles: News articles mentioning entities in this bucket
            week_start: Start of observation week

        Returns:
            Dict with metrics
        """
        article_count = len(articles)
        total_sentiment = 0
        mention_count = 0
        contributing_entities = []

        for article in articles:
            # Sentiment from 5D scoring
            sentiment = article.get("weighted_score", 5.0)
            total_sentiment += sentiment

            # Count entity mentions
            mentions = article.get("entity_mentions", [])
            mention_count += len(mentions)

            # Track contributing entities
            for mention in mentions[:3]:
                if isinstance(mention, dict):
                    contributing_entities.append(mention.get("entity", ""))
                elif isinstance(mention, str):
                    contributing_entities.append(mention)

        avg_sentiment = total_sentiment / article_count if article_count > 0 else 5.0

        return {
            "article_count": article_count,
            "mention_count": mention_count,
            "sentiment_avg": avg_sentiment,
            "contributing_entities": list(set(contributing_entities))[:10],
        }

    def compute_primary_velocity(self, metrics: Dict[str, Any]) -> float:
        """Compute primary velocity score."""
        article_count = metrics.get("article_count", 0)
        sentiment = metrics.get("sentiment_avg", 5.0)

        if article_count > 0:
            # Combine volume and sentiment
            volume_score = math.log10(article_count + 1)
            # Sentiment boost (1.0 = neutral, 1.5 = very positive)
            sentiment_multiplier = 1.0 + (sentiment - 5.0) / 10
            return volume_score * max(0.5, sentiment_multiplier)

        return 0.0


# =============================================================================
# Bucket Aggregator
# =============================================================================

class BucketAggregator:
    """
    Aggregates entity-level data into bucket-level scores.

    Main workflow:
    1. Tag entities to buckets
    2. Compute velocity metrics per bucket per instrument
    3. Convert to percentiles across all buckets
    4. Build BucketProfile with all four subscores
    """

    def __init__(self):
        self.tagger = BucketTagger()
        self.technical_scorer = TechnicalMomentumScorer()
        self.capital_scorer = CapitalConvictionScorer()
        self.enterprise_scorer = EnterpriseInstitutionalScorer()
        self.narrative_scorer = NarrativeAttentionScorer()

    def compute_all_bucket_scores(
        self,
        github_data: List[Dict[str, Any]],
        huggingface_data: List[Dict[str, Any]],
        company_data: List[Dict[str, Any]],
        sec_data: List[Dict[str, Any]],
        news_data: Optional[List[Dict[str, Any]]] = None,
        week_start: Optional[date] = None
    ) -> List[BucketProfile]:
        """
        Compute scores for all buckets from entity data.

        Args:
            github_data: GitHub trending repos
            huggingface_data: HuggingFace trending models/spaces
            company_data: Crunchbase companies
            sec_data: SEC EDGAR filings
            news_data: News articles (optional)
            week_start: Week start date (defaults to current week)

        Returns:
            List of BucketProfile for all scored buckets
        """
        if week_start is None:
            week_start, _ = get_week_bounds(date.today())

        # Step 1: Tag all entities to buckets
        entities_by_bucket = self._tag_all_entities(
            github_data, huggingface_data, company_data, sec_data
        )

        # Step 2: Compute raw velocities per bucket per instrument
        bucket_metrics = {}
        for bucket_id in self.tagger.buckets.keys():
            bucket_metrics[bucket_id] = {
                "technical": {"raw_score": 0},
                "capital": {"raw_score": 0},
                "enterprise_offensive": {"raw_score": 0},
                "enterprise_defensive": {"raw_score": 0},
                "narrative": {"raw_score": 0},
            }

        # Technical (GitHub + HuggingFace)
        for bucket_id, entities in entities_by_bucket.get("technical", {}).items():
            metrics = self.technical_scorer.compute_bucket_velocity(
                bucket_id, entities, week_start
            )
            raw_score = self.technical_scorer.compute_primary_velocity(metrics)
            bucket_metrics[bucket_id]["technical"] = {
                "raw_score": raw_score,
                "metrics": metrics,
            }

        # Capital (Companies)
        for bucket_id, companies in entities_by_bucket.get("capital", {}).items():
            metrics = self.capital_scorer.compute_bucket_velocity(
                bucket_id, companies, week_start
            )
            raw_score = self.capital_scorer.compute_primary_velocity(metrics)
            bucket_metrics[bucket_id]["capital"] = {
                "raw_score": raw_score,
                "metrics": metrics,
            }

        # Enterprise (SEC)
        for bucket_id, filings in entities_by_bucket.get("enterprise", {}).items():
            metrics = self.enterprise_scorer.compute_bucket_velocity(
                bucket_id, filings, week_start
            )
            off_score = self.enterprise_scorer.compute_primary_velocity(metrics, "offensive")
            def_score = self.enterprise_scorer.compute_primary_velocity(metrics, "defensive")
            bucket_metrics[bucket_id]["enterprise_offensive"] = {
                "raw_score": off_score,
                "metrics": metrics,
            }
            bucket_metrics[bucket_id]["enterprise_defensive"] = {
                "raw_score": def_score,
                "metrics": metrics,
            }

        # Step 3: Compute percentiles
        profiles = self._compute_percentiles_and_profiles(bucket_metrics, week_start)

        return profiles

    def _tag_all_entities(
        self,
        github_data: List[Dict[str, Any]],
        huggingface_data: List[Dict[str, Any]],
        company_data: List[Dict[str, Any]],
        sec_data: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
        """
        Tag all entities to buckets, organized by instrument.

        Returns:
            {
                "technical": {bucket_id: [entities...]},
                "capital": {bucket_id: [companies...]},
                "enterprise": {bucket_id: [filings...]}
            }
        """
        result = {
            "technical": defaultdict(list),
            "capital": defaultdict(list),
            "enterprise": defaultdict(list),
        }

        # GitHub repos
        for repo in github_data:
            matches = self.tagger.tag_entity(
                name=repo.get("name", ""),
                description=repo.get("description"),
                topics=repo.get("metrics", {}).get("topics", []),
                entity_type="repo"
            )
            for match in matches:
                result["technical"][match.bucket_id].append(repo)

        # HuggingFace models/spaces
        for model in huggingface_data:
            metrics = model.get("metrics", {})
            matches = self.tagger.tag_entity(
                name=model.get("name", ""),
                description=model.get("description"),
                tasks=[metrics.get("task")] if metrics.get("task") else None,
                tags=metrics.get("tags", []),
                entity_type="model"
            )
            for match in matches:
                result["technical"][match.bucket_id].append(model)

        # Companies
        for company in company_data:
            matches = self.tagger.tag_entity(
                name=company.get("name", ""),
                description=company.get("description"),
                tags=company.get("categories", []),
                entity_type="company"
            )
            for match in matches:
                result["capital"][match.bucket_id].append(company)

        # SEC filings
        for filing in sec_data:
            matches = self.tagger.tag_entity(
                name=filing.get("company_name", filing.get("name", "")),
                description=filing.get("description"),
                entity_type="issuer"
            )
            for match in matches:
                result["enterprise"][match.bucket_id].append(filing)

        return result

    def _compute_percentiles_and_profiles(
        self,
        bucket_metrics: Dict[str, Dict[str, Dict[str, Any]]],
        week_start: date
    ) -> List[BucketProfile]:
        """
        Convert raw scores to percentiles and build profiles.
        """
        profiles = []

        # Collect all raw scores per instrument
        all_technical = [m["technical"]["raw_score"] for m in bucket_metrics.values()]
        all_capital = [m["capital"]["raw_score"] for m in bucket_metrics.values()]
        all_eis_off = [m["enterprise_offensive"]["raw_score"] for m in bucket_metrics.values()]
        all_eis_def = [m["enterprise_defensive"]["raw_score"] for m in bucket_metrics.values()]

        for bucket_id, metrics in bucket_metrics.items():
            bucket = self.tagger.get_bucket(bucket_id)
            if not bucket:
                continue

            # Compute percentiles
            tms = compute_percentile(metrics["technical"]["raw_score"], all_technical)
            ccs = compute_percentile(metrics["capital"]["raw_score"], all_capital)
            eis_off = compute_percentile(metrics["enterprise_offensive"]["raw_score"], all_eis_off)
            eis_def = compute_percentile(metrics["enterprise_defensive"]["raw_score"], all_eis_def)

            # Compute heat score
            heat = 0.5 * tms + 0.3 * ccs + 0.2 * eis_off

            # Determine lifecycle state
            lifecycle = self._determine_lifecycle(tms, ccs, eis_off, eis_def)

            # Get top contributing entities
            tech_entities = metrics["technical"].get("metrics", {}).get("contributing_entities", [])
            cap_entities = metrics["capital"].get("metrics", {}).get("contributing_entities", [])
            ent_entities = metrics["enterprise_offensive"].get("metrics", {}).get("contributing_entities", [])

            profile = BucketProfile(
                bucket_id=bucket_id,
                bucket_name=bucket.name,
                week_start=week_start,
                tms=tms,
                ccs=ccs,
                eis_offensive=eis_off,
                eis_defensive=eis_def,
                heat_score=heat,
                lifecycle_state=lifecycle,
                top_technical_entities=tech_entities[:5],
                top_capital_entities=cap_entities[:5],
                top_enterprise_entities=ent_entities[:5],
            )
            profiles.append(profile)

        # Sort by heat score
        profiles.sort(key=lambda p: p.heat_score, reverse=True)
        return profiles

    def _determine_lifecycle(
        self,
        tms: float,
        ccs: float,
        eis_off: float,
        eis_def: float
    ) -> LifecycleState:
        """
        Determine lifecycle state from subscores.
        """
        # Emerging: High TMS, low CCS
        if tms > 70 and ccs < 40:
            return LifecycleState.EMERGING

        # Validating: Both TMS and CCS elevated
        if tms > 50 and ccs > 50:
            # Check if enterprise signals are appearing
            if eis_off > 50 or eis_def > 50:
                return LifecycleState.ESTABLISHING
            return LifecycleState.VALIDATING

        # Establishing: CCS + EIS high
        if ccs > 60 and (eis_off > 60 or eis_def > 60):
            return LifecycleState.ESTABLISHING

        # Mainstream: All stable, moderate levels
        if tms < 50 and ccs > 40 and (eis_off > 40 or eis_def > 40):
            return LifecycleState.MAINSTREAM

        # Default to emerging
        return LifecycleState.EMERGING


def generate_bucket_profiles_from_aggregates(
    trend_aggregate_dir: Path,
    crunchbase_dir: Optional[Path] = None,
    alternative_signals_dir: Optional[Path] = None,
    output_path: Optional[Path] = None,
    days_to_include: int = 7,
    include_financial_signals: bool = True
) -> List[BucketProfile]:
    """
    Generate bucket profiles from trend aggregate data, Crunchbase, and alternative signals.

    This merges multiple data sources to compute comprehensive bucket-level scores:
    - Trend aggregates (news articles) -> NAS
    - Crunchbase companies -> CCS
    - GitHub trending repos -> TMS
    - HuggingFace trending models -> TMS
    - SEC EDGAR filings -> EIS

    Args:
        trend_aggregate_dir: Path to data/cache/trend_aggregate/
        crunchbase_dir: Path to data/crunchbase/ (optional)
        alternative_signals_dir: Path to data/alternative_signals/ (optional)
        output_path: Where to save bucket_profiles.json (optional)
        days_to_include: How many days of data to merge

    Returns:
        List of BucketProfile objects
    """
    import glob
    import json
    from pathlib import Path
    from collections import defaultdict

    tagger = BucketTagger()

    # Track data sources loaded
    data_sources = []

    # =========================================================================
    # 1. LOAD TREND AGGREGATES (Articles -> NAS)
    # =========================================================================
    aggregate_files = sorted(
        glob.glob(str(trend_aggregate_dir / "combined_*.json")),
        reverse=True
    )[:days_to_include]

    print(f"Loading {len(aggregate_files)} trend aggregate files...")

    all_articles = []
    all_entities = defaultdict(set)  # bucket_id -> set of entity names
    bucket_article_counts = defaultdict(int)
    bucket_entity_data = defaultdict(list)  # bucket_id -> list of entity info

    for filepath in aggregate_files:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            articles = data.get("articles", [])
            all_articles.extend(articles)

            for article in articles:
                entities = article.get("searchable_entities", {})

                for company in entities.get("companies", []):
                    matches = tagger.tag_entity(
                        name=company,
                        description=article.get("content", "")[:500],
                        entity_type="company"
                    )
                    for match in matches:
                        all_entities[match.bucket_id].add(company)
                        bucket_article_counts[match.bucket_id] += 1
                        bucket_entity_data[match.bucket_id].append({
                            "name": company,
                            "type": "company",
                            "source": "article",
                        })

                for topic in entities.get("topics", []):
                    matches = tagger.tag_entity(
                        name=topic,
                        description=article.get("content", "")[:500],
                        entity_type="topic"
                    )
                    for match in matches:
                        all_entities[match.bucket_id].add(f"topic:{topic}")

        except Exception as e:
            print(f"  Error loading {filepath}: {e}")

    data_sources.append(f"trend_aggregates:{len(all_articles)}")

    # =========================================================================
    # 2. LOAD CRUNCHBASE COMPANIES (-> CCS)
    # =========================================================================
    crunchbase_companies = []
    if crunchbase_dir and crunchbase_dir.exists():
        cb_files = sorted(glob.glob(str(crunchbase_dir / "ai_companies_*.json")), reverse=True)
        if cb_files:
            try:
                with open(cb_files[0], 'r', encoding='utf-8') as f:
                    crunchbase_companies = json.load(f)
                print(f"Loaded {len(crunchbase_companies)} Crunchbase companies")

                for company in crunchbase_companies:
                    matches = tagger.tag_entity(
                        name=company.get("name", ""),
                        description=company.get("description", ""),
                        tags=company.get("industries", "").split(",") if company.get("industries") else [],
                        entity_type="company"
                    )
                    for match in matches:
                        all_entities[match.bucket_id].add(company.get("name", ""))
                        bucket_entity_data[match.bucket_id].append({
                            "name": company.get("name", ""),
                            "type": "company",
                            "source": "crunchbase",
                            "cb_rank": company.get("cb_rank"),
                        })
                data_sources.append(f"crunchbase:{len(crunchbase_companies)}")
            except Exception as e:
                print(f"  Error loading Crunchbase: {e}")

    # =========================================================================
    # 3. LOAD ALTERNATIVE SIGNALS (GitHub, HuggingFace, SEC, ProductHunt)
    # =========================================================================
    # Track technical velocity metrics per bucket
    bucket_github_stars = defaultdict(int)
    bucket_github_repos = defaultdict(int)
    bucket_hf_downloads = defaultdict(int)
    bucket_hf_models = defaultdict(int)
    bucket_sec_offensive = defaultdict(int)
    bucket_sec_defensive = defaultdict(int)
    bucket_producthunt = defaultdict(int)

    if alternative_signals_dir and alternative_signals_dir.exists():
        # ----- GitHub Trending -----
        github_files = sorted(glob.glob(str(alternative_signals_dir / "github_trending_*.json")), reverse=True)
        if github_files:
            try:
                with open(github_files[0], 'r', encoding='utf-8') as f:
                    github_data = json.load(f)
                print(f"Loaded {len(github_data)} GitHub trending repos")

                for repo in github_data:
                    name = repo.get("name", "")
                    desc = repo.get("description", "")
                    metrics = repo.get("metrics", {})
                    stars_today = metrics.get("stars_today", 0)

                    matches = tagger.tag_entity(
                        name=name,
                        description=desc,
                        entity_type="repo"
                    )
                    for match in matches:
                        all_entities[match.bucket_id].add(f"repo:{name}")
                        bucket_github_stars[match.bucket_id] += stars_today * 7  # weekly estimate
                        bucket_github_repos[match.bucket_id] += 1
                        bucket_entity_data[match.bucket_id].append({
                            "name": name,
                            "type": "repo",
                            "source": "github",
                            "stars_today": stars_today,
                        })
                data_sources.append(f"github:{len(github_data)}")
            except Exception as e:
                print(f"  Error loading GitHub: {e}")

        # ----- HuggingFace Trending -----
        hf_files = sorted(glob.glob(str(alternative_signals_dir / "huggingface_trending_*.json")), reverse=True)
        if hf_files:
            try:
                with open(hf_files[0], 'r', encoding='utf-8') as f:
                    hf_data = json.load(f)
                print(f"Loaded {len(hf_data)} HuggingFace models")

                for model in hf_data:
                    name = model.get("name", "")
                    desc = model.get("description", "")
                    metrics = model.get("metrics", {})
                    downloads = metrics.get("downloads_month", 0)
                    task = metrics.get("task", "")
                    tags = metrics.get("tags", [])

                    matches = tagger.tag_entity(
                        name=name,
                        description=desc,
                        tasks=[task] if task else None,
                        tags=tags if isinstance(tags, list) else [],
                        entity_type="model"
                    )
                    for match in matches:
                        all_entities[match.bucket_id].add(f"model:{name}")
                        bucket_hf_downloads[match.bucket_id] += downloads / 4  # weekly estimate
                        bucket_hf_models[match.bucket_id] += 1
                        bucket_entity_data[match.bucket_id].append({
                            "name": name,
                            "type": "model",
                            "source": "huggingface",
                            "downloads": downloads,
                        })
                data_sources.append(f"huggingface:{len(hf_data)}")
            except Exception as e:
                print(f"  Error loading HuggingFace: {e}")

        # ----- SEC EDGAR Filings -----
        sec_files = sorted(glob.glob(str(alternative_signals_dir / "sec_edgar_*.json")), reverse=True)
        if sec_files:
            try:
                with open(sec_files[0], 'r', encoding='utf-8') as f:
                    sec_data = json.load(f)
                print(f"Loaded {len(sec_data)} SEC filings")

                # Keywords for offensive vs defensive classification
                offensive_keywords = ["strategic", "growth", "investment", "platform", "innovation", "partnership"]
                defensive_keywords = ["risk", "competition", "regulatory", "compliance", "threat", "uncertainty"]

                for filing in sec_data:
                    name = filing.get("name", "")
                    desc = filing.get("description", "")
                    metrics = filing.get("metrics", {})
                    filing_type = metrics.get("filing_type", "")

                    matches = tagger.tag_entity(
                        name=name,
                        description=desc,
                        entity_type="company"
                    )

                    # Classify as offensive (S-1, growth) or defensive (10-K risk sections)
                    is_offensive = filing_type in ["S-1", "S-1/A", "8-K"]
                    desc_lower = (desc or "").lower()

                    for match in matches:
                        all_entities[match.bucket_id].add(f"sec:{name}")
                        if is_offensive:
                            bucket_sec_offensive[match.bucket_id] += 2
                        else:
                            # Check keywords in description
                            off_count = sum(1 for kw in offensive_keywords if kw in desc_lower)
                            def_count = sum(1 for kw in defensive_keywords if kw in desc_lower)
                            bucket_sec_offensive[match.bucket_id] += off_count
                            bucket_sec_defensive[match.bucket_id] += def_count

                        bucket_entity_data[match.bucket_id].append({
                            "name": name,
                            "type": "issuer",
                            "source": "sec",
                            "filing_type": filing_type,
                        })
                data_sources.append(f"sec:{len(sec_data)}")
            except Exception as e:
                print(f"  Error loading SEC: {e}")

        # ----- ProductHunt -----
        ph_files = sorted(glob.glob(str(alternative_signals_dir / "producthunt_*.json")), reverse=True)
        if ph_files:
            try:
                with open(ph_files[0], 'r', encoding='utf-8') as f:
                    ph_data = json.load(f)
                # ProductHunt data is minimal, just count launches
                valid_launches = [p for p in ph_data if p.get("name") and p.get("description")]
                print(f"Loaded {len(valid_launches)} ProductHunt launches")

                for launch in valid_launches:
                    name = launch.get("name", "")
                    desc = launch.get("description", "")

                    matches = tagger.tag_entity(
                        name=name,
                        description=desc,
                        entity_type="product"
                    )
                    for match in matches:
                        bucket_producthunt[match.bucket_id] += 1
                        bucket_entity_data[match.bucket_id].append({
                            "name": name,
                            "type": "product",
                            "source": "producthunt",
                        })
                if valid_launches:
                    data_sources.append(f"producthunt:{len(valid_launches)}")
            except Exception as e:
                print(f"  Error loading ProductHunt: {e}")

        # ----- News Search (from news_search_scraper.py) -----
        bucket_news_search = defaultdict(int)
        news_search_files = sorted(glob.glob(str(alternative_signals_dir / "news_search_*.json")), reverse=True)
        if news_search_files:
            try:
                with open(news_search_files[0], 'r', encoding='utf-8') as f:
                    news_data = json.load(f)
                print(f"Loaded {len(news_data)} news search articles")

                for article in news_data:
                    name = article.get("name", "")  # Title
                    desc = article.get("description", "")
                    source = article.get("source", "")

                    matches = tagger.tag_entity(
                        name=name,
                        description=desc,
                        entity_type="article"
                    )
                    for match in matches:
                        bucket_news_search[match.bucket_id] += 1
                        bucket_article_counts[match.bucket_id] += 1
                        bucket_entity_data[match.bucket_id].append({
                            "name": name[:80] if name else "",
                            "type": "article",
                            "source": f"news_search:{source}",
                        })
                if news_data:
                    data_sources.append(f"news_search:{len(news_data)}")
            except Exception as e:
                print(f"  Error loading news search: {e}")

        # ----- AI Labs News (from ai_labs_scraper.py) -----
        bucket_ai_labs = defaultdict(int)
        ai_labs_files = sorted(glob.glob(str(alternative_signals_dir / "ai_labs_news_*.json")), reverse=True)
        if ai_labs_files:
            try:
                with open(ai_labs_files[0], 'r', encoding='utf-8') as f:
                    ai_labs_data = json.load(f)
                print(f"Loaded {len(ai_labs_data)} AI labs news articles")

                for article in ai_labs_data:
                    name = article.get("name", "")  # Title
                    desc = article.get("description", "")
                    lab = article.get("lab", "")
                    research_areas = article.get("metrics", {}).get("research_areas", [])

                    # Use research areas for better bucket matching
                    enhanced_desc = f"{desc} {' '.join(research_areas)}"

                    matches = tagger.tag_entity(
                        name=name,
                        description=enhanced_desc,
                        entity_type="article"
                    )
                    for match in matches:
                        bucket_ai_labs[match.bucket_id] += 1
                        bucket_article_counts[match.bucket_id] += 1
                        bucket_entity_data[match.bucket_id].append({
                            "name": name[:80] if name else "",
                            "type": "ai_lab_news",
                            "source": f"ai_labs:{lab}",
                        })
                if ai_labs_data:
                    data_sources.append(f"ai_labs:{len(ai_labs_data)}")
            except Exception as e:
                print(f"  Error loading AI labs news: {e}")

    # =========================================================================
    # 3b. LOAD FINANCIAL SIGNALS (PMS/CSS)
    # =========================================================================
    bucket_pms = {}  # bucket_id -> PMS score (0-100)
    bucket_css = {}  # bucket_id -> CSS score (0-100)
    bucket_pms_contributors = {}  # bucket_id -> list of contributors
    bucket_css_contributors = {}  # bucket_id -> list of contributors

    if FINANCIAL_SIGNALS_AVAILABLE:
        try:
            financial_signals = get_bucket_financial_signals()
            if financial_signals:
                print(f"Loaded financial signals for {len(financial_signals)} buckets")
                for bucket_id, signals in financial_signals.items():
                    if signals.get("pms") is not None:
                        bucket_pms[bucket_id] = signals["pms"]
                        bucket_pms_contributors[bucket_id] = signals.get("pms_contributors_text", [])
                    if signals.get("css") is not None:
                        bucket_css[bucket_id] = signals["css"]
                        bucket_css_contributors[bucket_id] = signals.get("css_contributors_text", [])
                data_sources.append(f"financial_signals:{len(financial_signals)}")
        except Exception as e:
            print(f"  Warning: Could not load financial signals: {e}")

    # =========================================================================
    # 4. COMPUTE RAW SCORES PER BUCKET WITH COVERAGE TRACKING
    # =========================================================================
    print(f"\nData sources loaded: {', '.join(data_sources)}")
    print(f"Total articles: {len(all_articles)}")
    print(f"Buckets with data: {len(all_entities)}")

    week_start, _ = get_week_bounds(date.today())
    all_buckets = list(tagger.buckets.keys())

    raw_scores = {}
    for bucket_id in all_buckets:
        entity_count = len(all_entities.get(bucket_id, set()))
        article_count = bucket_article_counts.get(bucket_id, 0)

        # NAS (Narrative Attention Score) - articles + product launches
        nas_raw = article_count + bucket_producthunt.get(bucket_id, 0) * 2
        has_nas_data = article_count > 0 or bucket_producthunt.get(bucket_id, 0) > 0

        # CCS (Capital Conviction Score) - company count weighted by source
        company_entries = [e for e in bucket_entity_data.get(bucket_id, []) if e.get("type") == "company"]
        ccs_raw = len(company_entries)
        # Bonus for companies with CB rank in top 500
        for entry in company_entries:
            if entry.get("cb_rank") and entry["cb_rank"] <= 500:
                ccs_raw += 1
        has_ccs_data = len(company_entries) > 0

        # TMS (Technical Momentum Score) - REAL DATA from GitHub + HuggingFace
        github_velocity = bucket_github_stars.get(bucket_id, 0)
        hf_velocity = bucket_hf_downloads.get(bucket_id, 0)
        repo_count = bucket_github_repos.get(bucket_id, 0)
        model_count = bucket_hf_models.get(bucket_id, 0)
        has_tms_data = repo_count > 0 or model_count > 0

        # Log-scale to handle power-law distribution
        tms_raw = 0
        if github_velocity > 0:
            tms_raw += math.log10(github_velocity + 1) * 10
        if hf_velocity > 0:
            tms_raw += math.log10(hf_velocity + 1) * 5
        tms_raw += repo_count * 2 + model_count

        # EIS (Enterprise Institutional Signal) - REAL DATA from SEC filings
        eis_off_raw = bucket_sec_offensive.get(bucket_id, 0)
        eis_def_raw = bucket_sec_defensive.get(bucket_id, 0)
        has_eis_data = eis_off_raw > 0 or eis_def_raw > 0

        raw_scores[bucket_id] = {
            "nas": nas_raw,
            "ccs": ccs_raw,
            "tms": tms_raw,
            "eis_off": eis_off_raw,
            "eis_def": eis_def_raw,
            "entity_count": entity_count,
            "article_count": article_count,
            "github_repos": repo_count,
            "hf_models": model_count,
            # Coverage flags - None means no data, value means observed
            "has_tms_data": has_tms_data,
            "has_ccs_data": has_ccs_data,
            "has_nas_data": has_nas_data,
            "has_eis_data": has_eis_data,
        }

    # =========================================================================
    # 5. CONVERT TO PERCENTILES (only among buckets WITH data for that metric)
    # =========================================================================
    # Filter to only include buckets with actual data for each metric
    tms_with_data = [s["tms"] for s in raw_scores.values() if s["has_tms_data"]]
    ccs_with_data = [s["ccs"] for s in raw_scores.values() if s["has_ccs_data"]]
    nas_with_data = [s["nas"] for s in raw_scores.values() if s["has_nas_data"]]
    eis_off_with_data = [s["eis_off"] for s in raw_scores.values() if s["has_eis_data"]]
    eis_def_with_data = [s["eis_def"] for s in raw_scores.values() if s["has_eis_data"]]

    print(f"\nCoverage stats:")
    print(f"  TMS: {len(tms_with_data)}/{len(raw_scores)} buckets have technical data")
    print(f"  CCS: {len(ccs_with_data)}/{len(raw_scores)} buckets have capital data")
    print(f"  NAS: {len(nas_with_data)}/{len(raw_scores)} buckets have narrative data")
    print(f"  EIS: {len(eis_off_with_data)}/{len(raw_scores)} buckets have enterprise data")

    profiles = []
    for bucket_id, bucket in tagger.buckets.items():
        scores = raw_scores.get(bucket_id, {"nas": 0, "ccs": 0, "tms": 0, "eis_off": 0, "eis_def": 0, "entity_count": 0,
                                            "has_tms_data": False, "has_ccs_data": False, "has_nas_data": False, "has_eis_data": False})

        # For metrics with no data, use None to indicate "unknown" vs 0
        # For display, we'll use a default value but track coverage
        if scores["has_tms_data"]:
            tms = compute_percentile(scores["tms"], tms_with_data) if tms_with_data else 50
        else:
            tms = None  # No technical data for this bucket

        if scores["has_ccs_data"]:
            ccs = compute_percentile(scores["ccs"], ccs_with_data) if ccs_with_data else 50
        else:
            ccs = None  # No capital data for this bucket

        if scores["has_nas_data"]:
            nas = compute_percentile(scores["nas"], nas_with_data) if nas_with_data else 50
        else:
            nas = None  # No narrative data for this bucket

        if scores["has_eis_data"]:
            eis_off = compute_percentile(scores["eis_off"], eis_off_with_data) if eis_off_with_data else 50
            eis_def = compute_percentile(scores["eis_def"], eis_def_with_data) if eis_def_with_data else 50
        else:
            eis_off = None
            eis_def = None

        # For heat score and display, use actual value or 50 (neutral) if no data
        tms_display = tms if tms is not None else 50
        ccs_display = ccs if ccs is not None else 50
        nas_display = nas if nas is not None else 50
        eis_off_display = eis_off if eis_off is not None else 50
        eis_def_display = eis_def if eis_def is not None else 50

        # Compute heat score - only from metrics with data (weighted more heavily)
        # If a metric has no data, it contributes neutral (50) rather than 0
        heat = tms_display * 0.30 + ccs_display * 0.25 + eis_off_display * 0.20 + nas_display * 0.25

        # Compute coverage score (how many signals we have for this bucket)
        coverage_count = sum([
            1 if scores["has_tms_data"] else 0,
            1 if scores["has_ccs_data"] else 0,
            1 if scores["has_nas_data"] else 0,
            1 if scores["has_eis_data"] else 0,
        ])
        coverage_pct = coverage_count / 4.0  # 0 to 1

        # Determine lifecycle state based on signal patterns (only if we have data)
        if tms is not None and ccs is not None:
            if tms > 70 and ccs < 40:
                state = LifecycleState.EMERGING
            elif tms > 50 and ccs > 40 and (eis_off is None or eis_off < 60):
                state = LifecycleState.VALIDATING
            elif eis_off is not None and (eis_off > 60 or (ccs > 60 and eis_off > 40)):
                state = LifecycleState.ESTABLISHING
            else:
                state = LifecycleState.MAINSTREAM
        elif coverage_count < 2:
            # Not enough data to determine state
            state = LifecycleState.EMERGING  # Default for low-coverage buckets
        else:
            state = LifecycleState.MAINSTREAM

        # Get top entities by type
        bucket_entries = bucket_entity_data.get(bucket_id, [])
        tech_entities = [e["name"] for e in bucket_entries if e.get("source") in ("github", "huggingface")][:5]
        capital_entities = [e["name"] for e in bucket_entries if e.get("source") in ("crunchbase", "article") and e.get("type") == "company"][:5]
        enterprise_entities = [e["name"] for e in bucket_entries if e.get("source") == "sec"][:5]

        # Get PMS/CSS from financial signals
        pms = bucket_pms.get(bucket_id)
        css = bucket_css.get(bucket_id)

        # Determine Gartner Hype Cycle phase
        hype_phase, hype_confidence, hype_rationale = determine_hype_cycle_phase(
            tms=tms,
            ccs=ccs,
            nas=nas,
            eis_offensive=eis_off,
        )

        profile = BucketProfile(
            bucket_id=bucket_id,
            bucket_name=bucket.name,
            week_start=week_start,
            tms=tms,
            ccs=ccs,
            eis_offensive=eis_off,
            eis_defensive=eis_def,
            nas=nas,
            pms=pms,  # Public Market Signal from Yahoo Finance
            css=css,  # Crypto Sentiment Signal from Kraken
            heat_score=heat,
            lifecycle_state=state,
            hype_cycle_phase=hype_phase,
            hype_cycle_confidence=hype_confidence,
            hype_cycle_rationale=hype_rationale,
            top_technical_entities=tech_entities,
            top_capital_entities=capital_entities,
            top_enterprise_entities=enterprise_entities,
            entity_count=scores["entity_count"],
        )
        profiles.append(profile)

    # Sort by heat score
    profiles.sort(key=lambda p: p.heat_score, reverse=True)

    # =========================================================================
    # 6. SAVE OUTPUT
    # =========================================================================
    if output_path:
        # Build profiles with coverage info
        profile_data = []
        for p in profiles:
            scores = raw_scores.get(p.bucket_id, {})
            profile_entry = {
                "bucket_id": p.bucket_id,
                "bucket_name": p.bucket_name,
                "week_start": p.week_start.isoformat(),
                "tms": p.tms,
                "ccs": p.ccs,
                "eis_offensive": p.eis_offensive,
                "eis_defensive": p.eis_defensive,
                "nas": p.nas,
                # Financial signals (public markets + crypto)
                "pms": p.pms,
                "css": p.css,
                "pms_contributors": bucket_pms_contributors.get(p.bucket_id, []),
                "css_contributors": bucket_css_contributors.get(p.bucket_id, []),
                "heat_score": p.heat_score,
                "lifecycle_state": p.lifecycle_state.value,
                # Gartner Hype Cycle positioning
                "hype_cycle_phase": p.hype_cycle_phase.value,
                "hype_cycle_confidence": p.hype_cycle_confidence,
                "hype_cycle_rationale": p.hype_cycle_rationale,
                "top_technical_entities": p.top_technical_entities,
                "top_capital_entities": p.top_capital_entities,
                "top_enterprise_entities": p.top_enterprise_entities,
                "entity_count": p.entity_count,
                # Coverage flags - allows dashboard to distinguish "no data" from "zero"
                "has_tms_data": scores.get("has_tms_data", False),
                "has_ccs_data": scores.get("has_ccs_data", False),
                "has_nas_data": scores.get("has_nas_data", False),
                "has_eis_data": scores.get("has_eis_data", False),
                "has_pms_data": p.pms is not None,
                "has_css_data": p.css is not None,
                # Raw counts for debugging/transparency
                "github_repos": scores.get("github_repos", 0),
                "hf_models": scores.get("hf_models", 0),
                "article_count": scores.get("article_count", 0),
            }
            profile_data.append(profile_entry)

        # Coverage summary
        coverage_summary = {
            "tms_coverage": f"{len(tms_with_data)}/{len(raw_scores)}",
            "ccs_coverage": f"{len(ccs_with_data)}/{len(raw_scores)}",
            "nas_coverage": f"{len(nas_with_data)}/{len(raw_scores)}",
            "eis_coverage": f"{len(eis_off_with_data)}/{len(raw_scores)}",
            "pms_coverage": f"{len(bucket_pms)}/{len(raw_scores)}",
            "css_coverage": f"{len(bucket_css)}/{len(raw_scores)}",
        }

        output_data = {
            "generated_at": datetime.now().isoformat(),
            "week_start": week_start.isoformat(),
            "data_sources": data_sources,
            "source_files": [Path(f).name for f in aggregate_files],
            "total_articles": len(all_articles),
            "coverage_summary": coverage_summary,
            "profiles": profile_data,
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)

        print(f"\nSaved {len(profiles)} bucket profiles to {output_path}")

    return profiles


if __name__ == "__main__":
    import sys
    from pathlib import Path

    # Check for --generate flag to run from trend aggregates
    if len(sys.argv) > 1 and sys.argv[1] == "--generate":
        print("=" * 60)
        print("GENERATE BUCKET PROFILES FROM TREND AGGREGATES")
        print("=" * 60)

        base_dir = Path(__file__).parent.parent
        trend_aggregate_dir = base_dir / "data" / "cache" / "trend_aggregate"
        crunchbase_dir = base_dir / "data" / "crunchbase"
        alternative_signals_dir = base_dir / "data" / "alternative_signals"
        output_path = base_dir / "data" / "cache" / "bucket_profiles.json"

        if not trend_aggregate_dir.exists():
            print(f"Error: Trend aggregate directory not found: {trend_aggregate_dir}")
            print("Run the multi-pipeline first: python main.py --multi-pipeline")
            sys.exit(1)

        profiles = generate_bucket_profiles_from_aggregates(
            trend_aggregate_dir=trend_aggregate_dir,
            crunchbase_dir=crunchbase_dir if crunchbase_dir.exists() else None,
            alternative_signals_dir=alternative_signals_dir if alternative_signals_dir.exists() else None,
            output_path=output_path,
            days_to_include=14  # Last 2 weeks
        )

        print()
        print("Top 10 buckets by heat score:")
        for i, p in enumerate(profiles[:10], 1):
            print(f"  {i:2}. {p.bucket_name}")
            tms_str = f"{p.tms:.0f}" if p.tms is not None else "N/A"
            ccs_str = f"{p.ccs:.0f}" if p.ccs is not None else "N/A"
            nas_str = f"{p.nas:.0f}" if p.nas is not None else "N/A"
            print(f"      TMS={tms_str} CCS={ccs_str} NAS={nas_str} Heat={p.heat_score:.0f}")
            print(f"      State: {p.lifecycle_state.value}, Entities: {p.entity_count}")

        print()
        print("Done! Bucket Radar dashboard should now show real data.")

    else:
        # Original test code
        print("=" * 60)
        print("BUCKET SCORERS TEST")
        print("=" * 60)
        print()
        print("Usage:")
        print("  python -m utils.bucket_scorers --generate")
        print("    Generate bucket profiles from trend aggregate data")
        print()

        aggregator = BucketAggregator()

        # Minimal test data
        test_repos = [
            {"name": "langchain", "description": "Building LLM apps", "metrics": {"stars_today": 100}},
            {"name": "vllm", "description": "LLM inference", "metrics": {"stars_today": 50}},
        ]

        test_models = [
            {"name": "meta-llama/Llama-3", "metrics": {"downloads": 1000000, "task": "text-generation"}},
        ]

        test_companies = [
            {"name": "Anthropic", "cb_rank": 5},
            {"name": "OpenAI", "cb_rank": 3},
        ]

        test_filings = []

        profiles = aggregator.compute_all_bucket_scores(
            github_data=test_repos,
            huggingface_data=test_models,
            company_data=test_companies,
            sec_data=test_filings,
        )

        print(f"Computed {len(profiles)} bucket profiles")
        print()
        print("Top 5 buckets by heat:")
        for p in profiles[:5]:
            print(f"  {p.bucket_name}")
            print(f"    TMS={p.tms:.0f} CCS={p.ccs:.0f} EIS_off={p.eis_offensive:.0f} Heat={p.heat_score:.0f}")
            print(f"    State: {p.lifecycle_state.value}")
            print()
