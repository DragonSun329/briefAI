# Artifact-Based Pipeline Architecture

## Problem Statement

**Current Issue:** If the pipeline fails at phase 8, ALL work from phases 1-7 is lost. The pipeline keeps results in memory and only saves at the very end.

**User Request:** "why's there no cache or doc produced, so that if the pipeline failed midway there'll be something to work with. I would rather these phases be treated as agents, one process and produce a doc for the next phase, wouldn't that be better?"

## Proposed Solution: Agent-Based Artifact Pipeline

Each phase acts as an **autonomous agent** that:
1. Reads input artifacts from previous phase
2. Processes data independently
3. Writes output artifacts to disk
4. Next phase reads those artifacts

### Benefits

✅ **Resume from any phase** - If phase 8 fails, restart from phase 8 using phase 7's artifacts
✅ **Inspect intermediate results** - Check what went wrong by reading artifacts
✅ **Debug individual phases** - Test single phase with real data
✅ **Parallel development** - Multiple developers can work on different phases
✅ **Cost savings** - Don't re-run expensive LLM phases
✅ **Transparency** - See exactly what each phase produced

## Architecture Design

### Artifact Storage Structure

```
data/artifacts/
├── run_20251030_175101/
│   ├── phase1_initialization.json
│   ├── phase2_scraping.json         # 106 articles
│   ├── phase3_tier1_filter.json     # 32 articles
│   ├── phase4_tier2_batch.json      # 32 articles
│   ├── phase5_tier3_5d.json         # 10 articles
│   ├── phase6_ranking.json          # 10 ranked
│   ├── phase7_paraphrasing.json     # 10 with 500-600 char analysis
│   ├── phase8_enrichment.json       # 10 with entity backgrounds
│   ├── phase9_validation.json       # 10 validated
│   └── phase10_final_report.md      # Final output
│
├── run_20251030_182345/            # Another run
│   └── ...
│
└── latest -> run_20251030_175101/  # Symlink to latest run
```

### Artifact Format

Each artifact is a JSON file with metadata + data:

```json
{
  "metadata": {
    "run_id": "20251030_175101",
    "phase_name": "tier1_filter",
    "phase_number": 3,
    "timestamp": "2025-10-30T17:30:45Z",
    "duration_seconds": 0.234,
    "input_count": 106,
    "output_count": 32,
    "llm_calls": 0,
    "cost_usd": 0.00,
    "status": "completed"
  },
  "data": {
    "articles": [
      {
        "title": "...",
        "url": "...",
        "content": "...",
        "tier1_score": 8.5
      }
    ]
  }
}
```

## Phase-by-Phase Implementation

### Phase 1: Initialization
**Input:** Config files
**Output:** `phase1_initialization.json`
```json
{
  "categories": ["breakthrough_products", "ai_companies", ...],
  "company_context": "AI Industry Intelligence & Trend Tracking",
  "config": {...}
}
```

### Phase 2: Scraping
**Input:** `phase1_initialization.json`
**Output:** `phase2_scraping.json`
```json
{
  "data": {
    "articles": [...],  // 106 articles
    "sources_scraped": 86,
    "sources_failed": 0
  }
}
```

### Phase 3-10: Continue pattern...

Each phase:
1. Reads previous phase's artifact
2. Processes data
3. Writes output artifact
4. Logs metrics

## Resume Capability

```bash
# Resume from phase 8 (skips phases 1-7)
python3 run_orchestrated_pipeline.py --resume-from-phase 8 --run-id 20251030_175101

# Re-run specific phase only
python3 run_orchestrated_pipeline.py --run-phase 7 --run-id 20251030_175101

# Resume latest failed run
python3 run_orchestrated_pipeline.py --resume-latest
```

## Implementation Steps

### Step 1: Create ArtifactManager
```python
class ArtifactManager:
    def __init__(self, run_id: str):
        self.run_id = run_id
        self.artifact_dir = Path(f"data/artifacts/{run_id}")

    def save_artifact(self, phase_name: str, data: dict, metadata: dict):
        """Save phase output as artifact"""

    def load_artifact(self, phase_name: str) -> dict:
        """Load phase input from previous artifact"""

    def list_artifacts(self) -> List[str]:
        """List all artifacts for this run"""

    def get_latest_artifact(self) -> str:
        """Get name of latest artifact"""
```

### Step 2: Modify ACE Orchestrator

```python
class ACEOrchestrator:
    def __init__(self, run_id: str, resume_from: Optional[str] = None):
        self.artifact_manager = ArtifactManager(run_id)
        self.resume_from = resume_from

    def run_pipeline(self):
        phases = [
            'initialization', 'scraping', 'tier1_filter', ...
        ]

        # Skip to resume_from phase
        start_idx = 0
        if self.resume_from:
            start_idx = phases.index(self.resume_from)
            logger.info(f"Resuming from phase {self.resume_from}")

        for phase_name in phases[start_idx:]:
            # Load input from previous phase artifact
            if start_idx > 0:
                prev_phase = phases[start_idx - 1]
                input_data = self.artifact_manager.load_artifact(prev_phase)

            # Execute phase
            output_data = self.execute_phase(phase_name, input_data)

            # Save artifact immediately
            self.artifact_manager.save_artifact(
                phase_name=phase_name,
                data=output_data,
                metadata={...}
            )
```

### Step 3: Update Each Phase Function

```python
def phase_2_scraping(self, config: dict) -> dict:
    """
    Phase 2: Scraping

    Input: phase1_initialization artifact
    Output: phase2_scraping artifact with 106 articles
    """
    # Execute scraping
    articles = web_scraper.scrape_all(...)

    # Return data for artifact
    return {
        "articles": articles,
        "sources_scraped": len(sources),
        "sources_failed": failed_count
    }
```

## Inspection Tools

### View Artifacts
```bash
# List all runs
python3 scripts/list_artifacts.py

# View specific artifact
python3 scripts/view_artifact.py --run-id 20251030_175101 --phase scraping

# Compare two runs
python3 scripts/compare_runs.py run1 run2
```

### Artifact Viewer (Streamlit)
```python
# Launch artifact browser
streamlit run scripts/artifact_viewer.py
```

Shows:
- All runs with status
- Phase-by-phase breakdown
- Article counts at each phase
- Cost and duration per phase
- Ability to resume from any phase

## Monitoring Dashboard

Real-time pipeline visualization:
```
Phase 1: Initialization    [✓] 0.1s   0 articles → 0 articles   $0.00
Phase 2: Scraping          [✓] 2m 27s 0 articles → 106 articles $0.00
Phase 3: Tier1 Filter      [✓] 0.3s   106 → 32 articles         $0.00
Phase 4: Tier2 Batch Eval  [✓] 1m 4s  32 → 32 articles          $0.12
Phase 5: Tier3 5D Eval     [✓] 8m 56s 32 → 10 articles          $0.78
Phase 6: Ranking           [✓] 0.1s   10 → 10 articles          $0.00
Phase 7: Paraphrasing      [⏳] Running... (2m 15s so far)
Phase 8: Enrichment        [⏸️ ] Waiting...
Phase 9: Validation        [⏸️ ] Waiting...
Phase 10: Report Gen       [⏸️ ] Waiting...
```

## Error Recovery

If phase fails:
1. **Artifact is NOT saved** (partial data)
2. **Previous artifact remains intact**
3. **Pipeline can resume** from last successful phase

Example:
```bash
# Phase 8 failed
ERROR: Phase 'enrichment' failed: API timeout

# Resume from phase 8 with same artifacts
python3 run_orchestrated_pipeline.py --resume-from-phase 8 --run-id 20251030_175101

# Phase 8 reads phase 7 artifact and tries again
```

## Backward Compatibility

**Option 1: Hybrid Mode** (Default)
- Still keeps results in memory
- Also saves artifacts
- Can choose to resume or not

**Option 2: Artifact-Only Mode**
- Forces artifact-based operation
- Uses `--artifact-mode` flag

## Migration Path

### Week 1: Add ArtifactManager
- Create artifact storage system
- Add save/load methods
- No pipeline changes yet

### Week 2: Integrate with Orchestrator
- Modify ACE orchestrator
- Add resume capability
- Test with existing pipeline

### Week 3: Add Inspection Tools
- Build artifact viewer
- Create comparison tools
- Add monitoring dashboard

### Week 4: Production Rollout
- Enable artifact mode by default
- Update documentation
- Train users on resume feature

## Cost Analysis

**Storage Requirements:**
- Each run: ~5-10 MB (compressed JSON)
- 10 runs: ~50-100 MB
- 100 runs: ~500 MB - 1 GB

**Retention Policy:**
- Keep last 10 runs indefinitely
- Archive runs 11-100 (compress)
- Delete runs 101+ after 90 days

## Future Enhancements

1. **Phase Parallelization** - Run independent phases in parallel
2. **Distributed Execution** - Run phases on different machines
3. **Artifact Versioning** - Track changes to phase logic over time
4. **A/B Testing** - Compare different phase implementations
5. **Rollback Support** - Revert to previous run's artifacts

---

**Status:** Design complete, ready for implementation
**Priority:** HIGH - Solves critical production issue
**Estimated Implementation:** 2-3 days
