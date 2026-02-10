"""
A-Share Sector/Industry Analysis Agent (行业/板块分析)

Monitors sector-level sentiment, peer comparisons, and industry trends
for AI-related sectors (半导体, 算力, AI应用, etc.)
"""

import json
from datetime import datetime
from typing import Any, Dict, Optional, List

from loguru import logger

from agents.base import AgentCard, AgentInput, AgentOutput, BaseAgent


SYSTEM_PROMPT = """你是一位专业的A股行业分析师。根据提供的板块数据，分析行业整体状况和个股在板块中的位置。

分析维度：
1. **板块走势**：板块整体涨跌、资金流向
2. **龙头对比**：板块内主要个股横向对比
3. **行业情绪**：市场对该板块的情绪（乐观/悲观/中性）
4. **催化剂**：近期可能影响板块的事件/政策
5. **个股定位**：目标公司在板块中的地位和表现

输出格式 JSON：
{
  "sector": "板块名称",
  "sector_performance": "板块整体表现描述",
  "sector_change_pct": 0,
  "sector_fund_flow": "板块资金流向",
  "peer_comparison": [
    {"name": "公司名", "ticker": "代码", "change_pct": 0, "pe": 0}
  ],
  "sector_sentiment": "bullish|bearish|neutral",
  "catalysts": ["催化剂1", "催化剂2"],
  "sector_score": 0-100,
  "entity_position": "目标公司在板块中的定位"
}"""


# AI-related sector mappings
SECTOR_KEYWORDS = {
    "半导体": ["semiconductor", "芯片", "半导体", "chip"],
    "算力": ["computing_power", "算力", "服务器", "GPU"],
    "人工智能": ["ai", "人工智能", "AI应用", "大模型"],
    "信创": ["信创", "国产替代", "xinchuang"],
    "机器人": ["robot", "机器人", "具身智能"],
}

SECTOR_TICKERS = {
    "半导体": ["688256", "688041", "603986", "002049", "688008", "688981"],
    "算力": ["000977", "300308", "002230", "603019", "688579"],
    "人工智能": ["002230", "688111", "300033", "002410", "300253"],
}


class SectorAnalysisAgent(BaseAgent):
    """
    Sector/industry analysis — peer comparison, sector sentiment, fund flows.

    Data sources:
    - AKShare: sector quotes, sector fund flow, peer comparison
    """

    def __init__(self, llm_client=None):
        super().__init__(llm_client)

    @property
    def card(self) -> AgentCard:
        return AgentCard(
            agent_id="sector",
            name="A股行业/板块分析",
            description="分析A股板块走势：行业情绪、板块资金流向、龙头对比、个股板块定位",
            input_schema={"entity_name": "str (公司名/板块名)"},
            output_schema={"sector_score": "int", "peer_comparison": "list", "sector_sentiment": "str"},
            capabilities=["sector_analysis", "peer_comparison", "industry_sentiment", "a_share"],
            model_task="deep_research",
        )

    async def run(self, input: AgentInput) -> AgentOutput:
        query = input.context.get("query", input.entity_name)
        entity = input.entity_name

        sector = self._identify_sector(entity)
        signals = self._gather_sector_data(sector, entity)

        try:
            prompt = f"分析以下行业/板块：\n\n查询: {query}\n\n板块数据:\n{json.dumps(signals, ensure_ascii=False, indent=2)}"
            result = self._query_llm(prompt=prompt, system_prompt=SYSTEM_PROMPT, max_tokens=4096, temperature=0.2)
            return AgentOutput(agent_id="sector", status="completed", data=result)
        except Exception as e:
            logger.error(f"Sector analysis failed: {e}")
            return AgentOutput(agent_id="sector", status="completed", data={"raw_signals": signals, "error": str(e)})

    def _identify_sector(self, entity: str) -> str:
        """Identify which sector an entity belongs to."""
        entity_lower = entity.lower()
        for sector, keywords in SECTOR_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in entity_lower:
                    return sector
        # Default mapping by company name
        COMPANY_SECTORS = {
            "寒武纪": "半导体", "海光": "半导体", "中芯国际": "半导体",
            "科大讯飞": "人工智能", "商汤": "人工智能",
            "浪潮": "算力", "中科曙光": "算力",
        }
        for name, sector in COMPANY_SECTORS.items():
            if name in entity:
                return sector
        return "人工智能"

    def _gather_sector_data(self, sector: str, entity: str) -> Dict[str, Any]:
        """Gather sector-level data."""
        signals = {"sector": sector, "entity": entity, "data_sources": []}

        try:
            import akshare as ak

            # Sector performance (概念板块)
            try:
                df_sectors = ak.stock_board_concept_name_em()
                if df_sectors is not None and not df_sectors.empty:
                    # Find matching sector
                    matched = df_sectors[df_sectors["板块名称"].str.contains(sector, na=False)]
                    if not matched.empty:
                        row = matched.iloc[0]
                        signals["sector_overview"] = {
                            "name": str(row.get("板块名称", "")),
                            "change_pct": float(row.get("涨跌幅", 0)),
                            "turnover": float(row.get("成交额", 0)),
                            "leading_stock": str(row.get("领涨股票", "")),
                            "stock_count": int(row.get("上涨家数", 0)) + int(row.get("下跌家数", 0)) if "上涨家数" in row.index else 0,
                            "up_count": int(row.get("上涨家数", 0)) if "上涨家数" in row.index else 0,
                            "down_count": int(row.get("下跌家数", 0)) if "下跌家数" in row.index else 0,
                        }
                        signals["data_sources"].append("akshare_sector")
            except Exception as e:
                logger.debug(f"AKShare sector overview failed: {e}")

            # Peer comparison — use individual stock endpoint per ticker (faster than full market scan)
            try:
                tickers = SECTOR_TICKERS.get(sector, [])
                if tickers:
                    peers = []
                    for code in tickers[:8]:  # Limit to 8 peers
                        try:
                            market = "sh" if code.startswith("6") else "sz"
                            df_bid = ak.stock_bid_ask_em(symbol=f"{market}{code}")
                            if df_bid is not None and not df_bid.empty:
                                data = dict(zip(df_bid.iloc[:, 0], df_bid.iloc[:, 1]))
                                peers.append({
                                    "name": str(data.get("名称", "")),
                                    "code": code,
                                    "price": float(data.get("最新", 0) or data.get("现价", 0) or 0),
                                    "change_pct": float(data.get("涨幅", 0) or 0),
                                })
                        except Exception:
                            continue
                    peers.sort(key=lambda x: x.get("change_pct", 0), reverse=True)
                    signals["peer_comparison"] = peers
                    signals["data_sources"].append("akshare_peers")
            except Exception as e:
                logger.debug(f"AKShare peers failed: {e}")

        except ImportError:
            logger.warning("AKShare not installed")
        except Exception as e:
            logger.warning(f"Sector data gathering failed: {e}")

        return signals
