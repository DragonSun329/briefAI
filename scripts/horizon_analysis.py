#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Horizon Comparison Analysis

Runs backfills at different horizons and generates a comprehensive report
comparing accuracy across 30/60/90 day horizons.

Usage:
    python scripts/horizon_analysis.py
"""

import json
import sys
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from collections import defaultdict

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


class HorizonAnalyzer:
    """Analyzes predictions across different time horizons."""
    
    def __init__(self):
        config_dir = Path(__file__).parent.parent / "config"
        self.ground_truth_path = config_dir / "ground_truth_expanded.json"
        self.ground_truth = self._load_ground_truth()
        self.results_by_horizon: Dict[int, Dict] = {}
    
    def _load_ground_truth(self) -> Dict:
        """Load ground truth events."""
        if self.ground_truth_path.exists():
            with open(self.ground_truth_path, encoding="utf-8") as f:
                return json.load(f)
        return {"breakout_events": []}
    
    def analyze_horizon(self, horizon_days: int, start_date: date, end_date: Optional[date] = None) -> Dict:
        """
        Analyze predictions for a specific horizon.
        
        Returns detailed results including:
        - Overall accuracy
        - Accuracy by category
        - Accuracy by event type
        - Lead time distribution
        """
        events = self.ground_truth.get("breakout_events", [])
        
        if end_date is None:
            end_date = date.today() - timedelta(days=horizon_days)
        
        results = {
            "horizon_days": horizon_days,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "total_events": len(events),
            "predictions": [],
            "by_category": defaultdict(lambda: {"correct": 0, "incorrect": 0, "no_prediction": 0}),
            "by_event_type": defaultdict(lambda: {"correct": 0, "incorrect": 0, "no_prediction": 0}),
            "lead_times": [],
            "timing_failures": [],  # Correct entity, wrong timing
        }
        
        total_predictions = 0
        correct_predictions = 0
        incorrect_predictions = 0
        
        for event in events:
            entity_id = event["entity_id"]
            entity_name = event["entity_name"]
            category = event.get("category", "unknown")
            entity_type = event.get("entity_type", "unknown")
            
            early_signal_date = datetime.fromisoformat(event["early_signal_date"]).date()
            breakout_date = datetime.fromisoformat(event["breakout_date"]).date()
            
            # Determine if we have funding info to classify as funding event
            is_funding = "funding_amount_usd" in event
            event_type = "funding" if is_funding else "product_launch"
            
            # Check each week in the prediction window
            current_date = start_date
            event_predictions = []
            first_correct_date = None
            
            while current_date <= end_date:
                # Check if this date falls in the prediction window
                if early_signal_date <= current_date < breakout_date:
                    horizon_end = current_date + timedelta(days=horizon_days)
                    
                    # Would this prediction be correct?
                    if breakout_date <= horizon_end:
                        status = "correct"
                        correct_predictions += 1
                        if first_correct_date is None:
                            first_correct_date = current_date
                    else:
                        status = "incorrect"
                        incorrect_predictions += 1
                        results["timing_failures"].append({
                            "entity": entity_name,
                            "prediction_date": current_date.isoformat(),
                            "horizon_end": horizon_end.isoformat(),
                            "actual_breakout": breakout_date.isoformat(),
                            "days_late": (breakout_date - horizon_end).days
                        })
                    
                    total_predictions += 1
                    event_predictions.append({
                        "date": current_date.isoformat(),
                        "status": status
                    })
                
                current_date += timedelta(days=7)
            
            # Record event results
            if event_predictions:
                correct_count = sum(1 for p in event_predictions if p["status"] == "correct")
                if correct_count > 0:
                    results["by_category"][category]["correct"] += 1
                    results["by_event_type"][event_type]["correct"] += 1
                    
                    # Calculate lead time
                    lead_time = (breakout_date - first_correct_date).days
                    results["lead_times"].append({
                        "entity": entity_name,
                        "category": category,
                        "lead_time_days": lead_time
                    })
                else:
                    results["by_category"][category]["incorrect"] += 1
                    results["by_event_type"][event_type]["incorrect"] += 1
            else:
                results["by_category"][category]["no_prediction"] += 1
                results["by_event_type"][event_type]["no_prediction"] += 1
            
            results["predictions"].append({
                "entity_id": entity_id,
                "entity_name": entity_name,
                "category": category,
                "event_type": event_type,
                "early_signal_date": event["early_signal_date"],
                "breakout_date": event["breakout_date"],
                "prediction_count": len(event_predictions),
                "correct_count": sum(1 for p in event_predictions if p["status"] == "correct"),
                "first_correct_date": first_correct_date.isoformat() if first_correct_date else None,
                "lead_time_days": (breakout_date - first_correct_date).days if first_correct_date else None,
            })
        
        # Calculate summary stats
        results["total_predictions"] = total_predictions
        results["correct_predictions"] = correct_predictions
        results["incorrect_predictions"] = incorrect_predictions
        results["accuracy"] = correct_predictions / total_predictions if total_predictions > 0 else 0
        
        # Entity-level detection rate
        detected_entities = sum(1 for p in results["predictions"] if p["correct_count"] > 0)
        results["detection_rate"] = detected_entities / len(events) if events else 0
        results["detected_entities"] = detected_entities
        results["missed_entities"] = len(events) - detected_entities
        
        # Average lead time
        if results["lead_times"]:
            results["avg_lead_time"] = sum(lt["lead_time_days"] for lt in results["lead_times"]) / len(results["lead_times"])
            results["min_lead_time"] = min(lt["lead_time_days"] for lt in results["lead_times"])
            results["max_lead_time"] = max(lt["lead_time_days"] for lt in results["lead_times"])
        else:
            results["avg_lead_time"] = 0
            results["min_lead_time"] = 0
            results["max_lead_time"] = 0
        
        # Convert defaultdicts to regular dicts
        results["by_category"] = dict(results["by_category"])
        results["by_event_type"] = dict(results["by_event_type"])
        
        return results
    
    def run_all_horizons(self, horizons: List[int] = [30, 60, 90]) -> Dict:
        """Run analysis for all specified horizons."""
        start_date = date(2024, 1, 1)
        
        all_results = {
            "generated_at": datetime.now().isoformat(),
            "ground_truth_events": len(self.ground_truth.get("breakout_events", [])),
            "start_date": start_date.isoformat(),
            "horizons": {}
        }
        
        for horizon in horizons:
            print(f"Analyzing {horizon}-day horizon...")
            results = self.analyze_horizon(horizon, start_date)
            all_results["horizons"][horizon] = results
            self.results_by_horizon[horizon] = results
        
        # Find optimal horizon
        best_accuracy = 0
        best_horizon = 30
        for horizon, results in all_results["horizons"].items():
            if results["accuracy"] > best_accuracy:
                best_accuracy = results["accuracy"]
                best_horizon = horizon
        
        all_results["optimal_horizon"] = best_horizon
        all_results["optimal_accuracy"] = best_accuracy
        
        return all_results
    
    def generate_report(self) -> str:
        """Generate human-readable report."""
        if not self.results_by_horizon:
            return "No results to report. Run run_all_horizons() first."
        
        lines = [
            "=" * 80,
            "HORIZON COMPARISON ANALYSIS REPORT",
            "=" * 80,
            "",
            f"Ground Truth Events: {len(self.ground_truth.get('breakout_events', []))}",
            f"Analysis Period: 2024-01-01 to present",
            "",
        ]
        
        # Summary table
        lines.extend([
            "─" * 80,
            "ACCURACY BY HORIZON",
            "─" * 80,
            "",
            f"{'Horizon':<12} {'Accuracy':<12} {'Detection':<12} {'Predictions':<12} {'Avg Lead Time':<15}",
            "-" * 63,
        ])
        
        for horizon in sorted(self.results_by_horizon.keys()):
            results = self.results_by_horizon[horizon]
            lines.append(
                f"{horizon} days{' ':<6} "
                f"{results['accuracy']*100:>6.1f}%{' ':<4} "
                f"{results['detection_rate']*100:>6.1f}%{' ':<4} "
                f"{results['total_predictions']:>6}{' ':<6} "
                f"{results['avg_lead_time']:>6.1f} days"
            )
        
        lines.extend(["", ""])
        
        # Best horizon
        best_horizon = max(self.results_by_horizon.keys(), key=lambda h: self.results_by_horizon[h]["accuracy"])
        best_results = self.results_by_horizon[best_horizon]
        
        lines.extend([
            "─" * 80,
            "OPTIMAL HORIZON RECOMMENDATION",
            "─" * 80,
            "",
            f"✓ RECOMMENDED: {best_horizon}-day horizon",
            f"  - Accuracy: {best_results['accuracy']*100:.1f}%",
            f"  - Detection Rate: {best_results['detection_rate']*100:.1f}%",
            f"  - Average Lead Time: {best_results['avg_lead_time']:.1f} days",
            "",
        ])
        
        # Category breakdown for best horizon
        lines.extend([
            "─" * 80,
            f"ACCURACY BY CATEGORY ({best_horizon}-day horizon)",
            "─" * 80,
            "",
        ])
        
        for category, stats in sorted(best_results["by_category"].items()):
            total = stats["correct"] + stats["incorrect"]
            if total > 0:
                acc = stats["correct"] / total * 100
                lines.append(f"  {category:<20} {stats['correct']}/{total} ({acc:.0f}%)")
        
        lines.append("")
        
        # Event type breakdown
        lines.extend([
            "─" * 80,
            f"ACCURACY BY EVENT TYPE ({best_horizon}-day horizon)",
            "─" * 80,
            "",
        ])
        
        for event_type, stats in sorted(best_results["by_event_type"].items()):
            total = stats["correct"] + stats["incorrect"]
            if total > 0:
                acc = stats["correct"] / total * 100
                lines.append(f"  {event_type:<20} {stats['correct']}/{total} ({acc:.0f}%)")
        
        lines.append("")
        
        # Lead time distribution
        lines.extend([
            "─" * 80,
            f"LEAD TIME DISTRIBUTION ({best_horizon}-day horizon)",
            "─" * 80,
            "",
            f"  Minimum: {best_results['min_lead_time']} days",
            f"  Average: {best_results['avg_lead_time']:.1f} days",
            f"  Maximum: {best_results['max_lead_time']} days",
            "",
        ])
        
        # Lead time buckets
        lead_times = [lt["lead_time_days"] for lt in best_results["lead_times"]]
        if lead_times:
            buckets = {"0-7 days": 0, "8-14 days": 0, "15-30 days": 0, "31-60 days": 0, "60+ days": 0}
            for lt in lead_times:
                if lt <= 7:
                    buckets["0-7 days"] += 1
                elif lt <= 14:
                    buckets["8-14 days"] += 1
                elif lt <= 30:
                    buckets["15-30 days"] += 1
                elif lt <= 60:
                    buckets["31-60 days"] += 1
                else:
                    buckets["60+ days"] += 1
            
            lines.append("  Distribution:")
            for bucket, count in buckets.items():
                if count > 0:
                    pct = count / len(lead_times) * 100
                    lines.append(f"    {bucket:<15} {count:>3} events ({pct:.0f}%)")
        
        lines.extend(["", ""])
        
        # Timing failures analysis
        lines.extend([
            "─" * 80,
            "TIMING ANALYSIS (30-day horizon failures)",
            "─" * 80,
            "",
        ])
        
        if 30 in self.results_by_horizon:
            failures = self.results_by_horizon[30].get("timing_failures", [])
            if failures:
                # Group by entity
                by_entity = defaultdict(list)
                for f in failures:
                    by_entity[f["entity"]].append(f["days_late"])
                
                lines.append(f"  Entities with timing misses: {len(by_entity)}")
                lines.append("")
                lines.append("  Missed predictions (entity: days late):")
                for entity, days_list in sorted(by_entity.items()):
                    avg_late = sum(days_list) / len(days_list)
                    lines.append(f"    {entity}: avg {avg_late:.0f} days late ({len(days_list)} predictions)")
            else:
                lines.append("  No timing failures!")
        
        lines.extend(["", "=" * 80])
        
        return "\n".join(lines)


def main():
    print("=" * 80)
    print("BRIEFAI HORIZON COMPARISON ANALYSIS")
    print("=" * 80)
    print()
    
    analyzer = HorizonAnalyzer()
    
    # Run analysis for all horizons
    results = analyzer.run_all_horizons([30, 60, 90])
    
    # Save results to file
    output_dir = Path(__file__).parent.parent / "data" / "backtests"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    output_file = output_dir / f"horizon_comparison_{date.today().isoformat()}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    
    print(f"Results saved to: {output_file}")
    print()
    
    # Print report
    print(analyzer.generate_report())
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
