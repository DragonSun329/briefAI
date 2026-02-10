#!/usr/bin/env python3
"""
Portfolio Tracker for briefAI.

Track your positions and compare against briefAI signals.
Identify alignment and divergence between holdings and intelligence.
"""

import json
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from loguru import logger


@dataclass
class Position:
    """A portfolio position."""
    symbol: str
    entity_name: str
    shares: float
    avg_cost: float
    current_price: Optional[float] = None
    market_value: Optional[float] = None
    gain_loss: Optional[float] = None
    gain_loss_pct: Optional[float] = None
    
    # briefAI signal alignment
    media_score: Optional[float] = None
    technical_score: Optional[float] = None
    momentum_7d: Optional[float] = None
    signal_alignment: Optional[str] = None  # aligned, divergent, neutral


@dataclass
class PortfolioAnalysis:
    """Portfolio analysis results."""
    total_value: float
    total_cost: float
    total_gain_loss: float
    total_gain_loss_pct: float
    positions: List[Position]
    aligned_positions: int
    divergent_positions: int
    signal_score: float  # Overall portfolio signal health


class PortfolioTracker:
    """Track and analyze portfolio vs briefAI signals."""
    
    def __init__(self, portfolio_path: str = "config/portfolio.json"):
        self.portfolio_path = Path(portfolio_path)
        self.signals_db = Path("data/signals.db")
        self.portfolio: Dict = {}
        self._load_portfolio()
    
    def _load_portfolio(self):
        """Load portfolio from config."""
        if self.portfolio_path.exists():
            with open(self.portfolio_path, encoding="utf-8") as f:
                self.portfolio = json.load(f)
        else:
            self.portfolio = {"positions": [], "cash": 0}
    
    def save_portfolio(self):
        """Save portfolio to config."""
        self.portfolio_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.portfolio_path, "w", encoding="utf-8") as f:
            json.dump(self.portfolio, f, indent=2)
    
    def add_position(self, symbol: str, entity_name: str, shares: float, avg_cost: float):
        """Add or update a position."""
        # Check if position exists
        for pos in self.portfolio.get("positions", []):
            if pos["symbol"].upper() == symbol.upper():
                # Update existing
                total_shares = pos["shares"] + shares
                total_cost = (pos["shares"] * pos["avg_cost"]) + (shares * avg_cost)
                pos["shares"] = total_shares
                pos["avg_cost"] = total_cost / total_shares if total_shares > 0 else 0
                self.save_portfolio()
                return
        
        # Add new
        self.portfolio.setdefault("positions", []).append({
            "symbol": symbol.upper(),
            "entity_name": entity_name,
            "shares": shares,
            "avg_cost": avg_cost,
            "added_at": datetime.now().isoformat()
        })
        self.save_portfolio()
    
    def remove_position(self, symbol: str):
        """Remove a position."""
        self.portfolio["positions"] = [
            p for p in self.portfolio.get("positions", [])
            if p["symbol"].upper() != symbol.upper()
        ]
        self.save_portfolio()
    
    def get_signal_data(self, entity_name: str) -> Dict:
        """Get latest signal data for an entity."""
        if not self.signals_db.exists():
            return {}
        
        conn = sqlite3.connect(self.signals_db)
        cur = conn.cursor()
        
        # Get latest profile
        cur.execute("""
            SELECT media_score, technical_score, financial_score,
                   momentum_7d, momentum_30d, composite_score
            FROM signal_profiles
            WHERE LOWER(entity_name) = LOWER(?)
            ORDER BY created_at DESC
            LIMIT 1
        """, (entity_name,))
        
        row = cur.fetchone()
        conn.close()
        
        if row:
            return {
                "media_score": row[0],
                "technical_score": row[1],
                "financial_score": row[2],
                "momentum_7d": row[3],
                "momentum_30d": row[4],
                "composite_score": row[5]
            }
        return {}
    
    def get_current_price(self, symbol: str) -> Optional[float]:
        """Get current price for a symbol."""
        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            data = ticker.history(period="1d")
            if len(data) > 0:
                return float(data["Close"].iloc[-1])
        except Exception as e:
            logger.warning(f"Could not get price for {symbol}: {e}")
        return None
    
    def determine_alignment(self, position: Dict, signals: Dict) -> str:
        """Determine if position aligns with signals."""
        if not signals:
            return "unknown"
        
        media_score = signals.get("media_score", 5)
        momentum = signals.get("momentum_7d", 0)
        
        # Long position alignment
        if media_score >= 6 and momentum >= 0:
            return "aligned"  # Bullish signals, you're long
        elif media_score <= 4 or momentum < -10:
            return "divergent"  # Bearish signals, but you're long
        else:
            return "neutral"
    
    def analyze_portfolio(self, fetch_prices: bool = True) -> PortfolioAnalysis:
        """Analyze full portfolio against signals."""
        positions = []
        total_value = 0
        total_cost = 0
        aligned = 0
        divergent = 0
        signal_sum = 0
        signal_count = 0
        
        for pos_data in self.portfolio.get("positions", []):
            symbol = pos_data["symbol"]
            entity_name = pos_data["entity_name"]
            shares = pos_data["shares"]
            avg_cost = pos_data["avg_cost"]
            
            # Get current price
            current_price = None
            if fetch_prices:
                current_price = self.get_current_price(symbol)
            
            # Calculate values
            cost_basis = shares * avg_cost
            market_value = shares * current_price if current_price else cost_basis
            gain_loss = market_value - cost_basis
            gain_loss_pct = (gain_loss / cost_basis * 100) if cost_basis > 0 else 0
            
            # Get signals
            signals = self.get_signal_data(entity_name)
            alignment = self.determine_alignment(pos_data, signals)
            
            if alignment == "aligned":
                aligned += 1
            elif alignment == "divergent":
                divergent += 1
            
            if signals.get("composite_score"):
                signal_sum += signals["composite_score"]
                signal_count += 1
            
            position = Position(
                symbol=symbol,
                entity_name=entity_name,
                shares=shares,
                avg_cost=avg_cost,
                current_price=current_price,
                market_value=market_value,
                gain_loss=gain_loss,
                gain_loss_pct=gain_loss_pct,
                media_score=signals.get("media_score"),
                technical_score=signals.get("technical_score"),
                momentum_7d=signals.get("momentum_7d"),
                signal_alignment=alignment
            )
            positions.append(position)
            
            total_value += market_value
            total_cost += cost_basis
        
        total_gain_loss = total_value - total_cost
        total_gain_loss_pct = (total_gain_loss / total_cost * 100) if total_cost > 0 else 0
        signal_score = signal_sum / signal_count if signal_count > 0 else 5.0
        
        return PortfolioAnalysis(
            total_value=round(total_value, 2),
            total_cost=round(total_cost, 2),
            total_gain_loss=round(total_gain_loss, 2),
            total_gain_loss_pct=round(total_gain_loss_pct, 2),
            positions=positions,
            aligned_positions=aligned,
            divergent_positions=divergent,
            signal_score=round(signal_score, 2)
        )
    
    def get_recommendations(self, analysis: PortfolioAnalysis) -> List[Dict]:
        """Generate recommendations based on portfolio vs signals."""
        recommendations = []
        
        for pos in analysis.positions:
            if pos.signal_alignment == "divergent":
                recommendations.append({
                    "type": "warning",
                    "symbol": pos.symbol,
                    "entity": pos.entity_name,
                    "message": f"Position in {pos.entity_name} diverges from signals",
                    "detail": f"Media score: {pos.media_score}, Momentum: {pos.momentum_7d}%",
                    "action": "Consider reducing position or reviewing thesis"
                })
            
            if pos.momentum_7d and pos.momentum_7d < -15:
                recommendations.append({
                    "type": "alert",
                    "symbol": pos.symbol,
                    "entity": pos.entity_name,
                    "message": f"Strong negative momentum in {pos.entity_name}",
                    "detail": f"7-day momentum: {pos.momentum_7d}%",
                    "action": "Review for potential exit"
                })
            
            if pos.media_score and pos.media_score >= 8 and pos.signal_alignment == "aligned":
                recommendations.append({
                    "type": "positive",
                    "symbol": pos.symbol,
                    "entity": pos.entity_name,
                    "message": f"Strong bullish signals for {pos.entity_name}",
                    "detail": f"Media score: {pos.media_score}",
                    "action": "Position well-aligned with intelligence"
                })
        
        return recommendations
    
    def to_dict(self, analysis: PortfolioAnalysis) -> Dict:
        """Convert analysis to dictionary."""
        return {
            "total_value": analysis.total_value,
            "total_cost": analysis.total_cost,
            "total_gain_loss": analysis.total_gain_loss,
            "total_gain_loss_pct": analysis.total_gain_loss_pct,
            "aligned_positions": analysis.aligned_positions,
            "divergent_positions": analysis.divergent_positions,
            "signal_score": analysis.signal_score,
            "positions": [asdict(p) for p in analysis.positions]
        }


def main():
    """Demo the portfolio tracker."""
    tracker = PortfolioTracker()
    
    # Add sample positions if portfolio is empty
    if not tracker.portfolio.get("positions"):
        print("Adding sample positions...")
        tracker.add_position("NVDA", "NVIDIA", 100, 450.0)
        tracker.add_position("MSFT", "Microsoft", 50, 380.0)
        tracker.add_position("GOOGL", "Google", 30, 140.0)
        tracker.add_position("AMD", "AMD", 200, 120.0)
        tracker.add_position("META", "Meta", 75, 350.0)
    
    print("\nAnalyzing portfolio...")
    analysis = tracker.analyze_portfolio(fetch_prices=False)  # Skip price fetch for demo
    
    print(f"\n=== Portfolio Analysis ===")
    print(f"Total Cost: ${analysis.total_cost:,.2f}")
    print(f"Total Value: ${analysis.total_value:,.2f}")
    print(f"Gain/Loss: ${analysis.total_gain_loss:,.2f} ({analysis.total_gain_loss_pct:+.1f}%)")
    print(f"\nSignal Alignment:")
    print(f"  Aligned: {analysis.aligned_positions}")
    print(f"  Divergent: {analysis.divergent_positions}")
    print(f"  Portfolio Signal Score: {analysis.signal_score}/10")
    
    print(f"\n=== Positions ===")
    for pos in analysis.positions:
        print(f"  {pos.symbol} ({pos.entity_name}):")
        print(f"    Shares: {pos.shares}, Avg Cost: ${pos.avg_cost:.2f}")
        print(f"    Media Score: {pos.media_score}, Momentum: {pos.momentum_7d}%")
        print(f"    Alignment: {pos.signal_alignment}")
    
    print(f"\n=== Recommendations ===")
    recs = tracker.get_recommendations(analysis)
    for rec in recs:
        print(f"  [{rec['type'].upper()}] {rec['message']}")
        print(f"    {rec['detail']}")
        print(f"    Action: {rec['action']}")


if __name__ == "__main__":
    main()
