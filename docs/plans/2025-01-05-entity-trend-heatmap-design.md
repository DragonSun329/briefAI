# Entity Trend Heatmap: Discovery-Mode AI Signal Detection

**Date**: 2025-01-05
**Status**: Design Complete
**Purpose**: Automatically surface "what's heating up" in AI by tracking entity trends across weeks

---

## Overview

A discovery-mode system that analyzes entity mentions (companies, models, topics, people) across weekly briefings to detect emerging trends. Uses multi-signal detection (velocity spikes, new appearances, score surges) with configurable thresholds and confidence scoring.

**Core Value Proposition**:
- **No manual checking**: System automatically surfaces breakout entities
- **Evidence-based**: Every signal backed by specific articles
- **Multi-week context**: Compares current activity against 4-week baseline
- **Visual heatmap**: At-a-glance view of intensity patterns

---

## Design Principles

1. **Baseline Transparency**: Always show what we're comparing against (4-week rolling average)
2. **Guard Against Edge Cases**: Division by zero, empty lists, insufficient data
3. **Confidence Scoring**: Every signal has 0-1 confidence based on multiple factors
4. **Combination Signals**: Detect when multiple signals fire simultaneously (high confidence)
5. **Entity Normalization**: Canonical forms for deduplication (e.g., "Open AI" → "OpenAI")

---

## Data Model

### EntityMention (Weekly Facts)

Tracks entity activity for a single week. One record per entity per week.

```python
from pydantic import BaseModel, Field
from typing import List, Literal
from datetime import datetime

class EntityMention(BaseModel):
    entity_id: str  # Normalized form (e.g., "openai")
    entity_name: str  # Display form (e.g., "OpenAI")
    entity_type: Literal["company", "model", "topic", "person"]
    week_id: str  # Format: "2025-W01"
    mention_count: int  # Number of articles mentioning this entity
    avg_score: float  # Average 5D score across articles
    max_score: float  # Highest score among articles
    total_score: float  # Sum of all scores (intensity metric)
    article_ids: List[str]  # References to articles
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

**Key Fields**:
- `entity_id`: Normalized for deduplication (see normalization function below)
- `total_score`: Intensity metric (captures both frequency and importance)
- `article_ids`: Enables drill-down to evidence

### TrendSignal (Discoveries)

Represents a detected trend or breakout moment.

```python
class TrendSignal(BaseModel):
    entity_id: str
    entity_name: str
    entity_type: Literal["company", "model", "topic", "person"]
    signal_type: Literal["velocity_spike", "new_entity", "score_surge", "combo"]
    confidence: float  # 0-1, clamped to min_confidence threshold

    # Time context
    current_week: str
    baseline_weeks: int  # Number of weeks in baseline (e.g., 4)

    # Baseline metrics
    baseline_mentions: float  # Average mentions per week in baseline
    baseline_score: Optional[float]  # Average score in baseline (None if no baseline)
    weeks_observed: int  # How many weeks entity appeared in baseline

    # Current metrics
    current_mentions: int
    current_score: Optional[float]

    # Deltas
    velocity_change: float  # Percentage change: (current - baseline) / baseline
    score_delta: Optional[float]  # Absolute change: current_score - baseline_score

    # Evidence
    evidence_article_ids: List[str]
    evidence_titles: List[str]  # For display (separate from IDs)

    created_at: datetime = Field(default_factory=datetime.utcnow)
```

**Signal Types**:
- `velocity_spike`: Mention frequency increased >3x baseline
- `new_entity`: Entity appeared for first time with sufficient mentions
- `score_surge`: Impact score increased >1.5x baseline
- `combo`: Multiple signals fired simultaneously (highest confidence)

---

## Entity Normalization

Centralize normalization to ensure consistent `entity_id` across weeks.

```python
def normalize_entity_name(raw_name: str, entity_type: str) -> str:
    """
    Convert entity name to canonical form for deduplication

    Args:
        raw_name: Original name from extraction (e.g., "Open AI")
        entity_type: One of "company", "model", "topic", "person"

    Returns:
        Normalized entity_id (e.g., "openai")
    """
    # Basic normalization
    normalized = raw_name.lower().strip()

    # Remove common punctuation
    normalized = normalized.replace('-', '').replace('.', '').replace(' ', '')

    # Company-specific aliases
    company_aliases = {
        'openai': ['openai', 'open-ai', 'open.ai', 'open ai'],
        'anthropic': ['anthropic', 'anthropic ai'],
        'google': ['google', 'google llc', 'alphabet'],
        'microsoft': ['microsoft', 'msft', 'ms'],
        'meta': ['meta', 'facebook', 'meta platforms'],
    }

    # Model-specific aliases
    model_aliases = {
        'gpt4': ['gpt-4', 'gpt4', 'gpt 4'],
        'claude': ['claude', 'claude ai'],
        'llama': ['llama', 'llama2', 'llama 2'],
    }

    # Apply aliases based on entity type
    if entity_type == "company":
        for canonical, aliases in company_aliases.items():
            if normalized in aliases:
                return canonical
    elif entity_type == "model":
        for canonical, aliases in model_aliases.items():
            if normalized in aliases:
                return canonical

    return normalized
```

**Usage in Aggregation**:
```python
entity_id = normalize_entity_name(entity_data['name'], entity_data['type'])
```

---

## Aggregation Engine

### TrendAggregator Class

Central class for computing EntityMentions and detecting TrendSignals.

```python
from typing import List, Dict, Optional
from collections import defaultdict
from datetime import datetime
import json
from pathlib import Path

from utils.context_retriever import ContextRetriever
from utils.entity_extractor import EntityExtractor
from utils.schemas import EntityMention, TrendSignal

class TrendAggregator:
    """Aggregates entity mentions and detects trend signals"""

    def __init__(
        self,
        context: ContextRetriever,
        config_path: str = "./config/trend_detection.json"
    ):
        """
        Initialize aggregator

        Args:
            context: ContextRetriever for accessing weekly articles
            config_path: Path to trend detection configuration
        """
        self.context = context
        self.entity_extractor = EntityExtractor()

        # Load configuration
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)

    def aggregate_week(self, week_id: str) -> List[EntityMention]:
        """
        Aggregate entity mentions for a single week

        Args:
            week_id: Week identifier (e.g., "2025-W01")

        Returns:
            List of EntityMention objects for the week
        """
        # Get all articles for the week
        articles = self.context.get_articles_by_week(week_id)

        if not articles:
            return []

        # Group by entity
        entity_data: Dict[str, Dict] = defaultdict(lambda: {
            'count': 0,
            'scores': [],
            'article_ids': [],
            'display_name': None,
            'entity_type': None
        })

        for article in articles:
            # Extract entities from article
            entities = self.entity_extractor.extract_entities(article['content'])
            article_score = article.get('weighted_score', 0.0)

            # Process each entity type
            for entity_type in ['companies', 'models', 'topics', 'people']:
                entity_type_singular = entity_type.rstrip('s')  # "companies" -> "company"

                for entity_name in entities.get(entity_type, []):
                    # Normalize entity name for grouping
                    entity_id = normalize_entity_name(entity_name, entity_type_singular)

                    # Accumulate data
                    entity_data[entity_id]['count'] += 1
                    entity_data[entity_id]['scores'].append(article_score)
                    entity_data[entity_id]['article_ids'].append(article['id'])

                    # Store display name and type (use first occurrence)
                    if entity_data[entity_id]['display_name'] is None:
                        entity_data[entity_id]['display_name'] = entity_name
                        entity_data[entity_id]['entity_type'] = entity_type_singular

        # Convert to EntityMention objects
        mentions = []
        for entity_id, data in entity_data.items():
            scores = data['scores']

            # Handle empty score lists safely
            if scores:
                avg_score = sum(scores) / len(scores)
                max_score = max(scores)
                total_score = sum(scores)
            else:
                avg_score = 0.0
                max_score = 0.0
                total_score = 0.0

            mention = EntityMention(
                entity_id=entity_id,
                entity_name=data['display_name'],
                entity_type=data['entity_type'],
                week_id=week_id,
                mention_count=data['count'],
                avg_score=avg_score,
                max_score=max_score,
                total_score=total_score,
                article_ids=data['article_ids']
            )
            mentions.append(mention)

        return mentions

    def detect_trend_signals(
        self,
        current_week: str,
        baseline_weeks: int = 4
    ) -> List[TrendSignal]:
        """
        Detect trend signals by comparing current week against baseline

        Args:
            current_week: Week to analyze (e.g., "2025-W01")
            baseline_weeks: Number of historical weeks for baseline (default: 4)

        Returns:
            List of detected TrendSignal objects above confidence threshold
        """
        MIN_BASELINE_MENTIONS = self.config.get('thresholds', {}).get('min_baseline_mentions', 2)
        MIN_BASELINE_WEEKS = self.config.get('min_baseline_weeks', 2)
        MIN_CONFIDENCE = self.config.get('min_confidence', 0.3)

        # Get current week's mentions
        current_mentions = self.aggregate_week(current_week)
        current_by_entity = {m.entity_id: m for m in current_mentions}

        # Get baseline weeks
        baseline_week_ids = self._get_baseline_weeks(current_week, baseline_weeks)

        # Aggregate baseline data per entity
        baseline_data: Dict[str, Dict] = defaultdict(lambda: {
            'total_mentions': 0,
            'total_score': 0.0,
            'weeks_observed': 0
        })

        for week_id in baseline_week_ids:
            week_mentions = self.aggregate_week(week_id)
            for mention in week_mentions:
                baseline_data[mention.entity_id]['total_mentions'] += mention.mention_count
                baseline_data[mention.entity_id]['total_score'] += mention.total_score
                baseline_data[mention.entity_id]['weeks_observed'] += 1

        # Detect signals
        signals = []

        for entity_id, current_mention in current_by_entity.items():
            baseline = baseline_data.get(entity_id)

            # NEW ENTITY signal
            if baseline is None or baseline['weeks_observed'] == 0:
                new_entity_threshold = self.config['thresholds']['new_entity_min_mentions']
                if current_mention.mention_count >= new_entity_threshold:
                    confidence = self._compute_new_entity_confidence(current_mention)
                    if confidence >= MIN_CONFIDENCE:
                        signal = TrendSignal(
                            entity_id=entity_id,
                            entity_name=current_mention.entity_name,
                            entity_type=current_mention.entity_type,
                            signal_type="new_entity",
                            confidence=confidence,
                            current_week=current_week,
                            baseline_weeks=baseline_weeks,
                            baseline_mentions=0.0,
                            baseline_score=None,
                            weeks_observed=0,
                            current_mentions=current_mention.mention_count,
                            current_score=current_mention.avg_score,
                            velocity_change=0.0,
                            score_delta=None,
                            evidence_article_ids=current_mention.article_ids[:5],
                            evidence_titles=self._get_article_titles(current_mention.article_ids[:5])
                        )
                        signals.append(signal)
                continue

            # Compute baseline averages
            baseline_avg_mentions = baseline['total_mentions'] / baseline['weeks_observed']
            baseline_avg_score = baseline['total_score'] / baseline['total_mentions'] if baseline['total_mentions'] > 0 else 0.0

            # Guard against tiny baselines (reduce false positives)
            if baseline_avg_mentions < MIN_BASELINE_MENTIONS:
                continue

            # Guard against insufficient baseline weeks
            if baseline['weeks_observed'] < MIN_BASELINE_WEEKS:
                continue

            # VELOCITY SPIKE signal
            velocity = (current_mention.mention_count - baseline_avg_mentions) / baseline_avg_mentions
            velocity_threshold = self.config['thresholds']['velocity_spike']

            # SCORE SURGE signal
            score_surge = None
            if baseline_avg_score > 0:  # Only compute if baseline has scores
                score_surge = current_mention.avg_score / baseline_avg_score

            score_surge_threshold = self.config['thresholds']['score_surge']

            # Detect signals
            is_velocity_spike = velocity >= velocity_threshold
            is_score_surge = score_surge is not None and score_surge >= score_surge_threshold

            # COMBO signal (multiple signals fire)
            if is_velocity_spike and is_score_surge:
                confidence = self._compute_combo_confidence(
                    velocity=velocity,
                    score_surge=score_surge,
                    current_mention=current_mention,
                    baseline_weeks_observed=baseline['weeks_observed']
                )
                if confidence >= MIN_CONFIDENCE:
                    signal = TrendSignal(
                        entity_id=entity_id,
                        entity_name=current_mention.entity_name,
                        entity_type=current_mention.entity_type,
                        signal_type="combo",
                        confidence=confidence,
                        current_week=current_week,
                        baseline_weeks=baseline_weeks,
                        baseline_mentions=baseline_avg_mentions,
                        baseline_score=baseline_avg_score,
                        weeks_observed=baseline['weeks_observed'],
                        current_mentions=current_mention.mention_count,
                        current_score=current_mention.avg_score,
                        velocity_change=velocity,
                        score_delta=current_mention.avg_score - baseline_avg_score,
                        evidence_article_ids=current_mention.article_ids[:5],
                        evidence_titles=self._get_article_titles(current_mention.article_ids[:5])
                    )
                    signals.append(signal)

            # Individual VELOCITY SPIKE
            elif is_velocity_spike:
                confidence = self._compute_velocity_confidence(
                    velocity=velocity,
                    current_mention=current_mention,
                    baseline_weeks_observed=baseline['weeks_observed']
                )
                if confidence >= MIN_CONFIDENCE:
                    signal = TrendSignal(
                        entity_id=entity_id,
                        entity_name=current_mention.entity_name,
                        entity_type=current_mention.entity_type,
                        signal_type="velocity_spike",
                        confidence=confidence,
                        current_week=current_week,
                        baseline_weeks=baseline_weeks,
                        baseline_mentions=baseline_avg_mentions,
                        baseline_score=baseline_avg_score,
                        weeks_observed=baseline['weeks_observed'],
                        current_mentions=current_mention.mention_count,
                        current_score=current_mention.avg_score,
                        velocity_change=velocity,
                        score_delta=current_mention.avg_score - baseline_avg_score if baseline_avg_score > 0 else None,
                        evidence_article_ids=current_mention.article_ids[:5],
                        evidence_titles=self._get_article_titles(current_mention.article_ids[:5])
                    )
                    signals.append(signal)

            # Individual SCORE SURGE
            elif is_score_surge:
                confidence = self._compute_score_surge_confidence(
                    score_surge=score_surge,
                    current_mention=current_mention,
                    baseline_weeks_observed=baseline['weeks_observed']
                )
                if confidence >= MIN_CONFIDENCE:
                    signal = TrendSignal(
                        entity_id=entity_id,
                        entity_name=current_mention.entity_name,
                        entity_type=current_mention.entity_type,
                        signal_type="score_surge",
                        confidence=confidence,
                        current_week=current_week,
                        baseline_weeks=baseline_weeks,
                        baseline_mentions=baseline_avg_mentions,
                        baseline_score=baseline_avg_score,
                        weeks_observed=baseline['weeks_observed'],
                        current_mentions=current_mention.mention_count,
                        current_score=current_mention.avg_score,
                        velocity_change=velocity,
                        score_delta=current_mention.avg_score - baseline_avg_score,
                        evidence_article_ids=current_mention.article_ids[:5],
                        evidence_titles=self._get_article_titles(current_mention.article_ids[:5])
                    )
                    signals.append(signal)

        return signals

    def _get_baseline_weeks(self, current_week: str, num_weeks: int) -> List[str]:
        """Get list of baseline week IDs before current_week"""
        # Implementation: Parse week ID, compute previous weeks
        # Format: "2025-W01" -> ["2024-W51", "2024-W52", "2025-W01", ...]
        # Placeholder for now
        return []

    def _get_article_titles(self, article_ids: List[str]) -> List[str]:
        """Fetch article titles for evidence display"""
        titles = []
        for article_id in article_ids:
            article = self.context.get_article_by_id(article_id)
            if article:
                titles.append(article.get('title', 'Untitled'))
        return titles

    # Confidence scoring functions

    def _compute_new_entity_confidence(self, mention: EntityMention) -> float:
        """Compute confidence for new_entity signal"""
        # Factors: mention count, avg score, article diversity
        mention_factor = min(mention.mention_count / 5.0, 1.0)  # Cap at 5 mentions
        score_factor = min(mention.avg_score / 8.0, 1.0)  # Cap at score 8

        confidence = (mention_factor * 0.6 + score_factor * 0.4)
        return max(confidence, self.config.get('min_confidence', 0.3))

    def _compute_velocity_confidence(
        self,
        velocity: float,
        current_mention: EntityMention,
        baseline_weeks_observed: int
    ) -> float:
        """Compute confidence for velocity_spike signal"""
        # Factors: velocity magnitude, baseline stability, current mentions
        velocity_factor = min(velocity / 5.0, 1.0)  # Cap at 5x
        stability_factor = min(baseline_weeks_observed / 4.0, 1.0)  # More weeks = more stable
        mention_factor = min(current_mention.mention_count / 8.0, 1.0)

        confidence = (velocity_factor * 0.5 + stability_factor * 0.3 + mention_factor * 0.2)
        return max(confidence, self.config.get('min_confidence', 0.3))

    def _compute_score_surge_confidence(
        self,
        score_surge: float,
        current_mention: EntityMention,
        baseline_weeks_observed: int
    ) -> float:
        """Compute confidence for score_surge signal"""
        surge_factor = min((score_surge - 1.0) / 1.0, 1.0)  # Normalize above 1.0
        stability_factor = min(baseline_weeks_observed / 4.0, 1.0)

        confidence = (surge_factor * 0.6 + stability_factor * 0.4)
        return max(confidence, self.config.get('min_confidence', 0.3))

    def _compute_combo_confidence(
        self,
        velocity: float,
        score_surge: float,
        current_mention: EntityMention,
        baseline_weeks_observed: int
    ) -> float:
        """Compute confidence for combo signal (multi-signal breakout)"""
        # Combo signals get boosted confidence
        velocity_factor = min(velocity / 5.0, 1.0)
        surge_factor = min((score_surge - 1.0) / 1.0, 1.0)
        stability_factor = min(baseline_weeks_observed / 4.0, 1.0)
        mention_factor = min(current_mention.mention_count / 8.0, 1.0)

        confidence = (
            velocity_factor * 0.3 +
            surge_factor * 0.3 +
            stability_factor * 0.2 +
            mention_factor * 0.2
        )

        # Boost combo signals by 20%
        confidence = min(confidence * 1.2, 1.0)
        return max(confidence, self.config.get('min_confidence', 0.3))
```

---

## Configuration

**File: config/trend_detection.json**

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

**Parameters**:
- `baseline_weeks`: Rolling window for comparison (default: 4)
- `new_entity_min_mentions`: Minimum mentions to trigger new_entity signal (default: 3)
- `velocity_spike`: Threshold multiplier for velocity_spike (default: 3.0 = 300%)
- `score_surge`: Threshold multiplier for score_surge (default: 1.5 = 150%)
- `min_baseline_mentions`: Minimum avg mentions to consider entity established (default: 2)
- `min_confidence`: Minimum confidence to surface a signal (default: 0.3)
- `min_baseline_weeks`: Minimum weeks entity must appear in baseline (default: 2)

---

## Heatmap Visualization

### Streamlit UI Component

**File: modules/trend_heatmap.py**

```python
import streamlit as st
import pandas as pd
import plotly.express as px
from typing import List, Dict
from utils.schemas import EntityMention, TrendSignal
from utils.trend_aggregator import TrendAggregator

class TrendHeatmapUI:
    def __init__(self, aggregator: TrendAggregator):
        self.aggregator = aggregator

    def render(self, weeks: List[str], entity_type_filter: str = "all"):
        """Render the main heatmap view"""

        # Aggregate data for all weeks
        all_mentions: Dict[str, List[EntityMention]] = {}
        for week in weeks:
            all_mentions[week] = self.aggregator.aggregate_week(week)

        # Build heatmap matrix
        df = self._build_heatmap_dataframe(all_mentions, entity_type_filter)

        if df.empty:
            st.warning("No entity data found for selected weeks")
            return

        # Render heatmap using Plotly
        fig = px.imshow(
            df,
            labels=dict(x="Week", y="Entity", color="Intensity"),
            x=df.columns.tolist(),
            y=df.index.tolist(),
            color_continuous_scale="YlOrRd",
            aspect="auto",
            title="Entity Trend Heatmap"
        )

        fig.update_xaxes(side="bottom")
        fig.update_layout(
            height=max(400, len(df) * 30),  # Dynamic height
            xaxis_title="Week",
            yaxis_title="Entity",
            coloraxis_colorbar_title="Intensity"
        )

        st.plotly_chart(fig, use_container_width=True)

        # Detect and display trend signals
        self._render_trend_signals(weeks[-1], baseline_weeks=4)

    def _build_heatmap_dataframe(
        self,
        all_mentions: Dict[str, List[EntityMention]],
        entity_type_filter: str
    ) -> pd.DataFrame:
        """Convert EntityMention data to heatmap matrix"""

        entity_data: Dict[str, Dict[str, float]] = {}

        for week, mentions in all_mentions.items():
            for mention in mentions:
                if entity_type_filter != "all" and mention.entity_type != entity_type_filter:
                    continue

                entity_name = mention.entity_name
                if entity_name not in entity_data:
                    entity_data[entity_name] = {}

                # Use total_score for intensity
                entity_data[entity_name][week] = mention.total_score

        df = pd.DataFrame.from_dict(entity_data, orient='index')
        df = df.fillna(0)

        # Sort by total intensity
        df['_total'] = df.sum(axis=1)
        df = df.sort_values('_total', ascending=False).drop(columns=['_total'])

        # Limit to top 50
        df = df.head(50)

        return df

    def _render_trend_signals(self, current_week: str, baseline_weeks: int):
        """Display discovered trend signals in sidebar"""

        signals = self.aggregator.detect_trend_signals(
            current_week=current_week,
            baseline_weeks=baseline_weeks
        )

        if not signals:
            st.sidebar.info("No significant trends detected this week")
            return

        st.sidebar.subheader("🔥 Trending This Week")

        # Group signals by type
        signal_groups = {
            "velocity_spike": [],
            "new_entity": [],
            "score_surge": [],
            "combo": []
        }

        for signal in signals:
            signal_groups[signal.signal_type].append(signal)

        # Render each group
        signal_labels = {
            "combo": "🚀 Multi-Signal Breakout",
            "velocity_spike": "📈 Mention Spike",
            "new_entity": "✨ New Appearance",
            "score_surge": "💥 Impact Surge"
        }

        for signal_type, label in signal_labels.items():
            group_signals = signal_groups[signal_type]
            if not group_signals:
                continue

            with st.sidebar.expander(f"{label} ({len(group_signals)})", expanded=(signal_type == "combo")):
                for signal in sorted(group_signals, key=lambda s: s.confidence, reverse=True):
                    self._render_signal_card(signal)

    def _render_signal_card(self, signal: TrendSignal):
        """Render individual signal card with evidence"""

        # Header with confidence badge
        confidence_color = "green" if signal.confidence > 0.7 else "orange" if signal.confidence > 0.4 else "red"
        st.markdown(
            f"**{signal.entity_name}** "
            f"<span style='color:{confidence_color}'>●</span> {signal.confidence:.0%}",
            unsafe_allow_html=True
        )

        # Metrics
        cols = st.columns(2)
        with cols[0]:
            st.metric(
                label="Mentions",
                value=signal.current_mentions,
                delta=f"+{signal.velocity_change:.0%}"
            )

        with cols[1]:
            if signal.score_delta is not None:
                st.metric(
                    label="Impact Score",
                    value=f"{signal.current_score:.1f}",
                    delta=f"+{signal.score_delta:.1f}"
                )

        # Evidence articles
        if signal.evidence_titles:
            with st.expander("📄 Evidence Articles"):
                for title in signal.evidence_titles:
                    st.markdown(f"- {title}")

        st.markdown("---")
```

### Integration with app.py

Add new "Trend Radar" tab to existing Streamlit UI:

```python
import streamlit as st
from modules.trend_heatmap import TrendHeatmapUI
from utils.trend_aggregator import TrendAggregator
from utils.context_retriever import ContextRetriever
from pathlib import Path

def main():
    st.set_page_config(page_title="AI Industry Briefing", layout="wide")

    # Tabs: [Briefings, Chatbox, Trend Radar]
    tab1, tab2, tab3 = st.tabs(["📰 Briefings", "💬 Chatbox", "🔥 Trend Radar"])

    with tab1:
        render_briefings()  # Existing

    with tab2:
        render_chatbox()  # Existing

    with tab3:
        render_trend_radar()  # NEW

def render_trend_radar():
    st.title("🔥 Entity Trend Radar")
    st.markdown("Discover what's heating up in AI this week")

    # Sidebar filters
    st.sidebar.subheader("Filters")

    available_weeks = get_available_weeks()
    num_weeks = st.sidebar.slider("Weeks to analyze", 4, 12, 8)
    selected_weeks = available_weeks[-num_weeks:]

    entity_type = st.sidebar.selectbox(
        "Entity Type",
        options=["all", "company", "model", "topic", "person"],
        index=0
    )

    # Initialize components
    context = ContextRetriever(report_dir="./data/reports")
    aggregator = TrendAggregator(
        context=context,
        config_path="./config/trend_detection.json"
    )
    heatmap_ui = TrendHeatmapUI(aggregator)

    # Render heatmap
    heatmap_ui.render(weeks=selected_weeks, entity_type_filter=entity_type)

def get_available_weeks() -> List[str]:
    """Scan data/reports/ for weekly reports"""
    report_dir = Path("./data/reports")
    week_ids = []

    for report_file in sorted(report_dir.glob("weekly_*.md")):
        week_id = report_file.stem.replace("weekly_", "")
        week_ids.append(week_id)

    return week_ids
```

---

## Integration Points

### Existing Infrastructure Reused

1. **context_retriever.py**: `get_articles_by_week()` for article access
2. **entity_extractor.py**: `extract_entities()` for entity extraction
3. **checkpoint_manager.py**: (Optional) Cache aggregated mentions
4. **scoring_engine.py**: Reuse 5D weighted scores
5. **schemas.py**: Extend with EntityMention and TrendSignal models

### New Components Required

1. **utils/trend_aggregator.py**: Core aggregation and detection logic
2. **modules/trend_heatmap.py**: Streamlit visualization component
3. **config/trend_detection.json**: Configuration file
4. **tests/test_trend_aggregator.py**: Unit tests

---

## Implementation Phases

### Phase 1: Core Data Layer
- [ ] Extend `utils/schemas.py` with EntityMention and TrendSignal
- [ ] Implement `normalize_entity_name()` function
- [ ] Create `utils/trend_aggregator.py` with `aggregate_week()` method
- [ ] Add `config/trend_detection.json`
- [ ] Unit tests for aggregation logic

### Phase 2: Detection Logic
- [ ] Implement `detect_trend_signals()` method
- [ ] Add confidence scoring functions
- [ ] Implement `_get_baseline_weeks()` helper
- [ ] Add `_get_article_titles()` for evidence display
- [ ] Unit tests for signal detection

### Phase 3: Visualization
- [ ] Create `modules/trend_heatmap.py`
- [ ] Implement `TrendHeatmapUI` class
- [ ] Add heatmap rendering with Plotly
- [ ] Add trend signal sidebar
- [ ] Integrate with `app.py`

### Phase 4: Polish & Testing
- [ ] Add week range selector
- [ ] Implement entity type filters
- [ ] Add drill-down to article details
- [ ] End-to-end testing with real data
- [ ] Documentation and examples

---

## CLI Commands

```bash
# Generate weekly briefing with entity extraction
python main.py --defaults --finalize --weekly

# Test aggregation for current week
python -c "
from utils.trend_aggregator import TrendAggregator
from utils.context_retriever import ContextRetriever

context = ContextRetriever('./data/reports')
agg = TrendAggregator(context)

signals = agg.detect_trend_signals('2025-W01', baseline_weeks=4)
for s in signals:
    print(f'{s.entity_name}: {s.signal_type} (confidence={s.confidence:.0%})')
"

# Launch Streamlit UI
streamlit run app.py
```

---

## Visual Design

**Heatmap Color Scale**:
- Yellow: Baseline activity (total_score 0-20)
- Orange: Moderate increase (total_score 20-50)
- Red: High intensity (total_score 50+)

**Confidence Badges**:
- 🟢 Green: >70% confidence
- 🟠 Orange: 40-70% confidence
- 🔴 Red: <40% confidence

**Interaction**:
- Hover on heatmap cell → Show entity name, week, exact score
- Click on cell → Navigate to article drill-down
- Expand signal card → View evidence articles

---

## Success Metrics

- **Precision**: 80%+ of detected signals are genuinely interesting (validated by user)
- **Recall**: Catches major AI news breakouts within 1 week
- **False Positive Rate**: <20% (tuned via confidence thresholds)
- **Performance**: Aggregate 8 weeks in <30 seconds
- **UI Responsiveness**: Heatmap loads in <5 seconds

---

**Design Status**: ✅ Complete
**Next Step**: Implement Phase 1 (Core Data Layer)
**Estimated Implementation**: 4-6 hours (all phases)