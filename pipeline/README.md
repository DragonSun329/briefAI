# Pipeline - AI Briefing Report Generator

This directory contains the **report generation pipeline** for the weekly AI industry briefing system.

## Purpose

Generate high-quality, CEO-ready AI industry briefings in Mandarin Chinese by:
1. Scraping articles from 86 global news sources
2. Intelligent 3-tier filtering (keyword → batch LLM → deep 5D evaluation)
3. Ranking articles by 5D weighted scores
4. Generating 500-600 character deep analysis per article
5. Creating professional Markdown reports

## Running the Pipeline

### Quick Start

```bash
cd pipeline
./run_pipeline.sh
```

### Manual Run

```bash
cd pipeline
python3 run_pipeline.py --top-n 12
```

### Options

```bash
python3 run_pipeline.py --help

Options:
  --top-n N           Number of top articles to include (default: 12)
  --categories CATS   Comma-separated categories (default: from .env)
  --days-back N       Scrape articles from last N days (default: 7)
  --no-cache          Disable caching
  --resume            Resume from checkpoint if available
```

## Architecture

### Modules

- **web_scraper.py** - Scrapes 86 news sources via RSS feeds
- **batch_evaluator.py** - Tier 2 batch LLM evaluation (6.0 threshold)
- **news_evaluator.py** - Tier 3 deep 5D evaluation
- **article_paraphraser.py** - Generates 500-600 char deep analysis
- **report_formatter.py** - Creates final Markdown report
- **category_selector.py** - Parses business categories
- **entity_background_agent.py** - Provides entity context

### Orchestrator

The `orchestrator/` directory contains the ACE (Autonomous Cognitive Engine) orchestrator:
- 10-phase pipeline with adaptive context
- Error tracking and retry logic
- Checkpoint/resume functionality
- Comprehensive metrics and logging

### Dependencies

Imports from `../shared/`:
- `utils/` - LLM clients, cache manager, scoring engine, etc.
- `config/` - sources.json, categories.json, providers.json
- `data/` - cache/, reports/, chroma_db/

## Output

Reports are generated in: `../data/reports/ai_briefing_YYYYMMDD_cn.md`

Example output:
- 10-15 articles with 5D ranking
- 500-600 character analysis per article
- Professional Mandarin Chinese tone
- Ready for CEO distribution

## Scheduling

Run weekly using cron:

```bash
# Add to crontab: Run every Friday at 9am
0 9 * * 5 cd /path/to/briefAI/pipeline && ./run_pipeline.sh
```

## Configuration

Edit `../config/sources.json` to:
- Add/remove news sources
- Adjust credibility scores
- Enable paywall bypass
- Configure category mappings

Edit `../config/categories.json` to define business categories and keywords.

## Monitoring

Check logs in: `../logs/pipeline_YYYYMMDD.log`

## Troubleshooting

**No articles found?**
- Check `.env` file for valid `ANTHROPIC_API_KEY` or `OPENROUTER_API_KEY`
- Verify internet connection for RSS feeds
- Check `../data/cache/` for cached articles

**Pipeline hangs?**
- Use `--resume` flag to continue from checkpoint
- Check logs for timeout errors
- Reduce `--top-n` if processing too many articles

**Low report quality?**
- Adjust scoring thresholds in module configs
- Review category definitions in `../config/categories.json`
- Check source weights in `../config/sources.json`
