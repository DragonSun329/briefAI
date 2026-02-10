"""Tests for the agent base interface and registry."""

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.base import (
    AgentCard,
    AgentInput,
    AgentOutput,
    AgentRegistry,
    BaseAgent,
)


# ---------------------------------------------------------------------------
# Mock agent for testing
# ---------------------------------------------------------------------------

class MockAgent(BaseAgent):
    """Minimal agent for testing."""

    def __init__(self):
        super().__init__()

    @property
    def card(self) -> AgentCard:
        return AgentCard(
            agent_id="mock_agent",
            name="Mock Agent",
            description="A test agent",
            version="0.1.0",
            input_schema={"entity_name": "str"},
            output_schema={"score": "int"},
            capabilities=["testing"],
            model_task="article_evaluation",
        )

    async def run(self, input: AgentInput) -> AgentOutput:
        return AgentOutput(
            agent_id="mock_agent",
            status="completed",
            data={
                "entity": input.entity_name,
                "score": 85,
                "thesis": f"{input.entity_name} looks promising",
            },
        )


class FailingAgent(BaseAgent):
    """Agent that always fails."""

    @property
    def card(self) -> AgentCard:
        return AgentCard(agent_id="failing", name="Failing Agent", description="Always fails")

    async def run(self, input: AgentInput) -> AgentOutput:
        raise ValueError("Simulated agent failure")


# ---------------------------------------------------------------------------
# Tests: AgentCard
# ---------------------------------------------------------------------------

def test_agent_card_to_dict():
    card = AgentCard(
        agent_id="test",
        name="Test Agent",
        description="For testing",
        capabilities=["a", "b"],
    )
    d = card.to_dict()
    assert d["agent_id"] == "test"
    assert d["name"] == "Test Agent"
    assert d["capabilities"] == ["a", "b"]


# ---------------------------------------------------------------------------
# Tests: AgentInput / AgentOutput
# ---------------------------------------------------------------------------

def test_agent_input():
    inp = AgentInput(entity_name="OpenAI", signals={"github_stars": 50000})
    d = inp.to_dict()
    assert d["entity_name"] == "OpenAI"
    assert d["signals"]["github_stars"] == 50000


def test_agent_output():
    out = AgentOutput(agent_id="test", status="completed", data={"score": 90})
    assert out.succeeded
    d = out.to_dict()
    assert d["agent_id"] == "test"
    assert d["data"]["score"] == 90


def test_agent_output_failed():
    out = AgentOutput(agent_id="test", status="failed", error="boom")
    assert not out.succeeded


# ---------------------------------------------------------------------------
# Tests: BaseAgent
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mock_agent_run():
    agent = MockAgent()
    inp = AgentInput(entity_name="DeepSeek")
    output = await agent.run(inp)

    assert output.succeeded
    assert output.data["entity"] == "DeepSeek"
    assert output.data["score"] == 85


@pytest.mark.asyncio
async def test_timed_run():
    agent = MockAgent()
    inp = AgentInput(entity_name="Test")
    output = await agent.timed_run(inp)

    assert output.succeeded
    assert output.execution_time > 0


@pytest.mark.asyncio
async def test_timed_run_handles_failure():
    agent = FailingAgent()
    inp = AgentInput(entity_name="Test")
    output = await agent.timed_run(inp)

    assert not output.succeeded
    assert output.status == "failed"
    assert "Simulated" in output.error
    assert output.execution_time > 0


def test_agent_card_property():
    agent = MockAgent()
    assert agent.card.agent_id == "mock_agent"
    assert agent.card.model_task == "article_evaluation"


# ---------------------------------------------------------------------------
# Tests: AgentRegistry
# ---------------------------------------------------------------------------

def test_registry_register_and_get():
    reg = AgentRegistry()
    agent = MockAgent()
    reg.register(agent)

    assert "mock_agent" in reg
    assert len(reg) == 1
    assert reg.get("mock_agent") is agent
    assert reg.get("nonexistent") is None


def test_registry_list_cards():
    reg = AgentRegistry()
    reg.register(MockAgent())
    reg.register(FailingAgent())

    cards = reg.list_cards()
    assert len(cards) == 2
    ids = [c.agent_id for c in cards]
    assert "mock_agent" in ids
    assert "failing" in ids


def test_registry_ids():
    reg = AgentRegistry()
    reg.register(MockAgent())
    assert reg.ids() == ["mock_agent"]


# ---------------------------------------------------------------------------
# Tests: Real agents have cards
# ---------------------------------------------------------------------------

def test_real_agents_have_cards():
    """Verify the actual HypeMan, Skeptic, Arbiter agents have card properties."""
    from agents.hypeman import HypeManAgent
    from agents.skeptic import SkepticAgent
    from agents.arbiter import ArbiterAgent

    h = HypeManAgent()
    assert h.card.agent_id == "hypeman"
    assert h.card.model_task == "adversarial_analysis"

    s = SkepticAgent()
    assert s.card.agent_id == "skeptic"

    a = ArbiterAgent()
    assert a.card.agent_id == "arbiter"
    assert "synthesis" in a.card.capabilities


# ---------------------------------------------------------------------------
# Tests: JSON parsing helper
# ---------------------------------------------------------------------------

def test_parse_json_response_plain():
    result = BaseAgent._parse_json_response('{"score": 42}')
    assert result == {"score": 42}


def test_parse_json_response_code_block():
    text = 'Here is the analysis:\n```json\n{"score": 42}\n```\nDone.'
    result = BaseAgent._parse_json_response(text)
    assert result == {"score": 42}


def test_parse_json_response_invalid():
    result = BaseAgent._parse_json_response("not json at all")
    assert result == {}
