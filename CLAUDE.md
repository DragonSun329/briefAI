# AI Industry Weekly Briefing Agent

## Project Goal

Build an intelligent agent that automatically generates weekly AI industry briefings in Mandarin Chinese for a CEO. The system should scrape news, evaluate importance, paraphrase articles, and format them into a professional report.

## What This Agent Does

Every week, this agent will:
1. **Ask the CEO** what types of AI news they want (e.g., "大模型", "AI应用", "政策监管")
2. **Scrape articles** from Chinese and English AI news sources
3. **Evaluate** which articles are most important/relevant
4. **Paraphrase** selected articles into concise executive summaries (in Mandarin, paragraph format)
5. **Generate** a beautiful weekly report with insights and key takeaways

**Final Output**: A Markdown report in Mandarin Chinese, ready to send to the CEO every Friday.

## Key Requirements

### Critical Output Requirements
- ✅ All content must be in **Mandarin Chinese** (except technical terms like "GPT", "Claude")
- ✅ Article summaries must be in **paragraph format** (流畅的段落), NOT bullet points
- ✅ Length: 150-250 Chinese characters per article
- ✅ Professional, executive-level tone
- ✅ Factually accurate - no hallucinations

### Technical Requirements
- Python 3.10+
- Anthropic Claude API (Sonnet 4.5)
- Web scraping (RSS + HTML)
- Modular architecture (5 main components)

## Architecture Overview

```
User Input → Category Selector → Web Scraper → News Evaluator → Article Paraphraser → Report Formatter → Final Report
```

### The 5 Core Modules

1. **Category Selector** (`modules/category_selector.py`)
   - Interprets user preferences (e.g., "我想了解大模型和AI应用")
   - Maps to structured categories with priorities
   - Uses Claude to understand natural language input

2. **Web Scraper** (`modules/web_scraper.py`)
   - Scrapes from configured sources (机器之心, 量子位, TechCrunch AI, etc.)
   - Supports RSS feeds and HTML scraping
   - Caches articles to avoid re-scraping
   - Returns: title, url, content, date, source

3. **News Evaluator** (`modules/news_evaluator.py`)
   - Scores articles on 4 dimensions: Impact, Relevance, Recency, Credibility
   - Uses Claude with evaluation prompts
   - Ranks articles and selects top 10-15
   - Returns: scores, rationale, key takeaway (in Mandarin)

4. **Article Paraphraser** (`modules/article_paraphraser.py`)
   - Condenses full articles into executive summaries
   - Output in flowing paragraph format (NOT bullet points)
   - 150-250 Chinese characters
   - Includes fact-checking to prevent hallucinations
   - Returns: paraphrased content in Mandarin

5. **Report Formatter** (`modules/report_formatter.py`)
   - Compiles all paraphrased articles into final report
   - Generates executive summary (2-3 sentences)
   - Generates key insights (3-5 strategic takeaways)
   - Uses Jinja2 template for consistent formatting
   - Output: Markdown (with optional HTML/PDF export)

## Project Structure

```
ai_briefing_agent/
├── CLAUDE.md                      # This file - project overview
├── config/
│   ├── sources.json               # News source configurations
│   ├── categories.json            # Category taxonomy
│   └── report_template.md         # Report template (Jinja2)
├── modules/
│   ├── category_selector.py
│   ├── web_scraper.py
│   ├── news_evaluator.py
│   ├── article_paraphraser.py
│   └── report_formatter.py
├── utils/
│   ├── claude_client.py           # Claude API wrapper
│   ├── cache_manager.py           # Caching utilities
│   └── logger.py
├── data/
│   ├── cache/                     # Cached scraped articles
│   └── reports/                   # Generated reports
├── main.py                        # Main orchestrator
├── requirements.txt
└── .env                           # API keys and config
```

## Documentation

**READ THESE FILES FIRST** - They contain all the details you need:

1. **`ARCHITECTURE.md`** - Complete system architecture, data flow, technology stack, and configuration examples

2. **`PROMPTS.md`** - All Claude API prompt templates for each module (system prompts, user prompts, JSON formats)

3. **`GUIDE.md`** - Step-by-step implementation guide with code examples, 8-day development plan, and deployment instructions

## How to Get Started

### Phase 1: Setup (Start Here)
```bash
# 1. Create project structure
mkdir -p briefAI/{config,modules,utils,data/{cache,reports},logs}
cd briefAI

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# 3. Create requirements.txt
cat > requirements.txt << EOF
anthropic>=0.25.0
requests>=2.31.0
beautifulsoup4>=4.12.0
lxml>=4.9.0
feedparser>=6.0.10
playwright>=1.40.0
python-dateutil>=2.8.2
jinja2>=3.1.2
pyyaml>=6.0
python-dotenv>=1.0.0
EOF

# 4. Install dependencies
pip install -r requirements.txt

# 5. Create .env file
cat > .env << EOF
ANTHROPIC_API_KEY=your_api_key_here
DEFAULT_CATEGORIES=大模型,AI应用,政策监管
REPORT_OUTPUT_DIR=./data/reports
CACHE_DIR=./data/cache
LOG_LEVEL=INFO
EOF
```

### Phase 2: Build Core Components

**Start with the easiest module first** to validate the approach:

#### Step 1: Build Claude Client (`utils/claude_client.py`)
- Wrapper for Anthropic API
- Add retry logic and error handling
- Implement caching for repeated calls
- See implementation guide for code examples

#### Step 2: Build Category Selector (`modules/category_selector.py`)
- Load categories from `config/categories.json`
- Use Claude to parse user input
- Return structured category list
- Test with: "我想了解大模型和AI应用"

#### Step 3: Build RSS Scraper (simplest scraper)
- Start with just RSS feeds (easiest)
- Use `feedparser` library
- Scrape from 机器之心 RSS feed
- Cache results to avoid re-scraping

#### Step 4: Build News Evaluator
- Use evaluation prompts from templates doc
- Score articles on 4 dimensions
- Rank and select top articles

#### Step 5: Build Article Paraphraser
- CRITICAL: Output must be flowing paragraphs in Mandarin, NOT bullet points
- Use paraphrase prompts from templates doc
- Add fact-checking verification step
- Test thoroughly to prevent hallucinations

#### Step 6: Build Report Formatter
- Use Jinja2 template from config
- Generate executive summary with Claude
- Generate key insights
- Compile into final Markdown report

#### Step 7: Build Main Orchestrator (`main.py`)
- Connect all modules together
- Add CLI interface with argparse
- Implement workflow: select → scrape → evaluate → paraphrase → format
- Add progress logging

## Configuration Files to Create

### `config/sources.json`
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

### `config/categories.json`
See implementation guide for complete example with 7 categories.

### `config/report_template.md`
Jinja2 template with sections: 本周概览, 重点资讯 (by category), 关键洞察, 延伸阅读

## Testing Strategy

### Unit Tests
- Test each module independently
- Mock external dependencies (API calls, web requests)
- Validate data structures and outputs

### Integration Test
- Run end-to-end with 3-5 sample articles
- Verify report format and Mandarin output quality
- Check for hallucinations in paraphrased content

### Manual Quality Checks
- [ ] Verify factual accuracy against original articles
- [ ] Check Mandarin language quality and grammar
- [ ] Ensure paragraph format (not bullet points)
- [ ] Validate all links work
- [ ] Review executive summary relevance

## Success Criteria

- ✅ Generates report with 10-15 high-quality articles
- ✅ All content in professional Mandarin Chinese
- ✅ Article summaries are 150-250 characters, paragraph format
- ✅ 95%+ factual accuracy (no hallucinations)
- ✅ Complete workflow takes <30 minutes
- ✅ Output ready for CEO by Friday

## Cost Estimation

**Per weekly report:**
- ~60,000 tokens (input + output)
- Cost: $0.50 - $1.00 per report
- Monthly: ~$2-4

Very affordable for weekly CEO briefings!

## Common Pitfalls to Avoid

1. **Don't use bullet points** in article summaries - requirement is flowing paragraphs
2. **Always verify facts** - don't let Claude hallucinate
3. **Handle Chinese encoding properly** - always use `encoding='utf-8'`
4. **Respect rate limits** - add delays between API calls
5. **Cache aggressively** - don't re-scrape or re-evaluate
6. **Test prompts iteratively** - start simple, refine based on output

## Development Timeline

- **Day 1**: Project setup, configs, Claude client
- **Day 2**: Category selector + RSS scraper
- **Day 3**: News evaluator
- **Day 4**: Article paraphraser (most critical component)
- **Day 5**: Report formatter
- **Day 6**: Main orchestrator + CLI
- **Day 7**: Testing and refinement
- **Day 8**: Deployment + automation setup

## Next Steps

1. **Read the three documentation files** in detail
2. **Set up project structure** (Phase 1 above)
3. **Start with Claude client** - get API working
4. **Build modules incrementally** - test each one
5. **Iterate on prompts** - refine based on output quality
6. **Test with real data** - validate with CEO
7. **Automate** - set up weekly cron job

## Questions to Consider

- Which news sources should we prioritize?
- How many articles should each report include? (default: 10-15)
- Should we track trends week-over-week?
- Do we need PDF export or is Markdown sufficient?
- Should reports be emailed automatically?

## Important Notes

- This agent uses **Claude Sonnet 4.5** via Anthropic API
- All outputs are in **Mandarin Chinese** (except technical terms)
- Article summaries are **paragraph format**, never bullet points
- The system is designed to run **weekly** (every Monday/Friday)
- Focus on **quality over quantity** - better to have 10 great articles than 30 mediocre ones

---

## Ready to Build?

Start with the implementation guide and build incrementally. Test each module before moving to the next. The architecture is designed to be modular and maintainable.

**Key principle**: Make it work first (MVP), then make it better (refinement).

Good luck! 🚀