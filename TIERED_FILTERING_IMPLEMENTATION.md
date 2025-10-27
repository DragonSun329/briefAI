# Tiered Filtering System Implementation

## Overview
Implemented a 3-tier article evaluation system to reduce token usage by **75-90%** while maintaining quality. Articles are progressively filtered through three stages, with expensive LLM evaluation only applied to the most promising candidates.

## Architecture

```
Scraped Articles (50+)
        ↓
[TIER 1] Pre-filter (0 tokens) - Score based on relevance + recency + credibility
        ↓
15-20 articles remaining
        ↓
[TIER 2] Batch evaluation (lightweight LLM) - Quick pass/fail scoring
        ↓
8-10 articles remaining
        ↓
[TIER 3] Full evaluation (detailed analysis) - Original evaluation system
        ↓
Final report (10-15 articles)
```

## Files Created

### 1. `utils/article_filter.py` (200 lines)
**Purpose**: Tier 1 fast pre-filtering without LLM calls

**Key Components**:
- `ArticleFilter` class
- `filter_articles()` - Main entry point
- `_score_article()` - Calculates 0-10 importance score
- `_build_category_keywords()` - Extract keywords from user categories
- `_extract_tags()` - Detect trending tags (热门, 推荐, 精选, 🔥, etc.)

**Scoring Logic** (0-10 scale):
```
- Exact keyword match: +3 points
- Partial keyword match: +1 point
- Trending/hot tag detected: +2 points
- Published <24h ago: +2 points
- Published 24-48h ago: +1 point
- Source credibility >=9: +1 point
- Source credibility >=8: +0.5 points
- View count >100: +0.5 points
- View count >500: +1 point
```

**Configuration**:
- `TIER1_SCORE_THRESHOLD=4.0` (aggressive, Phase 1)
- Will adjust to `3.0` (moderate) after testing

**Expected Results**:
- Filters 60-70% of articles (52 → 15-20)
- 0 token usage
- Fast execution (<1 second)

### 2. `modules/batch_evaluator.py` (250 lines)
**Purpose**: Tier 2 lightweight batch LLM evaluation

**Key Components**:
- `BatchEvaluator` class
- `evaluate_batch()` - Main evaluation entry point
- `_evaluate_batch_call()` - Make single LLM call for multiple articles
- `_build_articles_text()` - Format articles for LLM
- `_parse_batch_response()` - Parse LLM JSON response

**Features**:
- Evaluates multiple articles (10 per call) in single LLM call
- Lightweight evaluation (impact + relevance only, not full 4D)
- Returns simple pass/fail + brief reasoning
- Articles scoring >= 6 pass to Tier 3

**Configuration**:
- `TIER2_BATCH_SIZE=10` (Phase 1: efficient)
- `TIER2_PASS_SCORE=6.0` (Articles need 6+ to pass)
- Will adjust to `TIER2_BATCH_SIZE=3` (Phase 2: higher quality)

**Expected Results**:
- Further filters 50-60% of Tier 1 candidates (15-20 → 8-10)
- ~1,500-2,000 tokens per run (vs 13,000 for individual evaluation)
- Batch processing saves 70%+ tokens on screening phase

### 3. Updates to `main.py`
**Changes**:
1. Added imports for `ArticleFilter` and `BatchEvaluator`
2. Initialize both modules in `BriefingAgent.__init__()`
3. Load configuration from environment variables
4. Modified workflow:
   - Step 2: Scrape articles
   - Step 3a: **TIER 1** Pre-filter → 15-20 articles
   - Step 3b: **TIER 2** Batch evaluate → 8-10 articles
   - Step 3c: **TIER 3** Full evaluation → final selection
   - Step 4: Paraphrase
   - Step 5: Generate report

**Workflow Code**:
```python
# Step 3a: Tier 1 Pre-filter
tier1_articles = self.article_filter.filter_articles(articles, categories)

# Step 3b: Tier 2 Batch evaluation
tier2_articles = self.batch_evaluator.evaluate_batch(tier1_articles, categories)

# Step 3c: Tier 3 Full evaluation
evaluated_articles = self.news_evaluator.evaluate_articles(
    tier2_articles, categories, top_n
)
```

### 4. Updates to `.env`
**New Configuration**:
```env
# TIER 1: Pre-filter threshold (0-10 scale)
# 4.0 = aggressive (save most tokens, lose ~10% good articles)
# 3.0 = moderate (lose ~5% good articles)
TIER1_SCORE_THRESHOLD=4.0

# TIER 2: Batch evaluation
# 10 = most efficient, 3 = highest quality
TIER2_BATCH_SIZE=10
TIER2_PASS_SCORE=6.0
```

## Token Usage Comparison

### Current System (Before)
```
52 articles scraped
→ All 52 evaluated individually
→ Tier 3 evaluation: 52 × 500 tokens = 26,000 tokens
→ Total: 26,000 tokens
```

### New System (Phase 1)
```
52 articles scraped
→ Tier 1 pre-filter: 0 tokens (52 → 15-20 articles)
→ Tier 2 batch eval: 2 batches × 600 tokens = 1,200 tokens (15-20 → 8-10 articles)
→ Tier 3 full eval: 8-10 × 500 tokens = 4,000-5,000 tokens
→ Total: 5,200-6,200 tokens

Savings: 75-80% reduction (19,800-20,800 tokens saved!)
```

### Phase 2 (After Testing & Refinement)
```
Adjustments:
- Tier 1 threshold: 4.0 → 3.0 (more articles pass)
- Tier 2 batch size: 10 → 3 (higher quality screening)

Expected results:
- Tier 1: 52 → 18-25 articles
- Tier 2: 18-25 → 10-12 articles (3 per batch = higher quality decisions)
- Tier 3: 10-12 articles

New token estimate: 6,000-7,000 tokens (still 75%+ savings)
```

## Quality Control

### Tier 1 Filtering (Aggressive - Score >= 4)
**Expected Miss Rate**: ~10% of good articles

**Safe Filtering Criteria**:
- ✅ Articles with trending tags
- ✅ Very recent articles (<24h)
- ✅ Articles from highly credible sources
- ✅ Articles with strong keyword matches

**More Likely to Miss**:
- Articles on niche subtopics
- Important analysis pieces with generic titles
- Deep-dive research without trending indicators

### Mitigation Strategy
If quality drops noticeably during testing:
1. Lower `TIER1_SCORE_THRESHOLD` to 3.0 (moderate)
2. Reduce `TIER2_BATCH_SIZE` to 5 or 3 (higher quality screening)
3. Increase `TIER2_PASS_SCORE` to 6.5 or 7.0
4. Add HTML view count extraction for better signals

## Testing Plan

### Phase 1: MVP Testing (Current)
**Run**: `python3 main.py --defaults --days 3 --top 10`

**Validation Points**:
- [ ] Tier 1 filters 60-70% of articles (check logs)
- [ ] Tier 2 filters additional 50-60% of remaining
- [ ] Final report quality meets expectations
- [ ] No obviously important articles accidentally filtered
- [ ] Total token usage reduced by 75%+

**Success Criteria**:
- Final report reads well and includes important articles
- Aggressive threshold (score >= 4) doesn't miss important pieces
- Processing completes successfully with new tiers

### Phase 2: Refinement Testing (After MVP validation)
**Changes**:
- Adjust `TIER1_SCORE_THRESHOLD` to 3.0 if miss rate is high
- Reduce `TIER2_BATCH_SIZE` to 3 for quality
- Monitor token savings continue

**Testing**: Run 2-3 full workflows and compare outputs

## Configuration Adjustment Reference

### To Keep More Articles (Less Aggressive):
```env
# Phase 1 (current) → Phase 2 adjustment
TIER1_SCORE_THRESHOLD=4.0 → 3.0     # Moderate filtering
TIER2_BATCH_SIZE=10 → 3              # Higher quality screening
TIER2_PASS_SCORE=6.0 → 6.5          # Stricter pass requirement
```

### To Filter More Aggressively (Save More Tokens):
```env
# More aggressive
TIER1_SCORE_THRESHOLD=5.0            # Only highest relevance articles
TIER2_BATCH_SIZE=15                  # Process more at once (lower quality)
TIER2_PASS_SCORE=5.5                 # Lower pass requirement
```

## Future Enhancements

### Phase 2 (After Testing):
1. **HTML View Count Extraction**
   - Parse view counts from Chinese news sites
   - Add engagement metrics (comments, shares)
   - Boost scoring for popular articles

2. **Semantic Similarity Deduplication**
   - Replace entity extraction with fast embeddings
   - Detect duplicate topics without LLM calls

3. **Dynamic Thresholds**
   - Adjust Tier 1 threshold based on article count
   - If <10 articles pass Tier 1, relax threshold
   - If >50 articles pass Tier 1, tighten threshold

4. **Learning from Feedback**
   - Track which Tier 1 filtered articles were actually important
   - Adjust keyword weights based on actual CEO feedback

### Phase 3 (Advanced):
1. **Cache Tier 1 scores** for articles already evaluated
2. **Provider-aware batch sizing** - larger batches for cheaper models
3. **Multi-language support** for English vs Chinese sources
4. **Real-time trending detection** - monitor which sources' trending indicators are most accurate

## Troubleshooting

### Too Many Articles Filtered Out
- **Symptom**: Tier 1 reduces to <10 articles, Tier 2 to <5
- **Fix**: Lower `TIER1_SCORE_THRESHOLD` from 4.0 to 3.0
- **Or**: Add more keywords to category config

### Too Few Articles Filtered Out
- **Symptom**: Tier 1 keeps 40+ articles, still expensive
- **Fix**: Raise `TIER1_SCORE_THRESHOLD` from 4.0 to 5.0
- **Or**: Improve scoring logic to detect better trending signals

### Tier 2 Batch Errors
- **Symptom**: "Failed to parse batch response"
- **Fix**: Reduce `TIER2_BATCH_SIZE` from 10 to 5 or 3
- **Or**: Check LLM JSON response format

### Quality Drop in Final Report
- **Symptom**: Final report missing important articles
- **Fix**:
  1. Check `TIER1_SCORE_THRESHOLD` - might be too high
  2. Increase `TIER2_BATCH_SIZE` to 3 for better screening quality
  3. Lower `TIER2_PASS_SCORE` from 6.0 to 5.5

## Monitoring

**Key Metrics to Track**:
1. Articles remaining after each tier
2. Total token usage (compare to 26,000 baseline)
3. Final report quality (subjective, but important)
4. Processing time
5. Provider distribution (which models used for Tiers 2-3)

**Log Output Example**:
```
[TIER 1] Pre-filtering 52 articles...
[TIER 1] Results: 18/52 articles kept (avg score: 5.2, threshold: 4.0)
[TIER 2] Batch evaluating 18 articles...
[TIER 2] Processing 2 batches of 10 articles
[TIER 2] Results: 10/18 articles passed (threshold: 6.0)
[TIER 3] TIER 3: Full article evaluation...
Selected top 10 articles after full evaluation
```

## Summary

✅ **Implementation Complete**:
- Tier 1 pre-filter (0 tokens, 0-10 scoring)
- Tier 2 batch evaluation (lightweight LLM)
- Tier 3 full evaluation (existing system)
- Configuration in .env
- Integrated into main workflow

✅ **Expected Results**:
- 75-90% token reduction
- Maintain article quality
- Faster overall processing
- Better resource utilization

✅ **Ready to Test**:
Run `python3 main.py --defaults --days 3 --top 10` and monitor logs
