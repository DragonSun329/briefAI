"""
ACE Orchestrator Package

Agentic Context Engineering (ACE) - Master orchestrator for the briefAI pipeline.
Provides context management, error tracking, metrics collection, and execution reporting.

Main Components:
- ACEOrchestrator: Main orchestrator class (9-phase pipeline)
- ContextEngine: Adaptive context management across runs
- ErrorTracker: Comprehensive error logging and classification
- PhaseManager: Phase execution and dependency management
- MetricsCollector: Detailed performance and token tracking
- ExecutionReporter: Summary and bug report generation
"""

from .ace_orchestrator import ACEOrchestrator
from .context_engine import ContextEngine
from .error_tracker import ErrorTracker
from .phase_manager import PhaseManager
from .metrics_collector import MetricsCollector
from .execution_reporter import ExecutionReporter

__all__ = [
    'ACEOrchestrator',
    'ContextEngine',
    'ErrorTracker',
    'PhaseManager',
    'MetricsCollector',
    'ExecutionReporter',
]

__version__ = '1.0.0'
