#!/usr/bin/env python3
"""
Rerun post-scraper evaluation pipeline (Steps 2-6).
Use after adding new scraper data mid-day.
"""
import subprocess
import sys
import os
from datetime import datetime
from pathlib import Path

os.chdir(Path(__file__).parent.parent)

steps = [
    ("Step 2: Rebuild signal profiles", ["python", "scripts/rebuild_profiles_v2.py"]),
    ("Step 3a: Accumulate predictions", ["python", "scripts/accumulate_predictions.py"]),
    ("Step 3b: Realtime validation", ["python", "scripts/realtime_validator.py", "--entities", "NVDA,META,MSFT,GOOGL,AMD"]),
    ("Step 4: Forecast generation", ["python", "scripts/run_forecast_phase.py", "--experiment", "v2_2_forward_test"]),
    ("Step 5: Verify ledger", ["python", "scripts/verify_ledger_integrity.py", "--experiment", "v2_2_forward_test"]),
]

print("=" * 60)
print(f"RERUNNING EVALUATION PIPELINE - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print("=" * 60)

for name, cmd in steps:
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")
    result = subprocess.run(cmd, capture_output=False, text=False)
    if result.returncode != 0:
        print(f"  [WARN] {name} exited with code {result.returncode} (continuing)")
    else:
        print(f"  [OK] {name}")

# Step 6: Generate brief (async)
print(f"\n{'='*60}")
print(f"  Step 6: Generate daily brief")
print(f"{'='*60}")
brief_code = '''
import asyncio
from modules.daily_brief import DailyBriefGenerator

async def main():
    gen = DailyBriefGenerator()
    report_path = await gen.generate()
    print(f"Generated: {report_path}")

asyncio.run(main())
'''
result = subprocess.run(["python", "-c", brief_code], capture_output=False, text=False)
if result.returncode != 0:
    print(f"  [WARN] Brief generation exited with code {result.returncode}")
else:
    print(f"  [OK] Brief generated")

print(f"\n{'='*60}")
print(f"EVALUATION PIPELINE COMPLETE")
print(f"{'='*60}")
