"""
Quick test script for the Trend Radar pipeline.
Tests entity aggregation, trend signal detection, and multi-signal validation.
"""

from utils.trend_aggregator import TrendAggregator
from utils.context_retriever import ContextRetriever
from utils.entity_matcher import EntityMatcher
from utils.snapshot_builder import SnapshotBuilder
from utils.trend_signal_enricher import TrendSignalEnricher, TrendSignal
from datetime import datetime

def main():
    print("=" * 60)
    print("Testing Trend Radar Pipeline")
    print("=" * 60)

    # Initialize components
    context = ContextRetriever(cache_dir="./data/cache/article_contexts")
    aggregator = TrendAggregator(
        context=context,
        config_path="./config/trend_detection.json"
    )

    print("\n1. Testing Configuration Load...")
    print(f"   Baseline weeks: {aggregator.config.get('baseline_weeks')}")
    print(f"   Min confidence: {aggregator.config.get('min_confidence')}")
    print(f"   Thresholds: {aggregator.config.get('thresholds')}")

    print("\n2. Checking Available Reports...")
    reports = context.list_available_reports()
    print(f"   Found {len(reports)} cached reports")

    if not reports:
        print("   [!] No cached reports found. Generate a weekly briefing first:")
        print("      python main.py --defaults --finalize --weekly")
        return

    # Show available reports
    for report in reports[:5]:
        print(f"   - {report['date']}: {report['article_count']} articles")

    # Calculate current week ID from latest report
    if reports:
        latest_date = reports[0]['date']
        date_obj = datetime.strptime(latest_date, "%Y-%m-%d")
        iso_year, iso_week, _ = date_obj.isocalendar()
        current_week = f"{iso_year}-W{iso_week:02d}"

        print(f"\n3. Testing Entity Aggregation for {current_week}...")
        mentions = aggregator.aggregate_week(current_week)
        print(f"   Found {len(mentions)} unique entities")

        if mentions:
            print("\n   Top 10 entities by mention count:")
            sorted_mentions = sorted(mentions, key=lambda m: m.mention_count, reverse=True)
            for i, mention in enumerate(sorted_mentions[:10], 1):
                print(f"   {i:2d}. {mention.entity_name:20s} ({mention.entity_type:8s}): "
                      f"{mention.mention_count} mentions, avg_score={mention.avg_score:.1f}, "
                      f"total_score={mention.total_score:.1f}")

        print(f"\n4. Testing Trend Signal Detection for {current_week}...")
        signals = aggregator.detect_trend_signals(current_week, baseline_weeks=4)
        print(f"   Detected {len(signals)} trend signals")

        if signals:
            # Group by signal type
            signal_groups = {}
            for signal in signals:
                if signal.signal_type not in signal_groups:
                    signal_groups[signal.signal_type] = []
                signal_groups[signal.signal_type].append(signal)

            for signal_type, group_signals in signal_groups.items():
                print(f"\n   {signal_type.upper()} ({len(group_signals)} signals):")
                sorted_signals = sorted(group_signals, key=lambda s: s.confidence, reverse=True)
                for signal in sorted_signals[:5]:
                    print(f"      - {signal.entity_name:20s}: confidence={signal.confidence:.0%}, "
                          f"mentions={signal.current_mentions} (baseline={signal.baseline_mentions:.1f}), "
                          f"velocity={signal.velocity_change:+.0%}")
        else:
            print("   [i] No signals detected. This could mean:")
            print("      - Not enough historical data (need 4+ weeks)")
            print("      - No entities exceeded the detection thresholds")
            print("      - Baseline activity is similar to current week")

        print(f"\n5. Testing Helper Methods...")
        baseline_weeks = aggregator._get_baseline_weeks(current_week, 4)
        print(f"   Baseline weeks for {current_week}: {baseline_weeks}")

        print(f"\n6. Testing Entity Matcher...")
        try:
            matcher = EntityMatcher()
            test_names = ["OpenAI", "deepseek-v3", "claude", "gpt-4", "Meta AI"]
            for name in test_names:
                result = matcher.resolve_entity(name, source="news")
                if result.primary_match:
                    print(f"   '{name}' → {result.primary_name} ({result.resolution_path}, conf={result.resolution_confidence:.1%})")
                else:
                    flags = ", ".join(result.ambiguity_flags) if result.ambiguity_flags else "no match"
                    print(f"   '{name}' → unresolved ({flags})")

            # Validate registry
            issues = matcher.validate_registry()
            domain_conflicts = issues.get("domain_conflicts", [])
            alias_collisions = issues.get("alias_collisions", [])
            if domain_conflicts:
                print(f"   [!] Domain conflicts: {len(domain_conflicts)}")
            if alias_collisions:
                print(f"   [!] Alias collisions: {len(alias_collisions)}")
            if not domain_conflicts and not alias_collisions:
                print("   [OK] Registry validation passed")
        except Exception as e:
            print(f"   [!] EntityMatcher error: {e}")

        print(f"\n7. Testing Snapshot Builder...")
        try:
            builder = SnapshotBuilder()
            available_snapshots = builder.list_snapshots()
            print(f"   Available snapshots: {len(available_snapshots)}")

            # Build or load snapshot
            if available_snapshots:
                snapshot = builder.load_latest_snapshot()
                print(f"   Loaded snapshot: {snapshot.get('snapshot_date', 'unknown')}")
            else:
                print("   Building new snapshot...")
                snapshot = builder.build_snapshot(save=True)
                print(f"   Built snapshot: {snapshot.get('snapshot_date', 'unknown')}")

            # Show data health
            health = snapshot.get("data_health", {})
            available = len(health.get("sources_available", []))
            missing = len(health.get("sources_missing", []))
            stale = len(health.get("sources_stale", []))
            print(f"   Data health: {available} available, {missing} missing, {stale} stale")

            if health.get("sources_available"):
                print(f"   Sources: {', '.join(health['sources_available'][:5])}...")
        except Exception as e:
            print(f"   [!] SnapshotBuilder error: {e}")

        print(f"\n8. Testing Signal Enricher (Multi-Signal Validation)...")
        if signals:
            try:
                # Convert aggregator signals to TrendSignal format
                trend_signals = []
                for sig in signals[:10]:  # Test top 10 signals
                    trend_signals.append(TrendSignal(
                        entity_id=sig.entity_name.lower().replace(" ", "_"),
                        entity_name=sig.entity_name,
                        signal_type=sig.signal_type,
                        current_week=current_week,
                        momentum_score=sig.confidence,
                        article_count=sig.current_mentions,
                        week_over_week_change=sig.velocity_change,
                        context="",
                    ))

                # Enrich with validation
                enricher = TrendSignalEnricher()
                validated = enricher.enrich(trend_signals)

                print(f"   Enriched {len(validated)} signals")
                print("\n   === Validated Trend Signals ===\n")

                # Show results
                for i, vsig in enumerate(validated[:5], 1):
                    print(f"   {i}. {vsig.canonical_name or vsig.entity_name} ({vsig.entity_type})")
                    print(f"      Signal: {vsig.signal_type} ({'+' if vsig.week_over_week_change > 0 else ''}{vsig.week_over_week_change:.0%})")
                    print(f"      Momentum: {vsig.momentum_score:.0%}")
                    print(f"      Validation: {vsig.validation_score:.0%} ({vsig.validation_status})")
                    print(f"      └─ Coverage: {len(vsig.corroborating_sources)} sources")
                    tier_strs = [f"Tier {t}: {c}" for t, c in vsig.tier_distribution.items() if c > 0]
                    if tier_strs:
                        print(f"      └─ Strength: {', '.join(tier_strs)}")
                    if vsig.corroborating_sources:
                        print(f"      └─ Sources: {', '.join(vsig.corroborating_sources)}")
                    if not vsig.is_validated and vsig.validation_fail_reasons:
                        fail_summary = ", ".join(f"{k}={v}" for k, v in list(vsig.validation_fail_reasons.items())[:3])
                        print(f"      └─ Fail: {fail_summary}")
                    print()

                # Summary stats
                validated_count = sum(1 for v in validated if v.is_validated)
                high_conf_count = sum(1 for v in validated if v.validation_status == "high_confidence")
                print(f"   Summary: {validated_count}/{len(validated)} validated, {high_conf_count} high confidence")

            except Exception as e:
                print(f"   [!] SignalEnricher error: {e}")
                import traceback
                traceback.print_exc()
        else:
            print("   [!] No signals to enrich (need trend signals from step 4)")

    print("\n" + "=" * 60)
    print("[OK] Pipeline Test Complete!")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Generate more weekly briefings to build historical data")
    print("2. Run: python main.py --defaults --finalize --weekly")
    print("3. Run scrapers to populate alternative_signals for validation:")
    print("   python scrapers/run_all_scrapers.py")
    print("4. View trends in Streamlit UI")
    print("=" * 60)

if __name__ == "__main__":
    main()