"""Integration tests for bucket dashboard with new components."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestAlertPanelIntegration:
    """Tests for alert panel integration."""

    def test_import_new_components(self):
        """Dashboard imports new components successfully."""
        from modules.components.alert_card import AlertCardRenderer, build_alert_card_data
        from utils.dashboard_helpers import get_confidence_style, format_persistence_text

        assert AlertCardRenderer is not None
        assert build_alert_card_data is not None
        assert get_confidence_style is not None
        assert format_persistence_text is not None

    def test_alert_store_integration(self):
        """Alert store can be used in dashboard."""
        from utils.alert_store import AlertStore
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            store = AlertStore(db_path=Path(f.name))
            alerts = store.get_active_alerts()
            assert isinstance(alerts, list)
            store.close()

    def test_bucket_dashboard_imports_enhanced_components(self):
        """Bucket dashboard module has enhanced imports."""
        from modules import bucket_dashboard

        # Check that enhanced components are imported
        assert hasattr(bucket_dashboard, 'AlertStore')
        assert hasattr(bucket_dashboard, 'AlertCardRenderer')
        assert hasattr(bucket_dashboard, 'build_alert_card_data')
        assert hasattr(bucket_dashboard, 'AlertCardData')
        assert hasattr(bucket_dashboard, 'format_persistence_text')
        assert hasattr(bucket_dashboard, 'get_severity_config')

    def test_render_alerts_panel_exists(self):
        """The render_alerts_panel function exists and is callable."""
        from modules.bucket_dashboard import render_alerts_panel

        assert callable(render_alerts_panel)

    def test_render_enhanced_alert_card_exists(self):
        """The _render_enhanced_alert_card helper function exists."""
        from modules.bucket_dashboard import _render_enhanced_alert_card

        assert callable(_render_enhanced_alert_card)

    def test_alert_card_data_creation(self):
        """AlertCardData can be created with required fields."""
        from utils.dashboard_helpers import AlertCardData, format_persistence_text

        card_data = AlertCardData(
            bucket_name="test-bucket",
            alert_type="alpha_zone",
            alert_name="Alpha Zone (Hidden Gem)",
            severity="WARN",
            confidence=0.75,
            evidence_text="5 entities",
            persistence_text=format_persistence_text(3),
            action_hint="Monitor for capital inflow",
            trigger_scores={"magnitude": 25, "threshold": 20},
        )

        assert card_data.bucket_name == "test-bucket"
        assert card_data.confidence == 0.75
        assert card_data.persistence_text == "3 weeks"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])