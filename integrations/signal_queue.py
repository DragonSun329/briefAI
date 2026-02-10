"""
Signal Queue - Real-Time Signal Processing

Implements a high-performance queue for incoming signals with:
- Redis support (when available) for distributed processing
- In-memory fallback for single-node operation
- Priority queuing for urgent signals
- Batch processing with configurable windows
- Target: < 1 minute end-to-end latency

Architecture:
    SignalQueue
        +-- InMemoryQueue (default)
        |   +-- Priority heaps
        +-- RedisQueue (optional)
        |   +-- Redis Streams
        +-- QueueProcessor
            +-- Worker pool

Usage:
    queue = SignalQueue()
    
    # Add signals
    await queue.enqueue(signal)
    await queue.enqueue_priority(urgent_signal)
    
    # Process signals
    async for signal in queue.stream():
        result = await process(signal)
"""

import asyncio
import heapq
import inspect
import json
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import IntEnum
from abc import ABC, abstractmethod
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Try Redis
try:
    import redis.asyncio as aioredis
    REDIS_AVAILABLE = True
except ImportError:
    try:
        import aioredis
        REDIS_AVAILABLE = True
    except ImportError:
        aioredis = None
        REDIS_AVAILABLE = False
        logger.info("Redis not available - using in-memory queue")


class SignalPriority(IntEnum):
    """Signal priority levels."""
    LOW = 3
    NORMAL = 2
    HIGH = 1
    URGENT = 0  # Lower number = higher priority


@dataclass
class QueuedSignal:
    """A signal in the queue."""
    signal_id: str
    entity_id: str
    ticker: Optional[str]
    signal_type: str
    sentiment: float
    confidence: float
    headline: str
    source: str
    priority: SignalPriority
    enqueued_at: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "entity_id": self.entity_id,
            "ticker": self.ticker,
            "signal_type": self.signal_type,
            "sentiment": self.sentiment,
            "confidence": self.confidence,
            "headline": self.headline,
            "source": self.source,
            "priority": self.priority.value,
            "enqueued_at": self.enqueued_at.isoformat(),
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QueuedSignal":
        return cls(
            signal_id=data["signal_id"],
            entity_id=data["entity_id"],
            ticker=data.get("ticker"),
            signal_type=data["signal_type"],
            sentiment=data["sentiment"],
            confidence=data["confidence"],
            headline=data["headline"],
            source=data["source"],
            priority=SignalPriority(data.get("priority", SignalPriority.NORMAL)),
            enqueued_at=datetime.fromisoformat(data["enqueued_at"]),
            metadata=data.get("metadata", {}),
        )
    
    def __lt__(self, other: "QueuedSignal") -> bool:
        """For priority queue ordering."""
        if self.priority != other.priority:
            return self.priority < other.priority
        return self.enqueued_at < other.enqueued_at


class QueueBackend(ABC):
    """Abstract queue backend."""
    
    @abstractmethod
    async def push(self, signal: QueuedSignal) -> bool:
        pass
    
    @abstractmethod
    async def pop(self, timeout: Optional[float] = None) -> Optional[QueuedSignal]:
        pass
    
    @abstractmethod
    async def peek(self) -> Optional[QueuedSignal]:
        pass
    
    @abstractmethod
    async def size(self) -> int:
        pass
    
    @abstractmethod
    async def clear(self) -> None:
        pass


class InMemoryQueue(QueueBackend):
    """
    In-memory priority queue implementation.
    
    Uses a heap for O(log n) insert/pop operations.
    Suitable for single-node operation.
    """
    
    def __init__(self, max_size: int = 10000):
        self.max_size = max_size
        self._heap: List[Tuple[int, int, QueuedSignal]] = []
        self._counter = 0  # For stable sorting
        self._lock = asyncio.Lock()
    
    async def push(self, signal: QueuedSignal) -> bool:
        async with self._lock:
            if len(self._heap) >= self.max_size:
                # Drop lowest priority if full
                if signal.priority < self._heap[-1][2].priority:
                    heapq.heappop(self._heap)
                else:
                    logger.warning("Queue full, dropping signal")
                    return False
            
            self._counter += 1
            entry = (signal.priority.value, self._counter, signal)
            heapq.heappush(self._heap, entry)
            return True
    
    async def pop(self, timeout: Optional[float] = None) -> Optional[QueuedSignal]:
        start = time.time()
        
        while True:
            async with self._lock:
                if self._heap:
                    _, _, signal = heapq.heappop(self._heap)
                    return signal
            
            if timeout is not None:
                if time.time() - start >= timeout:
                    return None
            
            await asyncio.sleep(0.01)  # Small sleep to avoid busy-wait
    
    async def peek(self) -> Optional[QueuedSignal]:
        async with self._lock:
            if self._heap:
                return self._heap[0][2]
            return None
    
    async def size(self) -> int:
        async with self._lock:
            return len(self._heap)
    
    async def clear(self) -> None:
        async with self._lock:
            self._heap.clear()
            self._counter = 0


class RedisQueue(QueueBackend):
    """
    Redis-backed queue using Redis Streams.
    
    Features:
    - Distributed processing
    - Persistence
    - Consumer groups for parallel processing
    """
    
    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        stream_name: str = "briefai:signals",
        consumer_group: str = "signal_processors",
        consumer_name: Optional[str] = None,
    ):
        self.redis_url = redis_url
        self.stream_name = stream_name
        self.consumer_group = consumer_group
        self.consumer_name = consumer_name or f"consumer_{uuid.uuid4().hex[:8]}"
        
        self._redis: Optional[aioredis.Redis] = None
        self._initialized = False
    
    async def _ensure_connection(self) -> None:
        if self._redis is None:
            self._redis = aioredis.from_url(self.redis_url)
        
        if not self._initialized:
            try:
                await self._redis.xgroup_create(
                    self.stream_name,
                    self.consumer_group,
                    id="0",
                    mkstream=True
                )
            except Exception as e:
                if "BUSYGROUP" not in str(e):
                    raise
            self._initialized = True
    
    async def push(self, signal: QueuedSignal) -> bool:
        await self._ensure_connection()
        
        try:
            data = signal.to_dict()
            data["_json"] = json.dumps(data)
            
            await self._redis.xadd(
                self.stream_name,
                {"data": data["_json"]},
                maxlen=10000,
            )
            return True
        except Exception as e:
            logger.error(f"Redis push error: {e}")
            return False
    
    async def pop(self, timeout: Optional[float] = None) -> Optional[QueuedSignal]:
        await self._ensure_connection()
        
        try:
            block_ms = int(timeout * 1000) if timeout else 0
            
            result = await self._redis.xreadgroup(
                groupname=self.consumer_group,
                consumername=self.consumer_name,
                streams={self.stream_name: ">"},
                count=1,
                block=block_ms,
            )
            
            if result:
                stream_name, messages = result[0]
                msg_id, msg_data = messages[0]
                
                # Acknowledge the message
                await self._redis.xack(
                    self.stream_name,
                    self.consumer_group,
                    msg_id
                )
                
                data = json.loads(msg_data[b"data"])
                return QueuedSignal.from_dict(data)
            
            return None
            
        except Exception as e:
            logger.error(f"Redis pop error: {e}")
            return None
    
    async def peek(self) -> Optional[QueuedSignal]:
        await self._ensure_connection()
        
        try:
            result = await self._redis.xrange(
                self.stream_name,
                count=1,
            )
            
            if result:
                msg_id, msg_data = result[0]
                data = json.loads(msg_data[b"data"])
                return QueuedSignal.from_dict(data)
            
            return None
            
        except Exception as e:
            logger.error(f"Redis peek error: {e}")
            return None
    
    async def size(self) -> int:
        await self._ensure_connection()
        
        try:
            return await self._redis.xlen(self.stream_name)
        except Exception as e:
            logger.error(f"Redis size error: {e}")
            return 0
    
    async def clear(self) -> None:
        await self._ensure_connection()
        
        try:
            await self._redis.delete(self.stream_name)
            self._initialized = False
        except Exception as e:
            logger.error(f"Redis clear error: {e}")
    
    async def close(self) -> None:
        if self._redis:
            await self._redis.close()
            self._redis = None


class SignalQueue:
    """
    Main signal queue interface.
    
    Provides:
    - Priority-based queuing
    - Streaming interface
    - Batch processing
    - Metrics tracking
    """
    
    def __init__(
        self,
        backend: Optional[QueueBackend] = None,
        use_redis: bool = False,
        redis_url: str = "redis://localhost:6379",
    ):
        if backend:
            self._backend = backend
        elif use_redis and REDIS_AVAILABLE:
            self._backend = RedisQueue(redis_url=redis_url)
            logger.info("Using Redis queue backend")
        else:
            self._backend = InMemoryQueue()
            logger.info("Using in-memory queue backend")
        
        # Metrics
        self._metrics = {
            "enqueued": 0,
            "processed": 0,
            "dropped": 0,
            "avg_wait_ms": 0,
            "wait_times": [],
        }
        
        self._running = False
    
    @property
    def metrics(self) -> Dict[str, Any]:
        return {
            **self._metrics,
            "queue_size": asyncio.create_task(self._backend.size()),
        }
    
    async def enqueue(
        self,
        entity_id: str,
        headline: str,
        source: str,
        signal_type: str = "news",
        sentiment: float = 5.0,
        confidence: float = 0.5,
        ticker: Optional[str] = None,
        priority: SignalPriority = SignalPriority.NORMAL,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """
        Add a signal to the queue.
        
        Returns signal_id if successful.
        """
        signal = QueuedSignal(
            signal_id=f"sig_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}",
            entity_id=entity_id,
            ticker=ticker,
            signal_type=signal_type,
            sentiment=sentiment,
            confidence=confidence,
            headline=headline,
            source=source,
            priority=priority,
            enqueued_at=datetime.now(),
            metadata=metadata or {},
        )
        
        success = await self._backend.push(signal)
        
        if success:
            self._metrics["enqueued"] += 1
            logger.debug(f"Enqueued signal: {signal.signal_id}")
            return signal.signal_id
        else:
            self._metrics["dropped"] += 1
            return None
    
    async def enqueue_priority(
        self,
        entity_id: str,
        headline: str,
        source: str,
        **kwargs,
    ) -> Optional[str]:
        """Enqueue with HIGH priority."""
        return await self.enqueue(
            entity_id=entity_id,
            headline=headline,
            source=source,
            priority=SignalPriority.HIGH,
            **kwargs,
        )
    
    async def enqueue_urgent(
        self,
        entity_id: str,
        headline: str,
        source: str,
        **kwargs,
    ) -> Optional[str]:
        """Enqueue with URGENT priority."""
        return await self.enqueue(
            entity_id=entity_id,
            headline=headline,
            source=source,
            priority=SignalPriority.URGENT,
            **kwargs,
        )
    
    async def dequeue(self, timeout: Optional[float] = None) -> Optional[QueuedSignal]:
        """Get next signal from queue."""
        signal = await self._backend.pop(timeout=timeout)
        
        if signal:
            # Track wait time
            wait_ms = (datetime.now() - signal.enqueued_at).total_seconds() * 1000
            self._metrics["wait_times"].append(wait_ms)
            if len(self._metrics["wait_times"]) > 1000:
                self._metrics["wait_times"] = self._metrics["wait_times"][-500:]
            self._metrics["avg_wait_ms"] = sum(self._metrics["wait_times"]) / len(self._metrics["wait_times"])
            self._metrics["processed"] += 1
        
        return signal
    
    async def peek(self) -> Optional[QueuedSignal]:
        """Look at next signal without removing it."""
        return await self._backend.peek()
    
    async def size(self) -> int:
        """Get current queue size."""
        return await self._backend.size()
    
    async def stream(
        self,
        batch_size: int = 1,
        batch_timeout: float = 1.0,
    ) -> AsyncIterator[List[QueuedSignal]]:
        """
        Stream signals from the queue.
        
        Yields batches of signals for processing.
        
        Args:
            batch_size: Max signals per batch
            batch_timeout: Max seconds to wait for full batch
        """
        self._running = True
        
        while self._running:
            batch = []
            deadline = time.time() + batch_timeout
            
            while len(batch) < batch_size and time.time() < deadline:
                remaining = deadline - time.time()
                signal = await self.dequeue(timeout=max(0.1, remaining))
                
                if signal:
                    batch.append(signal)
            
            if batch:
                yield batch
            else:
                await asyncio.sleep(0.1)  # Prevent tight loop
    
    async def stream_single(self) -> AsyncIterator[QueuedSignal]:
        """Stream individual signals."""
        async for batch in self.stream(batch_size=1):
            for signal in batch:
                yield signal
    
    def stop(self) -> None:
        """Stop streaming."""
        self._running = False
    
    async def clear(self) -> None:
        """Clear all signals from queue."""
        await self._backend.clear()
        self._metrics = {
            "enqueued": 0,
            "processed": 0,
            "dropped": 0,
            "avg_wait_ms": 0,
            "wait_times": [],
        }


class QueueProcessor:
    """
    Processes signals from the queue.
    
    Features:
    - Configurable worker count
    - Automatic retry
    - Dead letter queue for failed signals
    """
    
    def __init__(
        self,
        queue: SignalQueue,
        process_fn: Callable[[QueuedSignal], Any],
        workers: int = 4,
        max_retries: int = 3,
    ):
        self.queue = queue
        self.process_fn = process_fn
        self.workers = workers
        self.max_retries = max_retries
        
        self._running = False
        self._tasks: List[asyncio.Task] = []
        self._dead_letters: List[QueuedSignal] = []
        
        # Metrics
        self._processed = 0
        self._failed = 0
        self._processing_times: List[float] = []
    
    @property
    def metrics(self) -> Dict[str, Any]:
        avg_time = sum(self._processing_times) / len(self._processing_times) if self._processing_times else 0
        return {
            "processed": self._processed,
            "failed": self._failed,
            "dead_letters": len(self._dead_letters),
            "avg_processing_ms": avg_time,
        }
    
    async def start(self) -> None:
        """Start processing workers."""
        self._running = True
        
        for i in range(self.workers):
            task = asyncio.create_task(self._worker_loop(i))
            self._tasks.append(task)
        
        logger.info(f"Started {self.workers} queue processors")
    
    async def stop(self) -> None:
        """Stop all workers."""
        self._running = False
        self.queue.stop()
        
        for task in self._tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        self._tasks.clear()
        logger.info("Queue processors stopped")
    
    async def _worker_loop(self, worker_id: int) -> None:
        """Worker processing loop."""
        logger.debug(f"Worker {worker_id} started")
        
        async for signal in self.queue.stream_single():
            if not self._running:
                break
            
            start_time = time.time()
            success = False
            retries = 0
            
            while retries <= self.max_retries and not success:
                try:
                    if inspect.iscoroutinefunction(self.process_fn):
                        await self.process_fn(signal)
                    else:
                        self.process_fn(signal)
                    success = True
                except Exception as e:
                    retries += 1
                    logger.warning(f"Worker {worker_id} retry {retries}: {e}")
                    if retries <= self.max_retries:
                        await asyncio.sleep(0.1 * retries)  # Backoff
            
            processing_ms = (time.time() - start_time) * 1000
            self._processing_times.append(processing_ms)
            if len(self._processing_times) > 1000:
                self._processing_times = self._processing_times[-500:]
            
            if success:
                self._processed += 1
            else:
                self._failed += 1
                self._dead_letters.append(signal)
                logger.error(f"Signal {signal.signal_id} failed after {retries} retries")


# =============================================================================
# Integration with RealtimeFeed
# =============================================================================

class StreamingPipeline:
    """
    Complete streaming pipeline.
    
    Connects signal sources to processing and output.
    Target: < 1 minute news-to-signal latency.
    """
    
    def __init__(
        self,
        use_redis: bool = False,
        redis_url: str = "redis://localhost:6379",
    ):
        self.queue = SignalQueue(use_redis=use_redis, redis_url=redis_url)
        self.processor: Optional[QueueProcessor] = None
        
        self._signal_handlers: List[Callable] = []
        self._running = False
    
    def on_processed(self, handler: Callable[[QueuedSignal], None]) -> None:
        """Register a handler for processed signals."""
        self._signal_handlers.append(handler)
    
    async def start(
        self,
        workers: int = 4,
    ) -> None:
        """Start the pipeline."""
        self._running = True
        
        async def process_signal(signal: QueuedSignal):
            for handler in self._signal_handlers:
                if inspect.iscoroutinefunction(handler):
                    await handler(signal)
                else:
                    handler(signal)
        
        self.processor = QueueProcessor(
            queue=self.queue,
            process_fn=process_signal,
            workers=workers,
        )
        
        await self.processor.start()
        logger.info("Streaming pipeline started")
    
    async def stop(self) -> None:
        """Stop the pipeline."""
        self._running = False
        
        if self.processor:
            await self.processor.stop()
        
        logger.info("Streaming pipeline stopped")
    
    async def ingest(
        self,
        entity_id: str,
        headline: str,
        source: str,
        **kwargs,
    ) -> Optional[str]:
        """Ingest a new signal into the pipeline."""
        return await self.queue.enqueue(
            entity_id=entity_id,
            headline=headline,
            source=source,
            **kwargs,
        )
    
    @property
    def metrics(self) -> Dict[str, Any]:
        return {
            "queue": self.queue.metrics,
            "processor": self.processor.metrics if self.processor else {},
        }


# =============================================================================
# Demo
# =============================================================================

async def demo():
    """Demonstrate signal queue functionality."""
    print("=" * 60)
    print("Signal Queue Demo")
    print("=" * 60)
    
    # Create pipeline
    pipeline = StreamingPipeline()
    
    processed_signals = []
    
    def on_signal(signal: QueuedSignal):
        processed_signals.append(signal)
        print(f"  Processed: {signal.entity_id} | {signal.headline[:40]}... | wait: {(datetime.now() - signal.enqueued_at).total_seconds()*1000:.1f}ms")
    
    pipeline.on_processed(on_signal)
    
    # Start pipeline
    await pipeline.start(workers=2)
    
    print("\nIngesting signals...")
    
    # Ingest test signals
    test_signals = [
        ("nvidia", "NVIDIA announces record Q4 earnings", "Bloomberg"),
        ("meta", "Meta AI research breakthrough", "Reuters"),
        ("microsoft", "Microsoft Azure AI growth accelerates", "WSJ"),
        ("google", "Google Gemini 2.0 announced", "TechCrunch"),
        ("amd", "AMD MI400 GPU challenges NVIDIA", "Wired"),
    ]
    
    for entity, headline, source in test_signals:
        await pipeline.ingest(
            entity_id=entity,
            headline=headline,
            source=source,
            sentiment=7.0,
        )
        await asyncio.sleep(0.1)  # Stagger ingestion
    
    # Add an urgent signal
    await pipeline.queue.enqueue_urgent(
        entity_id="nvidia",
        headline="BREAKING: NVIDIA stock halted on major announcement",
        source="NYSE",
        sentiment=5.0,
    )
    
    print("\nWaiting for processing...")
    await asyncio.sleep(2)
    
    # Print metrics
    print(f"\n{'='*60}")
    print("Metrics:")
    metrics = pipeline.metrics
    print(f"  Enqueued: {metrics['queue']['enqueued']}")
    print(f"  Processed: {metrics['processor']['processed']}")
    print(f"  Avg wait: {metrics['queue']['avg_wait_ms']:.2f}ms")
    print(f"  Avg processing: {metrics['processor']['avg_processing_ms']:.2f}ms")
    
    await pipeline.stop()
    print("\nPipeline stopped.")


if __name__ == "__main__":
    asyncio.run(demo())
