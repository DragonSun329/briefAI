"""
Weekly Utilities - Week ID generation, day detection, and weekly helpers

Handles week identification, day-of-week tracking for daily collection mode,
and scheduling helpers for the weekly article collection system.
"""

from datetime import datetime, timedelta
from typing import Tuple, Optional, List, Any
from loguru import logger


class WeeklyUtils:
    """Utilities for managing weekly article collection"""

    @staticmethod
    def get_current_week_id() -> str:
        """
        Get the current week ID in format: 'week_YYYY_WW'

        Returns:
            Week ID (e.g., 'week_2025_43' for week 43 of 2025)
        """
        now = datetime.now()
        year = now.isocalendar()[0]
        week = now.isocalendar()[1]
        return f"week_{year}_{week:02d}"

    @staticmethod
    def get_week_id_for_date(date: datetime) -> str:
        """
        Get the week ID for a specific date

        Args:
            date: Date to get week ID for

        Returns:
            Week ID (e.g., 'week_2025_43')
        """
        year = date.isocalendar()[0]
        week = date.isocalendar()[1]
        return f"week_{year}_{week:02d}"

    @staticmethod
    def get_current_day_of_week() -> int:
        """
        Get current day of week (1-7, Monday-Sunday)

        Returns:
            Day number (1=Monday, 7=Sunday)
        """
        return datetime.now().isoweekday()

    @staticmethod
    def get_day_name(day: int) -> str:
        """
        Get name of day from day number

        Args:
            day: Day number (1-7, Monday-Sunday)

        Returns:
            Day name in English
        """
        day_names = {
            1: "Monday",
            2: "Tuesday",
            3: "Wednesday",
            4: "Thursday",
            5: "Friday",
            6: "Saturday",
            7: "Sunday"
        }
        return day_names.get(day, "Unknown")

    @staticmethod
    def get_week_start_end() -> Tuple[datetime, datetime]:
        """
        Get start and end date of current week (Monday-Sunday)

        Returns:
            Tuple of (week_start, week_end)
        """
        now = datetime.now()
        # Monday is day 0 in weekday()
        days_since_monday = now.weekday()
        week_start = now - timedelta(days=days_since_monday)
        week_end = week_start + timedelta(days=6)

        # Reset to start of day for week_start
        week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
        # Set to end of day for week_end
        week_end = week_end.replace(hour=23, minute=59, second=59, microsecond=999999)

        return week_start, week_end

    @staticmethod
    def is_collection_day() -> bool:
        """
        Check if today is a collection day (Monday-Friday, days 1-5)

        Returns:
            True if today is Mon-Fri, False if weekend
        """
        day = datetime.now().isoweekday()
        return day <= 5

    @staticmethod
    def is_finalization_day() -> bool:
        """
        Check if today is finalization day (Friday evening or Saturday morning)

        For simplicity, finalization happens on Friday (day 5) during evening hours
        or can be triggered manually on Saturday.

        Returns:
            True if today is Friday or Saturday (days 5-6)
        """
        day = datetime.now().isoweekday()
        return day in [5, 6]

    @staticmethod
    def days_until_finalization() -> int:
        """
        Get number of days until finalization (end of week)

        Returns:
            Number of days until Friday end of day (0 if today is Friday/Saturday)
        """
        day = datetime.now().isoweekday()
        if day >= 5:  # Friday or later
            return 0
        return 5 - day  # Days until Friday

    @staticmethod
    def format_week_range(week_id: str) -> str:
        """
        Format week ID into readable date range

        Args:
            week_id: Week ID (e.g., 'week_2025_43')

        Returns:
            Formatted string (e.g., 'Oct 20 - Oct 26, 2025')
        """
        try:
            parts = week_id.split('_')
            year = int(parts[1])
            week = int(parts[2])

            # Get Monday of that week
            jan_4 = datetime(year, 1, 4)
            week_start = jan_4 - timedelta(days=jan_4.weekday())
            week_start = week_start + timedelta(weeks=week - 1)
            week_end = week_start + timedelta(days=6)

            return f"{week_start.strftime('%b %d')} - {week_end.strftime('%b %d, %Y')}"

        except Exception as e:
            logger.warning(f"Could not format week range for {week_id}: {e}")
            return week_id

    @staticmethod
    def get_collection_batch_id(week_id: str, day: Optional[int] = None) -> str:
        """
        Generate a batch ID for daily collection within a week

        Args:
            week_id: Week ID (e.g., 'week_2025_43')
            day: Day of week (optional, defaults to today)

        Returns:
            Batch ID (e.g., 'collection_week_2025_43_day_5')
        """
        if day is None:
            day = datetime.now().isoweekday()

        return f"collection_{week_id}_day_{day}"

    @staticmethod
    def get_finalization_batch_id(week_id: str) -> str:
        """
        Generate batch ID for weekly finalization

        Args:
            week_id: Week ID (e.g., 'week_2025_43')

        Returns:
            Batch ID (e.g., 'finalization_week_2025_43')
        """
        return f"finalization_{week_id}"

    @staticmethod
    def should_trigger_finalization() -> bool:
        """
        Determine if finalization should be triggered

        Finalization should trigger:
        - Manually via --finalize flag
        - Automatically on Friday evening (6 PM+)
        - Automatically on Saturday morning

        Returns:
            True if finalization should run
        """
        now = datetime.now()
        day = now.isoweekday()
        hour = now.hour

        # Friday at 6 PM or later
        if day == 5 and hour >= 18:
            return True

        # Saturday (any time)
        if day == 6:
            return True

        return False

    @staticmethod
    def log_collection_status(week_id: str, day: int, total_articles: int, tier2_count: int) -> None:
        """
        Log collection status for the day

        Args:
            week_id: Week ID
            day: Day of week
            total_articles: Total articles scraped
            tier2_count: Articles that passed Tier 2
        """
        day_name = WeeklyUtils.get_day_name(day)
        week_range = WeeklyUtils.format_week_range(week_id)

        logger.info(
            f"[COLLECTION {week_id}] {day_name}: "
            f"Scraped {total_articles} → Tier 2: {tier2_count} articles passed"
        )
        logger.info(f"[WEEK RANGE] {week_range}")

    @staticmethod
    def log_finalization_status(
        week_id: str,
        total_collected: int,
        tier3_count: int,
        final_count: int
    ) -> None:
        """
        Log finalization status

        Args:
            week_id: Week ID
            total_collected: Total articles collected during week
            tier3_count: Articles that passed Tier 3 full evaluation
            final_count: Final articles in report (usually 10-15)
        """
        week_range = WeeklyUtils.format_week_range(week_id)

        logger.info(
            f"[FINALIZATION {week_id}] Week {week_range}: "
            f"Collected {total_collected} → Tier 3: {tier3_count} → "
            f"Final Report: {final_count} articles"
        )

    # Early Report Methods

    @staticmethod
    def get_week_id_for_7day_window(target_date: Optional[datetime] = None) -> str:
        """
        Get week ID for 7-day window ending today (for early reports)

        Useful for generating reports that span Monday-Sunday regardless of current day.

        Args:
            target_date: Optional date to use instead of today

        Returns:
            Week ID (e.g., 'week_2025_43')
        """
        if target_date is None:
            target_date = datetime.now()

        # For early reports, use the week of the current date
        # This ensures Monday-Sunday coverage
        year = target_date.isocalendar()[0]
        week = target_date.isocalendar()[1]
        return f"week_{year}_{week:02d}"

    @staticmethod
    def get_collection_day_range_for_early_report() -> Tuple[int, int]:
        """
        Get the day range that should be covered for early 7-day report

        Returns:
            Tuple of (start_day, end_day) where:
            - start_day: 1-7 (1=Monday of current week)
            - end_day: 1-7 (current or previous week's Sunday)
        """
        today = datetime.now().isoweekday()  # 1=Monday, 7=Sunday

        # For early reports, we want Monday-Sunday coverage
        return (1, 7)  # Always cover full week

    @staticmethod
    def detect_missing_collection_days(
        week_id: str,
        checkpoint_manager: Any = None,  # Will import at runtime to avoid circular imports
        min_articles_per_day: int = 5
    ) -> Tuple[List[int], List[int], int]:
        """
        Detect which days have missing or low article coverage

        Args:
            week_id: Week ID to check
            checkpoint_manager: CheckpointManager instance to check articles
            min_articles_per_day: Minimum articles expected per day (default: 5)

        Returns:
            Tuple of (missing_days, low_days, total_articles)
            - missing_days: Days with 0 articles (should backfill)
            - low_days: Days with 1-4 articles (can backfill optionally)
            - total_articles: Total articles in checkpoint for this week
        """
        if checkpoint_manager is None:
            return [], [], 0

        # Load checkpoint for this week
        if not checkpoint_manager.load_weekly_checkpoint(week_id):
            logger.warning(f"No checkpoint found for {week_id}")
            return list(range(1, 6)), [], 0  # Missing Mon-Fri if no checkpoint

        articles = checkpoint_manager.processed_articles
        total_articles = len(articles)

        # Count articles by collection day
        articles_per_day = {day: 0 for day in range(1, 8)}
        for article_id, article_data in articles.items():
            day = article_data.get('collection_day', 0)
            if 1 <= day <= 7:
                articles_per_day[day] += 1

        # Find missing and low days
        missing_days = [day for day in range(1, 6) if articles_per_day[day] == 0]
        low_days = [day for day in range(1, 6) if 0 < articles_per_day[day] < min_articles_per_day]

        logger.info(
            f"[EARLY REPORT CHECK] Week {week_id}: "
            f"Total articles: {total_articles}, "
            f"Missing days: {missing_days}, "
            f"Low days: {low_days}"
        )

        return missing_days, low_days, total_articles

    @staticmethod
    def log_early_report_backfill(
        week_id: str,
        missing_days: List[int],
        low_days: List[int],
        backfill_enabled: bool
    ) -> None:
        """
        Log early report backfill status

        Args:
            week_id: Week ID
            missing_days: Days with 0 articles
            low_days: Days with low article count
            backfill_enabled: Whether backfill is enabled
        """
        day_names = [WeeklyUtils.get_day_name(d) for d in missing_days]

        if backfill_enabled:
            if missing_days or low_days:
                logger.info(
                    f"[EARLY REPORT] {week_id}: "
                    f"Backfilling missing days: {', '.join(day_names)}"
                )
            else:
                logger.info(
                    f"[EARLY REPORT] {week_id}: "
                    f"All days have adequate articles, no backfill needed"
                )
        else:
            logger.info(
                f"[EARLY REPORT] {week_id}: "
                f"Backfill disabled, using only collected articles"
            )

    @staticmethod
    def log_early_report_complete(
        week_id: str,
        total_articles: int,
        final_articles: int,
        backfilled_days: List[int]
    ) -> None:
        """
        Log early report completion

        Args:
            week_id: Week ID
            total_articles: Total articles used
            final_articles: Final articles in report
            backfilled_days: Days that were backfilled
        """
        backfill_info = ""
        if backfilled_days:
            day_names = [WeeklyUtils.get_day_name(d) for d in backfilled_days]
            backfill_info = f" (backfilled: {', '.join(day_names)})"

        logger.info(
            f"[EARLY REPORT] {week_id}: "
            f"Generated report with {final_articles}/{total_articles} articles{backfill_info}"
        )
