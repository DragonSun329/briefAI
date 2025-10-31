# Pipeline Execution Summary
**Run ID**: 20251031_155656
**Date**: 2025-10-31 15:59:14
**Duration**: 2m 17s
**Status**: ❌ FAILED

## Pipeline Flow
1. ✅ initialization (0s)
2. ✅ scraping (7s)
3. ⏸️  review_extraction (not started)
4. ✅ tier1_filter - 80 → 4 articles (0s)
5. ✅ tier2_batch_eval - 4 → 4 articles (8s)
6. ✅ tier3_5d_eval - 4 → 3 articles (59s)
7. ⏸️  trending_calculation (not started)
8. ✅ ranking (0s)
9. ✅ paraphrasing (49s)
10. ⏸️  review_summarization (not started)
11. ✅ entity_background (14s)
12. ✅ quality_validation (0s)
13. ❌ report_generation (FAILED)
14. ⏸️  finalization (not started)

## Metrics Summary
- **Articles**: 80 scraped → 3 final
- **Filter Rates**: Tier 1 (5.0%), Tier 2 (100.0%)
- **Token Usage**: 25,000 total (input: 19,700, output: 5,300)
- **Cost**: $0.0420 USD
- **LLM Calls**: 10 (avg latency: 2000ms)

## Errors & Warnings
- **Total Errors**: 2 (2 critical, 0 warnings)
- **By Type**:
  - UNKNOWN: 2

## Performance vs. Historical Average
- No historical data available for comparison

## Anomalies Detected
- **scraping**: duration_seconds deviated 93.9% from historical average (MEDIUM severity)
- **tier1_filter**: duration_seconds deviated 60.0% from historical average (MEDIUM severity)
- **tier1_filter**: articles_output deviated 89.5% from historical average (MEDIUM severity)
- **tier2_batch_eval**: duration_seconds deviated 86.7% from historical average (MEDIUM severity)
- **tier2_batch_eval**: articles_input deviated 89.5% from historical average (MEDIUM severity)
... and 26 more anomalies

## Recommendations
- Scraping success rate is 0.0% (below 85%). Consider increasing timeouts or adding backup RSS feeds.
- Detected 31 anomalies. Review error logs for details.

## Output Files
- Error Log: `data/logs/errors_20251031_155656.json`
- Context: `data/context/context_20251031_155656.json`
- Metrics: `data/metrics/metrics_20251031_155656.json`
