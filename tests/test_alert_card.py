"""Tests for alert card component."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.components.alert_card import (
    AlertCardRenderer,
    build_alert_card_data,
)
from utils.alert_store import StoredAlert


class TestBuildAlertCardData:
    """Tests for building alert card data."""

    def test_build_from_stored_alert(self):
        """Build card data from StoredAlert."""
        alert = StoredAlert(
            alert_id="test-123",
            bucket_id="ai-agents",
            bucket_name="Agent Frameworks",
            alert_type="alpha_zone",
            severity="WARN",
            interpretation="opportunity",
            first_detected="2026-01-01",
            last_updated="2026-01-15",
            weeks_persistent=2,
            trigger_scores={"tms": 92, "ccs": 28},
            evidence_payload={
                "top_repos": [{"name": "langchain"}],
                "top_articles": [{"title": "Article 1"}, {"title": "Article 2"}],
                "top_entities": [{"name": "Company 1"}],
            },
        )

        card_data = build_alert_card_data(alert, confidence=0.87)

        assert card_data.bucket_name == "Agent Frameworks"
        assert card_data.alert_type == "alpha_zone"
        assert card_data.persistence_text == "2 weeks"
        assert card_data.confidence == 0.87


class TestAlertCardRenderer:
    """Tests for alert card rendering."""

    def test_render_returns_html(self):
        """Renderer produces HTML string."""
        from utils.dashboard_helpers import AlertCardData

        card_data = AlertCardData(
            bucket_name="RAG & Retrieval",
            alert_type="alpha_zone",
            alert_name="Alpha Zone (Hidden Gem)",
            severity="WARN",
            confidence=0.87,
            evidence_text="12 repos, 47 articles, 3 companies",
            persistence_text="3 weeks",
            action_hint="Monitor for capital inflow",
            trigger_scores={"tms": 92, "ccs": 25},
        )

        renderer = AlertCardRenderer()
        html = renderer.render_card_html(card_data)

        assert "RAG & Retrieval" in html
        assert "Alpha Zone" in html
        assert "87%" in html or "0.87" in html


if __name__ == "__main__":
    pytest.main([__file__, "-v"])