"""
briefAI Paper Trading Engine

Uses briefAI's market signals (Finnhub data, news correlations, technical analysis)
to simulate trades. Goal: prove signal quality, target $100/mo on ~$5K capital.

Strategy v1 (mean-reversion + news catalyst):
- Buy oversold stocks (RSI < 30) WITH positive news catalyst
- Sell overbought stocks (RSI > 70) WITH negative news catalyst
- Position size: equal weight, max 5 concurrent positions
- Stop loss: -5%, Take profit: +8%
- Hold period: 1-5 days (swing trading)

Data sources:
- Finnhub: real-time prices, RSI, MACD, Bollinger
- Market-news correlator: news sentiment per ticker
- briefAI signals: composite scores, momentum labels
"""

import json
import os
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from loguru import logger

TRADING_DIR = Path(__file__).parent
PORTFOLIO_FILE = TRADING_DIR / "portfolio.json"
TRADE_LOG = TRADING_DIR / "trades.jsonl"
DAILY_PNL = TRADING_DIR / "daily_pnl.jsonl"

INITIAL_CAPITAL = 5000.0
MAX_POSITIONS = 5
POSITION_SIZE_PCT = 0.18  # 18% per position (leaves ~10% cash buffer)
STOP_LOSS_PCT = -0.05     # -5%
TAKE_PROFIT_PCT = 0.08    # +8%
MAX_HOLD_DAYS = 5


@dataclass
class Position:
    ticker: str
    side: str  # "long" or "short"
    entry_price: float
    entry_date: str
    shares: float
    entry_reason: str
    signal_source: str  # which briefAI signal triggered this
    stop_loss: float = 0.0
    take_profit: float = 0.0

    def __post_init__(self):
        if self.side == "long":
            self.stop_loss = self.entry_price * (1 + STOP_LOSS_PCT)
            self.take_profit = self.entry_price * (1 + TAKE_PROFIT_PCT)
        else:
            self.stop_loss = self.entry_price * (1 - STOP_LOSS_PCT)
            self.take_profit = self.entry_price * (1 - TAKE_PROFIT_PCT)


@dataclass
class Portfolio:
    cash: float = INITIAL_CAPITAL
    positions: Dict[str, dict] = field(default_factory=dict)
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0
    created_at: str = ""
    last_updated: str = ""

    def save(self):
        self.last_updated = datetime.now().isoformat()
        with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls) -> "Portfolio":
        if PORTFOLIO_FILE.exists():
            with open(PORTFOLIO_FILE, encoding="utf-8") as f:
                data = json.load(f)
            p = cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
            return p
        p = cls(created_at=datetime.now().isoformat())
        p.save()
        return p

    @property
    def nav(self) -> float:
        """Net asset value (cash + positions at entry price)."""
        pos_value = sum(
            p["entry_price"] * p["shares"] for p in self.positions.values()
        )
        return self.cash + pos_value

    @property
    def num_positions(self) -> int:
        return len(self.positions)


def log_trade(trade: dict):
    """Append trade to JSONL log."""
    trade["timestamp"] = datetime.now().isoformat()
    with open(TRADE_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(trade, ensure_ascii=False) + "\n")


def load_finnhub_data(date_str: str = None) -> Dict[str, Any]:
    """Load today's Finnhub market data."""
    date_str = date_str or date.today().isoformat()
    path = Path(f"data/market_signals/finnhub_{date_str}.json")
    if not path.exists():
        logger.warning(f"No Finnhub data for {date_str}")
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_correlations(date_str: str = None) -> Dict[str, Any]:
    """Load today's market-news correlations."""
    date_str = date_str or date.today().isoformat()
    path = Path(f"data/market_correlations/market_news_{date_str}.json")
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def generate_signals(finnhub: dict, correlations: dict) -> List[dict]:
    """
    Generate buy/sell signals from briefAI data.

    Signal types:
    1. OVERSOLD_BOUNCE: RSI < 30 + news not catastrophic -> BUY
    2. MEAN_REVERSION: >8% drop with weak/no negative news -> BUY (dip buy)
    3. NEWS_CATALYST: Strong positive news + price already moving up -> BUY
    """
    signals = []

    # Finnhub structure: stocks[] for prices, technical_analysis{ticker: {}} for TA
    stocks = finnhub.get("stocks", [])
    ta_data = finnhub.get("technical_analysis", {})  # {ticker: {rsi_14, macd_*, ...}}

    # Build correlation lookup from BOTH finnhub.correlations and market_news_correlator
    corr_map = {}
    # Finnhub's built-in correlations
    for item in finnhub.get("correlations", []):
        ticker = item.get("ticker", "")
        if ticker:
            corr_map[ticker] = item
    # Market-news correlator (separate file, richer data)
    for item in correlations.get("correlations", []):
        ticker = item.get("ticker", "")
        if ticker and ticker not in corr_map:
            corr_map[ticker] = item

    for stock in stocks:
        ticker = stock.get("ticker", "")
        if not ticker:
            continue

        price = stock.get("current_price", 0)
        if not price or price <= 0:
            continue

        day_change = stock.get("change_pct", 0) or 0

        # Technical analysis (separate dict keyed by ticker)
        ta = ta_data.get(ticker, {})
        rsi = ta.get("rsi_14", 0) or 0
        macd_hist = ta.get("macd_histogram", 0) or 0
        bb_position = ta.get("bollinger_position", "")
        ta_signals = ta.get("signals", [])  # e.g., ["oversold", "macd_bearish"]

        # News context from correlations
        corr = corr_map.get(ticker, {})
        # Finnhub correlations use "narrative" and "news" list
        news_list = corr.get("news", corr.get("top_articles", []))
        news_count = corr.get("related_news_count", corr.get("all_match_count", 0))
        explanation = corr.get("explanation_strength", "")
        narrative = corr.get("narrative", "")

        # Determine if news is strongly negative
        news_is_bad = any(
            kw in (narrative or "").lower()
            for kw in ["plunge", "crash", "scandal", "fraud", "bankrupt", "catastroph"]
        )
        first_headline = news_list[0].get("title", "")[:80] if news_list else ""

        # Signal 1: OVERSOLD_BOUNCE
        if rsi > 0 and rsi < 30 and day_change < -3:
            if not news_is_bad:
                signals.append({
                    "ticker": ticker,
                    "action": "BUY",
                    "signal_type": "OVERSOLD_BOUNCE",
                    "price": price,
                    "rsi": rsi,
                    "day_change": day_change,
                    "confidence": min(0.9, (30 - rsi) / 30 + 0.3),
                    "reason": f"RSI {rsi:.1f} oversold, down {day_change:.1f}%",
                    "news": first_headline or "no specific catalyst",
                    "ta_signals": ta_signals,
                })

        # Signal 2: MEAN_REVERSION (big dip, weak/no news explanation)
        if day_change < -8 and explanation in ("weak", "unexplained", ""):
            if not news_is_bad:
                signals.append({
                    "ticker": ticker,
                    "action": "BUY",
                    "signal_type": "MEAN_REVERSION",
                    "price": price,
                    "rsi": rsi,
                    "day_change": day_change,
                    "confidence": min(0.8, abs(day_change) / 15),
                    "reason": f"Down {day_change:.1f}% with {explanation or 'no'} news explanation",
                    "news": first_headline or "unexplained drop",
                    "ta_signals": ta_signals,
                })

        # Signal 3: NEWS_CATALYST (positive momentum + strong news)
        if day_change > 3 and news_count >= 2 and rsi < 65:
            signals.append({
                "ticker": ticker,
                "action": "BUY",
                "signal_type": "NEWS_CATALYST",
                "price": price,
                "rsi": rsi,
                "day_change": day_change,
                "confidence": 0.6,
                "reason": f"Up {day_change:.1f}% on {news_count} news articles, RSI {rsi:.1f}",
                "news": first_headline,
                "ta_signals": ta_signals,
            })

    # Sort by confidence
    signals.sort(key=lambda x: x["confidence"], reverse=True)
    return signals


def execute_signals(portfolio: Portfolio, signals: List[dict], use_debate: bool = True) -> List[dict]:
    """Execute top signals as paper trades, optionally filtered through LLM debate."""
    executed = []
    available_slots = MAX_POSITIONS - portfolio.num_positions

    if available_slots <= 0:
        logger.info("No open slots for new positions")
        return executed

    # Filter signals already in portfolio
    new_signals = [s for s in signals if s["ticker"] not in portfolio.positions]
    if not new_signals:
        return executed

    # Multi-agent debate (Bull/Bear/Risk Manager)
    if use_debate:
        try:
            from debate_engine import debate_signals
            current_holdings = list(portfolio.positions.keys())
            debates = debate_signals(new_signals, current_holdings, max_debates=available_slots + 2)
            approved = [d for d in debates if d.approved]
            logger.info(f"[DEBATE] {len(debates)} debated, {len(approved)} approved")

            for debate in approved[:available_slots]:
                signal = next((s for s in new_signals if s["ticker"] == debate.ticker), None)
                if not signal:
                    continue

                position_value = portfolio.cash * debate.position_size_pct
                if position_value < 100:
                    continue

                shares = position_value / signal["price"]
                pos = Position(
                    ticker=debate.ticker,
                    side="long",
                    entry_price=signal["price"],
                    entry_date=date.today().isoformat(),
                    shares=round(shares, 4),
                    entry_reason=debate.reasoning or signal["reason"],
                    signal_source=signal["signal_type"],
                )
                # Override stop/take from debate
                pos.stop_loss = signal["price"] * (1 + debate.stop_loss_pct)
                pos.take_profit = signal["price"] * (1 + debate.take_profit_pct)

                portfolio.positions[debate.ticker] = asdict(pos)
                portfolio.cash -= position_value
                portfolio.total_trades += 1

                trade = {
                    "action": "OPEN",
                    "ticker": debate.ticker,
                    "side": "long",
                    "price": signal["price"],
                    "shares": pos.shares,
                    "value": round(position_value, 2),
                    "signal_type": signal["signal_type"],
                    "reason": debate.reasoning,
                    "confidence": debate.confidence,
                    "debate_bull": debate.bull_case[:100],
                    "debate_bear": debate.bear_case[:100],
                    "debate_decision": debate.decision,
                }
                log_trade(trade)
                executed.append(trade)
                logger.info(f"OPENED {debate.ticker}: {pos.shares:.2f} shares @ ${signal['price']:.2f} (debate conf={debate.confidence:.2f})")
            return executed

        except Exception as e:
            logger.warning(f"Debate engine failed ({e}), falling back to direct execution")

    # Fallback: direct execution without debate
    for signal in new_signals[:available_slots]:
        ticker = signal["ticker"]
        position_value = portfolio.cash * POSITION_SIZE_PCT
        if position_value < 100:
            logger.warning(f"Insufficient cash for {ticker}")
            continue

        shares = position_value / signal["price"]
        pos = Position(
            ticker=ticker,
            side="long",
            entry_price=signal["price"],
            entry_date=date.today().isoformat(),
            shares=round(shares, 4),
            entry_reason=signal["reason"],
            signal_source=signal["signal_type"],
        )

        portfolio.positions[ticker] = asdict(pos)
        portfolio.cash -= position_value
        portfolio.total_trades += 1

        trade = {
            "action": "OPEN",
            "ticker": ticker,
            "side": "long",
            "price": signal["price"],
            "shares": pos.shares,
            "value": round(position_value, 2),
            "signal_type": signal["signal_type"],
            "reason": signal["reason"],
            "confidence": signal["confidence"],
        }
        log_trade(trade)
        executed.append(trade)
        logger.info(f"OPENED {ticker}: {pos.shares:.2f} shares @ ${signal['price']:.2f} ({signal['signal_type']})")

    return executed


def check_exits(portfolio: Portfolio, finnhub: dict) -> List[dict]:
    """Check stop-loss, take-profit, and max hold for existing positions."""
    exits = []
    stocks = finnhub.get("stocks", finnhub.get("data", []))
    if isinstance(stocks, dict):
        stocks = list(stocks.values())
    price_map = {}
    for s in stocks:
        t = s.get("ticker", s.get("symbol", ""))
        p = s.get("current_price", s.get("price", 0))
        if t and p:
            price_map[t] = p

    today = date.today().isoformat()
    to_close = []

    for ticker, pos in portfolio.positions.items():
        current_price = price_map.get(ticker)
        if not current_price:
            continue

        entry_price = pos["entry_price"]
        pnl_pct = (current_price - entry_price) / entry_price
        hold_days = (date.today() - date.fromisoformat(pos["entry_date"])).days

        exit_reason = None
        if current_price <= pos["stop_loss"]:
            exit_reason = f"STOP_LOSS ({pnl_pct:.1%})"
        elif current_price >= pos["take_profit"]:
            exit_reason = f"TAKE_PROFIT ({pnl_pct:.1%})"
        elif hold_days >= MAX_HOLD_DAYS:
            exit_reason = f"MAX_HOLD ({hold_days}d, {pnl_pct:.1%})"

        if exit_reason:
            pnl = (current_price - entry_price) * pos["shares"]
            to_close.append((ticker, current_price, pnl, pnl_pct, exit_reason))

    for ticker, price, pnl, pnl_pct, reason in to_close:
        pos = portfolio.positions.pop(ticker)
        portfolio.cash += price * pos["shares"]
        portfolio.total_pnl += pnl
        if pnl > 0:
            portfolio.winning_trades += 1
        else:
            portfolio.losing_trades += 1

        trade = {
            "action": "CLOSE",
            "ticker": ticker,
            "price": price,
            "shares": pos["shares"],
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct * 100, 2),
            "reason": reason,
            "hold_days": (date.today() - date.fromisoformat(pos["entry_date"])).days,
        }
        log_trade(trade)
        exits.append(trade)
        logger.info(f"CLOSED {ticker}: ${pnl:+.2f} ({pnl_pct:+.1%}) - {reason}")

    return exits


def daily_run(date_str: str = None) -> dict:
    """Run daily paper trading cycle."""
    date_str = date_str or date.today().isoformat()
    logger.info(f"=== Paper Trading: {date_str} ===")

    portfolio = Portfolio.load()
    finnhub = load_finnhub_data(date_str)
    correlations = load_correlations(date_str)

    if not finnhub:
        logger.warning("No market data available, skipping")
        return {"status": "no_data"}

    # Step 1: Check exits for existing positions
    exits = check_exits(portfolio, finnhub)

    # Step 2: Generate new signals
    signals = generate_signals(finnhub, correlations)
    logger.info(f"Generated {len(signals)} signals")
    for s in signals[:5]:
        logger.info(f"  {s['action']} {s['ticker']}: {s['reason']} (conf={s['confidence']:.2f})")

    # Step 3: Execute top signals
    new_trades = execute_signals(portfolio, signals)

    # Step 4: Save portfolio
    portfolio.save()

    # Step 5: Log daily P&L
    daily = {
        "date": date_str,
        "nav": round(portfolio.nav, 2),
        "cash": round(portfolio.cash, 2),
        "positions": portfolio.num_positions,
        "total_pnl": round(portfolio.total_pnl, 2),
        "total_trades": portfolio.total_trades,
        "win_rate": round(portfolio.winning_trades / max(1, portfolio.winning_trades + portfolio.losing_trades) * 100, 1),
        "new_trades": len(new_trades),
        "exits": len(exits),
    }
    with open(DAILY_PNL, "a", encoding="utf-8") as f:
        f.write(json.dumps(daily, ensure_ascii=False) + "\n")

    logger.info(f"NAV: ${daily['nav']:.2f} | P&L: ${daily['total_pnl']:+.2f} | Positions: {daily['positions']}/{MAX_POSITIONS}")
    return daily


def show_portfolio():
    """Display current portfolio status."""
    p = Portfolio.load()
    print(f"{'='*50}")
    print(f"Paper Trading Portfolio")
    print(f"{'='*50}")
    print(f"Cash:       ${p.cash:,.2f}")
    print(f"Positions:  {p.num_positions}/{MAX_POSITIONS}")
    print(f"Total P&L:  ${p.total_pnl:+,.2f}")
    print(f"Trades:     {p.total_trades} ({p.winning_trades}W / {p.losing_trades}L)")
    if p.winning_trades + p.losing_trades > 0:
        wr = p.winning_trades / (p.winning_trades + p.losing_trades) * 100
        print(f"Win Rate:   {wr:.1f}%")
    print(f"{'='*50}")
    for ticker, pos in p.positions.items():
        print(f"  {ticker}: {pos['shares']:.2f} shares @ ${pos['entry_price']:.2f} ({pos['signal_source']})")
    print()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "status":
        show_portfolio()
    else:
        os.chdir(str(Path(__file__).parent.parent))  # cd to briefAI root
        result = daily_run()
        print(json.dumps(result, indent=2))
