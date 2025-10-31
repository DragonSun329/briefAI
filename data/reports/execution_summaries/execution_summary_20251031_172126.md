# Pipeline Execution Summary
**Run ID**: 20251031_172126
**Date**: 2025-10-31 17:23:22
**Duration**: 1m 56s
**Status**: ✅ SUCCESS

## Pipeline Flow
1. ✅ initialization (0s)
2. ✅ scraping (3s)
3. ⏸️  review_extraction (not started)
4. ✅ tier1_filter - 77 → 3 articles (0s)
5. ✅ tier2_batch_eval - 3 → 3 articles (9s)
6. ✅ tier3_5d_eval - 3 → 2 articles (26s)
7. ⏸️  trending_calculation (not started)
8. ✅ ranking (0s)
9. ✅ paraphrasing (22s)
10. ⏸️  review_summarization (not started)
11. ✅ entity_background (38s)
12. ✅ quality_validation (0s)
13. ✅ report_generation (17s)
14. ✅ finalization (0s)

## Metrics Summary
- **Articles**: 77 scraped → 2 final
- **Filter Rates**: Tier 1 (3.9%), Tier 2 (100.0%)
- **Token Usage**: 16,900 total (input: 13,400, output: 3,500)
- **Cost**: $0.0284 USD
- **LLM Calls**: 6 (avg latency: 2083ms)

## Performance vs. Historical Average
- No historical data available for comparison

## Anomalies Detected
- **initialization**: duration_seconds deviated 87.5% from historical average (MEDIUM severity)
- **scraping**: duration_seconds deviated 97.5% from historical average (MEDIUM severity)
- **tier1_filter**: duration_seconds deviated 55.0% from historical average (MEDIUM severity)
- **tier1_filter**: articles_output deviated 92.1% from historical average (MEDIUM severity)
- **tier2_batch_eval**: duration_seconds deviated 84.8% from historical average (MEDIUM severity)
... and 34 more anomalies

## Recommendations
- Scraping success rate is 0.0% (below 85%). Consider increasing timeouts or adding backup RSS feeds.
- Detected 39 anomalies. Review error logs for details.

## Output Files
- Report: `data/reports/weekly_briefing_None_20251031.md`
- Error Log: `data/logs/errors_20251031_172126.json`
- Context: `data/context/context_20251031_172126.json`
- Metrics: `data/metrics/metrics_20251031_172126.json`
