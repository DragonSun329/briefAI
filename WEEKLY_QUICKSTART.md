# Weekly Collection System - Quick Start Guide

## What's New?

Instead of running the full workflow every day and wasting tokens, you now have two optimized modes:

1. **Collection Mode** (Monday-Friday, 5 min/day): Fast Tier 1+2 screening
2. **Finalization Mode** (Friday evening): Deduplicate + Tier 3 evaluation + Report

**Result**: 90% token savings! (18,000 tokens/week instead of 182,000)

## Daily Usage (Mon-Fri)

### Run Collection
```bash
python main.py --defaults --collect
```

**What it does**:
- Scrapes latest articles
- Tier 1 pre-filters (0 tokens)
- Tier 2 batch evaluates (~500 tokens)
- Saves to weekly checkpoint

**Time**: ~5 minutes
**Cost**: ~500 tokens/day

### Check Collection Progress
```bash
# View current week's collection stats
tail -20 ./data/logs/briefing_agent.log

# Look for output like:
# [COLLECTION SUMMARY] Monday (Day 1): 10 articles collected
# [COLLECTION SUMMARY] Tuesday (Day 2): 12 articles collected
```

## Weekly Finalization (Friday Evening)

### Run Finalization
```bash
python main.py --defaults --finalize
```

**What it does**:
1. Loads all articles collected Mon-Fri (150+)
2. Removes duplicates (~30)
3. Re-ranks by importance
4. Full Tier 3 evaluation on top 30
5. Selects final 10-15
6. Generates report
7. Saves to `./data/reports/weekly_briefing_*.md`

**Time**: ~30 minutes
**Cost**: ~15,000 tokens

## Early Report (Friday 8 AM) - NEW!

### Generate Early Report with Auto-Backfill
```bash
# Friday morning - generates report with automatic backfill of missing days
python main.py --defaults --finalize --early
```

**What it does**:
1. Checks which collection days have missing/low articles
2. Auto-collects articles for missing days (e.g., Friday if only Mon-Thu collected)
3. Deduplicates all articles collected during the week
4. Re-ranks by combined score (tier2 + recency + trending)
5. Runs Tier 3 full evaluation on top 30 candidates
6. Selects final 10-15 articles
7. Generates early report with full 7-day coverage

**Time**: ~30-40 minutes (includes backfilling)
**Cost**: ~15,000-17,000 tokens (Tier 3 eval + backfill collection)

### Generate Early Report WITHOUT Backfill
```bash
# Use only articles collected so far, don't wait for backfill
python main.py --defaults --finalize --early --no-backfill
```

**Faster**: ~20 minutes (no backfill collection)
**Useful when**: Friday morning, don't need maximum data

## Automated Scheduling (Optional)

Add to crontab for automatic execution:

```bash
crontab -e
```

### Option A: Daily Collection + Early Friday Report
```bash
# Monday-Friday at 9 AM: Daily collection
0 9 * * 1-5 cd /path/to/briefAI && python main.py --defaults --collect

# Friday at 8 AM: Early report with auto-backfill
0 8 * * 5 cd /path/to/briefAI && python main.py --defaults --finalize --early
```

### Option B: Daily Collection + Late Friday Report (No Backfill)
```bash
# Monday-Friday at 9 AM: Daily collection
0 9 * * 1-5 cd /path/to/briefAI && python main.py --defaults --collect

# Friday at 4 PM: Early report without backfill (faster, use only collected)
0 16 * * 5 cd /path/to/briefAI && python main.py --defaults --finalize --early --no-backfill
```

### Option C: Traditional - Saturday Evening Report
```bash
# Monday-Friday at 9 AM: Daily collection
0 9 * * 1-5 cd /path/to/briefAI && python main.py --defaults --collect

# Saturday at 6 PM: Full finalization (no backfill needed)
0 18 * * 6 cd /path/to/briefAI && python main.py --defaults --finalize
```

Replace `/path/to/briefAI` with your actual project path.

## Manual Week Management

### Finalize a Specific Week
```bash
# Finalize week 43 of 2025
python main.py --defaults --finalize --week week_2025_43
```

### Collect with Specific Day
```bash
# Collect for day 3 (Wednesday)
python main.py --defaults --collect --day 3
```

### View Collection Preview
```python
from modules.finalization_mode import FinalizationMode

finalizer = FinalizationMode()
candidates = finalizer.get_finalization_candidates(
    week_id='week_2025_43',
    limit=10
)

for candidate in candidates:
    print(f"{candidate['title']} (Score: {candidate['combined_score']:.2f})")
```

## File Locations

**Weekly Checkpoints**:
```
./data/cache/weekly_2025_43.json
./data/cache/weekly_2025_44.json
...
```

**Generated Reports**:
```
./data/reports/weekly_briefing_week_2025_43.md
./data/reports/weekly_briefing_week_2025_44.md
...
```

**Logs**:
```
./data/logs/briefing_agent.log
```

## Token Cost Comparison

### Old System (Run full workflow daily)
```
Monday:   26,000 tokens
Tuesday:  26,000 tokens
Wednesday: 26,000 tokens
Thursday: 26,000 tokens
Friday:   26,000 tokens
Saturday: 26,000 tokens
Sunday:   26,000 tokens
─────────────────────
TOTAL:   182,000 tokens/week 😰
```

### New System (Collection + Finalization)
```
Mon-Fri collection:    6 × 500  =   3,000 tokens
Friday finalization:       1    =  15,000 tokens
─────────────────────────────────
TOTAL:                         =  18,000 tokens/week 🎉

Savings: 164,000 tokens (90% reduction!)
```

## Common Commands

```bash
# Daily (Monday-Friday)
python main.py --defaults --collect

# Weekly finalization (Friday evening)
python main.py --defaults --finalize

# View help
python main.py --help

# Run old-style full workflow (all 3 tiers at once)
python main.py --defaults

# Use custom categories
python main.py --input "我想了解大模型和AI应用" --collect
python main.py --input "我想了解大模型和AI应用" --finalize
```

## Troubleshooting

### No articles collected
```bash
# Check if articles are being scraped
python main.py --defaults --collect

# Look for "Scraped X articles" in logs
# If 0 articles: check network and source configuration
```

### Low tier2 score (articles getting filtered)
```bash
# This is normal - Tier 2 is strict (threshold: 6.0)
# Articles rated 6+ out of 10 pass

# Check the "tier2_reasoning" to understand why articles were rejected
tail -100 ./data/logs/briefing_agent.log | grep "tier2_reasoning"
```

### Finalization fails with "No checkpoint found"
```bash
# Make sure you ran collection mode during the week
# Finalization needs collected articles

# Check checkpoint file exists:
ls ./data/cache/weekly_*.json

# If missing, run collection first:
python main.py --defaults --collect --week week_2025_43
```

### Report not generated
```bash
# Check finalization completed successfully
tail -50 ./data/logs/briefing_agent.log

# Look for "✅ Weekly report generated successfully!"
# If missing, check error message above
```

## Typical Weekly Workflow

### Monday 9 AM
```
💻 Automatic collection runs (or manual: python main.py --defaults --collect)
📊 Scrapes articles, screens with Tier 1+2, saves to checkpoint
⏱️  Takes ~5 minutes, uses ~500 tokens
```

### Tuesday-Friday 9 AM
```
💻 Automatic collection runs daily
📊 More articles accumulate in checkpoint
⏱️  Each day: 5 minutes, 500 tokens
```

### Friday 6 PM
```
💻 Automatic finalization runs (or manual: python main.py --defaults --finalize)
📊 Loads 150+ articles collected all week
🔄 Deduplicates, re-ranks, runs Tier 3 on top 30
📝 Generates polished report
💾 Saves to ./data/reports/weekly_briefing_*.md
⏱️  Takes ~30 minutes, uses ~15,000 tokens
📧 (Optional) Email report to stakeholders
```

## Key Metrics to Track

After running finalization, check:

```
[FINALIZATION] Loaded 150 articles from week
[FINALIZATION] After deduplication: 120 articles (removed 30 duplicates)
[FINALIZATION] Running Tier 3 full evaluation on 30 candidates...
[FINALIZATION] Tier 3 evaluation complete: 15/30 articles selected
```

This tells you:
- ✅ Articles collected: 150 (good spread across week)
- ✅ Unique articles: 120 (30% duplication rate - normal)
- ✅ Tier 3 evaluated: 30 (top candidates)
- ✅ Final report: 15 articles (quality selected)

## Next Steps

1. **Test collection mode** (run manually a few times)
2. **Test finalization mode** (run after a week of collection)
3. **Set up cron jobs** (for automatic daily/weekly execution)
4. **Monitor reports** (check quality of generated reports)
5. **Adjust thresholds** (if too many/too few articles pass tiers)

## Support

For detailed implementation info, see `WEEKLY_COLLECTION_IMPLEMENTATION.md`

For tier configuration, see `TIERED_FILTERING_IMPLEMENTATION.md`

Happy collecting! 🚀
