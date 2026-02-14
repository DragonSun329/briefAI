#!/usr/bin/env python3
"""
Prediction Accumulator for briefAI.

Generates predictions from current signals and tracks them over time.
Run daily to build up prediction history for validation.
"""

import sys
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import hashlib

sys.path.insert(0, str(Path(__file__).parent.parent))

class PredictionAccumulator:
    """Generates and tracks predictions from briefAI signals."""
    
    def __init__(self, db_path: str = "data/predictions.db"):
        self.db_path = db_path
        self.signals_db = "data/signals.db"
        self._init_db()
    
    def _init_db(self):
        """Initialize predictions database - handles existing schema."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        
        # Check if table exists
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='predictions'")
        exists = cur.fetchone() is not None
        
        if not exists:
            # Create new table with our schema
            cur.execute("""
                CREATE TABLE predictions (
                    id INTEGER PRIMARY KEY,
                    entity_id TEXT,
                    entity_name TEXT,
                    ticker TEXT,
                    signal_type TEXT,
                    prediction_type TEXT,
                    predicted_outcome TEXT,
                    confidence REAL,
                    horizon_days INTEGER,
                    created_at TEXT,
                    horizon_date TEXT,
                    status TEXT DEFAULT 'pending',
                    resolved_at TEXT,
                    actual_outcome TEXT,
                    outcome_correct INTEGER,
                    price_at_prediction REAL,
                    price_at_resolution REAL,
                    price_change_pct REAL,
                    metadata TEXT
                )
            """)
        else:
            # Check existing columns
            cur.execute("PRAGMA table_info(predictions)")
            columns = [row[1] for row in cur.fetchall()]
            
            # Add missing columns if needed
            if "outcome_correct" not in columns:
                try:
                    cur.execute("ALTER TABLE predictions ADD COLUMN outcome_correct INTEGER")
                except:
                    pass
            if "price_change_pct" not in columns:
                try:
                    cur.execute("ALTER TABLE predictions ADD COLUMN price_change_pct REAL")
                except:
                    pass
        
        conn.commit()
        conn.close()
    
    def get_current_signals(self) -> List[Dict]:
        """Get latest calibrated signals for prediction generation."""
        conn = sqlite3.connect(self.signals_db)
        cur = conn.cursor()
        
        # Get latest signal profiles with sentiment
        cur.execute("""
            SELECT 
                sp.entity_id,
                sp.entity_name,
                sp.media_score,
                sp.technical_score,
                sp.financial_score,
                sp.composite_score,
                sp.created_at
            FROM signal_profiles sp
            WHERE sp.created_at = (
                SELECT MAX(created_at) FROM signal_profiles
            )
            AND sp.media_score IS NOT NULL
            ORDER BY sp.composite_score DESC
            LIMIT 50
        """)
        
        signals = []
        for row in cur.fetchall():
            signals.append({
                "entity_id": row[0],
                "entity_name": row[1],
                "media_score": row[2] or 5.0,
                "technical_score": row[3] or 5.0,
                "financial_score": row[4] or 5.0,
                "conviction_score": row[5] or 5.0,
                "timestamp": row[6]
            })
        
        conn.close()
        return signals
    
    def load_asset_mappings(self) -> Dict[str, str]:
        """Load entity to ticker mappings."""
        mapping_path = Path("data/asset_mapping.json")
        if not mapping_path.exists():
            return {}
        
        with open(mapping_path, encoding="utf-8") as f:
            data = json.load(f)
        
        mappings = {}
        entities_data = data.get("entities", {})
        
        if isinstance(entities_data, dict):
            # New format: dict with entity keys
            for key, entity in entities_data.items():
                name = entity.get("name", key).lower()
                ticker = entity.get("ticker") or (entity.get("proxy_tickers", [None])[0] if entity.get("proxy_tickers") else None)
                if ticker:
                    mappings[name] = ticker
                    mappings[key.lower()] = ticker  # Also map by key
        else:
            # Old format: list
            for entity in entities_data:
                name = entity.get("name", "").lower()
                ticker = entity.get("ticker") or entity.get("proxy_ticker")
                if ticker:
                    mappings[name] = ticker
        
        return mappings
    
    def generate_prediction(self, signal: Dict, horizon_days: int = 60) -> Optional[Dict]:
        """Generate a prediction from a signal."""
        
        media_score = signal.get("media_score", 5.0)
        conviction = signal.get("conviction_score", 5.0)
        
        # Determine prediction based on sentiment
        if media_score >= 7.0:
            predicted_outcome = "bullish"
            confidence = min(0.9, 0.5 + (media_score - 5) * 0.1)
        elif media_score <= 3.0:
            predicted_outcome = "bearish"
            confidence = min(0.9, 0.5 + (5 - media_score) * 0.1)
        else:
            # Neutral - skip weak signals
            if abs(media_score - 5.0) < 1.0:
                return None
            predicted_outcome = "bullish" if media_score > 5.0 else "bearish"
            confidence = 0.5 + abs(media_score - 5.0) * 0.05
        
        # Boost confidence with conviction score
        if conviction > 7.0:
            confidence = confidence + 0.1
        
        now = datetime.now()
        horizon_date = now + timedelta(days=horizon_days)
        
        return {
            "entity_id": signal.get("entity_id"),
            "entity_name": signal.get("entity_name"),
            "signal_type": "media_sentiment",
            "prediction_type": "direction",
            "predicted_outcome": predicted_outcome,
            "confidence": confidence,
            "horizon_days": horizon_days,
            "created_at": now.isoformat(),
            "horizon_date": horizon_date.isoformat(),
            "metadata": json.dumps({
                "media_score": media_score,
                "technical_score": signal.get("technical_score"),
                "conviction_score": conviction,
                "source_timestamp": signal.get("timestamp")
            })
        }
    
    def prediction_exists(self, entity_name: str, horizon_days: int, lookback_days: int = 7) -> bool:
        """Check if a similar prediction already exists."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        
        cutoff = (datetime.now() - timedelta(days=lookback_days)).isoformat()
        
        cur.execute("""
            SELECT COUNT(*) FROM predictions
            WHERE entity_name = ?
            AND horizon_days = ?
            AND created_at > ?
        """, (entity_name, horizon_days, cutoff))
        
        count = cur.fetchone()[0]
        conn.close()
        return count > 0
    
    def save_prediction(self, prediction: Dict, ticker: Optional[str] = None):
        """Save a prediction to the database."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        
        # Check which columns exist
        cur.execute("PRAGMA table_info(predictions)")
        columns = [row[1] for row in cur.fetchall()]
        
        if "ticker" in columns:
            cur.execute("""
                INSERT INTO predictions (
                    entity_id, entity_name, ticker, signal_type, prediction_type,
                    predicted_outcome, confidence, horizon_days, created_at,
                    horizon_date, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                prediction["entity_id"],
                prediction["entity_name"],
                ticker,
                prediction["signal_type"],
                prediction["prediction_type"],
                prediction["predicted_outcome"],
                prediction["confidence"],
                prediction["horizon_days"],
                prediction["created_at"],
                prediction["horizon_date"],
                prediction.get("metadata", "{}")
            ))
        else:
            # Existing schema - adapt
            metadata = prediction.get("metadata", "{}")
            if ticker:
                # Store ticker in metadata
                try:
                    meta_dict = json.loads(metadata) if isinstance(metadata, str) else metadata
                    meta_dict["ticker"] = ticker
                    metadata = json.dumps(meta_dict)
                except:
                    pass
            
            cur.execute("""
                INSERT INTO predictions (
                    entity_id, entity_name, signal_type, prediction_type,
                    predicted_outcome, confidence, horizon_days, 
                    predicted_at, horizon_date, source_metadata, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                prediction["entity_id"],
                prediction["entity_name"],
                prediction["signal_type"],
                prediction["prediction_type"],
                prediction["predicted_outcome"],
                prediction["confidence"],
                prediction["horizon_days"],
                prediction["created_at"],
                prediction["horizon_date"],
                metadata,
                "pending"
            ))
        
        conn.commit()
        conn.close()
    
    def resolve_due_predictions(self):
        """Resolve predictions that have reached their horizon date."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        
        now = datetime.now().isoformat()
        
        # Check schema to determine status field name
        cur.execute("PRAGMA table_info(predictions)")
        columns = [row[1] for row in cur.fetchall()]
        
        # Get unresolved predictions past their horizon
        # Support both old schema (resolved) and new schema (status)
        if "status" in columns:
            # Extract ticker from source_metadata if available
            cur.execute("""
                SELECT id, entity_name, 
                       COALESCE(source_metadata, '{}') as metadata, 
                       predicted_outcome, horizon_days,
                       COALESCE(created_at, predicted_at) as created_at, 
                       NULL as price_at_prediction
                FROM predictions
                WHERE (status = 'pending' OR status IS NULL)
                AND horizon_date < ?
            """, (now,))
        else:
            cur.execute("""
                SELECT id, entity_name, ticker, predicted_outcome, horizon_days,
                       created_at, price_at_prediction
                FROM predictions
                WHERE resolved = 0
                AND horizon_date < ?
            """, (now,))
        
        due_predictions = cur.fetchall()
        conn.close()
        
        print(f"Found {len(due_predictions)} predictions to resolve")
        
        resolved_count = 0
        ticker_map = self.load_asset_mappings()
        
        for pred in due_predictions:
            pred_id, entity_name, metadata_or_ticker, predicted_outcome, horizon_days, created_at, price_at_pred = pred
            
            # Try to get ticker from metadata or lookup
            ticker = None
            if metadata_or_ticker and metadata_or_ticker.startswith('{'):
                try:
                    meta = json.loads(metadata_or_ticker)
                    ticker = meta.get("ticker")
                except:
                    pass
            elif metadata_or_ticker:
                ticker = metadata_or_ticker
            
            if not ticker:
                # Try lookup by entity name
                ticker = ticker_map.get(entity_name.lower())
            
            if not ticker:
                continue
            
            # Get price change
            try:
                import yfinance as yf
                
                start_date = datetime.fromisoformat(created_at)
                end_date = start_date + timedelta(days=horizon_days)
                
                stock = yf.Ticker(ticker)
                hist = stock.history(start=start_date, end=end_date + timedelta(days=1))
                
                if len(hist) < 2:
                    continue
                
                start_price = hist.iloc[0]["Close"]
                end_price = hist.iloc[-1]["Close"]
                price_change = (end_price - start_price) / start_price
                
                # Determine if prediction was correct
                actual_outcome = "bullish" if price_change > 0.02 else ("bearish" if price_change < -0.02 else "neutral")
                
                # Check correctness
                if predicted_outcome == "bullish":
                    correct = price_change > 0
                elif predicted_outcome == "bearish":
                    correct = price_change < 0
                else:
                    correct = abs(price_change) < 0.05
                
                # Update database
                self._resolve_prediction(
                    pred_id, 
                    actual_outcome, 
                    correct,
                    start_price,
                    end_price,
                    price_change * 100
                )
                resolved_count += 1
                
            except Exception as e:
                print(f"  Error resolving {entity_name}: {e}")
                continue
        
        print(f"Resolved {resolved_count} predictions")
        return resolved_count
    
    def _resolve_prediction(self, pred_id: int, actual_outcome: str, correct: bool,
                           price_at_pred: float, price_at_res: float, price_change_pct: float):
        """Update a prediction with resolution data."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        
        # Check schema
        cur.execute("PRAGMA table_info(predictions)")
        columns = [row[1] for row in cur.fetchall()]
        
        if "status" in columns:
            # New schema with status field
            cur.execute("""
                UPDATE predictions SET
                    status = 'resolved',
                    resolved_at = ?,
                    actual_outcome = ?,
                    outcome_correct = ?
                WHERE id = ?
            """, (
                datetime.now().isoformat(),
                actual_outcome,
                1 if correct else 0,
                pred_id
            ))
        else:
            # Old schema with resolved field
            cur.execute("""
                UPDATE predictions SET
                    resolved = 1,
                    resolved_at = ?,
                    actual_outcome = ?,
                    outcome_correct = ?,
                    price_at_prediction = ?,
                    price_at_resolution = ?,
                    price_change_pct = ?
                WHERE id = ?
            """, (
                datetime.now().isoformat(),
                actual_outcome,
                1 if correct else 0,
                price_at_pred,
                price_at_res,
                price_change_pct,
                pred_id
            ))
        
        conn.commit()
        conn.close()
    
    def get_stats(self) -> Dict:
        """Get prediction statistics."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        
        # Check schema
        cur.execute("PRAGMA table_info(predictions)")
        columns = [row[1] for row in cur.fetchall()]
        
        cur.execute("SELECT COUNT(*) FROM predictions")
        total = cur.fetchone()[0]
        
        if "status" in columns:
            # New schema
            cur.execute("SELECT COUNT(*) FROM predictions WHERE status = 'resolved'")
            resolved = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(*) FROM predictions WHERE status = 'resolved' AND outcome_correct = 1")
            correct = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(*) FROM predictions WHERE status = 'pending' OR status IS NULL")
            pending = cur.fetchone()[0]
        else:
            # Old schema
            cur.execute("SELECT COUNT(*) FROM predictions WHERE resolved = 1")
            resolved = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(*) FROM predictions WHERE resolved = 1 AND outcome_correct = 1")
            correct = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(*) FROM predictions WHERE resolved = 0")
            pending = cur.fetchone()[0]
        
        conn.close()
        
        return {
            "total": total,
            "resolved": resolved,
            "correct": correct,
            "accuracy": correct / resolved if resolved > 0 else 0,
            "pending": pending
        }
    
    def run(self, horizons: List[int] = [14, 30, 60]):
        """Run prediction accumulation."""
        print("=" * 60)
        print("briefAI Prediction Accumulator")
        print(f"Run at: {datetime.now().isoformat()}")
        print("=" * 60)
        
        # Load mappings
        ticker_map = self.load_asset_mappings()
        print(f"\nLoaded {len(ticker_map)} ticker mappings")
        
        # Get current signals
        signals = self.get_current_signals()
        print(f"Got {len(signals)} current signals")
        
        # Generate predictions
        new_predictions = 0
        skipped = 0
        
        for signal in signals:
            entity_name = signal.get("entity_name", "")
            ticker = ticker_map.get(entity_name.lower())
            
            for horizon in horizons:
                # Skip if recent prediction exists
                if self.prediction_exists(entity_name, horizon):
                    skipped += 1
                    continue
                
                prediction = self.generate_prediction(signal, horizon)
                if prediction:
                    self.save_prediction(prediction, ticker)
                    new_predictions += 1
        
        print(f"\nGenerated {new_predictions} new predictions")
        print(f"Skipped {skipped} (recent predictions exist)")
        
        # Resolve due predictions
        print("\n--- Resolving Due Predictions ---")
        self.resolve_due_predictions()
        
        # Print stats
        stats = self.get_stats()
        print("\n--- Statistics ---")
        print(f"Total predictions: {stats['total']}")
        print(f"Resolved: {stats['resolved']}")
        print(f"Correct: {stats['correct']}")
        print(f"Accuracy: {stats['accuracy']:.1%}")
        print(f"Pending: {stats['pending']}")
        
        return stats

def main():
    accumulator = PredictionAccumulator()
    stats = accumulator.run()
    
    # Return success if we have predictions
    return stats["total"] > 0

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
