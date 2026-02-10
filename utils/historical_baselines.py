"""
Historical Baselines Module

Computes historical percentiles and baselines for signals over
12-26 week windows to contextualize current values.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import math
import statistics


@dataclass
class HistoricalStats:
    """Statistical summary of historical signal values."""
    signal_name: str
    bucket_id: str

    # Basic stats
    mean: float = 0.0
    std: float = 0.0
    median: float = 0.0
    min_value: float = 0.0
    max_value: float = 0.0

    # Percentiles
    p10: float = 0.0
    p25: float = 0.0
    p75: float = 0.0
    p90: float = 0.0

    # Context
    weeks_observed: int = 0
    first_observation: Optional[str] = None
    last_observation: Optional[str] = None

    # Trend
    trend_slope: float = 0.0  # Linear regression slope
    trend_direction: str = "stable"  # rising, falling, stable

    def compute_percentile(self, current_value: float) -> float:
        """
        Compute percentile rank of current value vs historical.

        Returns:
            Percentile (0-100) where current value falls
        """
        if self.std == 0:
            return 50.0  # No variance, return median

        # Z-score approach
        z = (current_value - self.mean) / self.std

        # Convert z-score to percentile using normal CDF approximation
        # Using the Abramowitz and Stegun approximation
        percentile = self._normal_cdf(z) * 100

        return max(0, min(100, percentile))

    def compute_z_score(self, current_value: float) -> float:
        """Compute z-score relative to historical distribution."""
        if self.std == 0:
            return 0.0
        return (current_value - self.mean) / self.std

    def is_anomaly(self, current_value: float, threshold: float = 2.5) -> bool:
        """Check if current value is an anomaly (beyond threshold std devs)."""
        z = self.compute_z_score(current_value)
        return abs(z) > threshold

    @staticmethod
    def _normal_cdf(z: float) -> float:
        """Approximate normal CDF using Abramowitz and Stegun formula."""
        # Constants
        a1, a2, a3 = 0.254829592, -0.284496736, 1.421413741
        a4, a5 = -1.453152027, 1.061405429
        p = 0.3275911

        sign = 1 if z >= 0 else -1
        z = abs(z) / math.sqrt(2)

        t = 1.0 / (1.0 + p * z)
        y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * math.exp(-z * z)

        return 0.5 * (1.0 + sign * y)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "signal_name": self.signal_name,
            "bucket_id": self.bucket_id,
            "mean": round(self.mean, 2),
            "std": round(self.std, 2),
            "median": round(self.median, 2),
            "min_value": round(self.min_value, 2),
            "max_value": round(self.max_value, 2),
            "p10": round(self.p10, 2),
            "p25": round(self.p25, 2),
            "p75": round(self.p75, 2),
            "p90": round(self.p90, 2),
            "weeks_observed": self.weeks_observed,
            "first_observation": self.first_observation,
            "last_observation": self.last_observation,
            "trend_slope": round(self.trend_slope, 4),
            "trend_direction": self.trend_direction,
        }


@dataclass
class BaselineConfig:
    """Configuration for baseline calculations."""
    short_window_weeks: int = 12   # 3 months
    long_window_weeks: int = 26    # 6 months
    min_weeks_required: int = 4    # Minimum for valid baseline
    anomaly_threshold: float = 2.5 # Z-score threshold for anomalies


@dataclass
class WeeklySnapshot:
    """A weekly snapshot of bucket signal values."""
    week: str  # Format: YYYY-WXX
    generated_at: datetime
    buckets: Dict[str, Dict[str, Any]]  # bucket_id -> {signal_name: value}

    def get_signal(self, bucket_id: str, signal_name: str) -> Optional[float]:
        """Get a specific signal value from a bucket."""
        bucket = self.buckets.get(bucket_id, {})
        value = bucket.get(signal_name)
        return float(value) if value is not None else None

    def to_dict(self) -> Dict[str, Any]:
        """Convert snapshot to dictionary."""
        return {
            "week": self.week,
            "generated_at": self.generated_at.isoformat(),
            "buckets": self.buckets,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WeeklySnapshot":
        """Create snapshot from dictionary."""
        return cls(
            week=data["week"],
            generated_at=datetime.fromisoformat(data["generated_at"]),
            buckets=data.get("buckets", {}),
        )


class HistoricalBaselineCalculator:
    """
    Calculates historical baselines from weekly snapshots.

    Supports:
    - 12-week (short) and 26-week (long) baselines
    - Percentile rankings vs history
    - Anomaly detection
    - Trend analysis
    """

    def __init__(self, data_dir: Path = None, config: BaselineConfig = None):
        """
        Initialize calculator.

        Args:
            data_dir: Directory containing historical snapshot files
            config: Baseline configuration
        """
        self.data_dir = data_dir or Path("data/historical")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.config = config or BaselineConfig()

        # Cache for loaded historical data
        self._history_cache: Dict[str, List[Dict]] = {}
        self._stats_cache: Dict[str, HistoricalStats] = {}

    def load_weekly_snapshots(self, weeks_back: int = 26) -> Dict[str, List[Dict[str, Any]]]:
        """
        Load historical weekly snapshot files.

        Args:
            weeks_back: Number of weeks to load

        Returns:
            Dict of week_id -> snapshot data
        """
        snapshots = {}

        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(weeks=weeks_back)

        # Try multiple possible file patterns
        patterns = [
            "bucket_profiles_*.json",
            "*-W*.json",
            "weekly_*.json",
        ]

        # Also check cache directory
        cache_dir = Path("data/cache")
        historical_dir = self.data_dir

        for directory in [historical_dir, cache_dir]:
            if not directory.exists():
                continue

            for pattern in patterns:
                for file_path in directory.glob(pattern):
                    try:
                        # Extract week identifier from filename
                        week_id = self._extract_week_id(file_path)
                        if week_id and week_id not in snapshots:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                data = json.load(f)
                                snapshots[week_id] = data
                    except (json.JSONDecodeError, IOError) as e:
                        print(f"Warning: Could not load {file_path}: {e}")

        return snapshots

    def _extract_week_id(self, file_path: Path) -> Optional[str]:
        """Extract week identifier from filename."""
        name = file_path.stem

        # Try various formats
        # Format: YYYY-WXX
        import re
        match = re.search(r'(\d{4}-W\d{2})', name)
        if match:
            return match.group(1)

        # Format: YYYY-MM-DD (convert to week)
        match = re.search(r'(\d{4}-\d{2}-\d{2})', name)
        if match:
            date = datetime.strptime(match.group(1), "%Y-%m-%d")
            return date.strftime("%Y-W%W")

        return None

    def build_bucket_history(self, bucket_id: str,
                             signal_name: str) -> List[Tuple[str, float]]:
        """
        Build time series of signal values for a bucket.

        Args:
            bucket_id: Bucket identifier
            signal_name: Signal type (tms, ccs, etc.)

        Returns:
            List of (week_id, value) tuples sorted by week
        """
        cache_key = f"{bucket_id}:{signal_name}"
        if cache_key in self._history_cache:
            return self._history_cache[cache_key]

        # Load all available snapshots
        snapshots = self.load_weekly_snapshots(self.config.long_window_weeks)

        history = []
        for week_id, data in snapshots.items():
            # Handle both list format and dict format
            if isinstance(data, list):
                buckets = data
            elif isinstance(data, dict):
                buckets = data.get("bucket_profiles", data.get("profiles", []))
                if isinstance(buckets, dict):
                    buckets = list(buckets.values())
            else:
                continue

            for bucket in buckets:
                if bucket.get("bucket_id") == bucket_id:
                    value = bucket.get(signal_name)
                    if value is not None:
                        history.append((week_id, float(value)))
                    break

        # Sort by week
        history.sort(key=lambda x: x[0])

        self._history_cache[cache_key] = history
        return history

    def compute_baseline_stats(self, bucket_id: str, signal_name: str,
                               window_weeks: int = None) -> HistoricalStats:
        """
        Compute statistical baseline for a signal.

        Args:
            bucket_id: Bucket identifier
            signal_name: Signal type
            window_weeks: Window size (default: config.long_window_weeks)

        Returns:
            HistoricalStats object
        """
        window = window_weeks or self.config.long_window_weeks
        cache_key = f"{bucket_id}:{signal_name}:{window}"

        if cache_key in self._stats_cache:
            return self._stats_cache[cache_key]

        history = self.build_bucket_history(bucket_id, signal_name)

        # Filter to window
        if len(history) > window:
            history = history[-window:]

        stats = HistoricalStats(
            signal_name=signal_name,
            bucket_id=bucket_id,
        )

        if len(history) < self.config.min_weeks_required:
            # Not enough data for reliable baseline
            stats.weeks_observed = len(history)
            return stats

        values = [v for _, v in history]
        weeks = [w for w, _ in history]

        # Basic statistics
        stats.mean = statistics.mean(values)
        stats.std = statistics.stdev(values) if len(values) > 1 else 0
        stats.median = statistics.median(values)
        stats.min_value = min(values)
        stats.max_value = max(values)
        stats.weeks_observed = len(values)
        stats.first_observation = weeks[0]
        stats.last_observation = weeks[-1]

        # Percentiles
        sorted_values = sorted(values)
        n = len(sorted_values)
        stats.p10 = sorted_values[int(n * 0.10)]
        stats.p25 = sorted_values[int(n * 0.25)]
        stats.p75 = sorted_values[int(n * 0.75)]
        stats.p90 = sorted_values[min(int(n * 0.90), n - 1)]

        # Trend (simple linear regression)
        if len(values) >= 4:
            slope = self._compute_trend_slope(values)
            stats.trend_slope = slope

            # Classify trend direction
            # Significant if slope > 1 point per week
            if slope > 1.0:
                stats.trend_direction = "rising"
            elif slope < -1.0:
                stats.trend_direction = "falling"
            else:
                stats.trend_direction = "stable"

        self._stats_cache[cache_key] = stats
        return stats

    def _compute_trend_slope(self, values: List[float]) -> float:
        """Compute linear regression slope."""
        n = len(values)
        if n < 2:
            return 0.0

        x = list(range(n))  # Week indices
        y = values

        # Simple linear regression
        x_mean = sum(x) / n
        y_mean = sum(y) / n

        numerator = sum((x[i] - x_mean) * (y[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))

        if denominator == 0:
            return 0.0

        return numerator / denominator

    def compute_historical_percentile(self, bucket_id: str, signal_name: str,
                                       current_value: float,
                                       window_weeks: int = None) -> float:
        """
        Compute percentile rank of current value vs historical baseline.

        Args:
            bucket_id: Bucket identifier
            signal_name: Signal type
            current_value: Current signal value
            window_weeks: Baseline window

        Returns:
            Percentile (0-100)
        """
        stats = self.compute_baseline_stats(bucket_id, signal_name, window_weeks)

        if stats.weeks_observed < self.config.min_weeks_required:
            return 50.0  # Not enough history, return median

        return stats.compute_percentile(current_value)

    def compute_all_baselines(self, bucket_id: str) -> Dict[str, Dict[str, Any]]:
        """
        Compute baselines for all signals of a bucket.

        Args:
            bucket_id: Bucket identifier

        Returns:
            Dict of signal_name -> {stats_12w, stats_26w, current_percentiles}
        """
        signals = ["tms", "ccs", "eis_offensive", "eis_defensive", "nas", "pms", "css"]
        results = {}

        for signal in signals:
            stats_12w = self.compute_baseline_stats(
                bucket_id, signal, self.config.short_window_weeks
            )
            stats_26w = self.compute_baseline_stats(
                bucket_id, signal, self.config.long_window_weeks
            )

            results[signal] = {
                "stats_12w": stats_12w.to_dict(),
                "stats_26w": stats_26w.to_dict(),
            }

        return results

    def get_percentile_context(self, bucket_id: str, signal_name: str,
                                current_value: float) -> Dict[str, Any]:
        """
        Get full percentile context for a current value.

        Args:
            bucket_id: Bucket identifier
            signal_name: Signal type
            current_value: Current signal value

        Returns:
            Dict with percentiles, z-scores, and anomaly flags
        """
        stats_12w = self.compute_baseline_stats(
            bucket_id, signal_name, self.config.short_window_weeks
        )
        stats_26w = self.compute_baseline_stats(
            bucket_id, signal_name, self.config.long_window_weeks
        )

        return {
            "current_value": current_value,
            "percentile_12w": stats_12w.compute_percentile(current_value),
            "percentile_26w": stats_26w.compute_percentile(current_value),
            "z_score_12w": stats_12w.compute_z_score(current_value),
            "z_score_26w": stats_26w.compute_z_score(current_value),
            "is_anomaly_12w": stats_12w.is_anomaly(current_value, self.config.anomaly_threshold),
            "is_anomaly_26w": stats_26w.is_anomaly(current_value, self.config.anomaly_threshold),
            "mean_12w": stats_12w.mean,
            "mean_26w": stats_26w.mean,
            "std_12w": stats_12w.std,
            "std_26w": stats_26w.std,
            "trend_12w": stats_12w.trend_direction,
            "trend_26w": stats_26w.trend_direction,
            "weeks_observed_12w": stats_12w.weeks_observed,
            "weeks_observed_26w": stats_26w.weeks_observed,
        }

    def save_snapshot(self, week_id: str, profiles: List[Dict[str, Any]]) -> Path:
        """
        Save current snapshot for future baseline calculations.

        Args:
            week_id: Week identifier (YYYY-WXX format)
            profiles: List of bucket profile dicts

        Returns:
            Path to saved file
        """
        output_file = self.data_dir / f"{week_id}.json"

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump({
                "week_id": week_id,
                "saved_at": datetime.now().isoformat(),
                "bucket_profiles": profiles,
            }, f, indent=2)

        return output_file

    def clear_cache(self) -> None:
        """Clear internal caches."""
        self._history_cache = {}
        self._stats_cache = {}


# Convenience function for quick percentile lookup
def get_historical_percentile(bucket_id: str, signal_name: str,
                               current_value: float, window_weeks: int = 12) -> float:
    """
    Quick function to get historical percentile.

    Args:
        bucket_id: Bucket identifier
        signal_name: Signal type
        current_value: Current value
        window_weeks: Baseline window

    Returns:
        Percentile (0-100)
    """
    calc = HistoricalBaselineCalculator()
    return calc.compute_historical_percentile(
        bucket_id, signal_name, current_value, window_weeks
    )