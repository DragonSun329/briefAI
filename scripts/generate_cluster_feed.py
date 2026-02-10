#!/usr/bin/env python3
"""
Generate Cluster Feed - Gravity Engine v2.1

Loads today's articles, clusters them, builds dossiers,
and produces a ranked feed JSON.

Usage:
    python scripts/generate_cluster_feed.py
    python scripts/generate_cluster_feed.py --date 2026-02-09

Output:
    data/gravity/cluster_feed_YYYY-MM-DD.json
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
from modules.gravity_engine import GravityEngine
from utils.content_enricher import ContentEnricher
from utils.cluster_ranker import rank_feed, print_feed_summary


def load_articles(date_str: str = None) -> list:
    """
    Load articles from TechMeme scrape.
    
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
    
    logger.info(f"Loading articles from {target_file}")
    
    with open(target_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    articles = []
    for story in data.get('stories', []):
        articles.append({
            'title': story.get('title', ''),
            'source': story.get('source', 'Unknown'),
            'url': story.get('url', ''),
            'content': story.get('title', ''),
            'ai_relevance': story.get('ai_relevance', 0),
            'related_count': story.get('related_count', 0),
            'scraped_at': story.get('scraped_at'),
        })
    
    return articles


def enrich_articles(articles: list) -> list:
    """Enrich articles with body text."""
    enricher = ContentEnricher()
    
    if not enricher.available:
        logger.warning("Content enricher not available, skipping enrichment")
        return articles
    
    logger.info(f"Enriching {len(articles)} articles...")
    return enricher.enrich_batch(articles, max_workers=3)


def score_articles(articles: list) -> list:
    """Score articles with Gravity Engine."""
    engine = GravityEngine(
        novelty_gate=True,
        quality_filter=True,
        reprint_detection=False,  # Skip for speed in feed gen
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
            logger.debug(f"  [{i+1}/{len(articles)}] {article['title'][:40]}... -> {final_score:.2f}")
        except Exception as e:
            logger.warning(f"Failed to score article: {e}")
            article['gravity_score'] = 5.0
            article['gravity_details'] = {}
    
    return articles


def cluster_articles(articles: list) -> tuple:
    """Cluster articles using Story Clustering."""
    clustering = StoryClustering(
        mode=ClusterMode.TOPIC,
        auto_threshold=True,
        enforce_temporal_locality=True,
        max_topic_age_days=7,
    )
    
    if not clustering.available:
        logger.warning("Clustering not available")
        return [], articles
    
    logger.info(f"Clustering {len(articles)} articles...")
    clusters, singletons, debug = clustering.cluster_stories(articles, return_debug=True)
    
    logger.info(f"  Found {len(clusters)} clusters, {len(singletons)} singletons")
    logger.info(f"  Similarity: p50={debug['similarity_distribution']['p50']:.2f}, "
                f"max={debug['similarity_distribution']['max']:.2f}")
    
    return clusters, singletons


def main():
    parser = argparse.ArgumentParser(description='Generate cluster-ranked feed')
    parser.add_argument('--date', type=str, help='Date string YYYY-MM-DD')
    parser.add_argument('--skip-enrich', action='store_true', help='Skip content enrichment')
    parser.add_argument('--skip-score', action='store_true', help='Skip gravity scoring')
    parser.add_argument('--limit', type=int, default=50, help='Max articles to process')
    args = parser.parse_args()
    
    date_str = args.date or datetime.now().strftime('%Y-%m-%d')
    
    print(f"\n{'='*60}")
    print(f"GENERATING CLUSTER FEED - {date_str}")
    print(f"{'='*60}\n")
    
    # Load articles
    articles = load_articles(date_str)
    if not articles:
        print("No articles found!")
        return 1
    
    # Limit for testing
    articles = articles[:args.limit]
    print(f"Processing {len(articles)} articles\n")
    
    # Enrich
    if not args.skip_enrich:
        articles = enrich_articles(articles)
    
    # Score
    if not args.skip_score:
        articles = score_articles(articles)
    
    # Cluster
    clusters, singletons = cluster_articles(articles)
    
    # Build ranked feed
    logger.info("Building ranked feed...")
    feed = rank_feed(
        clusters=clusters,
        singletons=singletons,
        target_date=date_str,
        scorer_fn=None,  # Use canonical gravity scores
    )
    
    # Save feed
    output_dir = Path(__file__).parent.parent / "data" / "gravity"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"cluster_feed_{date_str}.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(feed, f, indent=2, ensure_ascii=False, default=str)
    
    logger.info(f"Feed saved to {output_file}")
    
    # Print summary
    print_feed_summary(feed, top_n=5)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
