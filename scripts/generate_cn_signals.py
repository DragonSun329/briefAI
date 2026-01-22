#!/usr/bin/env python
"""
Generate China Market Financial Signals

Usage:
    python scripts/generate_cn_signals.py [--date YYYYMMDD]

This script fetches A-share and HK stock data using AkShare,
computes PMS-CN and MRS-CN signals, and saves to JSON.
"""

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.financial_signals_cn import generate_cn_financial_signals
from loguru import logger


def main():
    parser = argparse.ArgumentParser(description="Generate CN financial signals")
    parser.add_argument(
        "--date",
        type=str,
        help="Target date in YYYYMMDD format (default: today)",
        default=None
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        help="Output directory for JSON files",
        default=None
    )
    args = parser.parse_args()

    # Parse target date
    target_date = date.today()
    if args.date:
        try:
            target_date = datetime.strptime(args.date, "%Y%m%d").date()
        except ValueError:
            logger.error(f"Invalid date format: {args.date}. Use YYYYMMDD.")
            sys.exit(1)

    # Set output directory
    output_dir = Path(args.output_dir) if args.output_dir else Path(__file__).parent.parent / "data" / "alternative_signals"
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Generating CN financial signals for {target_date}")
    logger.info(f"Output directory: {output_dir}")

    try:
        result = generate_cn_financial_signals(output_dir, target_date)

        # Print summary
        bucket_signals = result.get("bucket_signals", {})
        macro_regime = result.get("macro_regime_cn", {})
        sources = result.get("sources", {})
        quality = result.get("quality", {})

        print("\n" + "=" * 60)
        print("CN Financial Signals Generated Successfully")
        print("=" * 60)
        print(f"Date: {result.get('date')}")
        print(f"Generated at: {result.get('generated_at')}")
        print()

        print("Sources:")
        for source, info in sources.items():
            status = info.get("status", "unknown")
            print(f"  - {source}: {status}")
            for k, v in info.items():
                if k != "status":
                    print(f"      {k}: {v}")

        print()
        print("Quality:")
        print(f"  Status: {quality.get('overall_status', 'unknown')}")
        for warning in quality.get("warnings", []):
            print(f"  Warning: {warning}")

        print()
        print("Macro Regime (MRS-CN):")
        print(f"  Score: {macro_regime.get('mrs_cn', 'N/A')}")
        print(f"  Interpretation: {macro_regime.get('interpretation', 'unknown')}")

        print()
        print(f"Bucket Signals ({len(bucket_signals)} buckets):")
        for bucket_id, signals in sorted(bucket_signals.items(), key=lambda x: x[1].get("pms_cn") or 0, reverse=True):
            pms_cn = signals.get("pms_cn")
            bucket_name = signals.get("bucket_name", bucket_id)
            coverage = signals.get("pms_cn_coverage", {})
            if pms_cn is not None:
                print(f"  {bucket_name}: PMS-CN={pms_cn:.1f} (coverage: {coverage.get('tickers_present', 0)}/{coverage.get('tickers_total', 0)})")

        print()
        date_str = target_date.strftime("%Y-%m-%d")
        print(f"Output file: {output_dir / f'financial_signals_cn_{date_str}.json'}")
        print("=" * 60)

    except Exception as e:
        logger.exception(f"Failed to generate CN signals: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()