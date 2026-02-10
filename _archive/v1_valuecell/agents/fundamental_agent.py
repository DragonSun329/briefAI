"""
A-Share Fundamental Analysis Agent (基本面分析)

Analyzes financials, announcements, earnings, and corporate actions
for Chinese A-share companies using AKShare and public data.
"""

import json
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from loguru import logger

from agents.base import AgentCard, AgentInput, AgentOutput, BaseAgent


SYSTEM_PROMPT = """你是一位专业的A股基本面分析师。根据提供的数据，分析公司的基本面状况。

分析维度：
1. **财务健康**：营收增长、净利润、毛利率、资产负债率
2. **估值水平**：市盈率PE、市净率PB、与行业对比
3. **最新公告**：重大事项、业绩预告、股东变动
4. **研发投入**：研发费用占比（AI公司尤其重要）
5. **风险提示**：业绩亏损、商誉减值、质押风险等

输出格式 JSON：
{
  "entity": "公司名称",
  "ticker": "股票代码",
  "financial_summary": "财务概况描述",
  "valuation": {"pe": 0, "pb": 0, "market_cap": 0, "sector_avg_pe": 0},
  "recent_announcements": ["公告1", "公告2"],
  "earnings_trend": "业绩趋势描述",
  "fundamental_score": 0-100,
  "key_risks": ["风险1", "风险2"],
  "investment_thesis": "投资逻辑总结"
}"""


class FundamentalAnalysisAgent(BaseAgent):
    """
    A-share fundamental analysis — financials, announcements, valuation.

    Data sources:
    - AKShare: financial statements, announcements, PE/PB data
    """

    def __init__(self, llm_client=None):
        super().__init__(llm_client)

    @property
    def card(self) -> AgentCard:
        return AgentCard(
            agent_id="fundamental",
            name="A股基本面分析",
            description="分析A股基本面：财务数据、估值水平、最新公告、业绩趋势、风险提示",
            input_schema={"entity_name": "str (公司名或股票代码)"},
            output_schema={"fundamental_score": "int", "valuation": "dict", "key_risks": "list"},
            capabilities=["fundamental_analysis", "financial_data", "announcements", "a_share"],
            model_task="deep_research",
        )

    async def run(self, input: AgentInput) -> AgentOutput:
        query = input.context.get("query", input.entity_name)
        entity = input.entity_name

        ticker = self._resolve_ticker(entity)
        signals = self._gather_fundamental_data(ticker or entity)

        try:
            prompt = f"分析以下公司的基本面：\n\n查询: {query}\n\n基本面数据:\n{json.dumps(signals, ensure_ascii=False, indent=2)}"
            result = self._query_llm(prompt=prompt, system_prompt=SYSTEM_PROMPT, max_tokens=4096, temperature=0.2)
            return AgentOutput(agent_id="fundamental", status="completed", data=result)
        except Exception as e:
            logger.error(f"Fundamental analysis failed: {e}")
            return AgentOutput(agent_id="fundamental", status="completed", data={"raw_signals": signals, "error": str(e)})

    def _resolve_ticker(self, entity: str) -> Optional[str]:
        from agents.technical_agent import TechnicalAnalysisAgent
        return TechnicalAnalysisAgent()._resolve_ticker(entity)

    def _gather_fundamental_data(self, ticker_or_name: str) -> Dict[str, Any]:
        signals = {"entity": ticker_or_name, "data_sources": []}
        code = ticker_or_name.replace(".SS", "").replace(".SZ", "")

        if not (code.isdigit() and len(code) == 6):
            return signals

        try:
            import akshare as ak

            # Financial indicators
            try:
                df = ak.stock_financial_abstract_ths(symbol=code, indicator="按年度")
                if df is not None and not df.empty:
                    recent = df.head(4)  # Last 4 periods
                    signals["financials"] = []
                    for _, row in recent.iterrows():
                        signals["financials"].append({
                            "period": str(row.iloc[0]) if len(row) > 0 else "",
                            "revenue": str(row.iloc[2]) if len(row) > 2 else "",
                            "net_profit": str(row.iloc[4]) if len(row) > 4 else "",
                            "gross_margin": str(row.iloc[6]) if len(row) > 6 else "",
                        })
                    signals["data_sources"].append("akshare_financials")
            except Exception as e:
                logger.debug(f"AKShare financials failed: {e}")

            # Individual stock info (PE, PB, etc.) — use fast endpoint
            try:
                df_info = ak.stock_individual_info_em(symbol=code)
                if df_info is not None and not df_info.empty:
                    info = dict(zip(df_info.iloc[:, 0], df_info.iloc[:, 1]))
                    signals["valuation"] = {k: str(v) for k, v in info.items()}
                    signals["data_sources"].append("akshare_valuation")
            except Exception as e:
                logger.debug(f"AKShare valuation failed: {e}")

            # Recent announcements
            try:
                df_news = ak.stock_notice_report(symbol=code)
                if df_news is not None and not df_news.empty:
                    recent_news = df_news.head(5)
                    signals["announcements"] = [
                        {
                            "date": str(row.iloc[0]) if len(row) > 0 else "",
                            "title": str(row.iloc[2]) if len(row) > 2 else str(row.iloc[1]),
                        }
                        for _, row in recent_news.iterrows()
                    ]
                    signals["data_sources"].append("akshare_announcements")
            except Exception as e:
                logger.debug(f"AKShare announcements failed: {e}")

        except ImportError:
            logger.warning("AKShare not installed")
        except Exception as e:
            logger.warning(f"AKShare fundamental data failed: {e}")

        return signals
