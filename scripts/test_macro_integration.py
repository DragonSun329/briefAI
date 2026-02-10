"""
Test script for macro-economic integration.

Tests:
1. Economic context provider
2. Regime classifier
3. Macro-aware signal calibrator
4. Integration with briefAI signals
"""

import sys
import json
import traceback
from pathlib import Path
from datetime import datetime, timedelta

# Unbuffered output
sys.stdout.reconfigure(line_buffering=True)

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from integrations.economic_context import EconomicContextProvider
from utils.regime_classifier import RegimeClassifier, classify_and_save, get_current_regime
from utils.signal_calibrator import MacroAwareCalibrator, calibrate_with_macro_context


def test_economic_context():
    """Test economic context provider."""
    print("=" * 60)
    print("TESTING ECONOMIC CONTEXT PROVIDER")
    print("=" * 60)
    
    provider = EconomicContextProvider()
    
    # Test interest rate analysis
    print("\n[Interest Rate Analysis]")
    rates = provider.get_interest_rate_analysis()
    print(f"  Rate environment: {rates.get('assessment', {}).get('rate_environment', 'unknown')}")
    print(f"  Fed funds: {rates.get('fed_policy', {}).get('fed_funds_rate')}")
    
    # Test VIX analysis
    print("\n[VIX Analysis]")
    vix = provider.get_vix_analysis()
    print(f"  Current VIX: {vix.get('current', 'N/A')}")
    print(f"  VIX Regime: {vix.get('regime', 'unknown')}")
    print(f"  Signal reliability: {vix.get('risk_assessment', {}).get('signal_reliability', 'unknown')}")
    
    # Test sector relative strength
    print("\n[Sector Relative Strength]")
    sector = provider.get_sector_etf_relative_strength()
    print(f"  SPY return (1mo): {sector.get('spy_return', 0):.2f}%")
    print(f"  AI sector strength: {sector.get('ai_sector_strength', 'unknown')}")
    
    # Print top 3 sectors
    rankings = sector.get('rankings', [])[:3]
    for name, rs in rankings:
        print(f"    {name}: {rs:+.2f}%")
    
    # Test PMI/enterprise spending
    print("\n[PMI/Enterprise Spending]")
    pmi = provider.get_pmi_ism_analysis()
    print(f"  Enterprise spending outlook: {pmi.get('enterprise_spending_outlook', 'unknown')}")
    
    # Test geopolitical risk
    print("\n[Geopolitical Risk]")
    geo = provider.get_geopolitical_risk_context()
    print(f"  US-China tension: {geo.get('us_china_tension_level', 'unknown')}")
    print(f"  Overall risk: {geo.get('overall_risk_level', 'unknown')}")
    if geo.get('risk_factors'):
        for rf in geo['risk_factors'][:3]:
            print(f"    - {rf}")
    
    # Test comprehensive context
    print("\n[Comprehensive Macro Context]")
    full = provider.get_comprehensive_macro_context()
    summary = full.get('summary', {})
    print(f"  Headline: {summary.get('headline', 'N/A')}")
    print(f"  Confidence modifier: {summary.get('signal_implications', {}).get('confidence_modifier', 1.0):.2f}")
    print(f"  Recommendation: {summary.get('signal_implications', {}).get('recommendation', 'N/A')}")
    
    return True


def test_regime_classifier():
    """Test regime classifier."""
    print("\n" + "=" * 60)
    print("TESTING REGIME CLASSIFIER")
    print("=" * 60)
    
    classifier = RegimeClassifier()
    
    # Classify current regime
    print("\n[Current Regime Classification]")
    snapshot = classifier.classify_regime()
    print(f"  Regime: {snapshot.regime}")
    print(f"  Confidence: {snapshot.confidence:.2f}")
    print(f"  Momentum score: {snapshot.momentum_score:+.3f}")
    print(f"  Volatility score: {snapshot.volatility_score:.3f}")
    print(f"  Trend score: {snapshot.trend_score:+.3f}")
    print(f"  VIX level: {snapshot.vix_level:.1f}")
    print(f"  S&P 500 1M return: {snapshot.sp500_return_1m*100:+.2f}%")
    print(f"  Tech vs SPY: {snapshot.tech_vs_spy_1m*100:+.2f}%")
    print(f"  Semis vs SPY: {snapshot.semis_vs_spy_1m*100:+.2f}%")
    
    if snapshot.notes:
        print("  Notes:")
        for note in snapshot.notes:
            print(f"    - {note}")
    
    # Get AI-specific context
    print("\n[AI Signal Context]")
    ai_context = classifier.get_regime_for_ai_signals()
    adj = ai_context.get('signal_adjustments', {})
    ai_sector = ai_context.get('ai_sector', {})
    
    print(f"  Sentiment reliability: {adj.get('sentiment_reliability', 1.0):.2f}")
    print(f"  Bullish signal boost: {adj.get('bullish_signal_boost', 0):+.2f}")
    print(f"  Risk-on environment: {ai_sector.get('risk_on_environment', False)}")
    print(f"  Sector rotation favorable: {ai_sector.get('sector_rotation_favorable', False)}")
    print(f"  Note: {adj.get('note', 'N/A')}")
    
    # Save regime to history
    print("\n[Saving Regime Snapshot]")
    classifier.save_regime_snapshot(snapshot)
    print(f"  Saved to: {classifier.history_file}")
    
    # Check history
    history = classifier.get_regime_history(days=7)
    print(f"  History entries (7d): {len(history)}")
    
    return True


def test_macro_calibrator():
    """Test macro-aware signal calibrator."""
    print("\n" + "=" * 60)
    print("TESTING MACRO-AWARE CALIBRATOR")
    print("=" * 60)
    
    calibrator = MacroAwareCalibrator()
    
    # Test signals for different entities
    test_cases = [
        {
            "entity": "nvidia",
            "signals": [
                {"sentiment": 7.5, "confidence": 0.8, "source_id": "news_search"},
                {"sentiment": 7.2, "confidence": 0.9, "source_id": "yfinance"},
                {"sentiment": 6.8, "confidence": 0.7, "source_id": "reddit"},
            ],
            "description": "Bullish NVIDIA (China-exposed)",
        },
        {
            "entity": "openai",
            "signals": [
                {"sentiment": 8.0, "confidence": 0.75, "source_id": "news_search"},
                {"sentiment": 7.5, "confidence": 0.85, "source_id": "github"},
            ],
            "description": "Bullish OpenAI (not China-exposed)",
        },
        {
            "entity": "intel",
            "signals": [
                {"sentiment": 3.5, "confidence": 0.7, "source_id": "news_search"},
                {"sentiment": 4.0, "confidence": 0.65, "source_id": "yfinance"},
            ],
            "description": "Bearish Intel (China-exposed)",
        },
    ]
    
    # Get macro context
    print("\n[Macro Context]")
    macro = calibrator.get_macro_summary()
    print(f"  Regime: {macro.get('regime', 'unknown')}")
    print(f"  VIX regime: {macro.get('vix_regime', 'unknown')}")
    print(f"  Sector strength: {macro.get('sector_strength', 'unknown')}")
    print(f"  Geopolitical risk: {macro.get('geopolitical_risk', 'unknown')}")
    print(f"  VIX confidence modifier: {macro.get('vix_confidence_modifier', 1.0):.2f}")
    
    for case in test_cases:
        print(f"\n[{case['description']}]")
        result = calibrator.calibrate_with_macro(case["entity"], case["signals"])
        
        base = result.get("base_calibration", {})
        print(f"  Entity: {result['entity_id']}")
        print(f"  Base sentiment: {base.get('sentiment', 'N/A'):.2f}")
        print(f"  Final sentiment: {result['calibrated_sentiment']:.2f}")
        print(f"  Final confidence: {result['calibrated_confidence']:.3f}")
        print(f"  Momentum: {result['momentum']}")
        
        if result.get("macro_adjustments"):
            print("  Macro adjustments:")
            for adj in result["macro_adjustments"]:
                print(f"    - {adj}")
    
    return True


def test_integration():
    """Test full integration with signal calibration."""
    print("\n" + "=" * 60)
    print("TESTING FULL INTEGRATION")
    print("=" * 60)
    
    # Use convenience function
    print("\n[Using calibrate_with_macro_context()]")
    result = calibrate_with_macro_context(
        entity_id="anthropic",
        signals=[
            {"sentiment": 8.5, "confidence": 0.9, "source_id": "news_search"},
            {"sentiment": 7.8, "confidence": 0.85, "source_id": "github"},
        ]
    )
    
    print(f"  Entity: {result['entity_id']}")
    print(f"  Calibrated sentiment: {result['calibrated_sentiment']:.2f}")
    print(f"  Calibrated confidence: {result['calibrated_confidence']:.3f}")
    print(f"  Momentum: {result['momentum']}")
    print(f"  Macro applied: {result['macro_applied']}")
    
    macro_ctx = result.get("macro_context", {})
    print(f"  Regime: {macro_ctx.get('regime', 'N/A')}")
    print(f"  VIX regime: {macro_ctx.get('vix_regime', 'N/A')}")
    
    return True


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("BRIEFAI MACRO-ECONOMIC INTEGRATION TEST")
    print("=" * 60)
    print(f"Timestamp: {datetime.now().isoformat()}")
    
    all_passed = True
    
    try:
        test_economic_context()
    except Exception as e:
        print(f"\n[ERROR] Economic context test failed: {e}")
        traceback.print_exc()
        all_passed = False
    
    try:
        test_regime_classifier()
    except Exception as e:
        print(f"\n[ERROR] Regime classifier test failed: {e}")
        traceback.print_exc()
        all_passed = False
    
    try:
        test_macro_calibrator()
    except Exception as e:
        print(f"\n[ERROR] Macro calibrator test failed: {e}")
        traceback.print_exc()
        all_passed = False
    
    try:
        test_integration()
    except Exception as e:
        print(f"\n[ERROR] Integration test failed: {e}")
        traceback.print_exc()
        all_passed = False
    
    print("\n" + "=" * 60)
    if all_passed:
        print("ALL TESTS PASSED!")
    else:
        print("SOME TESTS FAILED - see errors above")
    print("=" * 60)
