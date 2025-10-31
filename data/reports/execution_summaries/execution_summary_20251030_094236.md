# Pipeline Execution Summary
**Run ID**: 20251030_094236
**Date**: 2025-10-30 09:58:13
**Duration**: 15m 37s
**Status**: ✅ SUCCESS

## Pipeline Flow
1. ✅ initialization (0s)
2. ✅ scraping (1m 59s)
3. ✅ tier1_filter - 158 → 37 articles (0s)
4. ✅ tier2_batch_eval - 37 → 37 articles (52s)
5. ✅ tier3_5d_eval - 37 → 10 articles (8m 58s)
6. ✅ ranking (0s)
7. ✅ paraphrasing (2m 54s)
8. ✅ report_generation (54s)
9. ✅ finalization (0s)

## Metrics Summary
- **Articles**: 158 scraped → 10 final
- **Filter Rates**: Tier 1 (23.4%), Tier 2 (100.0%)
- **Token Usage**: 79,000 total (input: 63,000, output: 16,000)
- **Cost**: $0.1328 USD
- **LLM Calls**: 24 (avg latency: 2208ms)

## Performance vs. Historical Average
- No historical data available for comparison

## Recommendations
- Scraping success rate is 0.0% (below 85%). Consider increasing timeouts or adding backup RSS feeds.

## Output Files
- Report: `data/reports/weekly_briefing_None_20251030.md`
- Error Log: `data/logs/errors_20251030_094236.json`
- Context: `data/context/context_20251030_094236.json`
- Metrics: `data/metrics/metrics_20251030_094236.json`
