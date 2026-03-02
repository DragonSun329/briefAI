#!/usr/bin/env python3
"""Generate daily brief - wrapper for pipeline."""
import sys, asyncio
sys.path.insert(0, '.')
from modules.daily_brief import DailyBriefGenerator

async def main():
    gen = DailyBriefGenerator()
    report_path = await gen.generate()
    print(f'Generated: {report_path}')
    return 0

if __name__ == "__main__":
    sys.exit(asyncio.run(main()) or 0)
