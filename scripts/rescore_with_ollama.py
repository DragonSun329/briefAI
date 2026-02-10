#!/usr/bin/env python3
"""
Rescore existing signal_observations using Ollama LLM sentiment.

Replaces the flat 5.0 keyword-based scores with actual sentiment analysis.
"""

import sys
sys.path.insert(0, str(__file__).replace('\\', '/').rsplit('/', 2)[0])

import sqlite3
import json
from pathlib import Path
from datetime import datetime
from loguru import logger

# Reconfigure stdout for Unicode
sys.stdout.reconfigure(encoding='utf-8')

from utils.ollama_sentiment import OllamaSentimentAnalyzer, OllamaSentimentScorer

def rescore_observations(
    db_path: Path = None,
    entity_filter: list = None,
    limit: int = 100,
    dry_run: bool = False
):
    """
    Rescore signal_observations with Ollama sentiment.
    
    Args:
        db_path: Path to signals.db
        entity_filter: List of entity names to filter (optional)
        limit: Max observations to rescore
        dry_run: If True, don't update database
    """
    if db_path is None:
        db_path = Path(__file__).parent.parent / "data" / "signals.db"
    
    logger.info(f"Rescoring observations in {db_path}")
    
    # Initialize Ollama analyzer
    analyzer = OllamaSentimentAnalyzer(timeout=120)
    
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    # Get observations to rescore
    if entity_filter:
        placeholders = ','.join('?' * len(entity_filter))
        query = f"""
            SELECT so.id, e.name, so.raw_value, so.raw_data
            FROM signal_observations so
            JOIN entities e ON so.entity_id = e.id
            WHERE LOWER(e.name) IN ({placeholders})
              AND so.raw_data IS NOT NULL
            ORDER BY so.observed_at DESC
            LIMIT ?
        """
        c.execute(query, [n.lower() for n in entity_filter] + [limit])
    else:
        c.execute("""
            SELECT so.id, e.name, so.raw_value, so.raw_data
            FROM signal_observations so
            JOIN entities e ON so.entity_id = e.id
            WHERE so.raw_data IS NOT NULL
            ORDER BY so.observed_at DESC
            LIMIT ?
        """, (limit,))
    
    rows = c.fetchall()
    logger.info(f"Found {len(rows)} observations to rescore")
    
    updates = []
    
    for obs_id, entity_name, old_score, raw_data_json in rows:
        try:
            raw_data = json.loads(raw_data_json) if raw_data_json else {}
            
            # Get text to analyze
            title = raw_data.get('title', raw_data.get('headline', ''))
            summary = raw_data.get('summary', raw_data.get('description', ''))
            text = f"{title} {summary}".strip()
            
            if not text:
                continue
            
            # Analyze with Ollama
            result = analyzer.analyze(text)
            new_score = result.score
            
            # Track update
            delta = new_score - (old_score or 5.0)
            direction = "+" if delta > 0 else "-" if delta < 0 else "="
            
            sign = "+" if result.sentiment == "bullish" else "-" if result.sentiment == "bearish" else "="
            logger.info(f"[{sign}] {entity_name:15s} | {old_score:.1f} -> {new_score:.1f} ({direction}{abs(delta):.1f}) | {title[:40]}")
            
            updates.append((new_score, result.sentiment, result.confidence, obs_id))
            
        except Exception as e:
            logger.error(f"Error processing {obs_id}: {e}")
            continue
    
    # Apply updates
    if not dry_run and updates:
        logger.info(f"\nApplying {len(updates)} updates...")
        
        for new_score, sentiment, confidence, obs_id in updates:
            c.execute("""
                UPDATE signal_observations 
                SET raw_value = ?
                WHERE id = ?
            """, (new_score, obs_id))
        
        conn.commit()
        logger.info("Updates committed!")
    elif dry_run:
        logger.info("\nDry run - no changes made")
    
    conn.close()
    
    # Summary
    if updates:
        avg_old = sum(u[0] for u in updates) / len(updates) if updates else 0
        bearish_count = sum(1 for u in updates if u[1] == "bearish")
        bullish_count = sum(1 for u in updates if u[1] == "bullish")
        neutral_count = sum(1 for u in updates if u[1] == "neutral")
        
        print("\n" + "=" * 60)
        print("RESCORE SUMMARY")
        print("=" * 60)
        print(f"Total rescored: {len(updates)}")
        print(f"Bullish: {bullish_count} | Neutral: {neutral_count} | Bearish: {bearish_count}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Rescore observations with Ollama")
    parser.add_argument("--entities", type=str, help="Comma-separated entity names")
    parser.add_argument("--limit", type=int, default=50, help="Max observations")
    parser.add_argument("--dry-run", action="store_true", help="Don't update DB")
    
    args = parser.parse_args()
    
    entity_filter = None
    if args.entities:
        entity_filter = [e.strip() for e in args.entities.split(",")]
    
    rescore_observations(
        entity_filter=entity_filter,
        limit=args.limit,
        dry_run=args.dry_run
    )
