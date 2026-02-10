"""
Gravity Engine Integration for briefAI Pipeline

This module provides integration points for the Gravity Engine (16-dimensional 
scoring) and Story Clustering into briefAI's existing pipeline.

Integration Options:
1. Replace Tier 2 BatchEvaluator with Gravity Engine
2. Add as Tier 2.5 between batch eval and full eval
3. Post-process final articles with Gravity scoring

Recommended: Option 2 (additive, preserves existing flow)
"""

import json
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from pathlib import Path

from loguru import logger

# Import Gravity Engine components
from modules.gravity_engine import GravityEngine, GravityScore
from modules.story_clustering import StoryClustering, StoryCluster


class GravityPipelineIntegration:
    """
    Integrates Gravity Engine scoring and clustering into briefAI pipeline.
    
    This is designed to work alongside existing evaluators, adding:
    - 16-dimensional scoring (vs current 5D)
    - Novelty gate filtering
    - Quality flag detection
    - Story clustering
    """
    
    def __init__(
        self,
        llm_client=None,
        enable_gravity_scoring: bool = True,
        enable_clustering: bool = True,
        enable_novelty_gate: bool = True,
        enable_quality_filter: bool = True,
        min_gravity_score: float = 5.0
    ):
        """
        Initialize Gravity integration.
        
        Args:
            llm_client: Shared LLM client
            enable_gravity_scoring: Enable 16D scoring
            enable_clustering: Enable story clustering
            enable_novelty_gate: Filter low-novelty content
            enable_quality_filter: Filter PR fluff/speculation
            min_gravity_score: Minimum score to pass
        """
        self.enable_gravity = enable_gravity_scoring
        self.enable_clustering = enable_clustering
        self.min_score = min_gravity_score
        
        # Initialize components
        if enable_gravity_scoring:
            self.gravity_engine = GravityEngine(
                llm_client=llm_client,
                novelty_gate=enable_novelty_gate,
                quality_filter=enable_quality_filter
            )
            logger.info("Gravity Engine initialized")
        else:
            self.gravity_engine = None
        
        if enable_clustering:
            self.clustering = StoryClustering()
            if not self.clustering.available:
                logger.warning("Story clustering unavailable")
                self.clustering = None
        else:
            self.clustering = None
    
    def process_articles(
        self,
        articles: List[Dict[str, Any]],
        apply_clustering: bool = True
    ) -> Dict[str, Any]:
        """
        Process articles through Gravity Engine pipeline.
        
        Args:
            articles: Pre-filtered articles from existing pipeline
            apply_clustering: Group related stories
        
        Returns:
            Dict with:
            - scored_articles: Articles with gravity scores
            - clusters: Story clusters (if enabled)
            - singletons: Unique stories
            - filtered: Articles that didn't pass gates
            - summary: Editorial summary
        """
        logger.info(f"Gravity processing {len(articles)} articles...")
        
        result = {
            'input_count': len(articles),
            'scored_articles': [],
            'clusters': [],
            'singletons': [],
            'filtered': {
                'novelty_gate': [],
                'quality_flags': [],
                'low_score': []
            },
            'summary': {},
            'processed_at': datetime.now().isoformat()
        }
        
        if not articles:
            return result
        
        # Step 1: Gravity Scoring
        if self.gravity_engine:
            scored = self.gravity_engine.score_batch(articles)
            
            # Separate passed vs filtered
            for article in articles:
                filter_reason = article.get('gravity_filtered')
                if filter_reason:
                    result['filtered'][filter_reason].append({
                        'title': article.get('title'),
                        'source': article.get('source'),
                        'reason': filter_reason,
                        'score': article.get('gravity_score', 0)
                    })
            
            result['scored_articles'] = scored
            
            # Generate editorial summary
            result['summary'] = self.gravity_engine.get_editorial_summary(scored)
        else:
            result['scored_articles'] = articles
        
        # Step 2: Story Clustering
        if self.clustering and apply_clustering and result['scored_articles']:
            clusters, singletons = self.clustering.cluster_stories(
                result['scored_articles']
            )
            result['clusters'] = [c.to_dict() for c in clusters]
            result['singletons'] = singletons
        else:
            result['singletons'] = result['scored_articles']
        
        # Stats
        result['stats'] = {
            'input': len(articles),
            'passed_gravity': len(result['scored_articles']),
            'filtered_novelty': len(result['filtered']['novelty_gate']),
            'filtered_quality': len(result['filtered']['quality_flags']),
            'filtered_score': len(result['filtered']['low_score']),
            'clusters': len(result['clusters']),
            'singletons': len(result['singletons'])
        }
        
        logger.info(
            f"Gravity complete: {result['stats']['passed_gravity']} passed, "
            f"{result['stats']['clusters']} clusters"
        )
        
        return result
    
    def enrich_existing_scores(
        self,
        articles: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Add Gravity scores to articles that already have existing scores.
        
        Merges the 16D Gravity score with existing 5D NewsEvaluator scores.
        """
        if not self.gravity_engine:
            return articles
        
        for article in articles:
            try:
                gravity_score, final_score = self.gravity_engine.score_article(article)
                
                # Add gravity details alongside existing scores
                article['gravity_score'] = final_score
                article['gravity_details'] = {
                    'impact': gravity_score.impact_score,
                    'gravity': gravity_score.gravity_score,
                    'signals': gravity_score.signal_score,
                    'quality_flags': gravity_score.quality_score,
                    'novelty': gravity_score.novelty,
                    'passes_novelty_gate': gravity_score.passes_novelty_gate,
                    'editorial_verdict': gravity_score.editorial_verdict
                }
                
                # Compute combined score (existing + gravity)
                existing_score = article.get('weighted_score', 5)
                combined_score = (existing_score * 0.4 + final_score * 0.6)
                article['combined_score'] = round(combined_score, 2)
                
            except Exception as e:
                logger.warning(f"Gravity scoring failed for '{article.get('title', '')[:30]}': {e}")
                article['gravity_score'] = 5.0
                article['combined_score'] = article.get('weighted_score', 5)
        
        return articles
    
    def get_trend_signals(
        self,
        articles: List[Dict[str, Any]],
        threshold: float = 7.0
    ) -> List[Dict[str, Any]]:
        """
        Extract articles with high early_trend_signal scores.
        
        These are stories that may indicate emerging trends.
        """
        trend_articles = []
        
        for article in articles:
            details = article.get('gravity_details', {})
            full_scores = details.get('full_scores', {})
            
            trend_score = full_scores.get('early_trend_signal', 0)
            if trend_score >= threshold:
                trend_articles.append({
                    'title': article.get('title'),
                    'source': article.get('source'),
                    'trend_score': trend_score,
                    'insight': details.get('key_insight', ''),
                    'gravity_score': article.get('gravity_score', 0)
                })
        
        trend_articles.sort(key=lambda x: x['trend_score'], reverse=True)
        return trend_articles


# -----------------------------------------------------------------------------
# Pipeline Integration Example
# -----------------------------------------------------------------------------

def integrate_gravity_with_news_pipeline():
    """
    Example: How to integrate Gravity Engine into NewsPipeline.
    
    Add this to pipeline/news_pipeline.py after Tier 2 batch evaluation:
    
    ```python
    # After batch evaluation, before full evaluation
    from modules.gravity_integration import GravityPipelineIntegration
    
    gravity = GravityPipelineIntegration(
        llm_client=self._llm_client,
        enable_clustering=True
    )
    
    # Process batch-evaluated articles through Gravity
    gravity_result = gravity.process_articles(tier2_passed)
    
    # Use gravity-scored articles for Tier 3
    tier3_candidates = gravity_result['scored_articles']
    
    # Log filtered content
    logger.info(f"Gravity filtered: {gravity_result['stats']['filtered_novelty']} novelty, "
                f"{gravity_result['stats']['filtered_quality']} quality")
    
    # Story clusters for editorial review
    clusters = gravity_result['clusters']
    ```
    """
    pass


def create_gravity_stage():
    """
    Create a standalone Gravity evaluation stage for the orchestrator.
    
    This can be added to pipeline/orchestrator.py as an additional stage.
    """
    from pipeline.base import StageResult
    
    async def gravity_stage(articles: List[Dict], config: Dict) -> Tuple[List[Dict], StageResult]:
        """Gravity Engine evaluation stage."""
        stage_start = datetime.now()
        
        gravity = GravityPipelineIntegration(
            enable_gravity_scoring=config.get('enable_gravity', True),
            enable_clustering=config.get('enable_clustering', True),
            enable_novelty_gate=config.get('novelty_gate', True),
            min_gravity_score=config.get('min_gravity_score', 5.0)
        )
        
        result = gravity.process_articles(articles)
        
        stage_result = StageResult(
            stage_name="gravity_engine",
            input_count=len(articles),
            output_count=len(result['scored_articles']),
            duration_seconds=(datetime.now() - stage_start).total_seconds(),
            metadata={
                'clusters': len(result['clusters']),
                'filtered_novelty': result['stats']['filtered_novelty'],
                'filtered_quality': result['stats']['filtered_quality']
            }
        )
        
        return result['scored_articles'], stage_result
    
    return gravity_stage


if __name__ == "__main__":
    # Demo the integration
    print("Gravity Engine Integration Demo")
    print("=" * 50)
    
    # Test articles
    test_articles = [
        {
            'title': 'OpenAI releases GPT-5 with breakthrough reasoning',
            'source': 'TechCrunch',
            'content': 'OpenAI has announced GPT-5, their most advanced AI model yet...',
            'weighted_score': 8.0
        },
        {
            'title': 'Company XYZ launches AI-powered solution',
            'source': 'PR Newswire',
            'content': 'Company XYZ is excited to announce their revolutionary AI platform...',
            'weighted_score': 5.0
        }
    ]
    
    # Initialize integration
    gravity = GravityPipelineIntegration()
    
    # Process articles
    result = gravity.process_articles(test_articles)
    
    print(f"\nResults:")
    print(f"  Input: {result['stats']['input']}")
    print(f"  Passed: {result['stats']['passed_gravity']}")
    print(f"  Filtered (novelty): {result['stats']['filtered_novelty']}")
    print(f"  Filtered (quality): {result['stats']['filtered_quality']}")
    print(f"  Clusters: {result['stats']['clusters']}")
