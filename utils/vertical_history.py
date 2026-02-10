"""
Vertical History Tracking

Stores daily vertical snapshots for:
- Trend detection (7d, 30d momentum)
- Prediction tracking (did our signals pan out?)
- Historical analysis

Storage: SQLite database at data/vertical_history.db
"""

import json
import sqlite3
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import statistics


class VerticalHistory:
    """
    Stores and retrieves vertical signal history.
    
    Usage:
        history = VerticalHistory()
        history.save_snapshot(profiles)
        momentum = history.get_momentum("ai_healthcare", days=7)
    """
    
    def __init__(self, db_path: Optional[str] = None):
        """Initialize with database path."""
        if db_path is None:
            db_path = str(Path(__file__).parent.parent / "data" / "vertical_history.db")
        
        self.db_path = db_path
        self._ensure_tables()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection with row factory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _ensure_tables(self):
        """Create tables if they don't exist."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Daily snapshots table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vertical_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vertical_id TEXT NOT NULL,
                snapshot_date DATE NOT NULL,
                tech_momentum_score REAL,
                hype_score REAL,
                investment_score REAL,
                maturity REAL,
                hype_phase TEXT,
                divergence_type TEXT,
                divergence_magnitude REAL,
                entity_count INTEGER,
                raw_data TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(vertical_id, snapshot_date)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_vertical ON vertical_snapshots(vertical_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_date ON vertical_snapshots(snapshot_date)")
        
        # Predictions table (for tracking accuracy)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vertical_predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vertical_id TEXT NOT NULL,
                prediction_date DATE NOT NULL,
                prediction_type TEXT NOT NULL,
                predicted_outcome TEXT NOT NULL,
                confidence REAL,
                rationale TEXT,
                actual_outcome TEXT,
                outcome_date DATE,
                accuracy_score REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_predictions_vertical ON vertical_predictions(vertical_id)")
        
        # Alerts history table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vertical_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vertical_id TEXT NOT NULL,
                alert_date DATE NOT NULL,
                alert_type TEXT NOT NULL,
                severity TEXT,
                message TEXT,
                tech_score REAL,
                hype_score REAL,
                investment_score REAL,
                resolved INTEGER DEFAULT 0,
                resolved_date DATE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_alerts_date ON vertical_alerts(alert_date)")
        
        conn.commit()
        conn.close()
    
    def save_snapshot(self, profiles: List[Dict[str, Any]], snapshot_date: Optional[date] = None):
        """
        Save daily vertical snapshots.
        
        Args:
            profiles: List of vertical profiles from VerticalScorer
            snapshot_date: Date for snapshot (defaults to today)
        """
        if snapshot_date is None:
            snapshot_date = date.today()
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        for profile in profiles:
            vertical_id = profile.get("vertical_id")
            if not vertical_id:
                continue
            
            divergence = profile.get("divergence_signal", {})
            
            cursor.execute("""
                INSERT OR REPLACE INTO vertical_snapshots (
                    vertical_id, snapshot_date, tech_momentum_score,
                    hype_score, investment_score, maturity, hype_phase,
                    divergence_type, divergence_magnitude, entity_count, raw_data
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                vertical_id,
                snapshot_date.isoformat(),
                profile.get("tech_momentum_score"),
                profile.get("hype_score"),
                profile.get("investment_score"),
                profile.get("maturity"),
                profile.get("hype_phase"),
                divergence.get("type"),
                divergence.get("magnitude"),
                profile.get("entity_count"),
                json.dumps(profile),
            ))
        
        conn.commit()
        conn.close()
        
        return len(profiles)
    
    def get_snapshot(self, vertical_id: str, snapshot_date: date) -> Optional[Dict]:
        """Get snapshot for a specific date."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM vertical_snapshots
            WHERE vertical_id = ? AND snapshot_date = ?
        """, (vertical_id, snapshot_date.isoformat()))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return dict(row)
        return None
    
    def get_history(
        self,
        vertical_id: str,
        days: int = 30,
        end_date: Optional[date] = None
    ) -> List[Dict]:
        """
        Get historical snapshots for a vertical.
        
        Args:
            vertical_id: Vertical ID
            days: Number of days of history
            end_date: End date (defaults to today)
        
        Returns:
            List of snapshots ordered by date ascending
        """
        if end_date is None:
            end_date = date.today()
        
        start_date = end_date - timedelta(days=days)
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM vertical_snapshots
            WHERE vertical_id = ? AND snapshot_date >= ? AND snapshot_date <= ?
            ORDER BY snapshot_date ASC
        """, (vertical_id, start_date.isoformat(), end_date.isoformat()))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def get_momentum(
        self,
        vertical_id: str,
        days: int = 7,
        metric: str = "tech_momentum_score"
    ) -> Optional[Dict[str, Any]]:
        """
        Calculate momentum (change) for a vertical over N days.
        
        Args:
            vertical_id: Vertical ID
            days: Number of days to measure
            metric: Which metric to track
        
        Returns:
            Dict with current, previous, change, percent_change
        """
        history = self.get_history(vertical_id, days=days)
        
        if len(history) < 2:
            return None
        
        current = history[-1].get(metric)
        previous = history[0].get(metric)
        
        if current is None or previous is None:
            return None
        
        change = current - previous
        percent_change = (change / previous * 100) if previous != 0 else 0
        
        return {
            "vertical_id": vertical_id,
            "metric": metric,
            "days": days,
            "current": current,
            "previous": previous,
            "change": round(change, 2),
            "percent_change": round(percent_change, 2),
            "trend": "up" if change > 0 else "down" if change < 0 else "flat",
            "data_points": len(history),
        }
    
    def get_all_momentum(
        self,
        days: int = 7,
        min_change: float = 5.0
    ) -> List[Dict[str, Any]]:
        """
        Get momentum for all verticals with significant changes.
        
        Args:
            days: Number of days
            min_change: Minimum absolute change to include
        
        Returns:
            List of momentum records sorted by percent change
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Get all unique vertical IDs
        cursor.execute("SELECT DISTINCT vertical_id FROM vertical_snapshots")
        vertical_ids = [row["vertical_id"] for row in cursor.fetchall()]
        conn.close()
        
        results = []
        for vid in vertical_ids:
            for metric in ["tech_momentum_score", "hype_score", "investment_score"]:
                momentum = self.get_momentum(vid, days=days, metric=metric)
                if momentum and abs(momentum["change"]) >= min_change:
                    results.append(momentum)
        
        # Sort by absolute percent change
        results.sort(key=lambda x: abs(x["percent_change"]), reverse=True)
        
        return results
    
    def save_prediction(
        self,
        vertical_id: str,
        prediction_type: str,
        predicted_outcome: str,
        confidence: float,
        rationale: Optional[str] = None
    ) -> int:
        """
        Save a prediction for later validation.
        
        Args:
            vertical_id: Vertical ID
            prediction_type: Type of prediction (e.g., "hype_crash", "tech_growth")
            predicted_outcome: What we predict will happen
            confidence: Confidence level (0-1)
            rationale: Why we made this prediction
        
        Returns:
            Prediction ID
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO vertical_predictions (
                vertical_id, prediction_date, prediction_type,
                predicted_outcome, confidence, rationale
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            vertical_id,
            date.today().isoformat(),
            prediction_type,
            predicted_outcome,
            confidence,
            rationale,
        ))
        
        prediction_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return prediction_id
    
    def validate_prediction(
        self,
        prediction_id: int,
        actual_outcome: str,
        accuracy_score: float
    ):
        """
        Record the actual outcome of a prediction.
        
        Args:
            prediction_id: ID of the prediction
            actual_outcome: What actually happened
            accuracy_score: How accurate was the prediction (0-1)
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE vertical_predictions
            SET actual_outcome = ?, outcome_date = ?, accuracy_score = ?
            WHERE id = ?
        """, (actual_outcome, date.today().isoformat(), accuracy_score, prediction_id))
        
        conn.commit()
        conn.close()
    
    def get_prediction_accuracy(self, days: int = 90) -> Dict[str, Any]:
        """
        Calculate overall prediction accuracy.
        
        Returns:
            Dict with accuracy stats
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN accuracy_score IS NOT NULL THEN 1 ELSE 0 END) as validated,
                AVG(accuracy_score) as avg_accuracy,
                prediction_type,
                COUNT(*) as type_count,
                AVG(accuracy_score) as type_accuracy
            FROM vertical_predictions
            WHERE prediction_date >= ?
            GROUP BY prediction_type
        """, (cutoff,))
        
        rows = cursor.fetchall()
        conn.close()
        
        by_type = {}
        total = 0
        validated = 0
        accuracy_scores = []
        
        for row in rows:
            by_type[row["prediction_type"]] = {
                "count": row["type_count"],
                "accuracy": row["type_accuracy"],
            }
            total += row["type_count"]
            if row["type_accuracy"]:
                accuracy_scores.append(row["type_accuracy"])
        
        return {
            "total_predictions": total,
            "validated_predictions": len(accuracy_scores),
            "average_accuracy": statistics.mean(accuracy_scores) if accuracy_scores else None,
            "by_type": by_type,
            "period_days": days,
        }
    
    def save_alert(
        self,
        vertical_id: str,
        alert_type: str,
        severity: str,
        message: str,
        tech_score: float,
        hype_score: float,
        investment_score: float
    ) -> int:
        """Save an alert for tracking."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO vertical_alerts (
                vertical_id, alert_date, alert_type, severity,
                message, tech_score, hype_score, investment_score
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            vertical_id,
            date.today().isoformat(),
            alert_type,
            severity,
            message,
            tech_score,
            hype_score,
            investment_score,
        ))
        
        alert_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return alert_id
    
    def get_snapshot_count(self) -> Dict[str, int]:
        """Get count of snapshots by vertical."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT vertical_id, COUNT(*) as count
            FROM vertical_snapshots
            GROUP BY vertical_id
        """)
        
        result = {row["vertical_id"]: row["count"] for row in cursor.fetchall()}
        conn.close()
        
        return result


# Singleton instance
_history: Optional[VerticalHistory] = None


def get_vertical_history() -> VerticalHistory:
    """Get singleton VerticalHistory instance."""
    global _history
    if _history is None:
        _history = VerticalHistory()
    return _history
