"""Close positions that hit take-profit using yfinance prices."""
import json
from datetime import date
from pathlib import Path

TRADING_DIR = Path(__file__).parent
PORTFOLIO_FILE = TRADING_DIR / "portfolio.json"
TRADE_LOG = TRADING_DIR / "trades.jsonl"
DAILY_PNL = TRADING_DIR / "daily_pnl.jsonl"

import yfinance as yf

# Load portfolio
with open(PORTFOLIO_FILE) as f:
    portfolio = json.load(f)

to_close = []
for ticker, pos in list(portfolio["positions"].items()):
    h = yf.Ticker(ticker).history(period="1d")
    if h.empty:
        print(f"  {ticker}: no price data, skipping")
        continue
    price = float(h["Close"].iloc[-1])
    entry = pos["entry_price"]
    pnl_pct = (price - entry) / entry
    pnl = (price - entry) * pos["shares"]
    hold_days = (date.today() - date.fromisoformat(pos["entry_date"])).days

    reason = None
    if price >= pos["take_profit"]:
        reason = f"TAKE_PROFIT ({pnl_pct:.1%})"
    elif price <= pos["stop_loss"]:
        reason = f"STOP_LOSS ({pnl_pct:.1%})"
    elif hold_days >= 5:
        reason = f"MAX_HOLD ({hold_days}d, {pnl_pct:.1%})"

    if reason:
        to_close.append((ticker, price, pnl, pnl_pct, hold_days, reason))
        print(f"  CLOSE {ticker}: ${entry:.2f} -> ${price:.2f} ({pnl_pct:+.1%}) PnL=${pnl:+.2f} [{reason}]")
    else:
        print(f"  HOLD  {ticker}: ${entry:.2f} -> ${price:.2f} ({pnl_pct:+.1%})")

if not to_close:
    print("\nNo exits triggered.")
else:
    for ticker, price, pnl, pnl_pct, hold_days, reason in to_close:
        pos = portfolio["positions"].pop(ticker)
        portfolio["cash"] += price * pos["shares"]
        portfolio["total_pnl"] += pnl
        if pnl > 0:
            portfolio["winning_trades"] += 1
        else:
            portfolio["losing_trades"] += 1

        trade = {
            "action": "CLOSE",
            "ticker": ticker,
            "price": round(price, 2),
            "shares": pos["shares"],
            "entry_price": pos["entry_price"],
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct * 100, 2),
            "reason": reason,
            "hold_days": hold_days,
            "date": date.today().isoformat(),
        }
        with open(TRADE_LOG, "a") as f:
            f.write(json.dumps(trade) + "\n")

    # Save portfolio
    portfolio["last_updated"] = date.today().isoformat()
    with open(PORTFOLIO_FILE, "w") as f:
        json.dump(portfolio, f, indent=2)

    # Log daily PnL
    nav = portfolio["cash"] + sum(
        pos["entry_price"] * pos["shares"] for pos in portfolio["positions"].values()
    )
    pnl_entry = {
        "date": date.today().isoformat(),
        "nav": round(nav, 2),
        "cash": round(portfolio["cash"], 2),
        "positions": len(portfolio["positions"]),
        "total_pnl": round(portfolio["total_pnl"], 2),
        "total_trades": portfolio["total_trades"],
        "win_rate": round(portfolio["winning_trades"] / max(1, portfolio["winning_trades"] + portfolio["losing_trades"]) * 100, 1),
        "exits": len(to_close),
    }
    with open(DAILY_PNL, "a") as f:
        f.write(json.dumps(pnl_entry) + "\n")

    print(f"\nClosed {len(to_close)} positions.")
    print(f"Total PnL: ${portfolio['total_pnl']:+.2f}")
    print(f"Win rate: {pnl_entry['win_rate']}%")
    print(f"Cash: ${portfolio['cash']:.2f}")
    print(f"NAV: ${nav:.2f}")
