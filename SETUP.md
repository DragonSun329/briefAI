# Setup Guide

Complete setup instructions for the AI Industry Weekly Briefing Agent.

## Prerequisites

- Python 3.8 or higher
- Moonshot AI (Kimi) API key ([Get one here](https://platform.moonshot.cn/))
- Internet connection for scraping news sources

## Installation Steps

### 1. Clone or Download the Project

```bash
cd /Users/dragonsun/briefAI
```

### 2. Create Virtual Environment (Recommended)

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure API Key

Edit the `.env` file and add your Moonshot API key:

```bash
MOONSHOT_API_KEY=your_actual_api_key_here
```

**Getting your API key:**
1. Visit https://platform.moonshot.cn/
2. Register/login to your account
3. Navigate to API Keys section
4. Create a new API key
5. Copy and paste it into `.env`

### 5. Verify Installation

Check that all dependencies are installed:

```bash
python -c "import openai, requests, feedparser, jinja2, loguru; print('✅ All dependencies installed')"
```

## Configuration

### Categories Configuration

The system is pre-configured for fintech business. Edit `config/categories.json` to customize:

```json
{
  "categories": [
    {
      "id": "fintech_ai",
      "name": "金融科技AI应用",
      "aliases": ["金融AI", "fintech", "智能风控", "信贷"],
      "priority": 10
    }
  ],
  "company_context": {
    "business": "智能风控信贷",
    "industry": "金融科技 (Fintech)",
    "focus_areas": ["风险控制", "信贷决策", "数据分析"]
  }
}
```

### News Sources Configuration

Edit `config/sources.json` to add/remove news sources:

```json
{
  "sources": [
    {
      "id": "36kr_fintech",
      "name": "36氪 金融科技",
      "url": "https://36kr.com/information/fintech",
      "type": "web",
      "enabled": true,
      "relevance_weight": 10,
      "focus_tags": ["fintech", "风控", "信贷"]
    }
  ]
}
```

**Key fields:**
- `relevance_weight` (1-10): Higher = more priority in ranking
- `credibility_score` (1-10): Source trustworthiness
- `enabled`: Set to `false` to disable a source

### Report Template

Customize the report format by editing `config/report_template.md`.

## Usage

### Interactive Mode (Recommended for First Use)

```bash
python main.py --interactive
```

This will prompt you for:
1. Categories you want to focus on
2. Time range (how many days back)
3. Number of articles in the report

### Quick Start with Defaults

```bash
python main.py --defaults
```

Uses default categories: 金融科技AI, 数据分析, 智能营销

### Custom Category Input

```bash
python main.py --input "我想了解智能风控和数据分析"
```

### Advanced Options

```bash
# Last 3 days, top 10 articles
python main.py --defaults --days 3 --top 10

# Disable cache (force fresh scraping)
python main.py --defaults --no-cache

# Enable debug logging
python main.py --defaults --log-level DEBUG
```

### Command-Line Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--interactive`, `-i` | Interactive mode | - |
| `--input TEXT` | Natural language category preferences | - |
| `--defaults`, `-d` | Use default categories | - |
| `--days N` | Days to look back | 7 |
| `--top N` | Number of articles in report | 15 |
| `--no-cache` | Disable caching | False |
| `--log-level LEVEL` | Logging level (DEBUG/INFO/WARNING/ERROR) | INFO |

## Output

Reports are saved to `./data/reports/` with filename format:
```
ai_briefing_YYYYMMDD.md
```

Example: `ai_briefing_20241025.md`

## Troubleshooting

### Error: "MOONSHOT_API_KEY not found"

**Solution:** Make sure you've created `.env` file and added your API key.

### Error: "No articles found"

**Possible causes:**
1. News sources are unreachable
2. Source URLs have changed
3. Network connectivity issues

**Solution:**
- Check `config/sources.json` URLs are valid
- Try running with `--no-cache` to force fresh scraping
- Check logs in `./data/logs/`

### Error: "Failed to evaluate article"

**Possible causes:**
1. API key is invalid
2. API rate limit exceeded
3. API service is down

**Solution:**
- Verify API key is correct
- Check your Moonshot account has sufficient credits
- Wait a few minutes and try again

### Performance is slow

**Tips:**
- Enable caching (default) to reuse scraped articles
- Reduce `--top` number to process fewer articles
- Use `--days 3` for shorter time range

## Cost Estimation

Based on Kimi pricing (¥12/M tokens):

**Typical weekly report (15 articles, 7 days):**
- Category selection: ~1K tokens (¥0.01)
- Article evaluation: ~150K tokens (¥1.80)
- Article paraphrasing: ~100K tokens (¥1.20)
- Report formatting: ~50K tokens (¥0.60)

**Total cost: ~¥3.60 (~$0.50 USD) per report**

With caching enabled, repeated runs cost ~¥0.50 (~$0.07 USD).

## Next Steps

1. **Test the system**: Run `python main.py --interactive` to generate your first report
2. **Customize categories**: Edit `config/categories.json` to match your interests
3. **Add news sources**: Edit `config/sources.json` to add relevant sources
4. **Schedule automation**: Set up a cron job or scheduled task to run weekly

### Example Cron Job (Weekly on Monday 9am)

```bash
# Edit crontab
crontab -e

# Add this line:
0 9 * * 1 cd /Users/dragonsun/briefAI && /path/to/venv/bin/python main.py --defaults
```

## Support

For issues or questions:
1. Check the logs in `./data/logs/`
2. Review [ARCHITECTURE.md](ARCHITECTURE.md) for system design
3. Review [KIMI_MIGRATION.md](KIMI_MIGRATION.md) for LLM details
4. Review [FINTECH_CUSTOMIZATION.md](FINTECH_CUSTOMIZATION.md) for customization details
