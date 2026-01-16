"""Tests for explain drawer component."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.components.explain_drawer import (
    ExplainDrawerData,
    build_explain_drawer_data,
)


class TestExplainDrawerData:
    """Tests for explain drawer data building."""

    def test_build_drawer_data(self):
        """Build drawer data from bucket profile."""
        # Mock profile-like dict
        profile = {
            "bucket_id": "ai-agents",
            "bucket_name": "Agent Frameworks",
            "tms": 85,
            "ccs": 42,
            "nas": 72,
            "eis_offensive": 61,
            "signal_confidence": 0.85,
            "top_technical_entities": ["langchain/langchain", "vllm-project/vllm"],
            "top_capital_entities": ["Pinecone"],
            "entity_count": 15,
        }

        signal_history = {
            "tms": [75, 78, 80, 82, 83, 84, 85, 85],
            "ccs": [35, 36, 38, 39, 40, 41, 42, 42],
        }

        drawer_data = build_explain_drawer_data(profile, signal_history)

        assert drawer_data.bucket_name == "Agent Frameworks"
        assert len(drawer_data.sparklines) >= 2
        assert drawer_data.data_quality_pct > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])