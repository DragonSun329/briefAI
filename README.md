# briefAI - AI Industry Weekly Briefing Agent

Automatically generate professional weekly AI industry briefings in Mandarin Chinese for executive review. Scrapes 61 global news sources, applies intelligent 5D weighted scoring, generates 500-600 character deep analysis per article, and produces beautiful Markdown reports ready for CEO distribution.

**Built for:** China, Indonesia, Philippines, Spain, Mexico market analysis
**Status:** Production-ready | **Updated:** October 2025

## Quick Features

✅ **61 Global News Sources** - Official company blogs (OpenAI, Anthropic, DeepMind, Meta, Microsoft, Hugging Face), industry research (McKinsey, BCG, Deloitte, EY, PwC, Accenture), regional tech news (TechInAsia, DealStreetAsia, e27, SCMP, Xataka, and more)

✅ **5D Weighted Scoring** - Market Impact (25%), Competitive Impact (20%), Strategic Relevance (20%), Operational Relevance (15%), Credibility (10%)

✅ **Deep Analysis** - 500-600 characters per article with multi-paragraph format covering central argument, evidence, mechanisms, impact, and strategic risks

✅ **Mandarin Chinese** - All reports generated in professional Chinese with analytical-inspiring tone

✅ **Web Interface** - Beautiful Streamlit dashboard for browsing and searching reports

✅ **100% RSS-Based** - No fragile web scraping, automatic parallel fetching from all sources

✅ **Smart Filtering** - 3-tier intelligent filtering system (keyword-based → LLM quick eval → 5D deep eval)

## Getting Started

### Installation

```bash
# Clone and setup
git clone https://github.com/yourusername/briefAI.git
cd briefAI

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -r requirements.txt

# Configure API key
echo "ANTHROPIC_API_KEY=your_anthropic_api_key_here" > .env
```

### Running the Pipeline

```bash
# Generate a new report with full 5D scoring and deep analysis
python3 run_pipeline_with_categories.py --top-n 12

# View reports on web interface
streamlit run app.py
# Opens at http://localhost:8501
```

### Expected Output

- **Location**: `data/reports/ai_briefing_YYYYMMDD_cn.md`
- **Format**: Markdown with Mandarin Chinese content
- **Content**: 10-15 articles with 5D ranking and 500-600 char analysis
- **Time**: ~5-10 minutes for complete pipeline

## How It Works

### 1. Scraping (61 Sources)

Fetches fresh articles from:
- **Official Blogs (6)**: OpenAI, Anthropic, DeepMind, Meta, Microsoft, Hugging Face
- **Research Firms (6)**: McKinsey, BCG, Deloitte, EY, PwC, Accenture
- **Regional News (11)**: TechInAsia, Rest of World, DealStreetAsia, e27, Nikkei Asia, SCMP, Xataka, La Vanguardia, and more
- **AI News (32)**: TechCrunch, Techmeme, VentureBeat, Hacker News, and 28 specialized newsletters

### 2. Filtering (3-Tier System)

**Tier 1 - Pre-Filter** (Keyword-based)
- Quick matching against category keywords
- Threshold: 3.0/10
- Typical: 40/178 articles pass (22.5%)

**Tier 2 - Batch Evaluation** (LLM quick scoring)
- Fast LLM-based relevance check
- Threshold: 6.0/10
- Typical: 40/40 articles pass (100%)

**Tier 3 - Deep Evaluation** (5D weighted scoring)
- Full analysis with 5D scoring
- Selection: Top 10-15 articles
- Typical: 10/40 articles selected (25%)

### 3. Ranking (5D Weighting)

Articles ranked by weighted score:
- **Market Impact (25%)**: Industry-wide disruption potential
- **Competitive Impact (20%)**: Effect on competitive landscape
- **Strategic Relevance (20%)**: Alignment with business strategy
- **Operational Relevance (15%)**: Practical application value
- **Credibility (10%)**: Source reliability and evidence quality

### 4. Analysis (500-600 Characters)

Each article receives deep analysis including:
- Central argument & key data points
- Quantified impact & performance metrics
- Mechanism & differentiation from alternatives
- Practical use cases & business improvements
- Market significance & strategic risks

All in flowing paragraph format (never bullet points), 3-4 paragraphs, 500-600 Chinese characters.

### 5. Report Generation

Beautiful Markdown report with:
- Weekly overview & key trends
- Top 10 articles with 5D scores
- Full deep analysis per article
- Strategic insights & recommendations
- Professional formatting ready for CEO

## Project Structure

```
briefAI/
├── README.md                      # This file
├── CLAUDE.md                      # Detailed technical specification
├── ARCHITECTURE.md                # System architecture & data flow
├── PROMPTS.md                     # All LLM prompt templates
├── app.py                         # Streamlit web interface
├── run_pipeline_with_categories.py # Pipeline runner script
├── requirements.txt               # Python dependencies
├── .env                          # Configuration (API keys, etc.)
├── config/
│   ├── sources.json              # 61 news sources config
│   ├── categories.json           # Category taxonomy
│   ├── user_profile.md           # User preferences
│   └── report_template.md        # Jinja2 report template
├── modules/
│   ├── web_scraper.py            # Scrapes from 61 sources
│   ├── article_filter.py         # Tier 1 pre-filtering
│   ├── batch_evaluator.py        # Tier 2 LLM batch eval
│   ├── news_evaluator.py         # Tier 3 5D evaluation
│   ├── article_paraphraser.py    # 500-600 char analysis
│   └── report_formatter.py       # Final report generation
├── utils/
│   ├── llm_client_enhanced.py    # Claude API with fallback
│   ├── cache_manager.py          # Article & eval caching
│   ├── scoring_engine.py         # 5D weighting & ranking
│   ├── context_retriever.py      # Search & context retrieval
│   ├── provider_switcher.py      # LLM provider management
│   ├── category_loader.py        # Category utilities
│   └── logger.py                 # Logging configuration
├── data/
│   ├── cache/                    # Cached articles
│   ├── reports/                  # Generated Markdown reports
│   └── chroma_db/                # Vector database for search
├── docs/
│   ├── CLAUDE_CLIENT_API.md      # API documentation
│   ├── CATEGORY_SELECTOR_API.md  # Category selector docs
│   └── CLAUDE_CLIENT_QUICKREF.md # Quick reference
└── logs/                         # Application logs
```

## Key Files

| File | Purpose |
|------|---------|
| `CLAUDE.md` | Complete technical specification with architecture, modules, and config details |
| `ARCHITECTURE.md` | System design, data flow, technology stack, and deployment options |
| `PROMPTS.md` | All LLM prompt templates used throughout the system |
| `config/sources.json` | Configuration for 61 news sources (add/remove sources here) |
| `config/categories.json` | Business category definitions and keywords |
| `run_pipeline_with_categories.py` | Main pipeline runner - executes scraping → filtering → scoring → paraphrasing → reporting |

## Configuration

### Environment Variables

```bash
ANTHROPIC_API_KEY=your_key          # Required: Anthropic API access
DEFAULT_CATEGORIES=llm_tech,emerging_products
REPORT_OUTPUT_DIR=./data/reports    # Report output location
CACHE_DIR=./data/cache              # Cache directory
LOG_LEVEL=INFO                      # Logging level
```

### Add/Remove News Sources

Edit `config/sources.json`:
```json
{
  "id": "source_id",
  "name": "Source Name",
  "url": "https://example.com",
  "type": "rss",
  "rss_url": "https://example.com/feed.xml",
  "enabled": true,
  "credibility_score": 9,
  "relevance_weight": 10,
  "categories": ["category1", "category2"]
}
```

### Customize Categories

Edit `config/categories.json` to add business categories:
```json
{
  "id": "category_id",
  "name": "Category Name",
  "aliases": ["keyword1", "keyword2"],
  "priority": 10,
  "description": "Category description"
}
```

## Performance

**Report Generation Time**: 5-10 minutes (fully automated)

**Cost per Report**: $0.50-$1.00
- Scraping: Free (RSS feeds)
- Filtering: ~$0.15 (LLM Tier 2-3 evaluation)
- Paraphrasing: ~$0.35 (Claude Sonnet deep analysis)
- Total: $0.50-$1.00 per weekly report

**Monthly Cost**: ~$2-4 for weekly briefings

## News Sources (61 Total)

### Official Company Blogs (6)
OpenAI, Anthropic, Google DeepMind, Meta AI, Microsoft AI, Hugging Face

### Industry Research & Consulting (6)
McKinsey AI & Analytics, BCG AI & Analytics, Deloitte AI Insights, EY AI & Analytics, PwC AI Research, Accenture AI Blog

### Regional Tech News (11)
**Asia-Pacific**: TechInAsia, Rest of World, DealStreetAsia, e27 Southeast Asia, Nikkei Asia, SCMP Technology

**Spain/Mexico/Latin America**: Xataka, La Vanguardia Technology, México Business News, América Economía Tecnología, Entrepreneur Latin America

### General AI & Tech News (32)
TechCrunch, Techmeme, VentureBeat, CB Insights, Hacker News, Product Hunt, Indie Hackers, BetaList, There's An AI For That, FutureTools, and 22 specialized newsletters

**All 100% RSS-based (no web scraping)**

## Recent Updates (October 2025)

✅ **Removed 6 broken Chinese sources** - Eliminated non-working Chinese news feeds
✅ **Added 23 premium English sources** - Company blogs, research firms, regional coverage
✅ **Expanded to 61 sources** - From original 44
✅ **Implemented 5D scoring** - Sophisticated multi-dimensional article ranking
✅ **Deep analysis format** - Increased from 150-250 to 500-600 characters per article
✅ **Streamlit web interface** - Beautiful dashboard for report browsing
✅ **Parser improvements** - Correctly extracts and displays full analysis content

## Troubleshooting

### "No articles found"
- Verify `ANTHROPIC_API_KEY` in `.env` is valid
- Check internet connection for RSS feed access
- Look in `data/cache/` for cached articles

### "Rate limit errors"
- API quota may be exceeded
- Wait a few minutes and retry
- Check OpenRouter fallback provider in code

### "Low report quality"
- Adjust filtering thresholds in module code
- Review category keywords in `config/categories.json`
- Check source weights in `config/sources.json`
- Increase `--top-n` parameter to evaluate more articles

### "Memory errors"
- Reduce batch size for batch evaluator
- Clear old cache files: `rm data/cache/*.json`
- Run pipeline with `--limit-articles` parameter

## Documentation

- **CLAUDE.md** - Complete technical specification
- **ARCHITECTURE.md** - System design and technology stack
- **PROMPTS.md** - All LLM prompt templates
- **docs/** folder - API reference documentation

## Technology Stack

- **Language**: Python 3.10+
- **LLM**: Anthropic Claude Sonnet 4.5
- **Web Framework**: Streamlit (UI dashboard)
- **News Source**: RSS feeds (100 automated)
- **Caching**: JSON file-based cache
- **Vector DB**: Chromadb (semantic search)
- **Task Queue**: Sequential processing
- **Logging**: Loguru

## Deployment

### Local Development
```bash
streamlit run app.py --logger.level=debug
```

### Streamlit Cloud
```bash
# Push to GitHub, connect Streamlit Cloud to your repo
# Set ANTHROPIC_API_KEY as secret in Cloud settings
# Auto-deploys on push to main
```

### Docker
```bash
docker build -t briefai .
docker run -e ANTHROPIC_API_KEY=your_key briefai
```

### Scheduled Execution (Cron)
```bash
# Weekly at Friday 9 AM
0 9 * * FRI cd /path/to/briefAI && /usr/bin/python3 run_pipeline_with_categories.py --top-n 12
```

## Success Metrics

✅ **10-15 high-quality articles** per briefing
✅ **Mandarin Chinese** content with professional tone
✅ **500-600 characters** per article (deep analysis)
✅ **95%+ factually accurate** (no hallucinations)
✅ **5-10 minutes** for complete pipeline
✅ **Markdown format** ready for CEO distribution
✅ **5D ranked** by impact, relevance, credibility

## License

[Specify your license]

## Support

For detailed technical information, see:
- `CLAUDE.md` - Complete project specification
- `ARCHITECTURE.md` - System architecture details
- `PROMPTS.md` - LLM prompt templates
- GitHub Issues - Bug reports and feature requests

---

**Status**: Production-ready | **Last Updated**: October 28, 2025 | **Sources**: 61 | **Analysis**: 5D Scoring + 500-600 chars
