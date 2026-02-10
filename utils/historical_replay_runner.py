"""
Historical Replay Runner - Temporal Causality Backtesting.

Part of briefAI Validation & Public Credibility Layer.

Core Principle:
    When simulating a past date, the system may only use
    information available up to that date.
    NO FORWARD-LOOKING LEAKAGE.

This module treats the existing pipeline as a black-box research model
and wraps it in a temporal validation layer.

Usage:
    runner = HistoricalReplayRunner(data_dir)
    runner.run_replay("2025-11-01", "2026-02-01")
"""

import os
import json
import random
import hashlib
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from copy import deepcopy

from loguru import logger


# =============================================================================
# CONSTANTS
# =============================================================================

DEFAULT_DATA_DIR = Path(__file__).parent.parent / "data"
BACKTEST_DIR = "backtest"


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class ReplayDayResult:
    """Result from replaying a single day."""
    date: str
    signals_count: int
    metas_count: int
    hypotheses_count: int
    predictions_count: int
    execution_time_ms: int
    success: bool
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ReplayRunSummary:
    """Summary of a complete replay run."""
    run_id: str
    start_date: str
    end_date: str
    days_processed: int
    total_signals: int
    total_metas: int
    total_hypotheses: int
    total_predictions: int
    success_rate: float
    execution_time_seconds: float
    started_at: str
    completed_at: str
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# =============================================================================
# TEMPORAL DATA FILTER
# =============================================================================

class TemporalDataFilter:
    """
    Filters data to respect temporal causality.
    
    Only returns data with timestamp <= target_date.
    """
    
    @staticmethod
    def filter_by_date(
        data: List[Dict[str, Any]],
        max_date: str,
        date_field: str = "date",
    ) -> List[Dict[str, Any]]:
        """
        Filter list of dicts to only include items up to max_date.
        
        Args:
            data: List of data dicts
            max_date: Maximum date (YYYY-MM-DD)
            date_field: Field name containing date
        
        Returns:
            Filtered list
        """
        max_dt = datetime.strptime(max_date, "%Y-%m-%d")
        
        filtered = []
        for item in data:
            item_date = item.get(date_field, "")
            
            if not item_date:
                continue
            
            try:
                # Handle different date formats
                if "T" in item_date:
                    item_dt = datetime.fromisoformat(item_date.split("T")[0])
                else:
                    item_dt = datetime.strptime(item_date[:10], "%Y-%m-%d")
                
                if item_dt <= max_dt:
                    filtered.append(item)
            except (ValueError, TypeError):
                # Skip items with invalid dates
                pass
        
        return filtered
    
    @staticmethod
    def filter_file_by_date(
        file_path: Path,
        max_date: str,
        date_field: str = "date",
    ) -> List[Dict[str, Any]]:
        """
        Load and filter a JSONL file by date.
        
        Args:
            file_path: Path to JSONL file
            max_date: Maximum date
            date_field: Field containing date
        
        Returns:
            Filtered list of dicts
        """
        if not file_path.exists():
            return []
        
        data = []
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        data.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        
        return TemporalDataFilter.filter_by_date(data, max_date, date_field)


# =============================================================================
# DETERMINISTIC SEEDING
# =============================================================================

class DeterministicSeeder:
    """
    Provides deterministic seeding for reproducible runs.
    
    Seed is derived from date string so reruns produce identical results.
    """
    
    @staticmethod
    def get_seed_for_date(date: str) -> int:
        """
        Get deterministic seed for a date.
        
        Args:
            date: Date string (YYYY-MM-DD)
        
        Returns:
            Integer seed
        """
        hash_bytes = hashlib.sha256(date.encode()).digest()
        return int.from_bytes(hash_bytes[:4], 'big')
    
    @staticmethod
    def set_seed_for_date(date: str):
        """Set random seed for a date."""
        seed = DeterministicSeeder.get_seed_for_date(date)
        random.seed(seed)
        
        # Also set numpy seed if available
        try:
            import numpy as np
            np.random.seed(seed)
        except ImportError:
            pass


# =============================================================================
# HISTORICAL REPLAY RUNNER
# =============================================================================

class HistoricalReplayRunner:
    """
    Runs historical replay backtesting with strict temporal causality.
    
    For each day D in the date range:
    1. Load only data with timestamp <= D
    2. Run signal generation, meta-signals, hypotheses, predictions
    3. Store daily outputs
    4. DO NOT evaluate predictions (handled separately)
    """
    
    def __init__(self, data_dir: Path = None):
        """
        Initialize replay runner.
        
        Args:
            data_dir: Base data directory
        """
        if data_dir is None:
            data_dir = DEFAULT_DATA_DIR
        
        self.data_dir = Path(data_dir)
        self.backtest_dir = self.data_dir / BACKTEST_DIR
        self.temporal_filter = TemporalDataFilter()
        
        logger.debug(f"HistoricalReplayRunner initialized at {self.data_dir}")
    
    def run_replay(
        self,
        start_date: str,
        end_date: str,
        dry_run: bool = False,
    ) -> ReplayRunSummary:
        """
        Run historical replay for a date range.
        
        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            dry_run: If True, don't write outputs
        
        Returns:
            ReplayRunSummary
        """
        run_id = f"replay_{start_date}_{end_date}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        started_at = datetime.now().isoformat()
        
        logger.info(f"Starting historical replay: {start_date} to {end_date}")
        logger.info(f"Run ID: {run_id}")
        
        # Parse dates
        current = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        
        # Track results
        day_results: List[ReplayDayResult] = []
        total_signals = 0
        total_metas = 0
        total_hypotheses = 0
        total_predictions = 0
        
        # Process each day
        while current <= end:
            date_str = current.strftime("%Y-%m-%d")
            
            logger.info(f"Processing {date_str}...")
            
            result = self._replay_single_day(date_str, dry_run)
            day_results.append(result)
            
            if result.success:
                total_signals += result.signals_count
                total_metas += result.metas_count
                total_hypotheses += result.hypotheses_count
                total_predictions += result.predictions_count
            
            current += timedelta(days=1)
        
        completed_at = datetime.now().isoformat()
        
        # Calculate success rate
        success_count = sum(1 for r in day_results if r.success)
        success_rate = success_count / len(day_results) if day_results else 0.0
        
        # Calculate execution time
        started_dt = datetime.fromisoformat(started_at)
        completed_dt = datetime.fromisoformat(completed_at)
        execution_time = (completed_dt - started_dt).total_seconds()
        
        summary = ReplayRunSummary(
            run_id=run_id,
            start_date=start_date,
            end_date=end_date,
            days_processed=len(day_results),
            total_signals=total_signals,
            total_metas=total_metas,
            total_hypotheses=total_hypotheses,
            total_predictions=total_predictions,
            success_rate=round(success_rate, 4),
            execution_time_seconds=round(execution_time, 2),
            started_at=started_at,
            completed_at=completed_at,
        )
        
        # Save summary
        if not dry_run:
            self._save_run_summary(summary, day_results)
        
        logger.info(f"Replay complete: {len(day_results)} days, {total_predictions} predictions")
        
        return summary
    
    def _replay_single_day(
        self,
        date: str,
        dry_run: bool = False,
    ) -> ReplayDayResult:
        """
        Replay a single day.
        
        Args:
            date: Date to replay (YYYY-MM-DD)
            dry_run: If True, don't write outputs
        
        Returns:
            ReplayDayResult
        """
        import time
        start_time = time.time()
        
        try:
            # Set deterministic seed
            DeterministicSeeder.set_seed_for_date(date)
            
            # Load temporally-filtered data
            signals = self._load_signals_for_date(date)
            
            # Generate meta-signals
            metas = self._generate_metas_for_date(date, signals)
            
            # Generate hypotheses
            hypotheses = self._generate_hypotheses_for_date(date, metas)
            
            # Register predictions
            predictions = self._register_predictions_for_date(date, hypotheses)
            
            # Save outputs
            if not dry_run:
                self._save_day_outputs(date, signals, metas, hypotheses, predictions)
            
            execution_time_ms = int((time.time() - start_time) * 1000)
            
            return ReplayDayResult(
                date=date,
                signals_count=len(signals),
                metas_count=len(metas),
                hypotheses_count=len(hypotheses),
                predictions_count=len(predictions),
                execution_time_ms=execution_time_ms,
                success=True,
            )
            
        except Exception as e:
            logger.error(f"Replay failed for {date}: {e}")
            
            return ReplayDayResult(
                date=date,
                signals_count=0,
                metas_count=0,
                hypotheses_count=0,
                predictions_count=0,
                execution_time_ms=int((time.time() - start_time) * 1000),
                success=False,
                error=str(e),
            )
    
    def _load_signals_for_date(self, date: str) -> List[Dict[str, Any]]:
        """Load signals available up to date."""
        signals = []
        
        # Check for signals directory
        signals_dir = self.data_dir / "signals"
        if signals_dir.exists():
            for file_path in signals_dir.glob("*.jsonl"):
                filtered = self.temporal_filter.filter_file_by_date(
                    file_path, date, "timestamp"
                )
                signals.extend(filtered)
        
        # Also check news_signals
        news_dir = self.data_dir / "news_signals"
        if news_dir.exists():
            for file_path in news_dir.glob("*.json"):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    if isinstance(data, list):
                        filtered = self.temporal_filter.filter_by_date(
                            data, date, "date"
                        )
                        signals.extend(filtered)
                except Exception:
                    pass
        
        return signals
    
    def _generate_metas_for_date(
        self,
        date: str,
        signals: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Generate meta-signals for a date."""
        # Try to use existing meta-signal engine
        try:
            # Check if there's a pre-computed meta-signals file
            meta_file = self.data_dir / "meta_signals" / f"meta_signals_{date}.json"
            
            if meta_file.exists():
                with open(meta_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return data.get("meta_signals", [])
            
            # Otherwise, return empty (would need full signal pipeline)
            return []
            
        except Exception as e:
            logger.warning(f"Meta generation failed for {date}: {e}")
            return []
    
    def _generate_hypotheses_for_date(
        self,
        date: str,
        metas: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Generate hypotheses for a date."""
        try:
            # Check for pre-computed hypotheses
            hyp_file = self.data_dir / "hypotheses" / f"hypotheses_{date}.json"
            
            if hyp_file.exists():
                with open(hyp_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Flatten bundles to hypotheses list
                hypotheses = []
                for bundle in data.get("bundles", []):
                    for hyp in bundle.get("hypotheses", []):
                        hyp["concept_name"] = bundle.get("concept_name", "")
                        hyp["meta_id"] = bundle.get("meta_id", "")
                        hypotheses.append(hyp)
                
                return hypotheses
            
            return []
            
        except Exception as e:
            logger.warning(f"Hypothesis generation failed for {date}: {e}")
            return []
    
    def _register_predictions_for_date(
        self,
        date: str,
        hypotheses: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Register predictions for a date."""
        predictions = []
        
        for hyp in hypotheses:
            hyp_id = hyp.get("hypothesis_id", "")
            confidence = hyp.get("confidence", 0.5)
            mechanism = hyp.get("mechanism", "")
            concept = hyp.get("concept_name", "")
            
            for pred_signal in hyp.get("predicted_next_signals", []):
                if not pred_signal.get("measurable", False):
                    continue
                
                prediction = {
                    "date": date,
                    "hypothesis_id": hyp_id,
                    "concept_name": concept,
                    "mechanism": mechanism,
                    "confidence": confidence,
                    "predicted_signal": pred_signal.get("description", ""),
                    "category": pred_signal.get("category", ""),
                    "canonical_metric": pred_signal.get("canonical_metric", ""),
                    "expected_direction": pred_signal.get("direction", "up"),
                    "timeframe_days": pred_signal.get("expected_timeframe_days", 30),
                }
                
                predictions.append(prediction)
        
        return predictions
    
    def _save_day_outputs(
        self,
        date: str,
        signals: List[Dict],
        metas: List[Dict],
        hypotheses: List[Dict],
        predictions: List[Dict],
    ):
        """Save outputs for a day."""
        day_dir = self.backtest_dir / date
        day_dir.mkdir(parents=True, exist_ok=True)
        
        # Save signals
        with open(day_dir / "signals.json", 'w', encoding='utf-8') as f:
            json.dump(signals, f, indent=2, ensure_ascii=False)
        
        # Save metas
        with open(day_dir / "metas.json", 'w', encoding='utf-8') as f:
            json.dump(metas, f, indent=2, ensure_ascii=False)
        
        # Save hypotheses
        with open(day_dir / "hypotheses.json", 'w', encoding='utf-8') as f:
            json.dump(hypotheses, f, indent=2, ensure_ascii=False)
        
        # Save predictions
        with open(day_dir / "predictions.json", 'w', encoding='utf-8') as f:
            json.dump(predictions, f, indent=2, ensure_ascii=False)
        
        logger.debug(f"Saved outputs for {date}")
    
    def _save_run_summary(
        self,
        summary: ReplayRunSummary,
        day_results: List[ReplayDayResult],
    ):
        """Save run summary."""
        self.backtest_dir.mkdir(parents=True, exist_ok=True)
        
        # Save summary
        summary_file = self.backtest_dir / f"run_{summary.run_id}.json"
        
        output = {
            "summary": summary.to_dict(),
            "day_results": [r.to_dict() for r in day_results],
        }
        
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved run summary to {summary_file}")


# =============================================================================
# TESTS
# =============================================================================

def _test_temporal_filter():
    """Test temporal filtering."""
    data = [
        {"date": "2026-01-15", "value": 1},
        {"date": "2026-02-01", "value": 2},
        {"date": "2026-02-10", "value": 3},
        {"date": "2026-02-15", "value": 4},
    ]
    
    filtered = TemporalDataFilter.filter_by_date(data, "2026-02-05")
    
    assert len(filtered) == 2
    assert filtered[0]["value"] == 1
    assert filtered[1]["value"] == 2
    
    print("[PASS] _test_temporal_filter")


def _test_deterministic_seeding():
    """Test deterministic seeding."""
    seed1 = DeterministicSeeder.get_seed_for_date("2026-02-10")
    seed2 = DeterministicSeeder.get_seed_for_date("2026-02-10")
    seed3 = DeterministicSeeder.get_seed_for_date("2026-02-11")
    
    assert seed1 == seed2  # Same date = same seed
    assert seed1 != seed3  # Different date = different seed
    
    print("[PASS] _test_deterministic_seeding")


def run_tests():
    """Run all tests."""
    print("\n=== HISTORICAL REPLAY RUNNER TESTS ===\n")
    
    _test_temporal_filter()
    _test_deterministic_seeding()
    
    print("\n=== ALL TESTS PASSED ===")


if __name__ == "__main__":
    run_tests()
