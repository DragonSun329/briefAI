"""
Run Lock - Experimental Integrity Verification v1.0

Ensures every pipeline run is:
- Auditable (exact commit known)
- Reproducible (clean working tree)
- Experiment-aware (correct engine tag)
- Tamper-evident (no mid-experiment code changes)

This is the FIRST thing that runs in the pipeline.
If verification fails, the run MUST abort.

Research integrity guarantee:
    A third party can checkout the same commit, run the pipeline,
    and reproduce the same forecast structure and methodology.
"""

import subprocess
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from enum import Enum

from loguru import logger


# =============================================================================
# CONSTANTS
# =============================================================================

# Directories containing source code that must be clean
PROTECTED_DIRECTORIES = [
    'utils',
    'scripts',
    'modules',
    'agents',
    'config',
]

# File extensions that must be clean
PROTECTED_EXTENSIONS = {'.py', '.json', '.yaml', '.yml', '.md'}

# Files that are allowed to be modified (data outputs)
ALLOWED_MODIFIED_PATTERNS = [
    'data/',
    'logs/',
    '.cache/',
    '__pycache__/',
    '*.pyc',
    '.env',
    'node_modules/',
]


# =============================================================================
# ENUMS
# =============================================================================

class LockFailureReason(str, Enum):
    """Reasons why run lock verification can fail."""
    NO_EXPERIMENT = "no_active_experiment"
    ENGINE_TAG_MISMATCH = "engine_tag_mismatch"
    DIRTY_WORKING_TREE = "dirty_working_tree"
    NOT_DESCENDANT_OF_TAG = "not_descendant_of_engine_tag"
    GIT_ERROR = "git_command_error"
    EXPERIMENT_NOT_ACTIVE = "experiment_not_active"


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class RunIntegrityReport:
    """
    Report of run integrity verification.
    
    If valid=False, the pipeline MUST NOT proceed.
    """
    valid: bool
    experiment_id: Optional[str]
    engine_tag: Optional[str]
    current_commit: Optional[str]
    commit_short: Optional[str]
    dirty_files: List[str] = field(default_factory=list)
    failure_reason: Optional[LockFailureReason] = None
    failure_message: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    verified_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + 'Z')
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'valid': self.valid,
            'experiment_id': self.experiment_id,
            'engine_tag': self.engine_tag,
            'current_commit': self.current_commit,
            'commit_short': self.commit_short,
            'dirty_files': self.dirty_files,
            'failure_reason': self.failure_reason.value if self.failure_reason else None,
            'failure_message': self.failure_message,
            'warnings': self.warnings,
            'verified_at': self.verified_at,
        }
    
    def print_report(self) -> None:
        """Print human-readable report."""
        import sys
        import io
        # Handle Windows encoding issues
        if sys.stdout.encoding and sys.stdout.encoding.lower() not in ('utf-8', 'utf8'):
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        
        if self.valid:
            print("\n" + "=" * 60)
            print("[OK] RUN INTEGRITY VERIFIED")
            print("=" * 60)
            print(f"  Experiment:  {self.experiment_id}")
            print(f"  Engine Tag:  {self.engine_tag}")
            print(f"  Commit:      {self.commit_short}")
            print(f"  Verified:    {self.verified_at}")
            if self.warnings:
                print("\n  [!] Warnings:")
                for w in self.warnings:
                    print(f"    - {w}")
            print("=" * 60 + "\n")
        else:
            print("\n" + "=" * 60)
            print("[FAIL] RUN INTEGRITY FAILED - ABORTING")
            print("=" * 60)
            print(f"  Reason: {self.failure_reason.value if self.failure_reason else 'Unknown'}")
            print(f"  Details: {self.failure_message}")
            if self.dirty_files:
                print("\n  Dirty files:")
                for f in self.dirty_files[:10]:
                    print(f"    - {f}")
                if len(self.dirty_files) > 10:
                    print(f"    ... and {len(self.dirty_files) - 10} more")
            print("\n  To fix:")
            if self.failure_reason == LockFailureReason.DIRTY_WORKING_TREE:
                print("    git add -A && git commit -m 'pre-run commit'")
            elif self.failure_reason == LockFailureReason.ENGINE_TAG_MISMATCH:
                print("    git checkout <correct-tag>")
                print("    OR update experiments.json to match current engine")
            elif self.failure_reason == LockFailureReason.NO_EXPERIMENT:
                print("    Set 'active_experiment' in config/experiments.json")
            print("=" * 60 + "\n")


# =============================================================================
# GIT HELPERS
# =============================================================================

def _run_git_command(args: List[str], cwd: Path = None) -> tuple:
    """
    Run a git command and return (success, output).
    """
    if cwd is None:
        cwd = Path(__file__).parent.parent
    
    try:
        result = subprocess.run(
            ['git'] + args,
            capture_output=True,
            text=True,
            cwd=cwd,
        )
        return result.returncode == 0, result.stdout.strip()
    except Exception as e:
        return False, str(e)


def get_current_commit() -> Optional[str]:
    """Get the current git commit hash."""
    success, output = _run_git_command(['rev-parse', 'HEAD'])
    return output if success else None


def get_current_commit_short() -> Optional[str]:
    """Get the current git commit hash (short form)."""
    success, output = _run_git_command(['rev-parse', '--short', 'HEAD'])
    return output if success else None


def get_dirty_files() -> List[str]:
    """
    Get list of modified files in protected directories.
    
    Returns only files that would invalidate reproducibility.
    """
    success, output = _run_git_command(['status', '--porcelain'])
    
    if not success:
        return ['<git status failed>']
    
    if not output:
        return []
    
    dirty = []
    for line in output.split('\n'):
        if not line.strip():
            continue
        
        # Parse git status output (first 2 chars are status, then space, then path)
        status = line[:2]
        filepath = line[3:].strip()
        
        # Skip untracked files in allowed locations
        if status == '??':
            if any(filepath.startswith(p.rstrip('/')) for p in ALLOWED_MODIFIED_PATTERNS):
                continue
        
        # Check if file is in protected directory
        is_protected = False
        for protected_dir in PROTECTED_DIRECTORIES:
            if filepath.startswith(protected_dir + '/') or filepath.startswith(protected_dir + '\\'):
                # Check extension
                ext = Path(filepath).suffix.lower()
                if ext in PROTECTED_EXTENSIONS:
                    is_protected = True
                    break
        
        # Also check root-level protected files
        if not is_protected:
            ext = Path(filepath).suffix.lower()
            if ext in PROTECTED_EXTENSIONS:
                # Root-level files like AGENTS.md, etc.
                if '/' not in filepath and '\\' not in filepath:
                    is_protected = True
        
        if is_protected:
            dirty.append(filepath)
    
    return dirty


def is_descendant_of_tag(tag: str) -> tuple:
    """
    Check if current HEAD is a descendant of the given tag.
    
    Returns (is_descendant, relationship_description)
    """
    # First, check if the tag exists
    success, _ = _run_git_command(['rev-parse', tag])
    if not success:
        return False, f"Tag '{tag}' does not exist"
    
    # Check if HEAD is the tag itself
    success, tag_commit = _run_git_command(['rev-parse', tag + '^{commit}'])
    if not success:
        return False, f"Could not resolve tag '{tag}'"
    
    success, head_commit = _run_git_command(['rev-parse', 'HEAD'])
    if not success:
        return False, "Could not get HEAD commit"
    
    if tag_commit == head_commit:
        return True, "HEAD is exactly at tag"
    
    # Check if HEAD is a descendant (tag is an ancestor of HEAD)
    success, _ = _run_git_command(['merge-base', '--is-ancestor', tag, 'HEAD'])
    if success:
        # Get distance from tag
        success, distance = _run_git_command(['rev-list', '--count', f'{tag}..HEAD'])
        if success:
            return True, f"HEAD is {distance} commits ahead of tag"
        return True, "HEAD is ahead of tag"
    
    return False, f"HEAD is not a descendant of '{tag}'"


def is_exact_engine_commit(tag: str) -> tuple:
    """
    Check if current HEAD is EXACTLY at the engine tag commit.
    
    For research-grade reproducibility, we require exact commit match,
    not just descendant. This prevents running on commits that may have
    untested changes.
    
    Returns (is_exact, tag_commit_hash, relationship_description)
    """
    # First, check if the tag exists
    success, _ = _run_git_command(['rev-parse', tag])
    if not success:
        return False, None, f"Tag '{tag}' does not exist"
    
    # Resolve tag to commit hash
    success, tag_commit = _run_git_command(['rev-parse', tag + '^{commit}'])
    if not success:
        return False, None, f"Could not resolve tag '{tag}'"
    
    # Get HEAD commit
    success, head_commit = _run_git_command(['rev-parse', 'HEAD'])
    if not success:
        return False, None, "Could not get HEAD commit"
    
    if tag_commit == head_commit:
        return True, tag_commit, "HEAD is exactly at engine tag"
    
    # Check relationship for helpful error message
    success, _ = _run_git_command(['merge-base', '--is-ancestor', tag, 'HEAD'])
    if success:
        success, distance = _run_git_command(['rev-list', '--count', f'{tag}..HEAD'])
        if success:
            return False, tag_commit, f"HEAD is {distance} commits AHEAD of engine tag - checkout {tag} to run pipeline"
        return False, tag_commit, f"HEAD is ahead of engine tag - checkout {tag} to run pipeline"
    
    # Check if tag is ahead of HEAD
    success, _ = _run_git_command(['merge-base', '--is-ancestor', 'HEAD', tag])
    if success:
        return False, tag_commit, f"HEAD is BEHIND engine tag - checkout {tag} to run pipeline"
    
    return False, tag_commit, f"HEAD has diverged from engine tag - checkout {tag} to run pipeline"


def resolve_engine_commit_hash(experiment_id: str = None) -> Optional[str]:
    """
    Resolve the engine_tag to its commit hash.
    
    Args:
        experiment_id: Optional experiment ID. Uses active if None.
    
    Returns:
        Commit hash of the engine tag, or None if not found.
    """
    try:
        from utils.experiment_manager import get_active_experiment, get_experiment
        
        if experiment_id:
            experiment = get_experiment(experiment_id)
        else:
            experiment = get_active_experiment()
        
        if not experiment:
            return None
        
        engine_tag = experiment.engine_tag
        success, commit = _run_git_command(['rev-parse', engine_tag + '^{commit}'])
        return commit if success else None
    except Exception:
        return None


def get_closest_engine_tag() -> Optional[str]:
    """Get the closest ENGINE_* tag in history."""
    success, output = _run_git_command(['describe', '--tags', '--match', 'ENGINE_*', '--abbrev=0'])
    return output if success else None


# =============================================================================
# MAIN VERIFICATION
# =============================================================================

def verify_run_integrity(
    require_clean_tree: bool = True,
    require_tag_descendant: bool = True,
    require_exact_commit: bool = True,
) -> RunIntegrityReport:
    """
    Verify that the current state is valid for a pipeline run.
    
    Checks:
    1. Active experiment exists
    2. Engine tag is configured
    3. HEAD is EXACTLY at engine tag commit (research-grade requirement)
    4. Working tree is clean (no modified source code)
    
    Args:
        require_clean_tree: If True, fail on dirty working tree
        require_tag_descendant: If True, require HEAD to be at/after engine tag (legacy, overridden by exact)
        require_exact_commit: If True, require HEAD == engine_tag commit exactly (recommended)
    
    Returns:
        RunIntegrityReport with validation results
    
    Usage:
        report = verify_run_integrity()
        if not report.valid:
            report.print_report()
            sys.exit(1)
    
    Research Integrity:
        When require_exact_commit=True (default), the pipeline will only run
        if HEAD is exactly at the engine_tag commit. This ensures:
        - All predictions are made with auditable, frozen code
        - No untested commits sneak into production runs
        - Third parties can reproduce by checking out the exact tag
    """
    warnings = []
    
    # Get current commit
    current_commit = get_current_commit()
    commit_short = get_current_commit_short()
    
    if not current_commit:
        return RunIntegrityReport(
            valid=False,
            experiment_id=None,
            engine_tag=None,
            current_commit=None,
            commit_short=None,
            failure_reason=LockFailureReason.GIT_ERROR,
            failure_message="Could not determine current git commit",
        )
    
    # Load experiment configuration
    try:
        from utils.experiment_manager import get_active_experiment, load_experiments
        
        experiment = get_active_experiment()
        if not experiment:
            return RunIntegrityReport(
                valid=False,
                experiment_id=None,
                engine_tag=None,
                current_commit=current_commit,
                commit_short=commit_short,
                failure_reason=LockFailureReason.NO_EXPERIMENT,
                failure_message="No active experiment configured in experiments.json",
            )
        
        experiment_id = experiment.experiment_id
        engine_tag = experiment.engine_tag
        
        # Check experiment status
        if experiment.status not in ['active', 'pending']:
            warnings.append(f"Experiment status is '{experiment.status}'")
        
    except ImportError as e:
        return RunIntegrityReport(
            valid=False,
            experiment_id=None,
            engine_tag=None,
            current_commit=current_commit,
            commit_short=commit_short,
            failure_reason=LockFailureReason.GIT_ERROR,
            failure_message=f"Could not import experiment_manager: {e}",
        )
    
    # Check engine tag - exact commit match (research-grade)
    if require_exact_commit:
        is_exact, tag_commit, relationship = is_exact_engine_commit(engine_tag)
        if not is_exact:
            return RunIntegrityReport(
                valid=False,
                experiment_id=experiment_id,
                engine_tag=engine_tag,
                current_commit=current_commit,
                commit_short=commit_short,
                failure_reason=LockFailureReason.ENGINE_TAG_MISMATCH,
                failure_message=f"HEAD must be exactly at {engine_tag}. {relationship}",
            )
    elif require_tag_descendant:
        # Legacy mode: allow descendants (less strict)
        is_descendant, relationship = is_descendant_of_tag(engine_tag)
        if not is_descendant:
            return RunIntegrityReport(
                valid=False,
                experiment_id=experiment_id,
                engine_tag=engine_tag,
                current_commit=current_commit,
                commit_short=commit_short,
                failure_reason=LockFailureReason.NOT_DESCENDANT_OF_TAG,
                failure_message=f"Current HEAD is not a descendant of {engine_tag}: {relationship}",
            )
        
        # Warn if not exact match
        if "ahead" in relationship:
            warnings.append(f"WARNING: Running on descendant commit, not exact tag. {relationship}")
    
    # Check working tree cleanliness
    dirty_files = get_dirty_files()
    
    if require_clean_tree and dirty_files:
        return RunIntegrityReport(
            valid=False,
            experiment_id=experiment_id,
            engine_tag=engine_tag,
            current_commit=current_commit,
            commit_short=commit_short,
            dirty_files=dirty_files,
            failure_reason=LockFailureReason.DIRTY_WORKING_TREE,
            failure_message=f"Working tree has {len(dirty_files)} modified source file(s)",
        )
    
    # All checks passed
    return RunIntegrityReport(
        valid=True,
        experiment_id=experiment_id,
        engine_tag=engine_tag,
        current_commit=current_commit,
        commit_short=commit_short,
        dirty_files=dirty_files,  # May have non-protected dirty files
        warnings=warnings,
    )


def require_run_integrity() -> RunIntegrityReport:
    """
    Verify run integrity and abort if invalid.
    
    This is the main entry point for pipeline integration.
    Prints report and raises exception if invalid.
    
    Returns:
        RunIntegrityReport (only if valid)
    
    Raises:
        RuntimeError: If verification fails
    """
    report = verify_run_integrity()
    report.print_report()
    
    if not report.valid:
        raise RuntimeError(
            f"Run integrity check failed: {report.failure_reason.value}. "
            f"{report.failure_message}"
        )
    
    return report


# =============================================================================
# CONTEXT MANAGER
# =============================================================================

class RunLock:
    """
    Context manager for locked pipeline runs.
    
    Usage:
        with RunLock() as lock:
            # Pipeline code here
            # Guaranteed to have valid experiment context
            print(lock.report.experiment_id)
    
    Research-Grade Mode (default):
        Requires HEAD to be exactly at engine_tag commit.
        This is stricter than legacy mode but ensures reproducibility.
    """
    
    def __init__(
        self,
        require_clean: bool = True,
        require_tag: bool = True,
        require_exact: bool = True,
    ):
        self.require_clean = require_clean
        self.require_tag = require_tag
        self.require_exact = require_exact
        self.report: Optional[RunIntegrityReport] = None
    
    def __enter__(self) -> 'RunLock':
        self.report = verify_run_integrity(
            require_clean_tree=self.require_clean,
            require_tag_descendant=self.require_tag,
            require_exact_commit=self.require_exact,
        )
        self.report.print_report()
        
        if not self.report.valid:
            raise RuntimeError(
                f"Run lock failed: {self.report.failure_reason.value}"
            )
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass  # No cleanup needed


# =============================================================================
# CLI
# =============================================================================

def main():
    """CLI entry point for run lock verification."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Verify run integrity for pipeline execution'
    )
    parser.add_argument(
        '--no-clean-check',
        action='store_true',
        help='Skip working tree cleanliness check'
    )
    parser.add_argument(
        '--no-tag-check',
        action='store_true',
        help='Skip engine tag descendancy check'
    )
    parser.add_argument(
        '--no-exact-check',
        action='store_true',
        help='Allow descendants of engine tag (less strict, not recommended for production)'
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output as JSON'
    )
    
    args = parser.parse_args()
    
    report = verify_run_integrity(
        require_clean_tree=not args.no_clean_check,
        require_tag_descendant=not args.no_tag_check,
        require_exact_commit=not args.no_exact_check,
    )
    
    if args.json:
        import json
        print(json.dumps(report.to_dict(), indent=2))
    else:
        report.print_report()
    
    return 0 if report.valid else 1


if __name__ == "__main__":
    exit(main())
