"""
Public Forecast Logger v2.0

Logs predictions to experiment-specific ledgers for forward-testing.
Ensures experimental isolation and append-only audit trails.

Key features:
- Experiment-aware routing (no cross-experiment writes)
- Metadata stamping (experiment_id, engine_version, commit_hash)
- Append-only forecast history
- Daily snapshots with freeze timestamps
"""

import json
import hashlib
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from loguru import logger

from utils.experiment_manager import (
    get_experiment_context,
    get_ledger_path,
    get_forecast_history_path,
    get_daily_snapshot_path,
    get_run_metadata_path,
    validate_experiment_context,
    ExperimentContext,
)


# =============================================================================
# CONSTANTS
# =============================================================================

REQUIRED_PREDICTION_FIELDS = [
    'experiment_id',
    'engine_version',
    'commit_hash',
    'generation_timestamp',
]


# =============================================================================
# VALIDATION
# =============================================================================

def validate_prediction(prediction: Dict[str, Any]) -> tuple:
    """
    Validate a prediction has required metadata.
    
    Returns:
        (is_valid, missing_fields)
    """
    missing = []
    for field in REQUIRED_PREDICTION_FIELDS:
        if field not in prediction or not prediction[field]:
            missing.append(field)
    
    return len(missing) == 0, missing


def stamp_prediction(
    prediction: Dict[str, Any],
    context: ExperimentContext,
) -> Dict[str, Any]:
    """Add experiment metadata stamp to a prediction."""
    stamped = prediction.copy()
    stamped.update(context.get_metadata_stamp())
    
    # Add prediction ID if not present
    if 'prediction_id' not in stamped:
        content = json.dumps(stamped, sort_keys=True)
        stamped['prediction_id'] = 'pred_' + hashlib.sha256(content.encode()).hexdigest()[:12]
    
    return stamped


# =============================================================================
# FORECAST HISTORY LOGGER
# =============================================================================

class ForecastHistoryLogger:
    """
    Append-only logger for forecast history.
    
    Writes predictions to experiment-specific forecast_history.jsonl.
    """
    
    def __init__(self, experiment_id: str = None):
        """
        Initialize logger for an experiment.
        
        Args:
            experiment_id: Optional experiment ID. Uses active experiment if None.
        """
        self.context = get_experiment_context(experiment_id)
        self.ledger_path = get_ledger_path(self.context.experiment.experiment_id)
        self.history_path = get_forecast_history_path(self.context.experiment.experiment_id)
        
        # Validate context
        is_valid, warnings, errors = validate_experiment_context(self.context)
        for warning in warnings:
            logger.warning(f"[ForecastLogger] {warning}")
        for error in errors:
            logger.error(f"[ForecastLogger] {error}")
        
        if not is_valid:
            raise ValueError(f"Invalid experiment context: {errors}")
        
        logger.info(
            f"ForecastHistoryLogger initialized for experiment: "
            f"{self.context.experiment.experiment_id}"
        )
    
    def log_prediction(self, prediction: Dict[str, Any]) -> str:
        """
        Log a single prediction to the forecast history.
        
        Args:
            prediction: Prediction dict
        
        Returns:
            prediction_id
        """
        # Stamp with metadata
        stamped = stamp_prediction(prediction, self.context)
        
        # Validate
        is_valid, missing = validate_prediction(stamped)
        if not is_valid:
            raise ValueError(f"Prediction missing required fields: {missing}")
        
        # Append to JSONL
        with open(self.history_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(stamped, ensure_ascii=False) + '\n')
        
        return stamped['prediction_id']
    
    def log_predictions(self, predictions: List[Dict[str, Any]]) -> List[str]:
        """
        Log multiple predictions to the forecast history.
        
        Args:
            predictions: List of prediction dicts
        
        Returns:
            List of prediction_ids
        """
        ids = []
        for pred in predictions:
            pred_id = self.log_prediction(pred)
            ids.append(pred_id)
        
        logger.info(f"Logged {len(ids)} predictions to {self.history_path}")
        return ids
    
    def get_prediction_count(self) -> int:
        """Get the total number of predictions in the history."""
        if not self.history_path.exists():
            return 0
        
        count = 0
        with open(self.history_path, 'r', encoding='utf-8') as f:
            for _ in f:
                count += 1
        return count


# =============================================================================
# DAILY SNAPSHOT WRITER
# =============================================================================

class DailySnapshotWriter:
    """
    Writes daily snapshots for experiment ledgers.
    
    A daily snapshot contains all predictions generated on a specific date,
    frozen at a specific timestamp.
    """
    
    def __init__(self, experiment_id: str = None):
        """
        Initialize writer for an experiment.
        
        Args:
            experiment_id: Optional experiment ID. Uses active experiment if None.
        """
        self.context = get_experiment_context(experiment_id)
        self.ledger_path = get_ledger_path(self.context.experiment.experiment_id)
        
        logger.info(
            f"DailySnapshotWriter initialized for experiment: "
            f"{self.context.experiment.experiment_id}"
        )
    
    def write_snapshot(
        self,
        date: str,
        predictions: List[Dict[str, Any]],
        signals_data: Dict[str, Any] = None,
        additional_metadata: Dict[str, Any] = None,
    ) -> Path:
        """
        Write a daily snapshot.
        
        Args:
            date: Date string (YYYY-MM-DD)
            predictions: List of predictions for this date
            signals_data: Optional signals/meta-signals data
            additional_metadata: Optional additional metadata
        
        Returns:
            Path to the snapshot file
        """
        snapshot = {
            'date': date,
            'frozen_at': self.context.generation_timestamp,
            'experiment_id': self.context.experiment.experiment_id,
            'engine_tag': self.context.experiment.engine_tag,
            'commit_hash': self.context.commit_hash,
            'model_version': self.context.experiment.engine_version,
            'run_type': 'forward_test',
            'prediction_count': len(predictions),
            'predictions': predictions,
        }
        
        if signals_data:
            snapshot['signals'] = signals_data
        
        if additional_metadata:
            snapshot.update(additional_metadata)
        
        # Write snapshot
        snapshot_path = get_daily_snapshot_path(date, self.context.experiment.experiment_id)
        with open(snapshot_path, 'w', encoding='utf-8') as f:
            json.dump(snapshot, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Wrote daily snapshot: {snapshot_path}")
        return snapshot_path
    
    def write_run_metadata(self, date: str) -> Path:
        """
        Write run metadata for a specific date.
        
        Args:
            date: Date string (YYYY-MM-DD)
        
        Returns:
            Path to the metadata file
        """
        import platform
        import sys
        
        metadata = {
            'experiment_id': self.context.experiment.experiment_id,
            'engine_tag': self.context.experiment.engine_tag,
            'model_version': self.context.experiment.engine_version,
            'commit_hash': self.context.commit_hash,
            'run_type': 'forward_test',
            'rerun_allowed': False,
            'date': date,
            'timestamp_utc': self.context.generation_timestamp,
            'python_version': platform.python_version(),
            'os': f"{platform.system()} {platform.release()}",
        }
        
        # Write metadata
        metadata_path = get_run_metadata_path(date, self.context.experiment.experiment_id)
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Wrote run metadata: {metadata_path}")
        return metadata_path
    
    def write_completion_flag(self, date: str) -> Path:
        """
        Write a completion flag for a specific date.
        
        Args:
            date: Date string (YYYY-MM-DD)
        
        Returns:
            Path to the flag file
        """
        flag_path = self.ledger_path / f"RUN_COMPLETE_{date}.flag"
        
        with open(flag_path, 'w', encoding='utf-8') as f:
            f.write(f"Completed: {self.context.generation_timestamp}\n")
            f.write(f"Experiment: {self.context.experiment.experiment_id}\n")
            f.write(f"Commit: {self.context.commit_hash}\n")
        
        logger.info(f"Wrote completion flag: {flag_path}")
        return flag_path


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def log_predictions_to_experiment(
    predictions: List[Dict[str, Any]],
    experiment_id: str = None,
) -> List[str]:
    """
    Log predictions to an experiment's forecast history.
    
    Args:
        predictions: List of prediction dicts
        experiment_id: Optional experiment ID. Uses active experiment if None.
    
    Returns:
        List of prediction IDs
    """
    logger_instance = ForecastHistoryLogger(experiment_id)
    return logger_instance.log_predictions(predictions)


def create_daily_snapshot(
    date: str,
    predictions: List[Dict[str, Any]],
    signals_data: Dict[str, Any] = None,
    experiment_id: str = None,
) -> Dict[str, Path]:
    """
    Create a complete daily snapshot with metadata.
    
    Args:
        date: Date string (YYYY-MM-DD)
        predictions: List of predictions
        signals_data: Optional signals data
        experiment_id: Optional experiment ID
    
    Returns:
        Dict with paths to created files
    """
    writer = DailySnapshotWriter(experiment_id)
    
    # Stamp all predictions
    context = get_experiment_context(experiment_id)
    stamped_predictions = [
        stamp_prediction(pred, context) 
        for pred in predictions
    ]
    
    # Write files
    snapshot_path = writer.write_snapshot(date, stamped_predictions, signals_data)
    metadata_path = writer.write_run_metadata(date)
    flag_path = writer.write_completion_flag(date)
    
    # Log to forecast history
    history_logger = ForecastHistoryLogger(experiment_id)
    history_logger.log_predictions(stamped_predictions)
    
    return {
        'snapshot': snapshot_path,
        'metadata': metadata_path,
        'flag': flag_path,
        'prediction_count': len(stamped_predictions),
    }


# =============================================================================
# READING FUNCTIONS
# =============================================================================

def read_forecast_history(experiment_id: str = None) -> List[Dict[str, Any]]:
    """
    Read all predictions from an experiment's forecast history.
    
    Args:
        experiment_id: Optional experiment ID. Uses active experiment if None.
    
    Returns:
        List of prediction dicts
    """
    history_path = get_forecast_history_path(experiment_id)
    
    if not history_path.exists():
        return []
    
    predictions = []
    with open(history_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                predictions.append(json.loads(line))
    
    return predictions


def read_daily_snapshot(date: str, experiment_id: str = None) -> Optional[Dict[str, Any]]:
    """
    Read a daily snapshot for a specific date.
    
    Args:
        date: Date string (YYYY-MM-DD)
        experiment_id: Optional experiment ID
    
    Returns:
        Snapshot dict or None if not found
    """
    snapshot_path = get_daily_snapshot_path(date, experiment_id)
    
    if not snapshot_path.exists():
        return None
    
    with open(snapshot_path, 'r', encoding='utf-8') as f:
        return json.load(f)
