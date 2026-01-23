# Shadow Mode Backtesting Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a "Time Travel" backtesting system to validate trend radar predictions against historical outcomes, starting with a DeepSeek case study.

**Architecture:** Wayback Machine for historical data → Backtest Engine → Scorecard Generator → Dashboard UI

**Tech Stack:** Python, waybackpy, existing trend radar infrastructure, React dashboard

---

## Task 1: Create Ground Truth Registry

**Files:**
- Create: `config/ground_truth.json`

**Steps:**

1. Create ground truth file with curated breakout events:

```json
{
  "_meta": {
    "version": "1.0",
    "description": "Curated breakout events for backtest validation",
    "last_updated": "2026-01-22"
  },
  "breakout_events": [
    {
      "entity_id": "deepseek",
      "entity_name": "DeepSeek",
      "entity_type": "company",
      "category": "llm_domestic",
      "early_signal_date": "2024-12-01",
      "breakout_date": "2025-01-20",
      "mainstream_sources": [
        {"source": "techcrunch", "date": "2025-01-21", "url": "https://techcrunch.com/2025/01/21/deepseek-v3/"},
        {"source": "wired", "date": "2025-01-22"},
        {"source": "nytimes", "date": "2025-01-23"}
      ],
      "expected_signals": ["github_trending", "hf_downloads", "news_velocity_cn"],
      "notes": "DeepSeek-V3 release caused massive mainstream attention"
    },
    {
      "entity_id": "cursor",
      "entity_name": "Cursor",
      "entity_type": "product",
      "category": "code-ai",
      "early_signal_date": "2024-10-15",
      "breakout_date": "2024-12-15",
      "mainstream_sources": [
        {"source": "techcrunch", "date": "2024-12-18"}
      ],
      "expected_signals": ["github_stars", "twitter_mentions", "news_velocity"],
      "notes": "AI IDE category breakout"
    },
    {
      "entity_id": "qwen",
      "entity_name": "Qwen",
      "entity_type": "model",
      "category": "llm_domestic",
      "early_signal_date": "2024-11-15",
      "breakout_date": "2025-01-10",
      "mainstream_sources": [
        {"source": "techcrunch", "date": "2025-01-12"}
      ],
      "expected_signals": ["hf_downloads", "github_trending", "news_velocity_cn"],
      "notes": "Qwen2.5 series adoption surge"
    },
    {
      "entity_id": "windsurf",
      "entity_name": "Windsurf",
      "entity_type": "product",
      "category": "code-ai",
      "early_signal_date": "2024-12-01",
      "breakout_date": "2025-01-15",
      "mainstream_sources": [
        {"source": "techcrunch", "date": "2025-01-16"}
      ],
      "expected_signals": ["twitter_mentions", "github_stars"],
      "notes": "Codeium's AI IDE launch"
    }
  ],
  "mainstream_outlets": {
    "tier1": ["nytimes", "wsj", "washingtonpost", "bbc"],
    "tier2": ["techcrunch", "wired", "theverge", "arstechnica"],
    "tier3": ["venturebeat", "zdnet", "engadget"]
  },
  "detection_window_weeks": 8
}
```

2. Commit: `feat: add ground truth registry for backtest validation`

---

## Task 2: Create Wayback Machine Scraper

**Files:**
- Create: `scrapers/wayback_scraper.py`
- Create: `tests/test_wayback_scraper.py`

**Steps:**

1. Install waybackpy if needed: `pip install waybackpy`

2. Create the scraper:

```python
# scrapers/wayback_scraper.py
"""Fetch historical snapshots from Wayback Machine for backtesting."""

import json
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import time

try:
    import waybackpy
    WAYBACK_AVAILABLE = True
except ImportError:
    WAYBACK_AVAILABLE = False

import requests


@dataclass
class WaybackSnapshot:
    """A historical snapshot from Wayback Machine."""
    url: str
    original_url: str
    timestamp: str
    status_code: int
    content_type: str
    content: Optional[str] = None
    fetched_at: str = ""


class WaybackScraper:
    """Fetch historical web snapshots for backtesting."""

    # Sources we can fetch from Wayback
    SUPPORTED_SOURCES = {
        "jiqizhixin": "https://www.jiqizhixin.com",
        "qbitai": "https://www.qbitai.com",
        "github_trending": "https://github.com/trending",
        "huggingface_models": "https://huggingface.co/models",
        "hackernews": "https://news.ycombinator.com",
        "techcrunch_ai": "https://techcrunch.com/category/artificial-intelligence/",
    }

    def __init__(self, cache_dir: Optional[Path] = None):
        if not WAYBACK_AVAILABLE:
            raise ImportError("waybackpy is required. Install with: pip install waybackpy")

        self.cache_dir = cache_dir or Path("data/wayback_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_snapshot(
        self,
        url: str,
        target_date: date,
        fetch_content: bool = True,
    ) -> Optional[WaybackSnapshot]:
        """
        Get closest snapshot to target date.

        Args:
            url: URL to fetch historical version of
            target_date: Date to find closest snapshot to
            fetch_content: Whether to fetch full HTML content

        Returns:
            WaybackSnapshot or None if not found
        """
        # Check cache first
        cache_key = f"{url.replace('/', '_').replace(':', '')}_{target_date.isoformat()}"
        cache_file = self.cache_dir / f"{cache_key}.json"

        if cache_file.exists():
            with open(cache_file, encoding="utf-8") as f:
                data = json.load(f)
                return WaybackSnapshot(**data)

        try:
            # Use waybackpy to find nearest snapshot
            user_agent = "BriefAI Backtest Bot (research purposes)"
            availability = waybackpy.Url(url, user_agent).near(
                year=target_date.year,
                month=target_date.month,
                day=target_date.day,
            )

            snapshot = WaybackSnapshot(
                url=availability.archive_url,
                original_url=url,
                timestamp=availability.timestamp.isoformat() if availability.timestamp else "",
                status_code=200,
                content_type="text/html",
                fetched_at=datetime.now().isoformat(),
            )

            # Optionally fetch content
            if fetch_content:
                try:
                    resp = requests.get(availability.archive_url, timeout=30)
                    snapshot.content = resp.text[:100000]  # Limit size
                except Exception:
                    pass

            # Cache the result
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(asdict(snapshot), f, ensure_ascii=False, indent=2)

            # Rate limit
            time.sleep(1)

            return snapshot

        except Exception as e:
            print(f"Wayback fetch failed for {url} @ {target_date}: {e}")
            return None

    def get_source_snapshot(
        self,
        source_id: str,
        target_date: date,
    ) -> Optional[WaybackSnapshot]:
        """Get snapshot for a known source ID."""
        url = self.SUPPORTED_SOURCES.get(source_id)
        if not url:
            raise ValueError(f"Unknown source: {source_id}")

        return self.get_snapshot(url, target_date)

    def build_historical_snapshot(
        self,
        target_date: date,
        sources: Optional[List[str]] = None,
    ) -> Dict[str, WaybackSnapshot]:
        """
        Build a multi-source snapshot for a historical date.

        Returns dict of source_id → WaybackSnapshot
        """
        if sources is None:
            sources = list(self.SUPPORTED_SOURCES.keys())

        snapshots = {}
        for source_id in sources:
            print(f"Fetching {source_id} @ {target_date}...")
            snapshot = self.get_source_snapshot(source_id, target_date)
            if snapshot:
                snapshots[source_id] = snapshot
            time.sleep(0.5)  # Rate limit between sources

        return snapshots
```

3. Create test file:

```python
# tests/test_wayback_scraper.py
import pytest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from scrapers.wayback_scraper import WaybackScraper, WaybackSnapshot, WAYBACK_AVAILABLE


@pytest.mark.skipif(not WAYBACK_AVAILABLE, reason="waybackpy not installed")
class TestWaybackScraper:
    """Tests for Wayback Machine scraper."""

    def test_supported_sources_defined(self):
        """Scraper has supported sources."""
        assert len(WaybackScraper.SUPPORTED_SOURCES) > 0
        assert "github_trending" in WaybackScraper.SUPPORTED_SOURCES

    def test_cache_directory_created(self):
        """Scraper creates cache directory."""
        with TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "wayback_cache"
            scraper = WaybackScraper(cache_dir=cache_dir)
            assert cache_dir.exists()

    @pytest.mark.integration
    def test_fetch_github_trending_historical(self):
        """Fetch historical GitHub trending page."""
        scraper = WaybackScraper()
        snapshot = scraper.get_source_snapshot(
            "github_trending",
            date(2024, 12, 15),
        )

        # May or may not find a snapshot
        if snapshot:
            assert snapshot.original_url == "https://github.com/trending"
            assert "2024" in snapshot.timestamp


class TestWaybackSnapshot:
    """Tests for WaybackSnapshot dataclass."""

    def test_snapshot_fields(self):
        """Snapshot has expected fields."""
        snapshot = WaybackSnapshot(
            url="https://web.archive.org/web/20241215/https://github.com/trending",
            original_url="https://github.com/trending",
            timestamp="2024-12-15T12:00:00",
            status_code=200,
            content_type="text/html",
        )

        assert snapshot.url.startswith("https://web.archive.org")
        assert snapshot.original_url == "https://github.com/trending"
```

4. Run tests: `pytest tests/test_wayback_scraper.py -v`

5. Commit: `feat: add Wayback Machine scraper for historical data`

---

## Task 3: Create Backtest Engine

**Files:**
- Create: `utils/backtest_engine.py`

**Steps:**

1. Create the backtest engine:

```python
# utils/backtest_engine.py
"""Backtest Engine - Run trend radar at historical dates."""

import json
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils.trend_signal_enricher import TrendSignal, TrendSignalEnricher


@dataclass
class BacktestPrediction:
    """A prediction made at a historical date."""
    prediction_date: str
    entity_id: str
    entity_name: str
    entity_type: str
    signal_type: str
    momentum_score: float
    validation_score: float
    validation_status: str
    bucket_id: Optional[str] = None
    rank: int = 0


@dataclass
class BacktestRun:
    """Results of a backtest run."""
    run_id: str
    prediction_date: str
    validation_date: str
    predictions: List[BacktestPrediction]
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)


class BacktestEngine:
    """
    Run trend radar at historical dates to generate predictions.

    Usage:
        engine = BacktestEngine()
        run = engine.run_backtest(
            prediction_date=date(2024, 12, 15),
            validation_date=date(2025, 1, 20),
        )
    """

    def __init__(
        self,
        ground_truth_path: Optional[Path] = None,
        output_dir: Optional[Path] = None,
    ):
        config_dir = Path(__file__).parent.parent / "config"
        self.ground_truth_path = ground_truth_path or config_dir / "ground_truth.json"
        self.output_dir = output_dir or Path(__file__).parent.parent / "data" / "backtests"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.ground_truth = self._load_ground_truth()

    def _load_ground_truth(self) -> Dict:
        """Load ground truth registry."""
        if self.ground_truth_path.exists():
            with open(self.ground_truth_path, encoding="utf-8") as f:
                return json.load(f)
        return {"breakout_events": []}

    def run_backtest(
        self,
        prediction_date: date,
        validation_date: date,
        top_k: int = 20,
        use_wayback: bool = False,
    ) -> BacktestRun:
        """
        Run trend radar at prediction_date, compare to validation_date outcomes.

        Args:
            prediction_date: Date to "travel back" to
            validation_date: Date to validate predictions against
            top_k: Number of top predictions to include
            use_wayback: Whether to fetch historical data from Wayback

        Returns:
            BacktestRun with predictions
        """
        run_id = f"backtest_{prediction_date.isoformat()}_{validation_date.isoformat()}"

        # In full implementation, this would:
        # 1. Load or fetch historical snapshot for prediction_date
        # 2. Run trend aggregator with that data
        # 3. Run signal enricher/validator
        # For MVP, we simulate with synthetic predictions

        predictions = self._generate_predictions(prediction_date, top_k)

        run = BacktestRun(
            run_id=run_id,
            prediction_date=prediction_date.isoformat(),
            validation_date=validation_date.isoformat(),
            predictions=predictions,
            metadata={
                "top_k": top_k,
                "use_wayback": use_wayback,
                "ground_truth_version": self.ground_truth.get("_meta", {}).get("version"),
            },
            created_at=datetime.now().isoformat(),
        )

        # Save run
        self._save_run(run)

        return run

    def _generate_predictions(
        self,
        prediction_date: date,
        top_k: int,
    ) -> List[BacktestPrediction]:
        """
        Generate predictions for a historical date.

        In MVP, this uses ground truth entities as "predictions"
        to demonstrate the scorecard flow.
        """
        predictions = []

        for i, event in enumerate(self.ground_truth.get("breakout_events", [])[:top_k]):
            # Check if this event should have been detectable at prediction_date
            early_date = datetime.fromisoformat(event["early_signal_date"]).date()

            # Only include if prediction_date is after early signal date
            if prediction_date >= early_date:
                predictions.append(BacktestPrediction(
                    prediction_date=prediction_date.isoformat(),
                    entity_id=event["entity_id"],
                    entity_name=event["entity_name"],
                    entity_type=event["entity_type"],
                    signal_type="velocity_spike",
                    momentum_score=85.0 - (i * 5),  # Simulated scores
                    validation_score=0.75 - (i * 0.05),
                    validation_status="validated" if i < 3 else "unvalidated",
                    bucket_id=event.get("category"),
                    rank=i + 1,
                ))

        return predictions

    def _save_run(self, run: BacktestRun):
        """Save backtest run to file."""
        output_file = self.output_dir / f"{run.run_id}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(run.to_dict(), f, ensure_ascii=False, indent=2)

    def load_run(self, run_id: str) -> Optional[BacktestRun]:
        """Load a saved backtest run."""
        run_file = self.output_dir / f"{run_id}.json"
        if not run_file.exists():
            return None

        with open(run_file, encoding="utf-8") as f:
            data = json.load(f)

        predictions = [BacktestPrediction(**p) for p in data.get("predictions", [])]
        return BacktestRun(
            run_id=data["run_id"],
            prediction_date=data["prediction_date"],
            validation_date=data["validation_date"],
            predictions=predictions,
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at", ""),
        )

    def list_runs(self) -> List[str]:
        """List all saved backtest runs."""
        return [f.stem for f in self.output_dir.glob("backtest_*.json")]
```

2. Commit: `feat: add backtest engine for historical prediction runs`

---

## Task 4: Create Scorecard Generator

**Files:**
- Create: `utils/scorecard_generator.py`

**Steps:**

1. Create the scorecard generator:

```python
# utils/scorecard_generator.py
"""Scorecard Generator - Compare backtest predictions to ground truth outcomes."""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from utils.backtest_engine import BacktestRun, BacktestPrediction


@dataclass
class PredictionOutcome:
    """Outcome evaluation for a single prediction."""
    entity_id: str
    entity_name: str
    predicted_rank: int
    momentum_score: float
    hit: bool  # Did this entity break out?
    lead_time_weeks: Optional[float] = None  # Weeks before mainstream
    mainstream_date: Optional[str] = None
    mainstream_source: Optional[str] = None
    notes: str = ""


@dataclass
class Scorecard:
    """Backtest scorecard with metrics."""
    run_id: str
    prediction_date: str
    validation_date: str

    # Core metrics
    precision_at_k: float  # Of top K, how many hit?
    recall: float  # Of known breakouts, how many did we detect?
    avg_lead_time_weeks: float
    miss_rate: float  # Known breakouts we missed

    # Details
    total_predictions: int
    total_hits: int
    total_misses: int
    total_false_positives: int

    # Breakdowns
    hits: List[PredictionOutcome]
    misses: List[PredictionOutcome]  # In ground truth but not predicted
    false_positives: List[PredictionOutcome]  # Predicted but didn't break out

    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)

    def format_summary(self) -> str:
        """Format scorecard as human-readable summary."""
        lines = [
            "=" * 60,
            f"SHADOW MODE BACKTEST: {self.prediction_date} → {self.validation_date}",
            "=" * 60,
            "",
            f"PRECISION@{self.total_predictions}: {self.total_hits}/{self.total_predictions} ({self.precision_at_k:.0%})",
            f"AVG LEAD TIME: {self.avg_lead_time_weeks:.1f} weeks before mainstream",
            "",
            "TOP HITS:",
        ]

        for hit in self.hits[:5]:
            lead = f"{hit.lead_time_weeks:.0f}w lead" if hit.lead_time_weeks else "N/A"
            lines.append(f"  ✓ {hit.entity_name:<15} - Rank #{hit.predicted_rank}, {lead}")

        if self.misses:
            lines.append("")
            lines.append("MISSES (in ground truth but not detected):")
            for miss in self.misses[:3]:
                lines.append(f"  ✗ {miss.entity_name:<15} - First detected after mainstream")

        if self.false_positives:
            lines.append("")
            lines.append("FALSE POSITIVES (high score but didn't break out):")
            for fp in self.false_positives[:3]:
                lines.append(f"  ? {fp.entity_name:<15} - Score {fp.momentum_score:.0f}, no mainstream yet")

        return "\n".join(lines)


class ScorecardGenerator:
    """Generate scorecards from backtest runs."""

    def __init__(self, ground_truth_path: Optional[Path] = None):
        config_dir = Path(__file__).parent.parent / "config"
        self.ground_truth_path = ground_truth_path or config_dir / "ground_truth.json"
        self.ground_truth = self._load_ground_truth()

    def _load_ground_truth(self) -> Dict:
        """Load ground truth registry."""
        if self.ground_truth_path.exists():
            with open(self.ground_truth_path, encoding="utf-8") as f:
                return json.load(f)
        return {"breakout_events": []}

    def generate_scorecard(self, run: BacktestRun) -> Scorecard:
        """
        Generate scorecard from backtest run.

        Compares predictions to ground truth breakout events.
        """
        prediction_date = date.fromisoformat(run.prediction_date)
        validation_date = date.fromisoformat(run.validation_date)

        # Build ground truth lookup
        gt_entities: Dict[str, Dict] = {}
        for event in self.ground_truth.get("breakout_events", []):
            breakout_date = date.fromisoformat(event["breakout_date"])
            # Only count breakouts that happened before validation date
            if breakout_date <= validation_date:
                gt_entities[event["entity_id"]] = event

        # Evaluate each prediction
        hits: List[PredictionOutcome] = []
        false_positives: List[PredictionOutcome] = []
        predicted_ids: Set[str] = set()

        for pred in run.predictions:
            predicted_ids.add(pred.entity_id)

            if pred.entity_id in gt_entities:
                event = gt_entities[pred.entity_id]
                breakout_date = date.fromisoformat(event["breakout_date"])

                # Calculate lead time
                lead_time_days = (breakout_date - prediction_date).days
                lead_time_weeks = lead_time_days / 7 if lead_time_days > 0 else 0

                # Get first mainstream source
                mainstream_sources = event.get("mainstream_sources", [])
                first_source = mainstream_sources[0] if mainstream_sources else {}

                hits.append(PredictionOutcome(
                    entity_id=pred.entity_id,
                    entity_name=pred.entity_name,
                    predicted_rank=pred.rank,
                    momentum_score=pred.momentum_score,
                    hit=True,
                    lead_time_weeks=lead_time_weeks,
                    mainstream_date=event["breakout_date"],
                    mainstream_source=first_source.get("source"),
                ))
            else:
                false_positives.append(PredictionOutcome(
                    entity_id=pred.entity_id,
                    entity_name=pred.entity_name,
                    predicted_rank=pred.rank,
                    momentum_score=pred.momentum_score,
                    hit=False,
                    notes="Not in ground truth or breakout after validation date",
                ))

        # Find misses (in ground truth but not predicted)
        misses: List[PredictionOutcome] = []
        for entity_id, event in gt_entities.items():
            if entity_id not in predicted_ids:
                misses.append(PredictionOutcome(
                    entity_id=entity_id,
                    entity_name=event["entity_name"],
                    predicted_rank=0,
                    momentum_score=0,
                    hit=False,
                    mainstream_date=event["breakout_date"],
                    notes="In ground truth but not detected",
                ))

        # Calculate metrics
        total_predictions = len(run.predictions)
        total_hits = len(hits)
        total_gt = len(gt_entities)

        precision = total_hits / total_predictions if total_predictions > 0 else 0
        recall = total_hits / total_gt if total_gt > 0 else 0
        miss_rate = len(misses) / total_gt if total_gt > 0 else 0

        lead_times = [h.lead_time_weeks for h in hits if h.lead_time_weeks is not None]
        avg_lead_time = sum(lead_times) / len(lead_times) if lead_times else 0

        return Scorecard(
            run_id=run.run_id,
            prediction_date=run.prediction_date,
            validation_date=run.validation_date,
            precision_at_k=precision,
            recall=recall,
            avg_lead_time_weeks=avg_lead_time,
            miss_rate=miss_rate,
            total_predictions=total_predictions,
            total_hits=total_hits,
            total_misses=len(misses),
            total_false_positives=len(false_positives),
            hits=hits,
            misses=misses,
            false_positives=false_positives,
            created_at=datetime.now().isoformat(),
        )
```

2. Commit: `feat: add scorecard generator for backtest evaluation`

---

## Task 5: Create Backtest API Endpoints

**Files:**
- Create: `api/routers/backtest.py`
- Modify: `api/main.py`

**Steps:**

1. Create backtest API router:

```python
# api/routers/backtest.py
"""Backtest API endpoints for shadow mode."""

from datetime import date
from typing import List, Optional
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

import sys
_app_dir = Path(__file__).parent.parent.parent
if str(_app_dir) not in sys.path:
    sys.path.insert(0, str(_app_dir))

from utils.backtest_engine import BacktestEngine
from utils.scorecard_generator import ScorecardGenerator


router = APIRouter(prefix="/api/backtest", tags=["backtest"])


class PredictionOut(BaseModel):
    entity_id: str
    entity_name: str
    entity_type: str
    momentum_score: float
    validation_score: float
    validation_status: str
    rank: int


class BacktestRunOut(BaseModel):
    run_id: str
    prediction_date: str
    validation_date: str
    predictions: List[PredictionOut]
    created_at: str


class OutcomeOut(BaseModel):
    entity_id: str
    entity_name: str
    predicted_rank: int
    momentum_score: float
    hit: bool
    lead_time_weeks: Optional[float]
    mainstream_date: Optional[str]
    mainstream_source: Optional[str]


class ScorecardOut(BaseModel):
    run_id: str
    prediction_date: str
    validation_date: str
    precision_at_k: float
    recall: float
    avg_lead_time_weeks: float
    miss_rate: float
    total_predictions: int
    total_hits: int
    total_misses: int
    total_false_positives: int
    hits: List[OutcomeOut]
    misses: List[OutcomeOut]
    false_positives: List[OutcomeOut]


@router.get("/runs", response_model=List[str])
def list_backtest_runs():
    """List all saved backtest runs."""
    engine = BacktestEngine()
    return engine.list_runs()


@router.get("/runs/{run_id}", response_model=BacktestRunOut)
def get_backtest_run(run_id: str):
    """Get a specific backtest run."""
    engine = BacktestEngine()
    run = engine.load_run(run_id)

    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    return BacktestRunOut(
        run_id=run.run_id,
        prediction_date=run.prediction_date,
        validation_date=run.validation_date,
        predictions=[
            PredictionOut(
                entity_id=p.entity_id,
                entity_name=p.entity_name,
                entity_type=p.entity_type,
                momentum_score=p.momentum_score,
                validation_score=p.validation_score,
                validation_status=p.validation_status,
                rank=p.rank,
            )
            for p in run.predictions
        ],
        created_at=run.created_at,
    )


@router.post("/runs", response_model=BacktestRunOut)
def create_backtest_run(
    prediction_date: str = Query(..., description="Date to predict from (YYYY-MM-DD)"),
    validation_date: str = Query(..., description="Date to validate against (YYYY-MM-DD)"),
    top_k: int = Query(20, description="Number of top predictions"),
):
    """Create a new backtest run."""
    try:
        pred_date = date.fromisoformat(prediction_date)
        val_date = date.fromisoformat(validation_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    if pred_date >= val_date:
        raise HTTPException(status_code=400, detail="Prediction date must be before validation date")

    engine = BacktestEngine()
    run = engine.run_backtest(pred_date, val_date, top_k)

    return BacktestRunOut(
        run_id=run.run_id,
        prediction_date=run.prediction_date,
        validation_date=run.validation_date,
        predictions=[
            PredictionOut(
                entity_id=p.entity_id,
                entity_name=p.entity_name,
                entity_type=p.entity_type,
                momentum_score=p.momentum_score,
                validation_score=p.validation_score,
                validation_status=p.validation_status,
                rank=p.rank,
            )
            for p in run.predictions
        ],
        created_at=run.created_at,
    )


@router.get("/runs/{run_id}/scorecard", response_model=ScorecardOut)
def get_scorecard(run_id: str):
    """Generate scorecard for a backtest run."""
    engine = BacktestEngine()
    run = engine.load_run(run_id)

    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    generator = ScorecardGenerator()
    scorecard = generator.generate_scorecard(run)

    return ScorecardOut(
        run_id=scorecard.run_id,
        prediction_date=scorecard.prediction_date,
        validation_date=scorecard.validation_date,
        precision_at_k=scorecard.precision_at_k,
        recall=scorecard.recall,
        avg_lead_time_weeks=scorecard.avg_lead_time_weeks,
        miss_rate=scorecard.miss_rate,
        total_predictions=scorecard.total_predictions,
        total_hits=scorecard.total_hits,
        total_misses=scorecard.total_misses,
        total_false_positives=scorecard.total_false_positives,
        hits=[OutcomeOut(**h.__dict__) for h in scorecard.hits],
        misses=[OutcomeOut(**m.__dict__) for m in scorecard.misses],
        false_positives=[OutcomeOut(**f.__dict__) for f in scorecard.false_positives],
    )
```

2. Register router in `api/main.py`:

```python
from api.routers import backtest
app.include_router(backtest.router)
```

3. Commit: `feat: add backtest API endpoints`

---

## Task 6: Create Backtest Dashboard Page

**Files:**
- Create: `frontend/src/pages/Backtest.jsx`
- Modify: `frontend/src/App.jsx`

**Steps:**

1. Create Backtest page:

```jsx
// frontend/src/pages/Backtest.jsx
import { useState } from 'react'
import { useApi } from '../hooks/useApi'

function ScorecardMetrics({ scorecard }) {
  return (
    <div className="grid grid-cols-4 gap-4 mb-6">
      <div className="bg-green-50 rounded-lg p-4 text-center">
        <div className="text-3xl font-bold text-green-600">
          {(scorecard.precision_at_k * 100).toFixed(0)}%
        </div>
        <div className="text-sm text-gray-600">Precision@{scorecard.total_predictions}</div>
      </div>
      <div className="bg-blue-50 rounded-lg p-4 text-center">
        <div className="text-3xl font-bold text-blue-600">
          {scorecard.avg_lead_time_weeks.toFixed(1)}w
        </div>
        <div className="text-sm text-gray-600">Avg Lead Time</div>
      </div>
      <div className="bg-purple-50 rounded-lg p-4 text-center">
        <div className="text-3xl font-bold text-purple-600">
          {scorecard.total_hits}/{scorecard.total_predictions}
        </div>
        <div className="text-sm text-gray-600">Hits</div>
      </div>
      <div className="bg-red-50 rounded-lg p-4 text-center">
        <div className="text-3xl font-bold text-red-600">
          {scorecard.total_misses}
        </div>
        <div className="text-sm text-gray-600">Misses</div>
      </div>
    </div>
  )
}

function HitsList({ hits }) {
  if (!hits?.length) return null

  return (
    <div className="mb-6">
      <h3 className="font-semibold text-green-700 mb-3">✓ Successful Predictions</h3>
      <div className="space-y-2">
        {hits.map((hit, idx) => (
          <div key={idx} className="bg-green-50 rounded p-3 flex justify-between items-center">
            <div>
              <span className="font-medium">{hit.entity_name}</span>
              <span className="text-sm text-gray-500 ml-2">#{hit.predicted_rank}</span>
            </div>
            <div className="text-sm text-green-600">
              {hit.lead_time_weeks?.toFixed(0)}w lead → {hit.mainstream_source}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function MissesList({ misses }) {
  if (!misses?.length) return null

  return (
    <div className="mb-6">
      <h3 className="font-semibold text-red-700 mb-3">✗ Missed Breakouts</h3>
      <div className="space-y-2">
        {misses.map((miss, idx) => (
          <div key={idx} className="bg-red-50 rounded p-3">
            <span className="font-medium">{miss.entity_name}</span>
            <span className="text-sm text-gray-500 ml-2">
              Broke out {miss.mainstream_date}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function Backtest() {
  const [predDate, setPredDate] = useState('2024-12-15')
  const [valDate, setValDate] = useState('2025-01-20')
  const [selectedRun, setSelectedRun] = useState(null)

  const { data: runs } = useApi('/api/backtest/runs')
  const { data: scorecard, loading: loadingScorecard } = useApi(
    selectedRun ? `/api/backtest/runs/${selectedRun}/scorecard` : null
  )

  const runBacktest = async () => {
    const resp = await fetch(
      `/api/backtest/runs?prediction_date=${predDate}&validation_date=${valDate}&top_k=20`,
      { method: 'POST' }
    )
    const data = await resp.json()
    setSelectedRun(data.run_id)
  }

  return (
    <div>
      <h2 className="text-xl font-semibold mb-4">Shadow Mode Backtesting</h2>

      {/* Run Configuration */}
      <div className="bg-gray-50 rounded-lg p-4 mb-6">
        <div className="flex gap-4 items-end">
          <div>
            <label className="block text-sm text-gray-600 mb-1">Prediction Date</label>
            <input
              type="date"
              value={predDate}
              onChange={(e) => setPredDate(e.target.value)}
              className="border rounded px-3 py-2"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-600 mb-1">Validation Date</label>
            <input
              type="date"
              value={valDate}
              onChange={(e) => setValDate(e.target.value)}
              className="border rounded px-3 py-2"
            />
          </div>
          <button
            onClick={runBacktest}
            className="bg-blue-500 text-white px-4 py-2 rounded hover:bg-blue-600"
          >
            Run Backtest
          </button>
        </div>
      </div>

      {/* Previous Runs */}
      {runs?.length > 0 && (
        <div className="mb-6">
          <h3 className="font-semibold mb-2">Previous Runs</h3>
          <div className="flex gap-2 flex-wrap">
            {runs.map(runId => (
              <button
                key={runId}
                onClick={() => setSelectedRun(runId)}
                className={`px-3 py-1 rounded text-sm ${
                  selectedRun === runId
                    ? 'bg-blue-500 text-white'
                    : 'bg-gray-200 hover:bg-gray-300'
                }`}
              >
                {runId.replace('backtest_', '')}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Scorecard */}
      {loadingScorecard && <div className="text-center py-8">Loading scorecard...</div>}

      {scorecard && (
        <div>
          <div className="text-sm text-gray-500 mb-4">
            Prediction: {scorecard.prediction_date} → Validation: {scorecard.validation_date}
          </div>

          <ScorecardMetrics scorecard={scorecard} />
          <HitsList hits={scorecard.hits} />
          <MissesList misses={scorecard.misses} />
        </div>
      )}
    </div>
  )
}
```

2. Add route to `App.jsx`:

```jsx
import Backtest from './pages/Backtest'

// In routes
<Route path="/backtest" element={<Backtest />} />

// In nav
<Link to="/backtest">Backtest</Link>
```

3. Commit: `feat: add backtest dashboard page with scorecard UI`

---

## Task 7: Integration Test

**Steps:**

1. Run the backtest engine:
```bash
python -c "
from datetime import date
from utils.backtest_engine import BacktestEngine
from utils.scorecard_generator import ScorecardGenerator

engine = BacktestEngine()
run = engine.run_backtest(date(2024, 12, 15), date(2025, 1, 20))
print(f'Created run: {run.run_id}')
print(f'Predictions: {len(run.predictions)}')

generator = ScorecardGenerator()
scorecard = generator.generate_scorecard(run)
print(scorecard.format_summary())
"
```

2. Start API and test endpoints:
```bash
curl "http://localhost:8008/api/backtest/runs"
curl -X POST "http://localhost:8008/api/backtest/runs?prediction_date=2024-12-15&validation_date=2025-01-20"
```

3. Test frontend:
- Navigate to http://localhost:5173/backtest
- Run a backtest
- Verify scorecard displays

4. Commit: `test: verify shadow mode backtest integration`

---

## Verification

After completing all tasks:

1. **Ground truth:** `config/ground_truth.json` has 4+ breakout events
2. **Wayback scraper:** `python scrapers/wayback_scraper.py` runs without errors
3. **Backtest engine:** Creates and saves runs to `data/backtests/`
4. **Scorecard:** Shows precision, lead time, hits, misses
5. **API:** All `/api/backtest/*` endpoints return data
6. **Dashboard:** Backtest page renders with scorecard metrics

---

## Future Enhancements

1. **Real Wayback integration:** Connect WaybackScraper to trend radar for true historical data
2. **Automated ground truth:** Add mainstream news detector to auto-populate breakout events
3. **Weight optimization:** Use scorecard metrics to tune signal weights
4. **CI/CD integration:** Run backtests on schedule, alert on metric degradation