#!/usr/bin/env python3
"""
Generate Dual Feed - Gravity Engine v2.2

Expands TechMeme stories into article candidates, enriches and scores them,
then runs dual clustering (EVENT + THEME) to produce a ranked dual feed.

Key features:
- TechMeme related-link expansion (multi-source coverage)
- Dual clustering: EVENT (tight) + THEME (loose + gates)
- Ranked feeds for both event-level and theme-level stories

Usage:
    python scripts/generate_dual_feed.py
    python scripts/generate_dual_feed.py --date 2026-02-09
    python scripts/generate_dual_feed.py --limit 40 --max-related 8
    python scripts/generate_dual_feed.py --top-k 30 --skip-enrich

Output:
    data/gravity/dual_feed_YYYY-MM-DD.json
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from modules.story_clustering import StoryClustering, ClusterMode
from utils.techmeme_expander import (
    expand_techmeme_stories,
    filter_ai_relevant_candidates,
)
from utils.cluster_ranker import build_dual_feed, print_dual_feed_summary


def load_techmeme_stories(date_str: str = None) -> list:
    """
    Load raw TechMeme stories from scrape data.
    
    Falls back to latest available file if date not found.
    """
    data_dir = Path(__file__).parent.parent / "data" / "news_signals"
    
    if date_str:
        target_file = data_dir / f"techmeme_{date_str}.json"
    else:
        date_str = datetime.now().strftime('%Y-%m-%d')
        target_file = data_dir / f"techmeme_{date_str}.json"
    
    if not target_file.exists():
        # Find latest file
        files = sorted(data_dir.glob("techmeme_*.json"), reverse=True)
        if files:
            target_file = files[0]
            logger.info(f"Using latest file: {target_file.name}")
        else:
            logger.error("No TechMeme data files found")
            return []
    
    logger.info(f"Loading TechMeme stories from {target_file}")
    
    with open(target_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    return data.get('stories', [])


def enrich_articles(articles: list) -> list:
    """Enrich articles with body text using trafilatura."""
    try:
        from utils.content_enricher import ContentEnricher
        enricher = ContentEnricher()
        
        if not enricher.available:
            logger.warning("Content enricher not available, skipping enrichment")
            return articles
        
        logger.info(f"Enriching {len(articles)} articles...")
        return enricher.enrich_batch(articles, max_workers=3)
        
    except ImportError:
        logger.warning("ContentEnricher not available, skipping enrichment")
        return articles


def score_articles(articles: list) -> list:
    """Score articles with Gravity Engine."""
    try:
        from modules.gravity_engine import GravityEngine
        
        engine = GravityEngine(
            novelty_gate=True,
            quality_filter=True,
            reprint_detection=False,  # Skip for speed
        )
        
        logger.info(f"Scoring {len(articles)} articles with Gravity Engine...")
        
        for i, article in enumerate(articles):
            try:
                score_obj, final_score = engine.score_article(article)
                article['gravity_score'] = final_score
                article['gravity_details'] = {
                    'impact': score_obj.impact_score,
                    'gravity': score_obj.gravity_score,
                    'signals': score_obj.signal_score,
                    'quality_flags': score_obj.quality_score,
                    'novelty': score_obj.novelty,
                    'editorial_verdict': score_obj.editorial_verdict,
                    'key_insight': score_obj.key_insight,
                    'passes_novelty_gate': score_obj.passes_novelty_gate,
                }
                if (i + 1) % 10 == 0:
                    logger.debug(f"  Scored {i+1}/{len(articles)} articles")
            except Exception as e:
                logger.warning(f"Failed to score article: {e}")
                article['gravity_score'] = 5.0
                article['gravity_details'] = {}
        
        return articles
        
    except ImportError:
        logger.warning("GravityEngine not available, using default scores")
        for article in articles:
            article['gravity_score'] = article.get('ai_relevance', 0.5) * 10
            article['gravity_details'] = {}
        return articles


def cluster_event(articles: list) -> tuple:
    """
    Run EVENT clustering (tight threshold, same story across sources).
    
    Returns (clusters, singletons, debug_info)
    """
    clustering = StoryClustering(
        mode=ClusterMode.EVENT,
        threshold=0.86,
        auto_threshold=False,
        enforce_temporal_locality=False,  # Events can span days
    )
    
    if not clustering.available:
        logger.warning("EVENT clustering not available")
        return [], articles, {}
    
    logger.info(f"Running EVENT clustering on {len(articles)} articles (threshold=0.86)...")
    clusters, singletons, debug = clustering.cluster_stories(articles, return_debug=True)
    
    logger.info(f"  EVENT: {len(clusters)} clusters, {len(singletons)} singletons")
    
    return clusters, singletons, debug


def cluster_theme(articles: list) -> tuple:
    """
    Run THEME clustering (looser threshold + entity/bucket gates).
    
    Returns (clusters, singletons, debug_info)
    """
    clustering = StoryClustering(
        mode=ClusterMode.TOPIC,
        auto_threshold=True,  # Adapt to batch
        enforce_temporal_locality=True,
        max_topic_age_days=7,
    )
    
    if not clustering.available:
        logger.warning("THEME clustering not available")
        return [], articles, {}
    
    logger.info(f"Running THEME clustering on {len(articles)} articles (adaptive threshold)...")
    clusters, singletons, debug = clustering.cluster_stories(articles, return_debug=True)
    
    logger.info(f"  THEME: {len(clusters)} clusters, {len(singletons)} singletons")
    logger.info(f"  Threshold: {debug['clustering']['threshold']:.3f}")
    
    return clusters, singletons, debug


def main():
    parser = argparse.ArgumentParser(description='Generate dual event/theme ranked feed')
    parser.add_argument('--date', type=str, help='Date string YYYY-MM-DD')
    parser.add_argument('--skip-enrich', action='store_true', help='Skip content enrichment')
    parser.add_argument('--skip-score', action='store_true', help='Skip gravity scoring')
    parser.add_argument('--limit', type=int, default=100, help='Max stories to process')
    parser.add_argument('--max-related', type=int, default=8, help='Max related links per story')
    parser.add_argument('--top-k', type=int, default=30, help='Max items per feed section')
    parser.add_argument('--min-relevance', type=float, default=0.0, 
                        help='Min AI relevance to include (default 0 = all)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    args = parser.parse_args()
    
    date_str = args.date or datetime.now().strftime('%Y-%m-%d')
    
    print(f"\n{'='*60}")
    print(f"GENERATING DUAL FEED - {date_str}")
    print(f"{'='*60}\n")
    
    # 1. Load TechMeme stories
    stories = load_techmeme_stories(date_str)
    if not stories:
        print("No TechMeme stories found!")
        return 1
    
    stories = stories[:args.limit]
    print(f"Loaded {len(stories)} TechMeme stories\n")
    
    # 2. Expand into candidates
    print("Expanding stories into article candidates...")
    candidates = expand_techmeme_stories(stories, max_related=args.max_related)
    print(f"  Expanded to {len(candidates)} candidates")
    
    # Filter by relevance if specified
    if args.min_relevance > 0:
        candidates = filter_ai_relevant_candidates(candidates, args.min_relevance)
        print(f"  Filtered to {len(candidates)} AI-relevant candidates")
    
    if not candidates:
        print("No candidates after expansion!")
        return 1
    
    # 3. Enrich (optional)
    if not args.skip_enrich:
        candidates = enrich_articles(candidates)
    else:
        print("Skipping enrichment")
    
    # 4. Score with Gravity
    if not args.skip_score:
        candidates = score_articles(candidates)
    else:
        print("Skipping scoring, using ai_relevance as proxy")
        for c in candidates:
            c['gravity_score'] = c.get('ai_relevance', 0.5) * 10
            c['gravity_details'] = {}
    
    # 5. Run dual clustering
    print("\n--- Dual Clustering ---")
    
    # EVENT clustering
    clusters_event, singletons_event, debug_event = cluster_event(candidates)
    
    # THEME clustering (independent run from same pool)
    clusters_theme, singletons_theme, debug_theme = cluster_theme(candidates)
    
    # 6. Build dual feed
    print("\n--- Building Dual Feed ---")
    feed = build_dual_feed(
        clusters_event=clusters_event,
        singletons_event=singletons_event,
        clusters_theme=clusters_theme,
        singletons_theme=singletons_theme,
        target_date=date_str,
        candidate_count=len(candidates),
        scorer_fn=None,  # Use canonical gravity scores
        max_related=args.max_related,
        top_k=args.top_k,
    )
    
    # 7. Save feed
    output_dir = Path(__file__).parent.parent / "data" / "gravity"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"dual_feed_{date_str}.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(feed, f, indent=2, ensure_ascii=False, default=str)
    
    logger.info(f"Dual feed saved to {output_file}")
    
    # 8. Print summary
    print_dual_feed_summary(feed, top_n=5)
    
    # Verbose debug info
    if args.verbose:
        print(f"\n--- Debug Info ---")
        print(f"EVENT similarity: p50={debug_event.get('similarity_distribution', {}).get('p50', 0):.3f}, "
              f"max={debug_event.get('similarity_distribution', {}).get('max', 0):.3f}")
        print(f"THEME similarity: p50={debug_theme.get('similarity_distribution', {}).get('p50', 0):.3f}, "
              f"max={debug_theme.get('similarity_distribution', {}).get('max', 0):.3f}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
