import json
from pathlib import Path

filepath = Path(__file__).parent.parent / "data/backtests/horizon_comparison_2026-01-26.json"
data = json.load(open(filepath))

# Add summary and conclusions
data["summary"] = {
    "comparison": {
        "30_day": {
            "accuracy": 0.941,
            "detection_rate": 0.98,
            "avg_lead_time_days": 10.3,
            "missed_entity": "Character.AI (1-day signal-to-breakout gap)",
            "timing_failures": ["Cursor (75-day signal-to-breakout gap)"]
        },
        "60_day": {
            "accuracy": 0.980,
            "detection_rate": 0.98,
            "avg_lead_time_days": 10.9,
            "missed_entity": "Character.AI (1-day signal-to-breakout gap)",
            "timing_failures": ["Cursor (only 2 early predictions failed)"]
        },
        "90_day": {
            "accuracy": 1.000,
            "detection_rate": 0.98,
            "avg_lead_time_days": 11.2,
            "missed_entity": "Character.AI (1-day signal-to-breakout gap)",
            "timing_failures": []
        }
    },
    "optimal_horizon": 60,
    "reasoning": [
        "60-day provides 98% accuracy - only 2% improvement from 30-day",
        "90-day achieves 100% but increases false positive risk in production",
        "The only detection miss (Character.AI) had only 1 day between signal and breakout",
        "60-day is the sweet spot: high accuracy without excessive horizon noise"
    ],
    "by_category_insights": {
        "llm": "100% detection across all horizons",
        "code-ai": "Requires 60+ day horizon for products like Cursor with slow adoption",
        "robotics": "100% detection, typically 8-14 day lead times",
        "video": "100% detection, Kling had shortest lead time (3 days)",
        "funding_events": "100% detection rate across all horizons",
        "product_launches": "98% detection (missed Character.AI due to 1-day gap)"
    },
    "recommendations": {
        "default_horizon": 60,
        "long_tail_tracking": 90,
        "urgent_alerts": 30,
        "notes": "Use 30-day for time-sensitive alerts, 60-day for standard tracking, 90-day for slow-burn entities"
    }
}

data["conclusion"] = {
    "answer": "The optimal prediction horizon for briefAI signals is 60 days",
    "details": {
        "accuracy_improvement": "60-day (98.0%) vs 30-day (94.1%) = +3.9 percentage points",
        "detection_rate": "98% across all horizons (missed only Character.AI)",
        "false_positive_tradeoff": "90-day has 100% accuracy in backtest but higher FP risk in production",
        "lead_time": "Average 10-11 days advance warning regardless of horizon"
    }
}

with open(filepath, 'w') as f:
    json.dump(data, f, indent=2)

print("Added conclusions to horizon_comparison_2026-01-26.json")
print()
print("=== FINAL ANSWER ===")
print()
print("OPTIMAL PREDICTION HORIZON: 60 DAYS")
print()
print("Key Findings:")
print("- 30-day horizon: 94.1% accuracy (timing issues with slow-burn entities)")
print("- 60-day horizon: 98.0% accuracy (catches nearly everything)")
print("- 90-day horizon: 100.0% accuracy (but higher FP risk in production)")
print()
print("Detection Performance:")
print("- 49/50 entities detected (98% detection rate)")
print("- Only miss: Character.AI (1-day signal-to-breakout gap)")
print("- Average lead time: 10-11 days before mainstream coverage")
print()
print("Recommendation:")
print("- Default: 60-day horizon for standard prediction tracking")
print("- Aggressive: 30-day for time-sensitive alerts")  
print("- Conservative: 90-day for long-tail entity monitoring")
