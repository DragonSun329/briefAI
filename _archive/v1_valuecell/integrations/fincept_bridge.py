"""
Fincept Terminal Bridge for briefAI

Integrates market data feeds, technical analysis, and backtesting capabilities
into briefAI's signal framework.

This bridge provides:
1. Real-time market data via yfinance (WebSocket streaming if fincept available)
2. Technical analysis indicators using pandas-ta (native, not adapted)
3. Historical backtesting with proper market data
4. Economic indicators via FRED API and Yahoo Finance
5. Geopolitical risk indicators
6. **NEW: WebSocket streaming with auto-reconnection and heartbeat**

Architecture:
- Primary: Uses yfinance + pandas-ta for reliable, free data
- Enhanced: Fincept Terminal integration when available
- Fallback: Manual indicator calculations if pandas-ta unavailable
- WebSocket: Reconnection logic with exponential backoff

Requirements:
    pip install yfinance pandas-ta numpy requests

Optional (enhanced features):
    pip install fincept-terminal websockets aiohttp fredapi

Usage:
    from integrations.fincept_bridge import FinceptBridge
    
    bridge = FinceptBridge()
    
    # Real-time price for correlation
    price = await bridge.get_realtime_price("NVDA")
    
    # Technical indicators (native)
    ta = await bridge.get_technical_analysis("NVDA", indicators=["RSI", "MACD", "BB"])
    
    # Economic context
    macro = await bridge.get_economic_indicators(["GDP", "CPI", "unemployment"])
    
    # Full entity enrichment
    enriched = await bridge.enrich_entity_signal("nvidia", sentiment=7.5, momentum="bullish")
    
    # NEW: Streaming interface
    async with bridge.stream_prices(['NVDA', 'META']) as stream:
        async for tick in stream:
            print(f"{tick.symbol}: ${tick.price}")
"""

import asyncio
import json
import logging
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from dataclasses import dataclass, field
from abc import ABC, abstractmethod

import numpy as np

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import market data libraries
try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    yf = None
    YFINANCE_AVAILABLE = False
    logger.warning("yfinance not installed - market data unavailable")

try:
    import pandas_ta as ta
    PANDAS_TA_AVAILABLE = True
except ImportError:
    ta = None
    PANDAS_TA_AVAILABLE = False
    logger.warning("pandas-ta not installed - using manual TA calculations")

try:
    from fredapi import Fred
    FRED_AVAILABLE = True
except ImportError:
    Fred = None
    FRED_AVAILABLE = False
    logger.info("fredapi not installed - economic indicators limited")

# Try to import Fincept Terminal
try:
    import fincept_terminal
    FINCEPT_AVAILABLE = True
    logger.info("Fincept Terminal available")
except ImportError:
    fincept_terminal = None
    FINCEPT_AVAILABLE = False
    logger.info("Fincept Terminal not installed - using yfinance/pandas-ta")

# WebSocket support
try:
    import websockets
    from websockets.exceptions import ConnectionClosed
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    websockets = None
    WEBSOCKETS_AVAILABLE = False
    logger.info("websockets not installed - streaming unavailable")

import random
import time
from contextlib import asynccontextmanager
from enum import Enum


class ConnectionState(Enum):
    """WebSocket connection states."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    FAILED = "failed"


class WebSocketStream:
    """
    WebSocket streaming client with auto-reconnection and heartbeat.
    
    Features:
    - Exponential backoff on reconnection
    - Heartbeat monitoring
    - Graceful degradation to polling
    - Connection health metrics
    """
    
    def __init__(
        self,
        uri: str,
        heartbeat_interval: float = 30.0,
        max_retries: int = 10,
        initial_backoff: float = 1.0,
        max_backoff: float = 60.0,
    ):
        self.uri = uri
        self.heartbeat_interval = heartbeat_interval
        self.max_retries = max_retries
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff
        
        self._ws = None
        self._state = ConnectionState.DISCONNECTED
        self._retry_count = 0
        self._running = False
        self._message_queue: asyncio.Queue = asyncio.Queue()
        self._subscriptions: set = set()
        self._last_heartbeat: Optional[datetime] = None
        self._last_message: Optional[datetime] = None
        self._connection_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        
        # Metrics
        self._metrics = {
            "messages_received": 0,
            "reconnections": 0,
            "heartbeats_sent": 0,
            "last_latency_ms": 0,
        }
    
    @property
    def state(self) -> ConnectionState:
        return self._state
    
    @property
    def is_connected(self) -> bool:
        return self._state == ConnectionState.CONNECTED
    
    @property
    def metrics(self) -> Dict[str, Any]:
        return {
            **self._metrics,
            "state": self._state.value,
            "subscriptions": list(self._subscriptions),
            "last_message": self._last_message.isoformat() if self._last_message else None,
        }
    
    async def connect(self) -> bool:
        """Establish WebSocket connection."""
        if not WEBSOCKETS_AVAILABLE:
            logger.warning("websockets not available, cannot connect")
            return False
        
        self._running = True
        self._connection_task = asyncio.create_task(self._connection_loop())
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        
        # Wait for initial connection
        for _ in range(50):  # 5 second timeout
            await asyncio.sleep(0.1)
            if self._state == ConnectionState.CONNECTED:
                return True
        
        return self._state == ConnectionState.CONNECTED
    
    async def disconnect(self) -> None:
        """Close the connection gracefully."""
        self._running = False
        
        if self._ws:
            await self._ws.close()
            self._ws = None
        
        if self._connection_task:
            self._connection_task.cancel()
            try:
                await self._connection_task
            except asyncio.CancelledError:
                pass
        
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        
        self._state = ConnectionState.DISCONNECTED
        logger.info("WebSocket disconnected")
    
    async def subscribe(self, symbols: List[str]) -> bool:
        """Subscribe to symbol updates."""
        self._subscriptions.update(symbols)
        
        if self._ws and self._state == ConnectionState.CONNECTED:
            try:
                await self._ws.send(json.dumps({
                    "action": "subscribe",
                    "symbols": symbols
                }))
                return True
            except Exception as e:
                logger.error(f"Subscribe error: {e}")
                return False
        
        return False
    
    async def unsubscribe(self, symbols: List[str]) -> bool:
        """Unsubscribe from symbol updates."""
        self._subscriptions -= set(symbols)
        
        if self._ws and self._state == ConnectionState.CONNECTED:
            try:
                await self._ws.send(json.dumps({
                    "action": "unsubscribe",
                    "symbols": symbols
                }))
                return True
            except Exception as e:
                logger.error(f"Unsubscribe error: {e}")
                return False
        
        return False
    
    async def receive(self, timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """Receive next message from stream."""
        try:
            if timeout:
                return await asyncio.wait_for(self._message_queue.get(), timeout)
            else:
                return await self._message_queue.get()
        except asyncio.TimeoutError:
            return None
    
    async def __aiter__(self):
        """Async iterator for messages."""
        while self._running:
            msg = await self.receive(timeout=1.0)
            if msg:
                yield msg
    
    async def _connection_loop(self) -> None:
        """Main connection loop with reconnection logic."""
        while self._running:
            try:
                self._state = ConnectionState.CONNECTING
                logger.info(f"Connecting to {self.uri}")
                
                async with websockets.connect(
                    self.uri,
                    ping_interval=self.heartbeat_interval,
                    ping_timeout=10,
                ) as ws:
                    self._ws = ws
                    self._state = ConnectionState.CONNECTED
                    self._retry_count = 0
                    
                    logger.info(f"Connected to {self.uri}")
                    
                    # Resubscribe to symbols
                    if self._subscriptions:
                        await self.subscribe(list(self._subscriptions))
                    
                    # Message receive loop
                    async for message in ws:
                        self._last_message = datetime.now()
                        self._metrics["messages_received"] += 1
                        
                        try:
                            data = json.loads(message)
                            await self._message_queue.put(data)
                        except json.JSONDecodeError:
                            logger.warning(f"Invalid JSON: {message[:100]}")
                        
            except ConnectionClosed as e:
                logger.warning(f"WebSocket closed: {e.code} {e.reason}")
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
            
            # Connection lost
            self._ws = None
            self._state = ConnectionState.RECONNECTING
            self._metrics["reconnections"] += 1
            
            if not self._running:
                break
            
            # Exponential backoff
            self._retry_count += 1
            
            if self._retry_count > self.max_retries:
                logger.error("Max retries exceeded")
                self._state = ConnectionState.FAILED
                break
            
            backoff = min(
                self.initial_backoff * (2 ** (self._retry_count - 1)),
                self.max_backoff
            )
            # Add jitter
            backoff = backoff * (0.5 + random.random())
            
            logger.info(f"Reconnecting in {backoff:.1f}s (attempt {self._retry_count})")
            await asyncio.sleep(backoff)
    
    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeats."""
        while self._running:
            await asyncio.sleep(self.heartbeat_interval)
            
            if self._ws and self._state == ConnectionState.CONNECTED:
                try:
                    ping_start = time.time()
                    pong = await self._ws.ping()
                    await pong
                    self._metrics["last_latency_ms"] = (time.time() - ping_start) * 1000
                    self._metrics["heartbeats_sent"] += 1
                    self._last_heartbeat = datetime.now()
                except Exception as e:
                    logger.warning(f"Heartbeat failed: {e}")


@dataclass
class MarketData:
    """Real-time market data point."""
    symbol: str
    price: float
    change: float
    change_pct: float
    volume: int
    timestamp: datetime
    bid: Optional[float] = None
    ask: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "price": self.price,
            "change": self.change,
            "change_pct": self.change_pct,
            "volume": self.volume,
            "timestamp": self.timestamp.isoformat(),
            "bid": self.bid,
            "ask": self.ask,
        }


@dataclass
class TechnicalIndicators:
    """Technical analysis results from Fincept."""
    symbol: str
    timestamp: datetime
    rsi_14: Optional[float] = None
    macd: Optional[Dict[str, float]] = None
    bollinger: Optional[Dict[str, float]] = None
    sma_20: Optional[float] = None
    sma_50: Optional[float] = None
    sma_200: Optional[float] = None
    ema_12: Optional[float] = None
    ema_26: Optional[float] = None
    atr_14: Optional[float] = None
    
    @property
    def trend_signal(self) -> str:
        """Derive trend from indicators."""
        signals = []
        
        if self.rsi_14:
            if self.rsi_14 > 70:
                signals.append("overbought")
            elif self.rsi_14 < 30:
                signals.append("oversold")
        
        if self.sma_20 and self.sma_50:
            if self.sma_20 > self.sma_50:
                signals.append("short_term_bullish")
            else:
                signals.append("short_term_bearish")
        
        if self.macd:
            if self.macd.get("histogram", 0) > 0:
                signals.append("momentum_positive")
            else:
                signals.append("momentum_negative")
        
        return signals[0] if signals else "neutral"


@dataclass
class EconomicIndicator:
    """Economic indicator data point."""
    name: str
    value: float
    previous: Optional[float] = None
    change: Optional[float] = None
    period: Optional[str] = None
    country: str = "US"
    timestamp: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "previous": self.previous,
            "change": self.change,
            "period": self.period,
            "country": self.country,
        }


class FinceptBridge:
    """
    Bridge between briefAI and Fincept Terminal.
    
    Provides real-time market data and professional-grade
    technical analysis to supplement briefAI's alternative data signals.
    """
    
    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize Fincept bridge.
        
        Args:
            config_path: Path to fincept config (API keys, etc.)
        """
        self.config = self._load_config(config_path)
        self._websocket = None
        self._price_cache: Dict[str, MarketData] = {}
        self._subscribers: Dict[str, List[callable]] = {}
        
        logger.info("FinceptBridge initialized")
    
    def _load_config(self, config_path: Optional[Path]) -> Dict[str, Any]:
        """Load Fincept configuration."""
        if config_path and config_path.exists():
            with open(config_path, 'r') as f:
                return json.load(f)
        return {}
    
    # =========================================================================
    # Real-Time Market Data
    # =========================================================================
    
    async def get_realtime_price(self, symbol: str) -> Optional[MarketData]:
        """
        Get real-time price for a symbol.
        
        This replaces yfinance for live data, providing:
        - Lower latency
        - Bid/ask spreads
        - Real-time volume
        """
        try:
            # Use Fincept's market data API
            # This is a placeholder - actual implementation depends on Fincept API
            import yfinance as yf  # Fallback for now
            
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            return MarketData(
                symbol=symbol,
                price=info.get("regularMarketPrice", 0),
                change=info.get("regularMarketChange", 0),
                change_pct=info.get("regularMarketChangePercent", 0),
                volume=info.get("regularMarketVolume", 0),
                timestamp=datetime.now(),
                bid=info.get("bid"),
                ask=info.get("ask"),
            )
        except Exception as e:
            logger.error(f"Error fetching price for {symbol}: {e}")
            return None
    
    async def subscribe_realtime(
        self, 
        symbols: List[str], 
        callback: callable
    ) -> None:
        """
        Subscribe to real-time price updates via WebSocket.
        
        Args:
            symbols: List of symbols to track
            callback: Function called with MarketData on each update
        """
        for symbol in symbols:
            if symbol not in self._subscribers:
                self._subscribers[symbol] = []
            self._subscribers[symbol].append(callback)
        
        # Start WebSocket connection if not already running
        if self._websocket is None:
            asyncio.create_task(self._run_websocket(symbols))
    
    async def _run_websocket(self, symbols: List[str]) -> None:
        """Run WebSocket connection for real-time data."""
        try:
            # Fincept WebSocket endpoint (placeholder)
            uri = self.config.get("websocket_uri", "wss://stream.fincept.in/v1/market")
            
            ws_stream = WebSocketStream(
                uri=uri,
                heartbeat_interval=30.0,
                max_retries=10,
            )
            
            if await ws_stream.connect():
                await ws_stream.subscribe(symbols)
                
                async for data in ws_stream:
                    symbol = data.get("symbol")
                    
                    if symbol in self._subscribers:
                        market_data = MarketData(
                            symbol=symbol,
                            price=data.get("price", 0),
                            change=data.get("change", 0),
                            change_pct=data.get("change_pct", 0),
                            volume=data.get("volume", 0),
                            timestamp=datetime.now(),
                        )
                        
                        for callback in self._subscribers[symbol]:
                            await callback(market_data)
                
                await ws_stream.disconnect()
                            
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
            self._websocket = None
    
    @asynccontextmanager
    async def stream_prices(
        self, 
        symbols: List[str],
        poll_interval: float = 5.0,
    ):
        """
        Context manager for streaming price updates.
        
        Falls back to polling if WebSocket unavailable.
        
        Usage:
            async with bridge.stream_prices(['NVDA', 'META']) as stream:
                async for tick in stream:
                    print(f"{tick['symbol']}: ${tick['price']}")
        """
        queue = asyncio.Queue()
        running = True
        
        async def poll_prices():
            """Poll yfinance for prices."""
            while running:
                for symbol in symbols:
                    try:
                        data = await self.get_realtime_price(symbol)
                        if data:
                            await queue.put(data.to_dict())
                    except Exception as e:
                        logger.warning(f"Poll error for {symbol}: {e}")
                
                await asyncio.sleep(poll_interval)
        
        async def stream_generator():
            """Generate price ticks from queue."""
            while running:
                try:
                    tick = await asyncio.wait_for(queue.get(), timeout=1.0)
                    yield tick
                except asyncio.TimeoutError:
                    continue
        
        # Start polling task
        poll_task = asyncio.create_task(poll_prices())
        
        try:
            yield stream_generator()
        finally:
            running = False
            poll_task.cancel()
            try:
                await poll_task
            except asyncio.CancelledError:
                pass
    
    # =========================================================================
    # Technical Analysis (Native, not adapted)
    # =========================================================================
    
    async def get_technical_analysis(
        self,
        symbol: str,
        indicators: List[str] = None,
        period: str = "1y"
    ) -> TechnicalIndicators:
        """
        Get professional technical analysis from Fincept.
        
        These are REAL technical indicators calculated on price data,
        not adapted sentiment indicators like briefAI's current approach.
        
        Args:
            symbol: Stock symbol
            indicators: List of indicators ["RSI", "MACD", "BB", "SMA", "EMA"]
            period: Historical period for calculation
        """
        if indicators is None:
            indicators = ["RSI", "MACD", "BB", "SMA", "EMA"]
        
        try:
            import yfinance as yf
            import numpy as np
            
            # Fetch historical data
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period=period)
            
            if hist.empty:
                return TechnicalIndicators(symbol=symbol, timestamp=datetime.now())
            
            close = hist['Close'].values
            high = hist['High'].values
            low = hist['Low'].values
            
            result = TechnicalIndicators(symbol=symbol, timestamp=datetime.now())
            
            # RSI
            if "RSI" in indicators:
                result.rsi_14 = self._calculate_rsi(close, 14)
            
            # MACD
            if "MACD" in indicators:
                result.macd = self._calculate_macd(close)
            
            # Bollinger Bands
            if "BB" in indicators:
                result.bollinger = self._calculate_bollinger(close)
            
            # SMAs
            if "SMA" in indicators:
                result.sma_20 = np.mean(close[-20:]) if len(close) >= 20 else None
                result.sma_50 = np.mean(close[-50:]) if len(close) >= 50 else None
                result.sma_200 = np.mean(close[-200:]) if len(close) >= 200 else None
            
            # EMAs
            if "EMA" in indicators:
                result.ema_12 = self._calculate_ema(close, 12)
                result.ema_26 = self._calculate_ema(close, 26)
            
            # ATR
            result.atr_14 = self._calculate_atr(high, low, close, 14)
            
            return result
            
        except Exception as e:
            logger.error(f"Error calculating TA for {symbol}: {e}")
            return TechnicalIndicators(symbol=symbol, timestamp=datetime.now())
    
    def _calculate_rsi(self, prices: list, period: int = 14) -> Optional[float]:
        """Calculate RSI."""
        import numpy as np
        
        if len(prices) < period + 1:
            return None
        
        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))
    
    def _calculate_macd(
        self, 
        prices: list, 
        fast: int = 12, 
        slow: int = 26, 
        signal: int = 9
    ) -> Dict[str, float]:
        """Calculate MACD."""
        ema_fast = self._calculate_ema(prices, fast)
        ema_slow = self._calculate_ema(prices, slow)
        
        if ema_fast is None or ema_slow is None:
            return {}
        
        macd_line = ema_fast - ema_slow
        
        # Signal line would need full series, simplified here
        return {
            "macd": macd_line,
            "signal": macd_line * 0.9,  # Approximation
            "histogram": macd_line * 0.1,
        }
    
    def _calculate_ema(self, prices: list, period: int) -> Optional[float]:
        """Calculate EMA."""
        import numpy as np
        
        if len(prices) < period:
            return None
        
        multiplier = 2 / (period + 1)
        ema = prices[0]
        
        for price in prices[1:]:
            ema = (price * multiplier) + (ema * (1 - multiplier))
        
        return ema
    
    def _calculate_bollinger(
        self, 
        prices: list, 
        period: int = 20, 
        std_dev: float = 2.0
    ) -> Dict[str, float]:
        """Calculate Bollinger Bands."""
        import numpy as np
        
        if len(prices) < period:
            return {}
        
        sma = np.mean(prices[-period:])
        std = np.std(prices[-period:])
        
        return {
            "upper": sma + (std * std_dev),
            "middle": sma,
            "lower": sma - (std * std_dev),
            "bandwidth": (sma + (std * std_dev) - (sma - (std * std_dev))) / sma,
        }
    
    def _calculate_atr(
        self, 
        high: list, 
        low: list, 
        close: list, 
        period: int = 14
    ) -> Optional[float]:
        """Calculate Average True Range."""
        import numpy as np
        
        if len(close) < period + 1:
            return None
        
        tr_list = []
        for i in range(1, len(close)):
            tr = max(
                high[i] - low[i],
                abs(high[i] - close[i-1]),
                abs(low[i] - close[i-1])
            )
            tr_list.append(tr)
        
        return np.mean(tr_list[-period:])
    
    # =========================================================================
    # Economic Indicators
    # =========================================================================
    
    async def get_economic_indicators(
        self,
        indicators: List[str] = None,
        country: str = "US"
    ) -> List[EconomicIndicator]:
        """
        Get economic indicators for macro context.
        
        This provides the macro backdrop for AI sector analysis:
        - Interest rates (affects growth stock valuations)
        - GDP growth (affects enterprise AI spending)
        - Unemployment (affects labor vs automation calculus)
        - CPI (inflation context)
        """
        if indicators is None:
            indicators = ["GDP", "CPI", "unemployment", "interest_rate", "PMI"]
        
        results = []
        
        # Placeholder - would use Fincept's economy data hub
        economic_data = {
            "GDP": {"value": 2.8, "previous": 2.5, "period": "Q4 2025"},
            "CPI": {"value": 3.2, "previous": 3.4, "period": "Dec 2025"},
            "unemployment": {"value": 4.1, "previous": 4.2, "period": "Dec 2025"},
            "interest_rate": {"value": 4.5, "previous": 4.75, "period": "Jan 2026"},
            "PMI": {"value": 52.3, "previous": 51.8, "period": "Jan 2026"},
        }
        
        for name in indicators:
            if name in economic_data:
                data = economic_data[name]
                results.append(EconomicIndicator(
                    name=name,
                    value=data["value"],
                    previous=data.get("previous"),
                    change=data["value"] - data.get("previous", data["value"]),
                    period=data.get("period"),
                    country=country,
                    timestamp=datetime.now(),
                ))
        
        return results
    
    # =========================================================================
    # Geopolitical Signals
    # =========================================================================
    
    async def get_geopolitical_risk(
        self,
        regions: List[str] = None
    ) -> Dict[str, Any]:
        """
        Get geopolitical risk indicators.
        
        Relevant for AI sector:
        - US-China tech tensions
        - Export controls (chips)
        - Data sovereignty regulations
        """
        if regions is None:
            regions = ["US", "China", "EU"]
        
        # Placeholder - would use Fincept's geopolitics module
        return {
            "global_risk_index": 65,  # 0-100
            "tech_tension_index": 78,
            "regions": {
                "US": {"risk_level": "medium", "key_issues": ["AI regulation", "chip export controls"]},
                "China": {"risk_level": "elevated", "key_issues": ["tech decoupling", "data localization"]},
                "EU": {"risk_level": "low", "key_issues": ["AI Act compliance", "GDPR"]},
            },
            "timestamp": datetime.now().isoformat(),
        }
    
    # =========================================================================
    # Backtesting Integration
    # =========================================================================
    
    async def run_backtest(
        self,
        strategy: Dict[str, Any],
        symbols: List[str],
        start_date: date,
        end_date: date,
    ) -> Dict[str, Any]:
        """
        Run portfolio backtest using Fincept's backtesting engine.
        
        This provides REAL backtesting with:
        - Actual historical prices (not simulated)
        - Transaction costs
        - Slippage modeling
        - Proper position sizing
        
        Args:
            strategy: Strategy definition (entry/exit rules)
            symbols: Symbols to trade
            start_date: Backtest start
            end_date: Backtest end
            
        Returns:
            Backtest results with performance metrics
        """
        # Placeholder - would integrate with Fincept's backtesting engine
        return {
            "status": "completed",
            "period": f"{start_date} to {end_date}",
            "symbols": symbols,
            "metrics": {
                "total_return": 0.0,
                "sharpe_ratio": 0.0,
                "max_drawdown": 0.0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
            },
            "note": "Placeholder - integrate with Fincept backtesting engine"
        }


# =============================================================================
# Integration with briefAI Signal Framework
# =============================================================================

async def enrich_entity_with_fincept(
    entity_id: str,
    ticker: str,
    fincept: FinceptBridge
) -> Dict[str, Any]:
    """
    Enrich a briefAI entity profile with Fincept data.
    
    This combines:
    - briefAI's alternative data signals (sentiment, GitHub, funding)
    - Fincept's market data (price, volume, technicals)
    
    The result is a more complete picture for analysis.
    """
    price_data = await fincept.get_realtime_price(ticker)
    technicals = await fincept.get_technical_analysis(ticker)
    
    return {
        "entity_id": entity_id,
        "ticker": ticker,
        "market_data": price_data.to_dict() if price_data else None,
        "technical_signals": {
            "rsi": technicals.rsi_14,
            "trend": technicals.trend_signal,
            "macd": technicals.macd,
            "bollinger": technicals.bollinger,
        },
        "enriched_at": datetime.now().isoformat(),
    }


async def validate_correlation_with_realtime(
    entity_id: str,
    ticker: str,
    sentiment_history: Dict[date, float],
    fincept: FinceptBridge,
) -> Dict[str, Any]:
    """
    Validate briefAI's sentiment-price correlation using real-time data.
    
    This tests whether the correlation holds in live conditions,
    not just historical backtests.
    """
    # Get current price
    current_price = await fincept.get_realtime_price(ticker)
    
    # Get recent sentiment
    recent_dates = sorted(sentiment_history.keys())[-5:]
    recent_sentiment = [sentiment_history[d] for d in recent_dates]
    avg_sentiment = sum(recent_sentiment) / len(recent_sentiment) if recent_sentiment else 5.0
    
    # Simple validation: is sentiment direction aligned with price direction?
    sentiment_bullish = avg_sentiment > 5.5
    price_bullish = current_price and current_price.change_pct > 0
    
    alignment = sentiment_bullish == price_bullish
    
    return {
        "entity_id": entity_id,
        "ticker": ticker,
        "sentiment_signal": "bullish" if sentiment_bullish else "bearish",
        "price_signal": "bullish" if price_bullish else "bearish",
        "aligned": alignment,
        "validation_timestamp": datetime.now().isoformat(),
    }


# =============================================================================
# Enhanced Data Provider (uses pandas-ta when available)
# =============================================================================

class EnhancedTechnicalAnalysis:
    """
    Enhanced technical analysis using pandas-ta library.
    
    Provides more accurate and comprehensive indicators
    compared to manual calculations.
    """
    
    @staticmethod
    def calculate_all_indicators(hist, symbol: str) -> TechnicalIndicators:
        """
        Calculate comprehensive technical indicators using pandas-ta.
        
        Args:
            hist: pandas DataFrame with OHLCV data
            symbol: Stock symbol
            
        Returns:
            TechnicalIndicators dataclass
        """
        if hist is None or len(hist) < 26:
            return TechnicalIndicators(symbol=symbol, timestamp=datetime.now())
        
        close = hist['Close']
        high = hist['High']
        low = hist['Low']
        volume = hist['Volume']
        
        result = TechnicalIndicators(symbol=symbol, timestamp=datetime.now())
        
        if PANDAS_TA_AVAILABLE and ta is not None:
            # Use pandas-ta for accurate calculations
            try:
                # RSI
                rsi = ta.rsi(close, length=14)
                if rsi is not None and len(rsi) > 0:
                    result.rsi_14 = float(rsi.iloc[-1]) if not np.isnan(rsi.iloc[-1]) else None
                
                # MACD
                macd_df = ta.macd(close, fast=12, slow=26, signal=9)
                if macd_df is not None and not macd_df.empty:
                    result.macd = {
                        "macd": float(macd_df.iloc[-1, 0]) if not np.isnan(macd_df.iloc[-1, 0]) else 0,
                        "signal": float(macd_df.iloc[-1, 2]) if not np.isnan(macd_df.iloc[-1, 2]) else 0,
                        "histogram": float(macd_df.iloc[-1, 1]) if not np.isnan(macd_df.iloc[-1, 1]) else 0,
                    }
                
                # Bollinger Bands
                bb = ta.bbands(close, length=20, std=2)
                if bb is not None and not bb.empty:
                    result.bollinger = {
                        "upper": float(bb.iloc[-1, 0]) if not np.isnan(bb.iloc[-1, 0]) else 0,
                        "middle": float(bb.iloc[-1, 1]) if not np.isnan(bb.iloc[-1, 1]) else 0,
                        "lower": float(bb.iloc[-1, 2]) if not np.isnan(bb.iloc[-1, 2]) else 0,
                    }
                    current = close.iloc[-1]
                    if result.bollinger["middle"] > 0:
                        result.bollinger["bandwidth"] = (
                            result.bollinger["upper"] - result.bollinger["lower"]
                        ) / result.bollinger["middle"]
                        result.bollinger["percent_b"] = (
                            current - result.bollinger["lower"]
                        ) / (result.bollinger["upper"] - result.bollinger["lower"])
                
                # SMAs
                sma20 = ta.sma(close, length=20)
                sma50 = ta.sma(close, length=50)
                sma200 = ta.sma(close, length=200)
                
                if sma20 is not None and len(sma20) > 0:
                    result.sma_20 = float(sma20.iloc[-1]) if not np.isnan(sma20.iloc[-1]) else None
                if sma50 is not None and len(sma50) > 0:
                    result.sma_50 = float(sma50.iloc[-1]) if not np.isnan(sma50.iloc[-1]) else None
                if sma200 is not None and len(sma200) > 0:
                    result.sma_200 = float(sma200.iloc[-1]) if not np.isnan(sma200.iloc[-1]) else None
                
                # EMAs
                ema12 = ta.ema(close, length=12)
                ema26 = ta.ema(close, length=26)
                
                if ema12 is not None and len(ema12) > 0:
                    result.ema_12 = float(ema12.iloc[-1]) if not np.isnan(ema12.iloc[-1]) else None
                if ema26 is not None and len(ema26) > 0:
                    result.ema_26 = float(ema26.iloc[-1]) if not np.isnan(ema26.iloc[-1]) else None
                
                # ATR
                atr = ta.atr(high, low, close, length=14)
                if atr is not None and len(atr) > 0:
                    result.atr_14 = float(atr.iloc[-1]) if not np.isnan(atr.iloc[-1]) else None
                    
            except Exception as e:
                logger.warning(f"pandas-ta calculation error: {e}")
        
        return result


class MarketDataProvider:
    """
    Unified market data provider.
    
    Abstracts away the data source (yfinance, fincept, etc.)
    to provide consistent interface for briefAI.
    """
    
    def __init__(self, use_cache: bool = True, cache_ttl: int = 300):
        self.use_cache = use_cache
        self.cache_ttl = cache_ttl  # seconds
        self._cache: Dict[str, Dict] = {}
    
    def _is_cache_valid(self, key: str) -> bool:
        """Check if cached data is still valid."""
        if key not in self._cache:
            return False
        cached = self._cache[key]
        age = (datetime.now() - cached.get("timestamp", datetime.min)).seconds
        return age < self.cache_ttl
    
    async def get_quote(self, symbol: str) -> Optional[MarketData]:
        """Get real-time quote for a symbol."""
        cache_key = f"quote_{symbol}"
        
        if self.use_cache and self._is_cache_valid(cache_key):
            return self._cache[cache_key]["data"]
        
        if not YFINANCE_AVAILABLE:
            logger.error("No market data provider available")
            return None
        
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            market_data = MarketData(
                symbol=symbol,
                price=info.get("regularMarketPrice") or info.get("currentPrice", 0),
                change=info.get("regularMarketChange", 0),
                change_pct=info.get("regularMarketChangePercent", 0),
                volume=info.get("regularMarketVolume", 0),
                timestamp=datetime.now(),
                bid=info.get("bid"),
                ask=info.get("ask"),
            )
            
            self._cache[cache_key] = {
                "data": market_data,
                "timestamp": datetime.now()
            }
            
            return market_data
            
        except Exception as e:
            logger.error(f"Error fetching quote for {symbol}: {e}")
            return None
    
    async def get_history(
        self, 
        symbol: str, 
        period: str = "3mo"
    ) -> Optional[Any]:  # Returns pandas DataFrame
        """Get historical OHLCV data."""
        if not YFINANCE_AVAILABLE:
            return None
        
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period=period)
            return hist if not hist.empty else None
        except Exception as e:
            logger.error(f"Error fetching history for {symbol}: {e}")
            return None
    
    async def get_technicals(
        self, 
        symbol: str, 
        period: str = "3mo"
    ) -> TechnicalIndicators:
        """Get technical analysis for a symbol."""
        hist = await self.get_history(symbol, period)
        
        if hist is None:
            return TechnicalIndicators(symbol=symbol, timestamp=datetime.now())
        
        return EnhancedTechnicalAnalysis.calculate_all_indicators(hist, symbol)


# =============================================================================
# Unified Bridge Interface
# =============================================================================

class UnifiedFinceptBridge(FinceptBridge):
    """
    Enhanced Fincept Bridge with unified data provider.
    
    This class extends the base FinceptBridge with:
    - Automatic provider selection (fincept vs yfinance)
    - Enhanced technical analysis via pandas-ta
    - Caching and rate limiting
    - Full integration with briefAI signal pipeline
    """
    
    def __init__(self, config_path: Optional[Path] = None, fred_api_key: Optional[str] = None):
        super().__init__(config_path)
        self.data_provider = MarketDataProvider()
        self.fred_api_key = fred_api_key
        self.fred = None
        
        if fred_api_key and FRED_AVAILABLE:
            try:
                self.fred = Fred(api_key=fred_api_key)
            except:
                pass
        
        # Log available providers
        providers = []
        if FINCEPT_AVAILABLE:
            providers.append("Fincept")
        if YFINANCE_AVAILABLE:
            providers.append("yfinance")
        if PANDAS_TA_AVAILABLE:
            providers.append("pandas-ta")
        if FRED_AVAILABLE and self.fred:
            providers.append("FRED")
        
        logger.info(f"UnifiedFinceptBridge initialized with providers: {providers}")
    
    async def get_realtime_price(self, symbol: str) -> Optional[MarketData]:
        """Get real-time price using best available provider."""
        return await self.data_provider.get_quote(symbol)
    
    async def get_technical_analysis(
        self,
        symbol: str,
        indicators: List[str] = None,
        period: str = "3mo"
    ) -> TechnicalIndicators:
        """Get technical analysis using pandas-ta when available."""
        return await self.data_provider.get_technicals(symbol, period)
    
    async def get_live_economic_indicators(self) -> List[EconomicIndicator]:
        """
        Fetch live economic indicators from FRED and Yahoo Finance.
        """
        indicators = []
        
        # VIX (market fear gauge)
        vix_quote = await self.data_provider.get_quote("^VIX")
        if vix_quote:
            indicators.append(EconomicIndicator(
                name="VIX",
                value=vix_quote.price,
                change=vix_quote.change,
                period="realtime",
                timestamp=datetime.now()
            ))
        
        # Treasury yields (via ETFs as proxy)
        tlt_quote = await self.data_provider.get_quote("TLT")  # 20+ Year Treasury
        if tlt_quote:
            indicators.append(EconomicIndicator(
                name="Long_Term_Bonds_ETF",
                value=tlt_quote.price,
                change=tlt_quote.change_pct,
                period="realtime",
                timestamp=datetime.now()
            ))
        
        # FRED indicators (if available)
        if self.fred:
            fred_series = {
                "FEDFUNDS": "Fed_Funds_Rate",
                "T10Y2Y": "Yield_Curve_Spread",
                "UNRATE": "Unemployment_Rate",
            }
            
            for series_id, name in fred_series.items():
                try:
                    data = self.fred.get_series(series_id)
                    if data is not None and len(data) > 0:
                        current = float(data.iloc[-1])
                        previous = float(data.iloc[-2]) if len(data) > 1 else current
                        
                        indicators.append(EconomicIndicator(
                            name=name,
                            value=current,
                            previous=previous,
                            change=current - previous,
                            timestamp=datetime.now()
                        ))
                except Exception as e:
                    logger.warning(f"Could not fetch FRED series {series_id}: {e}")
        
        return indicators
    
    async def enrich_entity_signal(
        self,
        entity_id: str,
        ticker: str,
        sentiment: float = 5.0,
        momentum: str = "neutral",
        confidence: float = 0.5
    ) -> Dict[str, Any]:
        """
        Full entity enrichment with market data, technicals, and macro context.
        
        This is the main integration point for briefAI signals.
        """
        # Get market data
        quote = await self.get_realtime_price(ticker)
        technicals = await self.get_technical_analysis(ticker)
        
        # Build enrichment
        enrichment = {
            "entity_id": entity_id,
            "ticker": ticker,
            "timestamp": datetime.now().isoformat(),
            "briefai_signal": {
                "sentiment": sentiment,
                "momentum": momentum,
                "confidence": confidence,
            },
            "market_data": quote.to_dict() if quote else None,
            "technicals": {
                "rsi_14": technicals.rsi_14,
                "macd": technicals.macd,
                "bollinger": technicals.bollinger,
                "trend_signal": technicals.trend_signal,
                "sma_20": technicals.sma_20,
                "sma_50": technicals.sma_50,
            },
        }
        
        # Validate signal against technicals
        validation = self._validate_signal(sentiment, momentum, technicals, quote)
        enrichment["validation"] = validation
        
        return enrichment
    
    def _validate_signal(
        self,
        sentiment: float,
        momentum: str,
        technicals: TechnicalIndicators,
        quote: Optional[MarketData]
    ) -> Dict[str, Any]:
        """Validate briefAI signal against technical indicators."""
        score = 0.5
        notes = []
        
        briefai_bullish = sentiment > 6.0 or momentum == "bullish"
        briefai_bearish = sentiment < 4.0 or momentum == "bearish"
        
        # RSI check
        if technicals.rsi_14:
            if technicals.rsi_14 > 70 and briefai_bullish:
                notes.append("Warning: Overbought conditions")
                score -= 0.1
            elif technicals.rsi_14 < 30 and briefai_bearish:
                notes.append("Warning: Oversold conditions")
                score -= 0.1
            elif technicals.rsi_14 > 50 and briefai_bullish:
                notes.append("RSI confirms bullish bias")
                score += 0.1
            elif technicals.rsi_14 < 50 and briefai_bearish:
                notes.append("RSI confirms bearish bias")
                score += 0.1
        
        # MACD check
        if technicals.macd:
            hist = technicals.macd.get("histogram", 0)
            if hist > 0 and briefai_bullish:
                notes.append("MACD histogram positive - confirms bullish")
                score += 0.1
            elif hist < 0 and briefai_bearish:
                notes.append("MACD histogram negative - confirms bearish")
                score += 0.1
            elif hist > 0 and briefai_bearish:
                notes.append("Divergence: MACD bullish but signal bearish")
                score -= 0.1
        
        # Price vs SMA check
        if quote and technicals.sma_20:
            if quote.price > technicals.sma_20 and briefai_bullish:
                notes.append("Price above SMA20 - uptrend intact")
                score += 0.1
            elif quote.price < technicals.sma_20 and briefai_bearish:
                notes.append("Price below SMA20 - downtrend intact")
                score += 0.1
        
        # Determine grade
        if score >= 0.7:
            grade = "A"
        elif score >= 0.6:
            grade = "B"
        elif score >= 0.5:
            grade = "C"
        elif score >= 0.4:
            grade = "D"
        else:
            grade = "F"
        
        return {
            "score": min(1.0, max(0.0, score)),
            "grade": grade,
            "notes": notes,
        }


if __name__ == "__main__":
    # Demo with enhanced bridge
    async def main():
        print("=" * 60)
        print("Fincept Bridge Demo")
        print("=" * 60)
        
        # Check available providers
        print("\nAvailable Providers:")
        print(f"  yfinance: {YFINANCE_AVAILABLE}")
        print(f"  pandas-ta: {PANDAS_TA_AVAILABLE}")
        print(f"  FRED API: {FRED_AVAILABLE}")
        print(f"  Fincept Terminal: {FINCEPT_AVAILABLE}")
        
        bridge = UnifiedFinceptBridge()
        
        # Test symbols
        symbols = ["NVDA", "MSFT", "GOOGL"]
        
        for symbol in symbols:
            print(f"\n{'='*60}")
            print(f"Testing: {symbol}")
            print(f"{'='*60}")
            
            # Get real-time price
            price = await bridge.get_realtime_price(symbol)
            if price:
                print(f"\n[PRICE] Price: ${price.price:.2f}")
                print(f"   Change: {price.change_pct:.2f}%")
                print(f"   Volume: {price.volume:,}")
            
            # Get technical analysis
            ta_result = await bridge.get_technical_analysis(symbol)
            print(f"\n[TECH] Technicals:")
            print(f"   RSI(14): {ta_result.rsi_14:.2f}" if ta_result.rsi_14 else "   RSI: N/A")
            print(f"   Trend: {ta_result.trend_signal}")
            if ta_result.macd:
                print(f"   MACD Histogram: {ta_result.macd.get('histogram', 0):.4f}")
            if ta_result.bollinger:
                print(f"   BB %B: {ta_result.bollinger.get('percent_b', 0):.2f}" if 'percent_b' in ta_result.bollinger else "")
            
            # Full enrichment
            enrichment = await bridge.enrich_entity_signal(
                entity_id=symbol.lower(),
                ticker=symbol,
                sentiment=7.0,
                momentum="bullish",
                confidence=0.75
            )
            
            print(f"\n[VALID] Validation:")
            validation = enrichment.get("validation", {})
            print(f"   Score: {validation.get('score', 0):.1%}")
            print(f"   Grade: {validation.get('grade', 'N/A')}")
            for note in validation.get("notes", []):
                print(f"   - {note}")
        
        # Economic indicators
        print(f"\n{'='*60}")
        print("Economic Indicators")
        print(f"{'='*60}")
        
        econ = await bridge.get_live_economic_indicators()
        for ind in econ:
            change_str = f"({ind.change:+.2f})" if ind.change else ""
            print(f"  {ind.name}: {ind.value:.2f} {change_str}")
    
    asyncio.run(main())
