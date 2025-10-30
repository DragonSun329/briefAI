"""
Execution Reporter Module

Generates comprehensive execution summaries and bug reports.

Features:
- Pipeline execution summary
- Error and bug reports
- Performance analysis
- Historical comparison
- Recommendations
"""

from datetime import datetime
from typing import Dict, Any, Optional
from loguru import logger


class ExecutionReporter:
    """Generates execution summaries and reports"""

    def __init__(self, context_engine, error_tracker, metrics_collector, phase_manager):
        """
        Initialize execution reporter

        Args:
            context_engine: ContextEngine instance
            error_tracker: ErrorTracker instance
            metrics_collector: MetricsCollector instance
            phase_manager: PhaseManager instance
        """
        self.context_engine = context_engine
        self.error_tracker = error_tracker
        self.metrics_collector = metrics_collector
        self.phase_manager = phase_manager

        logger.info("Execution reporter initialized")

    def generate_execution_summary(
        self,
        status: str = 'SUCCESS',
        final_output_path: Optional[str] = None
    ) -> str:
        """
        Generate comprehensive execution summary

        Args:
            status: Overall pipeline status (SUCCESS, FAILED, PARTIAL)
            final_output_path: Path to final report file

        Returns:
            Markdown formatted summary
        """
        lines = []
        lines.append("# Pipeline Execution Summary")
        lines.append(f"**Run ID**: {self.context_engine.run_id}")
        lines.append(f"**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # Calculate total duration
        total_metrics = self.metrics_collector.get_total_metrics()
        duration_str = self._format_duration(total_metrics.get('total_duration_seconds', 0))

        status_emoji = {"SUCCESS": "✅", "FAILED": "❌", "PARTIAL": "⚠️"}.get(status, "❓")
        lines.append(f"**Duration**: {duration_str}")
        lines.append(f"**Status**: {status_emoji} {status}")
        lines.append("")

        # Pipeline Flow
        lines.append("## Pipeline Flow")
        phase_status = self.phase_manager.get_phase_status()

        for phase_name in self.phase_manager.PHASE_DEPENDENCIES.keys():
            if phase_name in self.phase_manager.completed_phases:
                phase_metrics = self.metrics_collector.get_phase_metrics(phase_name)
                duration = phase_metrics.get('duration_seconds', 0) if phase_metrics else 0
                duration_str = self._format_duration(duration)

                # Get article counts
                articles_info = ""
                if phase_metrics:
                    input_count = phase_metrics.get('articles_input')
                    output_count = phase_metrics.get('articles_output')
                    if input_count is not None and output_count is not None:
                        articles_info = f" - {input_count} → {output_count} articles"

                lines.append(f"{self._get_phase_number(phase_name)}. ✅ {phase_name}{articles_info} ({duration_str})")

            elif phase_name in self.phase_manager.failed_phases:
                lines.append(f"{self._get_phase_number(phase_name)}. ❌ {phase_name} (FAILED)")
            else:
                lines.append(f"{self._get_phase_number(phase_name)}. ⏸️  {phase_name} (not started)")

        lines.append("")

        # Metrics Summary
        lines.append("## Metrics Summary")
        lines.append(f"- **Articles**: {self._get_article_flow_summary()}")
        lines.append(f"- **Filter Rates**: {self._get_filter_rates()}")
        lines.append(f"- **Token Usage**: {total_metrics.get('total_tokens', 0):,} total "
                    f"(input: {total_metrics.get('total_input_tokens', 0):,}, "
                    f"output: {total_metrics.get('total_output_tokens', 0):,})")
        lines.append(f"- **Cost**: ${total_metrics.get('total_cost_usd', 0):.4f} USD")
        lines.append(f"- **LLM Calls**: {total_metrics.get('total_llm_calls', 0)} "
                    f"(avg latency: {self._get_avg_llm_latency()})")
        lines.append("")

        # Errors & Warnings
        error_summary = self.error_tracker.get_error_summary()
        if error_summary.get('total_errors', 0) > 0:
            lines.append("## Errors & Warnings")
            lines.append(f"- **Total Errors**: {error_summary['total_errors']} "
                        f"({error_summary.get('critical_errors', 0)} critical, "
                        f"{error_summary.get('warnings', 0)} warnings)")

            if error_summary.get('by_type'):
                lines.append("- **By Type**:")
                for error_type, count in sorted(error_summary['by_type'].items(), key=lambda x: x[1], reverse=True):
                    lines.append(f"  - {error_type}: {count}")

            # Show failed sources if scraping had errors
            failed_sources = self._get_failed_sources()
            if failed_sources:
                lines.append(f"\n### Failed Sources ({len(failed_sources)})")
                for idx, source in enumerate(failed_sources[:10], 1):  # Show first 10
                    lines.append(f"{idx}. {source}")
                if len(failed_sources) > 10:
                    lines.append(f"... and {len(failed_sources) - 10} more")

            lines.append("")

        # Performance vs Historical
        lines.append("## Performance vs. Historical Average")
        historical_comparison = self._compare_to_historical()
        for comparison in historical_comparison:
            lines.append(f"- {comparison}")
        lines.append("")

        # Anomalies
        anomalies = self.context_engine.context.get('anomalies_detected', [])
        if anomalies:
            lines.append("## Anomalies Detected")
            for anomaly in anomalies[:5]:  # Show first 5
                lines.append(
                    f"- **{anomaly.get('phase')}**: {anomaly.get('metric')} "
                    f"deviated {anomaly.get('deviation_percent')}% from historical average "
                    f"({anomaly.get('severity')} severity)"
                )
            if len(anomalies) > 5:
                lines.append(f"... and {len(anomalies) - 5} more anomalies")
            lines.append("")

        # Recommendations
        recommendations = self.context_engine.suggest_optimizations()
        if recommendations:
            lines.append("## Recommendations")
            for rec in recommendations:
                lines.append(f"- {rec}")
            lines.append("")

        # Output Files
        lines.append("## Output Files")
        if final_output_path:
            lines.append(f"- Report: `{final_output_path}`")
        lines.append(f"- Error Log: `{self.error_tracker.log_file}`")
        lines.append(f"- Context: `{self.context_engine.context_file}`")
        lines.append(f"- Metrics: `{self.metrics_collector.metrics_file}`")
        lines.append("")

        return "\n".join(lines)

    def create_bug_report(self) -> str:
        """
        Create detailed bug report

        Returns:
            Markdown formatted bug report
        """
        return self.error_tracker.generate_bug_report()

    def save_run_history(self, output_dir: str) -> bool:
        """
        Save run history to files

        Args:
            output_dir: Directory to save history files

        Returns:
            True if successful
        """
        try:
            # Save context
            self.context_engine.save_snapshot()

            # Save metrics
            self.metrics_collector.save_to_file()

            # Error log is saved automatically

            logger.info(f"Run history saved to {output_dir}")
            return True

        except Exception as e:
            logger.error(f"Failed to save run history: {e}")
            return False

    def _format_duration(self, seconds: float) -> str:
        """Format duration in human-readable format"""
        if seconds < 60:
            return f"{seconds:.0f}s"
        elif seconds < 3600:
            minutes = seconds // 60
            secs = seconds % 60
            return f"{minutes:.0f}m {secs:.0f}s"
        else:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            return f"{hours:.0f}h {minutes:.0f}m"

    def _get_phase_number(self, phase_name: str) -> int:
        """Get phase number (1-9)"""
        phase_order = list(self.phase_manager.PHASE_DEPENDENCIES.keys())
        try:
            return phase_order.index(phase_name) + 1
        except ValueError:
            return 0

    def _get_article_flow_summary(self) -> str:
        """Get article flow summary across phases"""
        scraping = self.metrics_collector.get_phase_metrics('scraping')
        ranking = self.metrics_collector.get_phase_metrics('ranking')

        if scraping and ranking:
            start = scraping.get('articles_output', 0)
            end = ranking.get('articles_output', 0)
            return f"{start} scraped → {end} final"
        elif scraping:
            return f"{scraping.get('articles_output', 0)} scraped"
        else:
            return "N/A"

    def _get_filter_rates(self) -> str:
        """Get filter rate summary"""
        tier1 = self.metrics_collector.get_phase_metrics('tier1_filter')
        tier2 = self.metrics_collector.get_phase_metrics('tier2_batch_eval')

        rates = []

        if tier1 and tier1.get('articles_input'):
            rate = tier1.get('articles_output', 0) / tier1['articles_input']
            rates.append(f"Tier 1 ({rate:.1%})")

        if tier2 and tier2.get('articles_input'):
            rate = tier2.get('articles_output', 0) / tier2['articles_input']
            rates.append(f"Tier 2 ({rate:.1%})")

        return ", ".join(rates) if rates else "N/A"

    def _get_avg_llm_latency(self) -> str:
        """Get average LLM latency"""
        if not self.metrics_collector.llm_calls:
            return "N/A"

        total_latency = sum(c['latency_ms'] for c in self.metrics_collector.llm_calls)
        avg_latency = total_latency / len(self.metrics_collector.llm_calls)

        return f"{avg_latency:.0f}ms"

    def _get_failed_sources(self) -> list:
        """Get list of failed source names"""
        scraping_errors = self.error_tracker.get_errors_by_phase('scraping')

        failed_sources = []
        for error in scraping_errors:
            context = error.get('context', {})
            source_id = context.get('source_id')
            if source_id and source_id not in failed_sources:
                failed_sources.append(source_id)

        return failed_sources

    def _compare_to_historical(self) -> list:
        """Compare current run to historical averages"""
        comparisons = []

        # Scraping success rate
        scraping = self.metrics_collector.get_phase_metrics('scraping')
        if scraping:
            current_success = scraping.get('custom_metrics', {}).get('sources_succeeded', {}).get('value', 0)
            current_attempted = scraping.get('custom_metrics', {}).get('sources_attempted', {}).get('value', 1)
            current_rate = current_success / max(current_attempted, 1)

            hist_avg = self.context_engine.get_average_metric('sources_success_rate', 'scraping')
            if hist_avg:
                diff = current_rate - hist_avg
                emoji = "✅" if diff >= 0 else "⚠️"
                comparisons.append(
                    f"Scraping success: {current_rate:.1%} (avg: {hist_avg:.1%}) {emoji} "
                    f"{'+' if diff >= 0 else ''}{diff:.1%}"
                )

        # Filter rates
        tier1 = self.metrics_collector.get_phase_metrics('tier1_filter')
        if tier1 and tier1.get('articles_input'):
            current_rate = tier1.get('articles_output', 0) / tier1['articles_input']
            hist_avg = self.context_engine.get_average_metric('filter_rate', 'tier1_filter')

            if hist_avg:
                diff = current_rate - hist_avg
                emoji = "✅"
                comparisons.append(
                    f"Tier 1 filter: {current_rate:.1%} (avg: {hist_avg:.1%}) {emoji}"
                )

        if not comparisons:
            comparisons.append("No historical data available for comparison")

        return comparisons


if __name__ == "__main__":
    from orchestrator.context_engine import ContextEngine
    from orchestrator.error_tracker import ErrorTracker
    from orchestrator.metrics_collector import MetricsCollector
    from orchestrator.phase_manager import PhaseManager

    # Test execution reporter
    context_engine = ContextEngine("test_20251030_120000")
    error_tracker = ErrorTracker("test_20251030_120000")
    metrics_collector = MetricsCollector("test_20251030_120000")
    phase_manager = PhaseManager(context_engine, error_tracker, metrics_collector)

    reporter = ExecutionReporter(context_engine, error_tracker, metrics_collector, phase_manager)

    # Simulate some activity
    phase_manager.completed_phases = ['initialization', 'scraping', 'tier1_filter']

    print("=" * 60)
    print("Execution Summary")
    print("=" * 60)
    print(reporter.generate_execution_summary(status='SUCCESS'))
