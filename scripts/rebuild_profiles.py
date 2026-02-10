#!/usr/bin/env python3
"""
Rebuild signal_profiles with proper media scoring.

This script fixes the broken pipeline by:
1. Aggregating signal_observations into scores per entity
2. Running MediaScorer on aggregated news data
3. Updating signal_profiles with media_score
4. Recalculating composite_score including media

Also applies recency weighting to technical scores.
"""

import sys
sys.path.insert(0, str(__file__).replace('\\', '/').rsplit('/', 2)[0])

import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict
from loguru import logger

from utils.signal_scorers import MediaScorer, TechnicalScorer
from utils.signal_models import SignalCategory


def get_db():
    db_path = Path(__file__).parent.parent / "data" / "signals.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def aggregate_media_observations(conn, entity_id: str, days: int = 30) -> dict:
    """Aggregate news observations for an entity into MediaScorer format."""
    c = conn.cursor()
    
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    
    c.execute("""
        SELECT so.raw_value, so.observed_at, so.raw_data, ss.name as source_name
        FROM signal_observations so
        JOIN signal_sources ss ON so.source_id = ss.id
        WHERE so.entity_id = ?
          AND so.category = 'media'
          AND so.observed_at > ?
        ORDER BY so.observed_at DESC
    """, (entity_id, cutoff))
    
    rows = c.fetchall()
    
    if not rows:
        return None
    
    # Aggregate
    sentiments = []
    articles = []
    sources = defaultdict(int)
    
    for row in rows:
        sentiment = row['raw_value'] or 5.0
        sentiments.append(float(sentiment))
        sources[row['source_name']] += 1
        
        if row['raw_data']:
            try:
                data = json.loads(row['raw_data'])
                articles.append(data)
            except:
                pass
    
    # Calculate weighted average (recent articles count more)
    if sentiments:
        # Weight: most recent = 1.0, oldest = 0.5
        weights = [1.0 - (i * 0.5 / len(sentiments)) for i in range(len(sentiments))]
        weighted_sum = sum(s * w for s, w in zip(sentiments, weights))
        weighted_avg = weighted_sum / sum(weights)
    else:
        weighted_avg = 5.0
    
    return {
        'source': 'news_pipeline',
        'weighted_score': weighted_avg,
        'mention_count': len(rows),
        'article_count': len(articles),
        'articles': articles,
        'source_tiers': dict(sources),
    }


def calculate_recency_adjusted_technical(conn, entity_id: str) -> float:
    """
    Calculate technical score with recency weighting.
    
    Old commits/activity from 2+ years ago shouldn't count as much.
    """
    c = conn.cursor()
    
    # Get existing technical score
    c.execute("""
        SELECT technical_score, data_freshness
        FROM signal_profiles
        WHERE entity_id = ?
    """, (entity_id,))
    
    row = c.fetchone()
    if not row or not row['technical_score']:
        return None
    
    base_score = row['technical_score']
    freshness = json.loads(row['data_freshness']) if row['data_freshness'] else {}
    
    # Check when technical data was last updated
    tech_date_str = freshness.get('technical')
    if tech_date_str:
        try:
            tech_date = datetime.fromisoformat(tech_date_str.replace('Z', '+00:00'))
            days_old = (datetime.now() - tech_date.replace(tzinfo=None)).days
            
            # Decay: lose 5% per month for old data
            if days_old > 30:
                months_old = days_old / 30
                decay = max(0.5, 1.0 - (months_old * 0.05))  # Min 50%
                return base_score * decay
        except:
            pass
    
    return base_score


def rebuild_all_profiles(dry_run: bool = False):
    """Rebuild all entity profiles with proper media scoring."""
    
    conn = get_db()
    c = conn.cursor()
    
    media_scorer = MediaScorer()
    
    # Get all entities
    c.execute("SELECT id, name FROM entities")
    entities = c.fetchall()
    
    logger.info(f"Processing {len(entities)} entities...")
    
    updated = 0
    
    for entity in entities:
        entity_id = entity['id']
        entity_name = entity['name']
        
        # Get current profile
        c.execute("""
            SELECT technical_score, company_score, financial_score, product_score, media_score,
                   technical_confidence, company_confidence
            FROM signal_profiles
            WHERE entity_id = ?
        """, (entity_id,))
        
        profile = c.fetchone()
        
        # Aggregate media observations
        media_data = aggregate_media_observations(conn, entity_id)
        
        new_media_score = None
        if media_data:
            new_media_score = media_scorer.score(media_data)
        
        # Get recency-adjusted technical score
        adjusted_tech = calculate_recency_adjusted_technical(conn, entity_id)
        
        # Calculate new composite score
        scores = []
        weights = []
        
        if profile:
            # Technical (with recency adjustment)
            tech = adjusted_tech or (profile['technical_score'] if profile else None)
            if tech:
                scores.append(tech)
                weights.append(0.25)
            
            # Company
            company = profile['company_score'] if profile else None
            if company:
                scores.append(company)
                weights.append(0.20)
            
            # Financial
            financial = profile['financial_score'] if profile else None
            if financial:
                scores.append(financial)
                weights.append(0.20)
            
            # Product
            product = profile['product_score'] if profile else None
            if product:
                scores.append(product)
                weights.append(0.15)
        
        # Media (newly calculated)
        if new_media_score:
            scores.append(new_media_score)
            weights.append(0.20)  # Give media 20% weight
        
        # Calculate composite
        if scores:
            # Normalize weights
            total_weight = sum(weights)
            new_composite = sum(s * w for s, w in zip(scores, weights)) / total_weight
            
            # Coverage penalty
            if len(scores) < 3:
                new_composite *= 0.8  # 20% penalty for sparse data
        else:
            new_composite = None
        
        # Log changes
        old_media = profile['media_score'] if profile else None
        old_composite = None
        if profile:
            c.execute("SELECT composite_score FROM signal_profiles WHERE entity_id = ?", (entity_id,))
            old_row = c.fetchone()
            old_composite = old_row[0] if old_row else None
        
        if new_media_score or new_composite:
            media_str = f"{new_media_score:.1f}" if new_media_score else "None"
            old_comp_str = f"{old_composite:.1f}" if old_composite else "None"
            new_comp_str = f"{new_composite:.1f}" if new_composite else "None"
            logger.info(f"{entity_name}: media {old_media} -> {media_str}, composite {old_comp_str} -> {new_comp_str}")
            
            if not dry_run:
                # Update or insert profile
                c.execute("""
                    UPDATE signal_profiles
                    SET media_score = ?,
                        composite_score = ?,
                        as_of = ?
                    WHERE entity_id = ?
                """, (new_media_score, new_composite, datetime.now().isoformat(), entity_id))
                
                if c.rowcount == 0:
                    # Insert new profile
                    c.execute("""
                        INSERT INTO signal_profiles (
                            id, entity_id, entity_name, entity_type, as_of,
                            media_score, composite_score, media_confidence
                        ) VALUES (?, ?, ?, 'company', ?, ?, ?, 0.8)
                    """, (
                        f"profile_{entity_id}",
                        entity_id,
                        entity_name,
                        datetime.now().isoformat(),
                        new_media_score,
                        new_composite
                    ))
            
            updated += 1
    
    if not dry_run:
        conn.commit()
    
    conn.close()
    
    logger.info(f"\nUpdated {updated} profiles")
    return updated


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Rebuild signal profiles with media scoring")
    parser.add_argument("--dry-run", action="store_true", help="Don't update database")
    
    args = parser.parse_args()
    
    logger.info("=" * 60)
    logger.info("REBUILDING SIGNAL PROFILES")
    logger.info("=" * 60)
    
    rebuild_all_profiles(dry_run=args.dry_run)
