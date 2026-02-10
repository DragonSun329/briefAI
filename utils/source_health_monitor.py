"""
Source Health Monitor

Tracks the health and reliability of news sources:
- Last successful scrape time
- Success/failure rates
- Article freshness
- Dynamic credibility adjustment

Use this to:
1. Detect dead/stale sources
2. Adjust credibility scores dynamically
3. Prioritize healthy sources
4. Generate source health reports
"""

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from loguru import logger


@dataclass
class SourceHealth:
    """Health status for a single source."""
    source_id: str
    source_name: str
    last_success: Optional[str] = None
    last_failure: Optional[str] = None
    last_article_date: Optional[str] = None
    success_count_7d: int = 0
    failure_count_7d: int = 0
    article_count_7d: int = 0
    avg_articles_per_scrape: float = 0.0
    health_score: float = 1.0  # 0.0 to 1.0
    status: str = "unknown"  # healthy, degraded, stale, dead
    notes: str = ""


class SourceHealthMonitor:
    """
    Monitors and tracks source health over time.
    
    Health factors:
    - Recency: When was the last successful scrape?
    - Reliability: Success rate over last 7 days
    - Freshness: How recent are the articles?
    - Volume: Is the source producing expected content?
    """

    def __init__(self, db_path: Optional[Path] = None):
        """
        Initialize the health monitor.
        
        Args:
            db_path: Path to SQLite database (default: data/source_health.db)
        """
        self.db_path = db_path or Path(__file__).parent.parent / "data" / "source_health.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        
    def _init_db(self):
        """Initialize the SQLite database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS scrape_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id TEXT NOT NULL,
                    source_name TEXT,
                    timestamp TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    article_count INTEGER DEFAULT 0,
                    newest_article_date TEXT,
                    error_message TEXT,
                    duration_seconds REAL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_source_timestamp 
                ON scrape_events(source_id, timestamp)
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS source_config_cache (
                    source_id TEXT PRIMARY KEY,
                    source_name TEXT,
                    base_credibility INTEGER,
                    source_type TEXT,
                    last_updated TEXT
                )
            """)
            conn.commit()
            
    def record_scrape(
        self,
        source_id: str,
        source_name: str,
        success: bool,
        article_count: int = 0,
        newest_article_date: Optional[str] = None,
        error_message: Optional[str] = None,
        duration_seconds: Optional[float] = None
    ):
        """
        Record a scrape attempt.
        
        Args:
            source_id: Source identifier
            source_name: Human-readable source name
            success: Whether the scrape succeeded
            article_count: Number of articles retrieved
            newest_article_date: ISO date of newest article
            error_message: Error message if failed
            duration_seconds: How long the scrape took
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO scrape_events 
                (source_id, source_name, timestamp, success, article_count, 
                 newest_article_date, error_message, duration_seconds)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                source_id,
                source_name,
                datetime.now().isoformat(),
                1 if success else 0,
                article_count,
                newest_article_date,
                error_message,
                duration_seconds
            ))
            conn.commit()
            
    def get_source_health(self, source_id: str) -> SourceHealth:
        """
        Get health status for a single source.
        
        Args:
            source_id: Source identifier
            
        Returns:
            SourceHealth object with current status
        """
        cutoff = (datetime.now() - timedelta(days=7)).isoformat()
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            # Get recent events
            events = conn.execute("""
                SELECT * FROM scrape_events 
                WHERE source_id = ? AND timestamp > ?
                ORDER BY timestamp DESC
            """, (source_id, cutoff)).fetchall()
            
            if not events:
                return SourceHealth(
                    source_id=source_id,
                    source_name=source_id,
                    status="unknown",
                    notes="No scrape history"
                )
            
            # Calculate metrics
            source_name = events[0]['source_name'] or source_id
            successes = [e for e in events if e['success']]
            failures = [e for e in events if not e['success']]
            
            last_success = successes[0]['timestamp'] if successes else None
            last_failure = failures[0]['timestamp'] if failures else None
            
            # Get newest article date from successful scrapes
            newest_dates = [e['newest_article_date'] for e in successes if e['newest_article_date']]
            last_article_date = max(newest_dates) if newest_dates else None
            
            # Calculate averages
            total_articles = sum(e['article_count'] for e in successes)
            avg_articles = total_articles / len(successes) if successes else 0
            
            # Calculate health score
            health_score, status, notes = self._calculate_health(
                success_count=len(successes),
                failure_count=len(failures),
                last_success=last_success,
                last_article_date=last_article_date,
                avg_articles=avg_articles
            )
            
            return SourceHealth(
                source_id=source_id,
                source_name=source_name,
                last_success=last_success,
                last_failure=last_failure,
                last_article_date=last_article_date,
                success_count_7d=len(successes),
                failure_count_7d=len(failures),
                article_count_7d=total_articles,
                avg_articles_per_scrape=round(avg_articles, 1),
                health_score=health_score,
                status=status,
                notes=notes
            )
            
    def _calculate_health(
        self,
        success_count: int,
        failure_count: int,
        last_success: Optional[str],
        last_article_date: Optional[str],
        avg_articles: float
    ) -> Tuple[float, str, str]:
        """
        Calculate health score and status.
        
        Returns:
            Tuple of (health_score, status, notes)
        """
        score = 1.0
        issues = []
        
        total_attempts = success_count + failure_count
        
        # Factor 1: Success rate (weight: 0.3)
        if total_attempts > 0:
            success_rate = success_count / total_attempts
            score *= (0.7 + 0.3 * success_rate)
            if success_rate < 0.5:
                issues.append(f"Low success rate: {success_rate:.0%}")
        
        # Factor 2: Recency of last success (weight: 0.3)
        if last_success:
            last_success_dt = datetime.fromisoformat(last_success)
            hours_since = (datetime.now() - last_success_dt).total_seconds() / 3600
            
            if hours_since > 168:  # > 7 days
                score *= 0.3
                issues.append(f"No success in {hours_since/24:.0f} days")
            elif hours_since > 72:  # > 3 days
                score *= 0.6
                issues.append(f"No success in {hours_since/24:.0f} days")
            elif hours_since > 48:  # > 2 days
                score *= 0.8
        else:
            score *= 0.5
            issues.append("No successful scrapes recorded")
        
        # Factor 3: Article freshness (weight: 0.2)
        if last_article_date:
            try:
                last_article_dt = datetime.fromisoformat(last_article_date.replace('Z', '+00:00'))
                days_since = (datetime.now() - last_article_dt.replace(tzinfo=None)).days
                
                if days_since > 30:
                    score *= 0.5
                    issues.append(f"Stale content: {days_since} days old")
                elif days_since > 14:
                    score *= 0.7
                    issues.append(f"Content aging: {days_since} days old")
                elif days_since > 7:
                    score *= 0.9
            except ValueError:
                pass
        
        # Factor 4: Volume (weight: 0.2)
        if avg_articles < 1 and success_count > 2:
            score *= 0.8
            issues.append("Low article volume")
        
        # Determine status
        if score >= 0.8:
            status = "healthy"
        elif score >= 0.5:
            status = "degraded"
        elif score >= 0.2:
            status = "stale"
        else:
            status = "dead"
            
        notes = "; ".join(issues) if issues else "Operating normally"
        
        return round(score, 2), status, notes
    
    def get_all_health(self) -> List[SourceHealth]:
        """Get health status for all known sources."""
        with sqlite3.connect(self.db_path) as conn:
            source_ids = conn.execute("""
                SELECT DISTINCT source_id FROM scrape_events
            """).fetchall()
            
        return [self.get_source_health(row[0]) for row in source_ids]
    
    def get_credibility_adjustment(self, source_id: str, base_score: int) -> float:
        """
        Get adjusted credibility score based on health.
        
        Args:
            source_id: Source identifier
            base_score: Base credibility score from config (1-10)
            
        Returns:
            Adjusted score (can be lower than base, never higher)
        """
        health = self.get_source_health(source_id)
        
        # Health score ranges from 0 to 1, so adjusted score = base * health
        adjusted = base_score * health.health_score
        
        # Never go below 1
        return max(1.0, round(adjusted, 1))
    
    def get_healthy_sources(self, min_score: float = 0.5) -> List[str]:
        """Get list of source IDs with health score above threshold."""
        all_health = self.get_all_health()
        return [h.source_id for h in all_health if h.health_score >= min_score]
    
    def get_problem_sources(self, max_score: float = 0.5) -> List[SourceHealth]:
        """Get sources that need attention."""
        all_health = self.get_all_health()
        return [h for h in all_health if h.health_score < max_score]
    
    def generate_report(self) -> Dict[str, Any]:
        """Generate a health report for all sources."""
        all_health = self.get_all_health()
        
        if not all_health:
            return {
                "generated_at": datetime.now().isoformat(),
                "total_sources": 0,
                "summary": "No sources tracked yet"
            }
        
        # Group by status
        by_status = {}
        for h in all_health:
            by_status.setdefault(h.status, []).append(h)
        
        # Calculate stats
        avg_health = sum(h.health_score for h in all_health) / len(all_health)
        total_articles = sum(h.article_count_7d for h in all_health)
        
        return {
            "generated_at": datetime.now().isoformat(),
            "total_sources": len(all_health),
            "average_health_score": round(avg_health, 2),
            "total_articles_7d": total_articles,
            "by_status": {
                status: {
                    "count": len(sources),
                    "sources": [s.source_id for s in sources]
                }
                for status, sources in by_status.items()
            },
            "problem_sources": [
                asdict(h) for h in all_health if h.status in ("stale", "dead")
            ],
            "top_performers": [
                asdict(h) for h in sorted(all_health, key=lambda x: -x.article_count_7d)[:5]
            ]
        }
    
    def cleanup_old_events(self, days: int = 30):
        """Remove scrape events older than specified days."""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        
        with sqlite3.connect(self.db_path) as conn:
            result = conn.execute("""
                DELETE FROM scrape_events WHERE timestamp < ?
            """, (cutoff,))
            conn.commit()
            logger.info(f"Cleaned up {result.rowcount} old scrape events")


# Integration helper for web_scraper.py
class HealthAwareWebScraper:
    """
    Wrapper that adds health monitoring to WebScraper.
    
    Usage:
        from utils.source_health_monitor import HealthAwareWebScraper
        
        scraper = HealthAwareWebScraper(sources_config="config/sources.json")
        articles = scraper.scrape_all(days_back=7)
        
        # Get health report
        report = scraper.health_monitor.generate_report()
    """
    
    def __init__(self, **kwargs):
        from modules.web_scraper import WebScraper
        self.scraper = WebScraper(**kwargs)
        self.health_monitor = SourceHealthMonitor()
        
    def scrape_all(self, **kwargs) -> List[Dict[str, Any]]:
        """Scrape all sources with health tracking."""
        import time
        
        all_articles = []
        
        for source in self.scraper.sources:
            source_id = source['id']
            source_name = source['name']
            start_time = time.time()
            
            try:
                # Scrape single source
                articles = self.scraper._scrape_single_source(
                    source,
                    cutoff_date=kwargs.get('cutoff_date', datetime.now() - timedelta(days=7)),
                    use_cache=kwargs.get('use_cache', True),
                    query_plan=kwargs.get('query_plan')
                )
                
                duration = time.time() - start_time
                
                # Find newest article date
                newest_date = None
                if articles:
                    dates = [a.get('published_date') for a in articles if a.get('published_date')]
                    if dates:
                        newest_date = max(dates)
                
                # Record success
                self.health_monitor.record_scrape(
                    source_id=source_id,
                    source_name=source_name,
                    success=True,
                    article_count=len(articles),
                    newest_article_date=newest_date,
                    duration_seconds=duration
                )
                
                all_articles.extend(articles)
                
            except Exception as e:
                duration = time.time() - start_time
                
                # Record failure
                self.health_monitor.record_scrape(
                    source_id=source_id,
                    source_name=source_name,
                    success=False,
                    error_message=str(e),
                    duration_seconds=duration
                )
                
                logger.warning(f"Failed to scrape {source_name}: {e}")
        
        return all_articles
    
    def get_adjusted_credibility(self, source_id: str, base_score: int) -> float:
        """Get health-adjusted credibility score."""
        return self.health_monitor.get_credibility_adjustment(source_id, base_score)


def main():
    """CLI for health monitoring."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Source Health Monitor")
    parser.add_argument("--report", action="store_true", help="Generate health report")
    parser.add_argument("--problems", action="store_true", help="Show problem sources")
    parser.add_argument("--cleanup", type=int, help="Cleanup events older than N days")
    parser.add_argument("--source", type=str, help="Check specific source")
    
    args = parser.parse_args()
    monitor = SourceHealthMonitor()
    
    if args.cleanup:
        monitor.cleanup_old_events(args.cleanup)
        print(f"Cleaned up events older than {args.cleanup} days")
        
    elif args.source:
        health = monitor.get_source_health(args.source)
        print(json.dumps(asdict(health), indent=2))
        
    elif args.problems:
        problems = monitor.get_problem_sources()
        if problems:
            print(f"Found {len(problems)} problem sources:\n")
            for p in problems:
                print(f"  [{p.status.upper()}] {p.source_name}")
                print(f"    Health: {p.health_score:.0%} | {p.notes}")
                print()
        else:
            print("All sources healthy!")
            
    else:
        report = monitor.generate_report()
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
