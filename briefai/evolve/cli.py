"""
Engine Evolution CLI

Applies approved config patches to evolve the engine.
Creates git commits and tags for reproducibility.

Usage:
    python -m briefai evolve --apply-patch data/reviews/config_patch_YYYY-MM-DD.json
    python -m briefai evolve --validate data/reviews/config_patch_YYYY-MM-DD.json
    python -m briefai evolve --dry-run data/reviews/config_patch_YYYY-MM-DD.json

NEVER modifies historical experiments or ledgers.
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


def set_nested_value(data: dict, path: str, value) -> dict:
    """Set a nested value in a dict using dot notation, creating parents as needed."""
    keys = path.split(".")
    current = data
    
    for key in keys[:-1]:
        if key not in current:
            current[key] = {}
        current = current[key]
    
    current[keys[-1]] = value
    return data


def get_nested_value(data: dict, path: str, default=None):
    """Get a nested value from a dict using dot notation."""
    keys = path.split(".")
    current = data
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default
    return current


def validate_patch_document(patch_path: Path, config_root: Path) -> tuple[bool, list[str]]:
    """
    Validate all patches in a document.
    
    Returns (all_valid, list_of_issues)
    """
    issues = []
    
    if not patch_path.exists():
        return False, [f"Patch file not found: {patch_path}"]
    
    try:
        with open(patch_path, "r", encoding="utf-8") as f:
            doc = json.load(f)
    except json.JSONDecodeError as e:
        return False, [f"Invalid JSON: {e}"]
    
    if "patches" not in doc:
        return False, ["Missing 'patches' field"]
    
    for i, patch in enumerate(doc["patches"]):
        # Skip informational patches
        if not patch.get("is_actionable"):
            continue
        
        config_file = patch.get("config_file")
        if not config_file:
            issues.append(f"Patch {i}: Missing config_file")
            continue
        
        config_path = config_root / config_file
        if not config_path.exists():
            issues.append(f"Patch {i}: Config file not found: {config_file}")
            continue
        
        param_path = patch.get("parameter_path")
        if not param_path:
            issues.append(f"Patch {i}: Missing parameter_path")
        
        if patch.get("proposed_value") is None:
            issues.append(f"Patch {i}: Missing proposed_value")
    
    return len(issues) == 0, issues


def get_current_engine_version(config_root: Path) -> tuple[int, int, int]:
    """
    Get current engine version from experiments config or git tags.
    
    Returns (major, minor, learning_count)
    """
    # Try to get from latest git tag
    try:
        result = subprocess.run(
            ["git", "tag", "--sort=-version:refname", "-l", "ENGINE_v*"],
            capture_output=True,
            text=True,
            cwd=config_root,
        )
        tags = result.stdout.strip().split("\n")
        for tag in tags:
            if tag.startswith("ENGINE_v"):
                # Parse ENGINE_v2.2_LEARNING_3 format
                parts = tag.replace("ENGINE_v", "").split("_")
                version = parts[0]  # "2.2"
                major, minor = map(int, version.split("."))
                
                if len(parts) > 2 and parts[1] == "LEARNING":
                    learning = int(parts[2])
                else:
                    learning = 0
                
                return major, minor, learning
    except Exception:
        pass
    
    # Default version
    return 2, 2, 0


def get_next_learning_tag(config_root: Path) -> str:
    """Generate the next learning tag."""
    major, minor, learning = get_current_engine_version(config_root)
    next_learning = learning + 1
    return f"ENGINE_v{major}.{minor}_LEARNING_{next_learning}"


def apply_patch(
    patch_path: Path,
    config_root: Path,
    dry_run: bool = False,
    verbose: bool = False,
) -> tuple[bool, str]:
    """
    Apply a config patch document.
    
    Args:
        patch_path: Path to config_patch_YYYY-MM-DD.json
        config_root: Root directory of the project
        dry_run: If True, only show what would be changed
        verbose: Show detailed output
    
    Returns:
        (success, message)
    """
    # Validate first
    valid, issues = validate_patch_document(patch_path, config_root)
    if not valid:
        return False, f"Validation failed:\n" + "\n".join(f"  - {i}" for i in issues)
    
    # Load patch document
    with open(patch_path, "r", encoding="utf-8") as f:
        doc = json.load(f)
    
    review_date = doc["review_date"]
    patches = doc["patches"]
    actionable = [p for p in patches if p.get("is_actionable")]
    
    if not actionable:
        return True, "No actionable patches to apply."
    
    if verbose or dry_run:
        print(f"[Evolve] Processing {len(actionable)} actionable patches from {review_date}")
    
    # Group patches by config file
    by_file = {}
    for patch in actionable:
        cf = patch["config_file"]
        if cf not in by_file:
            by_file[cf] = []
        by_file[cf].append(patch)
    
    modified_files = []
    
    for config_file, file_patches in by_file.items():
        config_path = config_root / config_file
        
        # Load current config
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        
        if verbose or dry_run:
            print(f"\n  {config_file}:")
        
        for patch in file_patches:
            param_path = patch["parameter_path"]
            old_value = patch["old_value"]
            new_value = patch["proposed_value"]
            
            current = get_nested_value(config, param_path)
            
            if verbose or dry_run:
                print(f"    {param_path}: {current} -> {new_value}")
            
            if not dry_run:
                set_nested_value(config, param_path, new_value)
        
        if not dry_run:
            # Write updated config
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            modified_files.append(config_file)
    
    if dry_run:
        return True, f"DRY RUN: Would modify {len(modified_files)} config files."
    
    # Create git commit
    tag = get_next_learning_tag(config_root)
    commit_message = f"""[Learning] Apply config patch from {review_date}

Applied {len(actionable)} patches:
{chr(10).join(f'- {p["parameter_path"]}: {p["old_value"]} -> {p["proposed_value"]}' for p in actionable)}

Source: {doc['generated_from']}
Tag: {tag}
"""
    
    if verbose:
        print(f"\n[Evolve] Creating git commit...")
    
    try:
        # Stage modified files
        for cf in modified_files:
            subprocess.run(
                ["git", "add", cf],
                cwd=config_root,
                check=True,
                capture_output=True,
            )
        
        # Create commit
        subprocess.run(
            ["git", "commit", "-m", commit_message],
            cwd=config_root,
            check=True,
            capture_output=True,
        )
        
        # Create tag
        subprocess.run(
            ["git", "tag", "-a", tag, "-m", f"Learning evolution from {review_date}"],
            cwd=config_root,
            check=True,
            capture_output=True,
        )
        
        if verbose:
            print(f"[Evolve] Created commit with tag: {tag}")
        
    except subprocess.CalledProcessError as e:
        return False, f"Git operation failed: {e.stderr.decode() if e.stderr else str(e)}"
    
    return True, f"Applied {len(actionable)} patches. Created tag: {tag}"


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="briefAI Engine Evolution System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Validate a patch file
  python -m briefai evolve --validate data/reviews/config_patch_2026-02-25.json

  # Dry-run (show what would change)
  python -m briefai evolve --dry-run data/reviews/config_patch_2026-02-25.json

  # Apply patches (requires approval)
  python -m briefai evolve --apply-patch data/reviews/config_patch_2026-02-25.json
        """,
    )
    
    parser.add_argument(
        "--validate",
        type=Path,
        metavar="PATCH_FILE",
        help="Validate a patch file without applying",
    )
    parser.add_argument(
        "--dry-run",
        type=Path,
        metavar="PATCH_FILE",
        help="Show what would be changed without applying",
    )
    parser.add_argument(
        "--apply-patch",
        type=Path,
        metavar="PATCH_FILE",
        help="Apply a patch file (creates git commit and tag)",
    )
    parser.add_argument(
        "--config-root",
        type=Path,
        default=None,
        help="Root directory of the project (default: auto-detect)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed progress",
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Skip confirmation prompt",
    )
    
    args = parser.parse_args()
    
    # Determine config root
    if args.config_root:
        config_root = args.config_root
    else:
        config_root = Path(__file__).parent.parent.parent
    
    # Validate
    if args.validate:
        valid, issues = validate_patch_document(args.validate, config_root)
        if valid:
            print(f"[OK] Patch file is valid: {args.validate}")
            return 0
        else:
            print(f"[ERROR] Validation failed:")
            for issue in issues:
                print(f"  - {issue}")
            return 1
    
    # Dry run
    if args.dry_run:
        success, message = apply_patch(
            args.dry_run,
            config_root,
            dry_run=True,
            verbose=True,
        )
        print(f"\n{message}")
        return 0 if success else 1
    
    # Apply patch
    if args.apply_patch:
        if not args.force:
            print(f"[!] About to apply patches from: {args.apply_patch}")
            print(f"    This will modify config files and create a git commit/tag.")
            response = input("    Continue? [y/N] ").strip().lower()
            if response != "y":
                print("Aborted.")
                return 1
        
        success, message = apply_patch(
            args.apply_patch,
            config_root,
            dry_run=False,
            verbose=args.verbose,
        )
        print(f"\n{message}")
        return 0 if success else 1
    
    # No action specified
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
