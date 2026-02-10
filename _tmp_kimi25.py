import sys, io, json, asyncio
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import dotenv; dotenv.load_dotenv()

from agents.trend_detector import TrendDetectorAgent
from agents.base import AgentInput

async def main():
    agent = TrendDetectorAgent(llm_client=None)
    inp = AgentInput(entity_name="", context={"time_window_days": 14, "min_sources": 2})
    output = await agent.run(inp)
    
    print(f"Status: {output.status}")
    print(f"Data keys: {list(output.data.keys()) if output.data else 'None'}")
    
    trends = output.data.get("emerging_trends", [])
    print(f"\nTrends: {len(trends)}")
    for t in trends[:3]:
        print(f"  - {t.get('trend_name') or t.get('entity', '?')}: score={t.get('emergence_score', '?')}")
        if t.get('narrative'):
            print(f"    Narrative: {t['narrative'][:100]}")
    
    stealth = output.data.get("stealth_signals", [])
    print(f"\nStealth signals: {len(stealth)}")
    for s in stealth[:3]:
        print(f"  - {s.get('entity', '?')}: {s.get('description', '')[:80]}")

asyncio.run(main())
