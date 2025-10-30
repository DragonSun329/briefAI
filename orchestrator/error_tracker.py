"""
Error Tracker Module

Comprehensive error logging and classification system.
Tracks all errors, warnings, and issues during pipeline execution.

Features:
- Structured error logging to JSON per run
- Automatic error classification (NETWORK, LLM, PARSING, etc.)
- Severity levels (CRITICAL, WARNING, INFO)
- Error recovery suggestions
- Summary and analytics
"""

import json
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from loguru import logger


class ErrorTracker:
    """Tracks and logs all errors during pipeline execution"""

    # Error type categories
    ERROR_TYPES = {
        'NETWORK': ['timeout', 'connection_reset', 'dns_failure', 'connection_error', 'remote_end_closed'],
        'LLM': ['rate_limit', 'api_error', 'invalid_response', 'token_limit', 'provider_error'],
        'PARSING': ['invalid_json', 'missing_field', 'type_mismatch', 'parse_error'],
        'BUSINESS_LOGIC': ['threshold_not_met', 'no_articles', 'invalid_score', 'empty_result'],
        'SYSTEM': ['out_of_memory', 'disk_full', 'permission_denied', 'file_not_found']
    }

    def __init__(self, run_id: str, log_dir: str = "./data/logs"):
        """
        Initialize error tracker

        Args:
            run_id: Unique run identifier
            log_dir: Directory to save error logs
        """
        self.run_id = run_id
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self.log_file = self.log_dir / f"errors_{run_id}.json"

        # In-memory error storage
        self.errors: List[Dict[str, Any]] = []
        self.error_counter = 0

        logger.info(f"Error tracker initialized: {self.log_file}")

    def log_error(
        self,
        phase: str,
        error: Exception,
        severity: str = 'WARNING',
        context: Optional[Dict[str, Any]] = None,
        recovery_action: str = 'CONTINUE'
    ) -> str:
        """
        Log an error with full context

        Args:
            phase: Pipeline phase where error occurred
            error: The exception object
            severity: Error severity (CRITICAL, WARNING, INFO)
            context: Additional context data
            recovery_action: What action was taken (SKIP_SOURCE, FAIL_FAST, RETRY, CONTINUE)

        Returns:
            Error ID
        """
        self.error_counter += 1
        error_id = f"err_{self.error_counter:03d}"

        # Classify error
        error_type, error_subtype = self._classify_error(error)

        error_record = {
            'id': error_id,
            'timestamp': datetime.now().isoformat(),
            'phase': phase,
            'severity': severity,
            'error_type': error_type,
            'error_subtype': error_subtype,
            'message': str(error),
            'exception_class': error.__class__.__name__,
            'context': context or {},
            'traceback': traceback.format_exc() if severity == 'CRITICAL' else None,
            'recovery_action': recovery_action
        }

        self.errors.append(error_record)

        # Log to loguru
        log_message = f"[{error_id}] {phase} | {error_type}/{error_subtype}: {str(error)}"
        if severity == 'CRITICAL':
            logger.error(log_message)
        elif severity == 'WARNING':
            logger.warning(log_message)
        else:
            logger.info(log_message)

        # Save to file after each error
        self._save_to_file()

        return error_id

    def _classify_error(self, error: Exception) -> tuple[str, str]:
        """
        Classify error into type and subtype

        Args:
            error: Exception object

        Returns:
            Tuple of (error_type, error_subtype)
        """
        error_str = str(error).lower()
        exception_name = error.__class__.__name__.lower()

        # Check each category
        for category, subtypes in self.ERROR_TYPES.items():
            for subtype in subtypes:
                if subtype.replace('_', ' ') in error_str or subtype.replace('_', ' ') in exception_name:
                    return category, subtype

        # Default classification
        return 'UNKNOWN', 'unclassified'

    def get_error_summary(self) -> Dict[str, Any]:
        """
        Get summary of all errors

        Returns:
            Dict with error statistics
        """
        summary = {
            'total_errors': len(self.errors),
            'critical_errors': sum(1 for e in self.errors if e['severity'] == 'CRITICAL'),
            'warnings': sum(1 for e in self.errors if e['severity'] == 'WARNING'),
            'info': sum(1 for e in self.errors if e['severity'] == 'INFO'),
            'by_phase': {},
            'by_type': {},
            'by_severity': {}
        }

        # Count by phase
        for error in self.errors:
            phase = error['phase']
            summary['by_phase'][phase] = summary['by_phase'].get(phase, 0) + 1

        # Count by type
        for error in self.errors:
            error_type = error['error_type']
            summary['by_type'][error_type] = summary['by_type'].get(error_type, 0) + 1

        # Count by severity
        for error in self.errors:
            severity = error['severity']
            summary['by_severity'][severity] = summary['by_severity'].get(severity, 0) + 1

        return summary

    def get_errors_by_phase(self, phase_name: str) -> List[Dict[str, Any]]:
        """
        Get all errors for a specific phase

        Args:
            phase_name: Name of pipeline phase

        Returns:
            List of error records
        """
        return [e for e in self.errors if e['phase'] == phase_name]

    def get_errors_by_type(self, error_type: str) -> List[Dict[str, Any]]:
        """
        Get all errors of a specific type

        Args:
            error_type: Error type category

        Returns:
            List of error records
        """
        return [e for e in self.errors if e['error_type'] == error_type]

    def get_critical_errors(self) -> List[Dict[str, Any]]:
        """
        Get all critical errors

        Returns:
            List of critical error records
        """
        return [e for e in self.errors if e['severity'] == 'CRITICAL']

    def has_critical_errors(self) -> bool:
        """Check if any critical errors occurred"""
        return any(e['severity'] == 'CRITICAL' for e in self.errors)

    def generate_bug_report(self) -> str:
        """
        Generate human-readable bug report

        Returns:
            Markdown formatted bug report
        """
        lines = []
        lines.append(f"# Bug Report - Run {self.run_id}")
        lines.append(f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")

        summary = self.get_error_summary()

        lines.append("## Error Summary")
        lines.append(f"- **Total Errors**: {summary['total_errors']}")
        lines.append(f"- **Critical**: {summary['critical_errors']}")
        lines.append(f"- **Warnings**: {summary['warnings']}")
        lines.append(f"- **Info**: {summary['info']}")
        lines.append("")

        if summary['by_type']:
            lines.append("## Errors by Type")
            for error_type, count in sorted(summary['by_type'].items(), key=lambda x: x[1], reverse=True):
                lines.append(f"- **{error_type}**: {count}")
            lines.append("")

        if summary['by_phase']:
            lines.append("## Errors by Phase")
            for phase, count in sorted(summary['by_phase'].items(), key=lambda x: x[1], reverse=True):
                lines.append(f"- **{phase}**: {count}")
            lines.append("")

        # Show critical errors in detail
        critical_errors = self.get_critical_errors()
        if critical_errors:
            lines.append("## Critical Errors (Detailed)")
            lines.append("")
            for error in critical_errors:
                lines.append(f"### {error['id']} - {error['phase']}")
                lines.append(f"**Type**: {error['error_type']} / {error['error_subtype']}")
                lines.append(f"**Message**: {error['message']}")
                lines.append(f"**Recovery**: {error['recovery_action']}")
                if error.get('context'):
                    lines.append(f"**Context**: {json.dumps(error['context'], indent=2)}")
                lines.append("")

        return "\n".join(lines)

    def _save_to_file(self):
        """Save error log to JSON file"""
        try:
            log_data = {
                'run_id': self.run_id,
                'timestamp': datetime.now().isoformat(),
                'total_errors': len(self.errors),
                'critical_errors': sum(1 for e in self.errors if e['severity'] == 'CRITICAL'),
                'warnings': sum(1 for e in self.errors if e['severity'] == 'WARNING'),
                'errors': self.errors,
                'error_summary': self.get_error_summary()
            }

            with open(self.log_file, 'w', encoding='utf-8') as f:
                json.dump(log_data, f, indent=2, ensure_ascii=False)

        except Exception as e:
            logger.error(f"Failed to save error log: {e}")

    def load_from_file(self, run_id: str) -> bool:
        """
        Load error log from previous run

        Args:
            run_id: Run ID to load

        Returns:
            True if loaded successfully
        """
        try:
            log_file = self.log_dir / f"errors_{run_id}.json"
            if not log_file.exists():
                return False

            with open(log_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self.errors = data.get('errors', [])
            self.error_counter = len(self.errors)

            logger.info(f"Loaded {len(self.errors)} errors from {run_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to load error log: {e}")
            return False

    def get_error_stats(self) -> Dict[str, Any]:
        """Get detailed error statistics"""
        if not self.errors:
            return {}

        return {
            'total': len(self.errors),
            'by_severity': self.get_error_summary()['by_severity'],
            'by_type': self.get_error_summary()['by_type'],
            'by_phase': self.get_error_summary()['by_phase'],
            'recent_errors': self.errors[-5:] if len(self.errors) >= 5 else self.errors,
            'has_critical': self.has_critical_errors()
        }


if __name__ == "__main__":
    # Test error tracker
    tracker = ErrorTracker("test_20251030_120000")

    # Simulate some errors
    try:
        raise TimeoutError("RSS feed timeout after 60 seconds")
    except Exception as e:
        tracker.log_error(
            phase="scraping",
            error=e,
            severity="WARNING",
            context={'source_id': 'wsj_technology', 'url': 'https://example.com'},
            recovery_action="SKIP_SOURCE"
        )

    try:
        raise ConnectionError("Remote end closed connection without response")
    except Exception as e:
        tracker.log_error(
            phase="scraping",
            error=e,
            severity="WARNING",
            context={'source_id': 'bloomberg_tech'},
            recovery_action="SKIP_SOURCE"
        )

    try:
        raise ValueError("Invalid JSON response from LLM")
    except Exception as e:
        tracker.log_error(
            phase="tier2_batch_eval",
            error=e,
            severity="CRITICAL",
            context={'batch_number': 5},
            recovery_action="FAIL_FAST"
        )

    print("\n" + "=" * 60)
    print("Error Summary")
    print("=" * 60)
    print(json.dumps(tracker.get_error_summary(), indent=2))

    print("\n" + "=" * 60)
    print("Bug Report")
    print("=" * 60)
    print(tracker.generate_bug_report())
