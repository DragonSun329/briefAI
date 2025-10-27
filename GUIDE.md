# AI Briefing Agent - Implementation Guide for Claude Code

This guide provides step-by-step instructions for building the AI briefing agent system using Claude Code and Cursor.

---

## Prerequisites

### Required Tools:
- Python 3.10 or higher
- Claude Code CLI
- Cursor IDE (or VS Code with Cursor)
- Anthropic API key

### Required Python Packages:
```txt
anthropic>=0.25.0
requests>=2.31.0
beautifulsoup4>=4.12.0
lxml>=4.9.0
feedparser>=6.0.10
playwright>=1.40.0
python-dateutil>=2.8.2
markdownify>=0.11.6
jinja2>=3.1.2
pyyaml>=6.0
python-dotenv>=1.0.0
```

---

## Phase 1: Project Setup (Day 1)

### Step 1.1: Initialize Project Structure

```bash
# Create project directory
mkdir ai_briefing_agent
cd ai_briefing_agent

# Create subdirectories
mkdir -p config modules utils data/{cache,reports} logs

# Initialize git
git init
```

### Step 1.2: Create Configuration Files

**File: `.env`**
```env
ANTHROPIC_API_KEY=your_api_key_here
DEFAULT_CATEGORIES=大模型,AI应用,政策监管
REPORT_OUTPUT_DIR=./data/reports
CACHE_DIR=./data/cache
LOG_LEVEL=INFO
```

**File: `config/sources.json`**
```json
{
  "sources": [
    {
      "id": "jiqizhixin",
      "name": "机器之心",
      "url": "https://www.jiqizhixin.com",
      "type": "rss",
      "rss_url": "https://www.jiqizhixin.com/rss",
      "enabled": true,
      "categories": ["大模型", "AI应用", "研究突破"],
      "language": "zh-CN",
      "credibility_score": 9
    },
    {
      "id": "qbitai",
      "name": "量子位",
      "url": "https://www.qbitai.com",
      "type": "web",
      "enabled": true,
      "categories": ["大模型", "AI应用", "企业动态"],
      "language": "zh-CN",
      "credibility_score": 8
    }
  ]
}
```

**File: `config/categories.json`**
```json
{
  "categories": [
    {
      "id": "llm",
      "name_zh": "大模型",
      "name_en": "Large Language Models",
      "keywords": ["GPT", "Claude", "大模型", "语言模型", "LLM", "Gemini"],
      "priority_default": 9
    },
    {
      "id": "application",
      "name_zh": "AI应用",
      "name_en": "AI Applications",
      "keywords": ["应用", "落地", "产品", "工具", "应用场景"],
      "priority_default": 8
    },
    {
      "id": "infrastructure",
      "name_zh": "AI基础设施",
      "name_en": "AI Infrastructure",
      "keywords": ["芯片", "GPU", "算力", "云计算", "训练"],
      "priority_default": 7
    },
    {
      "id": "policy",
      "name_zh": "政策监管",
      "name_en": "Policy & Regulation",
      "keywords": ["政策", "监管", "法规", "伦理", "治理"],
      "priority_default": 7
    },
    {
      "id": "funding",
      "name_zh": "行业融资",
      "name_en": "Industry Funding",
      "keywords": ["融资", "投资", "收购", "IPO", "估值"],
      "priority_default": 6
    },
    {
      "id": "research",
      "name_zh": "研究突破",
      "name_en": "Research Breakthroughs",
      "keywords": ["论文", "研究", "突破", "学术", "技术"],
      "priority_default": 8
    },
    {
      "id": "company",
      "name_zh": "企业动态",
      "name_en": "Company Developments",
      "keywords": ["公司", "企业", "合作", "战略", "人事"],
      "priority_default": 6
    }
  ]
}
```

**File: `config/report_template.md`**
```markdown
# AI行业动态周报
**报告日期**: {{ report_date }}
**报告周期**: {{ week_start }} - {{ week_end }}

---

## 📊 本周概览

{{ executive_summary }}

---

{% for category in categories %}
## {{ category.icon }} {{ category.name }}

{% for article in category.articles %}
### {{ loop.index }}. {{ article.title }}
**来源**: {{ article.source }} | **日期**: {{ article.date }}

{{ article.summary }}

**原文链接**: [查看详情]({{ article.url }})

---

{% endfor %}
{% endfor %}

## 💡 关键洞察

{{ key_insights }}

---

## 🔗 延伸阅读

{% for article in extended_reading %}
- [{{ article.title }}]({{ article.url }}) - {{ article.source }}
{% endfor %}

---

*本报告由AI智能体自动生成和整理 | 生成时间: {{ generation_time }}*
```

---

## Phase 2: Build Core Modules (Days 2-5)

### Step 2.1: Claude API Client (`utils/claude_client.py`)

**Purpose**: Wrapper for Anthropic Claude API with retry logic and caching

**Key Functions**:
- `call_claude(prompt, system_prompt, model='claude-sonnet-4.5')` 
- `call_claude_with_retry()`
- `parse_json_response()`

**Implementation Notes**:
```python
import anthropic
import os
from typing import Dict, Any, Optional
import json
import time

class ClaudeClient:
    def __init__(self):
        self.client = anthropic.Anthropic(
            api_key=os.getenv('ANTHROPIC_API_KEY')
        )
        self.default_model = 'claude-sonnet-4-5-20250929'
    
    def call_claude(
        self, 
        prompt: str, 
        system_prompt: str = "",
        max_tokens: int = 4000,
        temperature: float = 0.7
    ) -> str:
        """Call Claude API with standard parameters"""
        # Implement with retry logic
        # Add caching for system prompts
        # Log all calls for debugging
        pass
    
    def call_with_json_response(
        self,
        prompt: str,
        system_prompt: str = ""
    ) -> Dict[Any, Any]:
        """Call Claude and parse JSON response"""
        # Add JSON parsing with validation
        # Handle malformed JSON gracefully
        pass
```

**Testing**:
```python
# Test file: tests/test_claude_client.py
def test_basic_call():
    client = ClaudeClient()
    response = client.call_claude("Say hello in Chinese")
    assert "你好" in response or "您好" in response
```

---

### Step 2.2: Category Selector Module (`modules/category_selector.py`)

**Purpose**: Parse user preferences and select relevant categories

**Key Functions**:
- `select_categories(user_input: str) -> List[Dict]`
- `parse_preferences(input: str) -> Dict`
- `get_default_categories() -> List[Dict]`

**Implementation Steps**:
1. Load categories from `config/categories.json`
2. Use Claude to interpret user input (use prompt from templates doc)
3. Return structured category list with priorities
4. Handle empty/vague input with sensible defaults

**Example Usage**:
```python
from modules.category_selector import CategorySelector

selector = CategorySelector()
result = selector.select_categories(
    "我想了解大模型的最新进展和AI应用的落地情况"
)

# Returns:
# [
#   {'id': 'llm', 'name': '大模型', 'priority': 10, 'keywords': [...]},
#   {'id': 'application', 'name': 'AI应用', 'priority': 9, 'keywords': [...]}
# ]
```

**Testing Scenarios**:
- Clear input: "大模型和政策监管"
- Vague input: "最近AI有什么新闻"
- English input: "LLM developments and AI applications"
- Empty input: ""

---

### Step 2.3: Web Scraper Module (`modules/web_scraper.py`)

**Purpose**: Collect articles from configured sources

**Key Classes**:
- `BaseScraper` (abstract base class)
- `RSSScaper` (for RSS feeds)
- `WebScraper` (for HTML scraping)
- `ScraperOrchestrator` (manages all scrapers)

**Implementation Priority**:

**Phase 1 - RSS Scraper (Easiest)**:
```python
import feedparser
from datetime import datetime, timedelta

class RSSScraper:
    def scrape(self, source_config: Dict) -> List[Dict]:
        """
        Scrape RSS feed and return article list
        
        Returns format:
        [
            {
                'title': str,
                'url': str,
                'source': str,
                'published_date': datetime,
                'content': str,
                'summary': str
            }
        ]
        """
        feed = feedparser.parse(source_config['rss_url'])
        articles = []
        
        for entry in feed.entries:
            # Filter by date (last 7 days)
            # Extract content
            # Clean HTML
            articles.append({...})
        
        return articles
```

**Phase 2 - Web Scraper (More Complex)**:
- Use `requests` + `BeautifulSoup4`
- Implement selectors for each source
- Handle pagination if needed
- Respect robots.txt and rate limits

**Phase 3 - Dynamic Content Scraper**:
- Use `playwright` for JavaScript-heavy sites
- More complex but handles modern web apps

**Scraper Orchestrator**:
```python
class ScraperOrchestrator:
    def __init__(self):
        self.sources = self.load_sources()
        self.rss_scraper = RSSScraper()
        self.web_scraper = WebScraper()
    
    def scrape_all(
        self, 
        categories: List[str],
        days_back: int = 7
    ) -> List[Dict]:
        """
        Scrape all enabled sources for given categories
        """
        all_articles = []
        
        for source in self.sources:
            if not source['enabled']:
                continue
            
            # Check if source covers requested categories
            if not any(cat in source['categories'] for cat in categories):
                continue
            
            # Use appropriate scraper
            if source['type'] == 'rss':
                articles = self.rss_scraper.scrape(source)
            else:
                articles = self.web_scraper.scrape(source)
            
            all_articles.extend(articles)
        
        return self.deduplicate(all_articles)
```

**Caching Strategy**:
```python
import hashlib
import json
from pathlib import Path

class ArticleCache:
    def __init__(self, cache_dir='./data/cache'):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def get_cache_key(self, url: str) -> str:
        return hashlib.md5(url.encode()).hexdigest()
    
    def is_cached(self, url: str) -> bool:
        cache_file = self.cache_dir / f"{self.get_cache_key(url)}.json"
        return cache_file.exists()
    
    def get(self, url: str) -> Optional[Dict]:
        if not self.is_cached(url):
            return None
        cache_file = self.cache_dir / f"{self.get_cache_key(url)}.json"
        return json.loads(cache_file.read_text(encoding='utf-8'))
    
    def set(self, url: str, article: Dict):
        cache_file = self.cache_dir / f"{self.get_cache_key(url)}.json"
        cache_file.write_text(
            json.dumps(article, ensure_ascii=False, indent=2),
            encoding='utf-8'
        )
```

**Error Handling**:
- Log failed scrapes to `logs/scraper_errors.log`
- Continue with partial results
- Implement exponential backoff for retries
- Handle encoding issues (especially for Chinese content)

---

### Step 2.4: News Evaluator Module (`modules/news_evaluator.py`)

**Purpose**: Score and rank articles by importance

**Key Functions**:
- `evaluate_article(article: Dict, context: Dict) -> Dict`
- `rank_articles(articles: List[Dict]) -> List[Dict]`
- `get_top_articles(articles: List[Dict], n: int = 15) -> List[Dict]`

**Implementation**:
```python
class NewsEvaluator:
    def __init__(self, claude_client: ClaudeClient):
        self.claude = claude_client
        self.system_prompt = self.load_evaluator_prompt()
    
    def evaluate_article(
        self, 
        article: Dict,
        ceo_interests: List[str],
        company_context: str = ""
    ) -> Dict:
        """
        Evaluate single article and return scores
        
        Returns:
        {
            'article_url': str,
            'scores': {
                'impact': int,
                'relevance': int,
                'recency': int,
                'credibility': int
            },
            'composite_score': float,
            'rationale': str,
            'key_takeaway': str,
            'priority': str,  # high/medium/low
            'tags': List[str]
        }
        """
        prompt = self.build_evaluation_prompt(
            article, ceo_interests, company_context
        )
        
        response = self.claude.call_with_json_response(
            prompt, self.system_prompt
        )
        
        # Calculate composite score
        scores = response['scores']
        composite = (
            scores['impact'] * 0.4 +
            scores['relevance'] * 0.3 +
            scores['recency'] * 0.2 +
            scores['credibility'] * 0.1
        )
        
        response['composite_score'] = composite
        response['article_url'] = article['url']
        
        return response
    
    def batch_evaluate(
        self,
        articles: List[Dict],
        ceo_interests: List[str],
        company_context: str = ""
    ) -> List[Dict]:
        """Evaluate multiple articles with progress tracking"""
        evaluations = []
        
        for i, article in enumerate(articles):
            print(f"Evaluating article {i+1}/{len(articles)}...")
            eval_result = self.evaluate_article(
                article, ceo_interests, company_context
            )
            evaluations.append(eval_result)
            
            # Rate limiting - space out API calls
            time.sleep(0.5)
        
        return evaluations
    
    def rank_articles(
        self,
        evaluations: List[Dict]
    ) -> List[Dict]:
        """Sort by composite score, descending"""
        return sorted(
            evaluations,
            key=lambda x: x['composite_score'],
            reverse=True
        )
```

**Optimization Tips**:
- Batch multiple articles in one API call if content is short
- Cache evaluations by article URL
- Skip re-evaluation if article was evaluated recently

---

### Step 2.5: Article Paraphraser Module (`modules/article_paraphraser.py`)

**Purpose**: Condense articles into executive summaries

**Key Functions**:
- `paraphrase_article(article: Dict, evaluation: Dict) -> str`
- `verify_accuracy(original: Dict, paraphrased: str) -> Dict`
- `batch_paraphrase(articles: List[Dict]) -> List[Dict]`

**Implementation**:
```python
class ArticleParaphraser:
    def __init__(self, claude_client: ClaudeClient):
        self.claude = claude_client
        self.paraphrase_prompt = self.load_paraphrase_prompt()
        self.quality_checker_prompt = self.load_quality_prompt()
    
    def paraphrase_article(
        self,
        article: Dict,
        target_length: int = 200  # Chinese characters
    ) -> Dict:
        """
        Paraphrase article into executive summary
        
        Returns:
        {
            'original_title': str,
            'paraphrased_title': str,  # May be cleaned up
            'summary': str,  # The paraphrased content
            'source': str,
            'date': str,
            'url': str,
            'word_count': int
        }
        """
        # Build paraphrase prompt
        prompt = self.paraphrase_prompt.format(
            title=article['title'],
            source=article['source'],
            date=article['published_date'].strftime('%Y年%m月%d日'),
            full_content=article['content'][:5000]  # Truncate if too long
        )
        
        # Get paraphrased content
        paraphrased = self.claude.call_claude(
            prompt,
            self.system_prompt,
            max_tokens=1000
        )
        
        # Verify quality
        quality_check = self.verify_accuracy(article, paraphrased)
        
        if quality_check['approval_status'] != 'approved':
            # Retry with corrections
            paraphrased = self.retry_with_corrections(
                article, paraphrased, quality_check
            )
        
        return {
            'original_title': article['title'],
            'paraphrased_title': self.clean_title(article['title']),
            'summary': paraphrased,
            'source': article['source'],
            'date': article['published_date'].strftime('%m月%d日'),
            'url': article['url'],
            'word_count': len(paraphrased)
        }
    
    def verify_accuracy(
        self,
        original_article: Dict,
        paraphrased_content: str
    ) -> Dict:
        """Use Claude to verify paraphrase quality"""
        # Extract key facts from original
        key_facts = self.extract_key_facts(original_article)
        
        # Build verification prompt
        prompt = self.quality_checker_prompt.format(
            original_key_points=key_facts,
            paraphrased_content=paraphrased_content
        )
        
        quality_result = self.claude.call_with_json_response(
            prompt,
            system_prompt="You verify content quality and accuracy."
        )
        
        return quality_result
```

**Quality Assurance**:
- Always verify paraphrased content doesn't hallucinate
- Check that key numbers and names are preserved
- Ensure output is in proper Mandarin
- Validate length is within target range

---

### Step 2.6: Report Formatter Module (`modules/report_formatter.py`)

**Purpose**: Compile everything into final report

**Key Functions**:
- `generate_report(articles: List[Dict], metadata: Dict) -> str`
- `generate_executive_summary(articles: List[Dict]) -> str`
- `generate_key_insights(articles: List[Dict]) -> str`
- `export_to_html(markdown: str) -> str`
- `export_to_pdf(markdown: str, output_path: str)`

**Implementation**:
```python
from jinja2 import Template
from datetime import datetime

class ReportFormatter:
    def __init__(self, claude_client: ClaudeClient):
        self.claude = claude_client
        self.template = self.load_template()
    
    def generate_report(
        self,
        articles_by_category: Dict[str, List[Dict]],
        week_start: datetime,
        week_end: datetime
    ) -> str:
        """
        Generate complete weekly report
        
        Args:
            articles_by_category: {
                '大模型': [article1, article2, ...],
                'AI应用': [article3, article4, ...]
            }
        """
        # Generate executive summary
        exec_summary = self.generate_executive_summary(
            articles_by_category
        )
        
        # Generate key insights
        key_insights = self.generate_key_insights(
            articles_by_category
        )
        
        # Format categories with icons
        formatted_categories = []
        category_icons = {
            '大模型': '🤖',
            'AI应用': '💼',
            'AI基础设施': '⚙️',
            '政策监管': '📋',
            '行业融资': '💰',
            '研究突破': '🔬',
            '企业动态': '🏢'
        }
        
        for category_name, articles in articles_by_category.items():
            formatted_categories.append({
                'name': category_name,
                'icon': category_icons.get(category_name, '📌'),
                'articles': articles
            })
        
        # Render template
        report = self.template.render(
            report_date=datetime.now().strftime('%Y年%m月%d日'),
            week_start=week_start.strftime('%m月%d日'),
            week_end=week_end.strftime('%m月%d日'),
            executive_summary=exec_summary,
            categories=formatted_categories,
            key_insights=key_insights,
            extended_reading=self.get_extended_reading(articles_by_category),
            generation_time=datetime.now().strftime('%Y-%m-%d %H:%M')
        )
        
        return report
    
    def generate_executive_summary(
        self,
        articles_by_category: Dict[str, List[Dict]]
    ) -> str:
        """Use Claude to generate 2-3 sentence overview"""
        # Collect all article titles and key takeaways
        summary_data = []
        for category, articles in articles_by_category.items():
            for article in articles:
                summary_data.append(
                    f"- {category}: {article['paraphrased_title']}"
                )
        
        prompt = f"""基于本周选中的这些AI新闻文章，写一个2-3句话的高层次总结：

{chr(10).join(summary_data)}

要求：
- 识别本周的主要趋势和重要发展
- 面向CEO，高度概括，不要细节
- 用清晰、专业的中文
- 具体指出发展内容，不要空泛

输出格式：
本周AI行业呈现[主要趋势]的特点。[具体发展1]引起广泛关注，同时[具体发展2]也标志着[某个方向]的重要进展。
"""
        
        summary = self.claude.call_claude(
            prompt,
            system_prompt="You craft executive summaries for CEO briefings."
        )
        
        return summary.strip()
    
    def generate_key_insights(
        self,
        articles_by_category: Dict[str, List[Dict]]
    ) -> str:
        """Generate 3-5 strategic insights connecting the dots"""
        # Build context from all articles
        articles_summary = []
        for category, articles in articles_by_category.items():
            for article in articles:
                articles_summary.append(
                    f"{category} - {article['paraphrased_title']}: "
                    f"{article['summary'][:200]}..."
                )
        
        prompt = f"""基于本周的AI新闻，生成3-5个关键战略洞察：

**本周文章**:
{chr(10).join(articles_summary)}

每个洞察应该：
- 2-3句话的中文
- 连接多个发展或识别趋势
- 对商业领导者有战略相关性
- 实质性的，不是表面观察

输出格式：
1. [洞察标题]：[2-3句解释]

2. [洞察标题]：[2-3句解释]

...

基于本周实际新闻生成具体洞察，不是泛泛的AI行业观察。
"""
        
        insights = self.claude.call_claude(
            prompt,
            system_prompt="You synthesize strategic insights from news."
        )
        
        return insights.strip()
```

---

## Phase 3: Main Orchestrator (Day 6)

### Step 3.1: Main Execution Script (`main.py`)

**Purpose**: Orchestrate the entire workflow

```python
#!/usr/bin/env python3
"""
AI Briefing Agent - Main Orchestrator
"""

import argparse
from datetime import datetime, timedelta
from pathlib import Path
import json

from modules.category_selector import CategorySelector
from modules.web_scraper import ScraperOrchestrator
from modules.news_evaluator import NewsEvaluator
from modules.article_paraphraser import ArticleParaphraser
from modules.report_formatter import ReportFormatter
from utils.claude_client import ClaudeClient
from utils.logger import setup_logger

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='Generate AI industry weekly briefing'
    )
    parser.add_argument(
        '--interactive',
        action='store_true',
        help='Interactive mode - ask for category preferences'
    )
    parser.add_argument(
        '--categories',
        type=str,
        help='Comma-separated categories (e.g., "大模型,AI应用")'
    )
    parser.add_argument(
        '--days',
        type=int,
        default=7,
        help='Number of days to look back (default: 7)'
    )
    parser.add_argument(
        '--top-n',
        type=int,
        default=15,
        help='Number of top articles to include (default: 15)'
    )
    parser.add_argument(
        '--output',
        type=str,
        help='Output file path (default: auto-generated)'
    )
    
    args = parser.parse_args()
    
    # Setup logging
    logger = setup_logger()
    logger.info("Starting AI Briefing Agent...")
    
    # Initialize components
    claude_client = ClaudeClient()
    category_selector = CategorySelector(claude_client)
    scraper = ScraperOrchestrator()
    evaluator = NewsEvaluator(claude_client)
    paraphraser = ArticleParaphraser(claude_client)
    formatter = ReportFormatter(claude_client)
    
    # Step 1: Select categories
    logger.info("Step 1: Selecting categories...")
    if args.interactive:
        print("\n欢迎使用AI行业动态简报生成器！")
        print("请描述您想了解哪些方面的AI资讯：")
        user_input = input("> ")
        categories = category_selector.select_categories(user_input)
    elif args.categories:
        # Parse comma-separated categories
        cat_list = [c.strip() for c in args.categories.split(',')]
        categories = category_selector.select_categories(
            f"我想了解{'、'.join(cat_list)}方面的资讯"
        )
    else:
        # Use default categories
        categories = category_selector.get_default_categories()
    
    logger.info(f"Selected categories: {[c['name'] for c in categories]}")
    
    # Step 2: Scrape articles
    logger.info("Step 2: Scraping articles from sources...")
    category_names = [c['name'] for c in categories]
    articles = scraper.scrape_all(
        categories=category_names,
        days_back=args.days
    )
    logger.info(f"Collected {len(articles)} articles")
    
    if len(articles) == 0:
        logger.error("No articles found. Exiting.")
        return
    
    # Step 3: Evaluate articles
    logger.info("Step 3: Evaluating article importance...")
    ceo_interests = [c['name'] for c in categories]
    evaluations = evaluator.batch_evaluate(
        articles,
        ceo_interests=ceo_interests,
        company_context=""  # Can be customized
    )
    
    # Rank and select top articles
    ranked = evaluator.rank_articles(evaluations)
    top_articles = ranked[:args.top_n]
    logger.info(f"Selected top {len(top_articles)} articles")
    
    # Step 4: Paraphrase articles
    logger.info("Step 4: Paraphrasing articles...")
    paraphrased_articles = []
    for i, eval_result in enumerate(top_articles):
        # Find original article
        original = next(
            a for a in articles if a['url'] == eval_result['article_url']
        )
        
        logger.info(f"Paraphrasing {i+1}/{len(top_articles)}: {original['title']}")
        paraphrased = paraphraser.paraphrase_article(original)
        
        # Merge evaluation data with paraphrased content
        paraphrased['evaluation'] = eval_result
        paraphrased['category'] = self.determine_category(
            original, categories
        )
        
        paraphrased_articles.append(paraphrased)
    
    # Group by category
    articles_by_category = {}
    for article in paraphrased_articles:
        cat = article['category']
        if cat not in articles_by_category:
            articles_by_category[cat] = []
        articles_by_category[cat].append(article)
    
    # Step 5: Generate report
    logger.info("Step 5: Generating report...")
    week_end = datetime.now()
    week_start = week_end - timedelta(days=args.days)
    
    report_markdown = formatter.generate_report(
        articles_by_category,
        week_start,
        week_end
    )
    
    # Save report
    if args.output:
        output_path = Path(args.output)
    else:
        output_dir = Path('./data/reports')
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"ai_briefing_{datetime.now().strftime('%Y%m%d')}.md"
        output_path = output_dir / filename
    
    output_path.write_text(report_markdown, encoding='utf-8')
    logger.info(f"Report saved to: {output_path}")
    
    print(f"\n✅ 报告生成完成！")
    print(f"📄 文件位置: {output_path}")
    print(f"📊 包含文章: {len(paraphrased_articles)} 篇")
    print(f"📂 涵盖分类: {', '.join(articles_by_category.keys())}")

if __name__ == '__main__':
    main()
```

---

## Phase 4: Testing & Refinement (Day 7)

### Step 4.1: Unit Tests

Create tests for each module:

```bash
tests/
├── test_category_selector.py
├── test_web_scraper.py
├── test_news_evaluator.py
├── test_article_paraphraser.py
└── test_report_formatter.py
```

### Step 4.2: Integration Test

```python
# tests/test_integration.py

def test_end_to_end_small():
    """Test complete workflow with minimal data"""
    # Mock 5 sample articles
    # Run through entire pipeline
    # Verify output format
    pass
```

### Step 4.3: Manual Quality Checks

- [ ] Verify facts in paraphrased content
- [ ] Check Mandarin language quality
- [ ] Validate report formatting
- [ ] Test with different category combinations
- [ ] Ensure links work
- [ ] Check for hallucinations

---

## Phase 5: Deployment & Automation (Day 8+)

### Step 5.1: Schedule Weekly Execution

**Option 1: Cron (Linux/Mac)**
```bash
# Edit crontab
crontab -e

# Add line to run every Monday at 9 AM
0 9 * * 1 cd /path/to/ai_briefing_agent && /path/to/python main.py --use-saved-preferences
```

**Option 2: Windows Task Scheduler**
- Create scheduled task
- Run `main.py` weekly

**Option 3: GitHub Actions** (if code is in GitHub)
```yaml
# .github/workflows/weekly_briefing.yml
name: Generate Weekly Briefing

on:
  schedule:
    - cron: '0 9 * * 1'  # Every Monday 9 AM UTC
  workflow_dispatch:  # Allow manual trigger

jobs:
  generate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.10'
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Generate report
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: python main.py --use-saved-preferences
      - name: Upload report
        uses: actions/upload-artifact@v2
        with:
          name: weekly-report
          path: data/reports/*.md
```

### Step 5.2: Email Integration (Optional)

```python
# utils/email_sender.py

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def send_report_email(
    report_content: str,
    recipient: str,
    subject: str = "AI行业动态周报"
):
    """Send report via email"""
    # Convert Markdown to HTML
    html_content = markdown_to_html(report_content)
    
    # Create email
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = 'your_email@example.com'
    msg['To'] = recipient
    
    # Attach HTML
    html_part = MIMEText(html_content, 'html')
    msg.attach(html_part)
    
    # Send via SMTP
    with smtplib.SMTP('smtp.gmail.com', 587) as server:
        server.starttls()
        server.login('your_email', 'your_password')
        server.send_message(msg)
```

---

## Troubleshooting Guide

### Common Issues:

**Issue 1: API Rate Limits**
- Solution: Add delays between API calls (`time.sleep(1)`)
- Use caching aggressively
- Consider upgrading API tier

**Issue 2: Scraping Failures**
- Solution: Implement robust retry logic
- Use multiple fallback sources
- Handle encoding issues with `chardet`

**Issue 3: Poor Paraphrase Quality**
- Solution: Refine prompts with examples
- Increase max_tokens if summaries are cut off
- Add quality verification step

**Issue 4: Chinese Encoding Issues**
- Solution: Always use `encoding='utf-8'`
- Verify source encoding with `chardet`
- Test with Chinese text in prompts

**Issue 5: Slow Execution**
- Solution: Implement parallel processing for scraping
- Cache aggressively
- Consider using faster Claude model for evaluation

---

## Performance Optimization

### Caching Strategy:
- Cache scraped articles for 24 hours
- Cache evaluations for 7 days
- Cache paraphrased content indefinitely

### Parallel Processing:
```python
from concurrent.futures import ThreadPoolExecutor

def batch_evaluate_parallel(articles, max_workers=5):
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(evaluate_article, article)
            for article in articles
        ]
        results = [f.result() for f in futures]
    return results
```

---

## Cost Estimation

### API Usage per Run:
- Category selection: 1 call (~500 tokens)
- Article evaluation: 50 calls (~25,000 tokens)
- Paraphrasing: 15 calls (~30,000 tokens)
- Report generation: 3 calls (~5,000 tokens)

**Total: ~60,000 tokens per weekly run**

At Claude Sonnet pricing (~$3 per million input tokens, ~$15 per million output tokens):
- **Cost per report: ~$0.50-$1.00**
- **Monthly cost: ~$2-$4**

Very affordable for weekly CEO briefings!

---

## Maintenance & Improvements

### Weekly Tasks:
- Review generated reports for quality
- Update source configurations if sites change
- Refine prompts based on output quality

### Monthly Tasks:
- Analyze which sources provide best content
- Add new high-quality sources
- Update category taxonomy if needed

### Quarterly Tasks:
- Review and optimize API usage
- Consider adding new features (email, PDF export)
- Gather CEO feedback and adjust

---

## Next Steps After MVP

1. **Add more sources** - Expand beyond initial 2-3 sources
2. **Web dashboard** - Build simple UI for easier interaction
3. **PDF export** - Generate professional PDF reports
4. **Preference learning** - Remember CEO's preferred topics
5. **Comparative analysis** - Track trends week-over-week
6. **Multi-language support** - Include English sources with translation

---

This implementation guide provides everything needed to build the AI briefing agent step by step. Start with Phase 1, build incrementally, test thoroughly, and iterate based on results.