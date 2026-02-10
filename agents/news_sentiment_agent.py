"""
News & Social Sentiment Agent (社交媒体/新闻分析)

Gathers and analyzes recent news, social media sentiment, and rumors
about specific entities using existing briefAI scrapers and data.
"""

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from agents.base import AgentCard, AgentInput, AgentOutput, BaseAgent


SYSTEM_PROMPT = """你是一位专业的舆情分析师。根据提供的新闻和社交媒体数据，分析实体的舆情状况。

分析维度：
1. **新闻热度**：近期提及频率、关注度趋势
2. **情绪分析**：正面/负面/中性新闻占比
3. **关键事件**：可能影响股价的重要新闻/传闻
4. **社交热度**：社交媒体讨论量、情绪倾向
5. **传闻追踪**：未经证实但广泛传播的信息

输出格式 JSON：
{
  "entity": "实体名称",
  "news_volume": {"7d": 0, "30d": 0},
  "sentiment": {"positive": 0, "negative": 0, "neutral": 0},
  "key_events": [
    {"title": "事件标题", "source": "来源", "date": "日期", "impact": "high|medium|low", "sentiment": "positive|negative|neutral"}
  ],
  "rumors": ["传闻1", "传闻2"],
  "social_buzz": "社交媒体热度描述",
  "sentiment_score": 0-100,
  "narrative": "当前主要叙事/话题",
  "risk_signals": ["风险信号1"]
}"""


class NewsSentimentAgent(BaseAgent):
    """
    News and social media sentiment analysis.

    Data sources:
    - trend_radar.db: entity mentions, news articles
    - Social media scrapers: Reddit, HackerNews, etc.
    - News pipeline cached articles
    """

    def __init__(self, llm_client=None, db_path: str = "data/trend_radar.db"):
        super().__init__(llm_client)
        self.db_path = Path(db_path)

    @property
    def card(self) -> AgentCard:
        return AgentCard(
            agent_id="sentiment",
            name="新闻/社交媒体分析",
            description="分析新闻舆情与社交媒体情绪：新闻热度、情绪倾向、关键事件、传闻追踪",
            input_schema={"entity_name": "str (公司名/实体名)"},
            output_schema={"sentiment_score": "int", "key_events": "list", "narrative": "str"},
            capabilities=["sentiment_analysis", "news_monitoring", "social_media", "rumor_tracking"],
            model_task="deep_research",
        )

    async def run(self, input: AgentInput) -> AgentOutput:
        query = input.context.get("query", input.entity_name)
        entity = input.entity_name

        signals = self._gather_sentiment_data(entity)

        try:
            prompt = f"分析以下实体的舆情：\n\n查询: {query}\n\n舆情数据:\n{json.dumps(signals, ensure_ascii=False, indent=2)}"
            result = self._query_llm(prompt=prompt, system_prompt=SYSTEM_PROMPT, max_tokens=4096, temperature=0.3)
            return AgentOutput(agent_id="sentiment", status="completed", data=result)
        except Exception as e:
            logger.error(f"Sentiment analysis failed: {e}")
            return AgentOutput(agent_id="sentiment", status="completed", data={"raw_signals": signals, "error": str(e)})

    def _gather_sentiment_data(self, entity: str) -> Dict[str, Any]:
        """Gather news and social sentiment data."""
        signals = {"entity": entity, "data_sources": []}

        # Entity name variants for search
        variants = self._get_entity_variants(entity)

        # 1. Query trend_radar.db for entity mentions
        self._query_trend_radar(variants, signals)

        # 2. Check cached pipeline articles
        self._check_pipeline_cache(variants, signals)

        # 3. Check social media signals
        self._check_social_signals(variants, signals)

        return signals

    def _get_entity_variants(self, entity: str) -> List[str]:
        """Get name variants for broader search."""
        VARIANTS = {
            "寒武纪": ["寒武纪", "Cambricon", "688256"],
            "海光": ["海光信息", "Hygon", "688041"],
            "科大讯飞": ["科大讯飞", "iFlytek", "002230"],
            "商汤": ["商汤", "SenseTime", "0020.HK"],
            "地平线": ["地平线", "Horizon Robotics", "688356"],
            "deepseek": ["DeepSeek", "深度求索"],
        }
        entity_lower = entity.lower()
        for key, vars in VARIANTS.items():
            if key.lower() in entity_lower or entity_lower in key.lower():
                return vars
        return [entity]

    def _query_trend_radar(self, variants: List[str], signals: Dict[str, Any]):
        """Query trend_radar.db for entity mentions."""
        if not self.db_path.exists():
            return

        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            # Check if entity_mentions table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='entity_mentions'")
            if not cursor.fetchone():
                conn.close()
                return

            # Get mention counts
            placeholders = " OR ".join(["entity_name LIKE ?" for _ in variants])
            params = [f"%{v}%" for v in variants]

            # 7-day mentions
            cursor.execute(f"""
                SELECT COUNT(*), AVG(relevance_score)
                FROM entity_mentions
                WHERE ({placeholders})
                AND mentioned_at > datetime('now', '-7 days')
            """, params)
            row_7d = cursor.fetchone()

            # 30-day mentions
            cursor.execute(f"""
                SELECT COUNT(*), AVG(relevance_score)
                FROM entity_mentions
                WHERE ({placeholders})
                AND mentioned_at > datetime('now', '-30 days')
            """, params)
            row_30d = cursor.fetchone()

            signals["mention_counts"] = {
                "7d": row_7d[0] if row_7d else 0,
                "30d": row_30d[0] if row_30d else 0,
                "avg_relevance_7d": round(row_7d[1] or 0, 2) if row_7d else 0,
            }

            # Get recent mention titles/sources
            cursor.execute(f"""
                SELECT entity_name, article_title, source, mentioned_at, relevance_score
                FROM entity_mentions
                WHERE ({placeholders})
                AND mentioned_at > datetime('now', '-7 days')
                ORDER BY mentioned_at DESC
                LIMIT 10
            """, params)
            recent = cursor.fetchall()
            if recent:
                signals["recent_mentions"] = [
                    {
                        "title": row[1],
                        "source": row[2],
                        "date": row[3],
                        "relevance": row[4],
                    }
                    for row in recent
                ]
                signals["data_sources"].append("trend_radar_mentions")

            conn.close()
        except Exception as e:
            logger.debug(f"Trend radar query failed: {e}")

    def _check_pipeline_cache(self, variants: List[str], signals: Dict[str, Any]):
        """Check cached pipeline articles for entity mentions."""
        cache_dir = Path("data/cache/pipeline_contexts")
        if not cache_dir.exists():
            return

        try:
            articles_found = []
            for cache_file in sorted(cache_dir.glob("*.json"), reverse=True)[:5]:
                with open(cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for article in data.get("articles", []):
                    title = article.get("title", "")
                    content = article.get("content", "")
                    for variant in variants:
                        if variant.lower() in (title + content).lower():
                            articles_found.append({
                                "title": title,
                                "source": article.get("source", ""),
                                "score": article.get("weighted_score", 0),
                                "date": article.get("published_date", ""),
                            })
                            break

            if articles_found:
                signals["pipeline_articles"] = articles_found[:10]
                signals["data_sources"].append("pipeline_cache")
        except Exception as e:
            logger.debug(f"Pipeline cache check failed: {e}")

    def _check_social_signals(self, variants: List[str], signals: Dict[str, Any]):
        """Check social media signal files."""
        signal_dir = Path("data/alternative_signals")
        if not signal_dir.exists():
            return

        try:
            # Check most recent social sentiment file
            social_files = sorted(signal_dir.glob("social_sentiment_*.json"), reverse=True)
            if social_files:
                with open(social_files[0], "r", encoding="utf-8") as f:
                    data = json.load(f)

                mentions = []
                for post in data.get("posts", data.get("signals", [])):
                    title = str(post.get("title", "") or post.get("name", ""))
                    for variant in variants:
                        if variant.lower() in title.lower():
                            mentions.append({
                                "platform": post.get("platform", ""),
                                "title": title[:200],
                                "score": post.get("score", 0),
                                "comments": post.get("num_comments", 0),
                            })
                            break

                if mentions:
                    signals["social_mentions"] = mentions[:10]
                    signals["data_sources"].append("social_media")
        except Exception as e:
            logger.debug(f"Social signals check failed: {e}")
