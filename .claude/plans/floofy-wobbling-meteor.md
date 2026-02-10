# Plan: Enrich Bucket Radar with Historical & Alternative Data Sources

## Problem
The current bucket radar only uses:
- 2 trend aggregate files (52 articles total)
- 998 Crunchbase companies

Missing data that IS available but NOT integrated:
- GitHub trending repos (daily star velocity)
- HuggingFace trending models (downloads/likes)
- SEC EDGAR filings (enterprise signals)
- Product Hunt launches
- Historical pipeline contexts

## Available Data Sources

| Source | Location | Status |
|--------|----------|--------|
| Trend Aggregates | `data/cache/trend_aggregate/combined_*.json` | Used (2 files) |
| Crunchbase | `data/crunchbase/ai_companies_*.json` | Used (998 companies) |
| GitHub Trending | `.worktrees/trend-radar/data/alternative_signals/github_trending_*.json` | **NOT USED** |
| HuggingFace | `data/alternative_signals/huggingface_trending_*.json` | **NOT USED** |
| SEC EDGAR | `.worktrees/trend-radar/data/alternative_signals/sec_edgar_*.json` | **NOT USED** |
| Product Hunt | `.worktrees/trend-radar/data/alternative_signals/producthunt_*.json` | **NOT USED** |

## Implementation Plan

### Step 1: Consolidate Alternative Signals to Main Directory
Copy all alternative signal files from worktree to main `data/alternative_signals/`:
- `github_trending_*.json`
- `sec_edgar_*.json`
- `producthunt_*.json`

### Step 2: Enhance `generate_bucket_profiles_from_aggregates()` in `bucket_scorers.py`

Add loaders for each data source:

```python
def generate_bucket_profiles_from_aggregates(
    trend_aggregate_dir: Path,
    crunchbase_dir: Optional[Path] = None,
    alternative_signals_dir: Optional[Path] = None,  # NEW
    output_path: Optional[Path] = None,
    days_to_include: int = 14
) -> List[BucketProfile]:
```

#### 2a. Load GitHub Trending → Feed TMS (Technical Momentum Score)
```python
# Load github_trending_*.json
# For each repo: tag to bucket, extract stars_today
# TMS_raw = sum(stars_today * 7) per bucket  # weekly velocity
```

#### 2b. Load HuggingFace Trending → Feed TMS
```python
# Load huggingface_trending_*.json
# For each model: tag to bucket by task/name
# TMS_raw += downloads_month / 4  # weekly estimate
```

#### 2c. Load SEC EDGAR → Feed EIS (Enterprise Institutional Signal)
```python
# Load sec_edgar_*.json
# For each filing: tag company to bucket
# Parse filing context for offensive/defensive keywords
# EIS_offensive = count of growth/strategic keywords
# EIS_defensive = count of risk/compliance keywords
```

#### 2d. Load Product Hunt → Feed NAS (Narrative Attention Score)
```python
# Load producthunt_*.json
# For each launch: tag to bucket
# NAS_raw += upvotes / 100  # product launch signal
```

### Step 3: Update Scoring Formula

Current (weak):
```python
tms_raw = entity_count * 0.5  # placeholder
eis_off = min(ccs * 0.8, 90)  # approximation
```

Enhanced:
```python
# TMS from real technical signals
tms_raw = github_stars_velocity + hf_download_velocity + new_repo_count

# EIS from real enterprise signals
eis_off = sec_offensive_mentions + product_hunt_launches
eis_def = sec_defensive_mentions

# NAS remains article-based but boosted by product signals
nas_raw = article_count + product_hunt_count
```

### Step 4: Run Generation with All Sources

```bash
python -m utils.bucket_scorers --generate
```

This should now produce profiles with:
- 998 Crunchbase companies → CCS
- GitHub trending repos → TMS
- HuggingFace models → TMS
- SEC filings → EIS
- Product Hunt → NAS
- 52 articles → NAS

## Files to Modify

1. **`utils/bucket_scorers.py`** (lines 647-882)
   - Add `alternative_signals_dir` parameter
   - Add loaders for GitHub, HuggingFace, SEC, ProductHunt
   - Update TMS/EIS computation to use real data

2. **`utils/bucket_scorers.py`** `__main__` block (lines 884-919)
   - Add path for alternative_signals_dir

## Expected Outcome

| Metric | Before | After |
|--------|--------|-------|
| TMS data source | entity_count proxy | GitHub + HF velocity |
| EIS data source | CCS approximation | SEC filings |
| NAS data source | 52 articles | Articles + ProductHunt |
| Buckets with data | 30 | 31 (all buckets) |
| Entity coverage | ~200 | ~500+ |

## User Decision
**Approach:** Integrate ALL data sources at once (GitHub + HuggingFace + SEC + ProductHunt)

## Execution Steps

1. Copy alternative signals from worktree to main directory
2. Modify `bucket_scorers.py` to load all signal sources
3. Update TMS computation with GitHub stars + HF downloads
4. Update EIS computation with SEC filing analysis
5. Update NAS computation with ProductHunt data
6. Re-run profile generation
7. Verify dashboard shows enriched data