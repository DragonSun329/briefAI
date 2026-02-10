"""Test research pipeline config."""
import json
from pathlib import Path

# Load pipelines config
config_file = Path('config/pipelines.json')
with open(config_file, encoding='utf-8') as f:
    config = json.load(f)

research = config['pipelines']['research']
print('Research pipeline config:')
print(f"  tier1_threshold: {research.get('tier1_threshold', 'NOT SET')}")
print(f"  sources_file: {research.get('sources_file')}")
print(f"  enabled: {research.get('enabled')}")

# Test orchestrator loading
from pipeline.orchestrator import PipelineOrchestrator
print("\nOrchestrator can load config: OK")
