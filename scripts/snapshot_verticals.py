#!/usr/bin/env python
"""
Daily Vertical Snapshot Script

Run this daily (via cron) to:
1. Compute current vertical profiles
2. Save snapshot to history database
3. Generate predictions from divergence signals
4. Log alerts for tracking

Usage:
    python scripts/snapshot_verticals.py
    python scripts/snapshot_verticals.py --date 2026-01-28
"""

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.vertical_scorer import get_vertical_scorer
from utils.vertical_history import get_vertical_history


def main():
    parser = argparse.ArgumentParser(description="Take daily vertical snapshot")
    parser.add_argument("--date", type=str, help="Snapshot date (YYYY-MM-DD), defaults to today")
    parser.add_argument("--dry-run", action="store_true", help="Don't save, just show what would be saved")
    args = parser.parse_args()
    
    # Parse date
    if args.date:
        snapshot_date = date.fromisoformat(args.date)
    else:
        snapshot_date = date.today()
    
    print(f"[{datetime.now().isoformat()}] Starting vertical snapshot for {snapshot_date}")
    
    # Get scorer and history
    scorer = get_vertical_scorer()
    history = get_vertical_history()
    
    # Compute profiles
    print("Computing vertical profiles...")
    result = scorer.compute_all_profiles()
    profiles = result.get("verticals", [])
    
    print(f"  Computed {len(profiles)} vertical profiles")
    
    if args.dry_run:
        print("\n[DRY RUN] Would save these profiles:")
        for p in profiles[:5]:
            print(f"  {p['name']}: TMS={p['tech_momentum_score']:.1f}, Hype={p['hype_score']:.1f}")
        if len(profiles) > 5:
            print(f"  ... and {len(profiles) - 5} more")
        return
    
    # Save snapshot
    print("Saving snapshot...")
    saved = history.save_snapshot(profiles, snapshot_date)
    print(f"  Saved {saved} snapshots")
    
    # Generate predictions from divergence signals
    print("Generating predictions from divergences...")
    predictions_made = 0
    
    for p in profiles:
        divergence = p.get("divergence_signal", {})
        div_type = divergence.get("type")
        
        if div_type == "alpha_opportunity":
            # Predict tech will maintain/grow, hype will catch up
            history.save_prediction(
                vertical_id=p["vertical_id"],
                prediction_type="alpha_opportunity",
                predicted_outcome="hype_increase_30d",
                confidence=0.6,
                rationale=f"Tech score ({p['tech_momentum_score']:.0f}) exceeds hype ({p['hype_score']:.0f}) by {divergence.get('magnitude', 0):.0f} points"
            )
            predictions_made += 1
            
        elif div_type == "bubble_warning":
            # Predict hype will decline or tech needs to catch up
            history.save_prediction(
                vertical_id=p["vertical_id"],
                prediction_type="bubble_warning",
                predicted_outcome="hype_decrease_30d",
                confidence=0.5,
                rationale=f"Hype ({p['hype_score']:.0f}) exceeds tech ({p['tech_momentum_score']:.0f}) by {divergence.get('magnitude', 0):.0f} points"
            )
            predictions_made += 1
    
    print(f"  Made {predictions_made} predictions")
    
    # Save alerts
    print("Saving alerts...")
    alerts_saved = 0
    
    for p in profiles:
        tech = p.get("tech_momentum_score", 50)
        hype = p.get("hype_score", 50)
        investment = p.get("investment_score", 50)
        
        # Alpha opportunity alert
        if tech > 70 and hype < 40:
            history.save_alert(
                vertical_id=p["vertical_id"],
                alert_type="alpha_opportunity",
                severity="medium",
                message=f"Undervalued: strong tech ({tech:.0f}), low hype ({hype:.0f})",
                tech_score=tech,
                hype_score=hype,
                investment_score=investment,
            )
            alerts_saved += 1
        
        # Bubble warning alert
        if tech < 30 and hype > 70:
            history.save_alert(
                vertical_id=p["vertical_id"],
                alert_type="bubble_warning",
                severity="high",
                message=f"Potential bubble: weak tech ({tech:.0f}), high hype ({hype:.0f})",
                tech_score=tech,
                hype_score=hype,
                investment_score=investment,
            )
            alerts_saved += 1
    
    print(f"  Saved {alerts_saved} alerts")
    
    # Print summary
    print(f"\n=== Snapshot Summary for {snapshot_date} ===")
    
    # Top movers (if we have history)
    snapshot_counts = history.get_snapshot_count()
    if any(c > 1 for c in snapshot_counts.values()):
        print("\n7-Day Momentum (significant changes):")
        momentum = history.get_all_momentum(days=7, min_change=5.0)
        for m in momentum[:10]:
            arrow = "↑" if m["trend"] == "up" else "↓" if m["trend"] == "down" else "→"
            print(f"  {m['vertical_id']}.{m['metric']}: {arrow} {m['change']:+.1f} ({m['percent_change']:+.1f}%)")
    
    # Current divergences
    print("\nCurrent Divergence Signals:")
    divergent = [p for p in profiles if p.get("divergence_signal", {}).get("type") != "balanced"]
    for p in sorted(divergent, key=lambda x: x.get("divergence_signal", {}).get("magnitude", 0), reverse=True)[:5]:
        div = p["divergence_signal"]
        marker = "[ALPHA]" if div["type"] == "alpha_opportunity" else "[WARN]"
        print(f"  {marker} {p['name']}: {div['type']} (magnitude: {div['magnitude']:.1f})")
    
    print(f"\nSnapshot complete. Total snapshots in DB: {sum(snapshot_counts.values())}")


if __name__ == "__main__":
    main()
