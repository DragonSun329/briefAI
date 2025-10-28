"""
Enhanced Report Formatter Module - CEO-Friendly Report Format

Generates reports with:
- Company and technology context (via ContextProvider)
- All merged sources displayed (no loss of attribution)
- Deep analysis (500-700 chars) focused on implications, evidence, data
- Sorted by CEO business relevance (FinTech, SaaS, Local Services, etc.)
- Removed shallow sections (risks, implications, key takeaways)
- Professional, analytical tone
"""

import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from jinja2 import Template
from loguru import logger

from utils.llm_client_enhanced import LLMClient
from modules.context_provider import ContextProvider


class ReportFormatterV2:
    """Enhanced report formatter for CEO-friendly briefings"""

    # CEO business relevance categories
    BUSINESS_CATEGORIES = {
        'fintech': ['金融科技', 'FinTech', '支付', '风控', '信贷', '理财'],
        'saas': ['SaaS', '企业应用', '协作', '生产力', '云计算'],
        'local_services': ['本地服务', '外卖', '出行', '住宿', '生活服务'],
        'enterprise_ai': ['企业AI', 'B2B', 'API', '集成', '中台'],
        'consumer': ['消费', 'C端', '内容', '社交', '电商']
    }

    def __init__(
        self,
        llm_client: LLMClient = None,
        context_provider: ContextProvider = None,
        output_dir: str = "./data/reports",
        ceo_business_context: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize enhanced report formatter

        Args:
            llm_client: LLM client instance
            context_provider: ContextProvider instance for company/tech context
            output_dir: Directory to save reports
            ceo_business_context: CEO's business focus (e.g., {'focus': 'fintech'})
        """
        self.llm_client = llm_client or LLMClient()
        self.context_provider = context_provider or ContextProvider(self.llm_client)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.ceo_business_context = ceo_business_context or {}

        logger.info("Enhanced report formatter v2 initialized")

    def generate_report(
        self,
        articles: List[Dict[str, Any]],
        report_period: str = None,
        week_id: str = None,
        title: str = "AI产业周刊"
    ) -> str:
        """
        Generate CEO-friendly report with context and merged sources

        Args:
            articles: List of evaluated and paraphrased articles
            report_period: Report period (e.g., "Oct 21-28, 2025")
            week_id: Week ID for filename
            title: Report title

        Returns:
            Path to generated report file
        """
        logger.info(f"Generating CEO-friendly report with {len(articles)} articles...")

        # Step 1: Sort articles by CEO business relevance
        articles_sorted = self._sort_by_business_relevance(articles)

        # Step 2: Prepare article data with context
        articles_enhanced = []
        for article in articles_sorted:
            enhanced_article = self._prepare_article_with_context(article)
            articles_enhanced.append(enhanced_article)

        # Step 3: Generate report metadata
        generation_time = datetime.now()
        if not report_period:
            from datetime import timedelta
            today = generation_time
            week_start = today - timedelta(days=today.weekday())
            week_end = week_start + timedelta(days=6)
            report_period = f"{week_start.strftime('%b %d')} - {week_end.strftime('%b %d, %Y')}"

        # Step 4: Render report content
        report_content = self._render_report(
            articles=articles_enhanced,
            title=title,
            report_period=report_period,
            generation_time=generation_time
        )

        # Step 5: Save report
        if not week_id:
            week_id = f"week_{generation_time.strftime('%Y_%W')}"

        report_filename = f"ceo_briefing_{week_id}_{generation_time.strftime('%Y%m%d')}.md"
        report_path = self.output_dir / report_filename

        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report_content)

        logger.info(f"Report saved to: {report_path}")
        logger.info(f"Total articles: {len(articles_enhanced)}")
        logger.info(f"Total context snippets cached: {len(self.context_provider.get_cache_stats())}")

        return str(report_path)

    def _sort_by_business_relevance(self, articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Sort articles by relevance to CEO's business

        Priority order:
        1. Articles matching CEO's primary business focus
        2. Enterprise AI (applicable to any business)
        3. Financial/cost optimization (broad impact)
        4. Other technology news
        """
        ceo_focus = self.ceo_business_context.get('focus', 'fintech').lower()

        def calculate_relevance_score(article: Dict[str, Any]) -> float:
            """Calculate relevance score for CEO"""
            score = 0.0

            title = article.get('title', '').lower()
            content = article.get('paraphrased_content', '').lower()
            category = article.get('evaluation', {}).get('recommended_category', '').lower()

            # Primary focus boost (3.0 points)
            focus_keywords = self.BUSINESS_CATEGORIES.get(ceo_focus, [])
            for keyword in focus_keywords:
                if keyword.lower() in title or keyword.lower() in category:
                    score += 3.0
                    break

            # Enterprise AI boost (2.5 points - applicable to all businesses)
            if any(k in category or k in title for k in ['enterprise', 'api', '集成', 'b2b']):
                score += 2.5

            # Cost/optimization boost (2.0 points)
            cost_keywords = ['成本', 'cost', 'efficiency', '效率', 'optimization', '优化']
            if any(k in title or k in content[:500] for k in cost_keywords):
                score += 2.0

            # Base score (weighted_score contribution)
            score += article.get('weighted_score', 0) * 0.5

            return score

        # Sort by relevance score (descending)
        articles_sorted = sorted(
            articles,
            key=lambda x: calculate_relevance_score(x),
            reverse=True
        )

        logger.debug(f"Articles sorted by CEO business relevance (focus: {ceo_focus})")
        return articles_sorted

    def _prepare_article_with_context(self, article: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prepare article with company/technology context

        Returns article enriched with:
        - all_sources list (merged sources)
        - company_contexts (company background + business model)
        - tech_contexts (technology principles)
        """
        enhanced = article.copy()

        # Extract all sources (including merged ones)
        all_sources = article.get('all_sources', [])
        if not all_sources:
            # Fallback: get from primary source
            source = article.get('source', '')
            if source:
                all_sources = [source]

        enhanced['all_sources'] = all_sources
        enhanced['sources_display'] = ' | '.join(all_sources) if all_sources else 'Unknown'

        # Get company and technology context
        article_context = self.context_provider.get_article_context(article)
        enhanced['company_contexts'] = article_context.get('companies_list', [])
        enhanced['tech_contexts'] = article_context.get('technologies_list', [])

        return enhanced

    def _render_report(
        self,
        articles: List[Dict[str, Any]],
        title: str,
        report_period: str,
        generation_time: datetime
    ) -> str:
        """Render report content in Markdown format"""

        # Build header
        header = f"""# 🤖 {title}

**报告周期**: {report_period}
**生成时间**: {generation_time.strftime('%Y年%m月%d日')}

---

## 📰 重点资讯 (按CEO业务相关性排序)

"""

        # Build articles section
        articles_section = ""
        for i, article in enumerate(articles, 1):
            article_md = self._format_article(article, i)
            articles_section += article_md + "\n\n"

        # Build footer
        footer = f"""---

**报告说明**:
- 所有合并的来源都已标明 | 分隔显示
- 公司/技术背景信息缓存以支持后续使用
- 分析内容聚焦于影响、证据和数据
- 专为CEO决策支持而准备

**下周期待继续深入洞察。** 🚀

---

*Generated by briefAI v2 - CEO-Friendly Intelligence Reports*
"""

        return header + articles_section + footer

    def _format_article(self, article: Dict[str, Any], index: int) -> str:
        """
        Format single article for report

        Format:
        ```
        ### 【Category】Article Title

        **评分**: [5D scores]

        **来源**: Source1 | Source2 | Source3 | **发布时间**: Date

        **【公司背景】**
        [Company context - 150-200 chars]

        **【技术原理】** (if applicable)
        [Tech context - 150-200 chars]

        **【关键信息】**
        [Deep analysis - 500-700 chars focused on implications, evidence, data]

        **来源链接**: [Link]
        ```
        """

        # Extract data
        title = article.get('title', 'Unknown Article')
        category = article.get('evaluation', {}).get('recommended_category', '行业动态')
        sources_display = article.get('sources_display', 'Unknown')
        published_date = article.get('published_date', 'Unknown')
        url = article.get('url', '')
        content = article.get('paraphrased_content', '')
        weighted_score = article.get('weighted_score', 0)

        # Get 5D scores if available
        scores = article.get('evaluation', {}).get('scores', {})
        score_str = self._format_5d_scores(scores, weighted_score)

        # Build article markdown
        article_md = f"""### 【{category}】{title}

**评分**: {score_str}

**来源**: {sources_display} | **发布时间**: {published_date}
"""

        # Add company contexts if available
        company_contexts = article.get('company_contexts', [])
        if company_contexts:
            article_md += "\n**【公司背景】**\n\n"
            for company in company_contexts:
                background = company.get('background', '')[:200]
                article_md += f"{background}\n\n"

        # Add tech contexts if available
        tech_contexts = article.get('tech_contexts', [])
        if tech_contexts:
            article_md += "**【技术原理】**\n\n"
            for tech in tech_contexts:
                principles = tech.get('principles', '')[:200]
                article_md += f"{principles}\n\n"

        # Add main analysis
        article_md += "**【关键信息】**\n\n"
        article_md += f"{content}\n"

        # Add source link
        if url:
            article_md += f"\n**来源链接**: [{url}]({url})\n"

        return article_md

    def _format_5d_scores(self, scores: Dict[str, float], weighted: float) -> str:
        """Format 5D scores for display"""
        market = scores.get('market_impact', 0)
        competitive = scores.get('competitive_impact', 0)
        strategic = scores.get('strategic_relevance', 0)
        operational = scores.get('operational_relevance', 0)
        credibility = scores.get('credibility', 0)

        # Generate stars (rough approximation)
        stars = min(5, int(weighted / 2)) if weighted else 3
        stars_str = "⭐" * stars + "☆" * (5 - stars)

        return f"{stars_str} **{weighted:.1f}/10** | Market {market:.0f} | Competitive {competitive:.0f} | Strategic {strategic:.0f} | Operational {operational:.0f} | Credibility {credibility:.0f}"

    def get_report_stats(self) -> Dict[str, Any]:
        """Get statistics about generated reports"""
        return {
            'output_directory': str(self.output_dir),
            'context_cache_stats': self.context_provider.get_cache_stats(),
            'business_focus': self.ceo_business_context.get('focus', 'general')
        }
