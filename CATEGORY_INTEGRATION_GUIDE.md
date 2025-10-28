# Category Integration Guide

## Overview

The evaluation pipeline uses **categories** to contextualize article evaluation. Categories are business-domain categories (fintech, data analytics, AI companies, etc.) that help the system:

1. **Tier 1 (ArticleFilter)**: Identify relevant articles based on keyword matching
2. **Tier 3 (NewsEvaluator)**: Score articles based on relevance to your business focus

## Category Structure

### What is a Category?

Each category in `config/categories.json` has this structure:

```json
{
  "id": "fintech_ai",
  "name": "Fintech AI Applications",
  "aliases": ["fintech", "finance", "banking", "lending", "fraud detection", ...],
  "priority": 10,
  "description": "AI applications in fintech: fraud detection, credit scoring, risk management..."
}
```

**Key fields:**
- **id**: Unique identifier (use this in code)
- **name**: Human-readable name
- **aliases**: Keywords that trigger category matching (used by Tier 1 filter)
- **priority**: Importance weighting (1-10 scale)
- **description**: What this category covers

### Available Categories

The system has **9 built-in categories**:

| ID | Name | Priority | Keywords |
|----|------|----------|----------|
| `fintech_ai` | Fintech AI Applications | 10 | fintech, fraud, lending, risk management |
| `data_analytics` | Data Analytics & ML | 10 | data science, machine learning, analytics |
| `marketing_ai` | Marketing & Growth AI | 9 | marketing, personalization, recommendation |
| `emerging_products` | AI Products & Tools | 9 | product, SaaS, startup, launch |
| `llm_tech` | LLM & Language Models | 8 | LLM, GPT, Claude, BERT, fine-tuning |
| `ai_companies` | Major AI Companies & Updates | 9 | OpenAI, Anthropic, NVIDIA, Google |
| `industry_cases` | Industry Applications & ROI | 8 | case study, deployment, ROI, impact |
| `compliance_policy` | AI Policy & Regulation | 7 | regulation, policy, privacy, ethics |
| `tech_stack` | AI Tech Stack & Infrastructure | 6 | framework, GPU, API, deployment |

### Default Categories

By default, 6 categories are selected:

```python
[
  "fintech_ai",
  "data_analytics",
  "marketing_ai",
  "emerging_products",
  "llm_tech",
  "ai_companies"
]
```

This reflects a company focused on fintech and AI products.

---

## How to Use Categories in the Pipeline

### Option 1: Use Default Categories (Recommended)

```python
from utils.category_loader import load_categories

# Load default categories (6 categories)
categories = load_categories()

# Or explicitly request defaults
categories = load_categories(category_ids=None)
```

### Option 2: Load Specific Categories

```python
from utils.category_loader import load_categories

# Load only fintech and data analytics
categories = load_categories(["fintech_ai", "data_analytics"])

# Result: 2 category dictionaries
```

### Option 3: Load All Categories

```python
from utils.category_loader import get_all_categories

# Load all 9 categories
categories = get_all_categories()
```

### Option 4: Load by Business Need

```python
from utils.category_loader import load_categories

# For a data science company
categories = load_categories([
    "data_analytics",
    "llm_tech",
    "tech_stack",
    "industry_cases"
])

# For a regulatory compliance focus
categories = load_categories([
    "compliance_policy",
    "fintech_ai",
    "industry_cases"
])
```

---

## Integration Points

### Tier 1: ArticleFilter

```python
from utils.article_filter import ArticleFilter
from utils.category_loader import load_categories

# Load categories
categories = load_categories()

# Initialize filter
tier1_filter = ArticleFilter(score_threshold=3.0)

# IMPORTANT: Pass categories as second argument
tier1_results = tier1_filter.filter_articles(articles, categories)
#                                           ^^^^^^^^  ^^^^^^^^^^
#                                           articles  categories
```

**What happens:**
- Filter extracts keywords from category `aliases`
- Matches keywords against article title, description, content
- Scores articles on keyword matches + recency + trending
- Returns articles scoring >= threshold

### Tier 3: NewsEvaluator

```python
from modules.news_evaluator import NewsEvaluator
from utils.category_loader import load_categories

# Load categories
categories = load_categories()

# Initialize evaluator
news_eval = NewsEvaluator()

# IMPORTANT: Pass categories as second argument
tier3_results = news_eval.evaluate_articles(articles, categories, top_n=12)
#                                          ^^^^^^^^  ^^^^^^^^^^
#                                          articles  categories
```

**What happens:**
- Evaluator passes category names to Claude
- Claude scores articles on 5 dimensions considering user's focus areas
- Returns top-N articles ranked by 5D weighted score

---

## Complete Pipeline Example

Here's how to use categories in a complete pipeline:

```python
from modules.web_scraper import WebScraper
from utils.article_filter import ArticleFilter
from modules.batch_evaluator import BatchEvaluator
from modules.news_evaluator import NewsEvaluator
from utils.category_loader import load_categories
from utils.cache_manager import CacheManager

# Load categories
categories = load_categories()  # Uses defaults

# Initialize components
cache_mgr = CacheManager()
scraper = WebScraper(cache_manager=cache_mgr)

# Step 1: Scrape articles
articles = scraper.scrape_all(days_back=7, use_cache=False)

# Step 2: Tier 1 - Pre-filter with categories
tier1_filter = ArticleFilter(score_threshold=3.0)
tier1_results = tier1_filter.filter_articles(articles, categories)  # ← Pass categories

# Step 3: Tier 2 - Batch evaluation
batch_eval = BatchEvaluator()
tier2_results = batch_eval.evaluate_batch(tier1_results)

# Step 4: Tier 3 - Full 5D evaluation with categories
news_eval = NewsEvaluator()
tier3_results = news_eval.evaluate_articles(tier2_results, categories, top_n=12)  # ← Pass categories

# Step 5: Paraphrase
paraphraser = ArticleParaphraser(min_length=500, max_length=600)
final_articles = paraphraser.paraphrase_articles(tier3_results)
```

---

## Running the Complete Pipeline

### Quick Start: Default Categories

```bash
python3 run_pipeline_with_categories.py
```

This will:
- Load default 6 categories
- Scrape from 44 sources
- Filter → Evaluate → Score → Paraphrase
- Select top 12 articles
- Output to `data/pipeline_output.json`

### Custom Categories

```bash
python3 run_pipeline_with_categories.py \
  --categories fintech_ai data_analytics llm_tech \
  --top-n 15
```

This will:
- Load 3 specific categories (fintech, data analytics, LLM)
- Select top 15 articles instead of default 12

### Quick Test: Early Exit at Tier 2

```bash
python3 run_pipeline_with_categories.py --early-exit
```

This will:
- Run only Tier 1-2 (no expensive Tier 3)
- Useful for testing and debugging
- Still returns ~10 good articles

### All Options

```bash
python3 run_pipeline_with_categories.py --help

Options:
  --categories FINTECH_AI DATA_ANALYTICS ...
                        Specific category IDs (defaults to: fintech_ai,
                        data_analytics, marketing_ai, emerging_products,
                        llm_tech, ai_companies)
  --top-n 12           Number of final articles (default: 12)
  --early-exit         Exit after Tier 2 (skip Tier 3 5D evaluation)
```

---

## Category Loader API Reference

### load_categories(category_ids=None)

Load specific categories or defaults.

```python
from utils.category_loader import load_categories

# Load default categories
categories = load_categories()

# Load specific categories
categories = load_categories(["fintech_ai", "llm_tech"])

# Returns:
# [
#   {
#     "id": "fintech_ai",
#     "name": "Fintech AI Applications",
#     "aliases": [...],
#     "priority": 10,
#     "description": "..."
#   },
#   {...}
# ]
```

### get_all_categories()

Get all 9 available categories.

```python
from utils.category_loader import get_all_categories

all_cats = get_all_categories()  # Returns list of all 9 categories
```

### get_default_categories()

Get the default category set.

```python
from utils.category_loader import get_default_categories

defaults = get_default_categories()  # Returns 6 default categories
```

### get_company_context()

Get company context information (used by NewsEvaluator).

```python
from utils.category_loader import get_company_context

context = get_company_context()
# Returns:
# {
#   "business": "Fintech & AI Products",
#   "industry": "Financial Technology / AI",
#   "focus_areas": ["Risk Management", "Credit Decisions", ...]
# }
```

### list_all_category_ids()

Get list of all available category IDs.

```python
from utils.category_loader import list_all_category_ids

ids = list_all_category_ids()
# Returns: ["fintech_ai", "data_analytics", ..., "tech_stack"]
```

### get_category_by_id(category_id)

Get a single category by ID.

```python
from utils.category_loader import get_category_by_id

cat = get_category_by_id("fintech_ai")
# Returns the category dict or None
```

---

## How Categories Affect Scoring

### Tier 1 Filter

Categories influence **keyword matching**:

```
Article title: "AI Fraud Detection System Launched"
Category: "fintech_ai"
Aliases: ["fintech", "fraud detection", "lending", ...]

Matching: "fraud detection" ✓ in title
Score boost: +1.5 points (keyword match)

Final Tier 1 score: 5.2 (passes 3.0 threshold)
```

### Tier 3 Evaluator

Categories inform **5D scoring dimensions**:

When Claude evaluates an article, it considers:
- "User cares about: fintech, data analytics, LLM"
- "These categories suggest focus on: Risk management, ML tools, language models"
- Scores the article on 5 dimensions considering this context

Example:
```
Article: "New GPT-4 Capabilities for Financial Analysis"

5D Scores (considering user's fintech + llm_tech focus):
- Market Impact: 8 (GPT-4 is significant market news)
- Competitive Impact: 8 (affects all fintech competitors)
- Strategic Relevance: 9 (directly relevant to fintech + LLM focus)
- Operational Relevance: 7 (useful for finance teams)
- Credibility: 9 (OpenAI is authoritative)

Weighted Score: (8×0.25) + (8×0.20) + (9×0.20) + (7×0.15) + (9×0.10) = 8.3
```

---

## Customizing Categories

### Add a New Category

Edit `config/categories.json`:

```json
{
  "id": "healthcare_ai",
  "name": "AI in Healthcare",
  "aliases": ["healthcare", "medical", "diagnosis", "treatment", "clinical"],
  "priority": 10,
  "description": "AI applications in healthcare and medicine"
}
```

Then use:
```python
categories = load_categories(["healthcare_ai"])
```

### Modify Keywords for a Category

In `config/categories.json`, expand the `aliases` list:

```json
{
  "id": "fintech_ai",
  "name": "Fintech AI Applications",
  "aliases": [
    "fintech", "finance", "banking", "lending",
    "fraud detection", "risk management",
    "blockchain", "cryptocurrency",  // ← New keywords
    "payment", "settlement"           // ← New keywords
  ],
  ...
}
```

### Change Default Categories

In `config/categories.json`:

```json
{
  "default_categories": [
    "fintech_ai",
    "data_analytics",
    "marketing_ai",
    "ai_companies",
    "your_new_category"  // ← Add your category
  ],
  ...
}
```

---

## Troubleshooting

### Error: "No valid categories found"

**Cause**: Requested category IDs don't exist

**Fix**:
```python
from utils.category_loader import list_all_category_ids

# Check what's available
ids = list_all_category_ids()
print(ids)  # ["fintech_ai", "data_analytics", ...]

# Use valid IDs
categories = load_categories(["fintech_ai", "data_analytics"])
```

### Error: "categories parameter missing"

**Cause**: Forgot to pass categories to filter or evaluator

**Fix**:
```python
# Wrong:
tier1_results = tier1_filter.filter_articles(articles)  # ✗ Missing categories

# Correct:
categories = load_categories()
tier1_results = tier1_filter.filter_articles(articles, categories)  # ✓
```

### Article isn't getting filtered in Tier 1

**Cause**: Keywords don't match article content

**Solution**: Check category keywords and article content:
```python
# Look at what keywords are being used
categories = load_categories(["fintech_ai"])
for cat in categories:
    print(f"{cat['id']}: {cat['aliases']}")

# Manual test:
article = {"title": "My article title", "content": "..."}
if any(kw in article['title'].lower() for kw in ["fintech", "fraud"]):
    print("Matches!")
```

### Article scoring seems wrong

**Cause**: Categories not providing enough context for Claude

**Solution**:
- Use more specific categories instead of all 9
- Or add company context via `get_company_context()`
- Or modify article content to be more explicit about relevance

---

## Best Practices

### 1. Use Specific Categories, Not All

```python
# Good: Focused on your business
categories = load_categories(["fintech_ai", "data_analytics", "llm_tech"])

# Bad: Too broad
categories = get_all_categories()  # All 9 categories
```

### 2. Keep Categories Consistent

Use the same categories across your pipeline:
```python
SELECTED_CATEGORIES = load_categories(["fintech_ai", "data_analytics"])

# Use SELECTED_CATEGORIES in:
# - Tier 1 filter
# - Tier 3 evaluator
# - Report generation
```

### 3. Update Company Context If Needed

If your company focus changes, update:
- `config/categories.json` → `company_context`
- `config/categories.json` → `default_categories`

### 4. Test with Small Samples

Before running full pipeline, test categories:
```python
# Test categories load correctly
from utils.category_loader import load_categories
categories = load_categories(["fintech_ai"])
assert len(categories) == 1
assert categories[0]['id'] == "fintech_ai"
```

### 5. Document Your Category Choice

In your pipeline script, document why categories were selected:
```python
# We focus on fintech applications and the financial market impact
# of LLMs. These 3 categories cover our core business areas:
CATEGORIES = load_categories([
    "fintech_ai",       # Our primary business
    "llm_tech",         # Technology we use
    "ai_companies"      # Market intelligence
])
```

---

## Summary

Categories are the **business context** for article evaluation. They:

1. **Guide Tier 1 filtering** via keyword matching
2. **Inform Tier 3 scoring** by telling Claude your focus areas
3. **Ensure relevance** to your business domain

**Key files:**
- `config/categories.json` - Define all categories + company context
- `utils/category_loader.py` - Load categories into memory
- `run_pipeline_with_categories.py` - Complete pipeline example

**Next steps:**
1. Review your `config/categories.json` and company context
2. Run `run_pipeline_with_categories.py` to test the full pipeline
3. Adjust categories if needed for your business
4. Generate your first complete report with proper category integration!
