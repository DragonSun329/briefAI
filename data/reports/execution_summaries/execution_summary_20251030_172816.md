# Pipeline Execution Summary
**Run ID**: 20251030_172816
**Date**: 2025-10-30 17:46:05
**Duration**: 17m 49s
**Status**: ❌ FAILED

## Pipeline Flow
1. ✅ initialization (0s)
2. ✅ scraping (2m 27s)
3. ✅ tier1_filter - 106 → 32 articles (0s)
4. ✅ tier2_batch_eval - 32 → 32 articles (1m 4s)
5. ✅ tier3_5d_eval - 32 → 10 articles (8m 56s)
6. ✅ ranking (0s)
7. ✅ paraphrasing (2m 45s)
8. ✅ entity_background (2m 37s)
9. ❌ quality_validation (FAILED)
10. ⏸️  report_generation (not started)
11. ⏸️  finalization (not started)

## Metrics Summary
- **Articles**: 106 scraped → 10 final
- **Filter Rates**: Tier 1 (30.2%), Tier 2 (100.0%)
- **Token Usage**: 83,200 total (input: 65,800, output: 17,400)
- **Cost**: $0.1398 USD
- **LLM Calls**: 31 (avg latency: 2048ms)

## Errors & Warnings
- **Total Errors**: 2 (2 critical, 0 warnings)
- **By Type**:
  - UNKNOWN: 2

## Performance vs. Historical Average
- No historical data available for comparison

## Anomalies Detected
- **ranking**: duration_seconds deviated 100.0% from historical average (MEDIUM severity)

## Recommendations
- Scraping success rate is 0.0% (below 85%). Consider increasing timeouts or adding backup RSS feeds.
- Detected 1 anomalies. Review error logs for details.

## Output Files
- Error Log: `data/logs/errors_20251030_172816.json`
- Context: `data/context/context_20251030_172816.json`
- Metrics: `data/metrics/metrics_20251030_172816.json`
