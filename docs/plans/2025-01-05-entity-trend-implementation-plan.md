# Entity Trend Heatmap - Implementation Plan

**Date**: 2025-01-05
**Design**: [2025-01-05-entity-trend-heatmap-design.md](2025-01-05-entity-trend-heatmap-design.md)
**Estimated Time**: 4-6 hours total

---

## Phase 1: Core Data Layer (1.5 hours)

### Task 1.1: Extend schemas.py with new models
**File**: `utils/schemas.py`
**Estimated**: 30 minutes

**Actions**:
- [ ] Add `Literal` import from `typing`
- [ ] Create `EntityMention` class with 9 fields
- [ ] Create `TrendSignal` class with 16 fields
- [ ] Add docstrings for both classes
- [ ] Run `pyright` to verify no type errors

**Acceptance Criteria**:
- Both models instantiate correctly
- All fields have correct types (Literal for enums)
- Pyright shows 0 errors
- `created_at` uses `Field(default_factory=datetime.utcnow)`

**Code Reference**:
```python
class EntityMention(BaseModel):
    entity_id: str
    entity_name: str
    entity_type: Literal["company", "model", "topic", "person"]
    week_id: str
    mention_count: int
    avg_score: float
    max_score: float
    total_score: float
    article_ids: List[str]
    created_at: datetime = Field(default_factory=datetime.utcnow)

class TrendSignal(BaseModel):
    entity_id: str
    entity_name: str
    entity_type: Literal["company", "model", "topic", "person"]
    signal_type: Literal["velocity_spike", "new_entity", "score_surge", "combo"]
    confidence: float
    current_week: str
    baseline_weeks: int
    baseline_mentions: float
    baseline_score: Optional[float]
    weeks_observed: int
    current_mentions: int
    current_score: Optional[float]
    velocity_change: float
    score_delta: Optional[float]
    evidence_article_ids: List[str]
    evidence_titles: List[str]
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

---

### Task 1.2: Create normalize_entity_name function
**File**: `utils/entity_normalizer.py` (NEW)
**Estimated**: 20 minutes

**Actions**:
- [ ] Create new file `utils/entity_normalizer.py`
- [ ] Implement `normalize_entity_name(raw_name: str, entity_type: str) -> str`
- [ ] Add company_aliases dictionary (5 companies)
- [ ] Add model_aliases dictionary (3 models)
- [ ] Add basic normalization (lowercase, strip, remove punctuation)
- [ ] Write docstring with examples
- [ ] Add `__all__` export

**Acceptance Criteria**:
- `normalize_entity_name("Open AI", "company")` returns `"openai"`
- `normalize_entity_name("GPT-4", "model")` returns `"gpt4"`
- Handles edge cases: empty string, None check, unknown aliases
- Function is pure (no side effects)

**Code Reference**:
```python
"""Entity name normalization for deduplication"""

def normalize_entity_name(raw_name: str, entity_type: str) -> str:
    """
    Convert entity name to canonical form for deduplication

    Args:
        raw_name: Original name (e.g., "Open AI")
        entity_type: One of "company", "model", "topic", "person"

    Returns:
        Normalized entity_id (e.g., "openai")

    Examples:
        >>> normalize_entity_name("Open AI", "company")
        'openai'
        >>> normalize_entity_name("GPT-4", "model")
        'gpt4'
    """
    # Implementation as per design doc
    pass
```

---

### Task 1.3: Create trend_detection.json config
**File**: `config/trend_detection.json` (NEW)
**Estimated**: 10 minutes

**Actions**:
- [ ] Create new file `config/trend_detection.json`
- [ ] Add `baseline_weeks` parameter (default: 4)
- [ ] Add `thresholds` object with 4 thresholds
- [ ] Add `min_confidence` (default: 0.3)
- [ ] Add `min_baseline_weeks` (default: 2)
- [ ] Add `entity_limits` object
- [ ] Validate JSON syntax

**Acceptance Criteria**:
- Valid JSON (no syntax errors)
- All parameters have sensible defaults
- File loads correctly with `json.load()`

**Code Reference**:
```json
{
  "baseline_weeks": 4,
  "thresholds": {
    "new_entity_min_mentions": 3,
    "velocity_spike": 3.0,
    "score_surge": 1.5,
    "min_baseline_mentions": 2
  },
  "min_confidence": 0.3,
  "min_baseline_weeks": 2,
  "entity_limits": {
    "heatmap_max_entities": 50,
    "signal_max_evidence": 5
  }
}
```

---

### Task 1.4: Create TrendAggregator skeleton
**File**: `utils/trend_aggregator.py` (NEW)
**Estimated**: 30 minutes

**Actions**:
- [ ] Create new file `utils/trend_aggregator.py`
- [ ] Add imports (json, pathlib, typing, schemas, etc.)
- [ ] Create `TrendAggregator` class
- [ ] Implement `__init__` (load config, init context/extractor)
- [ ] Add method stubs: `aggregate_week()`, `detect_trend_signals()`
- [ ] Add helper method stubs: `_get_baseline_weeks()`, `_get_article_titles()`
- [ ] Add confidence scoring method stubs (4 methods)
- [ ] Write class docstring
- [ ] Add type hints for all methods
- [ ] Run `pyright` to verify

**Acceptance Criteria**:
- Class instantiates without errors
- Config loads from JSON file
- All method signatures match design doc
- Pyright shows 0 errors
- Methods raise `NotImplementedError` for now

**Code Reference**:
```python
"""Trend aggregation and detection logic"""

from typing import List, Dict, Optional
from collections import defaultdict
from pathlib import Path
import json

from utils.context_retriever import ContextRetriever
from utils.entity_extractor import EntityExtractor
from utils.schemas import EntityMention, TrendSignal
from utils.entity_normalizer import normalize_entity_name

class TrendAggregator:
    """Aggregates entity mentions and detects trend signals"""

    def __init__(
        self,
        context: ContextRetriever,
        config_path: str = "./config/trend_detection.json"
    ):
        """Initialize aggregator"""
        self.context = context
        self.entity_extractor = EntityExtractor()

        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)

    def aggregate_week(self, week_id: str) -> List[EntityMention]:
        """Aggregate entity mentions for a single week"""
        raise NotImplementedError("Task 2.1")

    def detect_trend_signals(
        self,
        current_week: str,
        baseline_weeks: int = 4
    ) -> List[TrendSignal]:
        """Detect trend signals by comparing current week against baseline"""
        raise NotImplementedError("Task 2.2")

    # Helper methods (stubs)
    def _get_baseline_weeks(self, current_week: str, num_weeks: int) -> List[str]:
        raise NotImplementedError("Task 2.3")

    def _get_article_titles(self, article_ids: List[str]) -> List[str]:
        raise NotImplementedError("Task 2.3")

    # Confidence scoring methods (stubs)
    def _compute_new_entity_confidence(self, mention: EntityMention) -> float:
        raise NotImplementedError("Task 2.4")

    def _compute_velocity_confidence(
        self, velocity: float, current_mention: EntityMention, baseline_weeks_observed: int
    ) -> float:
        raise NotImplementedError("Task 2.4")

    def _compute_score_surge_confidence(
        self, score_surge: float, current_mention: EntityMention, baseline_weeks_observed: int
    ) -> float:
        raise NotImplementedError("Task 2.4")

    def _compute_combo_confidence(
        self, velocity: float, score_surge: float, current_mention: EntityMention, baseline_weeks_observed: int
    ) -> float:
        raise NotImplementedError("Task 2.4")
```

---

## Phase 2: Detection Logic (2 hours)

### Task 2.1: Implement aggregate_week()
**File**: `utils/trend_aggregator.py`
**Estimated**: 45 minutes

**Actions**:
- [ ] Get articles for week using `context.get_articles_by_week()`
- [ ] Loop through articles and extract entities
- [ ] Group entities by normalized entity_id
- [ ] Accumulate counts, scores, article_ids
- [ ] Handle empty score lists safely (if/else)
- [ ] Compute avg_score, max_score, total_score
- [ ] Create EntityMention objects
- [ ] Return list of mentions
- [ ] Add logging statements
- [ ] Test with sample data

**Acceptance Criteria**:
- Returns empty list if no articles
- Correctly groups entities by normalized ID
- Handles articles with no scores gracefully
- avg_score/max_score/total_score computed correctly
- No crashes on edge cases (empty lists, missing fields)

**Test Command**:
```python
from utils.trend_aggregator import TrendAggregator
from utils.context_retriever import ContextRetriever

context = ContextRetriever('./data/reports')
agg = TrendAggregator(context)
mentions = agg.aggregate_week('2025-W01')
print(f"Found {len(mentions)} entities")
for m in mentions[:5]:
    print(f"{m.entity_name}: {m.mention_count} mentions, avg_score={m.avg_score:.1f}")
```

---

### Task 2.2: Implement detect_trend_signals()
**File**: `utils/trend_aggregator.py`
**Estimated**: 60 minutes

**Actions**:
- [ ] Get current week's mentions
- [ ] Get baseline weeks using `_get_baseline_weeks()`
- [ ] Aggregate baseline data per entity
- [ ] Loop through current entities
- [ ] **NEW ENTITY detection**: Check if entity has no baseline
- [ ] **VELOCITY SPIKE detection**: Compare current vs baseline mentions
- [ ] **SCORE SURGE detection**: Compare current vs baseline scores
- [ ] **COMBO detection**: Check if both velocity and score surge fire
- [ ] Guard against division by zero (MIN_BASELINE_MENTIONS check)
- [ ] Guard against insufficient baseline weeks (MIN_BASELINE_WEEKS check)
- [ ] Compute confidence scores for each signal
- [ ] Filter signals below MIN_CONFIDENCE
- [ ] Return list of TrendSignal objects
- [ ] Add extensive logging

**Acceptance Criteria**:
- Detects all 4 signal types correctly
- Guards prevent false positives from tiny baselines
- Confidence scores in 0-1 range
- Evidence article_ids limited to 5
- Combo signals have higher confidence than individual signals
- No crashes on edge cases

**Test Command**:
```python
signals = agg.detect_trend_signals('2025-W01', baseline_weeks=4)
print(f"Detected {len(signals)} trend signals")
for s in signals:
    print(f"{s.entity_name}: {s.signal_type} (confidence={s.confidence:.0%})")
```

---

### Task 2.3: Implement helper methods
**File**: `utils/trend_aggregator.py`
**Estimated**: 30 minutes

**Actions**:
- [ ] Implement `_get_baseline_weeks()`:
  - Parse week_id format (e.g., "2025-W01")
  - Compute previous N weeks
  - Handle year boundaries (W01 → previous year W52)
  - Return list of week IDs
- [ ] Implement `_get_article_titles()`:
  - Loop through article_ids
  - Fetch article from context
  - Extract title field
  - Return list of titles
- [ ] Add error handling for missing articles
- [ ] Add logging

**Acceptance Criteria**:
- `_get_baseline_weeks("2025-W02", 2)` returns `["2024-W52", "2025-W01"]`
- Handles year boundaries correctly
- `_get_article_titles()` returns list matching article_ids length
- Missing articles return "Untitled"

---

### Task 2.4: Implement confidence scoring methods
**File**: `utils/trend_aggregator.py`
**Estimated**: 30 minutes

**Actions**:
- [ ] Implement `_compute_new_entity_confidence()`:
  - Factor in mention_count (cap at 5)
  - Factor in avg_score (cap at 8)
  - Weighted combination (60% mentions, 40% score)
  - Clamp to min_confidence
- [ ] Implement `_compute_velocity_confidence()`:
  - Factor in velocity magnitude (cap at 5x)
  - Factor in baseline stability (weeks_observed)
  - Factor in current mentions (cap at 8)
  - Weighted combination (50% velocity, 30% stability, 20% mentions)
- [ ] Implement `_compute_score_surge_confidence()`:
  - Factor in surge magnitude
  - Factor in baseline stability
  - Weighted combination (60% surge, 40% stability)
- [ ] Implement `_compute_combo_confidence()`:
  - 4 factors: velocity, surge, stability, mentions
  - Equal weighting (25% each... wait, design says 30/30/20/20)
  - Apply 20% boost for combo signals
  - Clamp to 1.0 max

**Acceptance Criteria**:
- All methods return float in 0-1 range
- Confidence increases with stronger signals
- Combo signals always have higher confidence than individual signals
- Capping prevents outliers from dominating

---

## Phase 3: Visualization (1.5 hours)

### Task 3.1: Create TrendHeatmapUI class
**File**: `modules/trend_heatmap.py` (NEW)
**Estimated**: 45 minutes

**Actions**:
- [ ] Create new file `modules/trend_heatmap.py`
- [ ] Add imports (streamlit, pandas, plotly, typing, schemas)
- [ ] Create `TrendHeatmapUI` class
- [ ] Implement `render()` method:
  - Loop through weeks and aggregate
  - Build heatmap dataframe
  - Create Plotly heatmap figure
  - Render with `st.plotly_chart()`
  - Call `_render_trend_signals()`
- [ ] Implement `_build_heatmap_dataframe()`:
  - Convert mentions to pandas DataFrame
  - Filter by entity_type
  - Sort by total intensity
  - Limit to top 50 entities
- [ ] Implement `_render_trend_signals()`:
  - Detect signals for current week
  - Group by signal_type
  - Render expandable sections in sidebar
- [ ] Implement `_render_signal_card()`:
  - Show entity name with confidence badge
  - Show metrics (mentions, score) with deltas
  - Show evidence articles in expander

**Acceptance Criteria**:
- Heatmap renders correctly in Streamlit
- Color scale is YlOrRd (yellow → orange → red)
- Sidebar shows trend signals grouped by type
- Signal cards show metrics and evidence
- No crashes on empty data

---

### Task 3.2: Integrate with app.py
**File**: `app.py`
**Estimated**: 30 minutes

**Actions**:
- [ ] Add import for `TrendHeatmapUI`
- [ ] Add import for `TrendAggregator`
- [ ] Change `st.tabs()` to include third tab "🔥 Trend Radar"
- [ ] Create `render_trend_radar()` function:
  - Add filters in sidebar (weeks, entity_type)
  - Initialize ContextRetriever and TrendAggregator
  - Initialize TrendHeatmapUI
  - Call `heatmap_ui.render()`
  - Add week-over-week metrics (3 st.metric calls)
- [ ] Create `get_available_weeks()` helper:
  - Scan `data/reports/` for weekly_*.md files
  - Extract week IDs from filenames
  - Return sorted list
- [ ] Create helper functions for metrics:
  - `count_new_entities()`
  - `count_active_signals()`
  - `compute_avg_intensity()`

**Acceptance Criteria**:
- New tab appears in Streamlit UI
- Filters work correctly
- Heatmap loads without errors
- Metrics display correct values
- Integration doesn't break existing tabs

---

### Task 3.3: Polish and testing
**File**: Multiple
**Estimated**: 15 minutes

**Actions**:
- [ ] Add title and subtitle to Trend Radar tab
- [ ] Verify responsive layout (heatmap height scales)
- [ ] Test with different week ranges (4, 8, 12 weeks)
- [ ] Test entity type filters (all, company, model, topic, person)
- [ ] Verify color scale is visually clear
- [ ] Check confidence badges show correct colors
- [ ] Verify evidence articles are clickable (if implemented)
- [ ] Test edge cases: no data, single entity, all same score

**Acceptance Criteria**:
- UI is visually polished
- All interactions work smoothly
- No visual bugs or layout issues
- Performance is acceptable (<5s load time)

---

## Phase 4: Testing & Documentation (1 hour)

### Task 4.1: Create unit tests
**File**: `tests/test_trend_aggregator.py` (NEW)
**Estimated**: 30 minutes

**Actions**:
- [ ] Create new file `tests/test_trend_aggregator.py`
- [ ] Write test for `normalize_entity_name()` (5 cases)
- [ ] Write test for `aggregate_week()` with mock data
- [ ] Write test for edge case: empty articles list
- [ ] Write test for edge case: articles with no scores
- [ ] Write test for `detect_trend_signals()` with mock baseline
- [ ] Write test for new_entity signal detection
- [ ] Write test for velocity_spike signal detection
- [ ] Write test for combo signal detection
- [ ] Write test for confidence score clamping

**Acceptance Criteria**:
- All tests pass
- Code coverage >80% for trend_aggregator.py
- Tests use mocks/fixtures (don't depend on real data)
- Tests are fast (<5 seconds total)

**Run Command**:
```bash
pytest tests/test_trend_aggregator.py -v
```

---

### Task 4.2: Manual end-to-end test
**Estimated**: 15 minutes

**Actions**:
- [ ] Generate a weekly briefing with entity extraction
- [ ] Run CLI test for aggregate_week()
- [ ] Run CLI test for detect_trend_signals()
- [ ] Launch Streamlit UI
- [ ] Navigate to Trend Radar tab
- [ ] Select different week ranges
- [ ] Test entity type filters
- [ ] Verify heatmap renders correctly
- [ ] Verify signals appear in sidebar
- [ ] Check evidence articles
- [ ] Verify metrics are accurate

**Acceptance Criteria**:
- Full workflow runs without errors
- Heatmap shows meaningful data
- Signals are detected and displayed
- UI is responsive and polished

---

### Task 4.3: Update documentation
**File**: `README.md`
**Estimated**: 15 minutes

**Actions**:
- [ ] Update "Development Status" section:
  - Move "Trend detection across weeks" to ✅
  - Add "Entity Trend Heatmap" as completed
- [ ] Update "Roadmap" section:
  - Add Phase 2.5 for Entity Trend Heatmap
- [ ] Update project structure:
  - Add `trend_aggregator.py`
  - Add `entity_normalizer.py`
  - Add `trend_heatmap.py`
  - Add `trend_detection.json`
- [ ] Add CLI example for testing trend detection
- [ ] Update "Last Updated" date and version

**Acceptance Criteria**:
- README accurately reflects new features
- Code examples are correct
- Project structure is up-to-date
- Version number incremented

---

## Summary Checklist

### Phase 1: Core Data Layer ✅
- [ ] Task 1.1: Extend schemas.py (30 min)
- [ ] Task 1.2: Create normalize_entity_name (20 min)
- [ ] Task 1.3: Create trend_detection.json (10 min)
- [ ] Task 1.4: Create TrendAggregator skeleton (30 min)

### Phase 2: Detection Logic ✅
- [ ] Task 2.1: Implement aggregate_week() (45 min)
- [ ] Task 2.2: Implement detect_trend_signals() (60 min)
- [ ] Task 2.3: Implement helper methods (30 min)
- [ ] Task 2.4: Implement confidence scoring (30 min)

### Phase 3: Visualization ✅
- [ ] Task 3.1: Create TrendHeatmapUI class (45 min)
- [ ] Task 3.2: Integrate with app.py (30 min)
- [ ] Task 3.3: Polish and testing (15 min)

### Phase 4: Testing & Documentation ✅
- [ ] Task 4.1: Create unit tests (30 min)
- [ ] Task 4.2: Manual end-to-end test (15 min)
- [ ] Task 4.3: Update documentation (15 min)

**Total Estimated Time**: 5 hours 45 minutes

---

## Success Criteria

- ✅ All Pyright type checks pass (0 errors)
- ✅ All unit tests pass
- ✅ Heatmap renders correctly in Streamlit
- ✅ Trend signals detected and displayed
- ✅ No performance issues (<5s load time)
- ✅ Documentation updated
- ✅ Manual testing confirms everything works

---

**Ready to Begin**: Start with Phase 1, Task 1.1
**Next Command**: `code utils/schemas.py`