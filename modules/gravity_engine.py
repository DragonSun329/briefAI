"""
Gravity Engine - 16-Dimensional AI Content Scoring

Inspired by Kevin Rose's editorial scoring system for Nylon/Digg.
Evaluates content across 16 dimensions grouped into 4 categories:

1. IMPACT (4 dimensions)      - How significant is this?
2. GRAVITY (5 dimensions)     - Intellectual value & novelty
3. SIGNALS (3 dimensions)     - Trend & viral indicators
4. QUALITY FLAGS (4 negative) - Content quality warnings

This module integrates with briefAI's existing pipeline to provide
Bloomberg-grade content curation with AI editorial judgment.
"""

import json
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass, field, asdict
from enum import Enum
from loguru import logger

# Import LLM client
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.llm_client_enhanced import LLMClient

# Try to import embedding support for reprint detection
try:
    import numpy as np
    from sentence_transformers import SentenceTransformer
    EMBEDDINGS_AVAILABLE = True
except ImportError:
    EMBEDDINGS_AVAILABLE = False
    np = None


class ReprintDetector:
    """
    Detect duplicate/near-duplicate articles (reprints) within a batch.
    
    Uses embedding similarity to identify when the same story appears
    from multiple sources with minimal original reporting.
    
    Computes:
    - duplicate_ratio: fraction of batch that are near-duplicates
    - domain_entropy: diversity of sources covering the story
    - reprint_penalty: score reduction for low-effort reprints
    """
    
    # Similarity threshold for "same story" detection
    REPRINT_THRESHOLD = 0.85  # Higher than clustering (0.75) for tighter match
    
    # Minimum duplicate ratio to trigger penalty
    MIN_RATIO_FOR_PENALTY = 0.6
    
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        """Initialize reprint detector with embedding model."""
        self.available = EMBEDDINGS_AVAILABLE
        self.model = None
        
        if self.available:
            try:
                self.model = SentenceTransformer(model_name)
                logger.debug("Reprint detector initialized with embeddings")
            except Exception as e:
                logger.warning(f"Failed to load embedding model: {e}")
                self.available = False
    
    def _get_text(self, article: Dict[str, Any]) -> str:
        """Extract text for embedding."""
        title = article.get('title', '')
        content = article.get('content', article.get('summary', ''))[:500]
        return f"{title}. {content}"
    
    def _cosine_similarity(self, a, b) -> float:
        """Compute cosine similarity."""
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
    
    def detect_reprints(
        self,
        articles: List[Dict[str, Any]]
    ) -> Dict[int, Dict[str, Any]]:
        """
        Detect reprints within a batch of articles.
        
        Returns:
            Dict mapping article index -> {
                'duplicate_ratio': float (0-1),
                'similar_indices': List[int],
                'source_entropy': float,
                'reprint_penalty': float (0-0.3)
            }
        """
        if not self.available or not articles or len(articles) < 2:
            return {i: {'duplicate_ratio': 0, 'similar_indices': [], 
                       'source_entropy': 1.0, 'reprint_penalty': 0} 
                    for i in range(len(articles))}
        
        # Compute embeddings
        texts = [self._get_text(a) for a in articles]
        embeddings = self.model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        
        results = {}
        n = len(articles)
        
        for i in range(n):
            similar_indices = []
            sources = {articles[i].get('source', 'unknown')}
            
            # Find similar articles
            for j in range(n):
                if i == j:
                    continue
                sim = self._cosine_similarity(embeddings[i], embeddings[j])
                if sim >= self.REPRINT_THRESHOLD:
                    similar_indices.append(j)
                    sources.add(articles[j].get('source', 'unknown'))
            
            # Compute metrics
            duplicate_ratio = len(similar_indices) / (n - 1) if n > 1 else 0
            
            # Source entropy: higher = more diverse sources (good)
            # If same story from 5 different sources, entropy is high
            # If same story from 1 source repeated, entropy is low
            unique_sources = len(sources)
            source_entropy = unique_sources / max(1, len(similar_indices) + 1)
            
            # Compute penalty
            # High duplicate_ratio + low source_entropy = reprint spam
            # High duplicate_ratio + high source_entropy = legitimate big story
            reprint_penalty = 0.0
            if duplicate_ratio >= self.MIN_RATIO_FOR_PENALTY:
                # Base penalty from duplicate ratio
                base_penalty = (duplicate_ratio - self.MIN_RATIO_FOR_PENALTY) / 0.4 * 0.3
                # Reduce penalty if sources are diverse (legitimate big story)
                diversity_factor = min(1.0, source_entropy)
                reprint_penalty = base_penalty * (1 - diversity_factor * 0.5)
                reprint_penalty = min(0.3, max(0, reprint_penalty))
            
            results[i] = {
                'duplicate_ratio': round(duplicate_ratio, 3),
                'similar_indices': similar_indices,
                'source_entropy': round(source_entropy, 3),
                'unique_source_count': unique_sources,
                'reprint_penalty': round(reprint_penalty, 3)
            }
        
        return results


class ScoreCategory(Enum):
    IMPACT = "impact"
    GRAVITY = "gravity"
    SIGNALS = "signals"
    QUALITY = "quality"


@dataclass
class GravityScore:
    """Full 16-dimensional score for an article"""
    
    # IMPACT (positive, 1-10)
    industry_impact: float = 5.0      # Importance for tech/business sector
    consumer_impact: float = 5.0      # Importance for end-users/society
    actionability: float = 5.0        # Does it call for action/response?
    risk_urgency: float = 5.0         # Warns of urgent issues/threats?
    
    # GRAVITY / Intellectual Value (positive, 1-10)
    novelty: float = 5.0              # Originality, new insights (CRITICAL)
    technical_depth: float = 5.0      # Level of technical substance
    second_order_effects: float = 5.0 # Broader consequences/implications
    builder_relevance: float = 5.0    # Useful to developers/creators
    entertainment_value: float = 5.0  # Interesting/buzzworthy
    
    # SIGNALS / Trend Markers (positive, 1-10)
    signal_to_noise: float = 5.0      # Real substance vs hype
    viral_potential: float = 5.0      # Likely to spread/generate discussion
    early_trend_signal: float = 5.0   # Hints at emerging trend
    
    # QUALITY FLAGS (negative, 1-10 where HIGH = BAD)
    pr_fluff: float = 2.0             # Marketing spin detected
    speculation: float = 2.0          # Unsupported claims
    vagueness: float = 2.0            # Lack of concreteness
    sponsored: float = 2.0            # Paid/sponsored content
    
    # Metadata
    passes_novelty_gate: bool = True
    editorial_verdict: str = ""
    key_insight: str = ""
    
    def compute_final_score(self) -> float:
        """
        Compute weighted final score in 0-10 space.
        
        All components stay in 0-10 throughout:
        - Impact (0-10): 25% weight
        - Gravity (0-10): 35% weight, novelty 2x
        - Signals (0-10): 20% weight
        - Quality penalty: max -1.5 points (soft cap)
        
        Hard gates applied separately (sponsored >= 7, pr_fluff >= 8).
        """
        import math
        
        # === Step 1: Compute component scores in 0-10 space ===
        
        # Impact: average of 4 dimensions (0-10)
        impact_10 = (self.industry_impact + self.consumer_impact + 
                     self.actionability + self.risk_urgency) / 4
        
        # Gravity: novelty weighted 2x, then averaged (0-10)
        gravity_10 = (self.novelty * 2 + self.technical_depth + 
                      self.second_order_effects + self.builder_relevance + 
                      self.entertainment_value) / 6
        
        # Signals: average of 3 dimensions (0-10)  
        signals_10 = (self.signal_to_noise + self.viral_potential + 
                      self.early_trend_signal) / 3
        
        # === Step 2: Weighted sum (normalized to 0-10) ===
        # Weights: Impact 25%, Gravity 35%, Signals 20% (total 80%)
        # Normalize by dividing by weight sum to get true 0-10 range
        weight_sum = 0.25 + 0.35 + 0.20  # 0.80
        raw_10 = (impact_10 * 0.25 + gravity_10 * 0.35 + signals_10 * 0.20) / weight_sum
        
        # === Step 3: Quality penalty (capped at -1.5 points) ===
        # Only penalize if quality flags are above baseline (3 = neutral)
        quality_avg = (self.pr_fluff + self.speculation + 
                       self.vagueness + self.sponsored) / 4
        # Linear penalty: 3 = 0, 10 = 1.5
        penalty = max(0, (quality_avg - 3) / 7) * 1.5
        
        penalized_10 = max(1, raw_10 - penalty)
        
        # === Step 4: Sigmoid stretch for better separation ===
        # Centers around 5.0 (average expected score)
        # Stretches differences in 3-7 range for better discrimination
        centered = (penalized_10 - 5.0) / 1.8  # Wider spread
        sigmoid = 1 / (1 + math.exp(-centered))
        
        # === Step 5: Tail boost for top-end separation ===
        # Convex transform: widens high scores without lifting junk
        # final = 10 * (sigmoid ** 1.15) maps 0-1 with slight top boost
        boosted = sigmoid ** 1.12  # Mild boost to avoid extreme separation
        final = 1 + boosted * 9  # Map 0-1 to 1-10
        
        return round(max(1, min(10, final)), 2)
    
    def check_hard_gates(self) -> tuple[bool, str]:
        """
        Check hard gates for obvious spam/low-quality content.
        
        Returns:
            (should_suppress, reason)
        """
        # Sponsored content gate
        if self.sponsored >= 7:
            return True, "sponsored_content"
        
        # PR fluff gate
        if self.pr_fluff >= 8:
            return True, "pr_fluff"
        
        # Combined low-quality gate (but allow high-impact override)
        if self.novelty < 4 and self.signal_to_noise < 4:
            # High-impact override: important stories get through even if "widely reported"
            if not self.has_high_impact_override():
                return True, "low_novelty_low_signal"
        
        return False, ""
    
    def has_high_impact_override(self) -> bool:
        """
        Check if article qualifies for high-impact override.
        
        Rule: If impact >= 7 and quality_flags <= 4, allow pass even if novelty borderline.
        This prevents filtering "important but mainstream" stories.
        """
        impact_avg = (self.industry_impact + self.consumer_impact + 
                      self.actionability + self.risk_urgency) / 4
        quality_avg = (self.pr_fluff + self.speculation + 
                       self.vagueness + self.sponsored) / 4
        
        return impact_avg >= 7 and quality_avg <= 4
    
    def should_pass_novelty_gate(self, threshold: float = 4.0) -> bool:
        """
        Check if article should pass novelty gate, with high-impact override.
        
        Returns True if:
        - novelty >= threshold, OR
        - high-impact override applies (important but mainstream)
        """
        if self.novelty >= threshold:
            return True
        
        # Allow borderline novelty (3-4) if high impact + clean quality
        if self.novelty >= 3 and self.has_high_impact_override():
            return True
        
        return False
    
    @property
    def impact_score(self) -> float:
        return round((self.industry_impact + self.consumer_impact + 
                     self.actionability + self.risk_urgency) / 4, 2)
    
    @property
    def gravity_score(self) -> float:
        return round((self.novelty + self.technical_depth + 
                     self.second_order_effects + self.builder_relevance + 
                     self.entertainment_value) / 5, 2)
    
    @property
    def signal_score(self) -> float:
        return round((self.signal_to_noise + self.viral_potential + 
                     self.early_trend_signal) / 3, 2)
    
    @property
    def quality_score(self) -> float:
        """Lower is better for quality flags"""
        return round((self.pr_fluff + self.speculation + 
                     self.vagueness + self.sponsored) / 4, 2)


class GravityEngine:
    """
    AI-powered 16-dimensional content scoring engine.
    
    Uses Claude/GPT to evaluate articles like a virtual editorial team,
    scoring across impact, novelty, trends, and quality dimensions.
    """
    
    # Novelty gate threshold - articles below this are filtered
    NOVELTY_GATE_THRESHOLD = 4.0
    
    # Minimum final score to include
    MIN_SCORE_THRESHOLD = 5.0
    
    # Quality flag threshold - high values trigger warnings
    QUALITY_FLAG_THRESHOLD = 6.0
    
    def __init__(
        self,
        llm_client: LLMClient = None,
        novelty_gate: bool = True,
        quality_filter: bool = True,
        reprint_detection: bool = True,
        batch_size: int = 5
    ):
        """
        Initialize Gravity Engine.
        
        Args:
            llm_client: LLM client for scoring
            novelty_gate: Enable novelty filtering (drop low-novelty content)
            quality_filter: Enable quality flag filtering
            reprint_detection: Enable reprint/duplicate detection and penalty
            batch_size: Articles per LLM call
        """
        self.llm_client = llm_client or LLMClient()
        self.novelty_gate = novelty_gate
        self.quality_filter = quality_filter
        self.reprint_detection = reprint_detection
        self.batch_size = batch_size
        
        # Initialize reprint detector if enabled
        self.reprint_detector = None
        if reprint_detection:
            self.reprint_detector = ReprintDetector()
            if not self.reprint_detector.available:
                logger.warning("Reprint detection disabled - missing dependencies")
                self.reprint_detection = False
        
        logger.info(
            f"Gravity Engine initialized "
            f"(novelty_gate={novelty_gate}, quality_filter={quality_filter}, "
            f"reprint_detection={self.reprint_detection})"
        )
    
    def _build_scoring_prompt(self) -> str:
        """Build the 16-dimension scoring prompt."""
        return """You are an AI editorial director evaluating content with the sophistication of a Bloomberg or Techmeme editor.

Score this article across 16 dimensions (1-10 scale):

## IMPACT (How significant is this?)
1. **industry_impact**: Importance for tech/business sector (10=industry-changing)
2. **consumer_impact**: Importance for end-users/society (10=affects millions)
3. **actionability**: Does it call for action/response? (10=urgent action needed)
4. **risk_urgency**: Warns of urgent issues/threats? (10=critical warning)

## GRAVITY (Intellectual value)
5. **novelty**: NEW information or insights? (10=breaking/original, 1=rehashed) ⚠️ CRITICAL
6. **technical_depth**: Level of technical substance (10=deep technical analysis)
7. **second_order_effects**: Broader consequences/implications (10=far-reaching effects)
8. **builder_relevance**: Useful to developers/builders? (10=immediately actionable)
9. **entertainment_value**: Interesting/buzzworthy? (10=highly engaging)

## SIGNALS (Trend indicators)
10. **signal_to_noise**: Real substance vs hype (10=all signal, 1=all noise)
11. **viral_potential**: Likely to spread/generate discussion (10=will dominate feeds)
12. **early_trend_signal**: Hints at emerging trend? (10=early indicator of major shift)

## QUALITY FLAGS (Higher = WORSE)
13. **pr_fluff**: Marketing spin detected (10=pure PR, 1=no spin)
14. **speculation**: Unsupported claims (10=baseless speculation, 1=well-sourced)
15. **vagueness**: Lack of concreteness (10=no specifics, 1=concrete details)
16. **sponsored**: Paid/sponsored content (10=obvious ad, 1=clearly independent)

## Calibration Anchors (use these as reference points):

**Score 3** = Press release reprint, opinion rehash, no new facts
  Example: "AI company announces they're 'committed to safety'" (vague, no specifics)

**Score 5** = Solid reporting with real information, standard news
  Example: "Company X raised $50M Series B, plans to expand to Europe"

**Score 7** = Strong technical analysis OR significant implications
  Example: "Detailed breakdown of new model architecture with benchmarks and methodology"

**Score 9** = Genuinely new capability, major policy shift, or industry breakthrough
  Example: "First working demonstration of [new capability] with reproducible results"

## Special Rules:
- NOVELTY GATE: If novelty < 4, mark passes_novelty_gate=false (rehashed content)
- Average article should score 5-6 on positive dimensions (not 4-5)
- Exceptional content (8-10) should be uncommon but not rare (~10-15% of good articles)
- Be skeptical of PR and hype, but don't penalize genuine product news

Return JSON:
{
  "scores": {
    "industry_impact": 7,
    "consumer_impact": 5,
    "actionability": 4,
    "risk_urgency": 3,
    "novelty": 8,
    "technical_depth": 6,
    "second_order_effects": 7,
    "builder_relevance": 5,
    "entertainment_value": 6,
    "signal_to_noise": 7,
    "viral_potential": 6,
    "early_trend_signal": 5,
    "pr_fluff": 2,
    "speculation": 3,
    "vagueness": 2,
    "sponsored": 1
  },
  "passes_novelty_gate": true,
  "editorial_verdict": "Strong technical story with genuine news value",
  "key_insight": "One sentence summary of the key takeaway"
}"""

    def _build_article_text(self, article: Dict[str, Any]) -> str:
        """Format article for evaluation."""
        title = article.get('title', 'Untitled')
        source = article.get('source', 'Unknown')
        content = article.get('content', article.get('summary', ''))[:2000]
        published = article.get('published_date', article.get('published_at', 'Unknown'))
        
        return f"""**Title**: {title}
**Source**: {source}
**Published**: {published}

**Content**:
{content}"""

    def score_article(self, article: Dict[str, Any]) -> Tuple[GravityScore, float]:
        """
        Score a single article across all 16 dimensions.
        
        Returns:
            Tuple of (GravityScore, final_score)
        """
        prompt = self._build_scoring_prompt()
        article_text = self._build_article_text(article)
        
        try:
            # Use chat() method which is standard in briefAI's LLM client
            response = self.llm_client.chat(
                system_prompt=prompt,
                user_message=article_text,
                temperature=0.3  # Low temp for consistent scoring
            )
            
            # Parse response
            if isinstance(response, str):
                # Try to extract JSON from response
                import re
                json_match = re.search(r'\{[\s\S]*\}', response)
                if json_match:
                    data = json.loads(json_match.group())
                else:
                    raise ValueError("No JSON found in response")
            else:
                data = response
            
            scores = data.get('scores', {})
            
            gravity_score = GravityScore(
                # Impact
                industry_impact=scores.get('industry_impact', 5),
                consumer_impact=scores.get('consumer_impact', 5),
                actionability=scores.get('actionability', 5),
                risk_urgency=scores.get('risk_urgency', 5),
                # Gravity
                novelty=scores.get('novelty', 5),
                technical_depth=scores.get('technical_depth', 5),
                second_order_effects=scores.get('second_order_effects', 5),
                builder_relevance=scores.get('builder_relevance', 5),
                entertainment_value=scores.get('entertainment_value', 5),
                # Signals
                signal_to_noise=scores.get('signal_to_noise', 5),
                viral_potential=scores.get('viral_potential', 5),
                early_trend_signal=scores.get('early_trend_signal', 5),
                # Quality flags
                pr_fluff=scores.get('pr_fluff', 2),
                speculation=scores.get('speculation', 2),
                vagueness=scores.get('vagueness', 2),
                sponsored=scores.get('sponsored', 2),
                # Meta
                passes_novelty_gate=data.get('passes_novelty_gate', True),
                editorial_verdict=data.get('editorial_verdict', ''),
                key_insight=data.get('key_insight', '')
            )
            
            # Apply novelty gate (with high-impact override)
            gravity_score.passes_novelty_gate = gravity_score.should_pass_novelty_gate(
                self.NOVELTY_GATE_THRESHOLD
            )
            
            final_score = gravity_score.compute_final_score()
            
            return gravity_score, final_score
            
        except Exception as e:
            logger.error(f"Gravity scoring failed: {e}")
            return GravityScore(), 5.0

    def score_batch(
        self,
        articles: List[Dict[str, Any]],
        parallel: bool = False,
        add_percentile: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Score a batch of articles with Gravity Engine.
        
        Args:
            articles: List of article dicts
            parallel: Use parallel processing (TODO)
            add_percentile: Add percentile ranking within batch
        
        Returns:
            Articles with gravity_score, gravity_percentile, and gravity_details added
        """
        logger.info(f"Gravity Engine scoring {len(articles)} articles...")
        
        all_scored = []  # Keep all for percentile calc
        passed = 0
        filtered_novelty = 0
        filtered_quality = 0
        filtered_hard_gate = 0
        
        for i, article in enumerate(articles):
            logger.debug(f"  Scoring [{i+1}/{len(articles)}]: {article.get('title', '')[:50]}...")
            
            gravity_score, final_score = self.score_article(article)
            
            # Check hard gates first
            should_suppress, gate_reason = gravity_score.check_hard_gates()
            
            # Coverage validation: check if single-source / low coverage
            # Tag as unvalidated_early if needs more corroboration
            source_count = article.get('source_count', 1)
            related_count = article.get('related_count', 0)
            is_validated = source_count > 1 or related_count > 0
            coverage_status = 'validated' if is_validated else 'unvalidated_early'
            
            # Add scores to article
            article['gravity_score'] = final_score
            article['gravity_details'] = {
                'impact': gravity_score.impact_score,
                'gravity': gravity_score.gravity_score,
                'signals': gravity_score.signal_score,
                'quality_flags': gravity_score.quality_score,
                'novelty': gravity_score.novelty,
                'editorial_verdict': gravity_score.editorial_verdict,
                'key_insight': gravity_score.key_insight,
                'passes_novelty_gate': gravity_score.passes_novelty_gate,
                'hard_gate_triggered': should_suppress,
                'hard_gate_reason': gate_reason,
                'high_impact_override': gravity_score.has_high_impact_override(),
                'coverage_status': coverage_status,
                'full_scores': asdict(gravity_score)
            }
            
            all_scored.append(article)
            
            # Apply hard gates (most severe)
            if should_suppress:
                article['gravity_filtered'] = f'hard_gate:{gate_reason}'
                filtered_hard_gate += 1
                continue
            
            # Apply novelty gate (respects high-impact override)
            if self.novelty_gate and not gravity_score.passes_novelty_gate:
                # Log if high-impact override was checked but didn't apply
                if gravity_score.novelty >= 3:
                    logger.debug(f"    Novelty gate filtered (novelty={gravity_score.novelty}, no impact override)")
                article['gravity_filtered'] = 'novelty_gate'
                filtered_novelty += 1
                continue
            
            # Apply quality filter (soft gate already applied in score)
            if self.quality_filter and gravity_score.quality_score > self.QUALITY_FLAG_THRESHOLD:
                article['gravity_filtered'] = 'quality_flags'
                filtered_quality += 1
                continue
            
            passed += 1
        
        # === Reprint Detection (batch-level) ===
        # Detect duplicates/reprints and apply penalty
        if self.reprint_detection and self.reprint_detector and len(all_scored) > 1:
            logger.debug("Running reprint detection...")
            reprint_info = self.reprint_detector.detect_reprints(all_scored)
            
            for i, article in enumerate(all_scored):
                info = reprint_info.get(i, {})
                penalty = info.get('reprint_penalty', 0)
                
                # Add reprint info to gravity_details
                article['gravity_details']['reprint_info'] = {
                    'duplicate_ratio': info.get('duplicate_ratio', 0),
                    'source_entropy': info.get('source_entropy', 1.0),
                    'unique_source_count': info.get('unique_source_count', 1),
                    'similar_count': len(info.get('similar_indices', [])),
                    'reprint_penalty': penalty
                }
                
                # Apply penalty to score (unless high impact)
                if penalty > 0:
                    # Don't penalize high-impact stories heavily
                    impact = article['gravity_details'].get('impact', 5)
                    if impact >= 7:
                        penalty *= 0.3  # Reduce penalty for important stories
                    
                    old_score = article['gravity_score']
                    article['gravity_score'] = round(max(1, old_score * (1 - penalty)), 2)
                    logger.debug(
                        f"  Reprint penalty: {article.get('title', '')[:40]}... "
                        f"{old_score} -> {article['gravity_score']} (-{penalty*100:.0f}%)"
                    )
        
        # Compute percentile rankings within batch
        if add_percentile and all_scored:
            scores = [a.get('gravity_score', 0) for a in all_scored]
            for article in all_scored:
                score = article.get('gravity_score', 0)
                # Percentile = % of articles this score beats
                lower_count = sum(1 for s in scores if s < score)
                article['gravity_percentile'] = round(100 * lower_count / len(scores), 1)
        
        # Filter to only passed articles
        scored_articles = [a for a in all_scored if 'gravity_filtered' not in a]
        
        # Sort by gravity score (post-penalty)
        scored_articles.sort(key=lambda x: x.get('gravity_score', 0), reverse=True)
        
        logger.info(
            f"Gravity Engine complete: {passed} passed, "
            f"{filtered_hard_gate} hard-gated, "
            f"{filtered_novelty} filtered (novelty), {filtered_quality} filtered (quality)"
        )
        
        return scored_articles

    def get_editorial_summary(self, scored_articles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Generate editorial summary of scored content.
        
        Returns summary with top stories, trends, and quality breakdown.
        """
        if not scored_articles:
            return {"error": "No articles to summarize"}
        
        # Top stories by gravity score
        top_stories = scored_articles[:10]
        
        # Stories with high early_trend_signal
        trend_signals = [
            a for a in scored_articles 
            if a.get('gravity_details', {}).get('full_scores', {}).get('early_trend_signal', 0) >= 7
        ]
        
        # Stories with high actionability
        actionable = [
            a for a in scored_articles
            if a.get('gravity_details', {}).get('full_scores', {}).get('actionability', 0) >= 7
        ]
        
        # Average scores
        avg_gravity = sum(a.get('gravity_score', 0) for a in scored_articles) / len(scored_articles)
        avg_novelty = sum(
            a.get('gravity_details', {}).get('novelty', 5) 
            for a in scored_articles
        ) / len(scored_articles)
        
        return {
            'total_scored': len(scored_articles),
            'average_gravity_score': round(avg_gravity, 2),
            'average_novelty': round(avg_novelty, 2),
            'top_stories': [
                {
                    'title': a.get('title'),
                    'score': a.get('gravity_score'),
                    'insight': a.get('gravity_details', {}).get('key_insight', '')
                }
                for a in top_stories[:5]
            ],
            'trend_signals': len(trend_signals),
            'actionable_items': len(actionable),
            'generated_at': datetime.now().isoformat()
        }


def integrate_with_news_evaluator():
    """
    Integration guide for existing NewsEvaluator.
    
    The Gravity Engine can be used as:
    1. A replacement for BatchEvaluator (Tier 2)
    2. An additional scoring layer after NewsEvaluator
    3. A standalone scorer for high-value content
    
    Example integration:
    
    ```python
    from modules.gravity_engine import GravityEngine
    from modules.news_evaluator import NewsEvaluator
    
    # Option 1: Add gravity scoring to existing pipeline
    evaluator = NewsEvaluator()
    gravity = GravityEngine()
    
    # Evaluate with existing system
    evaluated = evaluator.evaluate(articles, categories)
    
    # Add gravity scores to top candidates
    top_candidates = [a for a in evaluated if a.get('weighted_score', 0) >= 6]
    gravity_scored = gravity.score_batch(top_candidates)
    
    # Option 2: Replace Tier 2 batch evaluator
    # In pipeline/orchestrator.py, swap BatchEvaluator for GravityEngine
    ```
    """
    pass


if __name__ == "__main__":
    # Test the Gravity Engine
    from utils.llm_client_enhanced import LLMClient
    
    engine = GravityEngine()
    
    test_article = {
        'title': 'OpenAI releases GPT-5 with 10x performance improvement',
        'source': 'TechCrunch',
        'content': '''OpenAI has announced GPT-5, claiming a 10x improvement in reasoning 
        capabilities over GPT-4. The new model demonstrates breakthrough performance on 
        complex mathematical proofs and code generation tasks. CEO Sam Altman stated this 
        represents a "significant step toward AGI." The model will be available via API 
        starting next month with pricing at $0.03 per 1K tokens.''',
        'published_date': '2026-02-09'
    }
    
    score, final = engine.score_article(test_article)
    print(f"\nGravity Score: {final}")
    print(f"Impact: {score.impact_score}")
    print(f"Gravity: {score.gravity_score}")
    print(f"Signals: {score.signal_score}")
    print(f"Quality Flags: {score.quality_score}")
    print(f"Novelty Gate: {'PASS' if score.passes_novelty_gate else 'FAIL'}")
    print(f"Verdict: {score.editorial_verdict}")
