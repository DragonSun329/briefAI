"""
Phase Manager Module

Manages pipeline phase execution, validation, and dependencies.

Features:
- Phase dependency resolution
- Pre/post phase validation
- Error handling and recovery
- Phase state tracking
"""

from typing import Dict, Any, Callable, Optional, List
from loguru import logger


class PhaseManager:
    """Manages execution of pipeline phases"""

    # Phase dependencies (each phase depends on listed phases)
    PHASE_DEPENDENCIES = {
        'initialization': [],
        'scraping': ['initialization'],
        'review_extraction': ['scraping'],  # NEW for PRODUCT mode
        'tier1_filter': ['scraping'],  # For NEWS mode, or ['review_extraction'] for PRODUCT
        'tier2_batch_eval': ['tier1_filter'],
        'tier3_5d_eval': ['tier2_batch_eval'],
        'trending_calculation': ['tier3_5d_eval'],  # NEW for PRODUCT mode
        'ranking': ['tier3_5d_eval'],  # For NEWS mode, or ['trending_calculation'] for PRODUCT
        'paraphrasing': ['ranking'],
        'review_summarization': ['paraphrasing'],  # NEW for PRODUCT mode
        'entity_background': ['paraphrasing'],  # For NEWS mode, or ['review_summarization'] for PRODUCT
        'quality_validation': ['entity_background'],
        'report_generation': ['quality_validation'],
        'finalization': ['report_generation']
    }

    # Required context for each phase
    REQUIRED_CONTEXT = {
        'initialization': ['category_ids'],
        'scraping': ['days_back'],
        'review_extraction': ['articles'],  # NEW for PRODUCT mode
        'tier1_filter': ['articles'],
        'tier2_batch_eval': ['filtered_articles'],
        'tier3_5d_eval': ['tier2_articles', 'top_n'],
        'trending_calculation': ['evaluated_articles'],  # NEW for PRODUCT mode
        'ranking': ['evaluated_articles'],
        'paraphrasing': ['ranked_articles'],
        'review_summarization': ['paraphrased_articles'],  # NEW for PRODUCT mode
        'entity_background': ['paraphrased_articles'],
        'quality_validation': ['enriched_articles'],
        'report_generation': ['final_articles'],
        'finalization': []
    }

    def __init__(self, context_engine, error_tracker, metrics_collector, artifact_manager=None):
        """
        Initialize phase manager

        Args:
            context_engine: ContextEngine instance
            error_tracker: ErrorTracker instance
            metrics_collector: MetricsCollector instance
            artifact_manager: Optional ArtifactManager instance
        """
        self.context_engine = context_engine
        self.error_tracker = error_tracker
        self.metrics_collector = metrics_collector
        self.artifact_manager = artifact_manager

        # Track completed phases
        self.completed_phases: List[str] = []
        self.failed_phases: List[str] = []

        logger.info("Phase manager initialized")

    def execute(
        self,
        phase_name: str,
        phase_func: Callable,
        **kwargs
    ) -> Any:
        """
        Execute a pipeline phase with full management

        Args:
            phase_name: Name of phase
            phase_func: Function to execute for this phase
            **kwargs: Arguments to pass to phase function

        Returns:
            Phase output

        Raises:
            RuntimeError: If phase fails critically
        """
        logger.info(f"=" * 80)
        logger.info(f"PHASE: {phase_name}")
        logger.info(f"=" * 80)

        # Check dependencies
        if not self.check_dependencies(phase_name):
            raise RuntimeError(f"Phase '{phase_name}' dependencies not met")

        # Validate required context
        missing_context = self._validate_required_context(phase_name, kwargs)
        if missing_context:
            raise RuntimeError(
                f"Phase '{phase_name}' missing required context: {missing_context}"
            )

        # Start metrics collection
        self.metrics_collector.start_phase(phase_name)

        try:
            # Get context for this phase
            phase_context = self.context_engine.get_for_phase(phase_name)

            # Log phase start
            logger.info(f"Starting phase '{phase_name}'...")
            if phase_context.get('historical', {}).get('averages'):
                logger.info(f"Historical averages: {phase_context['historical']['averages']}")

            # Execute phase function
            result = phase_func(**kwargs)

            # Validate output
            if not self.validate_phase_output(phase_name, result):
                raise ValueError(f"Phase '{phase_name}' produced invalid output")

            # Mark phase as completed
            self.completed_phases.append(phase_name)

            # End metrics collection
            articles_input = kwargs.get('articles') or kwargs.get('filtered_articles') or kwargs.get('tier2_articles')
            articles_input_count = len(articles_input) if isinstance(articles_input, list) else None
            articles_output_count = len(result) if isinstance(result, list) else None

            self.metrics_collector.end_phase(
                phase_name,
                articles_input=articles_input_count,
                articles_output=articles_output_count
            )

            # Update context
            phase_metrics = self.metrics_collector.get_phase_metrics(phase_name)
            self.context_engine.update(
                phase=phase_name,
                metrics=phase_metrics or {},
                insights=self._extract_insights(phase_name, result, phase_metrics)
            )

            # Save artifact if artifact manager is available
            if self.artifact_manager:
                phase_number = list(self.PHASE_DEPENDENCIES.keys()).index(phase_name) + 1

                # Prepare artifact data
                artifact_data = {}
                if isinstance(result, list):
                    artifact_data['articles'] = result
                elif isinstance(result, str):
                    artifact_data['report_path'] = result
                elif isinstance(result, dict):
                    artifact_data = result
                else:
                    artifact_data['result'] = result

                # Prepare metadata
                artifact_metadata = {
                    'duration_seconds': phase_metrics.get('duration', 0) if phase_metrics else 0,
                    'llm_calls': phase_metrics.get('llm_calls', 0) if phase_metrics else 0,
                    'cost_usd': phase_metrics.get('cost', 0) if phase_metrics else 0,
                    'input_count': articles_input_count or 0,
                }

                # Save artifact
                try:
                    self.artifact_manager.save_artifact(
                        phase_name=phase_name,
                        phase_number=phase_number,
                        data=artifact_data,
                        metadata=artifact_metadata
                    )
                except Exception as artifact_err:
                    logger.warning(f"Failed to save artifact for phase '{phase_name}': {artifact_err}")

            logger.info(f"✓ Phase '{phase_name}' completed successfully")

            return result

        except Exception as e:
            # Handle phase failure
            self.failed_phases.append(phase_name)

            # Log error
            self.error_tracker.log_error(
                phase=phase_name,
                error=e,
                severity='CRITICAL',
                context={'phase_function': phase_func.__name__},
                recovery_action='FAIL_FAST'
            )

            logger.error(f"✗ Phase '{phase_name}' failed: {e}")

            # End metrics with failure
            self.metrics_collector.end_phase(phase_name)

            # Re-raise for fail-fast behavior
            raise RuntimeError(f"Phase '{phase_name}' failed: {e}") from e

    def check_dependencies(self, phase_name: str) -> bool:
        """
        Check if phase dependencies are met

        Args:
            phase_name: Name of phase to check

        Returns:
            True if all dependencies met
        """
        if phase_name not in self.PHASE_DEPENDENCIES:
            logger.warning(f"Phase '{phase_name}' not in dependency map")
            return True

        required_phases = self.PHASE_DEPENDENCIES[phase_name]

        for required_phase in required_phases:
            if required_phase not in self.completed_phases:
                logger.error(
                    f"Phase '{phase_name}' requires '{required_phase}' "
                    f"but it has not completed"
                )
                return False

        return True

    def validate_phase_output(self, phase_name: str, output: Any) -> bool:
        """
        Validate phase output

        Args:
            phase_name: Name of phase
            output: Phase output to validate

        Returns:
            True if output is valid
        """
        # Basic validation rules per phase
        validation_rules = {
            'initialization': lambda x: isinstance(x, dict),
            'scraping': lambda x: isinstance(x, list),
            'review_extraction': lambda x: isinstance(x, list) and len(x) > 0,  # NEW for PRODUCT
            'tier1_filter': lambda x: isinstance(x, list) and len(x) > 0,
            'tier2_batch_eval': lambda x: isinstance(x, list) and len(x) > 0,
            'tier3_5d_eval': lambda x: isinstance(x, list) and len(x) > 0,
            'trending_calculation': lambda x: isinstance(x, list) and len(x) > 0,  # NEW for PRODUCT
            'ranking': lambda x: isinstance(x, list) and len(x) > 0,
            'paraphrasing': lambda x: isinstance(x, list) and len(x) > 0,
            'review_summarization': lambda x: isinstance(x, list) and len(x) > 0,  # NEW for PRODUCT
            'entity_background': lambda x: isinstance(x, list) and len(x) > 0,
            'quality_validation': lambda x: isinstance(x, list) and len(x) > 0,
            'report_generation': lambda x: isinstance(x, str) and len(x) > 0,
            'finalization': lambda x: True  # Always valid
        }

        if phase_name not in validation_rules:
            logger.warning(f"No validation rule for phase '{phase_name}'")
            return True

        try:
            is_valid = validation_rules[phase_name](output)

            if not is_valid:
                logger.warning(f"Phase '{phase_name}' output failed validation")

            return is_valid

        except Exception as e:
            logger.error(f"Error validating phase '{phase_name}' output: {e}")
            return False

    def get_phase_status(self) -> Dict[str, Any]:
        """
        Get status of all phases

        Returns:
            Dict with phase status info
        """
        all_phases = list(self.PHASE_DEPENDENCIES.keys())

        return {
            'total_phases': len(all_phases),
            'completed': len(self.completed_phases),
            'failed': len(self.failed_phases),
            'remaining': len(all_phases) - len(self.completed_phases) - len(self.failed_phases),
            'completed_phases': self.completed_phases,
            'failed_phases': self.failed_phases,
            'completion_percent': round(len(self.completed_phases) / len(all_phases) * 100, 1)
        }

    def _validate_required_context(self, phase_name: str, kwargs: Dict[str, Any]) -> List[str]:
        """Check if required context is present in kwargs"""
        if phase_name not in self.REQUIRED_CONTEXT:
            return []

        required = self.REQUIRED_CONTEXT[phase_name]
        missing = [key for key in required if key not in kwargs]

        return missing

    def _extract_insights(
        self,
        phase_name: str,
        result: Any,
        metrics: Optional[Dict[str, Any]]
    ) -> List[str]:
        """Extract insights from phase execution"""
        insights = []

        # Phase-specific insight extraction
        if phase_name == 'scraping' and isinstance(result, list):
            if metrics:
                sources_attempted = metrics.get('custom_metrics', {}).get('sources_attempted', {}).get('value', 0)
                articles_count = len(result)
                if sources_attempted > 0:
                    avg_per_source = articles_count / sources_attempted
                    insights.append(f"Average {avg_per_source:.1f} articles per source")

        elif phase_name == 'tier1_filter' and isinstance(result, list):
            if metrics and metrics.get('articles_input'):
                filter_rate = len(result) / metrics['articles_input']
                insights.append(f"Tier 1 filter rate: {filter_rate:.1%}")

        elif phase_name == 'tier2_batch_eval' and isinstance(result, list):
            if metrics and metrics.get('articles_input'):
                pass_rate = len(result) / metrics['articles_input']
                insights.append(f"Tier 2 pass rate: {pass_rate:.1%}")

        elif phase_name == 'paraphrasing' and isinstance(result, list):
            if result:
                avg_length = sum(
                    len(art.get('paraphrased_content', '')) for art in result
                ) / len(result)
                insights.append(f"Average paraphrase length: {avg_length:.0f} characters")

        return insights


if __name__ == "__main__":
    from orchestrator.context_engine import ContextEngine
    from orchestrator.error_tracker import ErrorTracker
    from orchestrator.metrics_collector import MetricsCollector

    # Test phase manager
    context_engine = ContextEngine("test_20251030_120000")
    error_tracker = ErrorTracker("test_20251030_120000")
    metrics_collector = MetricsCollector("test_20251030_120000")

    phase_manager = PhaseManager(context_engine, error_tracker, metrics_collector)

    # Test phase execution
    def test_initialization():
        return {'status': 'ok', 'config_loaded': True}

    def test_scraping():
        return [{'title': 'Article 1'}, {'title': 'Article 2'}]

    # Execute phases
    result1 = phase_manager.execute('initialization', test_initialization)
    print(f"Initialization result: {result1}")

    result2 = phase_manager.execute('scraping', test_scraping)
    print(f"Scraping result: {len(result2)} articles")

    print("\nPhase Status:")
    print(json.dumps(phase_manager.get_phase_status(), indent=2))
