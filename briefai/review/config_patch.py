"""
Config Patch Generator

Converts review suggestions into structured config patches.
Patches are proposals only - never auto-applied.

NO LLM USAGE. All mappings are deterministic.
"""

import json
import hashlib
from datetime import date
from pathlib import Path
from typing import Optional


# Mapping from suggestion targets to config file paths and parameter locations
CONFIG_MAPPINGS = {
    "confidence_cap": {
        "config_file": "config/signal_config.json",
        "parameter_paths": {
            "global": "confidence.global_multiplier",
            "high": "confidence.bucket_caps.high",
            "very_high": "confidence.bucket_caps.very_high",
        },
        "default_path": "confidence.global_multiplier",
    },
    "mechanism_weight": {
        "config_file": "config/mechanism_taxonomy.json",
        "parameter_paths": {
            # Dynamic: mechanisms.{mechanism_name}.weight
        },
        "path_template": "mechanisms.{mechanism}.weight",
    },
    "media_only_threshold": {
        "config_file": "config/evidence_weights.json",
        "parameter_paths": {
            "min_sources": "validation.media_only.min_sources",
            "require_multi_source": "validation.media_only.require_multi_source",
        },
        "default_path": "validation.media_only.min_sources",
    },
    "check_date_policy": {
        "config_file": "config/signal_config.json",
        "parameter_paths": {
            "default_timeframe": "prediction.default_timeframe_days",
            "max_timeframe": "prediction.max_timeframe_days",
        },
        "default_path": "prediction.default_timeframe_days",
    },
    "signal_retention": {
        "config_file": "config/signal_config.json",
        "parameter_paths": {
            "retention_days": "storage.signal_retention_days",
        },
        "default_path": "storage.signal_retention_days",
    },
    "data_coverage": {
        "config_file": "config/sources.json",
        "parameter_paths": {
            # Informational only - manual expansion required
        },
        "is_informational": True,
    },
}


def generate_patch_id(suggestion_id: str, parameter_path: str, review_date: date) -> str:
    """Generate a deterministic patch ID."""
    raw = f"{suggestion_id}:{parameter_path}:{review_date.isoformat()}"
    return f"patch_{hashlib.sha256(raw.encode()).hexdigest()[:12]}"


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


def suggestion_to_patches(
    suggestion: dict,
    config_root: Path,
    review_date: date,
) -> list[dict]:
    """
    Convert a single suggestion into config patches.
    
    Returns list of patch dicts, each with:
    - patch_id
    - config_file
    - parameter_path
    - old_value
    - proposed_value
    - rationale
    - source_suggestion_id
    - requires_manual_review (always True)
    """
    patches = []
    target = suggestion.get("target", "")
    proposed = suggestion.get("proposed_change", {})
    
    if target not in CONFIG_MAPPINGS:
        # Unknown target - create informational patch
        patches.append({
            "patch_id": generate_patch_id(suggestion["suggestion_id"], "unknown", review_date),
            "config_file": None,
            "parameter_path": None,
            "old_value": None,
            "proposed_value": proposed,
            "rationale": f"[INFORMATIONAL] {suggestion.get('rationale', '')}",
            "source_suggestion_id": suggestion["suggestion_id"],
            "requires_manual_review": True,
            "is_actionable": False,
        })
        return patches
    
    mapping = CONFIG_MAPPINGS[target]
    
    # Handle informational-only suggestions
    if mapping.get("is_informational"):
        patches.append({
            "patch_id": generate_patch_id(suggestion["suggestion_id"], "informational", review_date),
            "config_file": mapping.get("config_file"),
            "parameter_path": None,
            "old_value": None,
            "proposed_value": proposed,
            "rationale": f"[MANUAL EXPANSION REQUIRED] {suggestion.get('rationale', '')}",
            "source_suggestion_id": suggestion["suggestion_id"],
            "requires_manual_review": True,
            "is_actionable": False,
        })
        return patches
    
    config_file = mapping["config_file"]
    config_path = config_root / config_file
    
    # Load current config to get old values
    current_config = {}
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            current_config = json.load(f)
    
    # Generate patches based on suggestion type
    if target == "confidence_cap":
        action = proposed.get("action", "")
        
        if action == "reduce_confidence_multiplier":
            factor = proposed.get("factor", 0.85)
            param_path = mapping["default_path"]
            old_value = get_nested_value(current_config, param_path, 1.0)
            
            patches.append({
                "patch_id": generate_patch_id(suggestion["suggestion_id"], param_path, review_date),
                "config_file": config_file,
                "parameter_path": param_path,
                "old_value": old_value,
                "proposed_value": factor,
                "rationale": suggestion.get("rationale", ""),
                "source_suggestion_id": suggestion["suggestion_id"],
                "requires_manual_review": True,
                "is_actionable": True,
            })
        
        elif action == "cap_confidence_at_bucket":
            bucket = proposed.get("bucket", "high")
            max_conf = proposed.get("max_confidence", 0.8)
            param_path = f"confidence.bucket_caps.{bucket}"
            old_value = get_nested_value(current_config, param_path, 1.0)
            
            patches.append({
                "patch_id": generate_patch_id(suggestion["suggestion_id"], param_path, review_date),
                "config_file": config_file,
                "parameter_path": param_path,
                "old_value": old_value,
                "proposed_value": max_conf,
                "rationale": suggestion.get("rationale", ""),
                "source_suggestion_id": suggestion["suggestion_id"],
                "requires_manual_review": True,
                "is_actionable": True,
            })
    
    elif target == "mechanism_weight":
        mechanism = proposed.get("mechanism", "unknown")
        action = proposed.get("action", "")
        suggested_weight = proposed.get("suggested_weight", 1.0)
        
        param_path = mapping["path_template"].format(mechanism=mechanism)
        old_value = get_nested_value(current_config, param_path, 1.0)
        
        patches.append({
            "patch_id": generate_patch_id(suggestion["suggestion_id"], param_path, review_date),
            "config_file": config_file,
            "parameter_path": param_path,
            "old_value": old_value,
            "proposed_value": suggested_weight,
            "rationale": suggestion.get("rationale", ""),
            "source_suggestion_id": suggestion["suggestion_id"],
            "requires_manual_review": True,
            "is_actionable": True,
        })
    
    elif target == "media_only_threshold":
        action = proposed.get("action", "")
        
        if action == "require_multi_source":
            min_sources = proposed.get("min_sources", 2)
            param_path = mapping["parameter_paths"]["min_sources"]
            old_value = get_nested_value(current_config, param_path, 1)
            
            patches.append({
                "patch_id": generate_patch_id(suggestion["suggestion_id"], param_path, review_date),
                "config_file": config_file,
                "parameter_path": param_path,
                "old_value": old_value,
                "proposed_value": min_sources,
                "rationale": suggestion.get("rationale", ""),
                "source_suggestion_id": suggestion["suggestion_id"],
                "requires_manual_review": True,
                "is_actionable": True,
            })
    
    elif target == "check_date_policy":
        action = proposed.get("action", "")
        
        if action in ("reduce_default_timeframe", "prefer_shorter_timeframes"):
            suggested_days = proposed.get("suggested_days", 10)
            param_path = mapping["parameter_paths"]["default_timeframe"]
            old_value = get_nested_value(current_config, param_path, 14)
            
            patches.append({
                "patch_id": generate_patch_id(suggestion["suggestion_id"], param_path, review_date),
                "config_file": config_file,
                "parameter_path": param_path,
                "old_value": old_value,
                "proposed_value": suggested_days,
                "rationale": suggestion.get("rationale", ""),
                "source_suggestion_id": suggestion["suggestion_id"],
                "requires_manual_review": True,
                "is_actionable": True,
            })
    
    elif target == "signal_retention":
        action = proposed.get("action", "")
        
        if action == "extend_signal_retention":
            suggested_days = proposed.get("suggested_days", 14)
            param_path = mapping["default_path"]
            old_value = get_nested_value(current_config, param_path, 7)
            
            patches.append({
                "patch_id": generate_patch_id(suggestion["suggestion_id"], param_path, review_date),
                "config_file": config_file,
                "parameter_path": param_path,
                "old_value": old_value,
                "proposed_value": suggested_days,
                "rationale": suggestion.get("rationale", ""),
                "source_suggestion_id": suggestion["suggestion_id"],
                "requires_manual_review": True,
                "is_actionable": True,
            })
    
    return patches


def generate_config_patches(
    suggestions_path: Path,
    config_root: Path = None,
    output_dir: Path = None,
) -> dict:
    """
    Generate config patches from suggestions file.
    
    Args:
        suggestions_path: Path to suggestions_YYYY-MM-DD.json
        config_root: Root directory containing config/ folder
        output_dir: Directory to write config_patch_YYYY-MM-DD.json
    
    Returns:
        Patch document dict
    """
    if config_root is None:
        config_root = Path(__file__).parent.parent.parent
    
    if output_dir is None:
        output_dir = suggestions_path.parent
    
    # Load suggestions
    with open(suggestions_path, "r", encoding="utf-8") as f:
        suggestions_doc = json.load(f)
    
    review_date = date.fromisoformat(suggestions_doc["review_date"])
    suggestions = suggestions_doc.get("suggestions", [])
    
    # Convert each suggestion to patches
    all_patches = []
    for suggestion in suggestions:
        patches = suggestion_to_patches(suggestion, config_root, review_date)
        all_patches.extend(patches)
    
    # Build output document
    patch_doc = {
        "review_date": review_date.isoformat(),
        "generated_from": str(suggestions_path.name),
        "total_patches": len(all_patches),
        "actionable_patches": sum(1 for p in all_patches if p.get("is_actionable")),
        "safety_notice": "All patches require manual review and approval before application.",
        "patches": all_patches,
    }
    
    # Write output
    output_path = output_dir / f"config_patch_{review_date.isoformat()}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(patch_doc, f, indent=2, ensure_ascii=False)
    
    return patch_doc


def load_patch_document(patch_path: Path) -> dict:
    """Load and validate a patch document."""
    with open(patch_path, "r", encoding="utf-8") as f:
        doc = json.load(f)
    
    # Validate required fields
    required = ["review_date", "patches"]
    for field in required:
        if field not in doc:
            raise ValueError(f"Patch document missing required field: {field}")
    
    return doc


def validate_patch(patch: dict, config_root: Path) -> tuple[bool, str]:
    """
    Validate a single patch.
    
    Returns (is_valid, message)
    """
    if not patch.get("is_actionable"):
        return True, "Informational patch - no validation needed"
    
    config_file = patch.get("config_file")
    if not config_file:
        return False, "Missing config_file"
    
    config_path = config_root / config_file
    if not config_path.exists():
        return False, f"Config file not found: {config_file}"
    
    param_path = patch.get("parameter_path")
    if not param_path:
        return False, "Missing parameter_path"
    
    proposed = patch.get("proposed_value")
    if proposed is None:
        return False, "Missing proposed_value"
    
    return True, "Valid"
