# PR: Ask Mode v1.0 - Dexter-style Interactive Research

## Summary

Implements an agentic research mode for briefAI that allows interactive questions against local pipeline artifacts. The system runs a plan→execute→reflect→answer loop while maintaining experiment isolation and deterministic reproducibility.

## Changes

### New Module: `briefai/ask/`

| File | Purpose |
|------|---------|
| `__init__.py` | Module exports |
| `models.py` | Data models: `AskLogEntry`, `ToolCallRecord`, `MeasurableCheck`, `EvidenceLink` |
| `tools.py` | Tool registry with 7 deterministic tools wrapping briefAI artifacts |
| `scratchpad.py` | Append-only scratchpad with loop detection |
| `quality_gates.py` | Deterministic quality validation rules |
| `engine.py` | Main agentic loop and write protection |
| `cli.py` | CLI interface |

### Entry Point

```bash
python -m briefai ask "QUESTION" --experiment v2_2_forward_test
```

### New Files

- `briefai/__init__.py` - Package init
- `briefai/__main__.py` - CLI entry point
- `briefai/ask/*` - Ask mode module (7 files)
- `tests/test_ask_mode.py` - Unit tests
- `docs/ASK_MODE.md` - Usage documentation

## Tool Registry

| Tool | Category | Description |
|------|----------|-------------|
| `search_meta_signals` | META | Search synthesized trends |
| `search_signals` | MIXED | Search raw signals from pipelines |
| `get_entity_profile` | COMPANY | Entity scores and velocity |
| `summarize_daily_brief` | MEDIA | Daily brief summaries |
| `retrieve_evidence` | MIXED | Evidence for metric/entity |
| `list_hypotheses` | META | Active hypotheses |
| `get_forecast_snapshot` | META | Frozen forecasts |

All tools are **deterministic** (no network) and return `DataMissing` when data doesn't exist.

## Quality Gates (Deterministic)

| Rule | Threshold | Effect |
|------|-----------|--------|
| Source Diversity | ≥2 categories | "insufficient" confidence if failed |
| Measurable Checks | ≥2 predictions | Quality note if failed |
| Media-Only | Non-media required | Caps confidence, sets review_required |

## Write Protection

**Cannot write to:**
- `forecast_history.jsonl`
- `daily_snapshot_*.json`
- `run_metadata_*.json`

**Writes only to:**
- `data/public/experiments/{experiment_id}/ask_logs/ask_history.jsonl`

## Ask Log Schema

```json
{
  "question": "string",
  "experiment_id": "string",
  "plan": "string",
  "tool_calls": [{"tool_name", "arguments", "result_summary", "result_type"}],
  "tool_results_summaries": ["string"],
  "evidence_links": [{"source_type", "source_id", "category", "snippet"}],
  "measurable_checks": [{"metric", "entity", "direction", "window_days"}],
  "final_answer": "string",
  "confidence_level": "insufficient|low|medium|high",
  "review_required": "boolean",
  "quality_notes": ["string"],
  "commit_hash": "string",
  "engine_tag": "string|null",
  "timestamp_utc": "ISO8601",
  "duration_ms": "int",
  "loop_iterations": "int",
  "loop_warnings": ["string"]
}
```

## Test Coverage

| Test | File | Description |
|------|------|-------------|
| Log location | `test_ask_mode.py::TestAskLogLocation` | Logs under experiment folder |
| Loop detection | `test_ask_mode.py::TestLoopDetection` | Duplicate/similar query warnings |
| Determinism | `test_ask_mode.py::TestDeterministicOutput` | Same inputs → same outputs |
| Write protection | `test_ask_mode.py::TestWriteProtection` | Cannot write to forecast ledger |
| Quality gates | `test_ask_mode.py::TestQualityGates` | Diversity and check requirements |
| Tool registry | `test_ask_mode.py::TestToolRegistry` | All tools registered |
| Serialization | `test_ask_mode.py::TestModelSerialization` | JSONL roundtrip |
| Integration | `test_ask_mode.py::TestIntegration` | Full ask flow |

## Usage Examples

```bash
# Basic
python -m briefai ask "What signals suggest AI chip demand growth?"

# With experiment
python -m briefai ask "Is enterprise AI adoption accelerating?" -e v2_2_forward_test

# Verbose
python -m briefai ask "Question" -v

# JSON output
python -m briefai ask "Question" --json

# List tools
python -m briefai ask --list-tools
```

## Design Decisions

### Why Offline Only?

- Reproducibility: Same artifacts always give same results
- Audit trail: Every data source is local and versioned
- Speed: No network latency
- Security: No data exfiltration

### Why Separate Ask Log?

- Preserves forecast ledger integrity
- Allows experimental queries without contamination
- Enables ask-specific analytics

### Why Scratchpad?

- Prevents infinite loops
- Tracks all reasoning steps
- Enables debugging and optimization

### Why Quality Gates?

- Enforces evidence standards without LLM
- Prevents overconfident answers
- Reproducible quality assessment

## Breaking Changes

None. This is a new feature.

## Migration

None required. Existing pipelines and experiments unchanged.

## Dependencies

Uses existing briefAI utilities:
- `utils/entity_store.py`
- `utils/meta_signal_engine.py`
- `utils/llm_client.py`

No new external dependencies.

## Performance

- Typical query: 2-5 seconds (depends on LLM)
- Tool calls: <100ms each (local file reads)
- Max iterations: 10 (configurable)

## Future Work

- [ ] Web UI for interactive queries
- [ ] Tool result caching
- [ ] Custom tool registration
- [ ] Streaming answers
- [ ] Cross-experiment queries (read-only)

## Reviewers

- [ ] Code review
- [ ] Documentation review
- [ ] Test execution (`pytest tests/test_ask_mode.py -v`)

---

**Author:** Mia (AI Assistant)  
**Date:** 2026-02-11  
**Commit:** TBD
