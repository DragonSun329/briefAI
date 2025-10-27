"""
Report Archiver Module

Handles archiving of daily reports after weekly finalization.
Moves previous week's daily reports to archive folder while keeping weekly reports.
"""

import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any
from loguru import logger
from dotenv import load_dotenv
import shutil
import json

load_dotenv()


class ReportArchiver:
    """Manages archiving of daily reports"""

    def __init__(self):
        """Initialize archiver with configured paths"""
        self.reports_dir = Path(os.getenv('REPORT_OUTPUT_DIR', './data/reports'))
        self.archive_dir = Path(os.getenv('ARCHIVE_PATH', './data/reports/archive'))

        # Create archive directory if it doesn't exist
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Report archiver initialized. Archive path: {self.archive_dir}")

    def archive_week_daily_reports(self, week_id: str = None) -> Dict[str, Any]:
        """
        Archive all daily reports from the previous week

        Args:
            week_id: Week ID (e.g., 'week_2025_43'). If None, uses previous week.

        Returns:
            Dictionary with archived file count and details
        """
        logger.info(f"Starting daily report archiving for week: {week_id}")

        # If no week_id provided, calculate previous week
        if not week_id:
            from utils.weekly_utils import WeeklyUtils
            today = datetime.now()
            # Get current week
            current_week_id = WeeklyUtils.get_current_week_id()
            # Go back 7 days to get previous week
            previous_date = today - timedelta(days=7)
            week_id = WeeklyUtils.get_week_id(previous_date)

        logger.info(f"Archiving daily reports for week: {week_id}")

        # Find all daily reports from this week
        archived_files = self._find_daily_reports_for_week(week_id)

        if not archived_files:
            logger.warning(f"No daily reports found for week {week_id}")
            return {
                'week_id': week_id,
                'archived_count': 0,
                'failed_count': 0,
                'archived_files': [],
                'status': 'no_reports_found'
            }

        # Archive each file
        archived_list = []
        failed_count = 0

        for original_file in archived_files:
            try:
                archived_path = self._archive_file(original_file, week_id)
                archived_list.append({
                    'original': str(original_file),
                    'archived': str(archived_path)
                })
                logger.info(f"Archived: {original_file.name} → {archived_path.name}")
            except Exception as e:
                logger.error(f"Failed to archive {original_file.name}: {e}")
                failed_count += 1

        logger.info(f"Archive complete: {len(archived_list)} files archived, {failed_count} failed")

        return {
            'week_id': week_id,
            'archived_count': len(archived_list),
            'failed_count': failed_count,
            'archived_files': archived_list,
            'status': 'success' if failed_count == 0 else 'partial_success'
        }

    def _find_daily_reports_for_week(self, week_id: str) -> List[Path]:
        """
        Find all daily reports from a specific week

        Daily report format: ai_briefing_YYYYMMDD.md
        Need to find reports from the 7 days of the week

        Args:
            week_id: Week ID (e.g., 'week_2025_43')

        Returns:
            List of Path objects for daily reports
        """
        from utils.weekly_utils import WeeklyUtils

        # Parse week_id to get week start date
        parts = week_id.split('_')
        year = int(parts[1])
        week_num = int(parts[2])

        # Calculate dates for the week (Monday to Sunday)
        # ISO week starts on Monday
        jan_1 = datetime(year, 1, 1)
        week_start = jan_1 + timedelta(weeks=week_num - 1, days=-jan_1.weekday())

        daily_reports = []

        # Check each day of the week
        for day_offset in range(7):
            report_date = week_start + timedelta(days=day_offset)
            report_filename = f"ai_briefing_{report_date.strftime('%Y%m%d')}.md"
            report_path = self.reports_dir / report_filename

            if report_path.exists():
                daily_reports.append(report_path)
                logger.debug(f"Found daily report: {report_filename}")

        logger.info(f"Found {len(daily_reports)} daily reports for week {week_id}")
        return daily_reports

    def _archive_file(self, original_file: Path, week_id: str) -> Path:
        """
        Archive a single daily report file

        Renames file to include week ID: archive_week_2025_43_daily_20251025.md

        Args:
            original_file: Path to the original file
            week_id: Week ID for naming

        Returns:
            Path to archived file
        """
        # Extract date from filename (ai_briefing_YYYYMMDD.md)
        filename_parts = original_file.stem.split('_')  # ai_briefing_20251025
        date_str = filename_parts[-1]  # 20251025

        # Create new filename with week ID
        archived_filename = f"archive_{week_id}_daily_{date_str}.md"
        archived_path = self.archive_dir / archived_filename

        # Move file to archive
        shutil.move(str(original_file), str(archived_path))

        return archived_path

    def list_archived_reports(self, week_id: str = None) -> List[Dict[str, Any]]:
        """
        List all archived reports, optionally filtered by week

        Args:
            week_id: Optional week ID to filter (e.g., 'week_2025_43')

        Returns:
            List of archived report metadata
        """
        archived_files = []

        for file_path in self.archive_dir.glob('*.md'):
            file_info = {
                'filename': file_path.name,
                'size': file_path.stat().st_size,
                'created': datetime.fromtimestamp(file_path.stat().st_ctime).isoformat(),
                'path': str(file_path)
            }

            # If week_id filter provided, check if it matches
            if week_id and week_id not in file_path.name:
                continue

            archived_files.append(file_info)

        # Sort by date (newest first)
        archived_files.sort(key=lambda x: x['created'], reverse=True)

        logger.info(f"Found {len(archived_files)} archived reports")
        return archived_files

    def get_archive_stats(self) -> Dict[str, Any]:
        """
        Get statistics about archived reports

        Returns:
            Dictionary with archive statistics
        """
        archived_files = list(self.archive_dir.glob('*.md'))

        if not archived_files:
            return {
                'total_files': 0,
                'total_size_bytes': 0,
                'oldest_file': None,
                'newest_file': None,
                'weeks_covered': 0
            }

        # Calculate statistics
        total_size = sum(f.stat().st_size for f in archived_files)
        creation_times = [datetime.fromtimestamp(f.stat().st_ctime) for f in archived_files]

        # Count unique weeks
        weeks = set()
        for f in archived_files:
            # Extract week_id from filename (archive_week_2025_43_daily_20251025.md)
            parts = f.name.split('_')
            if len(parts) >= 3:
                week_id = f"week_{parts[1]}_{parts[2]}"
                weeks.add(week_id)

        return {
            'total_files': len(archived_files),
            'total_size_bytes': total_size,
            'total_size_mb': round(total_size / (1024 * 1024), 2),
            'oldest_file': min(creation_times).isoformat(),
            'newest_file': max(creation_times).isoformat(),
            'weeks_covered': len(weeks),
            'week_ids': sorted(list(weeks))
        }

    def restore_report(self, filename: str) -> bool:
        """
        Restore an archived report back to the main reports directory

        Args:
            filename: Name of archived file to restore

        Returns:
            True if successful, False otherwise
        """
        archived_path = self.archive_dir / filename

        if not archived_path.exists():
            logger.error(f"Archived file not found: {filename}")
            return False

        # Extract original filename from archived name
        # archive_week_2025_43_daily_20251025.md → ai_briefing_20251025.md
        parts = filename.replace('archive_', '').replace('.md', '').split('_')
        if len(parts) >= 4:
            date_str = parts[-1]
            original_filename = f"ai_briefing_{date_str}.md"
        else:
            original_filename = filename

        restored_path = self.reports_dir / original_filename

        try:
            shutil.move(str(archived_path), str(restored_path))
            logger.info(f"Restored: {filename} → {original_filename}")
            return True
        except Exception as e:
            logger.error(f"Failed to restore {filename}: {e}")
            return False

    def cleanup_old_archives(self, days_to_keep: int = 365) -> Dict[str, Any]:
        """
        Clean up very old archived reports (older than specified days)

        Args:
            days_to_keep: Number of days of archives to keep (default: 365 = 1 year)

        Returns:
            Dictionary with cleanup statistics
        """
        cutoff_date = datetime.now() - timedelta(days=days_to_keep)
        removed_count = 0
        removed_size = 0

        for file_path in self.archive_dir.glob('*.md'):
            file_date = datetime.fromtimestamp(file_path.stat().st_ctime)

            if file_date < cutoff_date:
                try:
                    file_size = file_path.stat().st_size
                    file_path.unlink()
                    removed_count += 1
                    removed_size += file_size
                    logger.info(f"Deleted old archive: {file_path.name}")
                except Exception as e:
                    logger.error(f"Failed to delete {file_path.name}: {e}")

        logger.info(f"Cleanup complete: {removed_count} files deleted, {removed_size / 1024:.1f} KB freed")

        return {
            'removed_count': removed_count,
            'removed_size_bytes': removed_size,
            'removed_size_mb': round(removed_size / (1024 * 1024), 2)
        }


if __name__ == "__main__":
    # Test archiver
    archiver = ReportArchiver()

    # Test list archived reports
    archived = archiver.list_archived_reports()
    print(f"Archived reports: {len(archived)}")
    for report in archived[:3]:
        print(f"  - {report['filename']}")

    # Test get stats
    stats = archiver.get_archive_stats()
    print(f"\nArchive statistics:")
    print(f"  Total files: {stats['total_files']}")
    print(f"  Total size: {stats['total_size_mb']} MB")
    print(f"  Weeks covered: {stats['weeks_covered']}")
