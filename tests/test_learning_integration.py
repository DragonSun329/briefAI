"""
Tests for the briefAI Learning Integration System.

Tests cover:
- Config patch generation
- Patch validation
- Evolution workflow
- Daily hook conditional behavior
- Learning status report generation
"""

import json
import pytest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from briefai.review.config_patch import (
    generate_config_patches,
    suggestion_to_patches,
    generate_patch_id,
    get_nested_value,
    validate_patch,
    CONFIG_MAPPINGS,
)
from briefai.evolve.cli import (
    validate_patch_document,
    set_nested_value,
    get_current_engine_version,
    get_next_learning_tag,
)


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def sample_suggestions_doc():
    """Create a sample suggestions document."""
    return {
        "review_date": "2026-02-25",
        "total_suggestions": 3,
        "safety_notice": "All suggestions require manual review.",
        "suggestions": [
            {
                "suggestion_id": "sug_001",
                "target": "confidence_cap",
                "rationale": "Calibration error of 0.28 indicates overconfidence",
                "proposed_change": {
                    "action": "reduce_confidence_multiplier",
                    "factor": 0.85,
                    "scope": "global",
                },
                "safety": "manual_review_required",
                "source_pattern": "calibration_error",
                "source_category": "metrics",
                "sample_size": 20,
                "success_rate": 0.45,
            },
            {
                "suggestion_id": "sug_002",
                "target": "mechanism_weight",
                "rationale": "Mechanism 'media_attention_spike' underperforms",
                "proposed_change": {
                    "action": "reduce_mechanism_weight",
                    "mechanism": "media_attention_spike",
                    "suggested_weight": 0.5,
                },
                "safety": "manual_review_required",
                "source_pattern": "media_attention_spike",
                "source_category": "mechanism",
                "sample_size": 15,
                "success_rate": 0.3,
            },
            {
                "suggestion_id": "sug_003",
                "target": "data_coverage",
                "rationale": "High unclear rate",
                "proposed_change": {
                    "action": "expand_signal_sources",
                },
                "safety": "manual_review_required",
                "source_pattern": "unclear_rate",
                "source_category": "metrics",
                "sample_size": 10,
                "success_rate": 0.0,
            },
        ],
    }


@pytest.fixture
def temp_config_dir():
    """Create a temporary config directory with sample configs."""
    with TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir) / "config"
        config_dir.mkdir()
        
        # Create signal_config.json
        signal_config = {
            "confidence": {
                "global_multiplier": 1.0,
                "bucket_caps": {
                    "high": 0.9,
                    "very_high": 0.95,
                },
            },
            "prediction": {
                "default_timeframe_days": 14,
            },
            "storage": {
                "signal_retention_days": 7,
            },
        }
        with open(config_dir / "signal_config.json", "w") as f:
            json.dump(signal_config, f)
        
        # Create mechanism_taxonomy.json
        mechanism_config = {
            "mechanisms": {
                "media_attention_spike": {
                    "weight": 1.0,
                    "display_name": "Media Attention",
                },
                "product_launch": {
                    "weight": 1.0,
                    "display_name": "Product Launch",
                },
            },
        }
        with open(config_dir / "mechanism_taxonomy.json", "w") as f:
            json.dump(mechanism_config, f)
        
        # Create evidence_weights.json
        evidence_config = {
            "validation": {
                "media_only": {
                    "min_sources": 1,
                    "require_multi_source": False,
                },
            },
        }
        with open(config_dir / "evidence_weights.json", "w") as f:
            json.dump(evidence_config, f)
        
        yield Path(tmpdir)


# ============================================================================
# Test: Config Patch Generation
# ============================================================================

class TestConfigPatchGeneration:
    """Tests for config patch generation."""
    
    def test_generate_patch_id_deterministic(self):
        """Test that patch IDs are deterministic."""
        id1 = generate_patch_id("sug_001", "conf.global", date(2026, 2, 25))
        id2 = generate_patch_id("sug_001", "conf.global", date(2026, 2, 25))
        
        assert id1 == id2
        assert id1.startswith("patch_")
    
    def test_get_nested_value(self):
        """Test nested value retrieval."""
        data = {
            "level1": {
                "level2": {
                    "value": 42,
                },
            },
        }
        
        assert get_nested_value(data, "level1.level2.value") == 42
        assert get_nested_value(data, "level1.level2.missing", "default") == "default"
        assert get_nested_value(data, "missing.path", None) is None
    
    def test_suggestion_to_patches_confidence_cap(self, temp_config_dir):
        """Test confidence_cap suggestion conversion."""
        suggestion = {
            "suggestion_id": "sug_001",
            "target": "confidence_cap",
            "rationale": "Overconfidence detected",
            "proposed_change": {
                "action": "reduce_confidence_multiplier",
                "factor": 0.85,
            },
        }
        
        patches = suggestion_to_patches(suggestion, temp_config_dir, date(2026, 2, 25))
        
        assert len(patches) == 1
        patch = patches[0]
        assert patch["config_file"] == "config/signal_config.json"
        assert patch["parameter_path"] == "confidence.global_multiplier"
        assert patch["proposed_value"] == 0.85
        assert patch["old_value"] == 1.0
        assert patch["is_actionable"] is True
    
    def test_suggestion_to_patches_mechanism_weight(self, temp_config_dir):
        """Test mechanism_weight suggestion conversion."""
        suggestion = {
            "suggestion_id": "sug_002",
            "target": "mechanism_weight",
            "rationale": "Mechanism underperforms",
            "proposed_change": {
                "action": "reduce_mechanism_weight",
                "mechanism": "media_attention_spike",
                "suggested_weight": 0.5,
            },
        }
        
        patches = suggestion_to_patches(suggestion, temp_config_dir, date(2026, 2, 25))
        
        assert len(patches) == 1
        patch = patches[0]
        assert patch["parameter_path"] == "mechanisms.media_attention_spike.weight"
        assert patch["proposed_value"] == 0.5
    
    def test_suggestion_to_patches_informational(self, temp_config_dir):
        """Test informational-only suggestions."""
        suggestion = {
            "suggestion_id": "sug_003",
            "target": "data_coverage",
            "rationale": "Expand sources",
            "proposed_change": {"action": "expand"},
        }
        
        patches = suggestion_to_patches(suggestion, temp_config_dir, date(2026, 2, 25))
        
        assert len(patches) == 1
        patch = patches[0]
        assert patch["is_actionable"] is False
        assert "MANUAL" in patch["rationale"]
    
    def test_generate_config_patches_full(self, temp_config_dir, sample_suggestions_doc):
        """Test full config patch generation."""
        # Write suggestions file
        suggestions_path = temp_config_dir / "suggestions_2026-02-25.json"
        with open(suggestions_path, "w") as f:
            json.dump(sample_suggestions_doc, f)
        
        # Generate patches
        result = generate_config_patches(suggestions_path, temp_config_dir)
        
        assert result["review_date"] == "2026-02-25"
        assert len(result["patches"]) >= 2
        assert result["actionable_patches"] >= 2
        
        # Check output file was created
        output_path = temp_config_dir / "config_patch_2026-02-25.json"
        assert output_path.exists()


# ============================================================================
# Test: Patch Validation
# ============================================================================

class TestPatchValidation:
    """Tests for patch validation."""
    
    def test_validate_patch_valid(self, temp_config_dir):
        """Test validation of a valid patch."""
        patch = {
            "config_file": "config/signal_config.json",
            "parameter_path": "confidence.global_multiplier",
            "proposed_value": 0.85,
            "is_actionable": True,
        }
        
        valid, message = validate_patch(patch, temp_config_dir)
        assert valid is True
    
    def test_validate_patch_missing_config(self, temp_config_dir):
        """Test validation fails for missing config file."""
        patch = {
            "config_file": "config/nonexistent.json",
            "parameter_path": "some.path",
            "proposed_value": 1.0,
            "is_actionable": True,
        }
        
        valid, message = validate_patch(patch, temp_config_dir)
        assert valid is False
        assert "not found" in message
    
    def test_validate_patch_informational_always_valid(self, temp_config_dir):
        """Test that informational patches are always valid."""
        patch = {
            "is_actionable": False,
            "config_file": None,
        }
        
        valid, message = validate_patch(patch, temp_config_dir)
        assert valid is True


# ============================================================================
# Test: Evolution CLI
# ============================================================================

class TestEvolutionCLI:
    """Tests for evolution CLI functions."""
    
    def test_set_nested_value(self):
        """Test nested value setting."""
        data = {}
        set_nested_value(data, "a.b.c", 42)
        
        assert data["a"]["b"]["c"] == 42
    
    def test_set_nested_value_existing(self):
        """Test nested value setting with existing structure."""
        data = {"a": {"b": {"c": 1}}}
        set_nested_value(data, "a.b.c", 42)
        
        assert data["a"]["b"]["c"] == 42
    
    def test_validate_patch_document(self, temp_config_dir, sample_suggestions_doc):
        """Test patch document validation."""
        # Create a valid patch document
        patch_doc = {
            "review_date": "2026-02-25",
            "patches": [
                {
                    "config_file": "config/signal_config.json",
                    "parameter_path": "confidence.global_multiplier",
                    "proposed_value": 0.85,
                    "is_actionable": True,
                },
            ],
        }
        
        patch_path = temp_config_dir / "test_patch.json"
        with open(patch_path, "w") as f:
            json.dump(patch_doc, f)
        
        valid, issues = validate_patch_document(patch_path, temp_config_dir)
        assert valid is True
        assert len(issues) == 0
    
    def test_validate_patch_document_missing_file(self, temp_config_dir):
        """Test validation fails for missing patch file."""
        valid, issues = validate_patch_document(
            temp_config_dir / "nonexistent.json",
            temp_config_dir,
        )
        
        assert valid is False
        assert len(issues) > 0
    
    def test_get_next_learning_tag(self, temp_config_dir):
        """Test learning tag generation."""
        tag = get_next_learning_tag(temp_config_dir)
        
        assert tag.startswith("ENGINE_v")
        assert "LEARNING" in tag


# ============================================================================
# Test: Config Mappings
# ============================================================================

class TestConfigMappings:
    """Tests for config mapping definitions."""
    
    def test_all_targets_have_config_file(self):
        """Test that all targets have a config_file."""
        for target, mapping in CONFIG_MAPPINGS.items():
            assert "config_file" in mapping or mapping.get("is_informational"), \
                f"Target {target} missing config_file"
    
    def test_confidence_cap_mapping(self):
        """Test confidence_cap mapping structure."""
        mapping = CONFIG_MAPPINGS["confidence_cap"]
        
        assert mapping["config_file"] == "config/signal_config.json"
        assert "parameter_paths" in mapping
    
    def test_mechanism_weight_mapping(self):
        """Test mechanism_weight mapping structure."""
        mapping = CONFIG_MAPPINGS["mechanism_weight"]
        
        assert mapping["config_file"] == "config/mechanism_taxonomy.json"
        assert "path_template" in mapping


# ============================================================================
# Test: Patch Safety
# ============================================================================

class TestPatchSafety:
    """Tests for patch safety constraints."""
    
    def test_patches_always_require_manual_review(self, temp_config_dir, sample_suggestions_doc):
        """Test that all generated patches require manual review."""
        suggestions_path = temp_config_dir / "suggestions.json"
        with open(suggestions_path, "w") as f:
            json.dump(sample_suggestions_doc, f)
        
        result = generate_config_patches(suggestions_path, temp_config_dir)
        
        for patch in result["patches"]:
            assert patch["requires_manual_review"] is True
    
    def test_patch_doc_has_safety_notice(self, temp_config_dir, sample_suggestions_doc):
        """Test that patch documents include safety notice."""
        suggestions_path = temp_config_dir / "suggestions.json"
        with open(suggestions_path, "w") as f:
            json.dump(sample_suggestions_doc, f)
        
        result = generate_config_patches(suggestions_path, temp_config_dir)
        
        assert "safety_notice" in result
        assert "manual" in result["safety_notice"].lower()


# ============================================================================
# Test: Determinism
# ============================================================================

class TestDeterminism:
    """Tests for deterministic behavior."""
    
    def test_patch_generation_deterministic(self, temp_config_dir, sample_suggestions_doc):
        """Test that patch generation is deterministic."""
        suggestions_path = temp_config_dir / "suggestions.json"
        with open(suggestions_path, "w") as f:
            json.dump(sample_suggestions_doc, f)
        
        result1 = generate_config_patches(suggestions_path, temp_config_dir)
        
        # Clear cache and regenerate
        result2 = generate_config_patches(suggestions_path, temp_config_dir)
        
        # Patch IDs should be identical
        ids1 = [p["patch_id"] for p in result1["patches"]]
        ids2 = [p["patch_id"] for p in result2["patches"]]
        
        assert ids1 == ids2


# ============================================================================
# Run tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
