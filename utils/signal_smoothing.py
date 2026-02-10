"""
Signal Smoothing Module

Provides EWMA (Exponentially Weighted Moving Average) smoothing and
winsorization for volatile signals like NAS (Narrative Attention) and
CSS (Crypto Sentiment).
"""

from dataclasses import dataclass
from typing import List, Optional, Dict, Any, Tuple
import math
from datetime import datetime


@dataclass
class SmoothingConfig:
    """Configuration for signal smoothing."""
    signal_name: str
    ewma_alpha: float = 0.3       # Smoothing factor (0-1)
    enabled: bool = True
    winsorize: bool = True
    winsorize_lower: float = 0.05  # 5th percentile
    winsorize_upper: float = 0.95  # 95th percentile
    min_history: int = 3           # Minimum points for smoothing


# Default smoothing configurations by signal type
DEFAULT_SMOOTHING_CONFIGS = {
    "nas": SmoothingConfig(
        signal_name="nas",
        ewma_alpha=0.3,      # Slower smoothing for news (more stable)
        enabled=True,
        winsorize=True,
    ),
    "css": SmoothingConfig(
        signal_name="css",
        ewma_alpha=0.25,     # Even slower for crypto (very volatile)
        enabled=True,
        winsorize=True,
    ),
    "tms": SmoothingConfig(
        signal_name="tms",
        ewma_alpha=0.5,      # More reactive for technical signals
        enabled=False,       # Usually stable enough without smoothing
        winsorize=False,
    ),
    "ccs": SmoothingConfig(
        signal_name="ccs",
        ewma_alpha=0.5,
        enabled=False,
        winsorize=False,
    ),
    "pms": SmoothingConfig(
        signal_name="pms",
        ewma_alpha=0.4,
        enabled=True,        # Market signals can be volatile
        winsorize=True,
    ),
}


class SignalSmoother:
    """
    Applies EWMA smoothing and winsorization to signals.

    EWMA reduces noise while remaining responsive to real trends.
    Winsorization clips extreme values to reduce outlier impact.
    """

    def __init__(self, configs: Dict[str, SmoothingConfig] = None):
        """
        Initialize smoother with configurations.

        Args:
            configs: Signal-specific configurations. Uses defaults if not provided.
        """
        self.configs = configs or DEFAULT_SMOOTHING_CONFIGS.copy()
        self._state: Dict[str, Dict[str, Any]] = {}  # Per-signal state

    def get_config(self, signal_name: str) -> SmoothingConfig:
        """Get config for a signal, with fallback to defaults."""
        return self.configs.get(signal_name, SmoothingConfig(signal_name=signal_name))

    def winsorize(self, values: List[float], lower_pct: float = 0.05,
                  upper_pct: float = 0.95) -> List[float]:
        """
        Winsorize values by clipping to percentile bounds.

        Args:
            values: List of values to winsorize
            lower_pct: Lower percentile (0-1)
            upper_pct: Upper percentile (0-1)

        Returns:
            Winsorized values
        """
        if len(values) < 2:
            return values

        sorted_vals = sorted(values)
        n = len(sorted_vals)

        lower_idx = max(0, int(n * lower_pct))
        upper_idx = min(n - 1, int(n * upper_pct))

        lower_bound = sorted_vals[lower_idx]
        upper_bound = sorted_vals[upper_idx]

        return [max(lower_bound, min(upper_bound, v)) for v in values]

    def ewma(self, values: List[float], alpha: float = 0.3) -> List[float]:
        """
        Apply EWMA to a series of values.

        Args:
            values: Time series (oldest first)
            alpha: Smoothing factor (0-1). Higher = more reactive.

        Returns:
            Smoothed values (same length as input)
        """
        if not values:
            return []

        smoothed = [values[0]]  # First value is unchanged

        for i in range(1, len(values)):
            smoothed.append(alpha * values[i] + (1 - alpha) * smoothed[-1])

        return smoothed

    def smooth_signal(self, signal_name: str, new_value: float,
                      bucket_id: str = "default") -> Tuple[float, Dict[str, Any]]:
        """
        Apply configured smoothing to a new signal value.

        Args:
            signal_name: Signal type (tms, ccs, nas, etc.)
            new_value: New raw signal value
            bucket_id: Bucket identifier for state tracking

        Returns:
            Tuple of (smoothed_value, metadata)
        """
        config = self.get_config(signal_name)
        state_key = f"{signal_name}:{bucket_id}"

        # Initialize state if needed
        if state_key not in self._state:
            self._state[state_key] = {
                "history": [],
                "ewma": None,
                "last_updated": None,
            }

        state = self._state[state_key]

        # Add to history
        state["history"].append(new_value)
        if len(state["history"]) > 52:  # Keep 1 year max
            state["history"] = state["history"][-52:]

        # Apply smoothing if enabled and enough history
        if not config.enabled or len(state["history"]) < config.min_history:
            state["ewma"] = new_value
            state["last_updated"] = datetime.now()
            return new_value, {
                "smoothed": False,
                "raw_value": new_value,
                "ewma_value": new_value,
                "history_length": len(state["history"]),
            }

        # Winsorize history if enabled
        history = state["history"]
        if config.winsorize:
            history = self.winsorize(
                history,
                config.winsorize_lower,
                config.winsorize_upper
            )

        # Apply EWMA
        smoothed_history = self.ewma(history, config.ewma_alpha)
        smoothed_value = smoothed_history[-1]

        state["ewma"] = smoothed_value
        state["last_updated"] = datetime.now()

        # Compute smoothing metadata
        raw_std = self._std(state["history"])
        smoothed_std = self._std(smoothed_history)
        noise_reduction = 1 - (smoothed_std / raw_std) if raw_std > 0 else 0

        metadata = {
            "smoothed": True,
            "raw_value": new_value,
            "ewma_value": smoothed_value,
            "alpha": config.ewma_alpha,
            "winsorized": config.winsorize,
            "history_length": len(state["history"]),
            "noise_reduction": round(noise_reduction, 3),
        }

        return smoothed_value, metadata

    def get_smoothed_value(self, signal_name: str, bucket_id: str = "default") -> Optional[float]:
        """Get the current smoothed value for a signal."""
        state_key = f"{signal_name}:{bucket_id}"
        if state_key in self._state:
            return self._state[state_key].get("ewma")
        return None

    def get_history(self, signal_name: str, bucket_id: str = "default") -> List[float]:
        """Get raw value history for a signal."""
        state_key = f"{signal_name}:{bucket_id}"
        if state_key in self._state:
            return self._state[state_key].get("history", [])
        return []

    def reset_state(self, signal_name: str = None, bucket_id: str = None) -> None:
        """Reset smoothing state (useful for testing)."""
        if signal_name is None and bucket_id is None:
            self._state = {}
        else:
            keys_to_remove = []
            for key in self._state:
                if signal_name and bucket_id:
                    if key == f"{signal_name}:{bucket_id}":
                        keys_to_remove.append(key)
                elif signal_name:
                    if key.startswith(f"{signal_name}:"):
                        keys_to_remove.append(key)
                elif bucket_id:
                    if key.endswith(f":{bucket_id}"):
                        keys_to_remove.append(key)

            for key in keys_to_remove:
                del self._state[key]

    def load_history(self, signal_name: str, bucket_id: str,
                     history: List[float]) -> None:
        """
        Load historical values (e.g., from database).

        Args:
            signal_name: Signal type
            bucket_id: Bucket identifier
            history: Historical values (oldest first)
        """
        state_key = f"{signal_name}:{bucket_id}"
        config = self.get_config(signal_name)

        self._state[state_key] = {
            "history": history[-52:],  # Keep max 52 weeks
            "ewma": None,
            "last_updated": datetime.now(),
        }

        # Compute EWMA from history
        if config.enabled and len(history) >= config.min_history:
            processed = history
            if config.winsorize:
                processed = self.winsorize(
                    processed,
                    config.winsorize_lower,
                    config.winsorize_upper
                )
            smoothed = self.ewma(processed, config.ewma_alpha)
            self._state[state_key]["ewma"] = smoothed[-1]
        elif history:
            self._state[state_key]["ewma"] = history[-1]

    @staticmethod
    def _std(values: List[float]) -> float:
        """Compute standard deviation."""
        if len(values) < 2:
            return 0.0
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        return variance ** 0.5


class BatchSmoother:
    """
    Batch processing for smoothing multiple signals/buckets efficiently.
    """

    def __init__(self, smoother: SignalSmoother = None):
        self.smoother = smoother or SignalSmoother()

    def smooth_bucket_signals(self, bucket_id: str,
                               signals: Dict[str, float]) -> Dict[str, Dict[str, Any]]:
        """
        Smooth all signals for a bucket.

        Args:
            bucket_id: Bucket identifier
            signals: Dict of signal_name -> raw_value

        Returns:
            Dict of signal_name -> {smoothed_value, metadata}
        """
        results = {}

        for signal_name, raw_value in signals.items():
            if raw_value is not None:
                smoothed, metadata = self.smoother.smooth_signal(
                    signal_name, raw_value, bucket_id
                )
                results[signal_name] = {
                    "smoothed_value": smoothed,
                    "raw_value": raw_value,
                    **metadata
                }
            else:
                results[signal_name] = {
                    "smoothed_value": None,
                    "raw_value": None,
                    "smoothed": False,
                }

        return results

    def smooth_all_buckets(self, data: Dict[str, Dict[str, float]]) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """
        Smooth signals for all buckets.

        Args:
            data: Dict of bucket_id -> {signal_name -> raw_value}

        Returns:
            Dict of bucket_id -> {signal_name -> {smoothed_value, metadata}}
        """
        results = {}

        for bucket_id, signals in data.items():
            results[bucket_id] = self.smooth_bucket_signals(bucket_id, signals)

        return results


# Convenience functions
def smooth_nas(value: float, bucket_id: str, smoother: SignalSmoother = None) -> float:
    """Convenience function to smooth NAS signal."""
    s = smoother or SignalSmoother()
    smoothed, _ = s.smooth_signal("nas", value, bucket_id)
    return smoothed


def smooth_css(value: float, bucket_id: str, smoother: SignalSmoother = None) -> float:
    """Convenience function to smooth CSS signal."""
    s = smoother or SignalSmoother()
    smoothed, _ = s.smooth_signal("css", value, bucket_id)
    return smoothed