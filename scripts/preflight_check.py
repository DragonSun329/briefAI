#!/usr/bin/env python3
"""
Pre-flight Check - Verify pipeline is ready to run.

Checks:
1. Active experiment configured
2. Git working tree clean (for protected files)
3. HEAD at correct engine tag
4. Required directories exist
5. Python dependencies available

Usage:
    python scripts/preflight_check.py
    python scripts/preflight_check.py --fix  # Suggests fix commands
"""

import sys
import subprocess
import io
from pathlib import Path
from datetime import date

# Fix Windows encoding issues
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ('utf-8', 'utf8'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, str(Path(__file__).parent.parent))

# ASCII-safe status symbols
OK = "[+]"
FAIL = "[X]"
SKIP = "[-]"


def check_git_status():
    """Check git status."""
    result = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], 
                          capture_output=True, text=True)
    current_commit = result.stdout.strip() if result.returncode == 0 else None
    
    result = subprocess.run(['git', 'status', '--porcelain'], 
                          capture_output=True, text=True)
    dirty_files = result.stdout.strip().split('\n') if result.stdout.strip() else []
    
    return current_commit, dirty_files


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Pre-flight check for daily pipeline')
    parser.add_argument('--fix', action='store_true', help='Show fix commands')
    args = parser.parse_args()
    
    print("\n" + "=" * 60)
    print("PRE-FLIGHT CHECK")
    print("=" * 60)
    
    issues = []
    fixes = []
    
    # Check 1: Active experiment
    print("\n[1] Checking experiment config...")
    try:
        from utils.experiment_manager import get_active_experiment
        exp = get_active_experiment()
        if exp:
            print(f"    {OK} Active experiment: {exp.experiment_id}")
            print(f"    {OK} Engine tag: {exp.engine_tag}")
            engine_tag = exp.engine_tag
        else:
            print(f"    {FAIL} No active experiment")
            issues.append("No active experiment in config/experiments.json")
            fixes.append("Set 'active_experiment' in config/experiments.json")
            engine_tag = None
    except Exception as e:
        print(f"    {FAIL} Error: {e}")
        issues.append(f"Cannot load experiment config: {e}")
        engine_tag = None
    
    # Check 2: Git status
    print("\n[2] Checking git status...")
    current_commit, dirty_files = check_git_status()
    
    if current_commit:
        print(f"    {OK} Current commit: {current_commit}")
    else:
        print(f"    {FAIL} Cannot determine current commit")
        issues.append("Git not available or not a git repository")
    
    # Check 3: Engine tag match
    print("\n[3] Checking engine tag alignment...")
    if engine_tag and current_commit:
        result = subprocess.run(['git', 'rev-parse', '--short', f'{engine_tag}^{{commit}}'],
                              capture_output=True, text=True)
        if result.returncode == 0:
            tag_commit = result.stdout.strip()
            if tag_commit == current_commit:
                print(f"    {OK} HEAD is at engine tag {engine_tag}")
            else:
                print(f"    {FAIL} HEAD ({current_commit}) != engine tag ({engine_tag} = {tag_commit})")
                issues.append(f"HEAD is not at engine tag {engine_tag}")
                fixes.append(f"git checkout {engine_tag}")
        else:
            print(f"    {FAIL} Engine tag {engine_tag} does not exist")
            issues.append(f"Engine tag {engine_tag} not found")
            fixes.append(f"git tag {engine_tag} HEAD  # Create tag at current commit")
    else:
        print(f"    {SKIP} Skipped (missing prerequisite)")
    
    # Check 4: Working tree cleanliness
    print("\n[4] Checking working tree...")
    protected_dirty = [f for f in dirty_files if f and 
                       any(f[3:].startswith(d) for d in ['utils/', 'scripts/', 'modules/', 'agents/', 'config/'])]
    
    if not dirty_files or dirty_files == ['']:
        print(f"    {OK} Working tree clean")
    elif not protected_dirty:
        print(f"    {SKIP} {len(dirty_files)} files modified (data/logs only, OK)")
    else:
        print(f"    {FAIL} {len(protected_dirty)} protected files modified")
        for f in protected_dirty[:5]:
            print(f"       - {f}")
        issues.append("Protected source files modified")
        fixes.append("git stash  # or commit changes before running pipeline")
    
    # Check 5: Required directories
    print("\n[5] Checking directories...")
    required_dirs = [
        'data/public/experiments',
        'data/gravity',
        'data/reports',
        'logs',
    ]
    
    for d in required_dirs:
        path = Path(__file__).parent.parent / d
        if path.exists():
            print(f"    {OK} {d}/")
        else:
            print(f"    {FAIL} {d}/ missing")
            issues.append(f"Directory {d} does not exist")
            fixes.append(f"mkdir -p {d}")
    
    # Check 6: Python dependencies
    print("\n[6] Checking Python modules...")
    required_modules = [
        ('utils.run_lock', 'Run lock'),
        ('utils.public_forecast_logger', 'Forecast logger'),
        ('utils.experiment_manager', 'Experiment manager'),
        ('modules.daily_brief', 'Daily brief generator'),
    ]
    
    for module, name in required_modules:
        try:
            __import__(module)
            print(f"    {OK} {name}")
        except ImportError as e:
            print(f"    {FAIL} {name}: {e}")
            issues.append(f"Missing module: {module}")
    
    # Summary
    print("\n" + "=" * 60)
    
    if not issues:
        print(f"{OK} ALL CHECKS PASSED - Ready to run pipeline")
        print("=" * 60)
        print(f"\nRun: powershell -File scripts\\daily_bloomberg.ps1")
        return 0
    else:
        print(f"{FAIL} {len(issues)} ISSUE(S) FOUND")
        print("=" * 60)
        
        if args.fix:
            print("\nFIX COMMANDS:")
            for fix in fixes:
                print(f"  {fix}")
        else:
            print("\nRun with --fix to see suggested commands")
        
        return 1


if __name__ == "__main__":
    sys.exit(main())
