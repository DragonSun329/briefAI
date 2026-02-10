"""
Vertical Performance Validator

Validates vertical predictions against actual market performance:
1. Fetches stock prices for vertical tickers
2. Compares predicted outcomes vs actual price movements
3. Updates prediction accuracy scores
4. Tracks validation metrics over time

Bloomberg-level signal validation.
"""

import json
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import sqlite3

# Try to import yfinance for stock data
try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False


class VerticalValidator:
    """
    Validates vertical predictions against market performance.
    
    Usage:
        validator = VerticalValidator()
        results = validator.validate_predictions(days_ago=30)
    """
    
    def __init__(
        self,
        tickers_config_path: Optional[str] = None,
        history_db_path: Optional[str] = None,
    ):
        """Initialize validator with config paths."""
        base_path = Path(__file__).parent.parent
        
        self.tickers_config = tickers_config_path or str(
            base_path / "config" / "vertical_tickers.json"
        )
        self.history_db = history_db_path or str(
            base_path / "data" / "vertical_history.db"
        )
        
        self.ticker_mapping = self._load_ticker_mapping()
    
    def _load_ticker_mapping(self) -> Dict[str, Any]:
        """Load vertical to ticker mapping."""
        config_path = Path(self.tickers_config)
        if not config_path.exists():
            return {}
        
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    
    def _get_history_connection(self) -> Optional[sqlite3.Connection]:
        """Get connection to history database."""
        if not Path(self.history_db).exists():
            return None
        conn = sqlite3.connect(self.history_db)
        conn.row_factory = sqlite3.Row
        return conn
    
    def get_vertical_tickers(self, vertical_id: str) -> Dict[str, List[str]]:
        """Get all tickers for a vertical."""
        verticals = self.ticker_mapping.get("verticals", {})
        return verticals.get(vertical_id, {})
    
    def fetch_stock_performance(
        self,
        tickers: List[str],
        start_date: date,
        end_date: Optional[date] = None
    ) -> Dict[str, Dict[str, Any]]:
        """
        Fetch stock performance for tickers over a period.
        
        Returns:
            Dict mapping ticker to performance metrics
        """
        if not YFINANCE_AVAILABLE:
            return {}
        
        if end_date is None:
            end_date = date.today()
        
        results = {}
        
        for ticker in tickers:
            try:
                stock = yf.Ticker(ticker)
                hist = stock.history(
                    start=start_date.isoformat(),
                    end=end_date.isoformat()
                )
                
                if hist.empty or len(hist) < 2:
                    continue
                
                start_price = hist["Close"].iloc[0]
                end_price = hist["Close"].iloc[-1]
                
                change = end_price - start_price
                pct_change = (change / start_price) * 100 if start_price > 0 else 0
                
                results[ticker] = {
                    "start_price": round(start_price, 2),
                    "end_price": round(end_price, 2),
                    "change": round(change, 2),
                    "pct_change": round(pct_change, 2),
                    "days": len(hist),
                    "trend": "up" if pct_change > 2 else "down" if pct_change < -2 else "flat",
                }
            except Exception as e:
                results[ticker] = {"error": str(e)}
        
        return results
    
    def compute_vertical_performance(
        self,
        vertical_id: str,
        start_date: date,
        end_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """
        Compute aggregate performance for a vertical based on its tickers.
        
        Uses weighted average:
        - Primary tickers: 3x weight
        - Proxy tickers: 1x weight
        - ETFs: 2x weight
        """
        ticker_config = self.get_vertical_tickers(vertical_id)
        if not ticker_config:
            return {"error": "No tickers configured for vertical"}
        
        all_results = {}
        
        # Fetch primary tickers (3x weight)
        primary = ticker_config.get("primary_tickers", [])
        if primary:
            primary_perf = self.fetch_stock_performance(primary, start_date, end_date)
            for ticker, data in primary_perf.items():
                if "error" not in data:
                    data["weight"] = 3.0
                    all_results[ticker] = data
        
        # Fetch proxy tickers (1x weight)
        proxy = ticker_config.get("proxy_tickers", [])
        if proxy:
            proxy_perf = self.fetch_stock_performance(proxy, start_date, end_date)
            for ticker, data in proxy_perf.items():
                if "error" not in data:
                    data["weight"] = 1.0
                    all_results[ticker] = data
        
        # Fetch ETFs (2x weight)
        etfs = ticker_config.get("etfs", [])
        if etfs:
            etf_perf = self.fetch_stock_performance(etfs, start_date, end_date)
            for ticker, data in etf_perf.items():
                if "error" not in data:
                    data["weight"] = 2.0
                    all_results[ticker] = data
        
        if not all_results:
            return {"error": "No valid ticker data"}
        
        # Compute weighted average
        total_weight = 0
        weighted_pct = 0
        
        for ticker, data in all_results.items():
            weight = data.get("weight", 1.0)
            pct = data.get("pct_change", 0)
            weighted_pct += pct * weight
            total_weight += weight
        
        avg_pct = weighted_pct / total_weight if total_weight > 0 else 0
        
        return {
            "vertical_id": vertical_id,
            "start_date": start_date.isoformat(),
            "end_date": (end_date or date.today()).isoformat(),
            "weighted_avg_pct_change": round(avg_pct, 2),
            "trend": "up" if avg_pct > 2 else "down" if avg_pct < -2 else "flat",
            "ticker_count": len(all_results),
            "tickers": all_results,
        }
    
    def get_pending_predictions(self, min_age_days: int = 30) -> List[Dict]:
        """
        Get predictions that are old enough to validate.
        
        Args:
            min_age_days: Minimum age in days before validating
        
        Returns:
            List of prediction records
        """
        conn = self._get_history_connection()
        if not conn:
            return []
        
        cutoff = (date.today() - timedelta(days=min_age_days)).isoformat()
        
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM vertical_predictions
            WHERE prediction_date <= ? AND actual_outcome IS NULL
            ORDER BY prediction_date ASC
        """, (cutoff,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def validate_prediction(
        self,
        prediction: Dict,
    ) -> Dict[str, Any]:
        """
        Validate a single prediction against actual market performance.
        
        Args:
            prediction: Prediction record from database
        
        Returns:
            Validation result with accuracy score
        """
        vertical_id = prediction["vertical_id"]
        prediction_date = date.fromisoformat(prediction["prediction_date"])
        predicted_outcome = prediction["predicted_outcome"]
        
        # Calculate validation period (30 days from prediction)
        end_date = prediction_date + timedelta(days=30)
        if end_date > date.today():
            end_date = date.today()
        
        # Get actual market performance
        perf = self.compute_vertical_performance(
            vertical_id,
            prediction_date,
            end_date
        )
        
        if "error" in perf:
            return {
                "prediction_id": prediction["id"],
                "status": "error",
                "error": perf["error"],
            }
        
        actual_pct = perf["weighted_avg_pct_change"]
        actual_trend = perf["trend"]
        
        # Determine actual outcome
        if predicted_outcome == "hype_increase_30d":
            # We predicted hype would catch up (for alpha opportunities)
            # Validate by checking if stock price increased
            if actual_pct > 5:
                actual_outcome = "hype_increased"
                accuracy = 1.0
            elif actual_pct > 0:
                actual_outcome = "slight_increase"
                accuracy = 0.7
            elif actual_pct > -5:
                actual_outcome = "flat"
                accuracy = 0.4
            else:
                actual_outcome = "decreased"
                accuracy = 0.0
                
        elif predicted_outcome == "hype_decrease_30d":
            # We predicted hype would crash (for bubble warnings)
            # Validate by checking if stock price decreased
            if actual_pct < -5:
                actual_outcome = "hype_crashed"
                accuracy = 1.0
            elif actual_pct < 0:
                actual_outcome = "slight_decrease"
                accuracy = 0.7
            elif actual_pct < 5:
                actual_outcome = "flat"
                accuracy = 0.4
            else:
                actual_outcome = "increased"
                accuracy = 0.0
        else:
            actual_outcome = actual_trend
            accuracy = 0.5
        
        return {
            "prediction_id": prediction["id"],
            "vertical_id": vertical_id,
            "predicted_outcome": predicted_outcome,
            "actual_outcome": actual_outcome,
            "actual_pct_change": actual_pct,
            "accuracy_score": accuracy,
            "validation_period_days": (end_date - prediction_date).days,
            "ticker_count": perf["ticker_count"],
        }
    
    def validate_all_pending(self, min_age_days: int = 30) -> Dict[str, Any]:
        """
        Validate all pending predictions.
        
        Returns:
            Summary of validation results
        """
        predictions = self.get_pending_predictions(min_age_days)
        
        if not predictions:
            return {
                "status": "no_pending",
                "message": f"No predictions older than {min_age_days} days to validate",
            }
        
        results = []
        for pred in predictions:
            result = self.validate_prediction(pred)
            results.append(result)
            
            # Update database if validation succeeded
            if result.get("accuracy_score") is not None:
                self._update_prediction_outcome(
                    prediction_id=result["prediction_id"],
                    actual_outcome=result["actual_outcome"],
                    accuracy_score=result["accuracy_score"],
                )
        
        # Compute summary
        valid_results = [r for r in results if "accuracy_score" in r]
        avg_accuracy = (
            sum(r["accuracy_score"] for r in valid_results) / len(valid_results)
            if valid_results else None
        )
        
        return {
            "total_validated": len(valid_results),
            "errors": len(results) - len(valid_results),
            "average_accuracy": round(avg_accuracy, 3) if avg_accuracy else None,
            "results": results,
        }
    
    def _update_prediction_outcome(
        self,
        prediction_id: int,
        actual_outcome: str,
        accuracy_score: float
    ):
        """Update prediction with actual outcome."""
        conn = self._get_history_connection()
        if not conn:
            return
        
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE vertical_predictions
            SET actual_outcome = ?, outcome_date = ?, accuracy_score = ?
            WHERE id = ?
        """, (actual_outcome, date.today().isoformat(), accuracy_score, prediction_id))
        
        conn.commit()
        conn.close()
    
    def get_validation_summary(self, days: int = 90) -> Dict[str, Any]:
        """Get summary of validation accuracy."""
        conn = self._get_history_connection()
        if not conn:
            return {}
        
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        
        cursor = conn.cursor()
        
        # Overall stats
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN accuracy_score IS NOT NULL THEN 1 ELSE 0 END) as validated,
                AVG(accuracy_score) as avg_accuracy
            FROM vertical_predictions
            WHERE prediction_date >= ?
        """, (cutoff,))
        
        overall = dict(cursor.fetchone())
        
        # By prediction type
        cursor.execute("""
            SELECT 
                prediction_type,
                COUNT(*) as count,
                AVG(accuracy_score) as accuracy
            FROM vertical_predictions
            WHERE prediction_date >= ? AND accuracy_score IS NOT NULL
            GROUP BY prediction_type
        """, (cutoff,))
        
        by_type = {row["prediction_type"]: {
            "count": row["count"],
            "accuracy": round(row["accuracy"], 3) if row["accuracy"] else None
        } for row in cursor.fetchall()}
        
        # By vertical
        cursor.execute("""
            SELECT 
                vertical_id,
                COUNT(*) as count,
                AVG(accuracy_score) as accuracy
            FROM vertical_predictions
            WHERE prediction_date >= ? AND accuracy_score IS NOT NULL
            GROUP BY vertical_id
            ORDER BY accuracy DESC
        """, (cutoff,))
        
        by_vertical = {row["vertical_id"]: {
            "count": row["count"],
            "accuracy": round(row["accuracy"], 3) if row["accuracy"] else None
        } for row in cursor.fetchall()}
        
        conn.close()
        
        return {
            "period_days": days,
            "overall": overall,
            "by_type": by_type,
            "by_vertical": by_vertical,
        }


# Singleton
_validator: Optional[VerticalValidator] = None


def get_vertical_validator() -> VerticalValidator:
    """Get singleton validator instance."""
    global _validator
    if _validator is None:
        _validator = VerticalValidator()
    return _validator
