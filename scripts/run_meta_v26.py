"""Run Meta-Signal Engine v2.6 on current signals."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.meta_signal_engine import MetaSignalEngine
from utils.signal_tracker import SignalTracker
from datetime import datetime
import json

# Load today's signals
tracker = SignalTracker()

# Process with v2.6 engine
engine = MetaSignalEngine(use_embeddings=True)
result = engine.process_from_tracker(tracker, datetime.now().strftime('%Y-%m-%d'))

# Show results
print("=== META-SIGNAL ENGINE v2.6 RESULTS ===")
print(f"Version: {result['version']}")
print(f"Input signals: {result['stats']['input_signals']}")
print(f"Meta-signals found: {result['stats']['meta_signals_found']}")
print(f"Validated: {result['stats']['validated']}")
print(f"Weakly validated: {result['stats']['weakly_validated']}")
print(f"Review required: {result['stats']['review_required']}")
print(f"Name frozen: {result['stats']['name_frozen']}")
print()

for i, meta in enumerate(result['meta_signals'][:5]):
    print(f"--- META #{i+1} ---")
    print(f"Name: {meta['concept_name']}")
    print(f"Slug: {meta['concept_slug']}")
    print(f"Mechanism: {meta['mechanism']}")
    print(f"Confidence: {meta['concept_confidence']:.3f}")
    print(f"Independence: {meta['independence_score']:.3f}")
    print(f"Validation: {meta['validation_status']}")
    print(f"Name frozen: {meta['name_frozen']}")
    print(f"Persistence: {meta['persistence_days']} days")
    print(f"Signals: {len(meta['supporting_signals'])}")
    if meta.get('merge_reason'):
        print(f"Merge reason: {meta['merge_reason']}")
    if meta.get('hierarchy_reason'):
        print(f"Hierarchy reason: {meta['hierarchy_reason']}")
    if meta.get('confidence_breakdown'):
        bd = meta['confidence_breakdown']
        print(f"Confidence breakdown: base={bd['base']:.3f} div={bd['diversity']:.3f} indep={bd['independence']:.3f}")
    print()
