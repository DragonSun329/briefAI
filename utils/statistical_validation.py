#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Statistical Validation Utilities for briefAI

Provides rigorous statistical methods for validating prediction accuracy:
- P-value calculations for correlations
- Confidence intervals (bootstrap and analytical)
- Brier score tracking
- Walk-forward validation splits
- Multiple hypothesis correction

Author: briefAI Team
"""

import math
import random
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict
import json


@dataclass
class StatisticalResult:
    """Container for statistical test results."""
    metric_name: str
    value: float
    p_value: float
    confidence_interval: Tuple[float, float]
    sample_size: int
    is_significant: bool  # p < 0.05
    warning: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric": self.metric_name,
            "value": round(self.value, 4),
            "p_value": round(self.p_value, 4),
            "ci_lower": round(self.confidence_interval[0], 4),
            "ci_upper": round(self.confidence_interval[1], 4),
            "n": self.sample_size,
            "significant": self.is_significant,
            "warning": self.warning
        }


@dataclass
class BrierScoreTracker:
    """
    Tracks Brier score over time for probability calibration.
    
    Brier Score = (1/n) * Σ(forecast_i - outcome_i)²
    - 0 = perfect predictions
    - 0.25 = random guessing (for 50/50 events)
    - 1 = always wrong
    
    Good calibration: <0.15
    Acceptable: <0.25
    Poor: >0.25
    """
    scores: List[Dict] = field(default_factory=list)
    
    def add_prediction(
        self,
        entity_id: str,
        predicted_probability: float,
        actual_outcome: int,  # 0 or 1
        prediction_date: str,
        horizon_days: int,
    ):
        """Add a prediction for Brier score calculation."""
        score = (predicted_probability - actual_outcome) ** 2
        self.scores.append({
            "entity_id": entity_id,
            "predicted_prob": predicted_probability,
            "actual_outcome": actual_outcome,
            "brier_score": score,
            "date": prediction_date,
            "horizon_days": horizon_days,
        })
    
    def get_brier_score(self, horizon_days: Optional[int] = None) -> Optional[float]:
        """Calculate overall Brier score, optionally filtered by horizon."""
        filtered = self.scores
        if horizon_days is not None:
            filtered = [s for s in self.scores if s["horizon_days"] == horizon_days]
        
        if not filtered:
            return None
        
        return sum(s["brier_score"] for s in filtered) / len(filtered)
    
    def get_calibration_curve(self, n_bins: int = 10) -> List[Dict]:
        """
        Generate calibration curve data.
        
        Bins predictions by predicted probability and compares
        mean prediction to observed frequency.
        """
        if not self.scores:
            return []
        
        # Sort by predicted probability
        sorted_scores = sorted(self.scores, key=lambda x: x["predicted_prob"])
        
        # Create bins
        bin_size = len(sorted_scores) // n_bins
        bins = []
        
        for i in range(n_bins):
            start = i * bin_size
            end = start + bin_size if i < n_bins - 1 else len(sorted_scores)
            bin_scores = sorted_scores[start:end]
            
            if bin_scores:
                mean_predicted = sum(s["predicted_prob"] for s in bin_scores) / len(bin_scores)
                observed_freq = sum(s["actual_outcome"] for s in bin_scores) / len(bin_scores)
                
                bins.append({
                    "bin": i + 1,
                    "mean_predicted": round(mean_predicted, 3),
                    "observed_frequency": round(observed_freq, 3),
                    "count": len(bin_scores),
                    "calibration_error": round(abs(mean_predicted - observed_freq), 3),
                })
        
        return bins
    
    def get_reliability_diagram_data(self) -> Dict[str, Any]:
        """Get data for reliability diagram visualization."""
        calibration = self.get_calibration_curve()
        brier = self.get_brier_score()
        
        # Calculate reliability component
        reliability = 0
        if calibration:
            n_total = sum(b["count"] for b in calibration)
            for b in calibration:
                reliability += (b["count"] / n_total) * (b["mean_predicted"] - b["observed_frequency"]) ** 2
        
        return {
            "brier_score": round(brier, 4) if brier else None,
            "reliability": round(reliability, 4) if calibration else None,
            "calibration_curve": calibration,
            "total_predictions": len(self.scores),
        }


class StatisticalValidator:
    """
    Performs statistical validation on prediction results.
    
    Implements:
    - Correlation tests with p-values
    - Bootstrap confidence intervals
    - Multiple testing correction
    - Minimum sample size enforcement
    """
    
    MIN_SAMPLE_SIZE = 30  # Minimum n for reliable statistics
    SIGNIFICANCE_LEVEL = 0.05  # Alpha for hypothesis tests
    
    def __init__(self, min_sample_size: int = 30, alpha: float = 0.05):
        self.min_sample_size = min_sample_size
        self.alpha = alpha
    
    def pearson_correlation_test(
        self,
        x: List[float],
        y: List[float],
        name: str = "correlation"
    ) -> StatisticalResult:
        """
        Calculate Pearson correlation with p-value.
        
        Uses t-test for significance:
        t = r * sqrt(n-2) / sqrt(1-r²)
        df = n - 2
        """
        n = len(x)
        if n != len(y):
            raise ValueError("x and y must have same length")
        
        warning = None
        if n < self.min_sample_size:
            warning = f"Sample size {n} < {self.min_sample_size}, results may be unreliable"
        
        # Calculate means
        mean_x = sum(x) / n
        mean_y = sum(y) / n
        
        # Calculate correlation
        numerator = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
        denom_x = math.sqrt(sum((xi - mean_x) ** 2 for xi in x))
        denom_y = math.sqrt(sum((yi - mean_y) ** 2 for yi in y))
        
        if denom_x == 0 or denom_y == 0:
            return StatisticalResult(
                metric_name=name,
                value=0,
                p_value=1.0,
                confidence_interval=(0, 0),
                sample_size=n,
                is_significant=False,
                warning="Zero variance in data"
            )
        
        r = numerator / (denom_x * denom_y)
        
        # Calculate t-statistic and p-value
        if abs(r) >= 1:
            p_value = 0.0
        else:
            t_stat = r * math.sqrt(n - 2) / math.sqrt(1 - r ** 2)
            # Two-tailed p-value using approximation
            p_value = self._t_to_p(abs(t_stat), n - 2)
        
        # Fisher z-transformation for confidence interval
        if abs(r) < 1:
            z = 0.5 * math.log((1 + r) / (1 - r))
            se = 1 / math.sqrt(n - 3) if n > 3 else 0.5
            z_crit = 1.96  # 95% CI
            ci_low = math.tanh(z - z_crit * se)
            ci_high = math.tanh(z + z_crit * se)
        else:
            ci_low, ci_high = r, r
        
        return StatisticalResult(
            metric_name=name,
            value=r,
            p_value=p_value,
            confidence_interval=(ci_low, ci_high),
            sample_size=n,
            is_significant=p_value < self.alpha,
            warning=warning
        )
    
    def _t_to_p(self, t: float, df: int) -> float:
        """Approximate p-value from t-statistic (two-tailed)."""
        # Using approximation for large df
        if df > 100:
            # Normal approximation
            from math import erf
            return 2 * (1 - 0.5 * (1 + erf(t / math.sqrt(2))))
        
        # Simple approximation for smaller df
        # This is a rough approximation; for production use scipy.stats
        x = df / (df + t ** 2)
        p = self._incomplete_beta(df / 2, 0.5, x)
        return p
    
    def _incomplete_beta(self, a: float, b: float, x: float) -> float:
        """Simple incomplete beta function approximation."""
        # Very rough approximation - for production use scipy
        if x <= 0:
            return 0
        if x >= 1:
            return 1
        
        # Using continued fraction approximation
        result = 0
        for i in range(100):
            term = math.exp(
                math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) +
                a * math.log(x) + b * math.log(1 - x)
            ) / a
            result += term * (x ** i) / (a + i)
            if term < 1e-10:
                break
        
        return min(1.0, max(0.0, result))
    
    def bootstrap_confidence_interval(
        self,
        data: List[float],
        statistic_func: callable,
        n_bootstrap: int = 1000,
        confidence: float = 0.95,
        name: str = "bootstrap"
    ) -> StatisticalResult:
        """
        Calculate bootstrap confidence interval for any statistic.
        
        Args:
            data: Sample data
            statistic_func: Function to calculate statistic (e.g., mean, median)
            n_bootstrap: Number of bootstrap samples
            confidence: Confidence level (default 95%)
            name: Name for the result
        """
        n = len(data)
        warning = None
        if n < self.min_sample_size:
            warning = f"Sample size {n} < {self.min_sample_size}"
        
        # Original statistic
        original_stat = statistic_func(data)
        
        # Bootstrap samples
        bootstrap_stats = []
        for _ in range(n_bootstrap):
            sample = [random.choice(data) for _ in range(n)]
            bootstrap_stats.append(statistic_func(sample))
        
        # Calculate percentile confidence interval
        alpha = 1 - confidence
        sorted_stats = sorted(bootstrap_stats)
        lower_idx = int(n_bootstrap * alpha / 2)
        upper_idx = int(n_bootstrap * (1 - alpha / 2))
        
        ci_lower = sorted_stats[lower_idx]
        ci_upper = sorted_stats[upper_idx]
        
        # Calculate p-value (proportion of bootstrap samples with different sign)
        # This is a simple two-tailed test for whether statistic differs from 0
        if original_stat > 0:
            p_value = sum(1 for s in bootstrap_stats if s <= 0) / n_bootstrap
        else:
            p_value = sum(1 for s in bootstrap_stats if s >= 0) / n_bootstrap
        p_value = min(2 * p_value, 1.0)  # Two-tailed
        
        return StatisticalResult(
            metric_name=name,
            value=original_stat,
            p_value=p_value,
            confidence_interval=(ci_lower, ci_upper),
            sample_size=n,
            is_significant=p_value < self.alpha,
            warning=warning
        )
    
    def accuracy_with_ci(
        self,
        correct: int,
        total: int,
        name: str = "accuracy"
    ) -> StatisticalResult:
        """
        Calculate accuracy with Wilson score confidence interval.
        
        Wilson score interval is preferred over normal approximation
        for proportions, especially with small samples.
        """
        if total == 0:
            return StatisticalResult(
                metric_name=name,
                value=0,
                p_value=1.0,
                confidence_interval=(0, 0),
                sample_size=0,
                is_significant=False,
                warning="No data"
            )
        
        warning = None
        if total < self.min_sample_size:
            warning = f"Sample size {total} < {self.min_sample_size}"
        
        p = correct / total
        z = 1.96  # 95% CI
        
        # Wilson score interval
        denominator = 1 + z ** 2 / total
        centre = (p + z ** 2 / (2 * total)) / denominator
        margin = z * math.sqrt((p * (1 - p) + z ** 2 / (4 * total)) / total) / denominator
        
        ci_lower = max(0, centre - margin)
        ci_upper = min(1, centre + margin)
        
        # One-sample proportion test vs 0.5 (random baseline)
        # z = (p - 0.5) / sqrt(0.5 * 0.5 / n)
        z_stat = (p - 0.5) / math.sqrt(0.25 / total) if total > 0 else 0
        p_value = 2 * (1 - 0.5 * (1 + math.erf(abs(z_stat) / math.sqrt(2))))
        
        return StatisticalResult(
            metric_name=name,
            value=p,
            p_value=p_value,
            confidence_interval=(ci_lower, ci_upper),
            sample_size=total,
            is_significant=p_value < self.alpha,
            warning=warning
        )
    
    def bonferroni_correction(
        self,
        results: List[StatisticalResult]
    ) -> List[StatisticalResult]:
        """
        Apply Bonferroni correction for multiple comparisons.
        
        Adjusts alpha level to control family-wise error rate.
        """
        n_tests = len(results)
        adjusted_alpha = self.alpha / n_tests
        
        corrected = []
        for r in results:
            corrected.append(StatisticalResult(
                metric_name=r.metric_name,
                value=r.value,
                p_value=min(r.p_value * n_tests, 1.0),  # Adjusted p-value
                confidence_interval=r.confidence_interval,
                sample_size=r.sample_size,
                is_significant=r.p_value < adjusted_alpha,
                warning=r.warning or f"Bonferroni adjusted (k={n_tests})"
            ))
        
        return corrected


class WalkForwardValidator:
    """
    Walk-forward validation for time-series predictions.
    
    Implements expanding window and rolling window approaches
    to avoid lookahead bias and test temporal stability.
    """
    
    def __init__(
        self,
        train_ratio: float = 0.7,
        min_train_size: int = 30,
        step_days: int = 7,
    ):
        self.train_ratio = train_ratio
        self.min_train_size = min_train_size
        self.step_days = step_days
    
    def create_splits(
        self,
        events: List[Dict],
        date_field: str = "breakout_date"
    ) -> List[Dict[str, Any]]:
        """
        Create train/validate splits for walk-forward validation.
        
        Returns list of splits, each containing:
        - train_events: Events for training
        - validate_events: Events for validation
        - cutoff_date: Date separating train/validate
        - fold: Fold number
        """
        # Sort events by date
        sorted_events = sorted(
            events,
            key=lambda e: e.get(date_field, "9999-12-31")
        )
        
        n = len(sorted_events)
        if n < self.min_train_size * 2:
            # Not enough data for proper validation
            return [{
                "train_events": sorted_events[:int(n * self.train_ratio)],
                "validate_events": sorted_events[int(n * self.train_ratio):],
                "cutoff_date": sorted_events[int(n * self.train_ratio)][date_field] if int(n * self.train_ratio) < n else None,
                "fold": 1,
            }]
        
        splits = []
        train_size = max(self.min_train_size, int(n * self.train_ratio))
        
        # Expanding window approach
        fold = 1
        for i in range(train_size, n - self.min_train_size // 2, max(1, (n - train_size) // 5)):
            train_events = sorted_events[:i]
            validate_events = sorted_events[i:]
            
            splits.append({
                "train_events": train_events,
                "validate_events": validate_events,
                "cutoff_date": sorted_events[i][date_field],
                "fold": fold,
                "train_size": len(train_events),
                "validate_size": len(validate_events),
            })
            fold += 1
        
        return splits
    
    def evaluate_split(
        self,
        train_events: List[Dict],
        validate_events: List[Dict],
        prediction_func: callable,
    ) -> Dict[str, Any]:
        """
        Evaluate a single train/validate split.
        
        Args:
            train_events: Events used for training/calibration
            validate_events: Events used for validation
            prediction_func: Function that takes (train, event) and returns prediction
            
        Returns:
            Validation metrics for this split
        """
        predictions = []
        actuals = []
        
        for event in validate_events:
            pred = prediction_func(train_events, event)
            predictions.append(pred)
            actuals.append(1)  # All events in ground truth actually happened
        
        # Calculate metrics
        correct = sum(1 for p in predictions if p >= 0.5)
        total = len(predictions)
        
        return {
            "accuracy": correct / total if total > 0 else 0,
            "predictions": predictions,
            "n_train": len(train_events),
            "n_validate": len(validate_events),
        }
    
    def run_walk_forward(
        self,
        events: List[Dict],
        prediction_func: callable,
        date_field: str = "breakout_date"
    ) -> Dict[str, Any]:
        """
        Run full walk-forward validation.
        
        Returns aggregated results across all folds.
        """
        splits = self.create_splits(events, date_field)
        
        fold_results = []
        all_accuracies = []
        
        for split in splits:
            result = self.evaluate_split(
                split["train_events"],
                split["validate_events"],
                prediction_func
            )
            result["fold"] = split["fold"]
            result["cutoff_date"] = split["cutoff_date"]
            fold_results.append(result)
            all_accuracies.append(result["accuracy"])
        
        # Calculate aggregate statistics
        validator = StatisticalValidator()
        
        if all_accuracies:
            mean_accuracy = sum(all_accuracies) / len(all_accuracies)
            
            # Bootstrap CI for mean accuracy
            ci_result = validator.bootstrap_confidence_interval(
                all_accuracies,
                lambda x: sum(x) / len(x),
                name="mean_accuracy"
            )
            
            return {
                "mean_accuracy": round(mean_accuracy, 4),
                "std_accuracy": round(
                    math.sqrt(sum((a - mean_accuracy) ** 2 for a in all_accuracies) / len(all_accuracies)),
                    4
                ),
                "ci_lower": round(ci_result.confidence_interval[0], 4),
                "ci_upper": round(ci_result.confidence_interval[1], 4),
                "n_folds": len(fold_results),
                "fold_results": fold_results,
                "temporal_stability": self._assess_stability(all_accuracies),
            }
        
        return {
            "mean_accuracy": 0,
            "n_folds": 0,
            "error": "No valid splits"
        }
    
    def _assess_stability(self, accuracies: List[float]) -> str:
        """Assess temporal stability of accuracy across folds."""
        if len(accuracies) < 2:
            return "insufficient_data"
        
        # Check if accuracy is declining over time
        n = len(accuracies)
        mid = n // 2
        early_mean = sum(accuracies[:mid]) / mid
        late_mean = sum(accuracies[mid:]) / (n - mid)
        
        diff = late_mean - early_mean
        
        if abs(diff) < 0.05:
            return "stable"
        elif diff < -0.1:
            return "declining"
        elif diff > 0.1:
            return "improving"
        else:
            return "slight_" + ("decline" if diff < 0 else "improvement")


def calculate_backtest_statistics(
    predictions: List[Dict],
    horizons: List[int] = [7, 14, 30, 60, 90],
) -> Dict[str, Any]:
    """
    Calculate comprehensive backtest statistics.
    
    Args:
        predictions: List of prediction dicts with status, horizon_days, confidence
        horizons: Horizons to analyze
        
    Returns:
        Complete statistical analysis
    """
    validator = StatisticalValidator()
    results = {
        "overall": {},
        "by_horizon": {},
        "statistical_tests": [],
        "warnings": [],
    }
    
    # Overall accuracy
    correct = sum(1 for p in predictions if p.get("status") == "correct")
    total = len(predictions)
    
    accuracy_result = validator.accuracy_with_ci(correct, total, "overall_accuracy")
    results["overall"] = accuracy_result.to_dict()
    
    if accuracy_result.warning:
        results["warnings"].append(accuracy_result.warning)
    
    # By horizon
    for horizon in horizons:
        horizon_preds = [p for p in predictions if p.get("horizon_days") == horizon]
        if horizon_preds:
            correct_h = sum(1 for p in horizon_preds if p.get("status") == "correct")
            result = validator.accuracy_with_ci(
                correct_h,
                len(horizon_preds),
                f"accuracy_{horizon}d"
            )
            results["by_horizon"][horizon] = result.to_dict()
            
            if not result.is_significant:
                results["warnings"].append(
                    f"{horizon}d horizon: accuracy not statistically different from random (p={result.p_value:.3f})"
                )
    
    # Flag weak results
    if total < 30:
        results["warnings"].append(
            f"Total sample size ({total}) below recommended minimum (30)"
        )
    
    return results


if __name__ == "__main__":
    # Test the statistical validation
    print("Testing Statistical Validation Utilities")
    print("=" * 60)
    
    # Test correlation
    validator = StatisticalValidator()
    x = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10] * 3  # n=30
    y = [1.1, 2.2, 2.9, 4.1, 5.0, 6.2, 6.8, 8.1, 9.0, 10.2] * 3
    
    result = validator.pearson_correlation_test(x, y, "test_correlation")
    print(f"\nCorrelation Test:")
    print(f"  r = {result.value:.4f}")
    print(f"  p = {result.p_value:.4f}")
    print(f"  95% CI: [{result.confidence_interval[0]:.4f}, {result.confidence_interval[1]:.4f}]")
    print(f"  Significant: {result.is_significant}")
    
    # Test accuracy CI
    accuracy = validator.accuracy_with_ci(75, 100, "test_accuracy")
    print(f"\nAccuracy Test (75/100):")
    print(f"  Accuracy = {accuracy.value:.4f}")
    print(f"  95% CI: [{accuracy.confidence_interval[0]:.4f}, {accuracy.confidence_interval[1]:.4f}]")
    print(f"  p = {accuracy.p_value:.4f} (vs random)")
    
    # Test Brier score
    brier = BrierScoreTracker()
    for i in range(50):
        prob = 0.7 + 0.1 * (i % 3 - 1)  # 0.6, 0.7, 0.8
        outcome = 1 if i < 35 else 0  # 70% correct
        brier.add_prediction(f"entity_{i}", prob, outcome, f"2024-01-{i+1:02d}", 60)
    
    print(f"\nBrier Score: {brier.get_brier_score():.4f}")
    print(f"Calibration curve:")
    for bin_data in brier.get_calibration_curve(5):
        print(f"  Bin {bin_data['bin']}: predicted={bin_data['mean_predicted']:.2f}, "
              f"observed={bin_data['observed_frequency']:.2f}")
    
    print("\n" + "=" * 60)
    print("Statistical validation utilities ready for use.")
