# Pipeline Execution Summary
**Run ID**: 20251030_175101
**Date**: 2025-10-31 11:03:11
**Duration**: 17h 12m
**Status**: ✅ SUCCESS

## Pipeline Flow
1. ✅ initialization (0s)
2. ✅ scraping (2m 4s)
3. ✅ tier1_filter - 141 → 39 articles (0s)
4. ✅ tier2_batch_eval - 39 → 39 articles (1m 8s)
5. ✅ tier3_5d_eval - 39 → 10 articles (17h 5m)
6. ✅ ranking (0s)
7. ✅ paraphrasing (1m 41s)
8. ✅ entity_background (1m 25s)
9. ✅ quality_validation (0s)
10. ✅ report_generation (19s)
11. ✅ finalization (0s)

## Metrics Summary
- **Articles**: 141 scraped → 10 final
- **Filter Rates**: Tier 1 (27.7%), Tier 2 (100.0%)
- **Token Usage**: 80,800 total (input: 64,200, output: 16,600)
- **Cost**: $0.1358 USD
- **LLM Calls**: 27 (avg latency: 2130ms)

## Errors & Warnings
- **Total Errors**: 1 (1 critical, 0 warnings)
- **By Type**:
  - UNKNOWN: 1

## Performance vs. Historical Average
- No historical data available for comparison

## Anomalies Detected
- **tier3_5d_eval**: duration_seconds deviated 11346.8% from historical average (HIGH severity)
- **report_generation**: duration_seconds deviated 65.4% from historical average (MEDIUM severity)

## Recommendations
- Scraping success rate is 0.0% (below 85%). Consider increasing timeouts or adding backup RSS feeds.
- Detected 2 anomalies. Review error logs for details.

## Output Files
- Report: `data/reports/weekly_briefing_None_20251031.md`
- Error Log: `data/logs/errors_20251030_175101.json`
- Context: `data/context/context_20251030_175101.json`
- Metrics: `data/metrics/metrics_20251030_175101.json`
