#!/usr/bin/env python3
"""
CellCog Deep Research Integration for briefAI
Uses CellCog's #1 ranked deep research capabilities for AI industry analysis.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

# Output paths
DATA_DIR = Path(__file__).parent.parent / "data" / "deep_research"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Check for cellcog
try:
    from cellcog import CellCogClient
    CELLCOG_AVAILABLE = True
except ImportError:
    CELLCOG_AVAILABLE = False
    logger.warning("CellCog not installed. Run: pip install cellcog")


def get_cellcog_client() -> Optional[Any]:
    """
    Initialize CellCog client with API key.
    Get your key from: https://cellcog.ai/profile?tab=api-keys
    """
    if not CELLCOG_AVAILABLE:
        return None
    
    # Check for API key in environment or .env file
    api_key = os.environ.get('CELLCOG_API_KEY')
    
    if not api_key:
        # Load from .env file into environment
        env_file = Path(__file__).parent.parent / ".env"
        if env_file.exists():
            with open(env_file) as f:
                for line in f:
                    if line.startswith('CELLCOG_API_KEY='):
                        api_key = line.split('=', 1)[1].strip().strip('"\'')
                        os.environ['CELLCOG_API_KEY'] = api_key
                        break
    
    if not api_key:
        logger.warning("CELLCOG_API_KEY not found. Set it in .env or environment.")
        logger.info("Get your API key from: https://cellcog.ai/profile?tab=api-keys")
        return None
    
    # SDK v1.1+ reads API key from environment automatically
    client = CellCogClient()
    
    try:
        status = client.get_account_status()
        if status.get('configured'):
            logger.info(f"CellCog authenticated: {status.get('email', 'unknown')}")
            return client
    except Exception as e:
        logger.error(f"CellCog authentication failed: {e}")
    
    return None


def create_research_task(
    client: Any,
    topic: str,
    output_format: str = "json",
    notify_session: str = "agent:main:main"
) -> Optional[Dict]:
    """
    Create a deep research task with CellCog.
    
    Args:
        client: CellCog client
        topic: Research topic
        output_format: Output format (json, pdf, markdown)
        notify_session: Session key for notifications
        
    Returns:
        Task creation result
    """
    prompt = f"""
You are a financial analyst researching AI industry trends. 

Research Topic: {topic}

Provide a comprehensive analysis including:
1. Key developments in the past 7 days
2. Major company announcements and their implications
3. Investment signals (bullish/bearish indicators)
4. Emerging trends and patterns
5. Risk factors to watch

Format your response as structured JSON with the following schema:
{{
    "topic": "{topic}",
    "summary": "Executive summary (2-3 sentences)",
    "key_developments": [
        {{"event": "...", "entity": "...", "signal": "bullish/bearish/neutral", "importance": 1-10}}
    ],
    "investment_signals": [
        {{"entity": "...", "signal_type": "...", "direction": "bullish/bearish", "confidence": 0.0-1.0, "rationale": "..."}}
    ],
    "emerging_trends": [
        {{"trend": "...", "evidence": "...", "timeline": "..."}}
    ],
    "risk_factors": [
        {{"risk": "...", "affected_entities": [...], "severity": "high/medium/low"}}
    ],
    "analyst_outlook": "Overall outlook paragraph"
}}

Be specific with company names, dates, and quantitative signals where possible.
No clarifying questions needed - proceed directly with the research.
"""

    try:
        result = client.create_chat(
            prompt=prompt,
            notify_session_key=notify_session,
            task_label=f"briefai-research-{topic.replace(' ', '-')[:30]}",
            chat_mode="agent"  # Use "agent team" for deeper research
        )
        
        logger.info(f"Research task created: {result.get('chat_id')}")
        return result
        
    except Exception as e:
        logger.error(f"Failed to create research task: {e}")
        return None


def run_sync_research(topic: str) -> Optional[Dict]:
    """
    Run synchronous research (polls until complete).
    For integration into the pipeline.
    """
    client = get_cellcog_client()
    if not client:
        return None
    
    import time
    
    result = create_research_task(client, topic)
    if not result:
        return None
    
    chat_id = result.get('chat_id')
    
    # Poll for completion (max 5 minutes)
    max_wait = 300
    poll_interval = 10
    elapsed = 0
    
    while elapsed < max_wait:
        try:
            status = client.get_status(chat_id=chat_id)
            if not status.get('is_operating'):
                # Task complete - get results
                history = client.get_history(chat_id=chat_id)
                return {
                    'chat_id': chat_id,
                    'topic': topic,
                    'completed_at': datetime.now().isoformat(),
                    'result': history.get('formatted_output', '')
                }
        except Exception as e:
            logger.warning(f"Poll error: {e}")
        
        time.sleep(poll_interval)
        elapsed += poll_interval
        logger.info(f"  Waiting for research... ({elapsed}s)")
    
    logger.warning(f"Research task {chat_id} timed out")
    return None


# Pre-defined research topics for briefAI
RESEARCH_TOPICS = [
    "AI chip market developments and NVIDIA competitors",
    "Large language model releases and benchmark comparisons",
    "AI startup funding rounds and valuations this week",
    "Enterprise AI adoption trends and customer wins",
    "AI regulation and policy developments globally",
    "Open source AI models and community developments"
]


def run_daily_research() -> Dict[str, Any]:
    """
    Run daily deep research on key AI topics.
    """
    print("=" * 60)
    print("CELLCOG DEEP RESEARCH")
    print("=" * 60)
    
    client = get_cellcog_client()
    
    if not client:
        print("\n⚠️  CellCog not configured.")
        print("To enable deep research:")
        print("1. Get API key from: https://cellcog.ai/profile?tab=api-keys")
        print("2. Add to .env: CELLCOG_API_KEY=sk_...")
        return {'status': 'skipped', 'reason': 'no_api_key'}
    
    today = datetime.now().strftime("%Y-%m-%d")
    results = []
    
    # Run synchronous research (waits for results) for top topics
    for topic in RESEARCH_TOPICS[:2]:  # Limit to 2 for cost/time control
        logger.info(f"Running sync research: {topic}")
        print(f"  Researching: {topic}...")
        res = run_sync_research(topic)
        if res:
            results.append({
                'topic': topic,
                'chat_id': res.get('chat_id'),
                'status': 'completed',
                'result': res.get('result', ''),
            })
            print(f"  ✓ Completed: {topic}")
        else:
            # Fall back to async for remaining
            logger.info(f"Sync failed, creating async task: {topic}")
            result = create_research_task(client, topic)
            if result:
                results.append({
                    'topic': topic,
                    'chat_id': result.get('chat_id'),
                    'status': 'pending'
                })
    
    # Save results
    output_file = DATA_DIR / f"research_tasks_{today}.json"
    with open(output_file, 'w') as f:
        json.dump({
            'date': today,
            'tasks': results,
        }, f, indent=2, ensure_ascii=False)
    
    completed = sum(1 for r in results if r['status'] == 'completed')
    print(f"\nResearch: {completed} completed, {len(results) - completed} pending")
    print(f"Saved to: {output_file}")
    
    return {
        'status': 'completed' if completed > 0 else 'tasks_created',
        'count': len(results),
        'completed': completed,
        'tasks': results
    }


if __name__ == '__main__':
    run_daily_research()
