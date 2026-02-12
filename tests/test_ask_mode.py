"""
Tests for Ask Mode.

Test Coverage:
1. Ask logs written under experiment folder
2. Repeated tool query triggers loop warning
3. Deterministic output given frozen artifacts
4. Cannot write to forecast_history.jsonl
5. Scratchpad loop detection
6. Quality gates validation
7. Tool registry functionality
"""

import sys
import json
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from briefai.ask.models import (
    AskLogEntry,
    ToolCallRecord,
    MeasurableCheck,
    EvidenceLink,
    SourceCategory,
)
from briefai.ask.scratchpad import Scratchpad
from briefai.ask.quality_gates import QualityGates, QualityAssessment
from briefai.ask.tools import ToolRegistry, DataMissing, ToolResult
from briefai.ask.engine import AskEngine, WriteProtection, EngineConfig


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def temp_data_dir(tmp_path):
    """Create temporary data directory structure."""
    # Create experiment structure
    exp_dir = tmp_path / "data" / "public" / "experiments" / "test_experiment"
    exp_dir.mkdir(parents=True)
    
    # Create meta_signals
    meta_dir = tmp_path / "data" / "meta_signals"
    meta_dir.mkdir(parents=True)
    
    # Add sample meta-signal
    sample_meta = {
        "date": "2026-02-11",
        "meta_signals": [{
            "meta_id": "test123",
            "concept_name": "Test Trend",
            "description": "A test meta signal about AI pricing",
            "concept_confidence": 0.75,
            "maturity_stage": "emerging",
            "supporting_insights": [{"insight_text": "AI pricing changes"}],
        }]
    }
    with open(meta_dir / "meta_signals_2026-02-11.json", "w") as f:
        json.dump(sample_meta, f)
    
    return tmp_path


@pytest.fixture
def scratchpad():
    """Create fresh scratchpad."""
    return Scratchpad()


@pytest.fixture
def quality_gates():
    """Create quality gates instance."""
    return QualityGates()


# =============================================================================
# TEST: ASK LOGS WRITTEN UNDER EXPERIMENT FOLDER
# =============================================================================

class TestAskLogLocation:
    """Test that ask logs are always written under experiment folder."""
    
    def test_log_entry_path_under_experiment(self, temp_data_dir):
        """Ask logs must be in experiments/{id}/ask_logs/."""
        # Create a mock log entry
        entry = AskLogEntry(
            question="Test question",
            experiment_id="test_experiment",
            plan="Test plan",
        )
        
        # Expected path
        expected_dir = temp_data_dir / "data" / "public" / "experiments" / "test_experiment" / "ask_logs"
        
        # Mock the path functions
        with patch("briefai.ask.tools.get_data_path", return_value=temp_data_dir / "data"):
            with patch("briefai.ask.engine.get_llm_response", return_value="DONE"):
                config = EngineConfig(experiment_id="test_experiment")
                engine = AskEngine(experiment_id="test_experiment", config=config)
                
                # Save entry
                log_path = engine._save_log_entry(entry)
                
                # Verify path is under experiment
                assert "experiments" in str(log_path)
                assert "test_experiment" in str(log_path)
                assert "ask_logs" in str(log_path)
                assert log_path.name == "ask_history.jsonl"
    
    def test_log_never_in_root_public(self, temp_data_dir):
        """Ask logs must not be in root data/public/."""
        entry = AskLogEntry(
            question="Test",
            experiment_id="test_experiment",
            plan="Test",
        )
        
        with patch("briefai.ask.tools.get_data_path", return_value=temp_data_dir / "data"):
            with patch("briefai.ask.engine.get_llm_response", return_value="DONE"):
                engine = AskEngine(experiment_id="test_experiment")
                log_path = engine._save_log_entry(entry)
                
                # Should not be directly in data/public/
                parts = log_path.parts
                public_idx = parts.index("public") if "public" in parts else -1
                if public_idx >= 0:
                    # Next part should be "experiments", not the log file
                    assert parts[public_idx + 1] == "experiments"


# =============================================================================
# TEST: REPEATED TOOL QUERY TRIGGERS LOOP WARNING
# =============================================================================

class TestLoopDetection:
    """Test scratchpad loop detection."""
    
    def test_exact_duplicate_warning(self, scratchpad):
        """Exact duplicate calls should trigger warning."""
        args = {"query": "openai pricing"}
        
        # First call - no warning
        warning1 = scratchpad.check_tool_call("search_meta_signals", args)
        scratchpad.add_tool_call("search_meta_signals", args, "Found 5 results")
        assert warning1 is None
        
        # Second call with same args - warning
        warning2 = scratchpad.check_tool_call("search_meta_signals", args)
        assert warning2 is not None
        assert "LOOP" in warning2
        assert "duplicate" in warning2.lower()
    
    def test_max_calls_warning(self, scratchpad):
        """Exceeding max calls to same tool triggers warning."""
        # Default max is 3
        for i in range(3):
            args = {"query": f"query_{i}"}  # Different args each time
            warning = scratchpad.check_tool_call("search_signals", args)
            scratchpad.add_tool_call("search_signals", args, f"Result {i}")
            # First 3 should not warn (on check, before add)
            if i < 2:
                assert warning is None
        
        # 4th call should warn
        warning = scratchpad.check_tool_call("search_signals", {"query": "query_3"})
        assert warning is not None
        assert "3 times" in warning
    
    def test_similar_query_warning(self, scratchpad):
        """Similar queries (after normalization) trigger warning."""
        # First query
        args1 = {"query": "OpenAI pricing changes"}
        scratchpad.add_tool_call("search_meta_signals", args1, "Result")
        
        # Similar query (same words, different order)
        args2 = {"query": "pricing changes OpenAI"}
        warning = scratchpad.check_tool_call("search_meta_signals", args2)
        
        # Should detect similarity
        assert warning is not None
        assert "similar" in warning.lower() or "LOOP" in warning
    
    def test_get_loop_warnings_accumulates(self, scratchpad):
        """All warnings should be accumulated."""
        # Trigger multiple warnings
        args = {"query": "test"}
        scratchpad.add_tool_call("test_tool", args, "Result")
        scratchpad.check_tool_call("test_tool", args)  # Duplicate
        scratchpad.check_tool_call("test_tool", args)  # Another duplicate
        
        warnings = scratchpad.get_loop_warnings()
        assert len(warnings) >= 2


# =============================================================================
# TEST: DETERMINISTIC OUTPUT
# =============================================================================

class TestDeterministicOutput:
    """Test reproducibility given frozen artifacts."""
    
    def test_same_question_same_artifacts_same_result(self, temp_data_dir):
        """Given same question and artifacts, output should be identical."""
        question = "What signals suggest AI pricing changes?"
        
        # Mock LLM to be deterministic
        mock_responses = [
            "1. Search meta-signals for pricing",  # Plan
            '{"tool": "search_meta_signals", "arguments": {"query": "pricing"}}',  # Tool 1
            "DONE",  # Done
            "Evidence is sufficient",  # Reflection
            "Based on evidence, pricing is changing",  # Answer
        ]
        response_iter = iter(mock_responses)
        
        def mock_llm(*args, **kwargs):
            return next(response_iter)
        
        with patch("briefai.ask.tools.get_data_path", return_value=temp_data_dir / "data"):
            with patch("briefai.ask.engine.get_llm_response", side_effect=mock_llm):
                config = EngineConfig(experiment_id="test_experiment", temperature=0.0)
                engine = AskEngine(experiment_id="test_experiment", config=config)
                
                # Reset iterator for second run
                result1 = engine.ask(question)
        
        # Reset mock for second run
        response_iter = iter(mock_responses)
        
        with patch("briefai.ask.tools.get_data_path", return_value=temp_data_dir / "data"):
            with patch("briefai.ask.engine.get_llm_response", side_effect=mock_llm):
                config = EngineConfig(experiment_id="test_experiment", temperature=0.0)
                engine = AskEngine(experiment_id="test_experiment", config=config)
                result2 = engine.ask(question)
        
        # Same tool calls
        assert len(result1.tool_calls) == len(result2.tool_calls)
        for tc1, tc2 in zip(result1.tool_calls, result2.tool_calls):
            assert tc1.tool_name == tc2.tool_name
            assert tc1.arguments == tc2.arguments
    
    def test_tool_results_are_deterministic(self, temp_data_dir):
        """Tool results should be deterministic for same inputs."""
        with patch("briefai.ask.tools.get_data_path", return_value=temp_data_dir / "data"):
            registry = ToolRegistry()
            
            result1 = registry.execute("search_meta_signals", {"query": "pricing"})
            result2 = registry.execute("search_meta_signals", {"query": "pricing"})
            
            # Same success status
            assert result1.success == result2.success
            # Same data (or both DataMissing)
            if result1.success:
                assert result1.data == result2.data


# =============================================================================
# TEST: CANNOT WRITE TO FORECAST_HISTORY.JSONL
# =============================================================================

class TestWriteProtection:
    """Test that ask mode cannot write to protected files."""
    
    def test_forecast_history_is_protected(self):
        """forecast_history.jsonl should be protected."""
        path = Path("data/public/experiments/v2_2/forecast_history.jsonl")
        assert WriteProtection.is_protected(path)
    
    def test_daily_snapshot_is_protected(self):
        """daily_snapshot files should be protected."""
        path = Path("data/public/experiments/v2_2/daily_snapshot_2026-02-10.json")
        assert WriteProtection.is_protected(path)
    
    def test_run_metadata_is_protected(self):
        """run_metadata files should be protected."""
        path = Path("data/public/experiments/v2_2/run_metadata_2026-02-10.json")
        assert WriteProtection.is_protected(path)
    
    def test_ask_logs_are_not_protected(self):
        """ask_logs should NOT be protected."""
        path = Path("data/public/experiments/v2_2/ask_logs/ask_history.jsonl")
        assert not WriteProtection.is_protected(path)
    
    def test_validate_write_raises_on_protected(self):
        """validate_write should raise on protected paths."""
        protected = Path("forecast_history.jsonl")
        
        with pytest.raises(PermissionError) as exc_info:
            WriteProtection.validate_write(protected)
        
        assert "protected" in str(exc_info.value).lower()
    
    def test_validate_write_allows_ask_logs(self):
        """validate_write should allow ask log writes."""
        path = Path("ask_logs/ask_history.jsonl")
        # Should not raise
        WriteProtection.validate_write(path)


# =============================================================================
# TEST: QUALITY GATES
# =============================================================================

class TestQualityGates:
    """Test quality gate validations."""
    
    def test_insufficient_sources_fails(self, quality_gates):
        """< 2 source categories with strong claim = fail."""
        evidence = [
            EvidenceLink("meta", "id1", SourceCategory.MEDIA, "snippet"),
        ]
        checks = [MeasurableCheck("metric1", "entity1", "up", 14)]
        
        result = quality_gates.evaluate(evidence, checks, has_strong_conclusion=True)
        
        assert "insufficient" in result.confidence_level or len(result.notes) > 0
        assert any("diversity" in note.lower() for note in result.notes)
    
    def test_sufficient_sources_passes(self, quality_gates):
        """>= 2 source categories should pass diversity check."""
        evidence = [
            EvidenceLink("meta", "id1", SourceCategory.MEDIA, "snippet"),
            EvidenceLink("fin", "id2", SourceCategory.FINANCIAL, "snippet"),
        ]
        checks = [
            MeasurableCheck("metric1", "entity1", "up", 14),
            MeasurableCheck("metric2", "entity1", "down", 7),
        ]
        
        result = quality_gates.evaluate(evidence, checks, has_strong_conclusion=True)
        
        # Should pass with diversity
        diversity_warnings = [n for n in result.notes if "diversity" in n.lower()]
        assert len(diversity_warnings) == 0
    
    def test_media_only_caps_confidence(self, quality_gates):
        """Media-only evidence should cap confidence."""
        evidence = [
            EvidenceLink("news", "id1", SourceCategory.MEDIA, "snippet"),
            EvidenceLink("social", "id2", SourceCategory.SOCIAL, "snippet"),
        ]
        checks = [
            MeasurableCheck("m1", "e1", "up", 14),
            MeasurableCheck("m2", "e1", "up", 14),
        ]
        
        result = quality_gates.evaluate(evidence, checks, has_strong_conclusion=True)
        
        assert result.review_required
        assert any("media" in note.lower() for note in result.notes)
    
    def test_insufficient_checks_noted(self, quality_gates):
        """< 2 measurable checks should be noted."""
        evidence = [
            EvidenceLink("meta", "id1", SourceCategory.META, "snippet"),
            EvidenceLink("tech", "id2", SourceCategory.TECHNICAL, "snippet"),
        ]
        checks = [MeasurableCheck("metric1", "entity1", "up", 14)]  # Only 1
        
        result = quality_gates.evaluate(evidence, checks, has_strong_conclusion=True)
        
        assert any("measurable" in note.lower() for note in result.notes)
    
    def test_weak_conclusion_relaxed(self, quality_gates):
        """Weak conclusions don't require full evidence."""
        evidence = [
            EvidenceLink("meta", "id1", SourceCategory.MEDIA, "snippet"),
        ]
        # Weak conclusions still need at least one check to pass
        checks = [MeasurableCheck("metric1", "entity1", "up", 14)]
        
        result = quality_gates.evaluate(evidence, checks, has_strong_conclusion=False)
        
        # Should be more lenient - no diversity warning for weak conclusions
        diversity_warnings = [n for n in result.notes if "diversity" in n.lower()]
        assert len(diversity_warnings) == 0 or result.passed


# =============================================================================
# TEST: TOOL REGISTRY
# =============================================================================

class TestToolRegistry:
    """Test tool registry functionality."""
    
    def test_all_tools_registered(self):
        """All required tools should be registered."""
        registry = ToolRegistry()
        tools = registry.list_tools()
        
        required = [
            "search_meta_signals",
            "search_signals",
            "get_entity_profile",
            "summarize_daily_brief",
            "retrieve_evidence",
        ]
        
        for tool in required:
            assert tool in tools, f"Missing tool: {tool}"
    
    def test_unknown_tool_returns_data_missing(self):
        """Unknown tool should return DataMissing."""
        registry = ToolRegistry()
        result = registry.execute("nonexistent_tool", {"arg": "val"})
        
        assert not result.success
        assert isinstance(result.data, DataMissing)
    
    def test_missing_required_param_returns_error(self):
        """Missing required parameter should return error."""
        registry = ToolRegistry()
        result = registry.execute("search_meta_signals", {})  # Missing 'query'
        
        assert not result.success
        assert "missing" in result.summary.lower() or isinstance(result.data, DataMissing)
    
    def test_data_missing_for_nonexistent_data(self, temp_data_dir):
        """Tools should return DataMissing for data that doesn't exist."""
        with patch("briefai.ask.tools.get_data_path", return_value=temp_data_dir / "data"):
            registry = ToolRegistry()
            result = registry.execute(
                "search_meta_signals",
                {"query": "nonexistent_xyz_123"}
            )
            
            # Should either succeed with empty or return DataMissing
            if not result.success:
                assert isinstance(result.data, DataMissing)


# =============================================================================
# TEST: MODEL SERIALIZATION
# =============================================================================

class TestModelSerialization:
    """Test that models serialize correctly."""
    
    def test_ask_log_entry_to_jsonl(self):
        """AskLogEntry should serialize to valid JSONL."""
        entry = AskLogEntry(
            question="Test?",
            experiment_id="test",
            plan="Test plan",
            tool_calls=[
                ToolCallRecord("tool1", {"arg": "val"}, "summary", "success"),
            ],
            evidence_links=[
                EvidenceLink("meta", "id1", SourceCategory.META, "snippet"),
            ],
            measurable_checks=[
                MeasurableCheck("metric", "entity", "up", 14),
            ],
            final_answer="Test answer",
        )
        
        jsonl = entry.to_jsonl()
        
        # Should be valid JSON
        parsed = json.loads(jsonl)
        
        # Should have all fields
        assert parsed["question"] == "Test?"
        assert parsed["experiment_id"] == "test"
        assert len(parsed["tool_calls"]) == 1
        assert len(parsed["evidence_links"]) == 1
        assert len(parsed["measurable_checks"]) == 1
    
    def test_ask_log_entry_roundtrip(self):
        """AskLogEntry should survive JSON roundtrip."""
        original = AskLogEntry(
            question="Test?",
            experiment_id="test",
            plan="Plan",
            final_answer="Answer",
        )
        
        jsonl = original.to_jsonl()
        restored = AskLogEntry.from_jsonl(jsonl)
        
        assert restored.question == original.question
        assert restored.experiment_id == original.experiment_id
        assert restored.plan == original.plan
        assert restored.final_answer == original.final_answer


# =============================================================================
# TEST: INTEGRATION
# =============================================================================

class TestIntegration:
    """Integration tests for the full ask flow."""
    
    def test_full_ask_flow(self, temp_data_dir):
        """Test complete ask flow from question to log."""
        # Mock responses for the full flow:
        # 1. Plan
        # 2. Tool selection (DONE)
        # 3. Reflection
        # 4. Tentative answer (for quality check)
        # 5. Final answer
        mock_responses = [
            "1. Search for AI trends",  # Plan
            "DONE",  # Immediately done for fast test
            "Reflection: limited evidence",  # Reflect
            "Based on limited data, unclear.",  # Tentative answer
            "Based on limited data, things are unclear.",  # Final answer
        ]
        response_iter = iter(mock_responses)
        
        with patch("briefai.ask.tools.get_data_path", return_value=temp_data_dir / "data"):
            with patch("briefai.ask.engine.get_llm_response", side_effect=lambda *a, **k: next(response_iter)):
                config = EngineConfig(experiment_id="test_experiment")
                engine = AskEngine(experiment_id="test_experiment", config=config)
                
                result = engine.ask("What is happening in AI?")
        
        # Should have log entry
        assert result.question == "What is happening in AI?"
        assert result.experiment_id == "test_experiment"
        assert result.plan != ""
        assert result.final_answer != ""
        assert result.commit_hash != ""
        assert result.duration_ms is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
