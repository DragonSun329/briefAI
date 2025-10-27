# AI Industry News Briefing Agent - Architecture Design

## Project Overview

Build an intelligent agent system that generates weekly AI industry briefings for the CEO. The system should automatically collect, evaluate, summarize, and format AI news into a professional report in Mandarin Chinese.

## System Architecture

### Component Overview

```
User Input (Category Preferences)
    ↓
[1] Category Selector
    ↓
[2] Web Scraper (RPA Module)
    ↓
[3] News Evaluator
    ↓
[4] Article Paraphraser
    ↓
[5] Report Formatter
    ↓
Final Briefing Document (Mandarin)
```

---

## Component Specifications

### 1. Category Selector Module

**Purpose**: Interpret user preferences and determine which AI news categories to focus on.

**Input**: 
- Natural language prompt (e.g., "我想了解大模型、AI应用、和政策监管方面的资讯")

**Output**:
- Structured list of categories with priority levels
- Suggested sources for each category

**Implementation Approach**:
- Use LLM (Claude) to parse the natural language input
- Maintain a predefined taxonomy of AI categories:
  - Large Language Models (大模型)
  - AI Applications (AI应用)
  - AI Infrastructure (AI基础设施)
  - Policy & Regulation (政策监管)
  - Industry Funding (行业融资)
  - Research Breakthroughs (研究突破)
  - Company Developments (企业动态)
- Map user intent to 1-3 primary categories
- Return JSON structure with categories and weights

**Key Features**:
- Support for both English and Mandarin input
- Intelligent fallback to default categories if input is ambiguous
- Memory of previous preferences (optional enhancement)

---

### 2. Web Scraper (RPA Module)

**Purpose**: Automatically collect AI news from specified sources.

**Recommended Sources**:
- **Chinese Sources**:
  - 机器之心 (jiqizhixin.com)
  - 量子位 (qbitai.com)
  - 新智元 (newsminer.net)
  - 36氪 AI频道
  - 虎嗅 AI板块
- **English Sources**:
  - TechCrunch AI
  - The Verge AI
  - VentureBeat AI
  - OpenAI Blog
  - Anthropic Blog

**Technical Implementation**:
- **Tool Options**:
  - `requests` + `BeautifulSoup4` for basic scraping
  - `playwright` or `selenium` for JavaScript-heavy sites
  - RSS feed parsing (`feedparser`) where available
  - Consider API access where available (NewsAPI, etc.)

**Data Structure to Extract**:
```python
{
    "title": str,
    "url": str,
    "source": str,
    "published_date": datetime,
    "content": str,  # full article text
    "category": str,
    "author": str (optional),
    "summary_snippet": str (if available)
}
```

**Scraping Strategy**:
- Respect robots.txt and rate limits
- Implement retry logic with exponential backoff
- Cache results to avoid redundant requests
- Handle common anti-scraping measures (user agents, delays)
- Store raw data before processing

**Error Handling**:
- Log failed scrapes with reason
- Continue processing with available data
- Implement fallback sources for each category

---

### 3. News Evaluator (Headliner)

**Purpose**: Assess newsworthiness and relevance of collected articles.

**Evaluation Criteria**:
- **Impact Score** (1-10): How significant is this news to the AI industry?
- **Relevance Score** (1-10): How relevant is this to our company/interests?
- **Recency Score** (1-10): How timely is this information?
- **Source Credibility** (1-10): How reliable is the source?

**Implementation**:
- Use Claude with structured prompt to evaluate each article
- Provide context about CEO's interests and company focus
- Apply weighted scoring formula:
  ```
  Final Score = (Impact * 0.4) + (Relevance * 0.3) + (Recency * 0.2) + (Credibility * 0.1)
  ```

**Output**:
- Ranked list of articles (top 10-15)
- Rationale for each article's importance (1-2 sentences)
- Categorization tags

**Prompt Template**:
```
Evaluate the following AI news article for a CEO briefing:

Title: {title}
Source: {source}
Date: {date}
Content: {content}

Context: Our CEO is interested in {categories}. The company focuses on {company_context}.

Provide:
1. Impact score (1-10)
2. Relevance score (1-10)
3. Recency score (1-10)
4. Source credibility (1-10)
5. Brief rationale (2-3 sentences in Mandarin)
6. Key takeaway (1 sentence in Mandarin)
```

---

### 4. Article Paraphraser

**Purpose**: Condense full articles into concise, readable paragraphs (NOT bullet points).

**Requirements**:
- Output in **paragraph format** (流畅的段落形式)
- Length: 150-250 words per article
- Maintain key facts, figures, and context
- Professional, executive-level tone
- Output in Mandarin Chinese

**Structure for Each Paraphrased Article**:
```
**[标题]** ([来源], [日期])

[2-3段精简内容，涵盖：
  - 第一段：核心信息和背景
  - 第二段：关键细节和数据
  - 第三段（如需要）：影响和意义]
```

**Implementation**:
- Use Claude with specific formatting instructions
- Preserve proper nouns in original language
- Include hyperlinks to original article
- Maintain factual accuracy (critical requirement)

**Prompt Template**:
```
Paraphrase the following AI news article into a concise executive summary in Mandarin Chinese.

Article: {content}

Requirements:
- Write in smooth paragraph format (NOT bullet points)
- Length: 150-250 words
- Include key facts, numbers, and context
- Professional tone suitable for CEO briefing
- Maintain accuracy
- Start with strong opening sentence

Output format:
**[标题]** ([来源], [日期])

[段落形式的精简内容]
```

---

### 5. Report Formatter

**Purpose**: Compile paraphrased articles into a professional, well-formatted briefing document.

**Document Structure**:

```markdown
# AI行业动态周报
**报告日期**: YYYY年MM月DD日
**报告周期**: MM月DD日 - MM月DD日

---

## 📊 本周概览

[2-3句话总结本周AI行业的主要趋势和亮点]

---

## 🔥 重点资讯

### [分类1：例如"大模型进展"]

#### 1. [文章标题]
**来源**: [来源名称] | **日期**: MM月DD日

[精简的段落内容...]

**原文链接**: [URL]

---

#### 2. [文章标题]
...

---

### [分类2：例如"AI应用落地"]

...

---

## 💡 关键洞察

[基于本周新闻的3-5个关键洞察或趋势观察]

---

## 🔗 延伸阅读

[可选：列出3-5篇值得深度阅读的文章]

---

*本报告由AI智能体自动生成和整理*
```

**Formatting Requirements**:
- Use Markdown for structure
- Include emoji icons for visual clarity (but use sparingly)
- Ensure proper heading hierarchy
- Add horizontal rules for section separation
- Include clickable links
- Professional color scheme when exported to PDF/HTML

**Output Formats**:
- Primary: Markdown (.md)
- Optional: HTML export for email
- Optional: PDF for archival

**Implementation**:
- Template-based generation using Jinja2 or similar
- Consistent styling across reports
- Metadata tracking (generation date, sources used, article count)

---

## Technology Stack Recommendations

### Core Technologies:
- **Language**: Python 3.10+
- **LLM Integration**: Anthropic Claude API (claude-sonnet-4.5)
- **Web Scraping**: 
  - `requests` + `beautifulsoup4`
  - `playwright` (for complex sites)
  - `feedparser` (for RSS)
- **Data Storage**: 
  - SQLite for article cache
  - JSON for configuration
- **Document Generation**: 
  - `markdown` library
  - `weasyprint` or `pdfkit` for PDF generation

### Project Structure:
```
ai_briefing_agent/
├── config/
│   ├── sources.json          # Web source configurations
│   ├── categories.json        # Category taxonomy
│   └── template.md            # Report template
├── modules/
│   ├── __init__.py
│   ├── category_selector.py
│   ├── web_scraper.py
│   ├── news_evaluator.py
│   ├── article_paraphraser.py
│   └── report_formatter.py
├── utils/
│   ├── __init__.py
│   ├── claude_client.py      # Claude API wrapper
│   ├── cache_manager.py       # Data caching
│   └── logger.py              # Logging utilities
├── data/
│   ├── cache/                 # Scraped articles cache
│   └── reports/               # Generated reports
├── main.py                    # Orchestrator script
├── requirements.txt
└── README.md
```

---

## Workflow Execution

### Weekly Execution Flow:

1. **Monday (or start of week)**:
   ```bash
   python main.py --interactive
   # User provides category preferences
   ```

2. **Data Collection** (automated):
   - Scrape sources based on categories
   - Store raw articles in cache
   - Takes ~5-10 minutes depending on sources

3. **Evaluation & Selection**:
   - Evaluate all articles
   - Rank by composite score
   - Select top 10-15 articles

4. **Content Generation**:
   - Paraphrase selected articles
   - Generate executive summary
   - Compile final report

5. **Output**:
   - Save Markdown report
   - Generate HTML/PDF versions
   - Ready for CEO review by Friday

### CLI Commands:

```bash
# Interactive mode - ask for preferences
python main.py --interactive

# Use saved preferences
python main.py --use-saved-preferences

# Specify categories directly
python main.py --categories "大模型,AI应用,政策监管"

# Specify date range
python main.py --from-date 2025-10-18 --to-date 2025-10-24

# Dry run (scrape but don't generate report)
python main.py --dry-run

# Generate from cached data
python main.py --from-cache
```

---

## Key Implementation Considerations

### 1. Rate Limiting & API Usage:
- Claude API calls: ~50-100 per run (estimate)
- Implement batching where possible
- Cache evaluation results
- Use appropriate model (Sonnet for speed, Opus for quality)

### 2. Content Quality Assurance:
- Validate paraphrased content doesn't hallucinate
- Cross-reference facts with original articles
- Include confidence scores
- Flag uncertain information

### 3. Scalability:
- Design for easy addition of new sources
- Support multiple output formats
- Allow customization of evaluation criteria
- Enable manual override of article selection

### 4. Error Recovery:
- Graceful degradation if sources are unavailable
- Retry logic for API calls
- Logging for debugging
- Alert on critical failures

### 5. Localization:
- Handle mixed Chinese/English content
- Proper translation of technical terms
- Consistent terminology across reports

---

## Development Phases

### Phase 1: MVP (Core Functionality)
- [ ] Basic category selector
- [ ] 2-3 source scrapers
- [ ] Simple evaluation logic
- [ ] Basic paraphrasing
- [ ] Markdown output

### Phase 2: Enhancement
- [ ] Add more sources
- [ ] Sophisticated evaluation
- [ ] Template customization
- [ ] HTML/PDF export
- [ ] CLI interface

### Phase 3: Automation
- [ ] Scheduled execution
- [ ] Email integration
- [ ] Error monitoring
- [ ] Performance optimization
- [ ] Web dashboard (optional)

---

## Testing Strategy

### Unit Tests:
- Test each module independently
- Mock external dependencies (APIs, web requests)
- Validate data structures

### Integration Tests:
- End-to-end workflow with sample data
- API integration tests
- Output format validation

### Quality Tests:
- Human evaluation of paraphrased content
- Fact-checking against original articles
- Readability assessment

---

## Configuration Management

### sources.json Example:
```json
{
  "chinese_sources": [
    {
      "name": "机器之心",
      "url": "https://www.jiqizhixin.com/",
      "type": "rss",
      "rss_url": "https://www.jiqizhixin.com/rss",
      "categories": ["大模型", "AI应用", "研究突破"]
    }
  ],
  "english_sources": [
    {
      "name": "TechCrunch AI",
      "url": "https://techcrunch.com/category/artificial-intelligence/",
      "type": "web",
      "selector": "article.post-block",
      "categories": ["AI应用", "企业动态", "行业融资"]
    }
  ]
}
```

### categories.json Example:
```json
{
  "categories": [
    {
      "id": "llm",
      "name": "大模型",
      "name_en": "Large Language Models",
      "keywords": ["GPT", "Claude", "大模型", "语言模型"],
      "priority": 1
    },
    {
      "id": "application",
      "name": "AI应用",
      "name_en": "AI Applications",
      "keywords": ["应用", "落地", "产品"],
      "priority": 2
    }
  ]
}
```

---

## Success Metrics

- **Accuracy**: 95%+ factual accuracy in paraphrased content
- **Coverage**: 10-15 high-quality articles per week
- **Timeliness**: Report ready by Thursday for Friday delivery
- **Readability**: Executive-level clarity and conciseness
- **Automation**: <30 minutes of manual work per week

---

## Next Steps for Implementation

1. **Set up development environment**
   - Install Python 3.10+
   - Set up virtual environment
   - Install dependencies

2. **Configure Claude API**
   - Obtain API key from Anthropic
   - Set up authentication
   - Test basic API calls

3. **Build MVP**
   - Start with Category Selector
   - Add one scraper (simplest source)
   - Implement basic evaluation
   - Create simple paraphraser
   - Generate basic Markdown output

4. **Iterate and enhance**
   - Test with real data
   - Gather CEO feedback
   - Refine prompts and logic
   - Add more sources gradually

5. **Automate**
   - Set up scheduling (cron job or Task Scheduler)
   - Add monitoring and alerts
   - Document usage for team

---

## Notes for Claude Code

When implementing this system:

1. **Start with the orchestrator** (`main.py`) to understand the overall flow
2. **Build modules incrementally** - test each component independently
3. **Use Claude API for all LLM tasks** - don't try to build local models
4. **Implement caching early** - avoid redundant API calls and web scrapes
5. **Focus on error handling** - web scraping is inherently fragile
6. **Keep prompts in separate files** - easier to iterate and improve
7. **Log everything** - debugging scraping and API issues requires good logs
8. **Test with small datasets first** - validate logic before full-scale runs

This architecture is designed to be modular, maintainable, and scalable. Each component can be developed and tested independently, then integrated into the complete system.