#!/usr/bin/env python3
"""
Rebuild signal_profiles v2 - with recency decay and research scoring.

Improvements:
B) Recency decay: Technical scores decay if entity has no recent activity
C) Research score: Separate score for lab news, press releases, papers

Scoring formula:
- technical (20%) - with activity decay
- company (15%) - Crunchbase presence  
- financial (15%) - funding signals
- media (25%) - news sentiment
- research (25%) - lab news, press releases, papers
"""

import sys
sys.path.insert(0, str(__file__).replace('\\', '/').rsplit('/', 2)[0])

import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict
from loguru import logger

from utils.signal_scorers import MediaScorer


def get_db():
    db_path = Path(__file__).parent.parent / "data" / "signals.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def get_recent_activity_score(conn, entity_id: str, days: int = 30) -> float:
    """
    Check if entity has recent activity (news, mentions, etc.)
    Returns 0-1 score where 1 = very active, 0 = dormant
    """
    c = conn.cursor()
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    
    c.execute("""
        SELECT COUNT(*) as cnt
        FROM signal_observations
        WHERE entity_id = ?
          AND observed_at > ?
    """, (entity_id, cutoff))
    
    count = c.fetchone()['cnt']
    
    # Scale: 0 obs = 0.3, 10+ obs = 1.0
    if count == 0:
        return 0.3  # Dormant penalty
    elif count < 5:
        return 0.5 + (count * 0.1)
    else:
        return min(1.0, 0.7 + (count * 0.03))


def aggregate_media_observations(conn, entity_id: str, days: int = 30, exclude_newsrooms: bool = False) -> dict:
    """Aggregate news observations for an entity."""
    c = conn.cursor()
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    
    source_filter = ""
    if exclude_newsrooms:
        source_filter = "AND ss.name != 'Company Newsrooms'"
    
    c.execute(f"""
        SELECT so.raw_value, so.observed_at, so.raw_data, ss.name as source_name
        FROM signal_observations so
        JOIN signal_sources ss ON so.source_id = ss.id
        WHERE so.entity_id = ?
          AND so.category = 'media'
          AND so.observed_at > ?
          {source_filter}
        ORDER BY so.observed_at DESC
    """, (entity_id, cutoff))
    
    rows = c.fetchall()
    
    if not rows:
        return None
    
    sentiments = []
    sources = defaultdict(int)
    
    for row in rows:
        sentiment = row['raw_value'] or 5.0
        sentiments.append(float(sentiment))
        sources[row['source_name']] += 1
    
    # Recency-weighted average
    if sentiments:
        weights = [1.0 - (i * 0.5 / len(sentiments)) for i in range(len(sentiments))]
        weighted_sum = sum(s * w for s, w in zip(sentiments, weights))
        weighted_avg = weighted_sum / sum(weights)
    else:
        weighted_avg = 5.0
    
    return {
        'source': 'news_pipeline',
        'weighted_score': weighted_avg,
        'mention_count': len(rows),
        'article_count': len(rows),
        'source_tiers': dict(sources),
    }


def aggregate_research_observations(conn, entity_id: str, days: int = 60) -> dict:
    """
    Aggregate research/lab signals: press releases, company newsrooms, papers.
    Longer window (60 days) because research announcements are less frequent.
    """
    c = conn.cursor()
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    
    # Get Company Newsrooms specifically (press releases)
    c.execute("""
        SELECT so.raw_value, so.observed_at, so.raw_data
        FROM signal_observations so
        JOIN signal_sources ss ON so.source_id = ss.id
        WHERE so.entity_id = ?
          AND so.observed_at > ?
          AND ss.name = 'Company Newsrooms'
        ORDER BY so.observed_at DESC
    """, (entity_id, cutoff))
    
    newsroom_rows = c.fetchall()
    
    # Also check for any papers/research mentions in general news
    c.execute("""
        SELECT so.raw_value, so.raw_data
        FROM signal_observations so
        JOIN signal_sources ss ON so.source_id = ss.id
        WHERE so.entity_id = ?
          AND so.observed_at > ?
          AND so.category = 'media'
        ORDER BY so.observed_at DESC
    """, (entity_id, cutoff))
    
    all_rows = c.fetchall()
    
    # Count research-related keywords in news
    research_keywords = ['paper', 'research', 'published', 'study', 'breakthrough', 
                        'announce', 'release', 'launch', 'introduce', 'unveil',
                        'arxiv', 'journal', 'conference', 'nips', 'icml', 'cvpr']
    
    research_mentions = 0
    for row in all_rows:
        if row['raw_data']:
            try:
                data = json.loads(row['raw_data'])
                title = (data.get('title', '') + ' ' + data.get('summary', '')).lower()
                if any(kw in title for kw in research_keywords):
                    research_mentions += 1
            except:
                pass
    
    if not newsroom_rows and research_mentions == 0:
        return None
    
    # Calculate research score
    # Base: newsroom count * 3 (press releases are high signal)
    # Plus: research mentions in news
    newsroom_score = len(newsroom_rows) * 3
    mention_score = research_mentions
    
    # Sentiment from newsroom (usually positive for company announcements)
    if newsroom_rows:
        sentiments = [float(r['raw_value'] or 6.0) for r in newsroom_rows]
        avg_sentiment = sum(sentiments) / len(sentiments)
    else:
        avg_sentiment = 5.5  # Slightly positive default for research mentions
    
    # Convert to 0-100 scale
    raw_score = min(100, (newsroom_score + mention_score) * 5 + (avg_sentiment - 5) * 10)
    
    return {
        'score': max(0, raw_score),
        'newsroom_count': len(newsroom_rows),
        'research_mentions': research_mentions,
        'avg_sentiment': avg_sentiment,
    }


def rebuild_all_profiles(dry_run: bool = False):
    """Rebuild all profiles with new scoring formula."""
    
    conn = get_db()
    c = conn.cursor()
    
    media_scorer = MediaScorer()
    
    # Get all entities
    c.execute("SELECT id, name FROM entities")
    entities = c.fetchall()
    
    logger.info(f"Processing {len(entities)} entities...")
    
    # New weights
    WEIGHTS = {
        'technical': 0.20,  # Reduced from 25%
        'company': 0.15,
        'financial': 0.15,
        'media': 0.25,      # Increased
        'research': 0.25,   # New!
    }
    
    updated = 0
    results = []
    
    for entity in entities:
        entity_id = entity['id']
        entity_name = entity['name']
        
        # Get current profile
        c.execute("""
            SELECT technical_score, company_score, financial_score, product_score
            FROM signal_profiles
            WHERE entity_id = ?
        """, (entity_id,))
        profile = c.fetchone()
        
        # B) Calculate recency-adjusted technical score
        activity_score = get_recent_activity_score(conn, entity_id)
        
        tech_score = None
        if profile and profile['technical_score']:
            # Apply activity decay to technical score
            tech_score = profile['technical_score'] * activity_score
        
        # Media score (excluding newsrooms - those go to research)
        media_data = aggregate_media_observations(conn, entity_id, exclude_newsrooms=True)
        media_score = media_scorer.score(media_data) if media_data else None
        
        # C) Research score (newsrooms + research mentions)
        research_data = aggregate_research_observations(conn, entity_id)
        research_score = research_data['score'] if research_data else None
        
        # Company score
        company_score = profile['company_score'] if profile else None
        
        # Financial score
        financial_score = profile['financial_score'] if profile else None
        
        # Calculate weighted composite
        scores = []
        weights = []
        
        if tech_score:
            scores.append(tech_score)
            weights.append(WEIGHTS['technical'])
        
        if company_score:
            scores.append(company_score)
            weights.append(WEIGHTS['company'])
        
        if financial_score:
            scores.append(financial_score)
            weights.append(WEIGHTS['financial'])
        
        if media_score:
            scores.append(media_score)
            weights.append(WEIGHTS['media'])
        
        if research_score:
            scores.append(research_score)
            weights.append(WEIGHTS['research'])
        
        # Calculate composite
        if scores:
            total_weight = sum(weights)
            new_composite = sum(s * w for s, w in zip(scores, weights)) / total_weight
            
            # Coverage penalty for sparse data
            if len(scores) < 2:
                new_composite *= 0.7
            elif len(scores) < 3:
                new_composite *= 0.85
        else:
            new_composite = None
        
        # Store for logging
        if media_score or research_score or new_composite:
            results.append({
                'name': entity_name,
                'tech': tech_score,
                'company': company_score,
                'media': media_score,
                'research': research_score,
                'composite': new_composite,
                'activity': activity_score,
            })
            
            if not dry_run:
                c.execute("""
                    UPDATE signal_profiles
                    SET media_score = ?,
                        composite_score = ?,
                        as_of = ?
                    WHERE entity_id = ?
                """, (media_score, new_composite, datetime.now().isoformat(), entity_id))
                
                if c.rowcount == 0:
                    c.execute("""
                        INSERT INTO signal_profiles (
                            id, entity_id, entity_name, entity_type, as_of,
                            media_score, composite_score
                        ) VALUES (?, ?, ?, 'company', ?, ?, ?)
                    """, (
                        f"profile_{entity_id}",
                        entity_id,
                        entity_name,
                        datetime.now().isoformat(),
                        media_score,
                        new_composite
                    ))
            
            updated += 1
    
    if not dry_run:
        conn.commit()
    
    conn.close()
    
    # Print top 20 by new composite
    results.sort(key=lambda x: x['composite'] or 0, reverse=True)
    
    print("\n" + "=" * 100)
    print("NEW RANKINGS (Top 20)")
    print("=" * 100)
    print(f"{'Entity':<25} {'Tech':>8} {'Company':>8} {'Media':>8} {'Research':>8} {'Activity':>8} {'Composite':>10}")
    print("-" * 100)
    
    for r in results[:20]:
        tech = f"{r['tech']:.1f}" if r['tech'] else "-"
        company = f"{r['company']:.1f}" if r['company'] else "-"
        media = f"{r['media']:.1f}" if r['media'] else "-"
        research = f"{r['research']:.1f}" if r['research'] else "-"
        activity = f"{r['activity']:.2f}" if r['activity'] else "-"
        composite = f"{r['composite']:.1f}" if r['composite'] else "-"
        
        print(f"{r['name'][:25]:<25} {tech:>8} {company:>8} {media:>8} {research:>8} {activity:>8} {composite:>10}")
    
    print(f"\nUpdated {updated} profiles")
    return updated


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    
    rebuild_all_profiles(dry_run=args.dry_run)
