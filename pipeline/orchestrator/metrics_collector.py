"""
Metrics Collector Module

Detailed performance and token usage tracking for pipeline execution.

Features:
- Per-LLM-call token tracking with costs
- Phase-level performance metrics
- Latency and throughput monitoring
- Cost calculation across providers
- Historical metrics comparison
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from loguru import logger


class MetricsCollector:
    """Collects and tracks detailed performance metrics"""

    # Pricing per 1M tokens (as of Oct 2025)
    PRICING = {
        'kimi': {
            'moonshot-v1-8k': {'input': 12.0, 'output': 12.0},  # CNY per 1M tokens
            'moonshot-v1-32k': {'input': 24.0, 'output': 24.0},
            'moonshot-v1-128k': {'input': 60.0, 'output': 60.0},
        },
        'anthropic': {
            'claude-sonnet-4': {'input': 3.0, 'output': 15.0},  # USD per 1M tokens
            'claude-opus-4': {'input': 15.0, 'output': 75.0},
        },
        'openrouter': {
            'default': {'input': 1.0, 'output': 2.0},  # Estimate
        }
    }

    # CNY to USD conversion rate
    CNY_TO_USD = 0.14

    def __init__(self, run_id: str, metrics_dir: str = "./data/metrics"):
        """
        Initialize metrics collector

        Args:
            run_id: Unique run identifier
            metrics_dir: Directory to save metrics
        """
        self.run_id = run_id
        self.metrics_dir = Path(metrics_dir)
        self.metrics_dir.mkdir(parents=True, exist_ok=True)

        self.metrics_file = self.metrics_dir / f"metrics_{run_id}.json"

        # In-memory metrics storage
        self.llm_calls: List[Dict[str, Any]] = []
        self.phase_metrics: Dict[str, Dict[str, Any]] = {}
        self.call_counter = 0

        logger.info(f"Metrics collector initialized: {self.metrics_file}")

    def record_llm_call(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        latency_ms: int,
        phase: str,
        success: bool = True,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Record a single LLM API call with detailed metrics

        Args:
            provider: LLM provider name (kimi, anthropic, openrouter)
            model: Model name
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            latency_ms: Latency in milliseconds
            phase: Pipeline phase
            success: Whether call succeeded
            metadata: Additional metadata

        Returns:
            Call ID
        """
        self.call_counter += 1
        call_id = f"llm_call_{self.call_counter:03d}"

        # Calculate cost
        cost_usd = self._calculate_cost(provider, model, input_tokens, output_tokens)

        call_record = {
            'call_id': call_id,
            'timestamp': datetime.now().isoformat(),
            'phase': phase,
            'provider': provider,
            'model': model,
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'total_tokens': input_tokens + output_tokens,
            'cost_usd': round(cost_usd, 4),
            'latency_ms': latency_ms,
            'success': success,
            'metadata': metadata or {}
        }

        self.llm_calls.append(call_record)

        logger.debug(
            f"[{call_id}] {provider}/{model} | "
            f"{input_tokens + output_tokens} tokens | "
            f"${cost_usd:.4f} | {latency_ms}ms"
        )

        return call_id

    def record_metric(
        self,
        metric_name: str,
        value: Any,
        phase: str,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Record a custom metric

        Args:
            metric_name: Name of metric
            value: Metric value
            phase: Pipeline phase
            metadata: Additional metadata
        """
        if phase not in self.phase_metrics:
            self.phase_metrics[phase] = {
                'phase_name': phase,
                'custom_metrics': {},
                'started_at': datetime.now().isoformat(),
                'completed_at': None
            }

        self.phase_metrics[phase]['custom_metrics'][metric_name] = {
            'value': value,
            'timestamp': datetime.now().isoformat(),
            'metadata': metadata or {}
        }

    def start_phase(self, phase_name: str):
        """
        Mark the start of a pipeline phase

        Args:
            phase_name: Name of phase
        """
        if phase_name not in self.phase_metrics:
            self.phase_metrics[phase_name] = {
                'phase_name': phase_name,
                'started_at': datetime.now().isoformat(),
                'completed_at': None,
                'duration_seconds': None,
                'custom_metrics': {}
            }

    def end_phase(
        self,
        phase_name: str,
        articles_input: Optional[int] = None,
        articles_output: Optional[int] = None
    ):
        """
        Mark the end of a pipeline phase

        Args:
            phase_name: Name of phase
            articles_input: Number of input articles
            articles_output: Number of output articles
        """
        if phase_name not in self.phase_metrics:
            logger.warning(f"Phase '{phase_name}' was not started")
            return

        phase_data = self.phase_metrics[phase_name]
        phase_data['completed_at'] = datetime.now().isoformat()

        # Calculate duration
        started = datetime.fromisoformat(phase_data['started_at'])
        completed = datetime.fromisoformat(phase_data['completed_at'])
        duration = (completed - started).total_seconds()
        phase_data['duration_seconds'] = round(duration, 2)

        # Record article counts
        if articles_input is not None:
            phase_data['articles_input'] = articles_input
        if articles_output is not None:
            phase_data['articles_output'] = articles_output

        # Calculate LLM metrics for this phase
        phase_llm_calls = [c for c in self.llm_calls if c['phase'] == phase_name]

        if phase_llm_calls:
            phase_data['llm_calls'] = len(phase_llm_calls)
            phase_data['total_input_tokens'] = sum(c['input_tokens'] for c in phase_llm_calls)
            phase_data['total_output_tokens'] = sum(c['output_tokens'] for c in phase_llm_calls)
            phase_data['total_tokens'] = sum(c['total_tokens'] for c in phase_llm_calls)
            phase_data['total_cost_usd'] = round(sum(c['cost_usd'] for c in phase_llm_calls), 4)
            phase_data['avg_latency_ms'] = round(
                sum(c['latency_ms'] for c in phase_llm_calls) / len(phase_llm_calls), 0
            )

        logger.info(
            f"Phase '{phase_name}' completed: {duration:.1f}s | "
            f"{phase_data.get('llm_calls', 0)} LLM calls | "
            f"${phase_data.get('total_cost_usd', 0):.4f}"
        )

    def get_phase_metrics(self, phase_name: str) -> Optional[Dict[str, Any]]:
        """
        Get metrics for a specific phase

        Args:
            phase_name: Name of phase

        Returns:
            Phase metrics dict or None
        """
        return self.phase_metrics.get(phase_name)

    def get_total_metrics(self) -> Dict[str, Any]:
        """
        Get aggregated metrics across all phases

        Returns:
            Total metrics dict
        """
        total_llm_calls = len(self.llm_calls)
        total_input_tokens = sum(c['input_tokens'] for c in self.llm_calls)
        total_output_tokens = sum(c['output_tokens'] for c in self.llm_calls)
        total_cost = sum(c['cost_usd'] for c in self.llm_calls)

        # Calculate total duration from all phases
        completed_phases = [p for p in self.phase_metrics.values() if p.get('completed_at')]
        total_duration = sum(p.get('duration_seconds', 0) for p in completed_phases)

        return {
            'total_llm_calls': total_llm_calls,
            'total_input_tokens': total_input_tokens,
            'total_output_tokens': total_output_tokens,
            'total_tokens': total_input_tokens + total_output_tokens,
            'total_cost_usd': round(total_cost, 4),
            'total_duration_seconds': round(total_duration, 2),
            'avg_tokens_per_call': round(
                (total_input_tokens + total_output_tokens) / total_llm_calls, 0
            ) if total_llm_calls > 0 else 0,
            'phases_completed': len(completed_phases)
        }

    def generate_performance_report(self) -> str:
        """
        Generate human-readable performance report

        Returns:
            Markdown formatted report
        """
        lines = []
        lines.append(f"# Performance Metrics - Run {self.run_id}")
        lines.append(f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")

        total = self.get_total_metrics()

        lines.append("## Overall Metrics")
        lines.append(f"- **Total LLM Calls**: {total['total_llm_calls']}")
        lines.append(f"- **Total Tokens**: {total['total_tokens']:,} "
                    f"(input: {total['total_input_tokens']:,}, output: {total['total_output_tokens']:,})")
        lines.append(f"- **Total Cost**: ${total['total_cost_usd']:.4f} USD")
        lines.append(f"- **Total Duration**: {total['total_duration_seconds']:.1f}s")
        lines.append(f"- **Avg Tokens/Call**: {total['avg_tokens_per_call']}")
        lines.append("")

        # Phase breakdown
        if self.phase_metrics:
            lines.append("## Phase Breakdown")
            lines.append("")
            for phase_name, metrics in self.phase_metrics.items():
                if metrics.get('completed_at'):
                    lines.append(f"### {phase_name}")
                    lines.append(f"- **Duration**: {metrics.get('duration_seconds', 0):.1f}s")
                    if 'articles_input' in metrics:
                        lines.append(f"- **Articles**: {metrics['articles_input']} → {metrics.get('articles_output', 0)}")
                    if 'llm_calls' in metrics:
                        lines.append(f"- **LLM Calls**: {metrics['llm_calls']}")
                        lines.append(f"- **Tokens**: {metrics['total_tokens']:,}")
                        lines.append(f"- **Cost**: ${metrics['total_cost_usd']:.4f}")
                        lines.append(f"- **Avg Latency**: {metrics['avg_latency_ms']}ms")
                    lines.append("")

        # Provider breakdown
        provider_stats = self._get_provider_stats()
        if provider_stats:
            lines.append("## LLM Provider Breakdown")
            lines.append("")
            for provider, stats in provider_stats.items():
                lines.append(f"### {provider}")
                lines.append(f"- **Calls**: {stats['calls']}")
                lines.append(f"- **Tokens**: {stats['tokens']:,}")
                lines.append(f"- **Cost**: ${stats['cost']:.4f}")
                lines.append("")

        return "\n".join(lines)

    def _calculate_cost(self, provider: str, model: str, input_tokens: int, output_tokens: int) -> float:
        """Calculate cost in USD for LLM call"""
        # Get pricing
        provider_pricing = self.PRICING.get(provider, {})
        model_pricing = provider_pricing.get(model, provider_pricing.get('default', {'input': 1.0, 'output': 2.0}))

        input_cost = (input_tokens / 1_000_000) * model_pricing['input']
        output_cost = (output_tokens / 1_000_000) * model_pricing['output']

        total_cost = input_cost + output_cost

        # Convert CNY to USD for Chinese providers
        if provider == 'kimi':
            total_cost *= self.CNY_TO_USD

        return total_cost

    def _get_provider_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics by provider"""
        stats = {}

        for call in self.llm_calls:
            provider = call['provider']
            if provider not in stats:
                stats[provider] = {
                    'calls': 0,
                    'tokens': 0,
                    'cost': 0.0
                }

            stats[provider]['calls'] += 1
            stats[provider]['tokens'] += call['total_tokens']
            stats[provider]['cost'] += call['cost_usd']

        # Round costs
        for provider in stats:
            stats[provider]['cost'] = round(stats[provider]['cost'], 4)

        return stats

    def save_to_file(self):
        """Save metrics to JSON file"""
        try:
            metrics_data = {
                'run_id': self.run_id,
                'timestamp': datetime.now().isoformat(),
                'total_metrics': self.get_total_metrics(),
                'phase_metrics': self.phase_metrics,
                'llm_calls': self.llm_calls,
                'provider_stats': self._get_provider_stats()
            }

            with open(self.metrics_file, 'w', encoding='utf-8') as f:
                json.dump(metrics_data, f, indent=2, ensure_ascii=False)

            logger.info(f"Metrics saved to {self.metrics_file}")

        except Exception as e:
            logger.error(f"Failed to save metrics: {e}")

    def load_from_file(self, run_id: str) -> bool:
        """Load metrics from previous run"""
        try:
            metrics_file = self.metrics_dir / f"metrics_{run_id}.json"
            if not metrics_file.exists():
                return False

            with open(metrics_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self.llm_calls = data.get('llm_calls', [])
            self.phase_metrics = data.get('phase_metrics', {})
            self.call_counter = len(self.llm_calls)

            logger.info(f"Loaded metrics from {run_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to load metrics: {e}")
            return False


if __name__ == "__main__":
    # Test metrics collector
    collector = MetricsCollector("test_20251030_120000")

    # Simulate phase metrics
    collector.start_phase("scraping")
    collector.end_phase("scraping", articles_input=0, articles_output=452)

    collector.start_phase("tier2_batch_eval")
    collector.record_llm_call(
        provider="kimi",
        model="moonshot-v1-8k",
        input_tokens=2340,
        output_tokens=450,
        latency_ms=1850,
        phase="tier2_batch_eval"
    )
    collector.end_phase("tier2_batch_eval", articles_input=128, articles_output=35)

    print("\n" + "=" * 60)
    print("Total Metrics")
    print("=" * 60)
    print(json.dumps(collector.get_total_metrics(), indent=2))

    print("\n" + "=" * 60)
    print("Performance Report")
    print("=" * 60)
    print(collector.generate_performance_report())

    collector.save_to_file()
