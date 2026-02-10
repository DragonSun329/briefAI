# Chinese AI Ecosystem News Pipeline

## Overview

Add a dedicated Chinese AI ecosystem news pipeline ("china_ai") to BriefAI's multi-pipeline architecture. This pipeline focuses on broader Chinese AI industry coverage in original Chinese text, complementing the existing investing pipeline's Chinese VC portfolio data.

**Goal:** Chinese AI ecosystem coverage (regulations, model releases, industry trends) in 原文 (original Chinese).

**Not in scope:** Company-specific news alerts, English translation.

## Architecture

```
pipelines.json
├── news (existing - general AI)
├── product (existing - product launches)
├── investing (existing - VC/funding)
└── china_ai (NEW - Chinese AI ecosystem)
    ├── sources_china_ai.json
    ├── categories_china_ai.json
    └── output: china_ai_briefing_YYYY-MM-DD.md
```

The pipeline reuses existing `PipelineOrchestrator` infrastructure - no new orchestration code needed.

## Implementation Tasks

### Task 1: Create Chinese AI source configuration

**File:** `config/sources_china_ai.json`

**Sources to add:**

| Source | Type | Focus | Credibility |
|--------|------|-------|-------------|
| 机器之心 (Synced) | RSS | LLM/研究/技术 | 9 |
| 量子位 (QbitAI) | RSS | 国内AI新闻 | 8 |
| 36氪 AI频道 | Web | 创业/融资 | 8 |
| 新智元 | RSS | 大模型/AGI | 8 |
| 雷锋网 AI | RSS | 技术/产品 | 8 |
| AI科技评论 | Web | 行业分析 | 7 |
| PaperWeekly | RSS | 论文/学术 | 9 |
| 智源社区 (BAAI) | Web | 国产模型/研究 | 9 |

**Structure:**
```json
{
  "sources": [
    {
      "id": "jiqizhixin_main",
      "name": "机器之心",
      "url": "https://www.jiqizhixin.com",
      "type": "rss",
      "rss_url": "https://www.jiqizhixin.com/rss",
      "enabled": true,
      "categories": ["llm_domestic", "ai_research", "industry_trends"],
      "language": "zh-CN",
      "credibility_score": 9,
      "relevance_weight": 10,
      "focus_tags": ["大模型", "AI研究", "技术前沿"]
    }
    // ... more sources
  ]
}
```

**Steps:**
1. Create `config/sources_china_ai.json` with 8 Chinese AI sources
2. Test RSS feeds are accessible (机器之心, 量子位, 新智元, PaperWeekly)
3. For web-only sources, note they require `type: "web"` scraping

**Verification:** `python -c "import json; print(len(json.load(open('config/sources_china_ai.json'))['sources']))"`

---

### Task 2: Create Chinese AI categories

**File:** `config/categories_china_ai.json`

**Categories:**

| ID | Name | Description |
|----|------|-------------|
| llm_domestic | 国产大模型 | 文心、通义、智谱、DeepSeek等 |
| ai_regulation | AI监管政策 | 算法备案、数据安全、生成式AI管理 |
| ai_chips | 国产芯片 | 华为昇腾、寒武纪、地平线、壁仞 |
| ai_research | AI研究 | 学术论文、技术突破 |
| industry_trends | 行业动态 | 应用落地、市场趋势 |
| ai_investment | AI投融资 | 融资轮次、估值、IPO |

**Steps:**
1. Create `config/categories_china_ai.json`
2. Add Chinese aliases for each category (e.g., `"大模型", "LLM", "生成式AI"`)
3. Set appropriate priorities (llm_domestic: 10, ai_regulation: 9, etc.)

**Verification:** `python -c "import json; c=json.load(open('config/categories_china_ai.json')); print([x['id'] for x in c['categories']])"`

---

### Task 3: Register pipeline in pipelines.json

**File:** `config/pipelines.json`

**Add to `pipelines` object:**
```json
"china_ai": {
  "name": "中国AI生态",
  "description": "Chinese AI ecosystem: domestic models, regulations, chips, research",
  "sources_file": "sources_china_ai.json",
  "categories_file": "categories_china_ai.json",
  "output_prefix": "china_ai_briefing",
  "enabled": true,
  "schedule": {
    "frequency": "daily",
    "priority": 4
  },
  "scoring": {
    "weights": {
      "strategic_importance": 0.25,
      "domestic_relevance": 0.20,
      "regulatory_impact": 0.20,
      "technical_significance": 0.15,
      "credibility": 0.10,
      "novelty": 0.10
    }
  },
  "entity_focus": ["companies", "models", "regulations", "technologies"],
  "trend_radar_contribution": true
}
```

**Steps:**
1. Add `china_ai` pipeline config to `pipelines.json`
2. Add to `orchestrator.combined_report.sections` array
3. Add to `trend_radar.aggregate_from` array

**Verification:** `python -c "import json; p=json.load(open('config/pipelines.json')); print('china_ai' in p['pipelines'])"`

---

### Task 4: Create Chinese AI report template

**File:** `config/report_template_china_ai.md`

**Structure:**
```markdown
# 中国AI生态简报 - {{date}}

## 今日要点
{{executive_summary}}

## 国产大模型动态
{{llm_domestic_section}}

## AI监管政策
{{ai_regulation_section}}

## 国产芯片
{{ai_chips_section}}

## 研究进展
{{ai_research_section}}

## 行业动态
{{industry_trends_section}}

## 投融资
{{ai_investment_section}}
```

**Steps:**
1. Create `config/report_template_china_ai.md`
2. All section headers and formatting in Chinese

**Verification:** File exists and contains Chinese headers

---

### Task 5: Test pipeline end-to-end

**Command:** `python pipeline/orchestrator.py --pipeline china_ai --date 2026-01-22`

**Steps:**
1. Run pipeline with single date
2. Verify sources are scraped (check logs for article counts)
3. Verify categories are assigned
4. Check output file: `reports/china_ai_briefing_2026-01-22.md`
5. Verify Chinese text preserved (not garbled encoding)

**Verification:**
```bash
python pipeline/orchestrator.py --pipeline china_ai --date 2026-01-22
ls reports/china_ai_briefing_*.md
```

---

### Task 6: Add to combined daily run

**Steps:**
1. Update `scripts/cron_catchup.py` if needed
2. Test full orchestrator run: `python pipeline/orchestrator.py --all`
3. Verify china_ai appears in combined report

**Verification:** `python pipeline/orchestrator.py --all` completes without errors

## Files to Create/Modify

| Action | File |
|--------|------|
| CREATE | `config/sources_china_ai.json` |
| CREATE | `config/categories_china_ai.json` |
| CREATE | `config/report_template_china_ai.md` |
| MODIFY | `config/pipelines.json` |

## Dependencies

- No new Python packages required
- Uses existing `WebScraper`, `PipelineOrchestrator`, `ReportFormatter`
- RSS feeds must be accessible from network

## Success Criteria

1. Pipeline produces daily Chinese AI briefing in original Chinese
2. Categories correctly identify domestic model news, regulations, chips
3. Integrates with trend radar for cross-pipeline analysis
4. No encoding issues with Chinese characters
