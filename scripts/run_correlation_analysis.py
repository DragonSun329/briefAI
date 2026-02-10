"""
Run Correlation Analysis

Daily automation script for correlation analysis:
1. Calculate entity correlation matrices
2. Update lead-lag relationships
3. Generate sector correlations
4. Detect regime changes and divergences
5. Generate early warning signals
"""

import sys
from pathlib import Path
from datetime import datetime
from typing import List, Optional

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from loguru import logger

from utils.correlation_analysis import (
    CorrelationAnalyzer,
    run_full_correlation_analysis,
    SECTOR_DEFINITIONS
)
from utils.rolling_correlations import (
    RollingCorrelationTracker,
    run_rolling_correlation_scan
)
from utils.signal_propagation import SignalPropagationEngine


def get_active_entities(limit: int = 50) -> List[str]:
    """Get most active entities from signals database."""
    from utils.signal_store import SignalStore
    
    store = SignalStore()
    
    try:
        # Get top profiles by composite score
        profiles = store.get_top_profiles(limit=limit)
        return [p.entity_id for p in profiles]
    except Exception as e:
        logger.warning(f"Could not get active entities: {e}")
        # Return default list
        return list(set([
            entity 
            for sector in SECTOR_DEFINITIONS.values() 
            for entity in sector["entities"]
        ]))[:limit]


def run_daily_correlation_analysis(
    entities: Optional[List[str]] = None,
    signal_types: Optional[List[str]] = None,
    scan_top_pairs: int = 20
):
    """
    Run complete daily correlation analysis.
    
    Args:
        entities: Entities to analyze (None = auto-select)
        signal_types: Signal types to use
        scan_top_pairs: Number of top entity pairs to scan for regime changes
    """
    logger.info("=" * 60)
    logger.info("Starting Daily Correlation Analysis")
    logger.info(f"Time: {datetime.utcnow().isoformat()}")
    logger.info("=" * 60)
    
    if signal_types is None:
        signal_types = ["composite", "media", "financial", "technical"]
    
    if entities is None:
        logger.info("Fetching active entities...")
        entities = get_active_entities()
        logger.info(f"Found {len(entities)} active entities")
    
    # Step 1: Run full correlation analysis
    logger.info("\n[Step 1] Running full correlation analysis...")
    try:
        result = run_full_correlation_analysis(
            entities=entities,
            signal_types=signal_types
        )
        logger.info(f"  ✓ Analyzed {result['entities_analyzed']} entities")
        logger.info(f"  ✓ Found {result['lead_lag_count']} lead-lag relationships")
        logger.info(f"  ✓ Sector correlations: {'computed' if result['sector_correlations_computed'] else 'skipped'}")
    except Exception as e:
        logger.error(f"  ✗ Error in correlation analysis: {e}")
    
    # Step 2: Rolling correlation scan for top pairs
    logger.info(f"\n[Step 2] Scanning top {scan_top_pairs} entity pairs for regime changes...")
    try:
        # Generate pairs from top entities
        top_entities = entities[:scan_top_pairs]
        pairs = []
        for i, entity_a in enumerate(top_entities):
            for entity_b in top_entities[i+1:]:
                pairs.append((entity_a, entity_b))
        
        scan_result = run_rolling_correlation_scan(pairs, signal_types[:2])
        
        logger.info(f"  ✓ Scanned {scan_result['pairs_scanned']} pairs")
        logger.info(f"  ✓ Detected {len(scan_result['regime_changes'])} regime changes")
        logger.info(f"  ✓ Generated {len(scan_result['divergence_alerts'])} divergence alerts")
        
        # Log significant findings
        for change in scan_result['regime_changes']:
            if change.get('significance') == 'high':
                logger.warning(f"  ! HIGH significance regime change: {change['entity_a']} <-> {change['entity_b']}")
        
        for alert in scan_result['divergence_alerts']:
            if alert.get('alert_level') == 'critical':
                logger.warning(f"  ! CRITICAL divergence: {alert['entity_a']} <-> {alert['entity_b']}")
                
    except Exception as e:
        logger.error(f"  ✗ Error in rolling correlation scan: {e}")
    
    # Step 3: Build signal propagation graph
    logger.info("\n[Step 3] Building signal propagation graph...")
    try:
        engine = SignalPropagationEngine()
        graph = engine.build_dependency_graph(force_refresh=True)
        logger.info(f"  ✓ Graph built with {len(graph)} entities")
        
        # Find most connected entities
        connection_counts = {entity: len(connections) for entity, connections in graph.items()}
        top_connected = sorted(connection_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        logger.info("  Top connected entities:")
        for entity, count in top_connected:
            logger.info(f"    - {entity}: {count} connections")
            
    except Exception as e:
        logger.error(f"  ✗ Error building propagation graph: {e}")
    
    # Step 4: Analyze key entity dependencies
    logger.info("\n[Step 4] Analyzing key entity dependencies...")
    key_entities = ["nvidia", "openai", "microsoft", "google", "anthropic"]
    
    for entity in key_entities:
        try:
            deps = engine.get_entity_dependencies(entity)
            if deps['affects'] or deps['affected_by']:
                logger.info(f"  {entity.upper()}:")
                logger.info(f"    Affects {len(deps['affects'])} entities")
                logger.info(f"    Affected by {len(deps['affected_by'])} entities")
        except Exception as e:
            logger.debug(f"  Could not analyze {entity}: {e}")
    
    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("Daily Correlation Analysis Complete")
    logger.info("=" * 60)
    
    # Get summary statistics
    tracker = RollingCorrelationTracker()
    active_alerts = tracker.get_active_divergence_alerts()
    recent_changes = tracker.get_recent_regime_changes(days=1)
    
    logger.info(f"Active divergence alerts: {len(active_alerts)}")
    logger.info(f"Regime changes (last 24h): {len(recent_changes)}")
    
    return {
        "entities_analyzed": len(entities),
        "active_alerts": len(active_alerts),
        "recent_regime_changes": len(recent_changes),
        "completed_at": datetime.utcnow().isoformat()
    }


def run_quick_correlation_check(entity_id: str):
    """
    Run quick correlation check for a single entity.
    
    Useful for on-demand analysis or after significant events.
    """
    logger.info(f"Quick correlation check for {entity_id}...")
    
    analyzer = CorrelationAnalyzer()
    tracker = RollingCorrelationTracker()
    engine = SignalPropagationEngine()
    
    # Get correlations
    correlations = analyzer.get_entity_correlations(entity_id, min_correlation=0.3)
    logger.info(f"Found {len(correlations)} significant correlations")
    
    # Get lead-lag
    lead_lag = analyzer.get_lead_lag_for_entity(entity_id)
    logger.info(f"Leads {len(lead_lag['as_leader'])} entities")
    logger.info(f"Follows {len(lead_lag['as_follower'])} entities")
    
    # Get dependencies
    deps = engine.get_entity_dependencies(entity_id)
    
    return {
        "entity_id": entity_id,
        "correlation_count": len(correlations),
        "leads_count": len(lead_lag['as_leader']),
        "follows_count": len(lead_lag['as_follower']),
        "top_correlations": [c.to_dict() for c in correlations[:5]],
        "dependencies": deps
    }


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Run correlation analysis")
    parser.add_argument("--entity", "-e", type=str, help="Single entity to analyze")
    parser.add_argument("--full", "-f", action="store_true", help="Run full daily analysis")
    parser.add_argument("--limit", "-l", type=int, default=50, help="Entity limit for full analysis")
    
    args = parser.parse_args()
    
    if args.entity:
        result = run_quick_correlation_check(args.entity.lower())
        print(f"\nResults for {args.entity}:")
        print(f"  Correlations: {result['correlation_count']}")
        print(f"  Leads: {result['leads_count']} entities")
        print(f"  Follows: {result['follows_count']} entities")
        if result['top_correlations']:
            print(f"\n  Top correlations:")
            for c in result['top_correlations']:
                other = c['entity_b'] if c['entity_a'] == args.entity.lower() else c['entity_a']
                print(f"    {other}: {c['correlation']:.3f}")
    else:
        result = run_daily_correlation_analysis(
            scan_top_pairs=min(args.limit, 30)
        )
        print(f"\nAnalysis complete:")
        print(f"  Entities: {result['entities_analyzed']}")
        print(f"  Active alerts: {result['active_alerts']}")
        print(f"  Recent regime changes: {result['recent_regime_changes']}")
