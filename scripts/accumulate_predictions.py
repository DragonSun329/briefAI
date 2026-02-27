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
    
    def load_market_signals(self) -> Dict[str, Dict]:
        """Load latest Finnhub market data for momentum analysis."""
        market_data = {}
        signal_dir = Path("data/market_signals")
        
        if not signal_dir.exists():
            return market_data
        
        # Find the latest Finnhub file
        finnhub_files = list(signal_dir.glob("finnhub_*.json"))
        if not finnhub_files:
            return market_data
        
        latest_file = max(finnhub_files, key=lambda f: f.stat().st_mtime)
        
        try:
            with open(latest_file, encoding="utf-8") as f:
                data = json.load(f)
            
            # Extract price momentum data by ticker (work with actual Finnhub structure)
            for stock in data.get("stocks", []):
                ticker = stock.get("ticker")
                if ticker:
                    change_pct = stock.get("change_pct", 0)
                    signal = stock.get("signal", "neutral")
                    score = stock.get("score", 0)
                    
                    market_data[ticker] = {
                        "current_price": stock.get("current_price"),
                        "change_pct": change_pct,
                        "volume_signal": signal,
                        "score": score,
                        # Estimate momentum from available data
                        "momentum_strength": abs(score) if score else abs(change_pct) / 5.0
                    }
        except Exception as e:
            print(f"Error loading market signals: {e}")
        
        return market_data
    
    def load_insider_signals(self) -> Dict[str, float]:
        """Load latest insider trading signals."""
        insider_signals = {}
        signal_dir = Path("data/insider_signals")
        
        if not signal_dir.exists():
            return insider_signals
        
        # Find the latest insider file
        insider_files = list(signal_dir.glob("insider_trades_*.json"))
        if not insider_files:
            return insider_signals
        
        latest_file = max(insider_files, key=lambda f: f.stat().st_mtime)
        
        try:
            with open(latest_file, encoding="utf-8") as f:
                data = json.load(f)
            
            # Aggregate insider signals by entity
            for signal in data.get("signals", []):
                entity = signal.get("entity", "").upper()
                if not entity:
                    continue
                
                # Insider signal strength: +1 for buy, -1 for sell, weighted by value
                trade_type = signal.get("trade_type", "").lower()
                trade_value = signal.get("trade_value", 0)
                
                if trade_type in ["purchase", "buy"]:
                    signal_value = min(trade_value / 1000000, 5.0)  # Cap at $5M for scaling
                elif trade_type in ["sale", "sell"]:
                    signal_value = -min(trade_value / 1000000, 5.0)
                else:
                    continue
                
                if entity not in insider_signals:
                    insider_signals[entity] = 0
                insider_signals[entity] += signal_value
            
            # Normalize to -1 to +1 range
            for entity in insider_signals:
                insider_signals[entity] = max(-1.0, min(1.0, insider_signals[entity] / 3.0))
                
        except Exception as e:
            print(f"Error loading insider signals: {e}")
        
        return insider_signals

    def generate_prediction(self, signal: Dict, horizon_days: int = 60) -> Optional[Dict]:
        """Generate a prediction from multiple signal sources with proper confidence limits."""
        
        entity_name = signal.get("entity_name", "")
        media_score = signal.get("media_score", 5.0)
        conviction = signal.get("conviction_score", 5.0)
        
        # Normalize scores to 0-10 scale if they appear to be on 0-100 scale
        if media_score > 10:
            media_score = media_score / 10.0
        if conviction > 10:
            conviction = conviction / 10.0
        
        # Widen the neutral dead zone - skip if media_score is within 1.5 of center
        if abs(media_score - 5.0) < 1.5:
            return None
        
        # Get ticker for market data lookup
        ticker_map = self.load_asset_mappings()
        ticker = ticker_map.get(entity_name.lower())
        
        # Load additional signals
        market_data = self.load_market_signals()
        insider_signals = self.load_insider_signals()
        
        # Start with media sentiment
        media_bias = (media_score - 5.0) / 5.0  # -1 to +1 scale
        
        # Initialize signal components
        signals_present = ["media"]
        signal_strength = abs(media_bias)
        
        # Price momentum analysis (contrarian signals based on available data)
        momentum_bias = 0
        if ticker and ticker in market_data:
            mdata = market_data[ticker]
            change_pct = mdata.get("change_pct", 0)
            volume_signal = mdata.get("volume_signal", "neutral")
            score = mdata.get("score", 0)
            
            # Strong single-day moves suggest potential mean reversion
            if change_pct > 5:  # Strong up day - contrarian bearish bias
                momentum_bias -= 0.2
                signals_present.append("strong_up_day")
            elif change_pct < -5:  # Strong down day - contrarian bullish bias
                momentum_bias += 0.2
                signals_present.append("strong_down_day")
            
            # Volume signal provides momentum confirmation/contradiction
            if volume_signal == "bullish" or volume_signal == "slightly_bullish":
                if score > 0.3:  # Strong bullish volume signal
                    momentum_bias += 0.25
                    signals_present.append("volume_bullish")
                elif score > 0.1:  # Mild bullish volume
                    momentum_bias += 0.15
                    signals_present.append("volume_mild_bullish")
            elif volume_signal == "bearish" or volume_signal == "slightly_bearish":
                if score < -0.3:  # Strong bearish volume signal
                    momentum_bias -= 0.25
                    signals_present.append("volume_bearish")
                elif score < -0.1:  # Mild bearish volume
                    momentum_bias -= 0.15
                    signals_present.append("volume_mild_bearish")
        
        # Insider trading signals
        insider_bias = 0
        if ticker and ticker.upper() in insider_signals:
            insider_bias = insider_signals[ticker.upper()]
            if abs(insider_bias) > 0.1:  # Only count meaningful insider activity
                signals_present.append("insider")
        
        # Combine all signals
        total_bias = media_bias + momentum_bias + insider_bias
        
        # Determine prediction outcome
        if total_bias > 0.15:
            predicted_outcome = "bullish"
        elif total_bias < -0.15:
            predicted_outcome = "bearish"
        else:
            # Mixed/weak signals - skip prediction (neutral dead zone)
            return None
        
        # Calculate confidence based on signal count and agreement
        base_confidence = 0.45 + (abs(total_bias) * 0.25)
        
        # Confidence caps based on signal diversity
        if len(signals_present) == 1:
            # Single signal (media only) - max 70%
            confidence = min(base_confidence, 0.70)
        elif len(signals_present) >= 3:
            # Multiple independent signals - max 85%
            confidence = min(base_confidence, 0.85)
        else:
            # Two signals - max 78%
            confidence = min(base_confidence, 0.78)
        
        # Reduce confidence if media and momentum conflict
        if len(signals_present) > 1:
            media_momentum_conflict = (media_bias > 0 and momentum_bias < -0.1) or \
                                    (media_bias < 0 and momentum_bias > 0.1)
            if media_momentum_conflict:
                confidence *= 0.8  # 20% confidence penalty for conflicting signals
        
        # Ensure minimum confidence threshold
        confidence = max(confidence, 0.51)
        
        now = datetime.now()
        horizon_date = now + timedelta(days=horizon_days)
        
        # Enhanced metadata with all signal sources
        metadata = {
            "media_score": media_score,
            "media_bias": media_bias,
            "momentum_bias": momentum_bias,
            "insider_bias": insider_bias,
            "total_bias": total_bias,
            "signals_present": signals_present,
            "technical_score": signal.get("technical_score"),
            "conviction_score": conviction,
            "source_timestamp": signal.get("timestamp"),
            "ticker": ticker
        }
        
        # Add market data to metadata if available
        if ticker and ticker in market_data:
            metadata["market_data"] = market_data[ticker]
        
        return {
            "entity_id": signal.get("entity_id"),
            "entity_name": entity_name,
            "signal_type": "multi_source",  # Changed from media_sentiment
            "prediction_type": "direction",
            "predicted_outcome": predicted_outcome,
            "confidence": confidence,
            "horizon_days": horizon_days,
            "created_at": now.isoformat(),
            "horizon_date": horizon_date.isoformat(),
            "metadata": json.dumps(metadata)
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
        skipped_recent = 0
        skipped_neutral = 0
        bullish_count = 0
        bearish_count = 0
        
        for signal in signals:
            entity_name = signal.get("entity_name", "")
            ticker = ticker_map.get(entity_name.lower())
            
            for horizon in horizons:
                # Skip if recent prediction exists
                if self.prediction_exists(entity_name, horizon):
                    skipped_recent += 1
                    continue
                
                prediction = self.generate_prediction(signal, horizon)
                if prediction:
                    self.save_prediction(prediction, ticker)
                    new_predictions += 1
                    
                    # Track prediction types
                    if prediction["predicted_outcome"] == "bullish":
                        bullish_count += 1
                    elif prediction["predicted_outcome"] == "bearish":
                        bearish_count += 1
                else:
                    skipped_neutral += 1
        
        print(f"\nGenerated {new_predictions} new predictions:")
        print(f"  Bullish: {bullish_count}")
        print(f"  Bearish: {bearish_count}")
        print(f"Skipped {skipped_recent} (recent predictions exist)")
        print(f"Skipped {skipped_neutral} (neutral/weak signals)")
        
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
