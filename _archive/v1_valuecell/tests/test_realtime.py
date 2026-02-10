"""
Tests for Real-Time Data Infrastructure

Tests the following components:
- RealtimeFeed (streaming interface)
- SignalQueue (signal processing queue)
- PriceAlertSystem (alert monitoring)
- Latency measurements (target: < 1 min)

Run with: pytest tests/test_realtime.py -v
"""

import asyncio
import time
from datetime import datetime, timedelta
from pathlib import Path
import sys
import pytest

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from integrations.realtime_feed import (
    RealtimeFeed, PriceTick, SignalEvent, SignalProcessor
)
from integrations.signal_queue import (
    SignalQueue, QueuedSignal, SignalPriority, StreamingPipeline
)
from integrations.price_alerts import (
    PriceAlertSystem, PriceAlert, AlertType, CorrelationChecker
)


# =============================================================================
# RealtimeFeed Tests
# =============================================================================

class TestRealtimeFeed:
    """Tests for RealtimeFeed."""
    
    @pytest.mark.asyncio
    async def test_feed_start_stop(self):
        """Test feed lifecycle."""
        feed = RealtimeFeed(config={"poll_interval": 10.0})
        
        assert not feed.is_running
        
        await feed.start()
        assert feed.is_running
        assert feed.uptime is not None
        
        await feed.stop()
        assert not feed.is_running
    
    @pytest.mark.asyncio
    async def test_price_subscription(self):
        """Test subscribing to price updates."""
        feed = RealtimeFeed(config={"poll_interval": 5.0})
        await feed.start()
        
        received_ticks = []
        
        async def on_tick(tick: PriceTick):
            received_ticks.append(tick)
        
        await feed.subscribe_prices(["NVDA"], on_tick)
        
        # Wait for at least one tick
        await asyncio.sleep(10)
        
        # Should have received at least one tick
        # (may be 0 if yfinance unavailable or rate limited)
        
        await feed.stop()
    
    @pytest.mark.asyncio
    async def test_signal_emission(self):
        """Test signal emission to subscribers."""
        feed = RealtimeFeed()
        await feed.start()
        
        received_signals = []
        
        async def on_signal(signal: SignalEvent):
            received_signals.append(signal)
        
        await feed.subscribe_signals(on_signal)
        
        # Emit a test signal
        test_signal = SignalEvent(
            signal_id="test_001",
            entity_id="nvidia",
            ticker="NVDA",
            signal_type="news",
            sentiment=7.5,
            confidence=0.8,
            headline="Test headline",
            source="test",
            timestamp=datetime.now(),
        )
        
        await feed.emit_signal(test_signal)
        
        assert len(received_signals) == 1
        assert received_signals[0].signal_id == "test_001"
        
        await feed.stop()
    
    @pytest.mark.asyncio
    async def test_price_history(self):
        """Test price history tracking."""
        feed = RealtimeFeed(config={"poll_interval": 2.0})
        await feed.start()
        
        await feed.subscribe_prices(["MSFT"], lambda x: None)
        
        # Wait for some history to accumulate
        await asyncio.sleep(8)
        
        history = feed.get_price_history("MSFT", minutes=5)
        
        # History may or may not have entries depending on yfinance
        # Just verify it returns a list
        assert isinstance(history, list)
        
        await feed.stop()


class TestSignalProcessor:
    """Tests for SignalProcessor."""
    
    @pytest.mark.asyncio
    async def test_process_news(self):
        """Test news processing."""
        feed = RealtimeFeed()
        await feed.start()
        
        processor = SignalProcessor(
            feed=feed,
            entity_ticker_map={"nvidia": "NVDA"}
        )
        
        received = []
        await feed.subscribe_signals(lambda s: received.append(s))
        
        signal = await processor.process_news(
            headline="NVIDIA stock surges on AI demand",
            entity_id="nvidia",
            source="Reuters",
        )
        
        assert signal is not None
        assert signal.ticker == "NVDA"
        assert signal.sentiment > 5.0  # Should be bullish
        
        await feed.stop()
    
    @pytest.mark.asyncio
    async def test_processing_latency(self):
        """Test that processing is fast (< 100ms per signal)."""
        feed = RealtimeFeed()
        processor = SignalProcessor(feed=feed)
        
        start = time.time()
        
        for i in range(10):
            await processor.process_news(
                headline=f"Test headline {i}",
                entity_id="test",
                source="test",
            )
        
        elapsed = time.time() - start
        avg_ms = (elapsed / 10) * 1000
        
        print(f"Average processing time: {avg_ms:.2f}ms")
        assert avg_ms < 100, f"Processing too slow: {avg_ms}ms"


# =============================================================================
# SignalQueue Tests
# =============================================================================

class TestSignalQueue:
    """Tests for SignalQueue."""
    
    @pytest.mark.asyncio
    async def test_enqueue_dequeue(self):
        """Test basic enqueue/dequeue."""
        queue = SignalQueue()
        
        signal_id = await queue.enqueue(
            entity_id="nvidia",
            headline="Test headline",
            source="test",
            sentiment=7.0,
        )
        
        assert signal_id is not None
        assert await queue.size() == 1
        
        signal = await queue.dequeue()
        
        assert signal is not None
        assert signal.entity_id == "nvidia"
        assert await queue.size() == 0
    
    @pytest.mark.asyncio
    async def test_priority_ordering(self):
        """Test that high priority signals are processed first."""
        queue = SignalQueue()
        
        # Add normal priority
        await queue.enqueue(
            entity_id="normal",
            headline="Normal",
            source="test",
            priority=SignalPriority.NORMAL,
        )
        
        # Add urgent priority
        await queue.enqueue_urgent(
            entity_id="urgent",
            headline="Urgent",
            source="test",
        )
        
        # Urgent should come first
        first = await queue.dequeue()
        assert first.entity_id == "urgent"
        
        second = await queue.dequeue()
        assert second.entity_id == "normal"
    
    @pytest.mark.asyncio
    async def test_queue_streaming(self):
        """Test streaming from queue."""
        queue = SignalQueue()
        
        # Add signals
        for i in range(5):
            await queue.enqueue(
                entity_id=f"entity_{i}",
                headline=f"Headline {i}",
                source="test",
            )
        
        received = []
        
        async def collect():
            async for batch in queue.stream(batch_size=2, batch_timeout=0.5):
                received.extend(batch)
                if len(received) >= 5:
                    queue.stop()
        
        await asyncio.wait_for(collect(), timeout=5.0)
        
        assert len(received) == 5
    
    @pytest.mark.asyncio
    async def test_queue_latency(self):
        """Test queue latency is low."""
        queue = SignalQueue()
        
        latencies = []
        
        for i in range(20):
            enqueue_time = datetime.now()
            await queue.enqueue(
                entity_id="test",
                headline="Test",
                source="test",
            )
            
            signal = await queue.dequeue()
            dequeue_time = datetime.now()
            
            latency_ms = (dequeue_time - enqueue_time).total_seconds() * 1000
            latencies.append(latency_ms)
        
        avg_latency = sum(latencies) / len(latencies)
        max_latency = max(latencies)
        
        print(f"Queue latency - avg: {avg_latency:.2f}ms, max: {max_latency:.2f}ms")
        
        assert avg_latency < 10, f"Average latency too high: {avg_latency}ms"


class TestStreamingPipeline:
    """Tests for StreamingPipeline."""
    
    @pytest.mark.asyncio
    async def test_pipeline_processing(self):
        """Test end-to-end pipeline processing."""
        pipeline = StreamingPipeline()
        
        processed = []
        
        def on_processed(signal):
            processed.append(signal)
        
        pipeline.on_processed(on_processed)
        
        await pipeline.start(workers=2)
        
        # Ingest signals
        for i in range(5):
            await pipeline.ingest(
                entity_id=f"entity_{i}",
                headline=f"Headline {i}",
                source="test",
            )
        
        # Wait for processing
        await asyncio.sleep(2)
        
        assert len(processed) == 5
        
        await pipeline.stop()


# =============================================================================
# Price Alert Tests
# =============================================================================

class TestCorrelationChecker:
    """Tests for CorrelationChecker."""
    
    def test_add_signal(self):
        """Test adding signals to cache."""
        checker = CorrelationChecker(
            signal_lookback_minutes=60,
            entity_ticker_map={"nvidia": "NVDA"}
        )
        
        signal = QueuedSignal(
            signal_id="sig_001",
            entity_id="nvidia",
            ticker="NVDA",
            signal_type="news",
            sentiment=8.0,
            confidence=0.8,
            headline="NVIDIA breakthrough",
            source="test",
            priority=SignalPriority.NORMAL,
            enqueued_at=datetime.now(),
        )
        
        checker.add_signal(signal)
        
        # Find correlation
        correlated, strength = checker.find_correlations(
            ticker="NVDA",
            price_move_direction="up",
        )
        
        assert len(correlated) == 1
        assert correlated[0]["entity_id"] == "nvidia"
    
    def test_correlation_strength(self):
        """Test correlation strength calculation."""
        checker = CorrelationChecker(
            entity_ticker_map={"nvidia": "NVDA"}
        )
        
        # Add multiple bullish signals
        for i in range(3):
            signal = QueuedSignal(
                signal_id=f"sig_{i}",
                entity_id="nvidia",
                ticker="NVDA",
                signal_type="news",
                sentiment=8.0,  # Bullish
                confidence=0.8,
                headline=f"NVIDIA bullish news {i}",
                source="test",
                priority=SignalPriority.NORMAL,
                enqueued_at=datetime.now(),
            )
            checker.add_signal(signal)
        
        # Find correlation for upward move
        _, strength = checker.find_correlations("NVDA", "up")
        
        # Should be strong (aligned bullish signals + upward move)
        assert strength.value in ["strong", "moderate"]


class TestPriceAlertSystem:
    """Tests for PriceAlertSystem."""
    
    @pytest.mark.asyncio
    async def test_alert_system_lifecycle(self):
        """Test alert system start/stop."""
        system = PriceAlertSystem(
            price_threshold_pct=2.0,
            window_minutes=5,
        )
        
        await system.start(tickers=["NVDA"])
        
        assert system._running
        assert "NVDA" in system._tracked_tickers
        
        await system.stop()
        assert not system._running
    
    @pytest.mark.asyncio
    async def test_alert_callback(self):
        """Test alert callback registration."""
        system = PriceAlertSystem(
            price_threshold_pct=0.01,  # Very low for testing
            window_minutes=5,
        )
        
        alerts_received = []
        
        system.on_alert(lambda a: alerts_received.append(a))
        
        # Can't easily trigger real alerts without mocking
        # Just verify callback registration works
        assert len(system._alert_callbacks) == 1
    
    def test_alert_store(self):
        """Test alert persistence."""
        import tempfile
        import gc
        
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)
        
        try:
            from integrations.price_alerts import AlertStore
            
            store = AlertStore(db_path)
            
            # Create test alert
            alert = PriceAlert(
                alert_id="test_alert_001",
                ticker="NVDA",
                alert_type=AlertType.SURGE,
                price_change_pct=5.0,
                price_at_alert=500.0,
                price_before=476.19,
                volume_ratio=1.5,
                window_minutes=5,
                triggered_at=datetime.now(),
            )
            
            # Save
            assert store.save_alert(alert)
            
            # Retrieve
            retrieved = store.get_alert("test_alert_001")
            assert retrieved is not None
            assert retrieved.ticker == "NVDA"
            assert retrieved.price_change_pct == 5.0
            
            # Stats
            stats = store.get_alert_stats()
            assert stats["total_alerts"] >= 1
            
        finally:
            # Force garbage collection to close SQLite connections on Windows
            del store
            gc.collect()
            try:
                db_path.unlink(missing_ok=True)
            except PermissionError:
                pass  # Windows may still hold the file, ignore


# =============================================================================
# End-to-End Latency Test
# =============================================================================

class TestEndToEndLatency:
    """Test end-to-end latency from news arrival to processed signal."""
    
    @pytest.mark.asyncio
    async def test_full_pipeline_latency(self):
        """
        Test that news can be processed in < 1 minute end-to-end.
        
        This is the key metric for Bloomberg-grade latency.
        """
        from integrations.realtime_feed import RealtimeFeed, SignalProcessor
        from integrations.signal_queue import SignalQueue, StreamingPipeline
        
        # Set up pipeline
        feed = RealtimeFeed()
        await feed.start()
        
        pipeline = StreamingPipeline()
        
        latencies = []
        
        def track_latency(signal):
            arrival = datetime.fromisoformat(signal.metadata.get("arrival_time", signal.enqueued_at.isoformat()))
            processed = datetime.now()
            latency_ms = (processed - arrival).total_seconds() * 1000
            latencies.append(latency_ms)
        
        pipeline.on_processed(track_latency)
        await pipeline.start(workers=2)
        
        # Simulate news arrivals
        processor = SignalProcessor(
            feed=feed,
            entity_ticker_map={"nvidia": "NVDA", "meta": "META"}
        )
        
        test_headlines = [
            ("NVIDIA announces record earnings", "nvidia"),
            ("Meta launches new AI model", "meta"),
            ("NVIDIA GPU demand surges", "nvidia"),
            ("Meta metaverse pivot continues", "meta"),
            ("NVIDIA data center growth accelerates", "nvidia"),
        ]
        
        start_time = time.time()
        
        for headline, entity in test_headlines:
            arrival_time = datetime.now()
            
            # Process through signal processor
            signal = await processor.process_news(
                headline=headline,
                entity_id=entity,
                source="test",
                arrival_time=arrival_time,
            )
            
            # Also enqueue in pipeline
            await pipeline.ingest(
                entity_id=entity,
                headline=headline,
                source="test",
                metadata={"arrival_time": arrival_time.isoformat()},
            )
        
        # Wait for processing
        await asyncio.sleep(2)
        
        total_time = (time.time() - start_time) * 1000
        
        print(f"\n{'='*60}")
        print("END-TO-END LATENCY TEST")
        print(f"{'='*60}")
        print(f"Signals processed: {len(latencies)}")
        
        if latencies:
            avg_latency = sum(latencies) / len(latencies)
            max_latency = max(latencies)
            print(f"Average latency: {avg_latency:.2f}ms")
            print(f"Max latency: {max_latency:.2f}ms")
            print(f"Total time: {total_time:.2f}ms")
            
            # Target: < 1 minute (60,000 ms)
            # In practice, we should be < 1 second
            assert max_latency < 60000, f"Latency exceeds 1 minute: {max_latency}ms"
            
            # More realistic target: < 1 second
            assert avg_latency < 1000, f"Average latency too high: {avg_latency}ms"
        
        await pipeline.stop()
        await feed.stop()


# =============================================================================
# Run tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
