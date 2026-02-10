"""
Orchestrator API Router

The main intelligence endpoint — accepts natural language queries,
triages them through the Super Agent, plans multi-agent analysis,
executes in parallel, and streams results via SSE.

Endpoints:
- POST /api/v1/orchestrator/query     — submit query, stream analysis via SSE
- GET  /api/v1/orchestrator/agents    — list available agents for planning
- GET  /api/v1/orchestrator/conversations/{id} — get conversation history
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel

_app_dir = Path(__file__).parent.parent.parent.resolve()
if str(_app_dir) not in sys.path:
    sys.path.insert(0, str(_app_dir))

from agents.base import AgentRegistry
from agents.orchestrator import AgentOrchestrator, ConversationStore

router = APIRouter(prefix="/api/v1/orchestrator", tags=["orchestrator"])

# ---------------------------------------------------------------------------
# Shared state
# ---------------------------------------------------------------------------

_orchestrator: Optional[AgentOrchestrator] = None
_conversation_store = ConversationStore()


def get_orchestrator() -> AgentOrchestrator:
    """Get or initialize the orchestrator with all registered agents."""
    global _orchestrator
    if _orchestrator is None:
        registry = AgentRegistry()
        _register_agents(registry)
        _orchestrator = AgentOrchestrator(
            registry=registry,
            conversation_store=_conversation_store,
        )
    return _orchestrator


def _register_agents(registry: AgentRegistry):
    """Register all available agents."""
    # Adversarial agents
    try:
        from agents.hypeman import HypeManAgent
        registry.register(HypeManAgent())
    except Exception as e:
        logger.warning(f"Failed to register HypeManAgent: {e}")

    try:
        from agents.skeptic import SkepticAgent
        registry.register(SkepticAgent())
    except Exception as e:
        logger.warning(f"Failed to register SkepticAgent: {e}")

    try:
        from agents.arbiter import ArbiterAgent
        registry.register(ArbiterAgent())
    except Exception as e:
        logger.warning(f"Failed to register ArbiterAgent: {e}")

    # Domain-specific agents
    try:
        from agents.sector_agent import SectorAnalysisAgent
        registry.register(SectorAnalysisAgent())
    except Exception as e:
        logger.warning(f"Failed to register SectorAnalysisAgent: {e}")

    try:
        from agents.news_sentiment_agent import NewsSentimentAgent
        registry.register(NewsSentimentAgent())
    except Exception as e:
        logger.warning(f"Failed to register NewsSentimentAgent: {e}")

    try:
        from agents.trend_detector import TrendDetectorAgent
        registry.register(TrendDetectorAgent())
    except Exception as e:
        logger.warning(f"Failed to register TrendDetectorAgent: {e}")

    try:
        from agents.narrative_tracker import NarrativeTrackerAgent
        registry.register(NarrativeTrackerAgent())
    except Exception as e:
        logger.warning(f"Failed to register NarrativeTrackerAgent: {e}")

    try:
        from agents.prediction_engine import PredictionEngineAgent
        registry.register(PredictionEngineAgent())
    except Exception as e:
        logger.warning(f"Failed to register PredictionEngineAgent: {e}")


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class QueryRequest(BaseModel):
    query: str
    conversation_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/query")
async def submit_query(req: QueryRequest):
    """
    Submit a natural language query for multi-agent analysis.

    Returns: text/event-stream with orchestrator events.

    The orchestrator will:
    1. Triage the query (answer directly or plan)
    2. If planning: decompose into parallel agent tasks
    3. Execute all tasks concurrently
    4. Synthesize results into a coherent analysis

    Event types:
    - triage_start/triage_result: Super Agent analysis
    - direct_answer: Query answered without agents
    - plan_start/plan_ready: Task decomposition
    - task_start/task_complete/task_failed: Individual agent execution
    - synthesis_start/synthesis_complete: Final analysis
    - error: Non-fatal error
    - done: Stream complete

    Example SSE event:
        data: {"event":"plan_ready","message":"Plan ready: 4 tasks","data":{"tasks":[...]}}

    Example curl:
        curl -N -X POST http://localhost:8000/api/v1/orchestrator/query \\
          -H "Content-Type: application/json" \\
          -d '{"query": "为什么寒武纪今天跌了8%?"}'
    """
    orchestrator = get_orchestrator()

    async def event_stream():
        try:
            async for event in orchestrator.process(
                query=req.query,
                conversation_id=req.conversation_id,
            ):
                yield f"data: {json.dumps(event.to_dict(), ensure_ascii=False, default=str)}\n\n"
                await asyncio.sleep(0)  # Yield to event loop
        except Exception as e:
            logger.error(f"Orchestrator stream error: {e}")
            yield f"data: {json.dumps({'event': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Conversation-ID": req.conversation_id or "auto",
        },
    )


@router.get("/agents")
async def list_available_agents():
    """List all agents available for the orchestrator to use."""
    orchestrator = get_orchestrator()
    cards = orchestrator.registry.list_cards()
    return {
        "agents": [c.to_dict() for c in cards],
        "count": len(cards),
    }


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str, max_turns: int = 20):
    """Get conversation history for a session."""
    turns = _conversation_store.get_or_create(conversation_id)
    return {
        "conversation_id": conversation_id,
        "turns": [
            {
                "role": t.role,
                "content": t.content[:2000],
                "timestamp": t.timestamp,
            }
            for t in turns[-max_turns:]
        ],
        "total_turns": len(turns),
    }
