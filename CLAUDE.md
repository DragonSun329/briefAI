# AI Industry Weekly Briefing Agent

## Project Goal

Automatically generate weekly AI industry briefings in Mandarin Chinese for executive review. The system scrapes news from 61 global English-language sources, applies intelligent filtering and 5D weighted scoring, generates deep analysis (500-600 characters per article), and produces professional Markdown reports.

**Regional Focus:** News coverage for China, Indonesia, Philippines, Spain, and Mexico (via English-language sources)

## What This Agent Does

Every week, the complete pipeline:

1. **Scrapes articles** from 61 AI and tech news sources worldwide (100% English, RSS-based)
   - Official company blogs: OpenAI, Anthropic, DeepMind, Meta, Microsoft, Hugging Face
   - Industry research: McKinsey, BCG, Deloitte, EY, PwC, Accenture
   - Regional tech news: TechInAsia, Rest of World, DealStreetAsia, e27, Nikkei Asia, SCMP, Xataka, and more
   - General AI news: TechCrunch, Techmeme, VentureBeat, Hacker News, and other leading sources

2. **Filters and evaluates** articles using intelligent 3-tier system:
   - **Tier 1**: Keyword-based pre-filtering (3.0 threshold)
   - **Tier 2**: Quick LLM batch evaluation (6.0 threshold)
   - **Tier 3**: Deep 5D weighted evaluation (top 10-15 articles)

3. **Ranks** articles by 5D weighted scoring:
   - Market Impact (25%)
   - Competitive Impact (20%)
   - Strategic Relevance (20%)
   - Operational Relevance (15%)
   - Credibility (10%)

4. **Generates** deep analysis in 500-600 Chinese characters per article with:
   - Central argument & key supporting data
   - Quantified impact & performance metrics
   - Mechanism & differentiation from alternatives
   - Practical use cases & business improvements
   - Market significance & strategic risks

5. **Creates** a beautiful Markdown report with:
   - Weekly overview & key trends
   - Top 10 articles with 5D scores and deep analysis
   - Strategic insights & industry implications
   - Professional formatting ready for CEO review

**Final Output**: A professional CEO briefing in Mandarin Chinese, generated every Friday

## Key Features

### Critical Output Requirements
- ✅ All content in **Mandarin Chinese** (technical terms like GPT, Claude in English)
- ✅ Article summaries in **flowing paragraph format** (never bullet points)
- ✅ **500-600 Chinese characters per article** with deep analysis
- ✅ Professional, analytical-inspiring executive tone
- ✅ Factually accurate with no hallucinations

### 5D Scoring System
- ✅ **Market Impact (25%)**: Industry-wide implications, market disruption potential
- ✅ **Competitive Impact (20%)**: Effect on competitive landscape, market consolidation
- ✅ **Strategic Relevance (20%)**: Alignment with CEO strategic priorities
- ✅ **Operational Relevance (15%)**: Practical application to business operations
- ✅ **Credibility (10%)**: Source reliability, evidence quality, verification status

### Data Processing
- ✅ **Semantic deduplication**: Similar articles automatically merged (0.85+ cosine similarity)
- ✅ **Entity-based clustering**: Related topics grouped intelligently
- ✅ **Source weighting**: Premium sources (McKinsey, Gartner) weighted higher
- ✅ **Temporal filtering**: Recent articles prioritized (recency boost in scoring)

### Technical Stack
- Python 3.10+
- Anthropic Claude API (Sonnet 4.5)
- RSS feeds (100% automated, no web scraping)
- Streamlit web interface for viewing reports
- 61 news sources (expanded Oct 2025)

## Architecture Overview

```
61 News Sources → Scraper → Tier 1 Filter → Tier 2 Batch Eval → Tier 3 5D Eval → Ranking → Paraphraser → Report Formatter → Final Report
```

### Core Modules

1. **Web Scraper** (`modules/web_scraper.py`)
   - Fetches articles from 61 configured sources via RSS
   - Supports parallel scraping with caching
   - Returns: title, URL, content, publication date, source, language

2. **Article Filter** (`utils/article_filter.py`)
   - Tier 1 pre-filtering based on keywords and relevance
   - Quick keyword matching against category aliases
   - Configurable scoring threshold (default: 3.0)

3. **Batch Evaluator** (`modules/batch_evaluator.py`)
   - Tier 2 quick LLM-based evaluation
   - Scores 10 articles in parallel batches
   - Configurable pass score (default: 6.0)

4. **News Evaluator** (`modules/news_evaluator.py`)
   - Tier 3 deep evaluation with 5D scoring
   - Full analysis of article impact, relevance, credibility
   - Returns structured evaluation with scores and rationale

5. **Scoring Engine** (`utils/scoring_engine.py`)
   - Applies 5D weights to evaluation scores
   - Calculates final weighted rank (0-10 scale)
   - Handles deduplication and semantic clustering

6. **Article Paraphraser** (`modules/article_paraphraser.py`)
   - Condenses articles into 500-600 character deep analysis
   - Multi-paragraph format with structured sections
   - Mandarin Chinese output with professional tone

7. **Report Formatter** (`modules/report_formatter.py`)
   - Compiles all articles into final Markdown report
   - Generates executive summary and key insights
   - Uses Jinja2 template for consistent formatting

## Project Structure

```
briefAI/
├── README.md                      # Project overview and quick start
├── CLAUDE.md                      # This file - detailed specification
├── ARCHITECTURE.md                # System architecture & data flow
├── PROMPTS.md                     # LLM prompt templates
├── app.py                         # Streamlit web interface
├── main.py                        # Legacy CLI orchestrator
├── run_pipeline_with_categories.py # Pipeline runner with 5D scoring
├── requirements.txt               # Python dependencies
├── .env                          # API keys and configuration
├── config/
│   ├── sources.json              # 61 news sources configuration
│   ├── categories.json           # Business category taxonomy
│   ├── user_profile.md           # User preferences
│   └── report_template.md        # Jinja2 report template
├── modules/
│   ├── category_selector.py      # Category parsing from user input
│   ├── web_scraper.py            # Article scraping from 61 sources
│   ├── article_filter.py         # Tier 1 pre-filtering
│   ├── batch_evaluator.py        # Tier 2 batch LLM evaluation
│   ├── news_evaluator.py         # Tier 3 5D evaluation
│   ├── article_paraphraser.py    # 500-600 char deep analysis
│   └── report_formatter.py       # Final report generation
├── utils/
│   ├── llm_client.py             # Anthropic API wrapper
│   ├── llm_client_enhanced.py    # Enhanced LLM client with provider fallback
│   ├── claude_client.py          # Backup Claude API client
│   ├── cache_manager.py          # Article and evaluation caching
│   ├── scoring_engine.py         # 5D weighting and ranking
│   ├── context_retriever.py      # Context retrieval for search
│   ├── provider_switcher.py      # LLM provider switching
│   ├── category_loader.py        # Category loading utilities
│   └── logger.py                 # Logging configuration
├── data/
│   ├── cache/                    # Cached articles & evaluations
│   ├── reports/                  # Generated Markdown reports
│   └── chroma_db/                # Vector database for semantic search
├── docs/
│   ├── CLAUDE_CLIENT_API.md      # API documentation
│   ├── CATEGORY_SELECTOR_API.md  # Category selector API
│   └── CLAUDE_CLIENT_QUICKREF.md # Quick reference guide
└── logs/                         # Application logs
```

## Quick Start

### Installation

```bash
# Clone repository and setup
cd briefAI
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure API keys
echo "ANTHROPIC_API_KEY=your_key_here" > .env
```

### Running the Pipeline

```bash
# Generate a new report with full pipeline (5D scoring, 500-600 char analysis)
python3 run_pipeline_with_categories.py --top-n 12

# View reports on Streamlit web interface
streamlit run app.py
```

### Expected Output

- **Location**: `data/reports/ai_briefing_YYYYMMDD_cn.md`
- **Format**: Markdown with Mandarin Chinese content
- **Size**: 10-15 articles with 5D ranking
- **Analysis**: 500-600 characters per article
- **Time**: ~5-10 minutes for complete pipeline

## News Sources (61 Total)

### Official Company Blogs (6)
- OpenAI, Anthropic, Google DeepMind, Meta AI, Microsoft AI, Hugging Face

### Industry Research (6)
- McKinsey AI & Analytics, BCG, Deloitte, EY, PwC, Accenture

### Regional Tech News (11)
- **Asia-Pacific**: TechInAsia, Rest of World, DealStreetAsia, e27, Nikkei Asia, SCMP
- **Spain/Mexico**: Xataka, La Vanguardia, México Business News, América Economía, Entrepreneur Latin America

### General AI & Tech News (32)
- TechCrunch, Techmeme, VentureBeat, CB Insights, Hacker News, Product Hunt, and 26 specialized newsletters

**All sources use RSS feeds (100% automated, no fragile web scraping)**

## Key Improvements (October 2025)

✅ **Removed 6 broken Chinese sources** - Now 100% English language coverage
✅ **Added 23 new premium sources** - Industry research, company blogs, regional coverage
✅ **Implemented 5D scoring** - Sophisticated multi-dimensional ranking system
✅ **Deep analysis format** - 500-600 character analysis (vs previous 150-250)
✅ **Streamlit web interface** - Beautiful dashboard for report browsing
✅ **Parser improvements** - Correctly extracts full deep analysis content

## Configuration

### Key Environment Variables

```bash
ANTHROPIC_API_KEY=your_api_key         # Required: Claude API access
DEFAULT_CATEGORIES=fintech_ai,llm_tech,emerging_products
REPORT_OUTPUT_DIR=./data/reports       # Report output location
CACHE_DIR=./data/cache                 # Cache directory
LOG_LEVEL=INFO                         # Logging level
```

### News Sources Configuration

Edit `config/sources.json` to:
- Add/remove sources
- Adjust credibility scores (1-10)
- Modify relevance weights (1-10)
- Configure category mappings
- Enable/disable specific sources

### Category Configuration

Edit `config/categories.json` to define:
- Business categories (e.g., fintech_ai, llm_tech, emerging_products)
- Keywords and aliases
- Priority levels
- Focus tags

## Success Metrics

✅ **Report Quality**: 10-15 high-quality articles per briefing
✅ **Content**: All Mandarin Chinese with professional tone
✅ **Analysis Depth**: 500-600 characters per article (3-4 paragraphs)
✅ **Accuracy**: 95%+ factually accurate, no hallucinations
✅ **Speed**: Complete pipeline in 5-10 minutes
✅ **Format**: Professional Markdown, ready for executive distribution
✅ **Ranking**: Articles ranked by 5D weighted scores

## Cost Analysis

**Per weekly report:**
- ~60,000-80,000 tokens (all processing)
- Cost: $0.50-$1.00 per report
- Monthly: ~$2-4 for weekly briefings

**Very affordable for executive intelligence!**

## Deployment

### Local Development
```bash
streamlit run app.py --logger.level=debug
# Opens at http://localhost:8501
```

### Production
- Deploy on Streamlit Cloud (free tier available)
- Configure scheduled pipelines (cron jobs)
- Email reports automatically on Friday mornings
- Archive reports for trend analysis

## Important Notes

- ✅ System is **fully functional** and generating reports weekly
- ✅ **61 English-language sources** providing global AI industry coverage
- ✅ Reports in **Mandarin Chinese** with 500-600 character deep analysis
- ✅ Uses **Claude Sonnet 4.5** for all intelligent processing
- ✅ **Streamlit web interface** for viewing and searching reports
- ✅ **100% RSS-based** (no fragile web scraping)
- ✅ Regional focus on China, Indonesia, Philippines, Spain, Mexico

## Troubleshooting

**No articles found?**
- Check `.env` file for valid `ANTHROPIC_API_KEY`
- Verify internet connection for RSS feeds
- Check `data/cache/` for cached articles

**Low report quality?**
- Adjust scoring thresholds in module configs
- Review category definitions in `config/categories.json`
- Check source weights in `config/sources.json`

**LLM errors?**
- Verify API key is active and has quota
- Check rate limits (may need to add delays)
- Review logs in `logs/` directory

## Support & Documentation

- **ARCHITECTURE.md** - Complete system design and data flow
- **PROMPTS.md** - All LLM prompt templates used in the system
- **README.md** - Quick start guide and project overview
- **docs/** - Detailed API documentation for each module

---

**Status**: Production-ready | **Last Updated**: October 2025 | **Sources**: 61 | **Analysis**: 5D Scoring + 500-600 chars
