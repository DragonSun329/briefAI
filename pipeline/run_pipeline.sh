#!/bin/bash
# Pipeline Runner - Generate weekly AI briefing report
cd "$(dirname "$0")"
python3 run_pipeline.py --top-n 12
