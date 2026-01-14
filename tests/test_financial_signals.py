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
    TokenFetcher,
    TokenData,
    MacroFetcher,
    MacroData,
    BucketSignalAggregator,
    BucketFinancialSignal,
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


class TestTokenFetcher(unittest.TestCase):
    """Test crypto token fetcher."""

    def test_token_data_model(self):
        """Test TokenData model structure."""
        data = TokenData(
            symbol="FET",
            asof=datetime.now(),
            price_usd=2.15,
            change_1d_pct=5.2,
            change_7d_pct=12.8,
            change_30d_pct=-8.4,
            volume_24h_usd=180000000
        )
        self.assertEqual(data.symbol, "FET")
        self.assertAlmostEqual(data.price_usd, 2.15)

    def test_fetcher_init(self):
        """Test TokenFetcher initialization."""
        fetcher = TokenFetcher()
        self.assertIsNotNone(fetcher.tokens)
        self.assertIn("FET", fetcher.tokens)

    @patch('utils.financial_signals.ccxt.kraken')
    def test_fetch_returns_list(self, mock_kraken):
        """Test fetch returns list of TokenData."""
        # Mock ccxt response
        mock_exchange = MagicMock()
        mock_exchange.fetch_ticker.return_value = {
            'last': 2.15,
            'percentage': 5.2,
            'quoteVolume': 180000000,
        }
        mock_exchange.fetch_ohlcv.return_value = [
            [1, 2.0, 2.2, 1.9, 2.1, 1000],  # 7d ago
            [2, 2.1, 2.3, 2.0, 2.15, 1000],  # now
        ]
        mock_kraken.return_value = mock_exchange

        fetcher = TokenFetcher(tokens=["FET"])
        result = fetcher.fetch()

        self.assertIsInstance(result, list)


class TestMacroFetcher(unittest.TestCase):
    """Test DBnomics macro fetcher."""

    def test_macro_data_model(self):
        """Test MacroData model structure."""
        data = MacroData(
            series_id="FRED/VIXCLS",
            name="VIX Volatility",
            asof=datetime.now(),
            value=18.5,
            z_score=0.3
        )
        self.assertEqual(data.series_id, "FRED/VIXCLS")
        self.assertAlmostEqual(data.value, 18.5)

    def test_fetcher_init(self):
        """Test MacroFetcher initialization."""
        fetcher = MacroFetcher()
        self.assertIsNotNone(fetcher.series)
        self.assertGreater(len(fetcher.series), 0)

    def test_compute_mrs(self):
        """Test MRS computation from z-scores."""
        fetcher = MacroFetcher()
        macro_data = [
            MacroData("FRED/VIXCLS", "VIX", datetime.now(), 18.5, z_score=0.3),
            MacroData("FRED/FEDFUNDS", "Fed Rate", datetime.now(), 5.25, z_score=1.2),
            MacroData("FRED/UNRATE", "Unemployment", datetime.now(), 3.9, z_score=-0.4),
        ]
        mrs = fetcher.compute_mrs(macro_data)
        self.assertIsInstance(mrs, float)
        self.assertGreaterEqual(mrs, -1.0)
        self.assertLessEqual(mrs, 1.0)


class TestBucketSignalAggregator(unittest.TestCase):
    """Test bucket signal aggregation."""

    def test_bucket_signal_model(self):
        """Test BucketFinancialSignal model."""
        signal = BucketFinancialSignal(
            bucket_id="ai-chips",
            pms=78.0,
            pms_coverage={"tickers_present": 5, "tickers_total": 6},
            pms_contributors=[{"ticker": "NVDA", "change_7d_pct": 8.1}],
            css=None,
            css_coverage=None,
        )
        self.assertEqual(signal.bucket_id, "ai-chips")
        self.assertEqual(signal.pms, 78.0)
        self.assertIsNone(signal.css)

    def test_aggregator_computes_pms(self):
        """Test PMS computation from equity data."""
        aggregator = BucketSignalAggregator()

        equity_data = [
            EquityData("NVDA", datetime.now(), 900, 2.0, 8.0, 15.0, 50000000, 40000000, 2200),
            EquityData("AMD", datetime.now(), 180, 1.5, 5.0, 10.0, 30000000, 25000000, 280),
        ]

        signals = aggregator.compute_bucket_signals(equity_data=equity_data)

        self.assertIsInstance(signals, dict)
        self.assertIn("ai-chips", signals)
        self.assertIsNotNone(signals["ai-chips"].pms)

    def test_aggregator_computes_css(self):
        """Test CSS computation from token data."""
        aggregator = BucketSignalAggregator()

        token_data = [
            TokenData("FET", datetime.now(), 2.15, 5.0, 12.0, -8.0, 180000000),
        ]

        signals = aggregator.compute_bucket_signals(token_data=token_data)

        self.assertIsInstance(signals, dict)
        self.assertIn("agent-orchestration", signals)
        self.assertIsNotNone(signals["agent-orchestration"].css)


if __name__ == "__main__":
    unittest.main()
