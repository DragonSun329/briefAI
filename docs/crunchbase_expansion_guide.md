# Crunchbase Expansion Guide for Bucket Coverage

## Current State (998 Companies)

The existing Crunchbase data covers the **top 998 AI companies by significance**.
However, this creates gaps in niche/vertical buckets.

## Buckets Needing Company Expansion

### Critical Gaps (0-1 companies)

| Bucket | Current | Target | Search Strategy |
|--------|---------|--------|-----------------|
| LLM Serving & Inference | 0 | 10+ | Search "MLOps", "inference", "model serving" |
| Fine-tuning & Training | 0 | 10+ | Search "fine-tuning", "training", "RLHF" |
| Synthetic Data & Eval | 0 | 10+ | Search "synthetic data", "evaluation", "data labeling" |
| AI Security & Safety | 0 | 10+ | Search "AI safety", "guardrails", "AI governance" |
| AI for Education | 0 | 10+ | Search "AI tutoring", "edtech AI", "learning AI" |
| AI for Gaming | 0 | 8+ | Search "game AI", "NPC", "procedural generation" |
| AI for Legal | 1 | 8+ | Search "legal AI", "contract AI", "legal tech" |
| AI for Climate | 1 | 8+ | Search "climate AI", "sustainability AI", "energy AI" |

### Thin Coverage (2-4 companies)

| Bucket | Current | Target | Search Strategy |
|--------|---------|--------|-----------------|
| Foundation Models | 3 | 15+ | Search "LLM", "foundation model" |
| Agent Frameworks | 4 | 15+ | Search "AI agent", "orchestration" |
| AI for Code | 2 | 10+ | Search "code AI", "developer AI" |
| Speech & Audio | 2 | 10+ | Search "voice AI", "TTS", "STT" |
| AI Chips & Hardware | 3 | 10+ | Search "AI chip", "accelerator" |
| Healthcare AI | 2 | 12+ | Search "medical AI", "clinical AI" |

## Scraping Workflow

### Using `crunchbase_clipboard.py`

1. **Run the monitor**:
   ```bash
   python scrapers/crunchbase_clipboard.py
   ```

2. **For each bucket gap**:
   - Go to Crunchbase Discover
   - Filter by: Industries = [bucket keywords]
   - Sort by: Funding (recent first) or CB Rank
   - Copy table data (Ctrl+A, Ctrl+C)
   - Monitor will capture automatically

3. **Recommended filters per search**:
   - Industries: AI, Machine Learning, [vertical]
   - Funding Status: Any funded
   - Employee Count: 10+ (filters noise)
   - Operating Status: Active

## CB Rank Guidance

- **Top 1000**: Already captured - skip
- **Rank 1000-5000**: Include if matches gap bucket
- **Rank 5000+**: Only include for critical gaps (Legal, Education, Gaming)
- **No rank/Unknown**: Include if clearly relevant to gap bucket

## Example: OROLabs (CB Rank ~3800)

- If OROLabs is an **AI Legal** company → **YES, include**
- If OROLabs is a generic AI startup → **Probably skip** (adds noise)

## Post-Collection

After collecting new companies:

1. **Merge datasets**:
   ```python
   # Combine old + new, deduplicate by name
   all_companies = existing + new_vertical_companies
   unique = {c['name'].lower(): c for c in all_companies}
   ```

2. **Re-run bucket tagging**:
   ```bash
   python -m utils.bucket_tagger
   ```

3. **Re-compute CCS scores**:
   ```bash
   python -m utils.bucket_scorer_runner
   ```

## Target Company Count

| Priority | Current | Target |
|----------|---------|--------|
| Total Companies | 998 | 1500-2000 |
| Companies per bucket (avg) | 3-4 | 8-12 |
| Min per bucket | 0 | 5 |

## Confidence Impact

Adding 500-1000 targeted companies will:
- Move bucket CCS confidence from 0.6 → 0.8
- Enable better velocity calculation (more data points)
- Reduce internal variance (more representative sample)
