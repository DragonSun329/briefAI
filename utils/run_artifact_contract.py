"""
Run Artifact Contract - Daily Output Verification v1.0

Guarantees that every pipeline run produces a complete set of artifacts.
This is the LAST thing that runs in the pipeline.

Required artifacts for a valid run:
1. forecast_history.jsonl (appended with new predictions)
2. daily_snapshot_YYYY-MM-DD.json (frozen predictions)
3. run_metadata_YYYY-MM-DD.json (complete run context)
4. daily_brief_YYYY-MM-DD.md (human-readable report)

If any artifact is missing or invalid, the run is marked as failed.

Research integrity guarantee:
    Every run day has a complete, verifiable set of outputs.
    Missing data is explicit, not silent.
"""

import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, date
from pathlib import Path
from enum import Enum

from loguru import logger


# =============================================================================
# CONSTANTS
# =============================================================================

# Minimum file sizes (bytes) - to detect empty/corrupt files
MIN_FILE_SIZES = {
    'forecast_history.jsonl': 10,  # At least one short line
    'daily_snapshot': 100,         # At least a minimal JSON object
    'run_metadata': 50,            # At least a minimal JSON object
    'daily_brief': 100,            # At least a header
}

# Required fields in run_metadata (v1.1 - includes environment)
REQUIRED_METADATA_FIELDS = [
    'experiment_id',
    'engine_tag',
    'commit_hash',
    'generation_timestamp',
    'date',
    'artifact_contract_passed',
]

# Extended fields for research-grade runs
RESEARCH_GRADE_METADATA_FIELDS = [
    'engine_commit_hash',
    'environment',
    'config_dir_hash',
]

# Experiment base path
EXPERIMENTS_BASE_PATH = Path(__file__).parent.parent / "data" / "public" / "experiments"


# =============================================================================
# EXCEPTIONS
# =============================================================================

class RunArtifactViolation(Exception):
    """Raised when artifact contract is violated."""
    
    def __init__(self, message: str, violations: List[str]):
        super().__init__(message)
        self.violations = violations


class ExperimentPathViolation(Exception):
    """Raised when an artifact is written to wrong experiment path."""
    
    def __init__(self, path: Path, expected_experiment: str, message: str = None):
        self.path = path
        self.expected_experiment = expected_experiment
        super().__init__(
            message or f"Path {path} is not in experiment {expected_experiment}"
        )


# =============================================================================
# EXPERIMENT PATH ENFORCEMENT
# =============================================================================

def get_experiment_artifact_path(experiment_id: str) -> Path:
    """Get the canonical artifact path for an experiment."""
    return EXPERIMENTS_BASE_PATH / experiment_id


def validate_artifact_path(
    artifact_path: Path,
    experiment_id: str,
    raise_on_violation: bool = True,
) -> bool:
    """
    Validate that an artifact path is within the correct experiment directory.
    
    This prevents cross-experiment contamination where v2.1 predictions
    accidentally get written to v3.0's ledger.
    
    Args:
        artifact_path: Path to the artifact being written
        experiment_id: Expected experiment ID
        raise_on_violation: If True, raise ExperimentPathViolation
    
    Returns:
        True if path is valid
    
    Raises:
        ExperimentPathViolation: If path is not in experiment directory
    """
    expected_base = get_experiment_artifact_path(experiment_id)
    
    # Resolve to absolute paths for comparison
    try:
        artifact_abs = artifact_path.resolve()
        expected_abs = expected_base.resolve()
        
        # Check if artifact is under expected experiment path
        try:
            artifact_abs.relative_to(expected_abs)
            return True
        except ValueError:
            pass
        
        # Path is not under expected experiment
        if raise_on_violation:
            # Check if it's under a different experiment
            try:
                rel_to_experiments = artifact_abs.relative_to(EXPERIMENTS_BASE_PATH.resolve())
                wrong_experiment = str(rel_to_experiments).split('/')[0].split('\\')[0]
                raise ExperimentPathViolation(
                    artifact_path,
                    experiment_id,
                    f"Artifact path belongs to experiment '{wrong_experiment}', "
                    f"not '{experiment_id}'. Cross-experiment writes are forbidden."
                )
            except ValueError:
                raise ExperimentPathViolation(
                    artifact_path,
                    experiment_id,
                    f"Artifact path {artifact_path} is not in any experiment directory. "
                    f"All artifacts must be in data/public/experiments/{experiment_id}/"
                )
        
        return False
    except Exception as e:
        if raise_on_violation:
            raise
        return False


def enforce_experiment_paths(experiment_id: str) -> None:
    """
    Context check: Ensure the active experiment path exists and is exclusive.
    
    Call this at pipeline start to validate the experiment is properly isolated.
    
    Args:
        experiment_id: The active experiment ID
    
    Raises:
        ValueError: If experiment paths are not properly configured
    """
    experiment_path = get_experiment_artifact_path(experiment_id)
    
    # Ensure directory exists
    experiment_path.mkdir(parents=True, exist_ok=True)
    
    # Check for .experiment_id marker file
    marker_file = experiment_path / ".experiment_id"
    if marker_file.exists():
        stored_id = marker_file.read_text(encoding='utf-8').strip()
        if stored_id != experiment_id:
            raise ValueError(
                f"Experiment path conflict: {experiment_path} belongs to "
                f"'{stored_id}', not '{experiment_id}'"
            )
    else:
        # Create marker
        marker_file.write_text(experiment_id, encoding='utf-8')
    
    logger.info(f"Experiment path validated: {experiment_path}")


# =============================================================================
# DATA STRUCTURES
# =============================================================================

class ArtifactStatus(str, Enum):
    """Status of an artifact check."""
    OK = "ok"
    MISSING = "missing"
    EMPTY = "empty"
    INVALID = "invalid"
    PARSE_ERROR = "parse_error"


@dataclass
class ArtifactCheck:
    """Result of checking a single artifact."""
    artifact_name: str
    file_path: Path
    status: ArtifactStatus
    size_bytes: int = 0
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'artifact_name': self.artifact_name,
            'file_path': str(self.file_path),
            'status': self.status.value,
            'size_bytes': self.size_bytes,
            'error_message': self.error_message,
        }


@dataclass
class ArtifactContractReport:
    """Complete artifact contract verification report."""
    date: str
    experiment_id: str
    all_passed: bool
    artifacts: List[ArtifactCheck] = field(default_factory=list)
    forecast_entries_added: int = 0
    violations: List[str] = field(default_factory=list)
    verified_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + 'Z')
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'date': self.date,
            'experiment_id': self.experiment_id,
            'all_passed': self.all_passed,
            'artifacts': [a.to_dict() for a in self.artifacts],
            'forecast_entries_added': self.forecast_entries_added,
            'violations': self.violations,
            'verified_at': self.verified_at,
        }
    
    def print_report(self) -> None:
        """Print human-readable report."""
        import sys
        import io
        # Handle Windows encoding issues
        if sys.stdout.encoding and sys.stdout.encoding.lower() not in ('utf-8', 'utf8'):
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        
        if self.all_passed:
            print("\n" + "=" * 60)
            print("[OK] ARTIFACT CONTRACT VERIFIED")
            print("=" * 60)
            print(f"  Date:         {self.date}")
            print(f"  Experiment:   {self.experiment_id}")
            print(f"  Forecasts:    {self.forecast_entries_added} entries added")
            print("\n  Artifacts:")
            for a in self.artifacts:
                size_kb = a.size_bytes / 1024
                print(f"    [+] {a.artifact_name} ({size_kb:.1f} KB)")
            print("=" * 60 + "\n")
        else:
            print("\n" + "=" * 60)
            print("[FAIL] ARTIFACT CONTRACT VIOLATED")
            print("=" * 60)
            print(f"  Date:       {self.date}")
            print(f"  Experiment: {self.experiment_id}")
            print("\n  Violations:")
            for v in self.violations:
                print(f"    [x] {v}")
            print("\n  Artifact Status:")
            for a in self.artifacts:
                status_icon = "[+]" if a.status == ArtifactStatus.OK else "[x]"
                print(f"    {status_icon} {a.artifact_name}: {a.status.value}")
                if a.error_message:
                    print(f"        {a.error_message}")
            print("=" * 60 + "\n")


# =============================================================================
# ARTIFACT CHECKERS
# =============================================================================

def check_file_exists_and_valid(
    filepath: Path,
    artifact_name: str,
    min_size: int = 10,
) -> ArtifactCheck:
    """Check if a file exists and meets minimum size."""
    if not filepath.exists():
        return ArtifactCheck(
            artifact_name=artifact_name,
            file_path=filepath,
            status=ArtifactStatus.MISSING,
            error_message=f"File not found: {filepath}",
        )
    
    size = filepath.stat().st_size
    
    if size < min_size:
        return ArtifactCheck(
            artifact_name=artifact_name,
            file_path=filepath,
            status=ArtifactStatus.EMPTY,
            size_bytes=size,
            error_message=f"File too small ({size} bytes < {min_size} minimum)",
        )
    
    return ArtifactCheck(
        artifact_name=artifact_name,
        file_path=filepath,
        status=ArtifactStatus.OK,
        size_bytes=size,
    )


def check_json_valid(filepath: Path, artifact_name: str) -> ArtifactCheck:
    """Check if a JSON file is valid."""
    basic = check_file_exists_and_valid(
        filepath, artifact_name, MIN_FILE_SIZES.get(artifact_name, 50)
    )
    
    if basic.status != ArtifactStatus.OK:
        return basic
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            json.load(f)
        return basic
    except json.JSONDecodeError as e:
        return ArtifactCheck(
            artifact_name=artifact_name,
            file_path=filepath,
            status=ArtifactStatus.PARSE_ERROR,
            size_bytes=basic.size_bytes,
            error_message=f"Invalid JSON: {e}",
        )


def check_jsonl_valid(filepath: Path, artifact_name: str) -> tuple:
    """
    Check if a JSONL file is valid and count entries.
    
    Returns (ArtifactCheck, entry_count)
    """
    basic = check_file_exists_and_valid(
        filepath, artifact_name, MIN_FILE_SIZES.get(artifact_name, 10)
    )
    
    if basic.status != ArtifactStatus.OK:
        return basic, 0
    
    try:
        entry_count = 0
        with open(filepath, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if line:
                    json.loads(line)  # Validate each line
                    entry_count += 1
        
        return ArtifactCheck(
            artifact_name=artifact_name,
            file_path=filepath,
            status=ArtifactStatus.OK,
            size_bytes=basic.size_bytes,
        ), entry_count
    except json.JSONDecodeError as e:
        return ArtifactCheck(
            artifact_name=artifact_name,
            file_path=filepath,
            status=ArtifactStatus.PARSE_ERROR,
            size_bytes=basic.size_bytes,
            error_message=f"Invalid JSONL at line {line_num}: {e}",
        ), 0


def check_metadata_complete(filepath: Path) -> tuple:
    """
    Check if run_metadata has all required fields.
    
    Returns (ArtifactCheck, missing_fields)
    """
    basic = check_json_valid(filepath, 'run_metadata')
    
    if basic.status != ArtifactStatus.OK:
        return basic, []
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        missing = []
        for field in REQUIRED_METADATA_FIELDS:
            if field not in data:
                missing.append(field)
        
        if missing:
            return ArtifactCheck(
                artifact_name='run_metadata',
                file_path=filepath,
                status=ArtifactStatus.INVALID,
                size_bytes=basic.size_bytes,
                error_message=f"Missing required fields: {missing}",
            ), missing
        
        return basic, []
    except Exception as e:
        return ArtifactCheck(
            artifact_name='run_metadata',
            file_path=filepath,
            status=ArtifactStatus.PARSE_ERROR,
            size_bytes=basic.size_bytes,
            error_message=str(e),
        ), []


# =============================================================================
# MAIN VERIFICATION
# =============================================================================

def verify_run_artifacts(
    run_date: str = None,
    experiment_id: str = None,
    min_forecast_entries: int = 1,
) -> ArtifactContractReport:
    """
    Verify that all required artifacts exist for a run.
    
    Args:
        run_date: Date string (YYYY-MM-DD). Defaults to today.
        experiment_id: Experiment ID. Uses active experiment if None.
        min_forecast_entries: Minimum entries expected in forecast history.
    
    Returns:
        ArtifactContractReport with verification results
    """
    if run_date is None:
        run_date = date.today().isoformat()
    
    # Get experiment context
    try:
        from utils.experiment_manager import (
            get_experiment,
            get_active_experiment,
            get_ledger_path,
        )
        
        if experiment_id:
            experiment = get_experiment(experiment_id)
        else:
            experiment = get_active_experiment()
        
        if not experiment:
            return ArtifactContractReport(
                date=run_date,
                experiment_id='unknown',
                all_passed=False,
                violations=['No active experiment configured'],
            )
        
        experiment_id = experiment.experiment_id
        ledger_path = get_ledger_path(experiment_id)
        
    except ImportError as e:
        return ArtifactContractReport(
            date=run_date,
            experiment_id='unknown',
            all_passed=False,
            violations=[f'Could not import experiment_manager: {e}'],
        )
    
    artifacts = []
    violations = []
    
    # 1. Check forecast_history.jsonl
    history_path = ledger_path / "forecast_history.jsonl"
    history_check, entry_count = check_jsonl_valid(history_path, 'forecast_history.jsonl')
    artifacts.append(history_check)
    
    if history_check.status != ArtifactStatus.OK:
        violations.append(f"forecast_history.jsonl: {history_check.status.value}")
    elif entry_count < min_forecast_entries:
        violations.append(
            f"forecast_history.jsonl: Only {entry_count} entries "
            f"(minimum {min_forecast_entries} expected)"
        )
    
    # 2. Check daily_snapshot_YYYY-MM-DD.json
    snapshot_path = ledger_path / f"daily_snapshot_{run_date}.json"
    snapshot_check = check_json_valid(snapshot_path, f'daily_snapshot_{run_date}.json')
    artifacts.append(snapshot_check)
    
    if snapshot_check.status != ArtifactStatus.OK:
        violations.append(f"daily_snapshot: {snapshot_check.status.value}")
    
    # 3. Check run_metadata_YYYY-MM-DD.json
    metadata_path = ledger_path / f"run_metadata_{run_date}.json"
    metadata_check, missing_fields = check_metadata_complete(metadata_path)
    artifacts.append(metadata_check)
    
    if metadata_check.status != ArtifactStatus.OK:
        violations.append(f"run_metadata: {metadata_check.status.value}")
    if missing_fields:
        violations.append(f"run_metadata missing fields: {missing_fields}")
    
    # 4. Check daily_brief_YYYY-MM-DD.md (in reports directory)
    reports_path = Path(__file__).parent.parent / "data" / "reports"
    brief_path = reports_path / f"daily_brief_{run_date}.md"
    brief_check = check_file_exists_and_valid(
        brief_path, f'daily_brief_{run_date}.md', MIN_FILE_SIZES['daily_brief']
    )
    artifacts.append(brief_check)
    
    if brief_check.status != ArtifactStatus.OK:
        violations.append(f"daily_brief: {brief_check.status.value}")
    
    # Build report
    all_passed = len(violations) == 0
    
    return ArtifactContractReport(
        date=run_date,
        experiment_id=experiment_id,
        all_passed=all_passed,
        artifacts=artifacts,
        forecast_entries_added=entry_count,
        violations=violations,
    )


def require_run_artifacts(
    run_date: str = None,
    experiment_id: str = None,
) -> ArtifactContractReport:
    """
    Verify artifacts and raise exception if contract violated.
    
    Args:
        run_date: Date string (YYYY-MM-DD)
        experiment_id: Experiment ID
    
    Returns:
        ArtifactContractReport (only if all passed)
    
    Raises:
        RunArtifactViolation: If any artifact is missing or invalid
    """
    report = verify_run_artifacts(run_date, experiment_id)
    report.print_report()
    
    if not report.all_passed:
        raise RunArtifactViolation(
            f"Artifact contract violated for {report.date}",
            report.violations,
        )
    
    return report


# =============================================================================
# RUN METADATA BUILDER
# =============================================================================

@dataclass
class ScraperStats:
    """Statistics from a scraper run."""
    source_name: str
    items_fetched: int = 0
    items_stored: int = 0
    errors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'source': self.source_name,
            'fetched': self.items_fetched,
            'stored': self.items_stored,
            'errors': self.errors,
        }


class RunMetadataBuilder:
    """
    Builder for comprehensive run metadata.
    
    Collects statistics throughout the pipeline run and
    produces a complete run_metadata file.
    """
    
    def __init__(
        self,
        run_date: str = None,
        experiment_id: str = None,
    ):
        self.run_date = run_date or date.today().isoformat()
        self.start_time = datetime.utcnow()
        self.scraper_stats: Dict[str, ScraperStats] = {}
        self.scraper_failures: List[str] = []
        self.warnings: List[str] = []
        
        # Get experiment context
        try:
            from utils.experiment_manager import get_experiment_context
            self.context = get_experiment_context(experiment_id)
            self.experiment_id = self.context.experiment.experiment_id
            self.engine_tag = self.context.experiment.engine_tag
            self.commit_hash = self.context.commit_hash
        except Exception as e:
            logger.warning(f"Could not get experiment context: {e}")
            self.context = None
            self.experiment_id = experiment_id or 'unknown'
            self.engine_tag = 'unknown'
            self.commit_hash = 'unknown'
    
    def record_scraper(
        self,
        source_name: str,
        items_fetched: int,
        items_stored: int = None,
        errors: List[str] = None,
    ) -> None:
        """Record statistics from a scraper."""
        self.scraper_stats[source_name] = ScraperStats(
            source_name=source_name,
            items_fetched=items_fetched,
            items_stored=items_stored or items_fetched,
            errors=errors or [],
        )
        
        if errors:
            for e in errors:
                self.scraper_failures.append(f"{source_name}: {e}")
    
    def record_failure(self, source: str, message: str) -> None:
        """Record a scraper failure."""
        self.scraper_failures.append(f"{source}: {message}")
    
    def record_warning(self, message: str) -> None:
        """Record a warning."""
        self.warnings.append(message)
    
    def build(self, artifact_contract_passed: bool = True) -> Dict[str, Any]:
        """
        Build the complete run metadata with full environment fingerprint.
        
        Args:
            artifact_contract_passed: Result of artifact verification
        
        Returns:
            Complete metadata dict with:
            - Required experiment fields
            - Environment fingerprint (python, platform, deps)
            - Config directory hash
            - Engine commit verification
        """
        import platform
        import sys
        
        end_time = datetime.utcnow()
        duration_seconds = (end_time - self.start_time).total_seconds()
        
        # Build sources summary
        sources = {}
        for name, stats in self.scraper_stats.items():
            sources[name] = stats.items_stored
        
        # Compute environment fingerprint
        env_fingerprint = self._compute_environment_fingerprint()
        
        # Compute config directory hash
        config_hash = self._compute_config_hash()
        
        # Get engine commit hash for verification
        engine_commit = self._resolve_engine_commit()
        
        metadata = {
            # Required fields
            'experiment_id': self.experiment_id,
            'engine_tag': self.engine_tag,
            'commit_hash': self.commit_hash,
            'engine_commit_hash': engine_commit,
            'generation_timestamp': end_time.isoformat() + 'Z',
            'date': self.run_date,
            'artifact_contract_passed': artifact_contract_passed,
            
            # Extended fields
            'run_type': 'forward_test',
            'rerun_allowed': False,
            'start_time': self.start_time.isoformat() + 'Z',
            'end_time': end_time.isoformat() + 'Z',
            'duration_seconds': round(duration_seconds, 2),
            
            # Sources
            'sources': sources,
            'scraper_stats': {
                name: stats.to_dict() 
                for name, stats in self.scraper_stats.items()
            },
            'scraper_failures': self.scraper_failures,
            'warnings': self.warnings,
            
            # Environment fingerprint (research-grade reproducibility)
            'environment': env_fingerprint,
            
            # Config hash (detects config drift)
            'config_dir_hash': config_hash,
        }
        
        return metadata
    
    def _compute_environment_fingerprint(self) -> Dict[str, Any]:
        """
        Compute comprehensive environment fingerprint for reproducibility.
        
        Includes:
        - Python version and implementation
        - Platform details
        - Installed packages hash
        - Key dependency versions
        """
        import platform
        import sys
        import hashlib
        
        fingerprint = {
            'python_version': platform.python_version(),
            'python_implementation': platform.python_implementation(),
            'platform': f"{platform.system()} {platform.release()}",
            'platform_machine': platform.machine(),
            'platform_processor': platform.processor() or 'unknown',
        }
        
        # Try to get pip freeze hash
        try:
            import subprocess
            result = subprocess.run(
                [sys.executable, '-m', 'pip', 'freeze'],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                freeze_output = result.stdout.strip()
                fingerprint['pip_freeze_hash'] = hashlib.sha256(
                    freeze_output.encode('utf-8')
                ).hexdigest()[:16]
                
                # Extract key dependency versions
                key_deps = ['loguru', 'requests', 'openai', 'anthropic', 'numpy', 'pandas']
                for line in freeze_output.split('\n'):
                    for dep in key_deps:
                        if line.lower().startswith(dep + '=='):
                            fingerprint[f'dep_{dep}'] = line.split('==')[1]
        except Exception as e:
            fingerprint['pip_freeze_error'] = str(e)
        
        # Try to get requirements.txt hash
        try:
            req_path = Path(__file__).parent.parent / 'requirements.txt'
            if req_path.exists():
                content = req_path.read_text(encoding='utf-8')
                fingerprint['requirements_hash'] = hashlib.sha256(
                    content.encode('utf-8')
                ).hexdigest()[:16]
        except Exception:
            pass
        
        # Get embedding model if configured
        try:
            from utils.config_loader import load_config
            models_config = load_config('models.yaml')
            if models_config:
                fingerprint['embedding_model'] = models_config.get(
                    'embedding', {}).get('model', 'unknown'
                )
        except Exception:
            pass
        
        return fingerprint
    
    def _compute_config_hash(self) -> str:
        """
        Compute hash of all config/*.json files.
        
        This detects any config drift that could affect predictions.
        """
        import hashlib
        
        config_dir = Path(__file__).parent.parent / 'config'
        if not config_dir.exists():
            return 'config_dir_missing'
        
        hasher = hashlib.sha256()
        
        # Sort files for deterministic ordering
        config_files = sorted(config_dir.glob('*.json'))
        
        for config_file in config_files:
            try:
                content = config_file.read_text(encoding='utf-8')
                # Include filename in hash (so renaming is detected)
                hasher.update(f"{config_file.name}:{len(content)}:".encode('utf-8'))
                hasher.update(content.encode('utf-8'))
            except Exception:
                hasher.update(f"{config_file.name}:ERROR".encode('utf-8'))
        
        return hasher.hexdigest()[:16]
    
    def _resolve_engine_commit(self) -> Optional[str]:
        """Resolve the engine_tag to its commit hash."""
        try:
            import subprocess
            result = subprocess.run(
                ['git', 'rev-parse', self.engine_tag + '^{commit}'],
                capture_output=True,
                text=True,
                cwd=Path(__file__).parent.parent,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None
    
    def write(
        self,
        artifact_contract_passed: bool = True,
        experiment_id: str = None,
    ) -> Path:
        """
        Build and write the run metadata file.
        
        Returns:
            Path to the written file
        """
        from utils.experiment_manager import get_ledger_path
        
        metadata = self.build(artifact_contract_passed)
        
        ledger_path = get_ledger_path(experiment_id or self.experiment_id)
        metadata_path = ledger_path / f"run_metadata_{self.run_date}.json"
        
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Wrote run metadata: {metadata_path}")
        return metadata_path


# =============================================================================
# CLI
# =============================================================================

def main():
    """CLI entry point for artifact verification."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Verify run artifacts for a specific date'
    )
    parser.add_argument(
        '--date',
        default=date.today().isoformat(),
        help='Run date (YYYY-MM-DD)'
    )
    parser.add_argument(
        '--experiment',
        help='Experiment ID (uses active if not specified)'
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output as JSON'
    )
    
    args = parser.parse_args()
    
    report = verify_run_artifacts(
        run_date=args.date,
        experiment_id=args.experiment,
    )
    
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        report.print_report()
    
    return 0 if report.all_passed else 1


if __name__ == "__main__":
    exit(main())
