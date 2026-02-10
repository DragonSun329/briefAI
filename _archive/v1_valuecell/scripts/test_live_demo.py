#!/usr/bin/env python3
"""
Live Demo - Real-Time Infrastructure Test

Tests the complete real-time system with live market data.
Monitors 5 high-volume tickers: NVDA, META, MSFT, GOOGL, AMD

Run: python scripts/test_live_demo.py
"""

import asyncio
import time
from datetime import datetime
import sys
from pathlib import Path

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from integrations.realtime_feed import RealtimeFeed, SignalProcessor, PriceTick
from integrations.signal_queue import StreamingPipeline
from integrations.price_alerts import PriceAlertSystem


async def test_live():
    print("=" * 60)
    print("briefAI Real-Time Infrastructure - Live Test")
    print("=" * 60)
    print(f"Started: {datetime.now().isoformat()}")
    
    # Entity-ticker mapping for 5 high-volume tickers
    entity_map = {
        "nvidia": "NVDA",
        "meta": "META",
        "microsoft": "MSFT",
        "google": "GOOGL",
        "amd": "AMD",
    }
    tickers = list(entity_map.values())
    
    # Create components
    feed = RealtimeFeed(config={"poll_interval": 5.0})
    pipeline = StreamingPipeline()
    alerts = PriceAlertSystem(
        feed=feed,
        price_threshold_pct=2.0,  # 2% threshold
        window_minutes=5,
        entity_ticker_map=entity_map,
    )
    
    # Track results
    ticks_received = []
    signals_processed = []
    alerts_triggered = []
    latencies = []
    
    async def on_tick(tick: PriceTick):
        ticks_received.append(tick)
        if len(ticks_received) <= 10:  # Show first 10
            print(f"  TICK: {tick.symbol} = ${tick.price:.2f}")
    
    def on_signal(signal):
        signals_processed.append(signal)
        # Calculate latency
        arrival = signal.metadata.get("arrival_time")
        if arrival:
            arrival_dt = datetime.fromisoformat(arrival)
            latency_ms = (datetime.now() - arrival_dt).total_seconds() * 1000
            latencies.append(latency_ms)
        print(f"  SIGNAL: {signal.entity_id} ({signal.sentiment:.1f}/10)")
    
    async def on_alert(alert):
        alerts_triggered.append(alert)
        print(f"  ALERT: {alert.ticker} {alert.price_change_pct:+.2f}%")
    
    pipeline.on_processed(on_signal)
    alerts.on_alert(on_alert)
    
    # Start everything
    print(f"\nMonitoring: {tickers}")
    print(f"Threshold: 2% in 5 min")
    print()
    
    start_time = time.time()
    
    await feed.start()
    await pipeline.start(workers=2)
    await alerts.start(tickers=tickers)
    await feed.subscribe_prices(tickers, on_tick)
    
    # Create signal processor
    processor = SignalProcessor(feed=feed, entity_ticker_map=entity_map)
    
    # Simulate news arrivals
    test_news = [
        ("NVIDIA announces AI chip breakthrough with 50% performance gain", "nvidia"),
        ("Meta AI model outperforms competitors in benchmarks", "meta"),
        ("Microsoft Azure AI revenue surges to record high", "microsoft"),
        ("Google Gemini 2.0 released with improved reasoning", "google"),
        ("AMD MI400 GPU challenges NVIDIA datacenter dominance", "amd"),
    ]
    
    print("Processing test news...")
    for headline, entity in test_news:
        arrival = datetime.now()
        
        # Process through signal processor
        signal = await processor.process_news(
            headline=headline,
            entity_id=entity,
            source="test",
            arrival_time=arrival,
        )
        
        # Also enqueue in pipeline
        await pipeline.ingest(
            entity_id=entity,
            headline=headline,
            source="test",
            metadata={"arrival_time": arrival.isoformat()},
        )
    
    # Wait for live data
    print("\nCollecting live data (20 seconds)...")
    await asyncio.sleep(20)
    
    elapsed = time.time() - start_time
    
    # Results
    print()
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"Total runtime: {elapsed:.1f}s")
    print(f"Price ticks received: {len(ticks_received)}")
    print(f"Signals processed: {len(signals_processed)}")
    print(f"Alerts triggered: {len(alerts_triggered)}")
    
    # Latency analysis
    if latencies:
        avg_latency = sum(latencies) / len(latencies)
        max_latency = max(latencies)
        print(f"\nLatency Analysis:")
        print(f"  Average: {avg_latency:.2f}ms")
        print(f"  Maximum: {max_latency:.2f}ms")
        print(f"  Target (<60s): {'PASS' if max_latency < 60000 else 'FAIL'}")
    
    # Feed metrics
    metrics = feed.metrics
    print(f"\nFeed metrics:")
    print(f"  Ticks: {metrics['ticks_received']}")
    print(f"  Signals: {metrics['signals_processed']}")
    
    # Pipeline metrics
    p_metrics = pipeline.metrics
    print(f"\nPipeline metrics:")
    print(f"  Enqueued: {p_metrics['queue']['enqueued']}")
    print(f"  Processed: {p_metrics['processor']['processed']}")
    print(f"  Avg queue wait: {p_metrics['queue']['avg_wait_ms']:.2f}ms")
    if p_metrics['processor'].get('avg_processing_ms'):
        print(f"  Avg processing: {p_metrics['processor']['avg_processing_ms']:.2f}ms")
    
    # Alert metrics
    a_metrics = alerts.metrics
    print(f"\nAlert metrics:")
    print(f"  Alerts triggered: {a_metrics['alerts_triggered']}")
    print(f"  Correlations found: {a_metrics['correlations_found']}")
    
    # Price data summary
    print(f"\nPrice Data Summary:")
    seen_tickers = set()
    for tick in ticks_received:
        if tick.symbol not in seen_tickers:
            seen_tickers.add(tick.symbol)
            print(f"  {tick.symbol}: ${tick.price:.2f}")
    
    # Cleanup
    await alerts.stop()
    await pipeline.stop()
    await feed.stop()
    
    print()
    print("=" * 60)
    print("SUCCESS - Real-time infrastructure operational!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_live())
