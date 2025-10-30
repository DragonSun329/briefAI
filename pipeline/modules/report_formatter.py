"""
Report Formatter Module

Compiles evaluated and paraphrased articles into a final weekly report.
Uses Jinja2 templates and generates executive summary and key insights with Claude.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any
from jinja2 import Template
from loguru import logger
import os
from dotenv import load_dotenv

from utils.llm_client_enhanced import LLMClient
from utils.scoring_engine import ScoringEngine

load_dotenv()


class ReportFormatter:
    """Formats articles into final weekly report"""

    def __init__(
        self,
        template_path: str = "./config/report_template.md",
        llm_client: LLMClient = None,
        output_dir: str = "./data/reports",
        company_context: Dict[str, Any] = None,
        include_5d_scores: bool = True
    ):
        """
        Initialize report formatter

        Args:
            template_path: Path to Jinja2 report template
            llm_client: LLM client instance (creates new if None)
            output_dir: Directory to save reports
            company_context: Company context for tailored insights
            include_5d_scores: Whether to include 5D score breakdowns in report
        """
        self.template_path = Path(template_path)
        self.llm_client = llm_client or LLMClient()
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.company_context = company_context or {}
        self.include_5d_scores = include_5d_scores
        self.scoring_engine = ScoringEngine()

        # Load company context from categories config if not provided
        if not self.company_context:
            try:
                config_path = Path("./config/categories.json")
                if config_path.exists():
                    with open(config_path, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                        self.company_context = config.get('company_context', {})
            except Exception as e:
                logger.warning(f"Could not load company context: {e}")

        # Load template
        with open(self.template_path, 'r', encoding='utf-8') as f:
            self.template = Template(f.read())

        logger.info(f"Report formatter initialized (include_5d_scores: {include_5d_scores})")

    def generate_report(
        self,
        articles: List[Dict[str, Any]],
        categories: List[Dict[str, Any]],
        report_period: str = None,
        report_type: str = "daily",
        week_id: str = None,
        additional_readings: List[Dict[str, Any]] = None
    ) -> str:
        """
        Generate final daily or weekly report

        Args:
            articles: List of evaluated and paraphrased articles
            categories: Selected categories
            report_period: Report period string (e.g., "2024-10-24 至 2024-10-30")
            report_type: Type of report ("daily" or "weekly")
            week_id: Week ID for weekly reports (e.g., 'week_2025_43')
            additional_readings: Optional list of additional articles to link

        Returns:
            Path to generated report file
        """
        logger.info(f"Generating {report_type} report with {len(articles)} articles...")

        # Sort articles by weighted score (best first) for daily/weekly display
        articles_sorted = sorted(articles, key=lambda x: x.get('weighted_score', 0), reverse=True)

        # Generate report period if not provided
        if not report_period:
            today = datetime.now()
            if report_type == "weekly":
                year, week_num, _ = today.isocalendar()
                report_period = f"{year}年第{week_num}周"
            else:
                report_period = today.strftime("%Y年%m月%d日")

        # Calculate score statistics
        score_stats = self.scoring_engine.get_score_distribution(articles_sorted)

        # Group articles by category
        articles_by_category = self._group_by_category(articles_sorted)

        # Generate executive summary
        executive_summary = self._generate_executive_summary(articles_sorted, categories)

        # Generate key insights (only for weekly reports)
        key_insights = ""
        if report_type == "weekly":
            key_insights = self._generate_key_insights(articles_sorted)

        # Prepare metadata
        generation_timestamp = datetime.now()
        metadata = {
            'report_type': report_type,
            'generation_time': generation_timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            'generation_date': generation_timestamp.strftime("%Y-%m-%d"),
            'report_period': report_period,
            'article_date_range': self._get_article_date_range(articles_sorted),
            'focus_categories': ", ".join([cat['name'] for cat in categories]),
            'score_min': f"{score_stats['min']:.1f}",
            'score_max': f"{score_stats['max']:.1f}",
            'score_mean': f"{score_stats['mean']:.1f}",
            'total_articles_included': len(articles_sorted),
            'top_score_article': self._get_top_article_info(articles_sorted),
            'bottom_score_article': self._get_bottom_article_info(articles_sorted)
        }

        # Prepare template data
        template_data = {
            'report_period': report_period,
            'generation_time': metadata['generation_time'],
            'focus_categories': metadata['focus_categories'],
            'executive_summary': executive_summary,
            'articles_by_category': articles_by_category,
            'key_insights': key_insights,
            'total_articles_scraped': len(articles_sorted) * 5,  # Estimate
            'total_articles_included': len(articles_sorted),
            'additional_readings': additional_readings or [],
            'metadata': metadata,
            'include_5d_scores': self.include_5d_scores,
            'report_type': report_type
        }

        # Render template
        report_content = self.template.render(**template_data)

        # Add 5D score breakdown to report content if enabled
        if self.include_5d_scores:
            report_content = self._inject_5d_scores_into_content(report_content, articles_sorted)

        # Generate filename based on report type
        if report_type == "weekly":
            report_filename = f"weekly_briefing_{week_id}_{generation_timestamp.strftime('%Y%m%d')}.md"
        else:
            report_filename = f"ai_briefing_{generation_timestamp.strftime('%Y%m%d')}.md"

        report_path = self.output_dir / report_filename

        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report_content)

        logger.info(f"Report saved to: {report_path}")
        return str(report_path)

    def _group_by_category(
        self,
        articles: List[Dict[str, Any]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Group articles by recommended category"""
        grouped = {}

        for article in articles:
            # Get category from evaluation or default
            category = "其他"
            if 'evaluation' in article:
                category = article['evaluation'].get('recommended_category', '其他')

            if category not in grouped:
                grouped[category] = []

            grouped[category].append(article)

        return grouped

    def _generate_executive_summary(
        self,
        articles: List[Dict[str, Any]],
        categories: List[Dict[str, Any]]
    ) -> str:
        """Generate executive summary using Claude"""
        logger.debug("Generating executive summary...")

        # Prepare article summaries
        article_summaries = "\n\n".join([
            f"- {article['title']}: {article.get('paraphrased_content', article['content'][:200])}"
            for article in articles[:10]  # Top 10 articles
        ])

        context_info = ""
        if self.company_context:
            business = self.company_context.get('business', '')
            context_info = f"\n\n**公司背景**: {business}"

        system_prompt = f"""你是一位专业的高管简报撰写人,为CEO撰写每周AI行业概述。
{context_info}

请用简体中文撰写一段简洁的总览 (2-3句话, ~100-150字符)。

**要求**:
- 突出最重要的主题和趋势
- 专业、战略性的语气
- 聚焦"发生了什么"和"为什么重要"
- 不要罗列具体文章 - 综合主题
- 只用简体中文

**示例**:
"本周金融科技AI的焦点集中在智能风控技术的突破和数据分析能力的提升。多家公司推出了新一代信贷决策模型，精准度显著提高，同时营销投放策略也在向智能化方向发展。这些进展预示着AI在金融场景的应用正在从辅助工具转变为核心竞争力。"
"""

        user_message = f"""基于以下重点文章,撰写高管总览:

{article_summaries}

关注分类: {', '.join([cat['name'] for cat in categories])}

用简体中文撰写总览。"""

        try:
            summary = self.llm_client.chat(
                system_prompt=system_prompt,
                user_message=user_message,
                temperature=0.5
            )
            return summary.strip()

        except Exception as e:
            logger.error(f"Failed to generate executive summary: {e}")
            return "本周AI行业持续快速发展，多个领域出现重要突破和动态。"

    def _generate_key_insights(
        self,
        articles: List[Dict[str, Any]]
    ) -> str:
        """Generate key strategic insights using Claude"""
        logger.debug("Generating key insights...")

        # Prepare article data
        article_data = "\n\n".join([
            f"**{article['title']}**: {article.get('paraphrased_content', '')}"
            for article in articles[:12]
        ])

        context_info = ""
        if self.company_context:
            business = self.company_context.get('business', '')
            focus_areas = self.company_context.get('focus_areas', [])
            context_info = f"\n\n**公司背景**: {business}\n**关注领域**: {', '.join(focus_areas)}"

        system_prompt = f"""你是一位战略分析师,从AI行业新闻中识别关键洞察。
{context_info}

请用简体中文生成3-5条战略性要点。

**要求**:
- 每条洞察1-2句话
- 聚焦战略意义,不仅仅是事实陈述
- 识别模式、趋势和关联
- 专业、分析性的语气
- 使用编号列表格式
- 只用简体中文

**示例格式**:
1. **技术趋势**: 智能风控技术正在从规则引擎转向深度学习模型,更注重实时决策能力和反欺诈精准度的提升。

2. **商业化进展**: AI驱动的精准营销开始在金融场景深度应用,特别是在用户画像和投放策略优化方面取得突破。

3. **数据能力**: 数据分析平台向实时化和自动化方向发展,为信贷决策提供更快速准确的支持。
"""

        user_message = f"""基于以下文章,识别3-5条关键战略洞察:

{article_data}

用简体中文生成洞察。"""

        try:
            insights = self.llm_client.chat(
                system_prompt=system_prompt,
                user_message=user_message,
                temperature=0.6
            )
            return insights.strip()

        except Exception as e:
            logger.error(f"Failed to generate key insights: {e}")
            return "1. AI技术持续快速发展\n2. 应用场景不断拓展\n3. 监管政策逐步完善"

    def _get_article_date_range(self, articles: List[Dict[str, Any]]) -> str:
        """Get date range of articles"""
        if not articles:
            return "Unknown"

        dates = []
        for article in articles:
            pub_date = article.get('published_date', '')
            if pub_date:
                dates.append(pub_date)

        if not dates:
            return "Unknown"

        dates.sort()
        return f"{dates[0]} 至 {dates[-1]}"

    def _get_top_article_info(self, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Get info about highest scoring article"""
        if not articles:
            return {}

        top_article = articles[0]
        return {
            'title': top_article.get('title', 'Unknown'),
            'score': top_article.get('weighted_score', 0)
        }

    def _get_bottom_article_info(self, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Get info about lowest scoring article"""
        if not articles:
            return {}

        bottom_article = articles[-1]
        return {
            'title': bottom_article.get('title', 'Unknown'),
            'score': bottom_article.get('weighted_score', 0)
        }

    def _inject_5d_scores_into_content(
        self,
        content: str,
        articles: List[Dict[str, Any]]
    ) -> str:
        """
        Inject 5D score breakdowns into report content

        Args:
            content: Original report content
            articles: Articles with 5D score data

        Returns:
            Enhanced content with score breakdowns
        """
        enhanced_content = content

        # For each article, add score breakdown after the title
        for i, article in enumerate(articles):
            if i >= 15:  # Limit to 15 articles max
                break

            title = article.get('title', '')
            if not title:
                continue

            # Get score breakdown
            scores = article.get('5d_score_breakdown', {})
            if scores:
                score_str = self.scoring_engine.get_score_breakdown_str(scores)
                weighted_score = article.get('weighted_score', 0)

                # Create score line
                score_line = f"\n**综合评分**: {weighted_score:.1f}/10 | {score_str}\n"

                # Find and replace the title with title + scores
                search_str = f"\n## {title}\n"
                replacement = f"\n## {title}{score_line}"

                if search_str in enhanced_content:
                    enhanced_content = enhanced_content.replace(search_str, replacement, 1)
                else:
                    # Try without level 2 header
                    search_str = f"\n{title}\n"
                    if search_str in enhanced_content:
                        enhanced_content = enhanced_content.replace(
                            search_str,
                            f"\n{title}{score_line}",
                            1
                        )

        return enhanced_content


if __name__ == "__main__":
    # Test report formatter
    formatter = ReportFormatter()

    # Sample articles
    sample_articles = [
        {
            'title': 'OpenAI发布GPT-5',
            'url': 'https://example.com/article1',
            'source': '机器之心',
            'published_date': '2024-10-20',
            'paraphrased_content': 'OpenAI发布了GPT-5模型，在推理能力方面实现显著提升...',
            'evaluation': {
                'recommended_category': '大模型',
                'key_takeaway': 'GPT-5性能大幅提升'
            }
        }
    ]

    sample_categories = [
        {'id': 'llm', 'name': '大模型'}
    ]

    report_path = formatter.generate_report(sample_articles, sample_categories)
    print(f"Report generated: {report_path}")
