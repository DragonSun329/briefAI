"""Backtest Engine - Run trend radar at historical dates."""

import json
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class BacktestPrediction:
    """A prediction made at a historical date."""
    prediction_date: str
    entity_id: str
    entity_name: str
    entity_type: str
    signal_type: str
    momentum_score: float
    validation_score: float
    validation_status: str
    bucket_id: Optional[str] = None
    rank: int = 0


@dataclass
class BacktestRun:
    """Results of a backtest run."""
    run_id: str
    prediction_date: str
    validation_date: str
    predictions: List[BacktestPrediction]
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)


class BacktestEngine:
    """
    Run trend radar at historical dates to generate predictions.

    Usage:
        engine = BacktestEngine()
        run = engine.run_backtest(
            prediction_date=date(2024, 12, 15),
            validation_date=date(2025, 1, 20),
        )
    """

    def __init__(
        self,
        ground_truth_path: Optional[Path] = None,
        output_dir: Optional[Path] = None,
    ):
        config_dir = Path(__file__).parent.parent / "config"
        self.ground_truth_path = ground_truth_path or config_dir / "ground_truth.json"
        self.output_dir = output_dir or Path(__file__).parent.parent / "data" / "backtests"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.ground_truth = self._load_ground_truth()

    def _load_ground_truth(self) -> Dict:
        """Load ground truth registry."""
        if self.ground_truth_path.exists():
            with open(self.ground_truth_path, encoding="utf-8") as f:
                return json.load(f)
        return {"breakout_events": []}

    def run_backtest(
        self,
        prediction_date: date,
        validation_date: date,
        top_k: int = 20,
        use_wayback: bool = False,
    ) -> BacktestRun:
        """
        Run trend radar at prediction_date, compare to validation_date outcomes.

        Args:
            prediction_date: Date to "travel back" to
            validation_date: Date to validate predictions against
            top_k: Number of top predictions to include
            use_wayback: Whether to fetch historical data from Wayback

        Returns:
            BacktestRun with predictions
        """
        run_id = f"backtest_{prediction_date.isoformat()}_{validation_date.isoformat()}"

        # In full implementation, this would:
        # 1. Load or fetch historical snapshot for prediction_date
        # 2. Run trend aggregator with that data
        # 3. Run signal enricher/validator
        # For MVP, we simulate with synthetic predictions

        predictions = self._generate_predictions(prediction_date, top_k)

        run = BacktestRun(
            run_id=run_id,
            prediction_date=prediction_date.isoformat(),
            validation_date=validation_date.isoformat(),
            predictions=predictions,
            metadata={
                "top_k": top_k,
                "use_wayback": use_wayback,
                "ground_truth_version": self.ground_truth.get("_meta", {}).get("version"),
            },
            created_at=datetime.now().isoformat(),
        )

        # Save run
        self._save_run(run)

        return run

    def _generate_predictions(
        self,
        prediction_date: date,
        top_k: int,
    ) -> List[BacktestPrediction]:
        """
        Generate predictions for a historical date.

        In MVP, this uses ground truth entities as "predictions"
        to demonstrate the scorecard flow.
        """
        predictions = []

        for i, event in enumerate(self.ground_truth.get("breakout_events", [])[:top_k]):
            # Check if this event should have been detectable at prediction_date
            early_date = datetime.fromisoformat(event["early_signal_date"]).date()

            # Only include if prediction_date is after early signal date
            if prediction_date >= early_date:
                predictions.append(BacktestPrediction(
                    prediction_date=prediction_date.isoformat(),
                    entity_id=event["entity_id"],
                    entity_name=event["entity_name"],
                    entity_type=event["entity_type"],
                    signal_type="velocity_spike",
                    momentum_score=85.0 - (i * 5),  # Simulated scores
                    validation_score=0.75 - (i * 0.05),
                    validation_status="validated" if i < 3 else "unvalidated",
                    bucket_id=event.get("category"),
                    rank=i + 1,
                ))

        return predictions

    def _save_run(self, run: BacktestRun):
        """Save backtest run to file."""
        output_file = self.output_dir / f"{run.run_id}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(run.to_dict(), f, ensure_ascii=False, indent=2)

    def load_run(self, run_id: str) -> Optional[BacktestRun]:
        """Load a saved backtest run."""
        run_file = self.output_dir / f"{run_id}.json"
        if not run_file.exists():
            return None

        with open(run_file, encoding="utf-8") as f:
            data = json.load(f)

        predictions = [BacktestPrediction(**p) for p in data.get("predictions", [])]
        return BacktestRun(
            run_id=data["run_id"],
            prediction_date=data["prediction_date"],
            validation_date=data["validation_date"],
            predictions=predictions,
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at", ""),
        )

    def list_runs(self) -> List[str]:
        """List all saved backtest runs."""
        return [f.stem for f in self.output_dir.glob("backtest_*.json")]


if __name__ == "__main__":
    # Example usage
    engine = BacktestEngine()
    run = engine.run_backtest(
        prediction_date=date(2024, 12, 15),
        validation_date=date(2025, 1, 20),
    )
    print(f"Created run: {run.run_id}")
    print(f"Predictions: {len(run.predictions)}")
    for p in run.predictions:
        print(f"  #{p.rank} {p.entity_name}: {p.momentum_score:.0f}")