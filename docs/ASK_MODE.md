# Ask Mode - Interactive Research

**Version:** 1.2  
**Status:** Experimental  
**Added:** 2026-02-11  
**Updated:** 2026-02-11 (v1.2: Reflection, Daily Diff, Stable Evidence)

## Overview

Ask Mode provides Dexter-style interactive research queries against briefAI's local pipeline artifacts. It runs an agentic loop (plan → tool calls → reflect → answer) to answer questions while maintaining:

- **Offline/Deterministic**: Only reads local artifacts, no network calls
- **Experiment Isolation**: Writes only to experiment-specific ask logs
- **Reproducibility**: Same question + artifacts = same result
- **Audit Trail**: Complete trace of all tool calls and reasoning

## What's New in v1.1

### Freshness Banner
Every answer now starts with a data recency banner:
```
📌 Data scope: local artifacts only | Latest available: 2026-02-11 | Experiment: v2_2_forward_test
```

### Evidence Citations
All claims include grep-able citations:
```
[evidence: data/meta_signals/meta_signals_2026-02-11.json#meta_id=abc123]
[evidence: data/briefs/analyst_brief_2026-02-11.md#L1-L50]
```

### Intent Router
Queries are classified into intents to reduce tool thrash:
- `trend_explain` - Explain a trend/concept
- `entity_status` - Status of a specific entity
- `bull_bear_case` - Bull/bear analysis
- `compare` - Compare entities/trends
- `what_changed` - Recent changes
- `daily_change` - **v1.2**: "What changed today?" with diff tool
- `forecast_check` - Check predictions
- `general` - General research

## What's New in v1.2

### Reflection Self-Check Loop
Answers are now validated before output:
```
plan → tools → draft → self-check → (repair?) → final
```

Validation rules (deterministic, no LLM):
- Must include freshness banner
- Must cite ≥2 independent sources
- Every Key Takeaway needs citation
- Must include measurable prediction

If validation fails: ONE repair attempt allowed. If still failing: `⚠️ Partial Confidence` banner added.

### Daily Diff Mode
Ask "What changed today?" to get structured comparison:
```bash
python -m briefai ask "what changed in AI today?" --experiment v2_2_forward_test
```

Output includes:
- New/disappeared signals
- Strengthened/weakened signals
- New/resolved predictions

### Stable Evidence Anchors
Citations no longer use fragile line numbers:

**Before (fragile):** `[evidence: file.md#L45-L60]`  
**After (stable):** `[evidence: file.json#meta_id=abc123]`

Anchor types:
- JSON: `#meta_id=`, `#prediction_id=`, `#signal_id=`
- Markdown: `#heading=slug&quote=hash`

### Evidence Appendix
Every answer ends with deduplicated evidence list:
```markdown
---
## Evidence Used
- [evidence: data/meta_signals/...#meta_id=sig1] (as of 2026-02-11)
- [evidence: data/briefs/...#heading=summary&quote=abc] (as of 2026-02-11)
```

### Enhanced Staleness Warning
Banner now includes staleness indicator:
```
📌 Data scope: local briefAI artifacts only
Latest available: 2026-02-11
Experiment: v2_2_forward_test
Staleness: fresh (today)  ← NEW
```

## Quick Start

```bash
# Basic question
python -m briefai ask "What signals suggest OpenAI pricing changes?" --experiment v2_2_forward_test

# Verbose mode (see tool calls)
python -m briefai ask "Is LangChain adoption accelerating?" --verbose

# JSON output for scripting
python -m briefai ask "Question here" --json

# List available tools
python -m briefai ask --list-tools
```

## How It Works

### Agentic Loop

1. **Plan**: LLM generates a research plan based on the question
2. **Execute**: Tools are called to gather evidence from local artifacts
3. **Reflect**: Quality of gathered evidence is evaluated
4. **Answer**: Final answer with measurable predictions is generated

### Loop Prevention

The scratchpad tracks all tool calls and prevents infinite loops:

- ⚠️ Warning after exact duplicate calls
- ⚠️ Warning after 3 calls to the same tool
- ⚠️ Detection of semantically similar queries

### Quality Gates

Deterministic rules (no LLM) validate answer quality:

| Check | Requirement | Consequence if Failed |
|-------|-------------|----------------------|
| Source Diversity | ≥2 source categories | Confidence = "insufficient" |
| Measurable Checks | ≥2 predictions | Quality note added |
| Media-Only | Has non-media sources | Confidence capped, review_required |

## Available Tools

### 1. search_meta_signals

Search synthesized meta-signals (high-level trends).

```python
search_meta_signals(
    query="AI pricing",
    date_range=("2026-02-01", "2026-02-11")  # optional
)
```

### 2. search_signals

Search raw signals from pipelines (news, financial, social, etc.).

```python
search_signals(
    query="OpenAI",
    date_range=("2026-02-01", "2026-02-11"),  # optional
    signal_types=["news_signals", "financial_signals"]  # optional
)
```

### 3. get_entity_profile

Get entity profile with scores and mention velocity.

```python
get_entity_profile(entity="OpenAI")
```

### 4. summarize_daily_brief

Get daily brief summaries for a date.

```python
summarize_daily_brief(date="2026-02-11")
```

### 5. retrieve_evidence

Retrieve evidence observations for a metric/entity.

```python
retrieve_evidence(
    entity="OpenAI",
    canonical_metric="article_count"
)
```

### 6. list_hypotheses

List active hypotheses for a date.

```python
list_hypotheses(date="2026-02-11")
```

### 7. get_forecast_snapshot

Get frozen forecast snapshot.

```python
get_forecast_snapshot(
    date="2026-02-09",
    experiment_id="v2_2_forward_test"
)
```

## Output Format

### Console Output

```
============================================================
📋 ANSWER
============================================================
Based on the meta-signals from the past week, there are indications
of pricing shifts in the AI market...

------------------------------------------------------------
📊 QUALITY ASSESSMENT
------------------------------------------------------------
Confidence: medium
Review Required: False

Notes:
  • Found 2 source categories

------------------------------------------------------------
📈 MEASURABLE PREDICTIONS
------------------------------------------------------------
  • OpenAI api_pricing → down (within 30d)
  • enterprise_contracts article_count → up (within 14d)

------------------------------------------------------------
📝 METADATA
------------------------------------------------------------
Tool Calls: 3
Evidence Sources: 5
Loop Iterations: 4
Duration: 2341ms
Commit: 325adbf7
```

### JSON Output (--json)

```json
{
  "question": "What signals suggest OpenAI pricing changes?",
  "experiment_id": "v2_2_forward_test",
  "plan": "1. Search meta-signals for pricing...",
  "tool_calls": [
    {
      "tool_name": "search_meta_signals",
      "arguments": {"query": "pricing"},
      "result_summary": "Found 3 meta-signals",
      "result_type": "success"
    }
  ],
  "evidence_links": [
    {
      "source_type": "meta_signal",
      "source_id": "abc123",
      "category": "meta",
      "snippet": "Cost dynamics shifting..."
    }
  ],
  "measurable_checks": [
    {
      "metric": "api_pricing",
      "entity": "OpenAI",
      "direction": "down",
      "window_days": 30
    }
  ],
  "final_answer": "Based on evidence...",
  "confidence_level": "medium",
  "review_required": false,
  "commit_hash": "325adbf7f2e634c906014f593fb0f1e4ed50c46c",
  "timestamp_utc": "2026-02-11T14:30:00Z",
  "duration_ms": 2341
}
```

## Ask Log

All queries are logged to:

```
data/public/experiments/{experiment_id}/ask_logs/ask_history.jsonl
```

This is an **append-only** log. Each line is a complete JSON record of:

- Question and plan
- All tool calls with arguments and results
- Evidence links and measurable checks
- Final answer and quality assessment
- Commit hash and timestamp

## Reproducibility Stance

### What's Reproducible

1. **Same artifacts → Same tool results**: Tools only read local files
2. **Same LLM seed → Same reasoning**: Temperature = 0.0 by default
3. **Auditable trace**: Every tool call is logged with arguments

### What May Vary

1. **Different artifacts**: Running after a new pipeline produces different data
2. **LLM updates**: Model updates may change reasoning
3. **Code changes**: New tool implementations may return different formats

### Reproducing a Past Query

```python
# 1. Check out the commit from the log
git checkout <commit_hash>

# 2. Ensure same artifacts exist
# (artifacts are dated, so use same date range)

# 3. Run same question
python -m briefai ask "same question" --experiment same_experiment
```

## Write Protection

Ask mode **cannot write** to:

- `forecast_history.jsonl` (forecasting ledger)
- `daily_snapshot_*.json` (frozen predictions)
- `run_metadata_*.json` (pipeline metadata)

This ensures experiment isolation is maintained.

## Configuration

### Engine Config

```python
from briefai.ask.engine import AskEngine, EngineConfig

config = EngineConfig(
    experiment_id="v2_2_forward_test",
    max_iterations=10,      # Max tool call loops
    temperature=0.0,        # LLM temperature (0 = deterministic)
    verbose=False,          # Print progress
)

engine = AskEngine(config=config)
result = engine.ask("Question?")
```

### Quality Gates Config

```python
from briefai.ask.quality_gates import QualityGates

gates = QualityGates(
    min_source_categories=2,          # Require diverse sources
    min_measurable_checks=2,          # Require predictions
    media_only_confidence_cap="low",  # Cap if only media
)
```

## Troubleshooting

### "DataMissing" Results

This means the requested data doesn't exist locally. Solutions:

1. Run the daily pipeline to generate artifacts
2. Check the date range matches available data
3. Use `--list-tools` to see tool capabilities

### Loop Warnings

If you see loop warnings, the LLM is calling tools repeatedly. This usually means:

1. Data is genuinely missing
2. Query is too broad/narrow
3. Max iterations reached (try increasing `--max-iterations`)

### Low Confidence

Confidence is "low" or "insufficient" when:

1. Only 1 source category (need diversity)
2. No measurable predictions extracted
3. All evidence is media-only

Add more specific queries or check different signal types.

## API Reference

```python
from briefai.ask import (
    AskEngine,
    AskLogEntry,
    ToolRegistry,
    Scratchpad,
    QualityGates,
)

# Quick function
from briefai.ask.engine import ask
result = ask("Question?", experiment_id="v2_2_forward_test")
```

## Citation Format (v1.1)

Every claim in "Key Takeaways" and "What to Watch" must include a citation:

```
[evidence: <artifact_path>#<anchor>]
```

### Examples

| Artifact Type | Citation Format |
|---------------|-----------------|
| Meta-signal | `[evidence: data/meta_signals/meta_signals_2026-02-11.json#meta_id=abc123]` |
| Daily brief | `[evidence: data/briefs/analyst_brief_2026-02-11.md#L120-L140]` |
| Forecast | `[evidence: data/public/experiments/v2_2/daily_snapshot_2026-02-11.json#predictions]` |
| Signal | `[evidence: data/news_signals/techmeme_2026-02-11.json#id=sig_001]` |

### Grep Usage

```bash
# Find all evidence for a specific meta-signal
grep -r "meta_id=abc123" data/

# Find brief citations for a date
grep "analyst_brief_2026-02-11" data/public/experiments/*/ask_logs/*.jsonl
```

## Intent Router (v1.1)

The intent router classifies queries to optimize tool selection:

| Intent | Triggers | Default Tools | Max Iterations |
|--------|----------|---------------|----------------|
| `bull_bear_case` | "bull and bear", "long/short thesis" | get_entity_profile, search_meta_signals | 6 |
| `what_changed` | "what changed", "vs yesterday" | summarize_daily_brief, search_meta_signals | 4 |
| `trend_explain` | "explain trend", "what does X mean" | search_meta_signals, search_signals | 4 |
| `entity_status` | "how is X doing", entity name detected | get_entity_profile, search_signals | 4 |
| `compare` | "compare", "vs", "versus" | get_entity_profile, search_signals | 5 |
| `forecast_check` | "forecast", "prediction" | get_forecast_snapshot, list_hypotheses | 4 |
| `general` | (fallback) | search_meta_signals, search_signals | 6 |

### Disabling Intent Router

```python
config = EngineConfig(use_intent_router=False)
engine = AskEngine(config=config)
```

## Limitations

1. **Offline only**: Cannot fetch real-time data
2. **Local artifacts**: Only sees what pipeline has produced
3. **LLM dependency**: Requires LLM for planning/answering
4. **No cross-experiment reads**: Isolated to one experiment

## Future Enhancements

- [ ] Web-based UI for interactive queries
- [ ] Caching of expensive tool results
- [ ] Streaming answers for long queries
- [ ] Custom tool registration API
- [x] Freshness banner (v1.1)
- [x] Evidence citations (v1.1)
- [x] Intent router (v1.1)
