"""Scorecard Generator - Compare backtest predictions to ground truth outcomes."""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from utils.backtest_engine import BacktestRun, BacktestPrediction


@dataclass
class PredictionOutcome:
    """Outcome evaluation for a single prediction."""
    entity_id: str
    entity_name: str
    predicted_rank: int
    momentum_score: float
    hit: bool  # Did this entity break out?
    lead_time_weeks: Optional[float] = None  # Weeks before mainstream
    mainstream_date: Optional[str] = None
    mainstream_source: Optional[str] = None
    notes: str = ""


@dataclass
class Scorecard:
    """Backtest scorecard with metrics."""
    run_id: str
    prediction_date: str
    validation_date: str

    # Core metrics
    precision_at_k: float  # Of top K, how many hit?
    recall: float  # Of known breakouts, how many did we detect?
    avg_lead_time_weeks: float
    miss_rate: float  # Known breakouts we missed

    # Details
    total_predictions: int
    total_hits: int
    total_misses: int
    total_false_positives: int

    # Breakdowns
    hits: List[PredictionOutcome]
    misses: List[PredictionOutcome]  # In ground truth but not predicted
    false_positives: List[PredictionOutcome]  # Predicted but didn't break out

    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)

    def format_summary(self) -> str:
        """Format scorecard as human-readable summary."""
        lines = [
            "=" * 60,
            f"SHADOW MODE BACKTEST: {self.prediction_date} -> {self.validation_date}",
            "=" * 60,
            "",
            f"PRECISION@{self.total_predictions}: {self.total_hits}/{self.total_predictions} ({self.precision_at_k:.0%})",
            f"AVG LEAD TIME: {self.avg_lead_time_weeks:.1f} weeks before mainstream",
            "",
            "TOP HITS:",
        ]

        for hit in self.hits[:5]:
            lead = f"{hit.lead_time_weeks:.0f}w lead" if hit.lead_time_weeks else "N/A"
            lines.append(f"  + {hit.entity_name:<15} - Rank #{hit.predicted_rank}, {lead}")

        if self.misses:
            lines.append("")
            lines.append("MISSES (in ground truth but not detected):")
            for miss in self.misses[:3]:
                lines.append(f"  - {miss.entity_name:<15} - First detected after mainstream")

        if self.false_positives:
            lines.append("")
            lines.append("FALSE POSITIVES (high score but didn't break out):")
            for fp in self.false_positives[:3]:
                lines.append(f"  ? {fp.entity_name:<15} - Score {fp.momentum_score:.0f}, no mainstream yet")

        return "\n".join(lines)


class ScorecardGenerator:
    """Generate scorecards from backtest runs."""

    def __init__(self, ground_truth_path: Optional[Path] = None):
        config_dir = Path(__file__).parent.parent / "config"
        self.ground_truth_path = ground_truth_path or config_dir / "ground_truth.json"
        self.ground_truth = self._load_ground_truth()

    def _load_ground_truth(self) -> Dict:
        """Load ground truth registry."""
        if self.ground_truth_path.exists():
            with open(self.ground_truth_path, encoding="utf-8") as f:
                return json.load(f)
        return {"breakout_events": []}

    def generate_scorecard(self, run: BacktestRun) -> Scorecard:
        """
        Generate scorecard from backtest run.

        Compares predictions to ground truth breakout events.
        """
        prediction_date = date.fromisoformat(run.prediction_date)
        validation_date = date.fromisoformat(run.validation_date)

        # Build ground truth lookup
        gt_entities: Dict[str, Dict] = {}
        for event in self.ground_truth.get("breakout_events", []):
            breakout_date = date.fromisoformat(event["breakout_date"])
            # Only count breakouts that happened before validation date
            if breakout_date <= validation_date:
                gt_entities[event["entity_id"]] = event

        # Evaluate each prediction
        hits: List[PredictionOutcome] = []
        false_positives: List[PredictionOutcome] = []
        predicted_ids: Set[str] = set()

        for pred in run.predictions:
            predicted_ids.add(pred.entity_id)

            if pred.entity_id in gt_entities:
                event = gt_entities[pred.entity_id]
                breakout_date = date.fromisoformat(event["breakout_date"])

                # Calculate lead time
                lead_time_days = (breakout_date - prediction_date).days
                lead_time_weeks = lead_time_days / 7 if lead_time_days > 0 else 0

                # Get first mainstream source
                mainstream_sources = event.get("mainstream_sources", [])
                first_source = mainstream_sources[0] if mainstream_sources else {}

                hits.append(PredictionOutcome(
                    entity_id=pred.entity_id,
                    entity_name=pred.entity_name,
                    predicted_rank=pred.rank,
                    momentum_score=pred.momentum_score,
                    hit=True,
                    lead_time_weeks=lead_time_weeks,
                    mainstream_date=event["breakout_date"],
                    mainstream_source=first_source.get("source"),
                ))
            else:
                false_positives.append(PredictionOutcome(
                    entity_id=pred.entity_id,
                    entity_name=pred.entity_name,
                    predicted_rank=pred.rank,
                    momentum_score=pred.momentum_score,
                    hit=False,
                    notes="Not in ground truth or breakout after validation date",
                ))

        # Find misses (in ground truth but not predicted)
        misses: List[PredictionOutcome] = []
        for entity_id, event in gt_entities.items():
            if entity_id not in predicted_ids:
                misses.append(PredictionOutcome(
                    entity_id=entity_id,
                    entity_name=event["entity_name"],
                    predicted_rank=0,
                    momentum_score=0,
                    hit=False,
                    mainstream_date=event["breakout_date"],
                    notes="In ground truth but not detected",
                ))

        # Calculate metrics
        total_predictions = len(run.predictions)
        total_hits = len(hits)
        total_gt = len(gt_entities)

        precision = total_hits / total_predictions if total_predictions > 0 else 0
        recall = total_hits / total_gt if total_gt > 0 else 0
        miss_rate = len(misses) / total_gt if total_gt > 0 else 0

        lead_times = [h.lead_time_weeks for h in hits if h.lead_time_weeks is not None]
        avg_lead_time = sum(lead_times) / len(lead_times) if lead_times else 0

        return Scorecard(
            run_id=run.run_id,
            prediction_date=run.prediction_date,
            validation_date=run.validation_date,
            precision_at_k=precision,
            recall=recall,
            avg_lead_time_weeks=avg_lead_time,
            miss_rate=miss_rate,
            total_predictions=total_predictions,
            total_hits=total_hits,
            total_misses=len(misses),
            total_false_positives=len(false_positives),
            hits=hits,
            misses=misses,
            false_positives=false_positives,
            created_at=datetime.now().isoformat(),
        )


if __name__ == "__main__":
    # Example usage
    from utils.backtest_engine import BacktestEngine

    engine = BacktestEngine()
    run = engine.run_backtest(date(2024, 12, 15), date(2025, 1, 20))

    generator = ScorecardGenerator()
    scorecard = generator.generate_scorecard(run)
    print(scorecard.format_summary())