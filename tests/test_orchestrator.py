"""Tests for the Agent Orchestrator (Super Agent + Planner + Executor)."""

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.base import AgentCard, AgentInput, AgentOutput, AgentRegistry, BaseAgent
from agents.orchestrator import (
    AgentOrchestrator,
    ConversationStore,
    ExecutionPlan,
    OrchestratorEvent,
    OrchestratorEventType,
    TaskPlan,
    TaskResult,
    TriageDecision,
    TriageResult,
)


# ---------------------------------------------------------------------------
# Mock agents for testing
# ---------------------------------------------------------------------------

class MockAnalysisAgent(BaseAgent):
    """Fast mock agent that returns canned results."""

    def __init__(self, agent_id: str, name: str, description: str):
        super().__init__()
        self._agent_id = agent_id
        self._name = name
        self._description = description

    @property
    def card(self) -> AgentCard:
        return AgentCard(
            agent_id=self._agent_id,
            name=self._name,
            description=self._description,
            capabilities=["analysis"],
        )

    async def run(self, input: AgentInput) -> AgentOutput:
        return AgentOutput(
            agent_id=self._agent_id,
            status="completed",
            data={
                "analysis": f"Mock analysis from {self._name}",
                "query": input.entity_name,
                "score": 75,
            },
        )


class MockFailingAgent(BaseAgent):
    @property
    def card(self) -> AgentCard:
        return AgentCard(agent_id="failing", name="Failing", description="Always fails")

    async def run(self, input: AgentInput) -> AgentOutput:
        raise RuntimeError("Simulated agent failure")


# ---------------------------------------------------------------------------
# Tests: ConversationStore
# ---------------------------------------------------------------------------

def test_conversation_store_basic():
    store = ConversationStore()
    store.add_turn("conv1", "user", "Hello")
    store.add_turn("conv1", "assistant", "Hi there")

    assert store.has_context("conv1")
    assert not store.has_context("conv2")

    summary = store.get_context_summary("conv1")
    assert "Hello" in summary
    assert "Hi there" in summary


def test_conversation_store_max_turns():
    store = ConversationStore(max_turns=3)
    for i in range(5):
        store.add_turn("conv1", "user", f"Message {i}")

    turns = store.get_or_create("conv1")
    assert len(turns) == 3
    assert turns[0].content == "Message 2"  # Oldest trimmed


# ---------------------------------------------------------------------------
# Tests: Data models
# ---------------------------------------------------------------------------

def test_triage_result():
    tr = TriageResult(
        decision=TriageDecision.ANSWER,
        answer_content="42",
        reason="Simple math",
    )
    assert tr.decision == TriageDecision.ANSWER
    assert tr.answer_content == "42"


def test_execution_plan():
    plan = ExecutionPlan(
        plan_id="p1",
        original_query="test",
        enriched_query="test enriched",
        tasks=[
            TaskPlan(task_id="t1", agent_id="a1", query="q1", title="Task 1"),
            TaskPlan(task_id="t2", agent_id="a2", query="q2", title="Task 2"),
        ],
        reasoning="Split into 2 tasks",
    )
    d = plan.to_dict()
    assert d["plan_id"] == "p1"
    assert len(d["tasks"]) == 2
    assert d["tasks"][0]["agent_id"] == "a1"


def test_orchestrator_event():
    event = OrchestratorEvent(
        event_type=OrchestratorEventType.PLAN_READY,
        message="Plan ready: 3 tasks",
        data={"task_count": 3},
    )
    d = event.to_dict()
    assert d["event"] == "plan_ready"
    assert d["message"] == "Plan ready: 3 tasks"
    assert d["data"]["task_count"] == 3


# ---------------------------------------------------------------------------
# Tests: Task Executor (isolated)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_execute_tasks_parallel():
    """Test that tasks run in parallel and produce events."""
    registry = AgentRegistry()
    registry.register(MockAnalysisAgent("agent_a", "Agent A", "Does A"))
    registry.register(MockAnalysisAgent("agent_b", "Agent B", "Does B"))

    orchestrator = AgentOrchestrator(registry=registry)

    tasks = [
        TaskPlan(task_id="t1", agent_id="agent_a", query="Analyze X", title="X Analysis"),
        TaskPlan(task_id="t2", agent_id="agent_b", query="Analyze Y", title="Y Analysis"),
    ]

    events = []
    results = []
    async for event, result in orchestrator._execute_tasks(tasks):
        events.append(event)
        if result:
            results.append(result)

    # Should have: 2 start events + 2 complete events = 4
    assert len(events) == 4
    assert len(results) == 2

    # Both should be completed
    assert all(r.status == "completed" for r in results)

    # Check event types
    start_events = [e for e in events if e.event_type == OrchestratorEventType.TASK_START]
    complete_events = [e for e in events if e.event_type == OrchestratorEventType.TASK_COMPLETE]
    assert len(start_events) == 2
    assert len(complete_events) == 2


@pytest.mark.asyncio
async def test_execute_tasks_with_failure():
    """Test that failing tasks produce error events."""
    registry = AgentRegistry()
    registry.register(MockAnalysisAgent("good", "Good Agent", "Works"))
    registry.register(MockFailingAgent())

    orchestrator = AgentOrchestrator(registry=registry)

    tasks = [
        TaskPlan(task_id="t1", agent_id="good", query="Test", title="Good Task"),
        TaskPlan(task_id="t2", agent_id="failing", query="Test", title="Bad Task"),
    ]

    events = []
    results = []
    async for event, result in orchestrator._execute_tasks(tasks):
        events.append(event)
        if result:
            results.append(result)

    # One should complete, one should fail
    completed = [r for r in results if r.status == "completed"]
    failed = [r for r in results if r.status == "failed"]
    assert len(completed) == 1
    assert len(failed) == 1


@pytest.mark.asyncio
async def test_execute_tasks_unknown_agent():
    """Test that tasks with unknown agents produce error results."""
    registry = AgentRegistry()
    orchestrator = AgentOrchestrator(registry=registry)

    tasks = [
        TaskPlan(task_id="t1", agent_id="nonexistent", query="Test", title="Missing"),
    ]

    events = []
    results = []
    async for event, result in orchestrator._execute_tasks(tasks):
        events.append(event)
        if result:
            results.append(result)

    assert len(results) == 1
    assert results[0].status == "failed"
    assert "not found" in results[0].error


# ---------------------------------------------------------------------------
# Tests: Conversation context
# ---------------------------------------------------------------------------

def test_format_agent_descriptions():
    registry = AgentRegistry()
    registry.register(MockAnalysisAgent("a", "Agent A", "Does analysis A"))
    registry.register(MockAnalysisAgent("b", "Agent B", "Does analysis B"))

    orchestrator = AgentOrchestrator(registry=registry)
    desc = orchestrator._format_agent_descriptions()

    assert "agent_a" in desc or "a" in desc
    assert "Agent A" in desc
    assert "Agent B" in desc


def test_conversation_context_flow():
    """Test that conversation store integrates with orchestrator."""
    store = ConversationStore()
    registry = AgentRegistry()
    orchestrator = AgentOrchestrator(registry=registry, conversation_store=store)

    # Simulate turns
    store.add_turn("conv1", "user", "分析寒武纪")
    store.add_turn("conv1", "assistant", "寒武纪技术面分析...")

    assert store.has_context("conv1")
    summary = store.get_context_summary("conv1")
    assert "寒武纪" in summary


# ---------------------------------------------------------------------------
# Tests: JSON parsing
# ---------------------------------------------------------------------------

def test_parse_json_plain():
    result = AgentOrchestrator._parse_json('{"decision": "answer"}')
    assert result["decision"] == "answer"


def test_parse_json_code_block():
    text = 'Here:\n```json\n{"decision": "handoff_to_planner"}\n```'
    result = AgentOrchestrator._parse_json(text)
    assert result["decision"] == "handoff_to_planner"


def test_parse_json_invalid():
    result = AgentOrchestrator._parse_json("not json")
    assert result == {}
