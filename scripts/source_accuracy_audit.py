"""
Source Accuracy Audit

Analyzes which signal sources have the best predictive accuracy
and updates source_credibility.json with accuracy-based weights.

Usage:
    python scripts/source_accuracy_audit.py [--days 30] [--update]

The audit:
1. Loads historical predictions from the database
2. Matches predictions with price outcomes
3. Calculates accuracy per source
4. Updates source weights based on accuracy

Target: Reduce weight for consistently wrong sources
"""

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple, Any, Optional
import argparse

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.logger import logger


# Paths
CONFIG_DIR = Path(__file__).parent.parent / "config"
DATA_DIR = Path(__file__).parent.parent / "data"
DB_PATH = DATA_DIR / "briefai.db"
SOURCE_CREDIBILITY_PATH = CONFIG_DIR / "source_credibility.json"
AUDIT_RESULTS_PATH = DATA_DIR / "source_accuracy_audit.json"


def load_predictions(db_path: Path, days: int = 30) -> List[Dict]:
    """Load predictions from the database."""
    cutoff = datetime.now() - timedelta(days=days)
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Check what tables exist
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    
    predictions = []
    
    # Try signal_observations table
    if "signal_observations" in tables:
        cursor.execute("""
            SELECT 
                entity_id,
                source_id,
                raw_value as sentiment,
                observed_at,
                confidence
            FROM signal_observations
            WHERE observed_at > ?
            ORDER BY observed_at DESC
        """, (cutoff.isoformat(),))
        
        for row in cursor.fetchall():
            predictions.append(dict(row))
    
    # Also try predictions table if it exists
    if "predictions" in tables:
        cursor.execute("""
            SELECT 
                entity_id,
                source as source_id,
                predicted_direction,
                confidence,
                created_at as observed_at,
                outcome_direction,
                was_correct
            FROM predictions
            WHERE created_at > ?
        """, (cutoff.isoformat(),))
        
        for row in cursor.fetchall():
            predictions.append(dict(row))
    
    conn.close()
    return predictions


def load_price_outcomes(db_path: Path, days: int = 30) -> Dict[str, List[Dict]]:
    """Load price outcomes grouped by entity."""
    cutoff = datetime.now() - timedelta(days=days)
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Check for price data table
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    
    outcomes = defaultdict(list)
    
    if "price_history" in tables:
        cursor.execute("""
            SELECT entity_id, date, close_price, change_pct
            FROM price_history
            WHERE date > ?
            ORDER BY date
        """, (cutoff.isoformat(),))
        
        for row in cursor.fetchall():
            outcomes[row["entity_id"]].append(dict(row))
    
    conn.close()
    return dict(outcomes)


def calculate_source_accuracy(
    predictions: List[Dict],
    price_outcomes: Dict[str, List[Dict]],
    horizon_days: int = 5
) -> Dict[str, Dict[str, Any]]:
    """
    Calculate accuracy for each source.
    
    Returns dict of source_id -> {
        total: int,
        correct: int,
        accuracy: float,
        avg_confidence: float,
        entities_covered: set
    }
    """
    source_stats = defaultdict(lambda: {
        "total": 0,
        "correct": 0,
        "bullish_correct": 0,
        "bullish_total": 0,
        "bearish_correct": 0,
        "bearish_total": 0,
        "confidences": [],
        "entities": set(),
    })
    
    for pred in predictions:
        source_id = pred.get("source_id", "unknown")
        entity_id = pred.get("entity_id")
        
        if not entity_id:
            continue
        
        # Get sentiment/direction from prediction
        sentiment = pred.get("sentiment")
        direction = pred.get("predicted_direction")
        
        # Determine predicted direction
        if direction:
            predicted_bullish = direction.lower() in ["bullish", "up", "positive"]
            predicted_bearish = direction.lower() in ["bearish", "down", "negative"]
        elif sentiment is not None:
            predicted_bullish = float(sentiment) > 6
            predicted_bearish = float(sentiment) < 4
        else:
            continue
        
        # Skip neutral predictions
        if not predicted_bullish and not predicted_bearish:
            continue
        
        source_stats[source_id]["total"] += 1
        source_stats[source_id]["entities"].add(entity_id)
        
        if pred.get("confidence"):
            source_stats[source_id]["confidences"].append(float(pred["confidence"]))
        
        # Check if we have pre-computed outcome
        if pred.get("was_correct") is not None:
            was_correct = bool(pred["was_correct"])
        else:
            # Look up price outcome
            entity_prices = price_outcomes.get(entity_id, [])
            if not entity_prices:
                continue
            
            # Find price change after prediction
            pred_time = pred.get("observed_at")
            if isinstance(pred_time, str):
                try:
                    pred_date = datetime.fromisoformat(pred_time.replace("Z", "+00:00")).date()
                except:
                    continue
            else:
                continue
            
            # Find future price
            future_prices = [
                p for p in entity_prices
                if datetime.fromisoformat(p["date"]).date() > pred_date
            ]
            
            if not future_prices or len(future_prices) < 2:
                continue
            
            # Calculate actual price change
            if horizon_days <= len(future_prices):
                end_price = future_prices[horizon_days - 1]
            else:
                end_price = future_prices[-1]
            
            actual_change = end_price.get("change_pct", 0)
            
            # Compare prediction to outcome
            if predicted_bullish:
                source_stats[source_id]["bullish_total"] += 1
                was_correct = actual_change > 0
                if was_correct:
                    source_stats[source_id]["bullish_correct"] += 1
            else:
                source_stats[source_id]["bearish_total"] += 1
                was_correct = actual_change < 0
                if was_correct:
                    source_stats[source_id]["bearish_correct"] += 1
        
        if was_correct:
            source_stats[source_id]["correct"] += 1
    
    # Calculate final stats
    results = {}
    for source_id, stats in source_stats.items():
        if stats["total"] == 0:
            continue
        
        accuracy = stats["correct"] / stats["total"]
        avg_confidence = sum(stats["confidences"]) / len(stats["confidences"]) if stats["confidences"] else 0.5
        
        results[source_id] = {
            "total_predictions": stats["total"],
            "correct_predictions": stats["correct"],
            "accuracy": round(accuracy, 3),
            "avg_confidence": round(avg_confidence, 3),
            "bullish_accuracy": round(stats["bullish_correct"] / stats["bullish_total"], 3) if stats["bullish_total"] > 0 else None,
            "bearish_accuracy": round(stats["bearish_correct"] / stats["bearish_total"], 3) if stats["bearish_total"] > 0 else None,
            "entities_covered": len(stats["entities"]),
        }
    
    return results


def calculate_accuracy_weight(accuracy: float, total: int, min_samples: int = 10) -> float:
    """
    Convert accuracy to weight with sample size adjustment.
    
    Uses Bayesian-ish approach: 
    - Few samples → regress toward 0.5 accuracy (neutral weight)
    - Many samples → trust the accuracy more
    """
    # Weight reliability based on sample size
    reliability = min(1.0, total / min_samples)
    
    # Regress accuracy toward 0.5 based on reliability
    adjusted_accuracy = 0.5 + (accuracy - 0.5) * reliability
    
    # Convert accuracy to weight (0.3 - 1.0 scale)
    # 0.5 accuracy → 0.5 weight
    # 0.7 accuracy → 0.8 weight  
    # 0.3 accuracy → 0.3 weight (penalty for bad sources)
    weight = 0.3 + (adjusted_accuracy * 0.7)
    
    return round(weight, 2)


def update_source_credibility(
    accuracy_results: Dict[str, Dict],
    credibility_path: Path = SOURCE_CREDIBILITY_PATH,
    dry_run: bool = True
) -> Dict:
    """
    Update source_credibility.json with accuracy-based weights.
    """
    # Load existing credibility config
    with open(credibility_path) as f:
        config = json.load(f)
    
    # Create new accuracy_weights section
    accuracy_weights = {}
    
    for source_id, stats in accuracy_results.items():
        if stats["total_predictions"] >= 5:  # Minimum threshold
            weight = calculate_accuracy_weight(
                stats["accuracy"],
                stats["total_predictions"]
            )
            accuracy_weights[source_id] = {
                "weight": weight,
                "accuracy": stats["accuracy"],
                "samples": stats["total_predictions"],
                "updated_at": datetime.now().isoformat()
            }
    
    # Add accuracy_weights section to config
    config["accuracy_weights"] = accuracy_weights
    config["accuracy_last_updated"] = datetime.now().isoformat()
    
    if not dry_run:
        with open(credibility_path, "w") as f:
            json.dump(config, f, indent=2)
        logger.info(f"Updated {credibility_path} with accuracy weights for {len(accuracy_weights)} sources")
    else:
        logger.info(f"[DRY RUN] Would update {len(accuracy_weights)} source weights")
    
    return config


def run_audit(days: int = 30, update: bool = False) -> Dict:
    """Run the full source accuracy audit."""
    logger.info(f"Running source accuracy audit for past {days} days")
    
    # Check if DB exists
    if not DB_PATH.exists():
        logger.warning(f"Database not found at {DB_PATH}")
        # Return mock results for testing
        return {
            "status": "no_database",
            "message": "Database not found - run scrapers first"
        }
    
    # Load data
    predictions = load_predictions(DB_PATH, days)
    logger.info(f"Loaded {len(predictions)} predictions")
    
    price_outcomes = load_price_outcomes(DB_PATH, days)
    logger.info(f"Loaded price data for {len(price_outcomes)} entities")
    
    # Calculate accuracy
    accuracy_results = calculate_source_accuracy(predictions, price_outcomes)
    
    # Sort by accuracy
    sorted_sources = sorted(
        accuracy_results.items(),
        key=lambda x: x[1]["accuracy"],
        reverse=True
    )
    
    # Print results
    print("\n" + "=" * 70)
    print("SOURCE ACCURACY AUDIT RESULTS")
    print("=" * 70)
    print(f"{'Source':<25} {'Accuracy':>10} {'Samples':>10} {'Weight':>10}")
    print("-" * 70)
    
    for source_id, stats in sorted_sources:
        weight = calculate_accuracy_weight(stats["accuracy"], stats["total_predictions"])
        marker = "[+]" if stats["accuracy"] >= 0.6 else "[~]" if stats["accuracy"] >= 0.5 else "[-]"
        print(f"{marker} {source_id:<23} {stats['accuracy']:>10.1%} {stats['total_predictions']:>10} {weight:>10.2f}")
    
    print("=" * 70)
    
    # Save results
    audit_results = {
        "generated_at": datetime.now().isoformat(),
        "days_analyzed": days,
        "total_predictions": len(predictions),
        "sources_analyzed": len(accuracy_results),
        "source_accuracy": accuracy_results,
        "top_sources": [
            {"source": s, "accuracy": a["accuracy"], "samples": a["total_predictions"]}
            for s, a in sorted_sources[:5]
        ],
        "bottom_sources": [
            {"source": s, "accuracy": a["accuracy"], "samples": a["total_predictions"]}
            for s, a in sorted_sources[-5:]
        ] if len(sorted_sources) >= 5 else []
    }
    
    AUDIT_RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(AUDIT_RESULTS_PATH, "w") as f:
        json.dump(audit_results, f, indent=2)
    logger.info(f"Saved audit results to {AUDIT_RESULTS_PATH}")
    
    # Update credibility config if requested
    if update:
        update_source_credibility(accuracy_results, dry_run=False)
    else:
        update_source_credibility(accuracy_results, dry_run=True)
    
    return audit_results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Audit source signal accuracy")
    parser.add_argument("--days", type=int, default=30, help="Days of history to analyze")
    parser.add_argument("--update", action="store_true", help="Update source_credibility.json")
    
    args = parser.parse_args()
    
    results = run_audit(days=args.days, update=args.update)
    
    if results.get("status") == "no_database":
        print(f"\n[!] {results['message']}")
    else:
        print(f"\n[OK] Audit complete. Analyzed {results['sources_analyzed']} sources.")
