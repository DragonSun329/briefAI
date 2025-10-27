# Weekly Collection System Implementation

## Overview

Implemented a comprehensive weekly article collection and consolidation system that enables the briefing agent to run in **collection mode** (Days 1-6) and **finalization mode** (Day 7) for optimal token efficiency and comprehensive topic coverage.

**Expected Token Savings**: **90%** reduction compared to running full workflow daily
- Daily full workflow: 26,000 tokens × 7 days = 182,000 tokens/week
- New system: 3,000 tokens (collection) + 15,000 tokens (finalization) = 18,000 tokens/week

## Architecture

```
Days 1-6: COLLECTION MODE (Fast)
├─ Scrape articles
├─ Tier 1 pre-filter (0 tokens)
├─ Tier 2 batch eval (500 tokens/day)
└─ Save to weekly checkpoint

Day 7: FINALIZATION MODE (Thorough)
├─ Load all 7 days of collected articles
├─ Deduplicate by content + entities
├─ Re-rank by combined score
├─ Tier 3 full evaluation on top 30 (15,000 tokens)
├─ Select final 10-15 articles
├─ Paraphrase + generate report
└─ Publish weekly report
```

## Files Created/Modified

### 1. Enhanced `utils/checkpoint_manager.py` (NEW METHODS)

**Added weekly checkpoint support**:
- `create_weekly_checkpoint(week_id)` - Create new weekly checkpoint
- `load_weekly_checkpoint(week_id)` - Load existing weekly checkpoint
- `save_article_tier2_score()` - Save Tier 2 scores during collection
- `save_article_tier3_score()` - Save Tier 3 scores during finalization
- `get_articles_by_status(status)` - Filter articles by evaluation status
- `get_weekly_stats()` - Get statistics about weekly collection
- `merge_articles_from_checkpoint()` - Merge articles from multiple checkpoints
- `_status_rank()` - Helper to rank article evaluation completeness

**Checkpoint file format**:
```json
{
  "checkpoint_version": "2.0",
  "last_updated": "2025-10-25T18:45:32.123456",
  "week_id": "week_2025_43",
  "articles": {
    "article_id_1": {
      "article": { "title": "...", "url": "...", "content": "..." },
      "tier1_score": 5.2,
      "tier2_score": 7.5,
      "tier2_reasoning": "相关且重要",
      "collection_day": 3,
      "tier2_timestamp": "2025-10-23T10:30:00",
      "status": "tier2_evaluated"
    },
    "article_id_2": {
      "article": { ... },
      "tier2_score": 6.8,
      "tier3_scores": { "impact": 8, "relevance": 9, ... },
      "takeaway": "...",
      "tier3_timestamp": "2025-10-26T15:45:00",
      "status": "tier3_evaluated"
    }
  }
}
```

### 2. New `utils/weekly_utils.py` (280 lines)

**Purpose**: Week identification, day tracking, and scheduling helpers

**Key Methods**:
- `get_current_week_id()` → 'week_2025_43'
- `get_current_day_of_week()` → 1-7 (Monday-Sunday)
- `get_day_name(day)` → 'Monday', 'Tuesday', etc.
- `get_week_start_end()` → (start_datetime, end_datetime)
- `is_collection_day()` → True if Mon-Fri
- `is_finalization_day()` → True if Fri-Sat
- `days_until_finalization()` → Days remaining in week
- `format_week_range(week_id)` → 'Oct 20 - Oct 26, 2025'
- `get_collection_batch_id(week_id, day)` → 'collection_week_2025_43_day_3'
- `get_finalization_batch_id(week_id)` → 'finalization_week_2025_43'
- `should_trigger_finalization()` → True if Friday 6PM+ or Saturday
- `log_collection_status()` → Log daily collection progress
- `log_finalization_status()` → Log weekly finalization progress

**Example Usage**:
```python
from utils.weekly_utils import WeeklyUtils

# Get current week
week_id = WeeklyUtils.get_current_week_id()  # 'week_2025_43'

# Check if should collect
if WeeklyUtils.is_collection_day():
    # Run collection mode
    pass

# Check if should finalize
if WeeklyUtils.should_trigger_finalization():
    # Run finalization mode
    pass
```

### 3. New `utils/deduplication_utils.py` (330 lines)

**Purpose**: Detect and merge duplicate/similar articles collected during the week

**Key Methods**:
- `find_duplicate_articles(articles, strategy)` - Find potential duplicates
  - Strategies: 'title', 'content', 'entities', 'combined'
  - Returns: [(article_id_1, article_id_2, similarity_score), ...]

- `string_similarity(str1, str2)` - Calculate string similarity (0-1)

- `entity_overlap(entities1, entities2)` - Jaccard index of entity sets

- `merge_duplicate_articles(article1, article2, strategy)` - Merge articles
  - Strategies: 'prefer_higher_score', 'prefer_recent', 'combine'

- `deduplicate_articles(articles_dict, strategy)` - Deduplicate collection
  - Returns: (deduplicated_dict, removed_count)

- `rank_by_combined_score(articles)` - Re-rank articles
  - Combined score = (tier2_score × 0.4) + (recency × 0.4) + (trending × 0.2)
  - Returns: [(article_id, article_data, combined_score), ...]

**Thresholds**:
- Title similarity: 75% (for duplicate detection)
- Content similarity: 65%
- Entity overlap: 60% (Jaccard index)

**Example Usage**:
```python
from utils.deduplication_utils import DeduplicationUtils

# Find duplicates
duplicates = DeduplicationUtils.find_duplicate_articles(articles)

# Deduplicate collection
deduped, removed = DeduplicationUtils.deduplicate_articles(articles)

# Re-rank by combined score
ranked = DeduplicationUtils.rank_by_combined_score(deduped)
```

### 4. New `modules/collection_mode.py` (280 lines)

**Purpose**: Fast daily collection (Tier 1 + Tier 2 only)

**Workflow** (5 minutes/day):
```
Scrape articles
    ↓
Tier 1 pre-filter (0 tokens)
    ↓
Tier 2 batch eval (500 tokens)
    ↓
Save to weekly checkpoint
```

**Key Methods**:
- `collect_articles(articles, categories, week_id, day)` - Main entry point
  - Returns: {scraped, tier1_passed, tier2_passed, collected_articles, ...}

- `get_collection_summary(week_id)` - Get summary of weekly collection so far
  - Returns: {week_id, total_articles, by_collection_day: {...}}

- `log_collection_day_summary(week_id, day)` - Log day's results

**Example Usage**:
```python
from modules.collection_mode import CollectionMode

collector = CollectionMode()
result = collector.collect_articles(
    articles=articles,
    categories=categories,
    week_id='week_2025_43',
    day=3
)

# Result:
# {
#     'week_id': 'week_2025_43',
#     'day': 3,
#     'scraped': 52,
#     'tier1_passed': 18,
#     'tier2_passed': 10,
#     'collected_articles': [...],
#     'checkpoint_stats': {...}
# }
```

### 5. New `modules/finalization_mode.py` (310 lines)

**Purpose**: Week-end consolidation with expensive Tier 3 evaluation

**Workflow** (30 minutes/week):
```
Load all 7 days of collected articles
    ↓
Deduplicate by content + entities
    ↓
Re-rank by combined score
    ↓
Select top 30 candidates
    ↓
Tier 3 full evaluation (15,000 tokens)
    ↓
Select final 10-15 articles
    ↓
Paraphrase + generate report
```

**Key Methods**:
- `finalize_weekly_articles(week_id, categories, top_n)` - Main entry point
  - Returns: {week_id, total_collected, after_deduplication, final_articles, ...}

- `get_finalization_candidates(week_id, limit)` - Preview articles for Tier 3
  - Returns: [{id, title, tier2_score, combined_score, ...}, ...]

- `log_finalization_preview(week_id)` - Log preview of finalization

**Example Usage**:
```python
from modules.finalization_mode import FinalizationMode

finalizer = FinalizationMode(news_evaluator=evaluator)
result = finalizer.finalize_weekly_articles(
    week_id='week_2025_43',
    categories=categories,
    top_n=15
)

# Result:
# {
#     'week_id': 'week_2025_43',
#     'total_collected': 150,
#     'after_deduplication': 120,
#     'tier3_candidates': 30,
#     'final_articles': [...],  # 15 articles
#     'checkpoint_stats': {...}
# }
```

### 6. Updated `main.py`

**New Imports**:
```python
from typing import Dict, Any
from utils.weekly_utils import WeeklyUtils
from modules.collection_mode import CollectionMode
from modules.finalization_mode import FinalizationMode
```

**New BriefingAgent Methods**:
- `run_collection_mode(user_input, use_defaults, days_back, week_id, day)`
  - Runs fast collection (Tier 1 + Tier 2)

- `run_finalization_mode(week_id, user_input, use_defaults, top_n)`
  - Runs full finalization (Dedup + Tier 3 + Report)

**New Command-Line Arguments**:
```
--collect              Run in collection mode (Days 1-6)
--finalize             Run in finalization mode (Day 7)
--week WEEK_ID         Week ID for collection/finalization
--day DAY_NUMBER       Day number for collection (1-7)
```

**New Usage Examples**:
```bash
# Daily collection (Monday-Friday)
python main.py --defaults --collect
python main.py --defaults --collect --day 3  # Specific day

# Weekly finalization (Friday evening or Saturday)
python main.py --defaults --finalize
python main.py --defaults --finalize --week week_2025_43  # Specific week
```

## Weekly Workflow

### Day 1-6: Collection (5 minutes/day, ~500 tokens/day)

```bash
# Run in morning to collect new articles
python main.py --defaults --collect

# OR with time-based scheduling (cron)
0 9 * * 1-5 cd /path/to/briefAI && python main.py --defaults --collect
```

**What happens**:
1. Scrapes articles from all sources (50+ articles)
2. Tier 1 pre-filters to ~18 articles (0 tokens)
3. Tier 2 batch evaluates to ~10 articles (~500 tokens)
4. Saves to weekly checkpoint: `./data/cache/weekly_week_2025_43.json`
5. Runs in ~5 minutes

**Total token cost**: ~500 tokens/day × 6 days = 3,000 tokens

### Day 7: Finalization (30 minutes/week, ~15,000 tokens)

```bash
# Run Friday evening or Saturday morning
python main.py --defaults --finalize

# OR with automatic scheduling
0 18 * * 5 cd /path/to/briefAI && python main.py --defaults --finalize
```

**What happens**:
1. Loads all 150 articles collected Days 1-6
2. Deduplicates by content similarity → ~120 unique articles
3. Re-ranks by combined score (tier2 + recency + trending)
4. Tier 3 full evaluates top 30 candidates (~15,000 tokens)
5. Selects final 10-15 articles
6. Paraphrases articles
7. Generates final Markdown report
8. Saves to: `./data/reports/weekly_briefing_week_2025_43.md`
9. Saves Tier 3 scores back to checkpoint

**Total token cost**: ~15,000 tokens

**Total weekly cost**: 3,000 + 15,000 = **18,000 tokens** (vs 182,000 for daily full workflow)

## Configuration

No new `.env` variables needed - uses existing tier configuration:
```env
# Tier 1: Pre-filter threshold (aggressive = 4.0)
TIER1_SCORE_THRESHOLD=4.0

# Tier 2: Batch evaluation
TIER2_BATCH_SIZE=10
TIER2_PASS_SCORE=6.0
```

## Checkpoint Files

Weekly checkpoints saved to: `./data/cache/weekly_YYYY_WW.json`

Examples:
- `weekly_2025_43.json` - Week 43 of 2025
- `weekly_2025_44.json` - Week 44 of 2025

Each checkpoint contains articles with progressive evaluation:
- **After collection**: `tier2_score`, `tier2_reasoning`
- **After finalization**: `tier3_scores`, `takeaway`

## Logging

New log messages show collection progress:

```
[COLLECTION MODE] Starting daily collection for week_2025_43 (Day Monday)
[COLLECTION] Tier 1 results: 18/52 articles passed (threshold: 4.0)
[COLLECTION] Tier 2 results: 10/18 articles passed
[COLLECTION SUMMARY] Monday (Day 1): 10 articles collected

[FINALIZATION MODE] Starting week finalization for week_2025_43
[FINALIZATION] Loaded 150 articles from week week_2025_43
[FINALIZATION] After deduplication: 120 articles (removed 30 duplicates)
[FINALIZATION] Re-ranking articles by combined score...
[FINALIZATION] Running Tier 3 full evaluation on 30 candidates...
[FINALIZATION PREVIEW] Top 10 candidates...
```

## Testing the Weekly System

### Phase 1: Test Collection Mode

```bash
# Monday-Friday morning
python main.py --defaults --collect

# Check logs for daily progress
tail -f ./data/logs/briefing_agent.log

# Verify checkpoint created
ls -la ./data/cache/weekly_*.json
```

### Phase 2: Test Finalization Mode

```bash
# Friday evening or Saturday
python main.py --defaults --finalize

# Check generated report
cat ./data/reports/weekly_briefing_*.md

# Verify weekly stats
tail -f ./data/logs/briefing_agent.log
```

### Phase 3: Verify Token Savings

```bash
# Compare token usage between:
# 1. Old system: 7 × python main.py --defaults (26k tokens each)
# 2. New system: 6 × python main.py --collect + python main.py --finalize

# Check LLM stats in logs:
# "💰 LLM API Usage Statistics:"
```

## Future Enhancements

### Phase 2 (After testing):
1. **Automatic scheduling** - Cron jobs for daily collection and Friday finalization
2. **Email integration** - Auto-send finalized report via email
3. **Dynamic thresholds** - Adjust tier scores based on article count
4. **Learning from feedback** - Track CEO feedback to improve filtering

### Phase 3 (Advanced):
1. **Cache Tier 1 scores** - Don't re-evaluate articles from previous weeks
2. **Multi-week trends** - Show trending topics across multiple weeks
3. **Real-time updates** - Push notifications for breaking hot topics
4. **Provider optimization** - Larger batches for cheaper models during collection

## Summary

✅ **Complete weekly collection system implemented**:
- Enhanced checkpoint manager for weekly tracking
- Week ID generation and day detection utilities
- Duplicate detection and article deduplication
- Fast collection mode (Tier 1+2 only)
- Full finalization mode with Tier 3 evaluation
- Command-line integration with --collect and --finalize flags
- Comprehensive logging and progress tracking

✅ **Expected results**:
- 90% token reduction (18,000 vs 182,000 tokens/week)
- Better topic coverage (accumulate all week)
- Higher quality final report (7 days of data)
- Fast daily runs (5 minutes/day)
- Thorough weekly finalization (30 minutes/week)

✅ **Ready to deploy**:
Run daily collection Monday-Friday, finalize Friday evening or Saturday morning!

## Example Cron Schedule

```bash
# Add to crontab (crontab -e)

# Monday-Friday morning: Collection mode (9 AM)
0 9 * * 1-5 cd /path/to/briefAI && python main.py --defaults --collect

# Friday evening: Finalization mode (6 PM)
0 18 * * 5 cd /path/to/briefAI && python main.py --defaults --finalize
```

This will:
- Automatically collect articles Mon-Fri at 9 AM
- Automatically finalize and generate report Fri at 6 PM
- Require only 18,000 tokens per week
- Ensure comprehensive, high-quality weekly briefing
