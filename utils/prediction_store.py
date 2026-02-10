"""
Prediction Store

Registry for tracking predictions made by briefAI signals.
Links divergence alerts to specific, measurable predictions that can be validated.

A prediction is a bet: "This entity will [rise/fall/breakout/decline] within [horizon] days."
We track whether these bets were correct to measure signal quality.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class PredictionType(str, Enum):
    """Types of predictions we can make."""
    RISING = "rising"           # Entity score/attention will increase
    FALLING = "falling"         # Entity score/attention will decrease
    BREAKOUT = "breakout"       # Entity will hit mainstream (>X media mentions)
    DECLINE = "decline"         # Entity will fade from relevance
    STABLE = "stable"           # No significant change expected


class PredictionStatus(str, Enum):
    """Lifecycle status of a prediction."""
    PENDING = "pending"         # Waiting for horizon to pass
    CORRECT = "correct"         # Prediction was validated as correct
    INCORRECT = "incorrect"     # Prediction was wrong
    EXPIRED = "expired"         # Horizon passed, couldn't determine outcome
    CANCELLED = "cancelled"     # Prediction was invalidated (e.g., entity removed)


class PredictionMode(str, Enum):
    """Whether prediction is live or shadow."""
    PRODUCTION = "production"   # Real predictions, affects metrics
    SHADOW = "shadow"           # Test predictions, doesn't affect production metrics


@dataclass
class Prediction:
    """
    A specific, measurable prediction about an entity.
    
    The key insight: every divergence alert is implicitly a prediction.
    "Technical > Financial" means "this entity will attract funding."
    We make these implicit predictions explicit and track their outcomes.
    """
    id: str
    entity_id: str
    entity_name: str
    
    # What we're predicting
    signal_type: str              # Source signal (e.g., "divergence", "momentum_spike")
    prediction_type: PredictionType
    predicted_outcome: str        # Human-readable description
    
    # Confidence and horizon
    confidence: float             # 0.0 to 1.0
    horizon_days: int             # How many days until we validate
    
    # Thresholds for validation
    threshold_value: Optional[float] = None   # What counts as "happened"
    baseline_value: Optional[float] = None    # Value at prediction time
    
    # Source context
    source_divergence_id: Optional[str] = None  # If from divergence detector
    source_alert_id: Optional[str] = None       # If from alert system
    source_metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Lifecycle
    status: PredictionStatus = PredictionStatus.PENDING
    mode: PredictionMode = PredictionMode.PRODUCTION
    
    # Timestamps
    predicted_at: datetime = field(default_factory=datetime.utcnow)
    horizon_date: datetime = field(default=None)
    resolved_at: Optional[datetime] = None
    
    # Outcome (filled after resolution)
    actual_outcome: Optional[str] = None
    actual_value: Optional[float] = None
    outcome_evidence: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if self.horizon_date is None:
            self.horizon_date = self.predicted_at + timedelta(days=self.horizon_days)
    
    def is_past_horizon(self) -> bool:
        """Check if we're past the prediction horizon."""
        return datetime.utcnow() >= self.horizon_date
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        d = asdict(self)
        # Convert enums to values
        d["prediction_type"] = self.prediction_type.value
        d["status"] = self.status.value
        d["mode"] = self.mode.value
        # Convert datetimes to ISO strings
        d["predicted_at"] = self.predicted_at.isoformat()
        d["horizon_date"] = self.horizon_date.isoformat() if self.horizon_date else None
        d["resolved_at"] = self.resolved_at.isoformat() if self.resolved_at else None
        return d
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Prediction":
        """Create from dictionary."""
        d = d.copy()
        d["prediction_type"] = PredictionType(d["prediction_type"])
        d["status"] = PredictionStatus(d["status"])
        d["mode"] = PredictionMode(d["mode"])
        d["predicted_at"] = datetime.fromisoformat(d["predicted_at"])
        d["horizon_date"] = datetime.fromisoformat(d["horizon_date"]) if d.get("horizon_date") else None
        d["resolved_at"] = datetime.fromisoformat(d["resolved_at"]) if d.get("resolved_at") else None
        return cls(**d)


class PredictionStore:
    """
    SQLite-based storage for predictions.
    
    Tracks all predictions made by the system and their outcomes.
    """
    
    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize prediction store.
        
        Args:
            db_path: Path to SQLite database. Defaults to data/predictions.db
        """
        if db_path is None:
            db_path = str(Path(__file__).parent.parent / "data" / "predictions.db")
        
        self.db_path = db_path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
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
        
        # Predictions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS predictions (
                id TEXT PRIMARY KEY,
                entity_id TEXT NOT NULL,
                entity_name TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                prediction_type TEXT NOT NULL,
                predicted_outcome TEXT NOT NULL,
                confidence REAL NOT NULL,
                horizon_days INTEGER NOT NULL,
                threshold_value REAL,
                baseline_value REAL,
                source_divergence_id TEXT,
                source_alert_id TEXT,
                source_metadata TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                mode TEXT NOT NULL DEFAULT 'production',
                predicted_at TIMESTAMP NOT NULL,
                horizon_date TIMESTAMP NOT NULL,
                resolved_at TIMESTAMP,
                actual_outcome TEXT,
                actual_value REAL,
                outcome_evidence TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Indexes for common queries
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_predictions_entity ON predictions(entity_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_predictions_status ON predictions(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_predictions_mode ON predictions(mode)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_predictions_horizon ON predictions(horizon_date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_predictions_signal ON predictions(signal_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_predictions_type ON predictions(prediction_type)")
        
        conn.commit()
        conn.close()
    
    def add_prediction(self, prediction: Prediction) -> Prediction:
        """
        Add a new prediction to the store.
        
        Args:
            prediction: The prediction to store
            
        Returns:
            The stored prediction (with any auto-generated fields)
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO predictions (
                id, entity_id, entity_name, signal_type, prediction_type,
                predicted_outcome, confidence, horizon_days, threshold_value,
                baseline_value, source_divergence_id, source_alert_id,
                source_metadata, status, mode, predicted_at, horizon_date,
                resolved_at, actual_outcome, actual_value, outcome_evidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            prediction.id,
            prediction.entity_id,
            prediction.entity_name,
            prediction.signal_type,
            prediction.prediction_type.value,
            prediction.predicted_outcome,
            prediction.confidence,
            prediction.horizon_days,
            prediction.threshold_value,
            prediction.baseline_value,
            prediction.source_divergence_id,
            prediction.source_alert_id,
            json.dumps(prediction.source_metadata),
            prediction.status.value,
            prediction.mode.value,
            prediction.predicted_at.isoformat(),
            prediction.horizon_date.isoformat(),
            prediction.resolved_at.isoformat() if prediction.resolved_at else None,
            prediction.actual_outcome,
            prediction.actual_value,
            json.dumps(prediction.outcome_evidence),
        ))
        
        conn.commit()
        conn.close()
        return prediction
    
    def get_prediction(self, prediction_id: str) -> Optional[Prediction]:
        """Get a prediction by ID."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM predictions WHERE id = ?", (prediction_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return self._row_to_prediction(row)
        return None
    
    def update_prediction(self, prediction: Prediction) -> Prediction:
        """Update an existing prediction."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE predictions SET
                status = ?,
                resolved_at = ?,
                actual_outcome = ?,
                actual_value = ?,
                outcome_evidence = ?
            WHERE id = ?
        """, (
            prediction.status.value,
            prediction.resolved_at.isoformat() if prediction.resolved_at else None,
            prediction.actual_outcome,
            prediction.actual_value,
            json.dumps(prediction.outcome_evidence),
            prediction.id,
        ))
        
        conn.commit()
        conn.close()
        return prediction
    
    def get_pending_predictions(
        self,
        past_horizon_only: bool = False,
        mode: Optional[PredictionMode] = None,
    ) -> List[Prediction]:
        """
        Get all pending predictions that need resolution.
        
        Args:
            past_horizon_only: Only return predictions past their horizon date
            mode: Filter by prediction mode (production/shadow)
            
        Returns:
            List of pending predictions
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        query = "SELECT * FROM predictions WHERE status = 'pending'"
        params = []
        
        if past_horizon_only:
            query += " AND horizon_date <= ?"
            params.append(datetime.utcnow().isoformat())
        
        if mode:
            query += " AND mode = ?"
            params.append(mode.value)
        
        query += " ORDER BY horizon_date ASC"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        return [self._row_to_prediction(row) for row in rows]
    
    def get_predictions_for_entity(
        self,
        entity_id: str,
        include_resolved: bool = True,
    ) -> List[Prediction]:
        """Get all predictions for an entity."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        query = "SELECT * FROM predictions WHERE entity_id = ?"
        params = [entity_id]
        
        if not include_resolved:
            query += " AND status = 'pending'"
        
        query += " ORDER BY predicted_at DESC"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        return [self._row_to_prediction(row) for row in rows]
    
    def get_predictions_by_signal_type(
        self,
        signal_type: str,
        status: Optional[PredictionStatus] = None,
        mode: Optional[PredictionMode] = None,
    ) -> List[Prediction]:
        """Get predictions by signal type."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        query = "SELECT * FROM predictions WHERE signal_type = ?"
        params = [signal_type]
        
        if status:
            query += " AND status = ?"
            params.append(status.value)
        
        if mode:
            query += " AND mode = ?"
            params.append(mode.value)
        
        query += " ORDER BY predicted_at DESC"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        return [self._row_to_prediction(row) for row in rows]
    
    def get_resolved_predictions(
        self,
        since: Optional[datetime] = None,
        mode: Optional[PredictionMode] = None,
    ) -> List[Prediction]:
        """Get all resolved predictions."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        query = "SELECT * FROM predictions WHERE status IN ('correct', 'incorrect')"
        params = []
        
        if since:
            query += " AND resolved_at >= ?"
            params.append(since.isoformat())
        
        if mode:
            query += " AND mode = ?"
            params.append(mode.value)
        
        query += " ORDER BY resolved_at DESC"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        return [self._row_to_prediction(row) for row in rows]
    
    def get_stats(self, mode: Optional[PredictionMode] = None) -> Dict[str, Any]:
        """Get prediction statistics."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        mode_filter = " AND mode = ?" if mode else ""
        mode_params = [mode.value] if mode else []
        
        # Total counts by status
        cursor.execute(f"""
            SELECT status, COUNT(*) as count
            FROM predictions
            WHERE 1=1 {mode_filter}
            GROUP BY status
        """, mode_params)
        
        status_counts = {row["status"]: row["count"] for row in cursor.fetchall()}
        
        # Accuracy by signal type
        cursor.execute(f"""
            SELECT 
                signal_type,
                SUM(CASE WHEN status = 'correct' THEN 1 ELSE 0 END) as correct,
                SUM(CASE WHEN status = 'incorrect' THEN 1 ELSE 0 END) as incorrect,
                COUNT(*) as total
            FROM predictions
            WHERE status IN ('correct', 'incorrect') {mode_filter}
            GROUP BY signal_type
        """, mode_params)
        
        accuracy_by_signal = {}
        for row in cursor.fetchall():
            resolved = row["correct"] + row["incorrect"]
            if resolved > 0:
                accuracy_by_signal[row["signal_type"]] = {
                    "correct": row["correct"],
                    "incorrect": row["incorrect"],
                    "total": row["total"],
                    "accuracy": row["correct"] / resolved,
                }
        
        # Average confidence for correct vs incorrect
        cursor.execute(f"""
            SELECT 
                status,
                AVG(confidence) as avg_confidence
            FROM predictions
            WHERE status IN ('correct', 'incorrect') {mode_filter}
            GROUP BY status
        """, mode_params)
        
        confidence_by_status = {row["status"]: row["avg_confidence"] for row in cursor.fetchall()}
        
        conn.close()
        
        total_resolved = status_counts.get("correct", 0) + status_counts.get("incorrect", 0)
        overall_accuracy = (
            status_counts.get("correct", 0) / total_resolved
            if total_resolved > 0 else 0
        )
        
        return {
            "total_predictions": sum(status_counts.values()),
            "pending": status_counts.get("pending", 0),
            "correct": status_counts.get("correct", 0),
            "incorrect": status_counts.get("incorrect", 0),
            "expired": status_counts.get("expired", 0),
            "overall_accuracy": overall_accuracy,
            "accuracy_by_signal": accuracy_by_signal,
            "avg_confidence_correct": confidence_by_status.get("correct"),
            "avg_confidence_incorrect": confidence_by_status.get("incorrect"),
        }
    
    def _row_to_prediction(self, row: sqlite3.Row) -> Prediction:
        """Convert database row to Prediction object."""
        return Prediction(
            id=row["id"],
            entity_id=row["entity_id"],
            entity_name=row["entity_name"],
            signal_type=row["signal_type"],
            prediction_type=PredictionType(row["prediction_type"]),
            predicted_outcome=row["predicted_outcome"],
            confidence=row["confidence"],
            horizon_days=row["horizon_days"],
            threshold_value=row["threshold_value"],
            baseline_value=row["baseline_value"],
            source_divergence_id=row["source_divergence_id"],
            source_alert_id=row["source_alert_id"],
            source_metadata=json.loads(row["source_metadata"]) if row["source_metadata"] else {},
            status=PredictionStatus(row["status"]),
            mode=PredictionMode(row["mode"]),
            predicted_at=datetime.fromisoformat(row["predicted_at"]),
            horizon_date=datetime.fromisoformat(row["horizon_date"]) if row["horizon_date"] else None,
            resolved_at=datetime.fromisoformat(row["resolved_at"]) if row["resolved_at"] else None,
            actual_outcome=row["actual_outcome"],
            actual_value=row["actual_value"],
            outcome_evidence=json.loads(row["outcome_evidence"]) if row["outcome_evidence"] else {},
        )


def create_prediction_from_divergence(
    divergence,
    horizon_days: int = 30,
    confidence_multiplier: float = 1.0,
    mode: PredictionMode = PredictionMode.PRODUCTION,
) -> Prediction:
    """
    Create a prediction from a SignalDivergence.
    
    Maps divergence interpretation to prediction type:
    - OPPORTUNITY + high technical -> RISING (funding will follow)
    - OPPORTUNITY + high product -> BREAKOUT (will hit mainstream)
    - RISK + high financial -> FALLING (hype will fade)
    - RISK + high media -> DECLINE (substance won't follow)
    
    Args:
        divergence: SignalDivergence object
        horizon_days: Days until prediction should be validated
        confidence_multiplier: Adjust confidence (e.g., 0.5 for shadow mode)
        mode: Production or shadow
        
    Returns:
        Prediction object ready to store
    """
    from .signal_models import DivergenceInterpretation, SignalCategory
    
    # Map divergence to prediction type
    if divergence.interpretation == DivergenceInterpretation.OPPORTUNITY:
        if divergence.high_signal_category == SignalCategory.TECHNICAL:
            pred_type = PredictionType.RISING
            outcome = f"Funding/attention for {divergence.entity_name} will increase (technical leads financial)"
        elif divergence.high_signal_category == SignalCategory.PRODUCT_TRACTION:
            pred_type = PredictionType.BREAKOUT
            outcome = f"{divergence.entity_name} will hit mainstream media (organic growth story)"
        else:
            pred_type = PredictionType.RISING
            outcome = f"{divergence.entity_name} will gain momentum"
    
    elif divergence.interpretation == DivergenceInterpretation.RISK:
        if divergence.high_signal_category == SignalCategory.FINANCIAL:
            pred_type = PredictionType.FALLING
            outcome = f"{divergence.entity_name} funding won't translate to adoption"
        elif divergence.high_signal_category == SignalCategory.MEDIA_SENTIMENT:
            pred_type = PredictionType.DECLINE
            outcome = f"{divergence.entity_name} hype will fade without substance"
        else:
            pred_type = PredictionType.FALLING
            outcome = f"{divergence.entity_name} will lose momentum"
    
    else:
        pred_type = PredictionType.STABLE
        outcome = f"{divergence.entity_name} shows anomalous signal pattern"
    
    return Prediction(
        id=str(uuid.uuid4()),
        entity_id=divergence.entity_id,
        entity_name=divergence.entity_name,
        signal_type="divergence",
        prediction_type=pred_type,
        predicted_outcome=outcome,
        confidence=min(1.0, divergence.confidence * confidence_multiplier),
        horizon_days=horizon_days,
        threshold_value=divergence.divergence_magnitude * 0.5,  # Threshold is half the magnitude
        baseline_value=divergence.low_signal_score,  # Track from the low signal
        source_divergence_id=divergence.id,
        source_metadata={
            "divergence_type": divergence.divergence_type.value,
            "high_category": divergence.high_signal_category.value,
            "high_score": divergence.high_signal_score,
            "low_category": divergence.low_signal_category.value,
            "low_score": divergence.low_signal_score,
            "magnitude": divergence.divergence_magnitude,
        },
        mode=mode,
    )


if __name__ == "__main__":
    # Quick test
    store = PredictionStore()
    
    # Create a test prediction
    pred = Prediction(
        id=str(uuid.uuid4()),
        entity_id="test-entity",
        entity_name="Test Company",
        signal_type="test",
        prediction_type=PredictionType.RISING,
        predicted_outcome="Test company will grow",
        confidence=0.75,
        horizon_days=30,
    )
    
    store.add_prediction(pred)
    print(f"Added prediction: {pred.id}")
    
    # Retrieve it
    retrieved = store.get_prediction(pred.id)
    print(f"Retrieved: {retrieved.entity_name} - {retrieved.predicted_outcome}")
    
    # Get stats
    stats = store.get_stats()
    print(f"Stats: {stats}")
