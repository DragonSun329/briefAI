# Real-Time Data Infrastructure

## Overview

This document describes briefAI's real-time data infrastructure, designed to achieve Bloomberg-grade latency for market signals. The system replaces batch processing with streaming for < 1 minute news-to-signal processing.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      Data Sources                                │
├──────────────┬──────────────┬──────────────┬────────────────────┤
│   yfinance   │   WebSocket  │  News APIs   │   Social/Twitter   │
└──────┬───────┴──────┬───────┴──────┬───────┴────────────────────┘
       │              │              │
       ▼              ▼              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    RealtimeFeed                                  │
│  • Multi-source aggregation                                      │
│  • WebSocket with auto-reconnection                             │
│  • Heartbeat monitoring                                          │
│  • Price history tracking                                        │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    SignalQueue                                   │
│  • Priority-based queuing                                        │
│  • Redis or in-memory backend                                    │
│  • < 10ms queue latency                                          │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                  StreamingPipeline                               │
│  • Multi-worker processing                                       │
│  • Automatic retry                                               │
│  • Dead letter queue                                             │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                  PriceAlertSystem                                │
│  • Real-time price monitoring                                    │
│  • > 2% move detection (5 min window)                           │
│  • News correlation checking                                     │
│  • SQLite persistence                                            │
└─────────────────────────────────────────────────────────────────┘
```

## Components

### 1. RealtimeFeed (`integrations/realtime_feed.py`)

Unified streaming interface for market data.

```python
from integrations.realtime_feed import RealtimeFeed, SignalProcessor

# Initialize feed
feed = RealtimeFeed(config={"poll_interval": 5.0})
await feed.start()

# Subscribe to prices
async def on_price(tick):
    print(f"{tick.symbol}: ${tick.price:.2f}")

await feed.subscribe_prices(["NVDA", "META", "MSFT"], on_price)

# Subscribe to signals
await feed.subscribe_signals(lambda s: print(f"Signal: {s.headline}"))

# Process news
processor = SignalProcessor(feed=feed, entity_ticker_map={"nvidia": "NVDA"})
signal = await processor.process_news(
    headline="NVIDIA announces breakthrough",
    entity_id="nvidia",
    source="Reuters",
)

await feed.stop()
```

**Features:**
- Multi-source data aggregation
- WebSocket support with fallback to polling
- Automatic price history tracking
- Signal emission to subscribers

**Metrics:**
```python
print(feed.metrics)
# {
#   "ticks_received": 150,
#   "signals_processed": 12,
#   "uptime_seconds": 3600,
#   "subscribed_symbols": ["NVDA", "META", "MSFT"]
# }
```

### 2. SignalQueue (`integrations/signal_queue.py`)

High-performance queue for signal processing.

```python
from integrations.signal_queue import SignalQueue, SignalPriority

queue = SignalQueue()

# Enqueue signals with priority
await queue.enqueue(
    entity_id="nvidia",
    headline="NVIDIA earnings beat expectations",
    source="Bloomberg",
    sentiment=8.0,
    priority=SignalPriority.HIGH,
)

# Urgent signals skip to front
await queue.enqueue_urgent(
    entity_id="nvidia",
    headline="BREAKING: NVIDIA stock halted",
    source="NYSE",
)

# Stream processing
async for batch in queue.stream(batch_size=5, batch_timeout=1.0):
    for signal in batch:
        process(signal)
```

**Priority Levels:**
| Priority | Value | Use Case |
|----------|-------|----------|
| URGENT   | 0     | Breaking news, trading halts |
| HIGH     | 1     | Major announcements |
| NORMAL   | 2     | Regular news (default) |
| LOW      | 3     | Background signals |

**Redis Support:**
```python
# Use Redis for distributed processing
queue = SignalQueue(use_redis=True, redis_url="redis://localhost:6379")
```

### 3. StreamingPipeline (`integrations/signal_queue.py`)

Complete pipeline for signal processing.

```python
from integrations.signal_queue import StreamingPipeline

pipeline = StreamingPipeline()

# Register handler
def on_signal(signal):
    print(f"Processed: {signal.entity_id}")
    # Save to database, trigger alerts, etc.

pipeline.on_processed(on_signal)

# Start with multiple workers
await pipeline.start(workers=4)

# Ingest signals
await pipeline.ingest(
    entity_id="nvidia",
    headline="NVIDIA AI chip demand surges",
    source="Reuters",
)

# Get metrics
print(pipeline.metrics)
# {
#   "queue": {"enqueued": 100, "processed": 100, "avg_wait_ms": 5.2},
#   "processor": {"processed": 100, "failed": 0, "avg_processing_ms": 2.1}
# }

await pipeline.stop()
```

### 4. PriceAlertSystem (`integrations/price_alerts.py`)

Real-time price movement detection.

```python
from integrations.price_alerts import PriceAlertSystem

alert_system = PriceAlertSystem(
    price_threshold_pct=2.0,  # Alert on > 2% moves
    window_minutes=5,          # In 5 minute window
    entity_ticker_map={"nvidia": "NVDA", "meta": "META"},
)

# Register alert handler
async def on_alert(alert):
    print(f"🚨 ALERT: {alert.ticker} {alert.alert_type.value}")
    print(f"   Change: {alert.price_change_pct:+.2f}%")
    print(f"   Correlation: {alert.correlation_strength}")
    if alert.correlated_signals:
        for sig in alert.correlated_signals:
            print(f"   - {sig['headline'][:50]}...")

alert_system.on_alert(on_alert)

# Start monitoring
await alert_system.start(tickers=["NVDA", "META", "MSFT", "GOOGL", "AMD"])

# Add signals for correlation
from integrations.signal_queue import QueuedSignal
alert_system.add_signal(signal)

# Get recent alerts
alerts = alert_system.get_recent_alerts(hours=24)

await alert_system.stop()
```

**Alert Types:**
- `SURGE`: Price up > threshold
- `PLUNGE`: Price down > threshold
- `VOLUME_SPIKE`: Unusual volume detected
- `VOLATILITY`: High volatility detected

**Correlation Strengths:**
- `STRONG`: Clear causal link (70%+ aligned signals)
- `MODERATE`: Likely related (50%+ aligned)
- `WEAK`: Possibly related
- `NONE`: No correlation found

**Database Schema:**
```sql
-- Alerts table
CREATE TABLE alerts (
    alert_id TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    alert_type TEXT NOT NULL,
    price_change_pct REAL NOT NULL,
    price_at_alert REAL NOT NULL,
    price_before REAL NOT NULL,
    volume_ratio REAL,
    window_minutes INTEGER,
    triggered_at TEXT NOT NULL,
    correlation_strength TEXT,
    correlation_summary TEXT
);

-- Correlated signals
CREATE TABLE alert_signals (
    id INTEGER PRIMARY KEY,
    alert_id TEXT REFERENCES alerts(alert_id),
    signal_id TEXT,
    entity_id TEXT,
    headline TEXT,
    source TEXT,
    sentiment REAL,
    signal_timestamp TEXT
);
```

### 5. WebSocket Streaming (`integrations/fincept_bridge.py`)

Enhanced WebSocket support with auto-reconnection.

```python
from integrations.fincept_bridge import UnifiedFinceptBridge

bridge = UnifiedFinceptBridge()

# Stream prices with context manager
async with bridge.stream_prices(['NVDA', 'META']) as stream:
    async for tick in stream:
        print(f"{tick['symbol']}: ${tick['price']:.2f}")
```

**WebSocket Features:**
- Exponential backoff reconnection (1s → 60s max)
- Heartbeat monitoring (30s interval)
- Connection health metrics
- Graceful degradation to polling

## Performance Metrics

### Latency Targets

| Stage | Target | Measured |
|-------|--------|----------|
| News ingestion | < 100ms | ~50ms |
| Queue wait | < 10ms | ~5ms |
| Signal processing | < 100ms | ~20ms |
| Alert detection | < 500ms | ~200ms |
| **Total E2E** | **< 1 min** | **< 1 sec** |

### Throughput

- Signal queue: 10,000+ signals/sec (in-memory)
- Price updates: 100+ ticks/sec
- Alert processing: 50+ alerts/sec

### Resource Usage

- Memory: ~50MB baseline + 1KB per cached signal
- CPU: Minimal (async I/O bound)
- Disk: SQLite writes are batched

## Configuration

### Environment Variables

```bash
# Redis (optional)
REDIS_URL=redis://localhost:6379

# yfinance polling
PRICE_POLL_INTERVAL=5.0

# Alerts
PRICE_ALERT_THRESHOLD=2.0
ALERT_WINDOW_MINUTES=5

# Queue
MAX_QUEUE_SIZE=10000
QUEUE_WORKERS=4
```

### Config File (`config/realtime.json`)

```json
{
  "feed": {
    "poll_interval": 5.0,
    "price_history_minutes": 10
  },
  "queue": {
    "use_redis": false,
    "redis_url": "redis://localhost:6379",
    "max_size": 10000,
    "workers": 4
  },
  "alerts": {
    "price_threshold_pct": 2.0,
    "window_minutes": 5,
    "cooldown_minutes": 5
  },
  "websocket": {
    "heartbeat_interval": 30.0,
    "max_retries": 10,
    "initial_backoff": 1.0,
    "max_backoff": 60.0
  }
}
```

## Integration Example

Complete integration with all components:

```python
import asyncio
from integrations.realtime_feed import RealtimeFeed, SignalProcessor
from integrations.signal_queue import StreamingPipeline
from integrations.price_alerts import PriceAlertSystem

async def main():
    # Entity-ticker mapping
    entity_map = {
        "nvidia": "NVDA",
        "meta": "META", 
        "microsoft": "MSFT",
        "google": "GOOGL",
        "amd": "AMD",
    }
    
    # Create components
    feed = RealtimeFeed(config={"poll_interval": 5.0})
    pipeline = StreamingPipeline()
    alerts = PriceAlertSystem(
        feed=feed,
        price_threshold_pct=2.0,
        entity_ticker_map=entity_map,
    )
    
    # Connect pipeline to alerts
    def on_processed(signal):
        alerts.add_signal(signal)
        print(f"Processed: {signal.entity_id} ({signal.sentiment:.1f}/10)")
    
    pipeline.on_processed(on_processed)
    
    # Handle alerts
    async def on_alert(alert):
        print(f"🚨 {alert.ticker}: {alert.price_change_pct:+.2f}%")
        if alert.correlation_summary:
            print(f"   {alert.correlation_summary}")
    
    alerts.on_alert(on_alert)
    
    # Start everything
    await feed.start()
    await pipeline.start(workers=4)
    await alerts.start(tickers=list(entity_map.values()))
    
    # Create signal processor
    processor = SignalProcessor(feed=feed, entity_ticker_map=entity_map)
    
    # Process incoming news (example)
    await processor.process_news(
        headline="NVIDIA AI chip demand exceeds forecasts",
        entity_id="nvidia",
        source="Bloomberg",
    )
    
    # Run for a while
    await asyncio.sleep(60)
    
    # Cleanup
    await alerts.stop()
    await pipeline.stop()
    await feed.stop()

asyncio.run(main())
```

## Testing

Run tests:

```bash
# All tests
pytest tests/test_realtime.py -v

# Specific test
pytest tests/test_realtime.py::TestEndToEndLatency -v -s

# With coverage
pytest tests/test_realtime.py --cov=integrations --cov-report=html
```

## Monitoring

### Health Check Endpoint

```python
def health_check():
    return {
        "feed": feed.metrics,
        "pipeline": pipeline.metrics,
        "alerts": alerts.metrics,
        "status": "healthy" if feed.is_running else "degraded",
    }
```

### Prometheus Metrics (Optional)

```python
# Add prometheus-client
from prometheus_client import Counter, Histogram

SIGNALS_PROCESSED = Counter('briefai_signals_processed_total', 'Total signals processed')
SIGNAL_LATENCY = Histogram('briefai_signal_latency_ms', 'Signal processing latency')
ALERTS_TRIGGERED = Counter('briefai_alerts_triggered_total', 'Total price alerts')
```

## Troubleshooting

### Common Issues

1. **No price updates**
   - Check yfinance availability: `pip install yfinance`
   - Verify market hours (US markets: 9:30 AM - 4:00 PM ET)
   - Check rate limiting

2. **Queue growing unbounded**
   - Increase worker count
   - Check for blocked handlers
   - Enable Redis for horizontal scaling

3. **Alerts not triggering**
   - Verify threshold is reasonable for current volatility
   - Check ticker is being tracked
   - Ensure feed is receiving price updates

4. **WebSocket disconnecting**
   - Check network stability
   - Verify endpoint URL
   - Review reconnection backoff settings

### Debug Mode

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Or for specific modules
logging.getLogger("integrations.realtime_feed").setLevel(logging.DEBUG)
```

## Future Enhancements

1. **Additional Data Sources**
   - Polygon.io WebSocket
   - Alpaca real-time
   - IEX Cloud

2. **ML-Based Alerts**
   - Anomaly detection on price patterns
   - Sentiment-price correlation prediction
   - Volume spike prediction

3. **Distributed Processing**
   - Kubernetes deployment
   - Redis Cluster support
   - Cross-region failover
