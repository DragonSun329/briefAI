# AI Briefing Agent - Visual Architecture

## System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER INTERFACE                            │
│                                                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ Interactive  │  │   CLI Args   │  │   Automated Cron     │  │
│  │    Mode      │  │   --input    │  │   (Weekly Run)       │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                     MAIN ORCHESTRATOR                            │
│                        (main.py)                                 │
│                                                                   │
│  Workflow: Select → Scrape → Evaluate → Paraphrase → Format    │
└───────┬────────┬────────┬────────┬────────┬─────────────────────┘
        │        │        │        │        │
        ▼        ▼        ▼        ▼        ▼
┌───────────────────────────────────────────────────────────────────┐
│                        CORE MODULES                                │
│                                                                    │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐│
│  │ Category   │  │    Web     │  │    News    │  │  Article   ││
│  │ Selector   │  │  Scraper   │  │ Evaluator  │  │ Paraphraser││
│  │            │  │            │  │            │  │            ││
│  │ • Parse    │  │ • RSS      │  │ • Impact   │  │ • Summarize││
│  │   input    │  │ • HTML     │  │ • Relevance│  │ • Mandarin ││
│  │ • Map to   │  │ • Multi-   │  │ • Recency  │  │ • Paragraph││
│  │   categories│ │   source   │  │ • Credibility│ │ • 150-250 ││
│  │            │  │ • Cache    │  │ • Rank     │  │   chars    ││
│  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘│
│        │               │               │               │        │
└────────┼───────────────┼───────────────┼───────────────┼────────┘
         │               │               │               │
         │               │               │               ▼
         │               │               │        ┌────────────┐
         │               │               │        │  Report    │
         │               │               │        │ Formatter  │
         │               │               │        │            │
         │               │               │        │ • Executive│
         │               │               │        │   Summary  │
         │               │               │        │ • Key      │
         │               │               │        │   Insights │
         │               │               │        │ • Jinja2   │
         │               │               │        └─────┬──────┘
         │               │               │              │
┌────────┼───────────────┼───────────────┼──────────────┼────────┐
│        ▼               ▼               ▼              ▼         │
│                     UTILITY LAYER                               │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐│
│  │ Claude       │  │   Cache      │  │      Logger          ││
│  │ Client       │  │   Manager    │  │                      ││
│  │              │  │              │  │ • Console + File     ││
│  │ • API calls  │  │ • File-based │  │ • Daily rotation     ││
│  │ • Retry      │  │ • TTL        │  │ • Multiple levels    ││
│  │ • JSON parse │  │ • Expiry     │  │                      ││
│  └──────┬───────┘  └──────┬───────┘  └──────────────────────┘│
└─────────┼──────────────────┼─────────────────────────────────────┘
          │                  │
          ▼                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                      EXTERNAL SERVICES                           │
│                                                                   │
│  ┌─────────────────┐  ┌────────────────────────────────────┐   │
│  │ Anthropic       │  │     News Sources                   │   │
│  │ Claude API      │  │  • 机器之心 (RSS)                   │   │
│  │ (Sonnet 4.5)    │  │  • 量子位 (Web)                     │   │
│  │                 │  │  • TechCrunch AI (RSS)              │   │
│  │                 │  │  • MIT Tech Review (RSS)            │   │
│  │                 │  │  • arXiv (RSS)                      │   │
│  │                 │  │  • 36氪 AI (Web)                    │   │
│  │                 │  │  • AIBase (Web)                     │   │
│  └─────────────────┘  └────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────────┘
          │                              │
          ▼                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                          OUTPUT                                  │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │         data/reports/ai_briefing_YYYYMMDD.md             │  │
│  │                                                            │  │
│  │  • 本周概览 (Executive Summary)                            │  │
│  │  • 重点资讯 (Top Articles by Category)                    │  │
│  │  • 关键洞察 (Strategic Insights)                           │  │
│  │  • 延伸阅读 (Additional Readings)                          │  │
│  └──────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────┘
```

## Data Flow Sequence

```
1. USER INPUT
   ↓
   "我想了解大模型和AI应用"
   ↓
2. CATEGORY SELECTOR (Claude)
   ↓
   [
     {id: "llm", name: "大模型", priority: 10},
     {id: "ai_apps", name: "AI应用", priority: 9}
   ]
   ↓
3. WEB SCRAPER (RSS + Cache)
   ↓
   [
     {title: "...", url: "...", content: "...", source: "机器之心"},
     {title: "...", url: "...", content: "...", source: "TechCrunch"},
     ... (50+ articles)
   ]
   ↓
4. NEWS EVALUATOR (Claude)
   ↓
   [
     {
       title: "...",
       evaluation: {
         impact: 9, relevance: 8, recency: 7, credibility: 9,
         avg_score: 8.25,
         key_takeaway: "..."
       }
     },
     ... (top 15 articles)
   ]
   ↓
5. ARTICLE PARAPHRASER (Claude)
   ↓
   [
     {
       title: "...",
       paraphrased_content: "流畅的中文段落，150-250字符...",
       fact_check: "passed"
     },
     ... (15 articles)
   ]
   ↓
6. REPORT FORMATTER (Claude + Jinja2)
   ↓
   Markdown Report:
   - Executive Summary (2-3 sentences)
   - Articles grouped by category
   - Key strategic insights (3-5 points)
   - Additional reading links
   ↓
7. OUTPUT FILE
   data/reports/ai_briefing_20241024.md
```

## Module Dependencies

```
main.py
├── modules/category_selector.py
│   └── utils/claude_client.py
│
├── modules/web_scraper.py
│   └── utils/cache_manager.py
│
├── modules/news_evaluator.py
│   └── utils/claude_client.py
│
├── modules/article_paraphraser.py
│   └── utils/claude_client.py
│
└── modules/report_formatter.py
    └── utils/claude_client.py

utils/
├── claude_client.py
│   └── anthropic (external)
├── cache_manager.py
│   └── json, hashlib
└── logger.py
    └── loguru (external)
```

## Configuration Files

```
config/
├── sources.json          ─────►  Web Scraper
│   ├── id, name, url
│   ├── type (rss/web)
│   ├── categories
│   └── credibility_score
│
├── categories.json       ─────►  Category Selector
│   ├── id, name
│   ├── aliases
│   ├── priority
│   └── description
│
└── report_template.md    ─────►  Report Formatter
    ├── Jinja2 syntax
    ├── {{executive_summary}}
    ├── {{articles_by_category}}
    └── {{key_insights}}
```

## File Structure Map

```
briefAI/
│
├── 📄 main.py                    # Main orchestrator (CLI entry point)
│
├── 📁 modules/                   # Core business logic
│   ├── category_selector.py
│   ├── web_scraper.py
│   ├── news_evaluator.py
│   ├── article_paraphraser.py
│   └── report_formatter.py
│
├── 📁 utils/                     # Shared utilities
│   ├── claude_client.py
│   ├── cache_manager.py
│   └── logger.py
│
├── 📁 config/                    # Configuration files
│   ├── sources.json
│   ├── categories.json
│   └── report_template.md
│
├── 📁 data/
│   ├── cache/                    # Cached scraped articles
│   └── reports/                  # Generated reports (output)
│
├── 📁 logs/                      # Application logs
│
├── 📄 requirements.txt           # Python dependencies
├── 📄 .env.example               # Environment variables template
├── 📄 .gitignore                 # Git ignore rules
├── 📄 setup.sh                   # Quick setup script
│
└── 📁 Documentation/
    ├── README.md                 # Setup and usage guide
    ├── CLAUDE.md                 # Project requirements
    ├── ARCHITECTURE.md           # System design
    ├── GUIDE.md                  # Implementation guide
    ├── PROMPTS.md                # Prompt templates
    ├── PROJECT_SUMMARY.md        # Build summary
    └── ARCHITECTURE_VISUAL.md    # This file
```

## Claude API Usage Pattern

```
┌───────────────────────────────────────────────────┐
│         Claude API Call Pattern                   │
├───────────────────────────────────────────────────┤
│                                                    │
│  1. Category Selection        → 1 API call        │
│     Input: User preferences                       │
│     Output: Structured categories                 │
│                                                    │
│  2. Article Evaluation        → N API calls       │
│     Input: Article content                        │
│     Output: Scores + rationale                    │
│     (N = number of articles, typically 50-100)    │
│                                                    │
│  3. Article Paraphrasing      → N API calls       │
│     Input: Full article                           │
│     Output: 150-250 char summary                  │
│     (N = top articles, typically 15)              │
│                                                    │
│  4. Executive Summary         → 1 API call        │
│     Input: All selected articles                  │
│     Output: 2-3 sentence overview                 │
│                                                    │
│  5. Key Insights              → 1 API call        │
│     Input: All selected articles                  │
│     Output: 3-5 strategic takeaways               │
│                                                    │
│  TOTAL: ~80-130 API calls per report              │
│  COST: ~$0.50-$1.00 per report                   │
│                                                    │
└───────────────────────────────────────────────────┘
```

## Performance Optimization

```
┌─────────────────────────────────────────────────┐
│         Caching Strategy                         │
├─────────────────────────────────────────────────┤
│                                                  │
│  Level 1: Article Scraping (24h TTL)           │
│  ├─ Key: source_id + days_back                 │
│  ├─ Saves: HTTP requests                       │
│  └─ Effectiveness: 80%+ on re-runs             │
│                                                  │
│  Level 2: Article Evaluation (24h TTL)         │
│  ├─ Key: article_url hash                      │
│  ├─ Saves: Claude API calls                    │
│  └─ Effectiveness: 60%+ on re-runs             │
│                                                  │
│  Level 3: API Response (in-memory)             │
│  ├─ Key: Request hash                          │
│  ├─ Saves: Duplicate API calls in same session │
│  └─ Effectiveness: 20%+ savings                │
│                                                  │
└─────────────────────────────────────────────────┘
```

## Error Handling Flow

```
┌────────────────────────────────────────────────┐
│         Error Recovery Strategy                 │
├────────────────────────────────────────────────┤
│                                                 │
│  API Errors:                                   │
│  └─► Retry (3 attempts, exponential backoff)  │
│      └─► Log error                             │
│          └─► Continue with next item           │
│                                                 │
│  Scraping Errors:                              │
│  └─► Skip source                               │
│      └─► Log warning                           │
│          └─► Continue with other sources       │
│                                                 │
│  Evaluation Errors:                            │
│  └─► Use default score (5.0)                  │
│      └─► Log warning                           │
│          └─► Include article with caution flag │
│                                                 │
│  Paraphrasing Errors:                          │
│  └─► Use truncated original content           │
│      └─► Log error                             │
│          └─► Mark as "needs review"           │
│                                                 │
└────────────────────────────────────────────────┘
```

## Quality Assurance Checks

```
┌──────────────────────────────────────────┐
│       Quality Gates                       │
├──────────────────────────────────────────┤
│                                           │
│  ✓ Article Evaluation                    │
│    • Min score threshold: 6.0            │
│    • Min credibility: 7.0                │
│                                           │
│  ✓ Paraphrasing Validation               │
│    • Length: 150-250 characters          │
│    • Format: Paragraph (not bullets)     │
│    • Language: Mandarin Chinese          │
│    • Fact check: Pass                    │
│                                           │
│  ✓ Report Completeness                   │
│    • Min articles: 5                     │
│    • Max articles: 15                    │
│    • All sections present                │
│    • Valid markdown syntax               │
│                                           │
└──────────────────────────────────────────┘
```

---

**This visual architecture document provides a comprehensive overview of the system design, data flow, and component relationships.**
