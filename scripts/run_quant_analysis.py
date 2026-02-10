#!/usr/bin/env python3
"""
Run Quantitative Analysis Script

Batch analyzer that runs all quant modules on configured entities:
1. Loads entity/asset mappings
2. Fetches required data (prices, sentiment, mentions)
3. Runs correlation, momentum, sentiment technical analysis
4. Aggregates into composite scores
5. Generates leaderboard and report
"""

import argparse
import json
import sys
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional
from loguru import logger

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.correlation_engine import CorrelationEngine, create_ai_sector_correlation_matrix
from utils.momentum_signals import MomentumCalculator, rank_entities_by_momentum
from utils.sentiment_technicals import SentimentTechnicals
from utils.quant_aggregator import QuantAggregator, run_quant_aggregation


def load_asset_mapping() -> Dict[str, Any]:
    """Load the asset mapping configuration."""
    mapping_path = project_root / "data" / "asset_mapping.json"
    with open(mapping_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_recent_signals() -> Dict[str, Dict[date, float]]:
    """
    Load recent signal data from alternative_signals directory.
    
    Returns:
        Dict of entity_id -> date -> sentiment/score
    """
    signals_dir = project_root / "data" / "alternative_signals"
    entity_sentiments: Dict[str, Dict[date, float]] = {}
    entity_mentions: Dict[str, Dict[date, int]] = {}
    
    # Load recent news data
    news_files = sorted(signals_dir.glob("news_search_*.json"), reverse=True)
    
    for news_file in news_files[:30]:  # Last 30 days
        try:
            with open(news_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            file_date_str = news_file.stem.replace("news_search_", "")
            file_date = datetime.strptime(file_date_str, "%Y-%m-%d").date()
            
            # Extract sentiment per entity from articles
            for article in data.get("articles", []):
                entities = article.get("entities", [])
                sentiment = article.get("sentiment", {})
                
                # Get sentiment score (normalize to 0-10 if needed)
                score = sentiment.get("score", 5.0)
                if isinstance(score, str):
                    score = float(score) if score else 5.0
                
                for entity in entities:
                    entity_id = entity.lower().replace(" ", "-")
                    
                    if entity_id not in entity_sentiments:
                        entity_sentiments[entity_id] = {}
                        entity_mentions[entity_id] = {}
                    
                    # Aggregate sentiment for the day
                    if file_date in entity_sentiments[entity_id]:
                        # Average with existing
                        existing = entity_sentiments[entity_id][file_date]
                        entity_sentiments[entity_id][file_date] = (existing + score) / 2
                        entity_mentions[entity_id][file_date] += 1
                    else:
                        entity_sentiments[entity_id][file_date] = score
                        entity_mentions[entity_id][file_date] = 1
                        
        except Exception as e:
            logger.debug(f"Could not process {news_file}: {e}")
    
    return entity_sentiments, entity_mentions


def load_funding_events() -> Dict[str, List[Dict[str, Any]]]:
    """Load funding event data."""
    funding_events: Dict[str, List[Dict[str, Any]]] = {}
    
    # Load from Crunchbase data
    crunchbase_files = sorted(
        (project_root / "data" / "alternative_signals").glob("crunchbase_*.json"),
        reverse=True
    )
    
    for cb_file in crunchbase_files[:5]:
        try:
            with open(cb_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            for company in data.get("companies", []):
                entity_id = company.get("canonical_id", "").lower().replace(" ", "-")
                if not entity_id:
                    continue
                
                funding = company.get("funding", {})
                if funding:
                    if entity_id not in funding_events:
                        funding_events[entity_id] = []
                    
                    for round_info in funding.get("rounds", []):
                        event = {
                            "date": datetime.strptime(
                                round_info.get("date", "2020-01-01"), 
                                "%Y-%m-%d"
                            ).date() if round_info.get("date") else date.today(),
                            "amount_usd": round_info.get("amount_usd", 0),
                            "round": round_info.get("round_type", "unknown")
                        }
                        funding_events[entity_id].append(event)
                        
        except Exception as e:
            logger.debug(f"Could not process {cb_file}: {e}")
    
    # Also load from OpenBook VC
    openbook_files = sorted(
        (project_root / "data" / "alternative_signals").glob("openbook_vc_*.json"),
        reverse=True
    )
    
    for ob_file in openbook_files[:5]:
        try:
            with open(ob_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            for deal in data.get("deals", []):
                company_name = deal.get("company", "").lower().replace(" ", "-")
                if not company_name:
                    continue
                
                if company_name not in funding_events:
                    funding_events[company_name] = []
                
                event = {
                    "date": datetime.strptime(
                        deal.get("date", date.today().isoformat()),
                        "%Y-%m-%d"
                    ).date() if deal.get("date") else date.today(),
                    "amount_usd": deal.get("amount_usd", 0),
                    "round": deal.get("stage", "unknown")
                }
                funding_events[company_name].append(event)
                
        except Exception as e:
            logger.debug(f"Could not process {ob_file}: {e}")
    
    return funding_events


def run_analysis(
    entities: Optional[List[str]] = None,
    lookback_days: int = 60,
    output_dir: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Run full quantitative analysis pipeline.
    
    Args:
        entities: List of entity IDs to analyze (None = all from mapping)
        lookback_days: Days of historical data to use
        output_dir: Directory to save output
        
    Returns:
        Complete analysis results
    """
    logger.info(f"Starting quant analysis with {lookback_days} day lookback")
    
    # Load configurations
    asset_mapping = load_asset_mapping()
    entity_configs = asset_mapping.get("entities", {})
    
    if entities is None:
        # Use top 20 public AI companies
        entities = [
            eid for eid, config in entity_configs.items()
            if config.get("status") == "public" or config.get("proxy_tickers")
        ][:20]
    
    logger.info(f"Analyzing {len(entities)} entities")
    
    # Load historical data
    sentiment_data, mention_data = load_recent_signals()
    funding_data = load_funding_events()
    
    # Initialize analyzers
    correlation_engine = CorrelationEngine()
    momentum_calc = MomentumCalculator()
    sentiment_tech = SentimentTechnicals()
    
    # Analyze each entity
    entity_signals: Dict[str, Dict[str, Any]] = {}
    entity_names: Dict[str, str] = {}
    
    for entity_id in entities:
        config = entity_configs.get(entity_id, {})
        entity_names[entity_id] = config.get("name", entity_id.title())
        
        signals = {}
        
        # Get sentiment history for this entity
        sentiment_history = sentiment_data.get(entity_id, {})
        mention_history = mention_data.get(entity_id, {})
        funding_events = funding_data.get(entity_id, [])
        
        # If no direct data, try ticker-based lookup
        if not sentiment_history:
            # Try company name variations
            for key in sentiment_data:
                if entity_id in key or key in entity_id:
                    sentiment_history = sentiment_data[key]
                    mention_history = mention_data.get(key, {})
                    break
        
        logger.debug(f"Processing {entity_id}: {len(sentiment_history)} sentiment points, "
                    f"{len(mention_history)} mention points")
        
        # Correlation analysis (if we have ticker and sentiment)
        ticker = correlation_engine.get_ticker_for_entity(entity_id)
        if ticker and sentiment_history:
            corr_result = correlation_engine.analyze_entity(
                entity_id, sentiment_history, lookback_days=lookback_days
            )
            if corr_result.get("has_signal"):
                signals["correlation"] = corr_result.get("correlation", {})
                signals["lead_lag"] = corr_result.get("lead_lag", {})
        
        # Momentum analysis
        if mention_history:
            buzz = momentum_calc.calculate_buzz_momentum(entity_id, mention_history)
            signals["buzz_momentum"] = buzz.to_dict()
        
        if funding_events:
            funding = momentum_calc.calculate_funding_momentum(entity_id, funding_events)
            signals["funding_momentum"] = funding.to_dict()
        
        if sentiment_history:
            rsi = momentum_calc.generate_sentiment_rsi(entity_id, sentiment_history)
            signals["sentiment_rsi"] = rsi.to_dict()
        
        # Sentiment technicals
        if sentiment_history:
            ma_result = sentiment_tech.calculate_sentiment_mas(entity_id, sentiment_history)
            signals["moving_averages"] = ma_result.to_dict()
            
            bb_result = sentiment_tech.calculate_bollinger_bands(entity_id, sentiment_history)
            signals["bollinger_bands"] = bb_result.to_dict()
        
        # Price divergence (if we have both sentiment and price)
        if ticker and sentiment_history:
            start_date = min(sentiment_history.keys()) - timedelta(days=10)
            end_date = max(sentiment_history.keys()) + timedelta(days=5)
            
            price_history = correlation_engine.fetch_price_history(
                ticker, start_date, end_date
            )
            
            if price_history:
                div_result = sentiment_tech.detect_divergence(
                    entity_id, sentiment_history, price_history
                )
                signals["divergence"] = div_result.to_dict()
        
        if signals:
            entity_signals[entity_id] = signals
            logger.info(f"  {entity_id}: {len(signals)} signal types")
    
    # Aggregate signals
    logger.info("Aggregating signals into composite scores")
    result = run_quant_aggregation(entity_signals, entity_names)
    
    # Add correlation matrix
    logger.info("Building AI sector correlation matrix")
    corr_matrix = create_ai_sector_correlation_matrix(
        start_date=date.today() - timedelta(days=lookback_days),
        end_date=date.today()
    )
    result["correlation_matrix"] = corr_matrix
    
    # Add metadata
    result["metadata"] = {
        "generated_at": datetime.now().isoformat(),
        "lookback_days": lookback_days,
        "entities_analyzed": len(entity_signals),
        "entities_requested": len(entities),
        "data_coverage": {
            "sentiment_entities": len(sentiment_data),
            "mention_entities": len(mention_data),
            "funding_entities": len(funding_data),
        }
    }
    
    # Save results
    if output_dir is None:
        output_dir = project_root / "data" / "alternative_signals"
    
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"quant_analysis_{date.today().isoformat()}.json"
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False, default=str)
    
    logger.info(f"Saved quant analysis to {output_path}")
    
    return result


def print_report(result: Dict[str, Any]):
    """Print formatted report to console."""
    print("\n" + "=" * 70)
    print("QUANTITATIVE SIGNAL ANALYSIS REPORT")
    print("=" * 70)
    
    report = result.get("report", {})
    summary = report.get("summary", {})
    
    print(f"\nGenerated: {result.get('metadata', {}).get('generated_at', 'N/A')}")
    print(f"Entities Analyzed: {summary.get('total_entities', 0)}")
    print(f"Lookback Period: {result.get('metadata', {}).get('lookback_days', 0)} days")
    
    print("\n--- MARKET SENTIMENT ---")
    print(f"Bullish Entities: {summary.get('bullish_count', 0)} ({summary.get('bullish_ratio', 0)*100:.1f}%)")
    print(f"Bearish Entities: {summary.get('bearish_count', 0)}")
    print(f"Neutral Entities: {summary.get('neutral_count', 0)}")
    print(f"Average Composite Score: {summary.get('average_score', 0):.1f}")
    
    print("\n--- TOP BULLISH SIGNALS ---")
    for entry in report.get("top_bullish", []):
        print(f"  {entry['entity_name']}: Score {entry['composite_score']:.1f}, "
              f"Strength {entry['signal_strength']:.2f}")
    
    print("\n--- TOP BEARISH SIGNALS ---")
    for entry in report.get("top_bearish", []):
        print(f"  {entry['entity_name']}: Score {entry['composite_score']:.1f}, "
              f"Strength {entry['signal_strength']:.2f}")
    
    print("\n--- ACCELERATING MOMENTUM ---")
    for entry in report.get("accelerating", []):
        print(f"  {entry['entity_name']}: Score {entry['composite_score']:.1f}, "
              f"Momentum: {entry['momentum']}")
    
    print("\n--- LEADERBOARD ---")
    for entry in result.get("leaderboard", [])[:10]:
        direction_emoji = "🟢" if entry['direction'] == "bullish" else \
                         "🔴" if entry['direction'] == "bearish" else "⚪"
        print(f"  #{entry['rank']:2d} {direction_emoji} {entry['entity_name']:20s} "
              f"Score: {entry['composite_score']:5.1f}  "
              f"Strength: {entry['signal_strength']:.2f}")
    
    print("\n" + "=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description="Run quantitative signal analysis on AI entities"
    )
    parser.add_argument(
        "--entities", "-e",
        nargs="+",
        help="Specific entity IDs to analyze (default: top 20 public AI companies)"
    )
    parser.add_argument(
        "--lookback", "-l",
        type=int,
        default=60,
        help="Lookback period in days (default: 60)"
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        help="Output directory for results"
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress console report"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )
    
    args = parser.parse_args()
    
    # Configure logging
    logger.remove()
    log_level = "DEBUG" if args.debug else "INFO"
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
        level=log_level
    )
    
    # Run analysis
    result = run_analysis(
        entities=args.entities,
        lookback_days=args.lookback,
        output_dir=args.output
    )
    
    # Print report
    if not args.quiet:
        print_report(result)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
