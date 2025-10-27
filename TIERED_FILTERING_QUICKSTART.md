# Tiered Filtering System - Quick Start

## What Changed?

Your system now has **3 tiers of article filtering** instead of evaluating all articles with expensive LLM calls:

```
52 articles → Tier 1 (fast filter) → 15-20 articles
           → Tier 2 (batch LLM) → 8-10 articles
           → Tier 3 (full eval) → final report

Token savings: 75-90% (26,000 → 5,000-6,000 tokens)
```

## How to Use

### Run the System (Same as Before)
```bash
# Nothing changed! Run it the same way
python3 main.py --defaults --days 3 --top 10
```

### Monitor Progress
Look for these log lines showing each tier:
```
[TIER 1] Pre-filtering 52 articles...
[TIER 1] Results: 18/52 articles kept

[TIER 2] Batch evaluating 18 articles...
[TIER 2] Results: 10/18 articles passed

[TIER 3] TIER 3: Full article evaluation...
Selected top 10 articles after full evaluation
```

## Configuration (Optional)

Edit `.env` if you want to adjust behavior:

```env
# How aggressive to filter at Tier 1 (0-10 scale)
# Lower = keep more articles, higher = save more tokens
TIER1_SCORE_THRESHOLD=4.0      # Currently: aggressive (Phase 1)
                               # After testing: change to 3.0

# How many articles to evaluate together at Tier 2
# Higher = more efficient, Lower = better quality
TIER2_BATCH_SIZE=10            # Currently: efficient (Phase 1)
                               # After testing: change to 3

# Minimum score to pass Tier 2
TIER2_PASS_SCORE=6.0           # Articles need 6+ score to advance
```

## Phase 1 vs Phase 2

### Phase 1: Now (MVP Testing)
- `TIER1_SCORE_THRESHOLD=4.0` (aggressive, save max tokens)
- `TIER2_BATCH_SIZE=10` (most efficient)
- Goal: Validate the system works

### Phase 2: After Testing (Refinement)
- `TIER1_SCORE_THRESHOLD=3.0` (moderate, better quality)
- `TIER2_BATCH_SIZE=3` (higher quality screening)
- Goal: Balance token savings with article quality

To switch to Phase 2, just update `.env` and restart.

## What Gets Filtered?

### Tier 1 Filtering (Scoring 0-10)
Filters out articles that have:
- ❌ No keyword match to your categories
- ❌ Low source credibility
- ❌ Very old (>48 hours)
- ❌ No trending indicators

Keeps articles that have:
- ✅ Keywords matching your interests
- ✅ Published recently (<24h)
- ✅ From trusted sources (credibility >=8)
- ✅ Marked as trending/hot/featured on site

### Tier 2 Filtering (Score 6+)
LLM quickly evaluates if articles are:
- **Impact**: Does this matter to the industry?
- **Relevance**: Does it fit your focus areas?

Articles scoring <6 get filtered. 6+ pass to detailed analysis.

### Tier 3 (Full Evaluation)
Same as before - detailed scoring with:
- Impact, Relevance, Recency, Credibility
- Entity extraction
- Key takeaways

## Typical Output

**With 52 scraped articles:**
```
Tier 1: 52 → 18 articles (65% filtered, 0 tokens)
Tier 2: 18 → 10 articles (44% filtered, ~1,200 tokens)
Tier 3: 10 → 10 articles (full eval, ~5,000 tokens)

Total tokens: ~6,200 (vs 26,000 before = 76% savings!)
```

## If Something Goes Wrong

### "Only 5 articles passed Tier 1!"
Tier 1 is being too aggressive. Lower the threshold:
```env
TIER1_SCORE_THRESHOLD=4.0 → 3.0  # Relax filtering
```

### "Tier 2 batch eval failed"
Batch size might be too large. Reduce it:
```env
TIER2_BATCH_SIZE=10 → 5  # Process fewer at once
```

### "Final report is missing good articles"
Tiers are filtering too much. Loosen them:
```env
TIER1_SCORE_THRESHOLD=4.0 → 3.0    # Less aggressive
TIER2_BATCH_SIZE=10 → 3             # Higher quality eval
TIER2_PASS_SCORE=6.0 → 5.5         # Lower pass bar
```

## Token Savings Breakdown

### Original System
```
52 articles → ALL evaluated by LLM
52 × 500 tokens per evaluation = 26,000 tokens
```

### New System
```
52 articles → Tier 1 (0 tokens, 65% filtered)
18 articles → Tier 2 (2 batches × 600 = 1,200 tokens, 44% filtered)
10 articles → Tier 3 (10 × 500 = 5,000 tokens, full evaluation)

Total: 6,200 tokens (76% savings!)
```

## Files Changed/Added

**New Files**:
- `utils/article_filter.py` - Tier 1 pre-filtering logic
- `modules/batch_evaluator.py` - Tier 2 batch evaluation
- `TIERED_FILTERING_IMPLEMENTATION.md` - Detailed documentation

**Modified Files**:
- `main.py` - Added tiers to workflow
- `.env` - Added tier configuration

**No Changes**:
- Everything else works the same!
- API keys, sources, categories, paraphrasing - all unchanged

## Next Steps

1. **Test Phase 1**: Run a few times with default aggressive settings
   ```bash
   python3 main.py --defaults --days 3 --top 10
   ```

2. **Monitor Results**: Check that articles still look good

3. **After Testing**: Adjust to Phase 2 settings for better quality
   ```env
   TIER1_SCORE_THRESHOLD=3.0
   TIER2_BATCH_SIZE=3
   ```

4. **Final Optimization**: Fine-tune based on actual results

## Troubleshooting Checklist

- [ ] Run the command same as before
- [ ] Check logs for Tier 1/2/3 progress
- [ ] Verify final report quality
- [ ] Check token savings in stats
- [ ] Adjust `.env` if needed

## Questions?

Refer to `TIERED_FILTERING_IMPLEMENTATION.md` for:
- Detailed scoring logic
- Configuration reference
- Phase 2 enhancement ideas
- Advanced troubleshooting
