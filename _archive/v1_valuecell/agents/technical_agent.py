"""
A-Share Technical Analysis Agent (技术面分析)

Analyzes stock price action, volume, fund flows, and technical indicators
for Chinese A-share and HK-listed stocks using AKShare.
"""

import json
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from loguru import logger

from agents.base import AgentCard, AgentInput, AgentOutput, BaseAgent


SYSTEM_PROMPT = """你是一位专业的A股技术分析师。根据提供的市场数据，分析股票的技术面状况。

分析维度：
1. **价格走势**：近期涨跌幅、关键价位（支撑/阻力）
2. **成交量**：量价配合、放量/缩量特征
3. **资金流向**：主力资金净流入/流出、大单方向
4. **技术指标**：均线排列、MACD、RSI等信号
5. **异动分析**：是否存在异常波动、龙虎榜数据

输出格式 JSON：
{
  "entity": "公司名称",
  "ticker": "股票代码",
  "price_action": "价格走势描述",
  "volume_analysis": "成交量分析",
  "fund_flow": "资金流向描述",
  "technical_signals": ["信号1", "信号2"],
  "key_levels": {"support": 0, "resistance": 0},
  "technical_score": 0-100,
  "short_term_outlook": "短期展望",
  "risk_factors": ["风险1", "风险2"]
}"""


class TechnicalAnalysisAgent(BaseAgent):
    """
    A-share technical analysis — price action, volume, fund flows, indicators.

    Data sources:
    - AKShare: real-time quotes, historical OHLCV, fund flow, 龙虎榜
    - yfinance: fallback for HK/US-listed Chinese companies
    """

    def __init__(self, llm_client=None):
        super().__init__(llm_client)

    @property
    def card(self) -> AgentCard:
        return AgentCard(
            agent_id="technical",
            name="A股技术面分析",
            description="分析A股/港股技术面：价格走势、成交量、资金流向、技术指标、龙虎榜异动",
            input_schema={"entity_name": "str (公司名或股票代码)"},
            output_schema={"technical_score": "int", "price_action": "str", "fund_flow": "str"},
            capabilities=["technical_analysis", "price_action", "fund_flow", "a_share"],
            model_task="deep_research",
        )

    async def run(self, input: AgentInput) -> AgentOutput:
        query = input.context.get("query", input.entity_name)
        entity = input.entity_name

        # Try to resolve ticker
        ticker = self._resolve_ticker(entity)
        signals = self._gather_technical_data(ticker or entity)

        # LLM analysis
        try:
            prompt = f"分析以下股票的技术面：\n\n查询: {query}\n\n技术数据:\n{json.dumps(signals, ensure_ascii=False, indent=2)}"
            result = self._query_llm(
                prompt=prompt,
                system_prompt=SYSTEM_PROMPT,
                max_tokens=4096,
                temperature=0.2,
            )
            return AgentOutput(agent_id="technical", status="completed", data=result)
        except Exception as e:
            logger.error(f"Technical analysis failed: {e}")
            return AgentOutput(
                agent_id="technical", status="completed",
                data={"raw_signals": signals, "error": str(e), "entity": entity},
            )

    def _resolve_ticker(self, entity: str) -> Optional[str]:
        """Resolve company name to ticker symbol."""
        # Common A-share AI companies
        TICKER_MAP = {
            "寒武纪": "688256", "cambricon": "688256",
            "地平线": "688356", "horizon": "688356",
            "海光信息": "688041", "海光": "688041",
            "寒武紀": "688256",
            "中芯国际": "688981", "smic": "688981",
            "科大讯飞": "002230", "iflytek": "002230",
            "商汤": "0020.HK", "sensetime": "0020.HK",
            "百度": "BIDU", "baidu": "BIDU",
            "阿里巴巴": "BABA", "alibaba": "BABA",
            "腾讯": "0700.HK", "tencent": "0700.HK",
        }
        entity_lower = entity.lower().strip()
        for name, ticker in TICKER_MAP.items():
            if name in entity_lower or entity_lower in name:
                return ticker
        # If it looks like a ticker already, return as-is
        if entity.replace(".", "").replace("-", "").isdigit() or "." in entity:
            return entity
        return None

    def _gather_technical_data(self, ticker_or_name: str) -> Dict[str, Any]:
        """Gather technical data from AKShare."""
        signals = {"entity": ticker_or_name, "data_sources": []}

        ticker = ticker_or_name
        # Determine if A-share (6-digit number)
        is_ashare = ticker.replace(".", "").isdigit() and len(ticker.replace(".", "").replace("SS", "").replace("SZ", "")) == 6

        if is_ashare:
            self._gather_akshare_data(ticker, signals)
        else:
            self._gather_yfinance_data(ticker, signals)

        return signals

    def _gather_akshare_data(self, ticker: str, signals: Dict[str, Any]):
        """Gather A-share data via AKShare."""
        # Clean ticker (remove .SS/.SZ suffix)
        code = ticker.replace(".SS", "").replace(".SZ", "")

        try:
            import akshare as ak

            # Real-time quote (use individual stock endpoint — much faster than full market)
            try:
                market = "sh" if code.startswith("6") else "sz"
                symbol = f"{market}{code}"
                df = ak.stock_bid_ask_em(symbol=symbol)
                if df is not None and not df.empty:
                    # Parse bid/ask table into dict
                    data_dict = dict(zip(df.iloc[:, 0], df.iloc[:, 1]))
                    signals["realtime"] = {
                        "name": str(data_dict.get("名称", "")),
                        "price": float(data_dict.get("最新", 0) or data_dict.get("现价", 0) or 0),
                        "change_pct": float(data_dict.get("涨幅", 0) or 0),
                        "volume": float(data_dict.get("总量", 0) or 0),
                        "turnover": float(data_dict.get("金额", 0) or 0),
                        "high": float(data_dict.get("最高", 0) or 0),
                        "low": float(data_dict.get("最低", 0) or 0),
                        "open": float(data_dict.get("今开", 0) or 0),
                        "prev_close": float(data_dict.get("昨收", 0) or 0),
                    }
                    signals["data_sources"].append("akshare_realtime")
            except Exception as e:
                logger.debug(f"AKShare bid_ask realtime failed: {e}")
                # Fallback: try individual info
                try:
                    df_info = ak.stock_individual_info_em(symbol=code)
                    if df_info is not None and not df_info.empty:
                        info = dict(zip(df_info.iloc[:, 0], df_info.iloc[:, 1]))
                        signals["stock_info"] = {k: str(v) for k, v in info.items()}
                        signals["data_sources"].append("akshare_info")
                except Exception as e2:
                    logger.debug(f"AKShare individual info also failed: {e2}")

            # Historical daily (last 30 days)
            try:
                end_date = datetime.now().strftime("%Y%m%d")
                start_date = (datetime.now() - timedelta(days=60)).strftime("%Y%m%d")
                df_hist = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=start_date, end_date=end_date, adjust="qfq")
                if not df_hist.empty:
                    recent = df_hist.tail(10)
                    signals["recent_history"] = [
                        {
                            "date": str(row.get("日期", "")),
                            "close": float(row.get("收盘", 0)),
                            "change_pct": float(row.get("涨跌幅", 0)),
                            "volume": float(row.get("成交量", 0)),
                            "turnover": float(row.get("成交额", 0)),
                        }
                        for _, row in recent.iterrows()
                    ]
                    signals["data_sources"].append("akshare_history")

                    # Calculate simple technicals
                    closes = df_hist["收盘"].astype(float).tolist()
                    if len(closes) >= 20:
                        signals["technicals"] = {
                            "ma5": round(sum(closes[-5:]) / 5, 2),
                            "ma10": round(sum(closes[-10:]) / 10, 2),
                            "ma20": round(sum(closes[-20:]) / 20, 2),
                            "price_vs_ma20": round((closes[-1] / (sum(closes[-20:]) / 20) - 1) * 100, 2),
                            "30d_high": round(max(closes[-30:]) if len(closes) >= 30 else max(closes), 2),
                            "30d_low": round(min(closes[-30:]) if len(closes) >= 30 else min(closes), 2),
                        }
            except Exception as e:
                logger.debug(f"AKShare history failed: {e}")

            # Fund flow (individual stock)
            try:
                df_flow = ak.stock_individual_fund_flow(stock=code, market="sh" if code.startswith("6") else "sz")
                if not df_flow.empty:
                    recent_flow = df_flow.tail(5)
                    signals["fund_flow"] = [
                        {
                            "date": str(row.iloc[0]),
                            "main_net_inflow": float(row.iloc[6]) if len(row) > 6 else 0,
                        }
                        for _, row in recent_flow.iterrows()
                    ]
                    signals["data_sources"].append("akshare_fund_flow")
            except Exception as e:
                logger.debug(f"AKShare fund flow failed: {e}")

        except ImportError:
            logger.warning("AKShare not installed")
        except Exception as e:
            logger.warning(f"AKShare data gathering failed: {e}")

    def _gather_yfinance_data(self, ticker: str, signals: Dict[str, Any]):
        """Fallback: gather data via yfinance for HK/US stocks."""
        try:
            import yfinance as yf

            stock = yf.Ticker(ticker)
            hist = stock.history(period="1mo")

            if not hist.empty:
                latest = hist.iloc[-1]
                signals["realtime"] = {
                    "price": round(float(latest["Close"]), 2),
                    "volume": int(latest["Volume"]),
                    "high": round(float(latest["High"]), 2),
                    "low": round(float(latest["Low"]), 2),
                }
                signals["recent_history"] = [
                    {
                        "date": str(idx.date()),
                        "close": round(float(row["Close"]), 2),
                        "volume": int(row["Volume"]),
                    }
                    for idx, row in hist.tail(10).iterrows()
                ]
                signals["data_sources"].append("yfinance")
        except Exception as e:
            logger.debug(f"yfinance failed: {e}")
