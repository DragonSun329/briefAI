"""
Experiment Manager v1.0

Manages experimental isolation for forward-testing multiple forecasting models.
Each experiment has its own:
- Forecast history ledger
- Calibration metrics
- Audit trail

This ensures scientific integrity by preventing model contamination.
"""

import json
import subprocess
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from loguru import logger


# =============================================================================
# CONSTANTS
# =============================================================================

DEFAULT_EXPERIMENTS_PATH = Path(__file__).parent.parent / "config" / "experiments.json"
DEFAULT_PUBLIC_PATH = Path(__file__).parent.parent / "data" / "public"


# =============================================================================
# CONFIG LOADER
# =============================================================================

_EXPERIMENTS_CACHE = None


def load_experiments(config_path: Path = None, force_reload: bool = False) -> Dict[str, Any]:
    """Load experiments config with caching."""
    global _EXPERIMENTS_CACHE
    
    if _EXPERIMENTS_CACHE is not None and not force_reload:
        return _EXPERIMENTS_CACHE
    
    if config_path is None:
        config_path = DEFAULT_EXPERIMENTS_PATH
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            _EXPERIMENTS_CACHE = json.load(f)
            return _EXPERIMENTS_CACHE
    except Exception as e:
        logger.warning(f"Failed to load experiments.json: {e}")
        return {'experiments': {}, 'active_experiment': None}


def clear_cache():
    """Clear the experiments cache."""
    global _EXPERIMENTS_CACHE
    _EXPERIMENTS_CACHE = None


def save_experiments(config: Dict[str, Any], config_path: Path = None):
    """Save experiments config."""
    if config_path is None:
        config_path = DEFAULT_EXPERIMENTS_PATH
    
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    
    clear_cache()


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class Experiment:
    """Represents a forecasting experiment."""
    experiment_id: str
    engine_tag: str
    engine_version: str
    ledger_path: Path
    metrics_path: Path
    start_date: str
    description: str
    prediction_types: list
    status: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'experiment_id': self.experiment_id,
            'engine_tag': self.engine_tag,
            'engine_version': self.engine_version,
            'ledger_path': str(self.ledger_path),
            'metrics_path': str(self.metrics_path),
            'start_date': self.start_date,
            'description': self.description,
            'prediction_types': self.prediction_types,
            'status': self.status,
        }
    
    @classmethod
    def from_dict(cls, experiment_id: str, d: Dict[str, Any]) -> 'Experiment':
        return cls(
            experiment_id=experiment_id,
            engine_tag=d.get('engine_tag', ''),
            engine_version=d.get('engine_version', ''),
            ledger_path=Path(d.get('ledger_path', '')),
            metrics_path=Path(d.get('metrics_path', '')),
            start_date=d.get('start_date', ''),
            description=d.get('description', ''),
            prediction_types=d.get('prediction_types', []),
            status=d.get('status', 'pending'),
        )


@dataclass
class ExperimentContext:
    """Context for the current experiment, including git info."""
    experiment: Experiment
    commit_hash: str
    generation_timestamp: str
    
    def get_metadata_stamp(self) -> Dict[str, Any]:
        """Get metadata stamp for predictions."""
        return {
            'experiment_id': self.experiment.experiment_id,
            'engine_version': self.experiment.engine_tag,
            'commit_hash': self.commit_hash,
            'generation_timestamp': self.generation_timestamp,
        }


# =============================================================================
# GIT HELPERS
# =============================================================================

def get_current_commit_hash() -> str:
    """Get the current git commit hash."""
    try:
        result = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception as e:
        logger.warning(f"Failed to get git commit hash: {e}")
    return 'unknown'


def get_current_engine_tag() -> Optional[str]:
    """Get the current engine tag if HEAD is tagged."""
    try:
        result = subprocess.run(
            ['git', 'describe', '--tags', '--exact-match'],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
        )
        if result.returncode == 0:
            tag = result.stdout.strip()
            if tag.startswith('ENGINE_'):
                return tag
    except Exception:
        pass
    
    # Fallback: get closest engine tag
    try:
        result = subprocess.run(
            ['git', 'describe', '--tags', '--match', 'ENGINE_*'],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
        )
        if result.returncode == 0:
            return result.stdout.strip().split('-')[0]  # Get tag without offset
    except Exception:
        pass
    
    return None


def is_repo_clean() -> bool:
    """Check if the repository is clean (no uncommitted changes)."""
    try:
        result = subprocess.run(
            ['git', 'status', '--porcelain'],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
        )
        return result.returncode == 0 and not result.stdout.strip()
    except Exception:
        return False


# =============================================================================
# EXPERIMENT MANAGEMENT
# =============================================================================

def get_active_experiment() -> Optional[Experiment]:
    """Get the currently active experiment."""
    config = load_experiments()
    active_id = config.get('active_experiment')
    
    if not active_id:
        logger.warning("No active experiment configured")
        return None
    
    experiments = config.get('experiments', {})
    if active_id not in experiments:
        logger.warning(f"Active experiment '{active_id}' not found in registry")
        return None
    
    return Experiment.from_dict(active_id, experiments[active_id])


def get_experiment(experiment_id: str) -> Optional[Experiment]:
    """Get a specific experiment by ID."""
    config = load_experiments()
    experiments = config.get('experiments', {})
    
    if experiment_id not in experiments:
        return None
    
    return Experiment.from_dict(experiment_id, experiments[experiment_id])


def list_experiments() -> list:
    """List all experiments."""
    config = load_experiments()
    experiments = config.get('experiments', {})
    return [Experiment.from_dict(k, v) for k, v in experiments.items()]


def set_active_experiment(experiment_id: str) -> bool:
    """Set the active experiment."""
    config = load_experiments()
    
    if experiment_id not in config.get('experiments', {}):
        logger.error(f"Experiment '{experiment_id}' not found")
        return False
    
    config['active_experiment'] = experiment_id
    save_experiments(config)
    
    logger.info(f"Active experiment set to: {experiment_id}")
    return True


def create_experiment(
    experiment_id: str,
    engine_tag: str,
    description: str,
    prediction_types: list = None,
) -> Experiment:
    """Create a new experiment."""
    config = load_experiments()
    
    if experiment_id in config.get('experiments', {}):
        raise ValueError(f"Experiment '{experiment_id}' already exists")
    
    # Extract version from tag
    version = engine_tag.replace('ENGINE_v', '').replace('_', '.').split('.')[0]
    
    experiment_data = {
        'engine_tag': engine_tag,
        'engine_version': version,
        'ledger_path': f"data/public/experiments/{experiment_id}/",
        'metrics_path': f"data/metrics/{experiment_id}/",
        'start_date': datetime.now().strftime('%Y-%m-%d'),
        'description': description,
        'prediction_types': prediction_types or ['metric_trend'],
        'status': 'pending',
    }
    
    config['experiments'][experiment_id] = experiment_data
    save_experiments(config)
    
    experiment = Experiment.from_dict(experiment_id, experiment_data)
    
    # Create directories
    ledger_dir = Path(__file__).parent.parent / experiment.ledger_path
    metrics_dir = Path(__file__).parent.parent / experiment.metrics_path
    ledger_dir.mkdir(parents=True, exist_ok=True)
    metrics_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Created experiment: {experiment_id}")
    return experiment


# =============================================================================
# EXPERIMENT CONTEXT
# =============================================================================

def get_experiment_context(experiment_id: str = None) -> ExperimentContext:
    """
    Get the current experiment context with metadata.
    
    Args:
        experiment_id: Optional experiment ID. If None, uses active experiment.
    
    Returns:
        ExperimentContext with experiment info and git metadata
    
    Raises:
        ValueError: If no experiment is configured
    """
    if experiment_id:
        experiment = get_experiment(experiment_id)
    else:
        experiment = get_active_experiment()
    
    if not experiment:
        raise ValueError("No experiment configured. Set active_experiment in experiments.json")
    
    return ExperimentContext(
        experiment=experiment,
        commit_hash=get_current_commit_hash(),
        generation_timestamp=datetime.utcnow().isoformat() + 'Z',
    )


def validate_experiment_context(context: ExperimentContext) -> tuple:
    """
    Validate that the current state matches the experiment.
    
    Returns:
        (is_valid, warnings, errors)
    """
    warnings = []
    errors = []
    
    # Check engine tag
    current_tag = get_current_engine_tag()
    if current_tag and current_tag != context.experiment.engine_tag:
        # Check if current is a descendant (e.g., ENGINE_v3.0_ACTION vs ENGINE_v3.0_DAY1)
        if not current_tag.startswith(context.experiment.engine_tag.rsplit('_', 1)[0]):
            errors.append(
                f"Engine tag mismatch: current={current_tag}, "
                f"expected={context.experiment.engine_tag}"
            )
    
    # Check repo cleanliness
    if not is_repo_clean():
        warnings.append("Repository has uncommitted changes - predictions may not be reproducible")
    
    is_valid = len(errors) == 0
    return is_valid, warnings, errors


# =============================================================================
# LEDGER PATHS
# =============================================================================

def get_ledger_path(experiment_id: str = None) -> Path:
    """Get the ledger directory path for an experiment."""
    if experiment_id:
        experiment = get_experiment(experiment_id)
    else:
        experiment = get_active_experiment()
    
    if not experiment:
        raise ValueError("No experiment configured")
    
    base_path = Path(__file__).parent.parent
    ledger_path = base_path / experiment.ledger_path
    ledger_path.mkdir(parents=True, exist_ok=True)
    
    return ledger_path


def get_metrics_path(experiment_id: str = None) -> Path:
    """Get the metrics directory path for an experiment."""
    if experiment_id:
        experiment = get_experiment(experiment_id)
    else:
        experiment = get_active_experiment()
    
    if not experiment:
        raise ValueError("No experiment configured")
    
    base_path = Path(__file__).parent.parent
    metrics_path = base_path / experiment.metrics_path
    metrics_path.mkdir(parents=True, exist_ok=True)
    
    return metrics_path


def get_forecast_history_path(experiment_id: str = None) -> Path:
    """Get the forecast_history.jsonl path for an experiment."""
    return get_ledger_path(experiment_id) / "forecast_history.jsonl"


def get_daily_snapshot_path(date: str, experiment_id: str = None) -> Path:
    """Get the daily_snapshot path for a specific date."""
    return get_ledger_path(experiment_id) / f"daily_snapshot_{date}.json"


def get_run_metadata_path(date: str, experiment_id: str = None) -> Path:
    """Get the run_metadata path for a specific date."""
    return get_ledger_path(experiment_id) / f"run_metadata_{date}.json"


# =============================================================================
# PUBLIC INDEX
# =============================================================================

def update_public_index():
    """Update the public index file listing all experiments."""
    config = load_experiments()
    public_path = DEFAULT_PUBLIC_PATH
    public_path.mkdir(parents=True, exist_ok=True)
    
    index = {
        'generated_at': datetime.utcnow().isoformat() + 'Z',
        'experiments': list(config.get('experiments', {}).keys()),
        'active_experiment': config.get('active_experiment'),
        'experiment_details': {},
    }
    
    for exp_id, exp_data in config.get('experiments', {}).items():
        index['experiment_details'][exp_id] = {
            'engine_tag': exp_data.get('engine_tag'),
            'start_date': exp_data.get('start_date'),
            'description': exp_data.get('description'),
            'status': exp_data.get('status'),
        }
    
    index_path = public_path / "public_index.json"
    with open(index_path, 'w', encoding='utf-8') as f:
        json.dump(index, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Updated public index: {index_path}")
    return index_path


# =============================================================================
# MIGRATION HELPER
# =============================================================================

def migrate_genesis_ledger():
    """
    Migrate the Genesis (v2.1) ledger from data/public/ to the experiment folder.
    
    This is a one-time operation to set up experimental isolation.
    """
    base_path = Path(__file__).parent.parent
    old_public = base_path / "data" / "public"
    
    # Get v2.1 experiment path
    v21_experiment = get_experiment("v2_1_forward_test")
    if not v21_experiment:
        logger.error("v2_1_forward_test experiment not found")
        return False
    
    new_ledger = base_path / v21_experiment.ledger_path
    new_ledger.mkdir(parents=True, exist_ok=True)
    
    # Files to migrate
    files_to_migrate = [
        'forecast_history.jsonl',
        'daily_snapshot_2026-02-10.json',
        'run_metadata_2026-02-10.json',
        'RUN_COMPLETE_2026-02-10.flag',
    ]
    
    migrated = 0
    for filename in files_to_migrate:
        old_file = old_public / filename
        new_file = new_ledger / filename
        
        if old_file.exists():
            # Copy (don't move) to preserve original
            import shutil
            shutil.copy2(old_file, new_file)
            migrated += 1
            logger.info(f"Migrated: {filename}")
    
    if migrated > 0:
        # Update experiment status
        config = load_experiments()
        config['experiments']['v2_1_forward_test']['status'] = 'active'
        save_experiments(config)
        
        # Update public index
        update_public_index()
    
    logger.info(f"Migration complete: {migrated} files migrated")
    return True
