"""
Metric Observer - Data Collection for Prediction Verification.

Part of briefAI Prediction Verification Engine.

This module executes observable queries to collect baseline and current
metric values for prediction evaluation.

Supported metrics v1:
- article_count: News database queries
- keyword_frequency: News/social mention counting
- repo_activity: GitHub scraper data
- filing_mentions: SEC scraper data
- job_postings_count: Job scraper data

No LLM calls. Deterministic data collection.
"""

import json
import sqlite3
from typing import Tuple, Optional, Dict, Any, List
from datetime import datetime, timedelta
from pathlib import Path
from abc import ABC, abstractmethod

from loguru import logger


# =============================================================================
# CONSTANTS
# =============================================================================

DEFAULT_DATA_DIR = Path(__file__).parent.parent / "data"

# Metric source mapping
METRIC_SOURCES = {
    'article_count': 'news',
    'keyword_frequency': 'news',
    'headline_mentions': 'news',
    'repo_activity': 'github',
    'repo_stars': 'github',
    'repo_forks': 'github',
    'sdk_release': 'github',
    'filing_mentions': 'sec',
    'earnings_mentions': 'sec',
    'contract_count': 'sec',
    'job_postings_count': 'jobs',
    'discussion_volume': 'social',
    'sentiment_score': 'social',
}


# =============================================================================
# ABSTRACT OBSERVER
# =============================================================================

class MetricObserver(ABC):
    """Abstract base class for metric observers."""
    
    @abstractmethod
    def observe(
        self,
        entity: str,
        metric: str,
        start_date: datetime,
        end_date: datetime,
    ) -> Optional[float]:
        """
        Observe a metric value for an entity over a time period.
        
        Args:
            entity: Entity to observe (e.g., "nvidia")
            metric: Canonical metric name
            start_date: Start of observation period
            end_date: End of observation period
        
        Returns:
            Aggregated metric value, or None if data unavailable
        """
        pass


# =============================================================================
# NEWS OBSERVER
# =============================================================================

class NewsObserver(MetricObserver):
    """
    Observer for news-based metrics.
    
    Uses the briefAI news database to count articles and mentions.
    """
    
    def __init__(self, data_dir: Path = None):
        """Initialize news observer."""
        if data_dir is None:
            data_dir = DEFAULT_DATA_DIR
        
        self.data_dir = Path(data_dir)
        self.signals_db = self.data_dir / "signals.db"
        self.news_dir = self.data_dir / "news_signals"
    
    def observe(
        self,
        entity: str,
        metric: str,
        start_date: datetime,
        end_date: datetime,
    ) -> Optional[float]:
        """Observe news-based metric."""
        try:
            # Try database first
            if self.signals_db.exists():
                return self._observe_from_db(entity, metric, start_date, end_date)
            
            # Fallback to file-based counting
            return self._observe_from_files(entity, metric, start_date, end_date)
            
        except Exception as e:
            logger.warning(f"News observation failed for {entity}/{metric}: {e}")
            return None
    
    def _observe_from_db(
        self,
        entity: str,
        metric: str,
        start_date: datetime,
        end_date: datetime,
    ) -> Optional[float]:
        """Query signals database for news metrics."""
        try:
            conn = sqlite3.connect(str(self.signals_db))
            cursor = conn.cursor()
            
            # Build query based on metric type
            entity_lower = entity.lower()
            start_str = start_date.strftime('%Y-%m-%d')
            end_str = end_date.strftime('%Y-%m-%d')
            
            if metric in ['article_count', 'headline_mentions']:
                # Count articles mentioning entity
                query = """
                    SELECT COUNT(*) FROM signal_observations
                    WHERE LOWER(content) LIKE ?
                    AND date(timestamp) BETWEEN ? AND ?
                """
                cursor.execute(query, (f'%{entity_lower}%', start_str, end_str))
                
            elif metric == 'keyword_frequency':
                # Count total mentions
                query = """
                    SELECT COUNT(*) FROM signal_observations
                    WHERE LOWER(content) LIKE ?
                    AND date(timestamp) BETWEEN ? AND ?
                """
                cursor.execute(query, (f'%{entity_lower}%', start_str, end_str))
            
            else:
                conn.close()
                return None
            
            result = cursor.fetchone()
            conn.close()
            
            return float(result[0]) if result else 0.0
            
        except Exception as e:
            logger.debug(f"DB query failed: {e}")
            return None
    
    def _observe_from_files(
        self,
        entity: str,
        metric: str,
        start_date: datetime,
        end_date: datetime,
    ) -> Optional[float]:
        """Count from news signal files."""
        if not self.news_dir.exists():
            return None
        
        count = 0
        entity_lower = entity.lower()
        
        # Iterate through date range
        current = start_date
        while current <= end_date:
            date_str = current.strftime('%Y-%m-%d')
            
            # Check for signal files
            for pattern in [f"*{date_str}*.json", f"*{date_str}*.jsonl"]:
                for file_path in self.news_dir.glob(pattern):
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read().lower()
                            count += content.count(entity_lower)
                    except Exception:
                        pass
            
            current += timedelta(days=1)
        
        return float(count) if count > 0 else 0.0


# =============================================================================
# GITHUB OBSERVER
# =============================================================================

class GitHubObserver(MetricObserver):
    """
    Observer for GitHub-based metrics.
    
    Uses scraped GitHub data to track repository activity.
    """
    
    def __init__(self, data_dir: Path = None):
        """Initialize GitHub observer."""
        if data_dir is None:
            data_dir = DEFAULT_DATA_DIR
        
        self.data_dir = Path(data_dir)
        self.package_dir = self.data_dir / "package_signals"
    
    def observe(
        self,
        entity: str,
        metric: str,
        start_date: datetime,
        end_date: datetime,
    ) -> Optional[float]:
        """Observe GitHub-based metric."""
        try:
            return self._observe_from_files(entity, metric, start_date, end_date)
        except Exception as e:
            logger.warning(f"GitHub observation failed for {entity}/{metric}: {e}")
            return None
    
    def _observe_from_files(
        self,
        entity: str,
        metric: str,
        start_date: datetime,
        end_date: datetime,
    ) -> Optional[float]:
        """Count from package signal files."""
        if not self.package_dir.exists():
            return None
        
        # Look for entity in package signals
        entity_lower = entity.lower()
        activity_count = 0
        
        for file_path in self.package_dir.glob("*.json"):
            try:
                # Check file modification date
                mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                if start_date <= mtime <= end_date:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    # Check if entity mentioned
                    content_str = json.dumps(data).lower()
                    if entity_lower in content_str:
                        activity_count += 1
                        
            except Exception:
                pass
        
        return float(activity_count) if activity_count > 0 else 0.0


# =============================================================================
# SEC OBSERVER
# =============================================================================

class SECObserver(MetricObserver):
    """
    Observer for SEC filing-based metrics.
    
    Uses scraped SEC data to track filing mentions.
    """
    
    def __init__(self, data_dir: Path = None):
        """Initialize SEC observer."""
        if data_dir is None:
            data_dir = DEFAULT_DATA_DIR
        
        self.data_dir = Path(data_dir)
        self.financial_dir = self.data_dir / "financial_signals"
        self.earnings_dir = self.data_dir / "earnings_signals"
    
    def observe(
        self,
        entity: str,
        metric: str,
        start_date: datetime,
        end_date: datetime,
    ) -> Optional[float]:
        """Observe SEC-based metric."""
        try:
            return self._observe_from_files(entity, metric, start_date, end_date)
        except Exception as e:
            logger.warning(f"SEC observation failed for {entity}/{metric}: {e}")
            return None
    
    def _observe_from_files(
        self,
        entity: str,
        metric: str,
        start_date: datetime,
        end_date: datetime,
    ) -> Optional[float]:
        """Count from financial signal files."""
        search_dirs = [self.financial_dir, self.earnings_dir]
        entity_lower = entity.lower()
        mention_count = 0
        
        for search_dir in search_dirs:
            if not search_dir.exists():
                continue
            
            for file_path in search_dir.glob("*.json"):
                try:
                    # Check file date from name or mtime
                    mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                    if start_date <= mtime <= end_date:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read().lower()
                        
                        if entity_lower in content:
                            mention_count += content.count(entity_lower)
                            
                except Exception:
                    pass
        
        return float(mention_count) if mention_count > 0 else 0.0


# =============================================================================
# JOBS OBSERVER
# =============================================================================

class JobsObserver(MetricObserver):
    """
    Observer for job posting-based metrics.
    
    Uses scraped job data to track hiring activity.
    """
    
    def __init__(self, data_dir: Path = None):
        """Initialize jobs observer."""
        if data_dir is None:
            data_dir = DEFAULT_DATA_DIR
        
        self.data_dir = Path(data_dir)
        self.jobs_dir = self.data_dir / "job_signals"
    
    def observe(
        self,
        entity: str,
        metric: str,
        start_date: datetime,
        end_date: datetime,
    ) -> Optional[float]:
        """Observe jobs-based metric."""
        try:
            return self._observe_from_files(entity, metric, start_date, end_date)
        except Exception as e:
            logger.warning(f"Jobs observation failed for {entity}/{metric}: {e}")
            return None
    
    def _observe_from_files(
        self,
        entity: str,
        metric: str,
        start_date: datetime,
        end_date: datetime,
    ) -> Optional[float]:
        """Count from job signal files."""
        if not self.jobs_dir.exists():
            return None
        
        entity_lower = entity.lower()
        job_count = 0
        
        for file_path in self.jobs_dir.glob("*.json"):
            try:
                mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                if start_date <= mtime <= end_date:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    # Look for entity in job data
                    content_str = json.dumps(data).lower()
                    if entity_lower in content_str:
                        # Try to count actual job entries
                        if isinstance(data, list):
                            job_count += len([j for j in data if entity_lower in json.dumps(j).lower()])
                        else:
                            job_count += 1
                            
            except Exception:
                pass
        
        return float(job_count) if job_count > 0 else 0.0


# =============================================================================
# SOCIAL OBSERVER
# =============================================================================

class SocialObserver(MetricObserver):
    """
    Observer for social media-based metrics.
    
    Uses scraped social data to track discussion volume.
    """
    
    def __init__(self, data_dir: Path = None):
        """Initialize social observer."""
        if data_dir is None:
            data_dir = DEFAULT_DATA_DIR
        
        self.data_dir = Path(data_dir)
        self.social_dir = self.data_dir / "social_signals"
    
    def observe(
        self,
        entity: str,
        metric: str,
        start_date: datetime,
        end_date: datetime,
    ) -> Optional[float]:
        """Observe social-based metric."""
        try:
            return self._observe_from_files(entity, metric, start_date, end_date)
        except Exception as e:
            logger.warning(f"Social observation failed for {entity}/{metric}: {e}")
            return None
    
    def _observe_from_files(
        self,
        entity: str,
        metric: str,
        start_date: datetime,
        end_date: datetime,
    ) -> Optional[float]:
        """Count from social signal files."""
        if not self.social_dir.exists():
            return None
        
        entity_lower = entity.lower()
        mention_count = 0
        
        for file_path in self.social_dir.glob("*.json"):
            try:
                mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                if start_date <= mtime <= end_date:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read().lower()
                    
                    if entity_lower in content:
                        mention_count += content.count(entity_lower)
                        
            except Exception:
                pass
        
        return float(mention_count) if mention_count > 0 else 0.0


# =============================================================================
# UNIFIED OBSERVER
# =============================================================================

class UnifiedMetricObserver:
    """
    Unified interface for all metric observations.
    
    Routes to appropriate observer based on metric type.
    """
    
    def __init__(self, data_dir: Path = None):
        """Initialize unified observer with all sub-observers."""
        if data_dir is None:
            data_dir = DEFAULT_DATA_DIR
        
        self.data_dir = Path(data_dir)
        
        self.observers = {
            'news': NewsObserver(data_dir),
            'github': GitHubObserver(data_dir),
            'sec': SECObserver(data_dir),
            'jobs': JobsObserver(data_dir),
            'social': SocialObserver(data_dir),
        }
        
        logger.debug(f"UnifiedMetricObserver initialized at {self.data_dir}")
    
    def get_observer_for_metric(self, metric: str) -> Optional[MetricObserver]:
        """Get appropriate observer for a metric."""
        source = METRIC_SOURCES.get(metric)
        if source:
            return self.observers.get(source)
        
        # Try to infer from metric name
        if 'article' in metric or 'keyword' in metric or 'headline' in metric:
            return self.observers['news']
        elif 'repo' in metric or 'github' in metric or 'sdk' in metric:
            return self.observers['github']
        elif 'filing' in metric or 'earning' in metric or 'contract' in metric:
            return self.observers['sec']
        elif 'job' in metric or 'posting' in metric:
            return self.observers['jobs']
        elif 'discussion' in metric or 'sentiment' in metric or 'social' in metric:
            return self.observers['social']
        
        return None
    
    def observe_metric(
        self,
        entity: str,
        metric: str,
        days_back: int,
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        Observe a metric for prediction evaluation.
        
        Returns baseline (start of window) and current (end of window) values.
        
        Args:
            entity: Entity to observe
            metric: Canonical metric name
            days_back: How many days back to look for baseline
        
        Returns:
            Tuple of (baseline_value, current_value)
        """
        observer = self.get_observer_for_metric(metric)
        
        if observer is None:
            logger.warning(f"No observer available for metric: {metric}")
            return None, None
        
        now = datetime.now()
        
        # Calculate baseline period (first half of window)
        baseline_end = now - timedelta(days=days_back)
        baseline_start = baseline_end - timedelta(days=days_back)
        
        # Calculate current period (recent window)
        current_start = now - timedelta(days=days_back)
        current_end = now
        
        # Get baseline value
        baseline = observer.observe(entity, metric, baseline_start, baseline_end)
        
        # Get current value
        current = observer.observe(entity, metric, current_start, current_end)
        
        logger.debug(
            f"Observed {entity}/{metric}: baseline={baseline}, current={current}"
        )
        
        return baseline, current
    
    def observe_for_prediction(
        self,
        entity: str,
        metric: str,
        window_days: int,
        created_at: datetime,
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        Observe a metric for a specific prediction.
        
        Uses the prediction's creation date and window for accurate comparison.
        
        Args:
            entity: Entity to observe
            metric: Canonical metric name
            window_days: Prediction's observation window
            created_at: When the prediction was created
        
        Returns:
            Tuple of (baseline_value, current_value)
        """
        observer = self.get_observer_for_metric(metric)
        
        if observer is None:
            logger.warning(f"No observer available for metric: {metric}")
            return None, None
        
        now = datetime.now()
        
        # Baseline: period before prediction was created
        baseline_end = created_at
        baseline_start = created_at - timedelta(days=window_days)
        
        # Current: period from creation to now (or window end)
        current_start = created_at
        current_end = min(now, created_at + timedelta(days=window_days))
        
        # Get baseline value
        baseline = observer.observe(entity, metric, baseline_start, baseline_end)
        
        # Get current value
        current = observer.observe(entity, metric, current_start, current_end)
        
        logger.debug(
            f"Observed {entity}/{metric} for prediction: baseline={baseline}, current={current}"
        )
        
        return baseline, current


# =============================================================================
# MODULE-LEVEL FUNCTION
# =============================================================================

def observe_metric(
    entity: str,
    metric: str,
    days: int,
) -> Tuple[Optional[float], Optional[float]]:
    """
    Observe a metric for prediction verification.
    
    Convenience function that creates a UnifiedMetricObserver.
    
    Args:
        entity: Entity to observe (e.g., "nvidia")
        metric: Canonical metric name (e.g., "article_count")
        days: Observation window in days
    
    Returns:
        Tuple of (baseline_value, current_value)
    """
    observer = UnifiedMetricObserver()
    return observer.observe_metric(entity, metric, days)


# =============================================================================
# TESTS
# =============================================================================

def _test_metric_source_mapping():
    """Test metric to source mapping."""
    assert METRIC_SOURCES['article_count'] == 'news'
    assert METRIC_SOURCES['repo_activity'] == 'github'
    assert METRIC_SOURCES['filing_mentions'] == 'sec'
    assert METRIC_SOURCES['job_postings_count'] == 'jobs'
    
    print("[PASS] _test_metric_source_mapping")


def _test_unified_observer_routing():
    """Test observer routing logic."""
    observer = UnifiedMetricObserver()
    
    assert observer.get_observer_for_metric('article_count') is not None
    assert observer.get_observer_for_metric('repo_activity') is not None
    assert observer.get_observer_for_metric('filing_mentions') is not None
    assert observer.get_observer_for_metric('job_postings_count') is not None
    assert observer.get_observer_for_metric('unknown_metric_xyz') is None
    
    print("[PASS] _test_unified_observer_routing")


def run_tests():
    """Run all metric observer tests."""
    print("\n=== METRIC OBSERVER TESTS ===\n")
    
    _test_metric_source_mapping()
    _test_unified_observer_routing()
    
    print("\n=== ALL TESTS PASSED ===")


if __name__ == "__main__":
    run_tests()
