"""
Agents API Router

Provides discovery and invocation of registered agents.

Endpoints:
- GET  /api/v1/agents          — list registered agents and their capabilities
- GET  /api/v1/agents/{id}     — get a specific agent's card
- POST /api/v1/agents/{id}/run — invoke an agent with input
"""

import sys
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from loguru import logger
from pydantic import BaseModel

# Ensure project root on path
_app_dir = Path(__file__).parent.parent.parent.resolve()
if str(_app_dir) not in sys.path:
    sys.path.insert(0, str(_app_dir))

from agents.base import AgentInput, AgentRegistry

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])

# ---------------------------------------------------------------------------
# Registry (initialized on first access)
# ---------------------------------------------------------------------------

_registry = AgentRegistry()


def get_registry() -> AgentRegistry:
    """Get or initialize the agent registry."""
    if len(_registry) == 0:
        _register_defaults()
    return _registry


def _register_defaults():
    """Register built-in agents."""
    agent_classes = [
        ("agents.hypeman", "HypeManAgent"),
        ("agents.skeptic", "SkepticAgent"),
        ("agents.arbiter", "ArbiterAgent"),
        ("agents.sector_agent", "SectorAnalysisAgent"),
        ("agents.news_sentiment_agent", "NewsSentimentAgent"),
        ("agents.trend_detector", "TrendDetectorAgent"),
        ("agents.narrative_tracker", "NarrativeTrackerAgent"),
        ("agents.prediction_engine", "PredictionEngineAgent"),
    ]
    for module_name, class_name in agent_classes:
        try:
            import importlib
            mod = importlib.import_module(module_name)
            cls = getattr(mod, class_name)
            _registry.register(cls())
        except Exception as e:
            logger.warning(f"Failed to register {class_name}: {e}")


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class AgentRunRequest(BaseModel):
    entity_name: str
    signals: Optional[dict] = None
    context: Optional[dict] = None
    params: Optional[dict] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("")
async def list_agents():
    """List all registered agents with their capability cards."""
    registry = get_registry()
    return {
        "agents": [card.to_dict() for card in registry.list_cards()],
        "count": len(registry),
    }


@router.get("/{agent_id}")
async def get_agent(agent_id: str):
    """Get a specific agent's capability card."""
    registry = get_registry()
    agent = registry.get(agent_id)
    if not agent:
        raise HTTPException(
            status_code=404,
            detail=f"Agent '{agent_id}' not found. Available: {registry.ids()}",
        )
    return agent.card.to_dict()


@router.post("/{agent_id}/run")
async def run_agent(agent_id: str, req: AgentRunRequest):
    """
    Invoke an agent with the given input.

    Returns the agent's output including scores, thesis, and metadata.
    """
    registry = get_registry()
    agent = registry.get(agent_id)
    if not agent:
        raise HTTPException(
            status_code=404,
            detail=f"Agent '{agent_id}' not found. Available: {registry.ids()}",
        )

    agent_input = AgentInput(
        entity_name=req.entity_name,
        signals=req.signals or {},
        context=req.context or {},
        params=req.params or {},
    )

    output = await agent.timed_run(agent_input)
    return output.to_dict()
