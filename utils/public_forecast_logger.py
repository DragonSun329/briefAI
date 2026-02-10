"""
Public Forecast Logger - Append-Only Audit Trail.

Part of briefAI Validation & Public Credibility Layer.

Every time a hypothesis prediction is generated, append a line.
This file is the PUBLIC AUDIT TRAIL.

Rules:
- Append only
- Never overwrite
- Stable ordering
- Deterministic output

Output:
    data/public/forecast_history.jsonl
"""

import os
import json
import hashlib
from typing import List, Dict, Any, Optional

# File locking (Unix only)
if os.name != 'nt':
    import fcntl
else:
    fcntl = None
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

from loguru import logger


# =============================================================================
# CONSTANTS
# =============================================================================

DEFAULT_DATA_DIR = Path(__file__).parent.parent / "data"
PUBLIC_DIR = "public"
FORECAST_HISTORY_FILE = "forecast_history.jsonl"


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class ForecastEntry:
    """A single forecast entry in the public ledger."""
    
    # Identifiers
    forecast_id: str
    date: str
    hypothesis_id: str
    
    # The claim
    claim: str
    confidence: float
    mechanism: str
    
    # Prediction details
    predicted_signal: str
    category: str
    canonical_metric: str
    expected_direction: str
    timeframe_days: int
    
    # Metadata
    concept_name: str
    logged_at: str
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def to_jsonl(self) -> str:
        """Serialize to JSONL line (sorted keys for stability)."""
        return json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False)
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'ForecastEntry':
        return cls(**d)
    
    @classmethod
    def from_jsonl(cls, line: str) -> 'ForecastEntry':
        return cls.from_dict(json.loads(line))


# =============================================================================
# FORECAST ID GENERATOR
# =============================================================================

def generate_forecast_id(
    date: str,
    hypothesis_id: str,
    canonical_metric: str,
    category: str,
) -> str:
    """
    Generate a stable, deterministic forecast ID.
    
    Same inputs always produce same ID.
    """
    input_str = f"{date}|{hypothesis_id}|{canonical_metric}|{category}"
    hash_bytes = hashlib.sha256(input_str.encode()).hexdigest()
    return f"fc_{hash_bytes[:12]}"


# =============================================================================
# PUBLIC FORECAST LOGGER
# =============================================================================

class PublicForecastLogger:
    """
    Logs forecasts to an append-only public audit trail.
    
    Thread-safe (uses file locking on Unix).
    Idempotent (same forecast won't be logged twice).
    """
    
    def __init__(self, data_dir: Path = None):
        """
        Initialize forecast logger.
        
        Args:
            data_dir: Base data directory
        """
        if data_dir is None:
            data_dir = DEFAULT_DATA_DIR
        
        self.data_dir = Path(data_dir)
        self.public_dir = self.data_dir / PUBLIC_DIR
        self.public_dir.mkdir(parents=True, exist_ok=True)
        
        self.history_file = self.public_dir / FORECAST_HISTORY_FILE
        
        # Cache of logged forecast IDs (for idempotency)
        self._logged_ids: set = set()
        self._load_logged_ids()
        
        logger.debug(f"PublicForecastLogger initialized at {self.history_file}")
    
    def _load_logged_ids(self):
        """Load already logged forecast IDs."""
        if not self.history_file.exists():
            return
        
        try:
            with open(self.history_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entry = json.loads(line)
                            self._logged_ids.add(entry.get("forecast_id", ""))
                        except json.JSONDecodeError:
                            pass
        except Exception as e:
            logger.warning(f"Failed to load logged IDs: {e}")
    
    def log_forecast(self, entry: ForecastEntry) -> bool:
        """
        Log a single forecast entry.
        
        Args:
            entry: ForecastEntry to log
        
        Returns:
            True if logged, False if already exists
        """
        # Check for duplicate
        if entry.forecast_id in self._logged_ids:
            logger.debug(f"Forecast {entry.forecast_id} already logged")
            return False
        
        # Append to file
        try:
            with open(self.history_file, 'a', encoding='utf-8') as f:
                # File locking on Unix
                if fcntl is not None:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                
                f.write(entry.to_jsonl() + '\n')
                
                if fcntl is not None:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            
            self._logged_ids.add(entry.forecast_id)
            logger.debug(f"Logged forecast {entry.forecast_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to log forecast: {e}")
            return False
    
    def log_forecasts(self, entries: List[ForecastEntry]) -> int:
        """
        Log multiple forecast entries.
        
        Args:
            entries: List of ForecastEntry to log
        
        Returns:
            Number of new entries logged
        """
        logged = 0
        for entry in entries:
            if self.log_forecast(entry):
                logged += 1
        
        return logged
    
    def log_from_hypothesis(
        self,
        date: str,
        hypothesis: Dict[str, Any],
        concept_name: str = "",
    ) -> int:
        """
        Log forecasts from a hypothesis dict.
        
        Args:
            date: Date of forecast
            hypothesis: Hypothesis dict
            concept_name: Name of parent concept
        
        Returns:
            Number of entries logged
        """
        entries = []
        
        hypothesis_id = hypothesis.get("hypothesis_id", "")
        confidence = hypothesis.get("confidence", 0.5)
        mechanism = hypothesis.get("mechanism", "")
        title = hypothesis.get("title", "")
        
        for pred in hypothesis.get("predicted_next_signals", []):
            if not pred.get("measurable", False):
                continue
            
            forecast_id = generate_forecast_id(
                date,
                hypothesis_id,
                pred.get("canonical_metric", ""),
                pred.get("category", ""),
            )
            
            entry = ForecastEntry(
                forecast_id=forecast_id,
                date=date,
                hypothesis_id=hypothesis_id,
                claim=title,
                confidence=confidence,
                mechanism=mechanism,
                predicted_signal=pred.get("description", ""),
                category=pred.get("category", ""),
                canonical_metric=pred.get("canonical_metric", ""),
                expected_direction=pred.get("direction", "up"),
                timeframe_days=pred.get("expected_timeframe_days", 30),
                concept_name=concept_name,
                logged_at=datetime.now().isoformat(),
            )
            
            entries.append(entry)
        
        return self.log_forecasts(entries)
    
    def log_from_hypotheses_file(self, file_path: Path) -> int:
        """
        Log forecasts from a hypotheses JSON file.
        
        Args:
            file_path: Path to hypotheses_YYYY-MM-DD.json
        
        Returns:
            Number of entries logged
        """
        if not file_path.exists():
            logger.warning(f"Hypotheses file not found: {file_path}")
            return 0
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load hypotheses: {e}")
            return 0
        
        date = data.get("date", file_path.stem.split("_")[-1])
        logged = 0
        
        for bundle in data.get("bundles", []):
            concept_name = bundle.get("concept_name", "")
            
            for hyp in bundle.get("hypotheses", []):
                logged += self.log_from_hypothesis(date, hyp, concept_name)
        
        logger.info(f"Logged {logged} forecasts from {file_path.name}")
        return logged
    
    def get_forecast_count(self) -> int:
        """Get total number of logged forecasts."""
        return len(self._logged_ids)
    
    def get_forecasts_for_date(self, date: str) -> List[ForecastEntry]:
        """Get all forecasts for a specific date."""
        if not self.history_file.exists():
            return []
        
        forecasts = []
        
        with open(self.history_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entry = ForecastEntry.from_jsonl(line)
                        if entry.date == date:
                            forecasts.append(entry)
                    except Exception:
                        pass
        
        return forecasts
    
    def get_all_forecasts(self) -> List[ForecastEntry]:
        """Get all logged forecasts."""
        if not self.history_file.exists():
            return []
        
        forecasts = []
        
        with open(self.history_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        forecasts.append(ForecastEntry.from_jsonl(line))
                    except Exception:
                        pass
        
        return forecasts


# =============================================================================
# INTEGRATION HOOK
# =============================================================================

def log_hypothesis_predictions(
    hypotheses_data: Dict[str, Any],
    date: str = None,
    data_dir: Path = None,
) -> int:
    """
    Integration hook: Log predictions from hypotheses output.
    
    Call this after hypothesis generation to populate the public ledger.
    
    Args:
        hypotheses_data: Output from HypothesisEngine.process_meta_signals()
        date: Date of predictions (defaults to today)
        data_dir: Data directory
    
    Returns:
        Number of forecasts logged
    """
    if date is None:
        date = hypotheses_data.get("date", datetime.now().strftime("%Y-%m-%d"))
    
    logger_obj = PublicForecastLogger(data_dir)
    
    logged = 0
    for bundle in hypotheses_data.get("bundles", []):
        concept_name = bundle.get("concept_name", "")
        
        for hyp in bundle.get("hypotheses", []):
            logged += logger_obj.log_from_hypothesis(date, hyp, concept_name)
    
    return logged


# =============================================================================
# TESTS
# =============================================================================

def _test_forecast_entry():
    """Test ForecastEntry serialization."""
    entry = ForecastEntry(
        forecast_id="fc_test123",
        date="2026-02-10",
        hypothesis_id="hyp_001",
        claim="Infrastructure Scaling",
        confidence=0.78,
        mechanism="infra_scaling",
        predicted_signal="NVIDIA datacenter revenue beats",
        category="financial",
        canonical_metric="earnings_mentions",
        expected_direction="up",
        timeframe_days=30,
        concept_name="NVIDIA Demand",
        logged_at="2026-02-10T14:00:00",
    )
    
    jsonl = entry.to_jsonl()
    restored = ForecastEntry.from_jsonl(jsonl)
    
    assert restored.forecast_id == entry.forecast_id
    assert restored.confidence == entry.confidence
    
    print("[PASS] _test_forecast_entry")


def _test_forecast_id_stability():
    """Test forecast ID is deterministic."""
    id1 = generate_forecast_id("2026-02-10", "hyp_001", "arr", "financial")
    id2 = generate_forecast_id("2026-02-10", "hyp_001", "arr", "financial")
    id3 = generate_forecast_id("2026-02-10", "hyp_002", "arr", "financial")
    
    assert id1 == id2  # Same inputs = same ID
    assert id1 != id3  # Different inputs = different ID
    
    print("[PASS] _test_forecast_id_stability")


def _test_logger_idempotency():
    """Test logger doesn't log duplicates."""
    import tempfile
    
    with tempfile.TemporaryDirectory() as tmpdir:
        logger_obj = PublicForecastLogger(Path(tmpdir))
        
        entry = ForecastEntry(
            forecast_id="fc_test123",
            date="2026-02-10",
            hypothesis_id="hyp_001",
            claim="Test",
            confidence=0.78,
            mechanism="test",
            predicted_signal="Test signal",
            category="test",
            canonical_metric="test",
            expected_direction="up",
            timeframe_days=30,
            concept_name="Test",
            logged_at="2026-02-10T14:00:00",
        )
        
        # First log should succeed
        assert logger_obj.log_forecast(entry) == True
        
        # Second log should be idempotent (no duplicate)
        assert logger_obj.log_forecast(entry) == False
        
        # Count should be 1
        assert logger_obj.get_forecast_count() == 1
        
    print("[PASS] _test_logger_idempotency")


def run_tests():
    """Run all tests."""
    print("\n=== PUBLIC FORECAST LOGGER TESTS ===\n")
    
    _test_forecast_entry()
    _test_forecast_id_stability()
    _test_logger_idempotency()
    
    print("\n=== ALL TESTS PASSED ===")


if __name__ == "__main__":
    run_tests()
