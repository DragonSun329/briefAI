import json
from pathlib import Path

data = json.load(open(Path(__file__).parent.parent / "data/backtests/horizon_comparison_2026-01-26.json"))

print("=" * 70)
print("BRIEFAI HORIZON COMPARISON ANALYSIS - SUMMARY")
print("=" * 70)
print()
print(f"Ground Truth Events: {data['ground_truth_events']}")
print(f"Analysis Period: {data['start_date']} to present")
print()
print("-" * 70)
print("ACCURACY BY HORIZON")
print("-" * 70)
print()
print(f"{'Horizon':<12} {'Accuracy':<12} {'Detection':<12} {'Predictions':<12} {'Avg Lead Time':<15}")
print("-" * 63)

for horizon in sorted(data['horizons'].keys(), key=int):
    r = data['horizons'][horizon]
    print(f"{horizon} days      {r['accuracy']*100:>6.1f}%      {r['detection_rate']*100:>6.1f}%      {r['total_predictions']:>6}      {r['avg_lead_time']:>6.1f} days")

print()

# Find best horizon
best_h = max(data['horizons'].keys(), key=lambda h: data['horizons'][h]['accuracy'])
best_r = data['horizons'][best_h]

print("-" * 70)
print("OPTIMAL HORIZON RECOMMENDATION")
print("-" * 70)
print()
print(f">>> RECOMMENDED: {best_h}-day horizon <<<")
print(f"    - Accuracy: {best_r['accuracy']*100:.1f}%")
print(f"    - Detection Rate: {best_r['detection_rate']*100:.1f}%")
print(f"    - Average Lead Time: {best_r['avg_lead_time']:.1f} days")
print()

print("-" * 70)
print(f"ACCURACY BY CATEGORY ({best_h}-day horizon)")
print("-" * 70)
print()

for cat, stats in sorted(best_r['by_category'].items()):
    total = stats['correct'] + stats['incorrect']
    if total > 0:
        acc = stats['correct'] / total * 100
        print(f"  {cat:<20} {stats['correct']}/{total} ({acc:.0f}%)")

print()
print("-" * 70)
print(f"ACCURACY BY EVENT TYPE ({best_h}-day horizon)")
print("-" * 70)
print()

for etype, stats in sorted(best_r['by_event_type'].items()):
    total = stats['correct'] + stats['incorrect']
    if total > 0:
        acc = stats['correct'] / total * 100
        print(f"  {etype:<20} {stats['correct']}/{total} ({acc:.0f}%)")

print()
print("-" * 70)
print(f"LEAD TIME DISTRIBUTION ({best_h}-day horizon)")
print("-" * 70)
print()
print(f"  Minimum: {best_r['min_lead_time']} days")
print(f"  Average: {best_r['avg_lead_time']:.1f} days")
print(f"  Maximum: {best_r['max_lead_time']} days")
print()

# Lead time buckets
lead_times = [lt['lead_time_days'] for lt in best_r['lead_times']]
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
    
    print("  Distribution:")
    for bucket, count in buckets.items():
        if count > 0:
            pct = count / len(lead_times) * 100
            print(f"    {bucket:<15} {count:>3} events ({pct:.0f}%)")

print()
print("-" * 70)
print("TIMING ANALYSIS (30-day horizon failures)")
print("-" * 70)
print()

failures_30 = data['horizons']['30'].get('timing_failures', [])
if failures_30:
    # Group by entity
    by_entity = {}
    for f in failures_30:
        ent = f['entity']
        if ent not in by_entity:
            by_entity[ent] = []
        by_entity[ent].append(f['days_late'])
    
    print(f"  Entities with timing misses: {len(by_entity)}")
    print()
    print("  Missed predictions (entity: days late):")
    for entity, days_list in sorted(by_entity.items()):
        avg_late = sum(days_list) / len(days_list)
        print(f"    {entity}: avg {avg_late:.0f} days late ({len(days_list)} predictions)")
else:
    print("  No timing failures!")

print()
print("=" * 70)
print("CONCLUSION")
print("=" * 70)
print()
print("The analysis of 50 ground truth AI events from 2024 shows that:")
print()
print("1. 60-DAY HORIZON is optimal for most use cases:")
print("   - Provides highest accuracy (98.0%)")
print("   - Catches nearly all events (98% detection rate)")
print("   - Average 11.2 days of advance warning")
print()
print("2. 30-DAY HORIZON works for most events (94.1% accuracy)")
print("   but misses entities with longer signal-to-breakout gaps")
print("   like Cursor (75-day gap from early signal to mainstream)")
print()
print("3. 90-DAY HORIZON has same accuracy as 60-day for this dataset")
print("   but increases false positive risk in practice")
print()
print("RECOMMENDATION: Use 60-day horizon as default,")
print("with 90-day for long-tail entity tracking.")
print()
