# -*- coding: utf-8 -*-
"""
Validate Signal Deduplication Logic

Tests the dedup system to ensure it's working correctly:
1. Same headline from different sources → should dedup
2. Similar headlines about same event → should dedup
3. Different events about same entity → should NOT dedup
4. Same entity, different days → should NOT dedup
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
import json

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.signal_dedup import SignalDeduplicator


def test_dedup_logic():
    """Test deduplication logic with controlled examples."""
    
    dedup = SignalDeduplicator()
    
    print("=" * 70)
    print("DEDUP VALIDATION TESTS")
    print("=" * 70)
    
    now = datetime.utcnow()
    yesterday = now - timedelta(days=1)
    last_week = now - timedelta(days=7)
    
    tests = [
        # Test 1: Exact duplicate (same headline, same entity, same day)
        {
            "name": "Exact duplicate - SHOULD DEDUP",
            "signals": [
                {"entity": "test_openai", "headline": "OpenAI launches GPT-5", "time": now, "source": "source_a"},
                {"entity": "test_openai", "headline": "OpenAI launches GPT-5", "time": now, "source": "source_b"},
            ],
            "expected_unique": 1,
        },
        
        # Test 2: Similar headlines (same event, different wording)
        {
            "name": "Similar headlines - SHOULD DEDUP",
            "signals": [
                {"entity": "test_anthropic", "headline": "Anthropic raises $2B in new funding round", "time": now, "source": "techcrunch"},
                {"entity": "test_anthropic", "headline": "Anthropic raises $2 billion in funding round", "time": now, "source": "reuters"},
            ],
            "expected_unique": 1,
        },
        
        # Test 3: Different events, same entity
        {
            "name": "Different events same entity - SHOULD NOT DEDUP",
            "signals": [
                {"entity": "test_nvidia", "headline": "NVIDIA announces new H200 chip", "time": now, "source": "source_a"},
                {"entity": "test_nvidia", "headline": "NVIDIA reports record Q4 earnings", "time": now, "source": "source_b"},
            ],
            "expected_unique": 2,
        },
        
        # Test 4: Same event, different days
        {
            "name": "Same headline different days - SHOULD NOT DEDUP",
            "signals": [
                {"entity": "test_google", "headline": "Google releases Gemini 2.0", "time": now, "source": "source_a"},
                {"entity": "test_google", "headline": "Google releases Gemini 2.0", "time": last_week, "source": "source_a"},
            ],
            "expected_unique": 2,
        },
        
        # Test 5: Different entities, similar headlines
        {
            "name": "Different entities - SHOULD NOT DEDUP",
            "signals": [
                {"entity": "test_meta", "headline": "Company announces AI partnership", "time": now, "source": "source_a"},
                {"entity": "test_microsoft", "headline": "Company announces AI partnership", "time": now, "source": "source_b"},
            ],
            "expected_unique": 2,
        },
        
        # Test 6: Slight variation in headline (typo, punctuation)
        {
            "name": "Minor headline variation - SHOULD DEDUP",
            "signals": [
                {"entity": "test_deepseek", "headline": "DeepSeek V4 expected to launch soon", "time": now, "source": "source_a"},
                {"entity": "test_deepseek", "headline": "DeepSeek V4 expected to launch soon!", "time": now, "source": "source_b"},
            ],
            "expected_unique": 1,
        },
    ]
    
    all_passed = True
    
    for test in tests:
        print(f"\n{'─' * 70}")
        print(f"TEST: {test['name']}")
        print(f"{'─' * 70}")
        
        unique_count = 0
        
        for i, sig in enumerate(test["signals"]):
            raw_data = {"headline": sig["headline"], "signal_type": "test"}
            
            is_dup, existing_id = dedup.is_duplicate(
                entity_id=sig["entity"],
                raw_data=raw_data,
                observed_at=sig["time"],
                source_id=sig["source"]
            )
            
            if not is_dup:
                unique_count += 1
                # Register this signal
                dedup.register_signal(
                    observation_id=f"test_{sig['entity']}_{i}",
                    entity_id=sig["entity"],
                    raw_data=raw_data,
                    observed_at=sig["time"],
                    source_id=sig["source"]
                )
                print(f"  Signal {i+1}: NEW (registered)")
            else:
                print(f"  Signal {i+1}: DUPLICATE of {existing_id[:20]}...")
        
        passed = unique_count == test["expected_unique"]
        status = "PASS" if passed else "FAIL"
        
        print(f"\n  Result: {unique_count} unique (expected {test['expected_unique']}) → {status}")
        
        if not passed:
            all_passed = False
    
    print("\n" + "=" * 70)
    print(f"OVERALL: {'ALL TESTS PASSED' if all_passed else 'SOME TESTS FAILED'}")
    print("=" * 70)
    
    return all_passed


def analyze_real_dedup():
    """Analyze actual dedup behavior on real data."""
    
    print("\n" + "=" * 70)
    print("REAL DATA DEDUP ANALYSIS")
    print("=" * 70)
    
    import sqlite3
    
    conn = sqlite3.connect("data/signals.db")
    c = conn.cursor()
    
    # Check fingerprint table
    c.execute("SELECT COUNT(*) FROM signal_fingerprints")
    fp_count = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM signal_fingerprints WHERE observation_count > 1")
    multi_obs = c.fetchone()[0]
    
    c.execute("SELECT SUM(observation_count) FROM signal_fingerprints")
    total_obs = c.fetchone()[0] or 0
    
    print(f"\nFingerprint Stats:")
    print(f"  Unique events (fingerprints): {fp_count}")
    print(f"  Events with multiple observations: {multi_obs}")
    print(f"  Total observations tracked: {total_obs}")
    print(f"  Dedup savings: {total_obs - fp_count} ({(total_obs - fp_count) / max(total_obs, 1) * 100:.1f}%)")
    
    # Show some examples of duplicated events
    print(f"\nSample duplicated events (observation_count > 1):")
    c.execute("""
        SELECT entity_id, event_type, event_date, observation_count, sources 
        FROM signal_fingerprints 
        WHERE observation_count > 1 
        ORDER BY observation_count DESC 
        LIMIT 10
    """)
    
    for row in c.fetchall():
        sources = json.loads(row[4]) if row[4] else []
        print(f"  {row[0][:30]:30} | {row[2]} | {row[3]} obs | sources: {sources[:3]}")
    
    # Check for potential false positives (different headlines same fingerprint)
    print(f"\nChecking fingerprint collisions...")
    c.execute("""
        SELECT fp.entity_id, fp.full_hash, fp.observation_count,
               (SELECT raw_data FROM signal_observations WHERE id = fp.first_observation_id) as first_data
        FROM signal_fingerprints fp
        WHERE fp.observation_count > 2
        LIMIT 5
    """)
    
    for row in c.fetchall():
        if row[3]:
            data = json.loads(row[3])
            headline = data.get("headline", "N/A")[:50]
            print(f"  {row[0][:25]:25} | {row[2]} obs | \"{headline}...\"")
    
    conn.close()


if __name__ == "__main__":
    test_dedup_logic()
    analyze_real_dedup()
