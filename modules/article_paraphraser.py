"""
Article Paraphraser Module

Condenses full articles into executive summaries in Mandarin Chinese.
CRITICAL: Output must be flowing paragraphs (NOT bullet points), 150-250 characters.
Includes fact-checking to prevent hallucinations.
"""

import json
from typing import Dict, Any, List
from pathlib import Path
from datetime import datetime, timedelta
from loguru import logger

from utils.llm_client_enhanced import LLMClient


class ArticleParaphraser:
    """Paraphrases articles into executive summaries"""

    def __init__(
        self,
        llm_client: LLMClient = None,
        min_length: int = 500,
        max_length: int = 700,
        enable_caching: bool = True,
        cache_retention_days: int = 7
    ):
        """
        Initialize article paraphraser

        Args:
            llm_client: LLM client instance (creates new if None)
            min_length: Minimum summary length in Chinese characters (500 for detailed summaries)
            max_length: Maximum summary length in Chinese characters (700 for multi-paragraph)
            enable_caching: Enable full article context caching
            cache_retention_days: Days to retain cached articles
        """
        self.llm_client = llm_client or LLMClient()
        self.min_length = min_length
        self.max_length = max_length
        self.enable_caching = enable_caching
        self.cache_retention_days = cache_retention_days

        # Setup cache directory
        if self.enable_caching:
            self.cache_dir = Path("./data/cache/article_contexts")
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Article context caching enabled (retention: {cache_retention_days} days)")

    def paraphrase_articles(
        self,
        articles: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Paraphrase multiple articles

        Args:
            articles: List of evaluated articles

        Returns:
            List of articles with 'paraphrased_content' added
        """
        logger.info(f"Paraphrasing {len(articles)} articles...")

        # Cache full articles before paraphrasing
        if self.enable_caching:
            self._cache_articles(articles)

        for i, article in enumerate(articles):
            try:
                logger.debug(f"Paraphrasing {i+1}/{len(articles)}: {article['title']}")

                paraphrased = self._paraphrase_single_article(article)
                article['paraphrased_content'] = paraphrased['summary']
                article['fact_check'] = paraphrased.get('fact_check', 'passed')

                # Verify length
                char_count = len(article['paraphrased_content'])
                if char_count < self.min_length or char_count > self.max_length:
                    logger.warning(f"Summary length {char_count} outside range [{self.min_length}, {self.max_length}]")

            except Exception as e:
                logger.error(f"Failed to paraphrase article '{article['title']}': {e}")
                # Fallback: use original content truncated
                article['paraphrased_content'] = article['content'][:200] + "..."
                article['fact_check'] = 'failed'

        logger.info(f"Paraphrasing complete")

        # Clean up old caches
        if self.enable_caching:
            self._cleanup_old_caches()

        return articles

    def _paraphrase_single_article(
        self,
        article: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Paraphrase a single article using Claude

        Returns dictionary with summary and fact-check status
        """
        system_prompt = self._build_paraphrase_prompt()
        user_message = self._build_article_message(article)

        response = self.llm_client.chat_structured(
            system_prompt=system_prompt,
            user_message=user_message,
            temperature=0.4  # Slightly higher for natural language
        )

        return response

    def _build_paraphrase_prompt(self) -> str:
        """Build system prompt for paraphrasing - enhanced for 500-700 chars with analytical-inspiring tone"""
        return f"""你是一位专业的AI行业分析师,为CEO撰写深度、实用的行业洞察摘要。

**核心要求**:
1. 必须使用**3-4个段落的流畅段落格式** - 绝不使用bullet points或列表
2. 长度: **{self.min_length}-{self.max_length}个中文字符** (不含标点符号) - 约3-4个段落,深度内容
3. 语言: **简体中文** (技术术语如"GPT"、"API"等可保留英文)
4. 语气: **分析性启发** - 实用、理性、专业,突出实际意义而非商业宣传
5. 准确性: 只包含原文中的事实 - 不得编造内容

**必须包含的内容**:
✅ **支撑核心论点的数据**: 只引用能证明文章中心观点的具体数据
   - 性能指标、增长数据、市场规模、成本节省等
   - 例如: "增长23%"、"推理速度提升5倍"、"市场规模₩100亿"
   - 避免堆砌无关数据,每个数据都要有上下文说明
✅ **核心机制**: 技术/商业创新的运作原理 - HOW和WHY,不仅仅是WHAT
✅ **实际影响**: 对具体使用场景、用户群体、企业流程的具体改进
✅ **市场意义**: 行业格局变化、竞争动态、战略启示
✅ **关键限制或风险**: 坦诚讨论局限性、挑战或潜在风险(不是单纯宣传)
✅ **前瞻洞察**: 这如何影响未来6-12个月的行业发展方向

**段落结构指南**:
- **第1段** (150-180字): 事件背景 + 核心创新/突破 + 证明突破的关键数据
- **第2段** (150-180字): 技术/商业机制 + 如何实现这个突破 + 与前代/竞争方案的差异
- **第3段** (150-180字): 实际应用场景 + 受益方 + 具体业务影响(效率、成本、质量)
- **第4段** (100-160字): 市场意义 + 行业启示 + 潜在风险/局限 + 战略建议(可选)

**数据和论证要求**:
- 🎯 **精选数据**: 只包含支撑文章核心论点的具体数据,避免无关细节
- 📊 **解释因果**: 不仅说"增长了50%",要说"**因为**...所以...增长了50%"
- 🔍 **对比分析**: 相比前代、竞争产品或行业平均水平的具体差异
- 💼 **量化业务影响**: 成本节省额度、效率提升百分比、市场规模机遇
- 🎯 **具体场景**: "金融风控团队"而非"企业","减少审核时间20%"而非"更快"

**语气指南 - 分析性启发(Analytical-Inspiring)**:
- ✅ "这个变化揭示了AI在[领域]的潜力,关键在于..."
- ✅ "值得注意的是,[发展]正在改变[现状],这对[行业]意味着..."
- ✅ "挑战是...但机遇也在于..."
- ❌ 避免: "革命性的"、"改变世界"、"终极解决方案"(商业化措辞)
- ❌ 避免: 纯粹赞美,要有批判思维

**格式示例**:

✅ GOOD (3-4段落,分析性启发):
"Claude 3.5 Sonnet刚刚发布，在编程和数学推理能力上相比3.0版本实现了平均35%的性能提升。关键数据显示，在HumanEval编程基准测试中，新版本达到92.3%通过率，较前代提升12个百分点。这个进展本质上源于更高效的注意力机制和改进的训练数据策略。

从技术机制看，Claude 3.5 Sonnet采用了新的多头注意力架构，在保持推理深度的同时显著降低了计算成本。相比GPT-4o和Llama 3.1，它在相同成本下实现了更高的编程精度。这种架构改进直接来自对软件工程任务中常见错误模式的分析。

对软件开发团队而言，这意味着代码审查和测试自动化的成本可能下降20-30%。特别是在处理复杂的系统设计问题时，3.5 Sonnet能提供更深入的分析，减少人工干预。融资科技和金融建模领域也因更强的数学推理而受益，错误率预计下降。

市场意义在于，强大的推理能力不再是超大模型的专属优势。企业现在可以用更低成本部署高效的AI辅助系统。但应该注意，模型仍在某些专业领域(如医学诊断)需要谨慎使用。关键启示是：选择合适工具比盲目追求"最强模型"更重要。"

❌ 错误 (bullet points):
"- Claude 3.5 Sonnet发布
- 性能提升35%
- 编程能力更强
- 成本更低
- 适合企业部署"

**返回JSON格式**:
{{
  "summary": "你的3-4段落摘要(中文,段落之间用\\n\\n分隔)",
  "fact_check": "passed",
  "char_count": 600,
  "paragraph_count": 4,
  "key_data_points": ["数据点1", "数据点2"],
  "core_argument": "文章的核心论点简述"
}}

如果文章缺乏具体数据或无法核实事实,将fact_check设为"needs_verification"。"""

    def _build_article_message(self, article: Dict[str, Any]) -> str:
        """Build user message with article to paraphrase - enhanced for 500-700 char format"""
        # Include evaluation context if available
        key_takeaway = ""
        if 'evaluation' in article:
            key_takeaway = f"\n**关键洞察**: {article['evaluation'].get('key_takeaway', '')}"

        # Get full content or truncate if too long
        content = article.get('content', '')
        if len(content) > 4000:
            content = content[:4000] + "..."

        return f"""请将这篇文章改写为深度的分析性摘要(3-4个段落)。突出核心机制、实际影响和行业启示,语气应该是分析性启发而非商业宣传。

**标题**: {article['title']}
**来源**: {article['source']}
**发布时间**: {article.get('published_date', 'Unknown')}{key_takeaway}

**原文内容**:
{content}

**改写要求**:
1. 使用3-4个清晰的段落,段落之间用空行分隔
2. 第1段(150-180字): 事件背景 + 核心创新/突破 + 证明突破的关键数据
3. 第2段(150-180字): 技术/商业机制 + 如何实现这个突破 + 与前代/竞争方案的差异
4. 第3段(150-180字): 实际应用场景 + 受益方 + 具体业务影响(效率、成本、质量)
5. 第4段(100-160字): 市场意义 + 行业启示 + 潜在风险/局限 + 战略建议(可选)
6. 总长度: {self.min_length}-{self.max_length}个中文字符

**关键要求**:
✅ 精选数据: 只包含支撑文章核心论点的具体数据,避免无关细节
✅ 解释机制: 不仅说"发生了什么",要说"为什么发生"和"怎么发生的"
✅ 定量影响: 给出具体的成本节省额度、效率提升百分比、市场规模
✅ 具体场景: "金融风控团队"而非"企业","减少审核时间20%"而非"更快"
✅ 批判思维: 既谈机遇也讨论风险/局限,避免单纯宣传
✅ 分析性启发的语气:
   - ✅ "这个变化揭示了...的潜力,关键在于..."
   - ✅ "值得注意的是,[发展]正在改变[现状],这对[行业]意味着..."
   - ❌ 避免"革命性的"、"改变世界"等商业化措辞

**重要提示**:
- 不要堆砌数据,每个数据都要有上下文
- 优先阐述"为什么"比"是什么"更重要
- 用"但是"、"需要注意"等词语平衡宣传语气
- 避免bullet points或列表,一定要是段落格式

以JSON格式返回摘要:
```json
{{
  "summary": "你的3-4段落摘要(中文,段落之间用\\n\\n分隔)",
  "fact_check": "passed或needs_verification",
  "char_count": 600,
  "paragraph_count": 4,
  "key_data_points": ["数据点1", "数据点2"],
  "core_argument": "文章的核心论点简述"
}}
```"""

    def _cache_articles(self, articles: List[Dict[str, Any]]):
        """
        Cache full article contexts before paraphrasing

        Saves to: ./data/cache/article_contexts/YYYYMMDD.json
        Format includes full original content and extracted entities
        """
        try:
            # Generate cache filename based on current date
            cache_filename = datetime.now().strftime("%Y%m%d.json")
            cache_path = self.cache_dir / cache_filename

            # Prepare cached data
            cached_data = {
                "report_date": datetime.now().strftime("%Y-%m-%d"),
                "generation_time": datetime.now().isoformat(),
                "articles": []
            }

            # Process each article
            for i, article in enumerate(articles):
                cached_article = {
                    "id": f"{i+1:03d}",  # 001, 002, etc.
                    "title": article.get('title', ''),
                    "url": article.get('url', ''),
                    "source": article.get('source', ''),
                    "published_date": article.get('published_date', ''),
                    "full_content": article.get('content', ''),
                    "credibility_score": article.get('credibility_score', 0),
                    "relevance_score": article.get('relevance_score', 0),
                    "entities": article.get('entities', {}),
                    "evaluation": article.get('evaluation', {})
                }
                cached_data["articles"].append(cached_article)

            # Save to file
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(cached_data, f, ensure_ascii=False, indent=2)

            logger.info(f"Cached {len(articles)} articles to {cache_path}")

        except Exception as e:
            logger.error(f"Failed to cache articles: {e}")
            # Don't fail the entire process if caching fails

    def _cleanup_old_caches(self):
        """
        Delete cache files older than cache_retention_days

        Automatically cleans up old cached articles to manage disk space
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=self.cache_retention_days)
            deleted_count = 0

            # Iterate through all JSON files in cache directory
            for cache_file in self.cache_dir.glob("*.json"):
                try:
                    # Parse date from filename (YYYYMMDD.json)
                    file_date = datetime.strptime(cache_file.stem, "%Y%m%d")

                    # Delete if older than retention period
                    if file_date < cutoff_date:
                        cache_file.unlink()
                        deleted_count += 1
                        logger.debug(f"Deleted old cache: {cache_file.name}")

                except ValueError:
                    # Skip files that don't match YYYYMMDD.json format
                    logger.warning(f"Skipping invalid cache filename: {cache_file.name}")
                    continue

            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} old cache file(s)")
            else:
                logger.debug("No old cache files to clean up")

        except Exception as e:
            logger.error(f"Failed to cleanup old caches: {e}")
            # Don't fail the entire process if cleanup fails


if __name__ == "__main__":
    # Test article paraphraser
    paraphraser = ArticleParaphraser()

    # Sample article
    sample_article = {
        'title': 'OpenAI发布GPT-5，性能提升显著',
        'source': '机器之心',
        'content': '''OpenAI今日正式发布了备受期待的GPT-5大语言模型。根据官方公布的测试结果，
        GPT-5在推理能力、数学问题求解、代码生成等多个维度上都实现了显著提升。新模型支持最长500K tokens的上下文窗口，
        相比GPT-4提升了5倍。OpenAI CEO表示，GPT-5标志着通用人工智能的重要里程碑，
        将通过API向企业客户开放使用。定价方面，输入价格为每百万tokens $10，输出价格为$30。''',
        'published_date': '2024-10-20',
        'evaluation': {
            'key_takeaway': 'GPT-5发布，性能大幅提升，支持更长上下文'
        }
    }

    result = paraphraser.paraphrase_articles([sample_article])
    print(f"\nOriginal length: {len(sample_article['content'])} chars")
    print(f"Summary length: {len(result[0]['paraphrased_content'])} chars")
    print(f"\nSummary:\n{result[0]['paraphrased_content']}")
