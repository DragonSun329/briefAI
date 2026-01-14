"""Tests for financial signals module."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime
from utils.financial_signals import (
    EquityFetcher,
    EquityData,
)


class TestEquityFetcher(unittest.TestCase):
    """Test Yahoo Finance equity fetcher."""

    def test_equity_data_model(self):
        """Test EquityData model structure."""
        data = EquityData(
            ticker="NVDA",
            asof=datetime.now(),
            price=892.50,
            change_1d_pct=2.3,
            change_7d_pct=8.1,
            change_30d_pct=15.4,
            volume=45000000,
            volume_avg_30d=38000000,
            market_cap_b=2210.0
        )
        self.assertEqual(data.ticker, "NVDA")
        self.assertAlmostEqual(data.volume_ratio, 1.18, places=2)

    def test_fetcher_init(self):
        """Test EquityFetcher initialization."""
        fetcher = EquityFetcher()
        self.assertIsNotNone(fetcher.tickers)
        self.assertIn("NVDA", fetcher.tickers)

    @patch('utils.financial_signals.yf.Tickers')
    def test_fetch_returns_list(self, mock_tickers):
        """Test fetch returns list of EquityData."""
        # Mock yfinance response
        mock_ticker = MagicMock()
        mock_ticker.info = {
            'regularMarketPrice': 892.50,
            'regularMarketVolume': 45000000,
            'averageVolume': 38000000,
            'marketCap': 2210000000000,
        }
        mock_ticker.history.return_value = MagicMock()
        mock_ticker.history.return_value.empty = False
        mock_ticker.history.return_value.__getitem__ = lambda self, key: MagicMock(
            iloc=MagicMock(__getitem__=lambda s, i: 850.0 if i == 0 else 892.5)
        )

        mock_tickers.return_value.tickers = {"NVDA": mock_ticker}

        fetcher = EquityFetcher(tickers=["NVDA"])
        result = fetcher.fetch()

        self.assertIsInstance(result, list)


if __name__ == "__main__":
    unittest.main()
