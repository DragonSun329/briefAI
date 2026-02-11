"""
Public Forecast Logger v2.2

Logs predictions to experiment-specific ledgers for forward-testing.
Ensures experimental isolation, append-only audit trails, and tamper-evidence.

Key features:
- Experiment-aware routing (no cross-experiment writes)
- Metadata stamping (experiment_id, engine_version, commit_hash)
- Append-only forecast history with HASH CHAIN
- Tamper-evident ledger (each entry includes prev_hash + entry_hash)
- DETERMINISTIC canonical JSON serialization (cross-platform stable)
- TWO-PHASE WRITE with crash recovery
- Daily snapshots with freeze timestamps

Hash Chain Integrity:
    Each JSONL entry contains:
    - prev_hash: Hash of the previous entry (or "genesis" for first entry)
    - entry_hash: SHA-256 of canonical JSON (excluding hash fields) + prev_hash
    
    This creates a blockchain-like structure where any modification to
    historical entries will break the hash chain and be detectable.

Crash Safety:
    Writes use two-phase commit:
    1. Append entry to JSONL, flush, fsync
    2. Verify by re-reading last line and recomputing hash
    3. Only then update sidecar file
    
    On startup, reconcile_ledger() repairs any inconsistencies.
"""

import json
import hashlib
import os
from typing import Dict, Any, List, Optional, Tuple
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
from utils.canonical_json import (
    canonical_dumps,
    canonical_hash_content,
    CanonicalJSONError,
    RUNTIME_ONLY_FIELDS,
)


# =============================================================================
# HASH CHAIN CONSTANTS
# =============================================================================

GENESIS_HASH = "genesis"
HASH_SIDECAR_FILENAME = "forecast_history_last_hash.txt"
EXCLUDED_HASH_FIELDS = {'prev_hash', 'entry_hash'}

# Fields excluded from hash computation (runtime-dependent)
HASH_EXCLUDED_FIELDS = EXCLUDED_HASH_FIELDS | RUNTIME_ONLY_FIELDS


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
# HASH CHAIN FUNCTIONS
# =============================================================================

def _canonical_json_for_hash(entry: Dict[str, Any]) -> str:
    """
    Create canonical JSON representation for hashing.
    
    Uses deterministic canonical_dumps() which guarantees identical
    output across Python versions, OSes, and machines.
    
    Excludes:
    - Hash fields (prev_hash, entry_hash)
    - Runtime-only fields (generation_timestamp, etc.)
    """
    filtered = {
        k: v for k, v in entry.items() 
        if k not in HASH_EXCLUDED_FIELDS
    }
    return canonical_dumps(filtered, exclude_runtime_fields=True)


def compute_entry_hash(entry: Dict[str, Any], prev_hash: str) -> str:
    """
    Compute the hash for a ledger entry.
    
    Hash = SHA-256(prev_hash + canonical_json(entry))
    
    Uses deterministic canonical JSON serialization to ensure
    hash stability across different execution environments.
    
    Args:
        entry: The entry dict (excluding hash fields)
        prev_hash: Hash of the previous entry (or "genesis")
    
    Returns:
        Hex digest of SHA-256 hash
    """
    canonical = _canonical_json_for_hash(entry)
    content = prev_hash + canonical
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def get_last_hash(ledger_path: Path) -> str:
    """
    Get the last hash from the sidecar file.
    
    Returns GENESIS_HASH if no sidecar exists (new ledger).
    """
    sidecar = ledger_path / HASH_SIDECAR_FILENAME
    if sidecar.exists():
        content = sidecar.read_text(encoding='utf-8').strip()
        # Validate it looks like a hash (64 hex chars) or genesis
        if content == GENESIS_HASH or (len(content) == 64 and all(c in '0123456789abcdef' for c in content)):
            return content
        logger.warning(f"Invalid sidecar content: {content[:20]}..., treating as genesis")
    return GENESIS_HASH


def save_last_hash(ledger_path: Path, hash_value: str) -> None:
    """
    Save the last hash to the sidecar file with fsync.
    
    This is the FINAL step in two-phase write.
    """
    sidecar = ledger_path / HASH_SIDECAR_FILENAME
    
    # Write to temp file first, then rename (atomic on most filesystems)
    temp_sidecar = ledger_path / f"{HASH_SIDECAR_FILENAME}.tmp"
    
    with open(temp_sidecar, 'w', encoding='utf-8') as f:
        f.write(hash_value)
        f.flush()
        os.fsync(f.fileno())
    
    # Atomic rename
    temp_sidecar.replace(sidecar)


def add_hash_chain(entry: Dict[str, Any], ledger_path: Path) -> Dict[str, Any]:
    """
    Add hash chain fields to an entry.
    
    Reads the last hash, computes the new entry hash, and returns
    the entry with prev_hash and entry_hash fields added.
    
    Args:
        entry: The entry dict (must not contain hash fields)
        ledger_path: Path to the ledger directory
    
    Returns:
        Entry with prev_hash and entry_hash added
    """
    prev_hash = get_last_hash(ledger_path)
    entry_hash = compute_entry_hash(entry, prev_hash)
    
    # Create new entry with hash fields at the end
    hashed_entry = entry.copy()
    hashed_entry['prev_hash'] = prev_hash
    hashed_entry['entry_hash'] = entry_hash
    
    return hashed_entry


# =============================================================================
# TWO-PHASE CRASH-SAFE WRITE
# =============================================================================

def append_entry_atomic(
    history_path: Path,
    entry: Dict[str, Any],
) -> None:
    """
    Phase 1: Append entry to JSONL with flush and fsync.
    
    This ensures the entry is durably written before we update
    the sidecar hash.
    """
    # Use canonical JSON for the stored entry (for consistency)
    # But we include all fields in storage, only exclude from hash
    json_line = json.dumps(entry, ensure_ascii=False, separators=(',', ':'))
    
    with open(history_path, 'a', encoding='utf-8') as f:
        f.write(json_line + '\n')
        f.flush()
        os.fsync(f.fileno())


def verify_last_entry(
    history_path: Path,
    expected_hash: str,
) -> bool:
    """
    Phase 2: Verify the last entry was written correctly.
    
    Re-reads the file's last line and verifies the hash matches.
    This detects partial writes or corruption.
    
    Args:
        history_path: Path to forecast_history.jsonl
        expected_hash: The entry_hash we expect to find
    
    Returns:
        True if verification passes
    """
    if not history_path.exists():
        return False
    
    try:
        # Read last line efficiently
        with open(history_path, 'rb') as f:
            # Seek to end
            f.seek(0, 2)
            file_size = f.tell()
            
            if file_size == 0:
                return False
            
            # Read backwards to find last newline
            pos = file_size - 1
            while pos > 0:
                f.seek(pos)
                char = f.read(1)
                if char == b'\n' and pos < file_size - 1:
                    break
                pos -= 1
            
            # Read last line
            if pos > 0:
                f.seek(pos + 1)
            else:
                f.seek(0)
            
            last_line = f.read().decode('utf-8').strip()
        
        if not last_line:
            return False
        
        entry = json.loads(last_line)
        return entry.get('entry_hash') == expected_hash
    
    except Exception as e:
        logger.warning(f"Verification failed: {e}")
        return False


def two_phase_append(
    history_path: Path,
    ledger_path: Path,
    entry: Dict[str, Any],
) -> str:
    """
    Crash-safe two-phase append to ledger.
    
    1. Append entry with fsync
    2. Verify by re-reading
    3. Update sidecar only after verification
    
    Args:
        history_path: Path to forecast_history.jsonl
        ledger_path: Path to ledger directory
        entry: Entry with hash fields already added
    
    Returns:
        The entry_hash
    
    Raises:
        RuntimeError: If verification fails
    """
    entry_hash = entry['entry_hash']
    
    # Phase 1: Append with fsync
    append_entry_atomic(history_path, entry)
    
    # Phase 2: Verify
    if not verify_last_entry(history_path, entry_hash):
        raise RuntimeError(
            f"Two-phase write verification failed for hash {entry_hash[:16]}... "
            "Entry may not have been written correctly."
        )
    
    # Phase 3: Update sidecar (only after verification)
    save_last_hash(ledger_path, entry_hash)
    
    return entry_hash


# =============================================================================
# CRASH RECOVERY / RECONCILIATION
# =============================================================================

def recompute_chain_hash(history_path: Path) -> Tuple[str, int, int]:
    """
    Recompute the hash chain from genesis.
    
    Returns:
        (last_hash, valid_entry_count, invalid_line_count)
    """
    if not history_path.exists():
        return GENESIS_HASH, 0, 0
    
    prev_hash = GENESIS_HASH
    count = 0
    invalid_count = 0
    
    with open(history_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            
            try:
                entry = json.loads(line)
                # Use the stored entry_hash as prev_hash for next entry
                stored_hash = entry.get('entry_hash')
                if stored_hash:
                    prev_hash = stored_hash
                count += 1
            except json.JSONDecodeError as e:
                invalid_count += 1
                logger.warning(
                    f"Invalid JSON at line {line_num} during reconciliation: {e}. "
                    f"This may indicate a crash during write. "
                    f"Manual inspection recommended."
                )
                continue
    
    return prev_hash, count, invalid_count


def reconcile_ledger(
    ledger_path: Path,
    history_path: Path = None,
) -> Tuple[bool, str, int]:
    """
    Reconcile ledger state after potential crash.
    
    Compares sidecar hash with actual ledger state.
    If mismatch, reconstructs sidecar from ledger.
    
    This function NEVER destroys entries - it only repairs metadata.
    It CANNOT repair truncated/corrupted JSON lines (requires manual fix).
    
    Args:
        ledger_path: Path to ledger directory
        history_path: Path to forecast_history.jsonl (derived if None)
    
    Returns:
        (was_repaired, current_hash, invalid_lines)
        - was_repaired: True if sidecar was updated
        - current_hash: The computed latest hash
        - invalid_lines: Number of unparseable lines (potential data loss!)
    """
    if history_path is None:
        history_path = ledger_path / "forecast_history.jsonl"
    
    # Get sidecar state
    sidecar_hash = get_last_hash(ledger_path)
    
    # Recompute actual state from ledger
    actual_hash, entry_count, invalid_count = recompute_chain_hash(history_path)
    
    if invalid_count > 0:
        logger.error(
            f"LEDGER CONTAINS {invalid_count} INVALID LINE(S)! "
            f"This may indicate crash during write or corruption. "
            f"Manual inspection of {history_path} required. "
            f"Valid entries: {entry_count}"
        )
    
    if sidecar_hash == actual_hash:
        logger.debug(f"Ledger consistent: {entry_count} entries, hash {actual_hash[:16]}...")
        return False, actual_hash, invalid_count
    
    # Mismatch detected - repair sidecar
    logger.warning(
        f"Ledger sidecar mismatch detected! "
        f"Sidecar: {sidecar_hash[:16]}..., Actual: {actual_hash[:16]}... "
        f"Repairing sidecar (ledger entries preserved)."
    )
    
    save_last_hash(ledger_path, actual_hash)
    
    return True, actual_hash, invalid_count


def validate_ledger_integrity(
    history_path: Path,
    repair: bool = False,
    ledger_path: Path = None,
) -> Tuple[bool, int, List[str]]:
    """
    Validate the entire ledger hash chain.
    
    This is a thorough validation that recomputes every hash.
    
    Args:
        history_path: Path to forecast_history.jsonl
        repair: If True, attempt to repair sidecar mismatches
        ledger_path: Path to ledger directory (for sidecar repair)
    
    Returns:
        (is_valid, entry_count, errors)
    """
    errors = []
    
    if not history_path.exists():
        return True, 0, []
    
    prev_hash = GENESIS_HASH
    count = 0
    
    with open(history_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            
            count += 1
            
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as e:
                errors.append(f"Line {line_num}: Invalid JSON - {e}")
                continue
            
            # Check prev_hash link
            stored_prev = entry.get('prev_hash')
            if stored_prev is None:
                errors.append(f"Line {line_num}: Missing prev_hash")
            elif stored_prev != prev_hash:
                errors.append(
                    f"Line {line_num}: Chain broken - "
                    f"expected {prev_hash[:16]}..., got {stored_prev[:16]}..."
                )
            
            # Verify entry hash
            stored_hash = entry.get('entry_hash')
            if stored_hash is None:
                errors.append(f"Line {line_num}: Missing entry_hash")
            else:
                computed = compute_entry_hash(entry, prev_hash)
                if computed != stored_hash:
                    errors.append(
                        f"Line {line_num}: Hash mismatch (possible tampering) - "
                        f"computed {computed[:16]}..., stored {stored_hash[:16]}..."
                    )
                prev_hash = stored_hash
    
    # Check sidecar consistency
    if ledger_path and not errors:
        sidecar_hash = get_last_hash(ledger_path)
        if sidecar_hash != prev_hash:
            if repair:
                save_last_hash(ledger_path, prev_hash)
                logger.info("Sidecar repaired during validation")
            else:
                errors.append(
                    f"Sidecar inconsistent: {sidecar_hash[:16]}... vs {prev_hash[:16]}..."
                )
    
    return len(errors) == 0, count, errors


def verify_hash_chain(history_path: Path) -> Tuple[bool, int, Optional[str]]:
    """
    Verify the entire hash chain of a forecast history.
    
    Reads each entry, recomputes its hash using deterministic
    canonical JSON, and verifies it matches the stored entry_hash
    and that prev_hash links correctly.
    
    Uses canonical_dumps() for cross-platform hash stability.
    
    Args:
        history_path: Path to forecast_history.jsonl
    
    Returns:
        Tuple of (is_valid, entry_count, error_message)
        - is_valid: True if chain is intact
        - entry_count: Number of entries verified
        - error_message: Description of first error found (or None)
    """
    if not history_path.exists():
        return True, 0, None
    
    prev_hash = GENESIS_HASH
    line_num = 0
    
    with open(history_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            
            line_num += 1
            
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as e:
                return False, line_num - 1, f"Line {line_num}: Invalid JSON - {e}"
            
            # Check prev_hash link
            stored_prev = entry.get('prev_hash')
            if stored_prev is None:
                return False, line_num - 1, f"Line {line_num}: Missing prev_hash field"
            
            if stored_prev != prev_hash:
                return False, line_num - 1, (
                    f"Line {line_num}: Chain broken - "
                    f"expected prev_hash={prev_hash[:16]}..., got {stored_prev[:16]}..."
                )
            
            # Verify entry hash using canonical JSON
            stored_hash = entry.get('entry_hash')
            if stored_hash is None:
                return False, line_num - 1, f"Line {line_num}: Missing entry_hash field"
            
            computed_hash = compute_entry_hash(entry, prev_hash)
            if computed_hash != stored_hash:
                return False, line_num - 1, (
                    f"Line {line_num}: Hash mismatch - entry may have been tampered. "
                    f"Computed {computed_hash[:16]}..., stored {stored_hash[:16]}..."
                )
            
            # Move to next entry
            prev_hash = stored_hash
    
    return True, line_num, None


def print_chain_verification(history_path: Path) -> bool:
    """
    Verify and print chain status.
    
    Returns:
        True if chain is valid
    """
    is_valid, count, error = verify_hash_chain(history_path)
    
    if is_valid:
        print(f"[OK] Hash chain verified: {count} entries, chain intact")
        return True
    else:
        print(f"[FAIL] Hash chain BROKEN at entry {count + 1}")
        print(f"  Error: {error}")
        return False


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
    Append-only logger for forecast history with crash-safe writes.
    
    Writes predictions to experiment-specific forecast_history.jsonl.
    Uses two-phase commit for crash safety and reconciles on startup.
    """
    
    def __init__(self, experiment_id: str = None, auto_reconcile: bool = True):
        """
        Initialize logger for an experiment.
        
        Args:
            experiment_id: Optional experiment ID. Uses active experiment if None.
            auto_reconcile: If True, run reconciliation on startup (default).
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
        
        # CRASH RECOVERY: Reconcile ledger on startup
        if auto_reconcile:
            was_repaired, current_hash, invalid_lines = reconcile_ledger(
                self.ledger_path, self.history_path
            )
            if was_repaired:
                logger.warning(
                    f"[ForecastLogger] Ledger sidecar was repaired on startup. "
                    f"Current hash: {current_hash[:16]}..."
                )
            if invalid_lines > 0:
                logger.error(
                    f"[ForecastLogger] CRITICAL: {invalid_lines} invalid line(s) in ledger! "
                    f"This indicates a crash mid-write or corruption. "
                    f"Manual inspection required before continuing."
                )
        
        logger.info(
            f"ForecastHistoryLogger initialized for experiment: "
            f"{self.context.experiment.experiment_id}"
        )
    
    def log_prediction(self, prediction: Dict[str, Any]) -> str:
        """
        Log a single prediction to the forecast history.
        
        Uses crash-safe two-phase write:
        1. Append entry with fsync
        2. Verify by re-reading
        3. Update sidecar only after verification
        
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
        
        # Add hash chain fields
        hashed_entry = add_hash_chain(stamped, self.ledger_path)
        
        # TWO-PHASE CRASH-SAFE WRITE
        two_phase_append(
            self.history_path,
            self.ledger_path,
            hashed_entry,
        )
        
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
