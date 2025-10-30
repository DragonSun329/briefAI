# BriefAI Project Restructure Plan

## Overview

Split briefAI into two independent programs under one project:
1. **Pipeline**: Report generation (batch processing, cron-scheduled)
2. **WebApp**: Streamlit interface + Ask function (user-facing, always-on)

## Current Issues

- Monolithic structure makes maintenance difficult
- Pipeline and webapp have different deployment needs
- Paywalled sources fail silently (lost articles)
- Mixed dependencies cause conflicts

## Proposed Structure

```
briefAI/
├── pipeline/                          # Report Generation System
│   ├── run_pipeline.py               # Main entry point (moved from root)
│   ├── config/                        # Pipeline-specific config
│   │   ├── sources.json
│   │   ├── categories.json
│   │   ├── providers.json
│   │   └── user_profile.md
│   ├── modules/                       # Scraper, evaluator, paraphraser
│   ├── orchestrator/                  # ACE orchestrator
│   └── requirements.txt              # Pipeline dependencies
│
├── webapp/                            # Streamlit Application
│   ├── app.py                        # Main Streamlit app (moved from root)
│   ├── pages/                        # Multi-page support
│   │   ├── 1_ask.py                 # Q&A function
│   │   ├── 2_search.py              # Article search
│   │   └── 3_analytics.py           # Usage analytics
│   ├── components/                   # Reusable UI components
│   │   ├── article_card.py
│   │   ├── search_filters.py
│   │   └── context_enrichment.py
│   └── requirements.txt              # Webapp dependencies
│
├── shared/                            # Shared Code & Data
│   ├── utils/                        # Shared utilities
│   │   ├── llm_provider.py
│   │   ├── cache_manager.py
│   │   ├── context_retriever.py
│   │   └── scoring_engine.py
│   ├── data/                         # Shared data folder
│   │   ├── cache/
│   │   ├── reports/
│   │   └── chroma_db/
│   └── .env                          # Shared environment variables
│
├── scripts/                           # Utility Scripts
│   ├── setup.sh                      # Initial setup
│   ├── deploy_pipeline.sh            # Deploy pipeline to cron
│   └── deploy_webapp.sh              # Deploy webapp to cloud
│
├── docs/                              # Documentation
│   ├── ARCHITECTURE.md
│   ├── PIPELINE_README.md            # Pipeline-specific docs
│   └── WEBAPP_README.md              # Webapp-specific docs
│
├── .gitignore
├── README.md                          # Project overview
└── LICENSE
```

## Phase 1: Paywall Bypass Integration

### Implementation

Add to `modules/web_scraper.py`:

```python
def _scrape_with_paywall_bypass(
    self,
    source: Dict[str, Any],
    days_back: int
) -> List[Dict[str, Any]]:
    """
    Try normal RSS scrape first, fallback to paywallbuster if failed

    Args:
        source: Source configuration dict
        days_back: Number of days to look back

    Returns:
        List of scraped articles
    """
    # Step 1: Try normal RSS fetch
    articles = self._scrape_rss(source, days_back)

    # Step 2: Check if paywall bypass needed
    if (not articles or len(articles) == 0) and source.get('use_paywall_bypass', False):
        logger.warning(f"Normal scrape failed for {source['name']}, trying paywallbuster")

        original_url = source['rss_url']
        paywall_url = f"https://www.paywallbuster.com/?url={original_url}"

        # Create modified source with paywallbuster URL
        paywall_source = source.copy()
        paywall_source['rss_url'] = paywall_url

        # Retry with paywallbuster
        articles = self._scrape_rss(paywall_source, days_back)

        if articles:
            logger.info(f"✅ Paywallbuster success: {len(articles)} articles from {source['name']}")
            # Mark articles as coming from paywall bypass
            for article in articles:
                article['scraped_via_paywall_bypass'] = True
        else:
            logger.warning(f"❌ Paywallbuster also failed for {source['name']}")

    return articles
```

### Configuration Changes

Add `use_paywall_bypass` flag to `config/sources.json`:

```json
{
  "name": "Wall Street Journal AI",
  "rss_url": "https://www.wsj.com/xml/rss/3_7455.xml",
  "category": "ai_companies",
  "credibility_score": 9,
  "relevance_weight": 10,
  "enabled": true,
  "use_paywall_bypass": true  // NEW FLAG
}
```

### Known Paywalled Sources

Update these sources in `sources.json` with `use_paywall_bypass: true`:
- Wall Street Journal
- Financial Times
- The Economist
- Harvard Business Review
- MIT Technology Review (some articles)
- Bloomberg (some articles)

## Phase 2: Project Restructure

### Migration Steps

#### Step 1: Create New Directory Structure

```bash
# Create directories
mkdir -p pipeline/{config,modules,orchestrator,utils}
mkdir -p webapp/{pages,components}
mkdir -p shared/{utils,data/{cache,reports,chroma_db}}
mkdir -p scripts docs
```

#### Step 2: Move Files

**Pipeline Files:**
```bash
# Move pipeline-specific files
mv run_orchestrated_pipeline.py pipeline/run_pipeline.py
mv config/* pipeline/config/
mv modules/* pipeline/modules/
mv orchestrator/* pipeline/orchestrator/

# Move shared utilities that pipeline uses
cp utils/{llm_provider,cache_manager,context_retriever}.py shared/utils/
```

**Webapp Files:**
```bash
# Move Streamlit app
mv app.py webapp/app.py

# Create multi-page structure
# (Extract ask function, search function into separate pages)
```

**Shared Resources:**
```bash
# Move shared data
mv data/* shared/data/
mv .env shared/.env
```

#### Step 3: Update Import Paths

**Pipeline imports:**
```python
# Old: from utils.llm_provider import KimiProvider
# New:
import sys
sys.path.insert(0, '../shared')
from utils.llm_provider import KimiProvider
```

**Webapp imports:**
```python
# Old: from utils.context_retriever import ContextRetriever
# New:
import sys
sys.path.insert(0, '../shared')
from utils.context_retriever import ContextRetriever
```

#### Step 4: Create Separate Requirements Files

**pipeline/requirements.txt:**
```
feedparser>=6.0.0
beautifulsoup4>=4.12.0
loguru>=0.7.0
anthropic>=0.25.0
openai>=1.30.0
chromadb>=0.4.0
requests>=2.31.0
python-dotenv>=1.0.0
```

**webapp/requirements.txt:**
```
streamlit>=1.32.0
loguru>=0.7.0
anthropic>=0.25.0
openai>=1.30.0
chromadb>=0.4.0
python-dotenv>=1.0.0
```

### Deployment Strategy

**Pipeline Deployment (Cron):**
```bash
# Add to crontab
0 9 * * FRI cd /path/to/briefAI/pipeline && python3 run_pipeline.py --top-n 12
```

**Webapp Deployment (Streamlit Cloud):**
```bash
# Streamlit Cloud configuration
# Main file: webapp/app.py
# Python version: 3.10+
# Requirements: webapp/requirements.txt
```

## Benefits

### Split Architecture

✅ **Independent Deployment**
- Pipeline runs on cron (Friday mornings)
- Webapp runs 24/7 on Streamlit Cloud
- Update one without affecting other

✅ **Resource Isolation**
- Pipeline uses heavy processing (scraping, LLM calls)
- Webapp uses light resources (read-only queries)
- No resource contention

✅ **Easier Maintenance**
- Clear separation of concerns
- Focused testing for each component
- Simpler debugging

✅ **Scalability**
- Can run multiple pipeline instances
- Webapp scales independently
- Add more features without bloat

### Paywall Bypass

✅ **More Articles**
- Access 10-20% more sources
- Previously unavailable premium content
- Automatic retry for paywalled sources

✅ **Better Coverage**
- WSJ, FT, Economist now accessible
- Higher quality sources included
- More comprehensive briefings

✅ **Zero Configuration**
- Automatic fallback on failure
- No manual intervention needed
- Configurable per-source

## Implementation Timeline

### Week 1: Paywall Bypass
- [ ] Add `_scrape_with_paywall_bypass()` method
- [ ] Update `sources.json` with flags
- [ ] Test with known paywalled sources
- [ ] Monitor success rates

### Week 2: Project Restructure
- [ ] Create new directory structure
- [ ] Move files to new locations
- [ ] Update all import paths
- [ ] Create separate requirements files
- [ ] Test pipeline independently
- [ ] Test webapp independently

### Week 3: Deployment & Documentation
- [ ] Setup cron for pipeline
- [ ] Deploy webapp to Streamlit Cloud
- [ ] Update documentation
- [ ] Create deployment scripts
- [ ] Final testing

## Testing Plan

### Paywall Bypass Testing

```python
# Test specific paywalled source
python3 -c "
from modules.web_scraper import WebScraper

scraper = WebScraper()
articles = scraper._scrape_with_paywall_bypass(
    {
        'name': 'WSJ AI',
        'rss_url': 'https://www.wsj.com/xml/rss/3_7455.xml',
        'use_paywall_bypass': True
    },
    days_back=7
)
print(f'Articles found: {len(articles)}')
"
```

### Split Architecture Testing

```bash
# Test pipeline independently
cd pipeline
python3 run_pipeline.py --top-n 5

# Test webapp independently
cd webapp
streamlit run app.py
```

## Rollback Plan

If issues occur:

1. **Paywall Bypass**: Set `use_paywall_bypass: false` in sources.json
2. **Project Restructure**: Keep old structure in `main` branch, new structure in `restructure` branch until proven stable

## Notes

- Keep both structures working during transition
- Use feature branches for major changes
- Test thoroughly before merging to main
- Document all breaking changes

## Questions for Review

1. Should we keep old structure in a `legacy/` folder?
2. Any other components that should be in `shared/`?
3. Should we add CI/CD pipelines for automated testing?
4. Any additional paywall bypass services to try besides paywallbuster?

---

**Status**: Planning Phase
**Created**: 2025-10-30
**Author**: Claude (AI Assistant)
