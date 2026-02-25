"""
Multi-Agent Debate Engine for Trading Decisions

Inspired by TradingAgents + NOFX AI Debate Arena.
Three LLM agents debate each trade signal:
  1. Bull Analyst - argues FOR the trade
  2. Bear Analyst - argues AGAINST the trade  
  3. Risk Manager - makes final decision with position sizing

Uses free Gemini Flash via OpenRouter.
"""

import json
import os
import sys
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from loguru import logger

# OpenRouter config
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "google/gemini-2.0-flash-001"  # Free tier


def _load_env():
    """Load .env if key not in environment."""
    global OPENROUTER_API_KEY
    if not OPENROUTER_API_KEY:
        env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
        if os.path.exists(env_path):
            for line in open(env_path, encoding='utf-8'):
                line = line.strip()
                if line.startswith('OPENROUTER_API_KEY='):
                    OPENROUTER_API_KEY = line.split('=', 1)[1].strip().strip('"\'')
                    break


def _call_llm(system_prompt: str, user_prompt: str, max_tokens: int = 300) -> str:
    """Call OpenRouter with Gemini Flash."""
    _load_env()
    if not OPENROUTER_API_KEY:
        logger.warning("No OpenRouter API key, skipping LLM debate")
        return ""

    import httpx
    try:
        resp = httpx.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "max_tokens": max_tokens,
                "temperature": 0.3,
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        return ""


BULL_SYSTEM = """You are a Bull Analyst at a trading firm. Your job is to argue FOR buying this stock.
Be specific about catalysts, technical setup, and upside potential.
End with a conviction score: STRONG_BUY (>80% confident), BUY (60-80%), or WEAK_BUY (<60%).
Keep response under 150 words."""

BEAR_SYSTEM = """You are a Bear Analyst at a trading firm. Your job is to argue AGAINST buying this stock.
Be specific about risks, headwinds, and why the dip could continue.
End with a risk score: HIGH_RISK (avoid), MEDIUM_RISK (caution), or LOW_RISK (acceptable).
Keep response under 150 words."""

RISK_MANAGER_SYSTEM = """You are the Risk Manager at a trading firm. You've heard the Bull and Bear cases.
Make the FINAL trading decision. Consider:
- Position sizing (what % of capital)
- Stop-loss level (how tight?)
- Is the risk/reward favorable?
- Portfolio correlation (are we already exposed to this sector?)

Respond in this EXACT JSON format:
{
  "decision": "BUY" or "SKIP",
  "confidence": 0.0-1.0,
  "position_size_pct": 0.05-0.20,
  "stop_loss_pct": -0.03 to -0.08,
  "take_profit_pct": 0.05 to 0.15,
  "reasoning": "one sentence"
}"""


@dataclass
class DebateResult:
    ticker: str
    bull_case: str
    bear_case: str
    decision: str  # "BUY" or "SKIP"
    confidence: float
    position_size_pct: float
    stop_loss_pct: float
    take_profit_pct: float
    reasoning: str
    raw_risk_response: str = ""

    @property
    def approved(self) -> bool:
        return self.decision == "BUY" and self.confidence >= 0.5


def build_signal_context(signal: dict, portfolio_positions: List[str] = None) -> str:
    """Build context string for LLM agents from a trading signal."""
    lines = [
        f"Ticker: {signal['ticker']}",
        f"Current Price: ${signal['price']:.2f}",
        f"Day Change: {signal['day_change']:.1f}%",
        f"Signal Type: {signal['signal_type']}",
        f"Signal Reason: {signal['reason']}",
    ]
    if signal.get('rsi'):
        lines.append(f"RSI(14): {signal['rsi']:.1f}")
    if signal.get('news'):
        lines.append(f"News Context: {signal['news']}")
    if signal.get('ta_signals'):
        lines.append(f"Technical Signals: {', '.join(signal['ta_signals'])}")
    if portfolio_positions:
        lines.append(f"Current Portfolio: {', '.join(portfolio_positions)}")
    return "\n".join(lines)


def debate_signal(signal: dict, portfolio_positions: List[str] = None) -> DebateResult:
    """
    Run multi-agent debate on a trading signal.
    Returns DebateResult with final decision.
    """
    ticker = signal["ticker"]
    context = build_signal_context(signal, portfolio_positions)
    logger.info(f"[DEBATE] {ticker}: Starting bull/bear/risk debate...")

    # Step 1: Bull case
    bull_case = _call_llm(BULL_SYSTEM, context)
    if not bull_case:
        # LLM unavailable — fall back to original signal
        return DebateResult(
            ticker=ticker, bull_case="(LLM unavailable)", bear_case="(LLM unavailable)",
            decision="BUY", confidence=signal.get("confidence", 0.5),
            position_size_pct=0.18, stop_loss_pct=-0.05, take_profit_pct=0.08,
            reasoning="LLM debate unavailable, using original signal"
        )

    # Step 2: Bear case
    bear_case = _call_llm(BEAR_SYSTEM, context)

    # Step 3: Risk Manager decides
    risk_prompt = f"""Signal Context:
{context}

=== BULL ANALYST ===
{bull_case}

=== BEAR ANALYST ===
{bear_case}

Make your final decision. Respond in JSON only."""

    risk_response = _call_llm(RISK_MANAGER_SYSTEM, risk_prompt, max_tokens=200)
    logger.info(f"[DEBATE] {ticker} Bull: {bull_case[:60]}...")
    logger.info(f"[DEBATE] {ticker} Bear: {bear_case[:60]}...")
    logger.info(f"[DEBATE] {ticker} Risk: {risk_response[:100]}")

    # Parse risk manager JSON
    try:
        # Extract JSON from response (might have markdown wrapping)
        json_str = risk_response
        if "```" in json_str:
            json_str = json_str.split("```")[1]
            if json_str.startswith("json"):
                json_str = json_str[4:]
        decision = json.loads(json_str.strip())
    except (json.JSONDecodeError, IndexError):
        logger.warning(f"[DEBATE] {ticker}: Failed to parse risk manager response, defaulting to cautious BUY")
        decision = {
            "decision": "BUY",
            "confidence": 0.5,
            "position_size_pct": 0.10,
            "stop_loss_pct": -0.05,
            "take_profit_pct": 0.08,
            "reasoning": "Parse error, using conservative defaults",
        }

    return DebateResult(
        ticker=ticker,
        bull_case=bull_case,
        bear_case=bear_case,
        decision=decision.get("decision", "SKIP"),
        confidence=float(decision.get("confidence", 0.5)),
        position_size_pct=float(decision.get("position_size_pct", 0.15)),
        stop_loss_pct=float(decision.get("stop_loss_pct", -0.05)),
        take_profit_pct=float(decision.get("take_profit_pct", 0.08)),
        reasoning=decision.get("reasoning", ""),
        raw_risk_response=risk_response,
    )


def debate_signals(signals: List[dict], portfolio_positions: List[str] = None, max_debates: int = 5) -> List[DebateResult]:
    """Run debate on top N signals. Returns list of DebateResults."""
    results = []
    for signal in signals[:max_debates]:
        result = debate_signal(signal, portfolio_positions)
        results.append(result)
        if result.approved:
            # Add to portfolio context for subsequent debates (correlation awareness)
            if portfolio_positions is None:
                portfolio_positions = []
            portfolio_positions.append(result.ticker)
    return results


if __name__ == "__main__":
    # Test with a sample signal
    test_signal = {
        "ticker": "IBM",
        "action": "BUY",
        "signal_type": "MEAN_REVERSION",
        "price": 223.35,
        "day_change": -13.2,
        "rsi": 22.9,
        "confidence": 0.8,
        "reason": "Down -13.2% with no news explanation",
        "news": "Anthropic AI capabilities spooked legacy tech",
        "ta_signals": ["oversold", "macd_bearish", "below_lower_bb"],
    }
    result = debate_signal(test_signal, ["MDB", "NET", "SNOW"])
    print(f"\n{'='*50}")
    print(f"Ticker: {result.ticker}")
    print(f"Decision: {result.decision} (conf={result.confidence:.2f})")
    print(f"Position Size: {result.position_size_pct:.0%}")
    print(f"Stop Loss: {result.stop_loss_pct:.1%}")
    print(f"Take Profit: {result.take_profit_pct:.1%}")
    print(f"Reasoning: {result.reasoning}")
    print(f"\nBull: {result.bull_case[:200]}")
    print(f"\nBear: {result.bear_case[:200]}")
