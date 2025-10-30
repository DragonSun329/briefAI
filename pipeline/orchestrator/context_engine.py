"""
Context Engine Module

Agentic Context Engineering (ACE) - Manages adaptive context across pipeline phases and runs.

Features:
- Phase-to-phase context passing
- Historical context learning (past 5 runs)
- Anomaly detection in metrics
- Optimization suggestions
- Context persistence between runs
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional
from loguru import logger


class ContextEngine:
    """Manages adaptive context for Agentic Context Engineering"""

    def __init__(self, run_id: str, persist_dir: str = "./data/context"):
        """
        Initialize context engine

        Args:
            run_id: Unique run identifier
            persist_dir: Directory to persist context
        """
        self.run_id = run_id
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)

        self.context_file = self.persist_dir / f"context_{run_id}.json"

        # Current run context
        self.context = {
            'run_id': run_id,
            'created_at': datetime.now().isoformat(),
            'phases': {},
            'global_insights': [],
            'historical_averages': {},
            'anomalies_detected': []
        }

        # Load historical context
        self.historical_context = self._load_historical_context(lookback_runs=5)

        logger.info(f"Context engine initialized: {self.context_file}")
        logger.info(f"Loaded {len(self.historical_context)} historical runs")

    def update(
        self,
        phase: str,
        metrics: Dict[str, Any],
        insights: Optional[List[str]] = None
    ):
        """
        Update context for a phase

        Args:
            phase: Pipeline phase name
            metrics: Metrics dict for the phase
            insights: Optional list of insights discovered
        """
        self.context['phases'][phase] = {
            'completed_at': datetime.now().isoformat(),
            'metrics': metrics,
            'insights': insights or []
        }

        # Check for anomalies
        anomalies = self._detect_anomalies(phase, metrics)
        if anomalies:
            self.context['anomalies_detected'].extend(anomalies)
            for anomaly in anomalies:
                logger.warning(f"Anomaly detected in {phase}: {anomaly}")

        logger.debug(f"Context updated for phase '{phase}'")

    def get_for_phase(self, phase_name: str) -> Dict[str, Any]:
        """
        Get relevant context for a specific phase

        Args:
            phase_name: Name of pipeline phase

        Returns:
            Dict with relevant context
        """
        phase_context = {
            'current_run': {
                'run_id': self.run_id,
                'completed_phases': list(self.context['phases'].keys()),
                'previous_phase_data': self._get_previous_phase_data(phase_name)
            },
            'historical': {
                'averages': self._get_historical_averages_for_phase(phase_name),
                'success_patterns': self._get_success_patterns(phase_name)
            },
            'insights': self.context.get('global_insights', []),
            'anomalies': [a for a in self.context.get('anomalies_detected', []) if a.get('phase') == phase_name]
        }

        return phase_context

    def add_global_insight(self, insight: str):
        """
        Add a global insight that applies across phases

        Args:
            insight: Insight text
        """
        self.context['global_insights'].append({
            'timestamp': datetime.now().isoformat(),
            'insight': insight
        })

    def save_snapshot(self, filename: Optional[str] = None):
        """
        Save current context to file

        Args:
            filename: Optional custom filename
        """
        try:
            save_path = self.context_file if not filename else self.persist_dir / filename

            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(self.context, f, indent=2, ensure_ascii=False)

            logger.info(f"Context snapshot saved: {save_path}")

        except Exception as e:
            logger.error(f"Failed to save context snapshot: {e}")

    def load_historical_context(self, lookback_runs: int = 5) -> List[Dict[str, Any]]:
        """
        Load context from previous runs

        Args:
            lookback_runs: Number of recent runs to load

        Returns:
            List of context dicts
        """
        return self._load_historical_context(lookback_runs)

    def get_average_metric(self, metric_name: str, phase: str) -> Optional[float]:
        """
        Get historical average for a specific metric

        Args:
            metric_name: Name of metric
            phase: Pipeline phase

        Returns:
            Average value or None
        """
        values = []

        for hist_context in self.historical_context:
            phase_data = hist_context.get('phases', {}).get(phase, {})
            metrics = phase_data.get('metrics', {})

            if metric_name in metrics:
                values.append(metrics[metric_name])

        return sum(values) / len(values) if values else None

    def detect_anomalies(self, current_metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Detect anomalies in current metrics compared to historical data

        Args:
            current_metrics: Current run metrics

        Returns:
            List of detected anomalies
        """
        anomalies = []

        for phase in current_metrics.get('phases', {}).keys():
            phase_anomalies = self._detect_anomalies(phase, current_metrics['phases'][phase])
            anomalies.extend(phase_anomalies)

        return anomalies

    def suggest_optimizations(self) -> List[str]:
        """
        Suggest optimizations based on context and history

        Returns:
            List of optimization suggestions
        """
        suggestions = []

        # Check scraping success rate
        scraping_data = self.context.get('phases', {}).get('scraping', {})
        if scraping_data:
            metrics = scraping_data.get('metrics', {})
            success_rate = metrics.get('sources_succeeded', 0) / max(metrics.get('sources_attempted', 1), 1)

            if success_rate < 0.85:
                suggestions.append(
                    f"Scraping success rate is {success_rate:.1%} (below 85%). "
                    "Consider increasing timeouts or adding backup RSS feeds."
                )

        # Check LLM cost
        total_cost = self.context.get('total_cost_usd', 0)
        avg_historical_cost = self.get_average_metric('total_cost_usd', 'total')

        if avg_historical_cost and total_cost > avg_historical_cost * 1.5:
            suggestions.append(
                f"Current run cost (${total_cost:.2f}) is 50% higher than historical average "
                f"(${avg_historical_cost:.2f}). Consider optimizing prompts or using cheaper models."
            )

        # Check anomalies
        if self.context.get('anomalies_detected'):
            suggestions.append(
                f"Detected {len(self.context['anomalies_detected'])} anomalies. "
                "Review error logs for details."
            )

        return suggestions

    def _get_previous_phase_data(self, current_phase: str) -> Optional[Dict[str, Any]]:
        """Get data from the immediately previous phase"""
        phase_order = [
            'initialization', 'scraping', 'tier1_filter', 'tier2_batch_eval',
            'tier3_5d_eval', 'ranking', 'paraphrasing', 'report_generation', 'finalization'
        ]

        try:
            current_idx = phase_order.index(current_phase)
            if current_idx > 0:
                prev_phase = phase_order[current_idx - 1]
                return self.context['phases'].get(prev_phase)
        except (ValueError, IndexError):
            pass

        return None

    def _load_historical_context(self, lookback_runs: int = 5) -> List[Dict[str, Any]]:
        """Load context from recent runs"""
        historical = []

        try:
            # Get all context files sorted by modification time (newest first)
            context_files = sorted(
                self.persist_dir.glob("context_*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )

            # Load most recent N files (excluding current run)
            for context_file in context_files[:lookback_runs + 1]:
                # Skip current run's file
                if context_file.name == f"context_{self.run_id}.json":
                    continue

                try:
                    with open(context_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        historical.append(data)

                    if len(historical) >= lookback_runs:
                        break

                except Exception as e:
                    logger.warning(f"Failed to load {context_file.name}: {e}")

        except Exception as e:
            logger.warning(f"Failed to load historical context: {e}")

        return historical

    def _get_historical_averages_for_phase(self, phase: str) -> Dict[str, float]:
        """Calculate historical averages for a specific phase"""
        averages = {}

        if not self.historical_context:
            return averages

        # Collect metrics from historical runs
        metric_values = {}

        for hist_context in self.historical_context:
            phase_data = hist_context.get('phases', {}).get(phase, {})
            metrics = phase_data.get('metrics', {})

            for metric_name, value in metrics.items():
                if isinstance(value, (int, float)):
                    if metric_name not in metric_values:
                        metric_values[metric_name] = []
                    metric_values[metric_name].append(value)

        # Calculate averages
        for metric_name, values in metric_values.items():
            averages[metric_name] = sum(values) / len(values)

        return averages

    def _get_success_patterns(self, phase: str) -> Dict[str, Any]:
        """Identify success patterns from historical data"""
        patterns = {
            'typical_output_range': None,
            'typical_duration_range': None,
            'common_issues': []
        }

        if not self.historical_context:
            return patterns

        # Collect output ranges
        outputs = []
        durations = []

        for hist_context in self.historical_context:
            phase_data = hist_context.get('phases', {}).get(phase, {})
            metrics = phase_data.get('metrics', {})

            if 'articles_output' in metrics:
                outputs.append(metrics['articles_output'])
            if 'duration_seconds' in metrics:
                durations.append(metrics['duration_seconds'])

        if outputs:
            patterns['typical_output_range'] = (min(outputs), max(outputs))

        if durations:
            patterns['typical_duration_range'] = (min(durations), max(durations))

        return patterns

    def _detect_anomalies(self, phase: str, metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Detect anomalies in phase metrics"""
        anomalies = []

        # Get historical averages
        hist_averages = self._get_historical_averages_for_phase(phase)

        if not hist_averages:
            return anomalies  # No historical data yet

        # Check each metric
        for metric_name, current_value in metrics.items():
            if not isinstance(current_value, (int, float)):
                continue

            if metric_name not in hist_averages:
                continue

            hist_avg = hist_averages[metric_name]

            # Detect significant deviations (>50% from average)
            if hist_avg > 0:
                deviation = abs(current_value - hist_avg) / hist_avg

                if deviation > 0.5:  # 50% threshold
                    anomalies.append({
                        'phase': phase,
                        'metric': metric_name,
                        'current_value': current_value,
                        'historical_average': hist_avg,
                        'deviation_percent': round(deviation * 100, 1),
                        'severity': 'HIGH' if deviation > 1.0 else 'MEDIUM'
                    })

        return anomalies

    def get_context_summary(self) -> str:
        """Generate human-readable context summary"""
        lines = []
        lines.append(f"# Context Summary - Run {self.run_id}")
        lines.append("")

        lines.append("## Completed Phases")
        for phase_name in self.context['phases'].keys():
            lines.append(f"- {phase_name}")
        lines.append("")

        if self.context.get('global_insights'):
            lines.append("## Global Insights")
            for insight in self.context['global_insights']:
                lines.append(f"- {insight.get('insight', '')}")
            lines.append("")

        if self.context.get('anomalies_detected'):
            lines.append("## Anomalies Detected")
            for anomaly in self.context['anomalies_detected']:
                lines.append(
                    f"- {anomaly.get('phase')}: {anomaly.get('metric')} "
                    f"deviated {anomaly.get('deviation_percent')}% from historical average"
                )
            lines.append("")

        suggestions = self.suggest_optimizations()
        if suggestions:
            lines.append("## Optimization Suggestions")
            for suggestion in suggestions:
                lines.append(f"- {suggestion}")
            lines.append("")

        return "\n".join(lines)


if __name__ == "__main__":
    # Test context engine
    engine = ContextEngine("test_20251030_120000")

    # Simulate phase updates
    engine.update(
        phase="scraping",
        metrics={
            'sources_attempted': 86,
            'sources_succeeded': 72,
            'articles_collected': 452,
            'duration_seconds': 312.5
        },
        insights=["14 sources timed out", "WSJ and Bloomberg consistently failing"]
    )

    engine.update(
        phase="tier2_batch_eval",
        metrics={
            'articles_input': 128,
            'articles_output': 35,
            'llm_calls': 13,
            'total_cost_usd': 0.68
        }
    )

    engine.add_global_insight("Scraping success rate lower than usual - investigate timeouts")

    print("\n" + "=" * 60)
    print("Context for Tier 3 Evaluation")
    print("=" * 60)
    tier3_context = engine.get_for_phase("tier3_5d_eval")
    print(json.dumps(tier3_context, indent=2))

    print("\n" + "=" * 60)
    print("Context Summary")
    print("=" * 60)
    print(engine.get_context_summary())

    engine.save_snapshot()
