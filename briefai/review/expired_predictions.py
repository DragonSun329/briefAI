"""
Expired Prediction Detection

Scans the forecast ledger for predictions whose check_date has passed.
"""

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterator

from .models import ExpiredPrediction, Direction


def parse_date(date_str: str) -> date:
    """Parse date string in YYYY-MM-DD format."""
    return datetime.strptime(date_str[:10], "%Y-%m-%d").date()


def calculate_check_date(prediction_date: date, timeframe_days: int) -> date:
    """Calculate when a prediction should be checked."""
    return prediction_date + timedelta(days=timeframe_days)


def extract_entity_from_prediction(entry: dict) -> str:
    """
    Extract the primary entity from a prediction entry.
    
    Tries multiple fields to find the most relevant entity.
    """
    # Direct entity field
    if "entity" in entry:
        return entry["entity"]
    
    # From concept name (most common case)
    concept = entry.get("concept_name", "")
    if concept and concept != "Mixed Signals Review":
        return concept
    
    # From claim text
    claim = entry.get("claim", "")
    if claim:
        # Extract first noun phrase or entity reference
        # Simple heuristic: take first capitalized word sequence
        words = claim.split()
        for word in words:
            if word[0].isupper() and len(word) > 2:
                return word.strip(":")
    
    return "unknown"


def extract_direction(entry: dict) -> Direction:
    """Extract prediction direction from entry."""
    direction = entry.get("expected_direction", "unknown")
    
    if direction == "up":
        return Direction.UP
    elif direction == "down":
        return Direction.DOWN
    else:
        return Direction.UNKNOWN


def load_ledger(experiment_path: Path) -> Iterator[dict]:
    """
    Load forecast entries from the ledger.
    
    Yields entries one at a time for memory efficiency.
    """
    ledger_path = experiment_path / "forecast_history.jsonl"
    
    if not ledger_path.exists():
        return
    
    with open(ledger_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue


def find_expired_predictions(
    experiment_id: str,
    data_root: Path = None,
    as_of_date: date = None,
) -> list[ExpiredPrediction]:
    """
    Find all predictions whose check_date has passed.
    
    Args:
        experiment_id: Experiment identifier (e.g., "v2_2_forward_test")
        data_root: Root data directory (defaults to data/public/experiments)
        as_of_date: Date to use as "today" (defaults to actual today)
    
    Returns:
        List of ExpiredPrediction objects ready for review
    """
    if data_root is None:
        data_root = Path(__file__).parent.parent.parent / "data" / "public" / "experiments"
    
    if as_of_date is None:
        as_of_date = date.today()
    
    experiment_path = data_root / experiment_id
    
    if not experiment_path.exists():
        raise FileNotFoundError(f"Experiment not found: {experiment_id}")
    
    expired = []
    seen_ids = set()  # Deduplicate by prediction_id
    
    for entry in load_ledger(experiment_path):
        # Skip non-pending entries if status is tracked
        status = entry.get("status", "pending")
        if status not in ("pending", None, ""):
            continue
        
        # Get prediction date and timeframe
        pred_date_str = entry.get("date")
        if not pred_date_str:
            continue
        
        pred_date = parse_date(pred_date_str)
        timeframe = entry.get("timeframe_days", 14)
        check_date = calculate_check_date(pred_date, timeframe)
        
        # Check if expired
        if check_date >= as_of_date:
            continue
        
        # Get prediction ID
        pred_id = entry.get("prediction_id", "")
        if not pred_id or pred_id in seen_ids:
            continue
        seen_ids.add(pred_id)
        
        # Build ExpiredPrediction
        expired_pred = ExpiredPrediction(
            prediction_id=pred_id,
            entity=extract_entity_from_prediction(entry),
            direction=extract_direction(entry),
            confidence=entry.get("confidence", 0.5),
            check_date=check_date,
            hypothesis_text=entry.get("claim", entry.get("predicted_signal", "")),
            evidence_refs=entry.get("evidence_refs", []),
            mechanism=entry.get("mechanism", ""),
            category=entry.get("category", ""),
            concept_name=entry.get("concept_name", ""),
            canonical_metric=entry.get("canonical_metric", ""),
            date_made=pred_date,
            hypothesis_id=entry.get("hypothesis_id", ""),
        )
        
        expired.append(expired_pred)
    
    return expired


def group_by_hypothesis(predictions: list[ExpiredPrediction]) -> dict[str, list[ExpiredPrediction]]:
    """
    Group expired predictions by their hypothesis ID.
    
    Useful for analyzing hypothesis-level accuracy.
    """
    groups = {}
    for pred in predictions:
        h_id = pred.hypothesis_id or "unknown"
        if h_id not in groups:
            groups[h_id] = []
        groups[h_id].append(pred)
    return groups


def group_by_mechanism(predictions: list[ExpiredPrediction]) -> dict[str, list[ExpiredPrediction]]:
    """Group expired predictions by mechanism."""
    groups = {}
    for pred in predictions:
        mech = pred.mechanism or "unknown"
        if mech not in groups:
            groups[mech] = []
        groups[mech].append(pred)
    return groups


def group_by_category(predictions: list[ExpiredPrediction]) -> dict[str, list[ExpiredPrediction]]:
    """Group expired predictions by category."""
    groups = {}
    for pred in predictions:
        cat = pred.category or "unknown"
        if cat not in groups:
            groups[cat] = []
        groups[cat].append(pred)
    return groups
