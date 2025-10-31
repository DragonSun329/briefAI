# Pipeline Execution Summary
**Run ID**: 20251030_111745
**Date**: 2025-10-30 11:51:42
**Duration**: 33m 56s
**Status**: ❌ FAILED

## Pipeline Flow
1. ✅ initialization (0s)
2. ✅ scraping (14m 14s)
3. ✅ tier1_filter - 132 → 29 articles (0s)
4. ✅ tier2_batch_eval - 29 → 29 articles (3m 0s)
5. ✅ tier3_5d_eval - 29 → 10 articles (11m 18s)
6. ✅ ranking (0s)
7. ✅ paraphrasing (3m 6s)
8. ✅ entity_background (2m 18s)
9. ❌ quality_validation (FAILED)
10. ⏸️  report_generation (not started)
11. ⏸️  finalization (not started)

## Metrics Summary
- **Articles**: 132 scraped → 10 final
- **Filter Rates**: Tier 1 (22.0%), Tier 2 (100.0%)
- **Token Usage**: 80,700 total (input: 63,800, output: 16,900)
- **Cost**: $0.1356 USD
- **LLM Calls**: 30 (avg latency: 2050ms)

## Errors & Warnings
- **Total Errors**: 2 (2 critical, 0 warnings)
- **By Type**:
  - UNKNOWN: 2

## Performance vs. Historical Average
- No historical data available for comparison

## Anomalies Detected
- **initialization**: duration_seconds deviated 57.1% from historical average (MEDIUM severity)
- **scraping**: duration_seconds deviated 615.1% from historical average (HIGH severity)
- **tier2_batch_eval**: duration_seconds deviated 247.5% from historical average (HIGH severity)

## Recommendations
- Scraping success rate is 0.0% (below 85%). Consider increasing timeouts or adding backup RSS feeds.
- Detected 3 anomalies. Review error logs for details.

## Output Files
- Error Log: `data/logs/errors_20251030_111745.json`
- Context: `data/context/context_20251030_111745.json`
- Metrics: `data/metrics/metrics_20251030_111745.json`
