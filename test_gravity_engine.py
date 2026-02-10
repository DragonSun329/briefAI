#!/usr/bin/env python3
"""
Test Gravity Engine on today's scraped TechMeme articles.
"""

import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from loguru import logger
from modules.gravity_engine import GravityEngine
from modules.story_clustering import StoryClustering
from modules.gravity_integration import GravityPipelineIntegration

# Load today's TechMeme data
DATA_FILE = Path(__file__).parent / "data" / "news_signals" / "techmeme_2026-02-09.json"


def load_articles():
    """Load articles from TechMeme scrape."""
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Convert to format expected by Gravity Engine
    articles = []
    for story in data.get('stories', [])[:10]:  # Test with top 10
        articles.append({
            'title': story.get('title', ''),
            'source': story.get('source', 'Unknown'),
            'url': story.get('url', ''),
            'content': story.get('title', ''),  # TechMeme only has titles
            'ai_relevance': story.get('ai_relevance', 0),
            'related_count': story.get('related_count', 0)
        })
    
    return articles


def test_gravity_scoring():
    """Test Gravity Engine scoring on articles."""
    print("=" * 70)
    print("GRAVITY ENGINE TEST")
    print(f"Testing on TechMeme articles from {DATA_FILE.name}")
    print("=" * 70)
    
    articles = load_articles()
    print(f"\nLoaded {len(articles)} articles\n")
    
    # Initialize Gravity Engine with reprint detection
    engine = GravityEngine(
        novelty_gate=True,
        quality_filter=True,
        reprint_detection=True
    )
    
    # Score each article individually first (for detailed output)
    results = []
    for i, article in enumerate(articles):
        print(f"\n[{i+1}/{len(articles)}] {article['title'][:60]}...")
        print(f"    Source: {article['source']}")
        
        try:
            score, final = engine.score_article(article)
            
            results.append({
                'title': article['title'],
                'source': article['source'],
                'gravity_score': final,
                'impact': score.impact_score,
                'gravity': score.gravity_score,
                'signals': score.signal_score,
                'quality_flags': score.quality_score,
                'novelty': score.novelty,
                'novelty_gate': 'PASS' if score.passes_novelty_gate else 'FAIL',
                'verdict': score.editorial_verdict,
                'insight': score.key_insight
            })
            
            print(f"    -> Gravity Score: {final}")
            print(f"    -> Impact: {score.impact_score} | Gravity: {score.gravity_score} | Signals: {score.signal_score}")
            print(f"    -> Novelty: {score.novelty} | Quality Flags: {score.quality_score}")
            print(f"    -> Novelty Gate: {'[PASS]' if score.passes_novelty_gate else '[FAIL]'}")
            if score.editorial_verdict:
                print(f"    -> Verdict: {score.editorial_verdict[:80]}...")
                
        except Exception as e:
            print(f"    -> ERROR: {e}")
            results.append({
                'title': article['title'],
                'error': str(e)
            })
    
    # Now run batch scoring (includes reprint detection)
    print("\n" + "-" * 70)
    print("BATCH SCORING (with reprint detection)")
    print("-" * 70)
    
    # Reload articles for batch scoring
    batch_articles = load_articles()
    scored_batch = engine.score_batch(batch_articles)
    
    # Show reprint info
    print(f"\nReprint Detection Results:")
    for article in batch_articles:
        reprint = article.get('gravity_details', {}).get('reprint_info', {})
        if reprint.get('duplicate_ratio', 0) > 0:
            print(f"  - {article['title'][:50]}...")
            print(f"    duplicate_ratio: {reprint.get('duplicate_ratio')}")
            print(f"    source_entropy: {reprint.get('source_entropy')}")
            print(f"    penalty: {reprint.get('reprint_penalty')}")
    
    if not any(a.get('gravity_details', {}).get('reprint_info', {}).get('duplicate_ratio', 0) > 0 
               for a in batch_articles):
        print("  No reprints detected (all unique stories)")
    
    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    valid_results = [r for r in results if 'gravity_score' in r]
    
    if valid_results:
        # Sort by gravity score
        valid_results.sort(key=lambda x: x['gravity_score'], reverse=True)
        
        print(f"\nTop Stories by Gravity Score:")
        for i, r in enumerate(valid_results[:5]):
            print(f"  {i+1}. [{r['gravity_score']:.1f}] {r['title'][:55]}...")
            print(f"     {r['verdict'][:70]}..." if r.get('verdict') else "")
        
        # Stats
        avg_score = sum(r['gravity_score'] for r in valid_results) / len(valid_results)
        avg_novelty = sum(r['novelty'] for r in valid_results) / len(valid_results)
        passed_gate = sum(1 for r in valid_results if r['novelty_gate'] == 'PASS')
        
        print(f"\nStats:")
        print(f"  Average Gravity Score: {avg_score:.2f}")
        print(f"  Average Novelty: {avg_novelty:.2f}")
        print(f"  Passed Novelty Gate: {passed_gate}/{len(valid_results)}")
    
    # Save results
    output_file = Path(__file__).parent / "data" / "gravity_test_results.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            'test_date': datetime.now().isoformat(),
            'articles_tested': len(articles),
            'results': results
        }, f, indent=2, ensure_ascii=False)
    
    print(f"\nResults saved to: {output_file}")
    
    return results


def test_clustering():
    """Test story clustering with content enrichment."""
    print("\n" + "=" * 70)
    print("STORY CLUSTERING TEST")
    print("=" * 70)
    
    from modules.story_clustering import StoryClustering, ClusterMode
    from utils.content_enricher import ContentEnricher, diagnose_enrichment
    
    # Load articles
    articles = load_articles()
    
    # Enrich content (fetch article bodies)
    print("\nEnriching articles (fetching content)...")
    enricher = ContentEnricher()
    if enricher.available:
        articles = enricher.enrich_batch(articles, max_workers=3)
        
        # Show enrichment stats
        stats = diagnose_enrichment(articles)
        print(f"  Enriched: {stats['enriched']}/{stats['total']} ({stats['enriched_pct']}%)")
        print(f"  Has body (>200 chars): {stats['has_body_200']}")
        print(f"  Avg body length: {stats['avg_body_length']}")
    else:
        print("  Content enricher not available")
    
    # Test EVENT mode (strict, requires enriched content)
    print("\n--- EVENT MODE (strict, threshold=0.86) ---")
    clustering = StoryClustering(mode=ClusterMode.EVENT)
    
    if not clustering.available:
        print("Clustering not available - missing dependencies")
        return
    
    clusters, singletons, debug = clustering.cluster_stories(articles, return_debug=True)
    
    print(f"\nSimilarity stats:")
    print(f"  p50={debug['similarity_distribution']['p50']:.2f}, "
          f"p90={debug['similarity_distribution']['p90']:.2f}, "
          f"max={debug['similarity_distribution']['max']:.2f}")
    print(f"  Pairs >= {debug['clustering']['threshold']}: {debug['clustering']['pairs_above_threshold']}")
    
    print(f"\nClusters found: {len(clusters)}")
    for c in clusters:
        print(f"\n  [Cluster] {c.canonical_story['title'][:50]}...")
        print(f"     Sources: {', '.join(c.sources)}")
        print(f"     Size: {c.cluster_size}")
    
    # Test TOPIC mode (loose)
    print("\n--- TOPIC MODE (loose, threshold=0.68) ---")
    clustering_topic = StoryClustering(mode=ClusterMode.TOPIC)
    clusters_t, singletons_t, debug_t = clustering_topic.cluster_stories(articles, return_debug=True)
    
    print(f"  Pairs >= {debug_t['clustering']['threshold']}: {debug_t['clustering']['pairs_above_threshold']}")
    print(f"  Clusters found: {len(clusters_t)}")
    
    print(f"\nUnique stories: {len(singletons)}")
    for s in singletons[:5]:
        print(f"  - {s['title'][:60]}...")


if __name__ == "__main__":
    test_gravity_scoring()
    test_clustering()
