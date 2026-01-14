"""Integration tests for financial signals pipeline."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import unittest
import tempfile
from datetime import date
from unittest.mock import patch, MagicMock


class TestFinancialSignalsIntegration(unittest.TestCase):
    """Test full financial signals pipeline."""

    @patch('utils.financial_signals.yf.Tickers')
    @patch('utils.financial_signals.ccxt.kraken')
    @patch('utils.financial_signals.dbnomics.fetch_series')
    def test_full_pipeline(self, mock_dbnomics, mock_kraken, mock_yf):
        """Test full pipeline with mocked data sources."""
        from utils.financial_signals import generate_financial_signals

        # Mock Yahoo Finance
        mock_ticker = MagicMock()
        mock_ticker.info = {
            'regularMarketPrice': 900.0,
            'regularMarketVolume': 50000000,
            'averageVolume': 40000000,
            'marketCap': 2200000000000,
        }
        mock_hist = MagicMock()
        mock_hist.empty = False
        mock_hist.__getitem__ = lambda s, k: MagicMock(
            iloc=MagicMock(__getitem__=lambda s, i: 850.0)
        )
        mock_ticker.history.return_value = mock_hist
        mock_yf.return_value.tickers = {"NVDA": mock_ticker}

        # Mock Kraken
        mock_exchange = MagicMock()
        mock_exchange.fetch_ticker.return_value = {
            'last': 2.15, 'percentage': 5.0, 'quoteVolume': 180000000
        }
        mock_exchange.fetch_ohlcv.return_value = [[1, 2, 2.2, 1.9, 2.0, 1000]]
        mock_kraken.return_value = mock_exchange

        # Mock DBnomics
        import pandas as pd
        mock_df = pd.DataFrame({'value': [18.0, 18.5, 19.0, 18.5]})
        mock_dbnomics.return_value = mock_df

        # Run pipeline
        with tempfile.TemporaryDirectory() as tmpdir:
            output = generate_financial_signals(
                output_dir=Path(tmpdir),
                target_date=date.today()
            )

            # Verify output
            self.assertIsNotNone(output)
            self.assertIsInstance(output.mrs, float)
            self.assertIn(output.mrs_interpretation,
                         ["risk_off", "mildly_risk_off", "neutral", "mildly_risk_on", "risk_on"])

            # Check file was created
            output_file = Path(tmpdir) / f"financial_signals_{date.today().isoformat()}.json"
            self.assertTrue(output_file.exists())


if __name__ == "__main__":
    unittest.main()
