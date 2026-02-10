"""
Agent Orchestrator — Super Agent + LLM Planner + Async Task Executor

The brain of briefAI's multi-agent system. Handles:
  1. Super Agent triage: answer directly vs plan multi-step analysis
  2. LLM Planner: decompose complex queries into parallel agent tasks
  3. Async executor: run tasks concurrently, stream results via events
  4. Conversation context: maintain state for follow-up questions

Usage:
    orchestrator = AgentOrchestrator()
    async for event in orchestrator.process("为什么寒武纪今天跌了8%?"):
        print(event.to_dict())

Architecture (inspired by ValueCell):
    User Query
        → Super Agent (triage: answer | plan)
        → Planner (query → List[Task] with agent assignments)
        → Task Executor (parallel async, streaming events)
        → Conversation Store (context for follow-ups)
"""

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, AsyncGenerator, Dict, List, Optional, Callable

from loguru import logger

from agents.base import AgentCard, AgentInput, AgentOutput, AgentRegistry, BaseAgent


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class TriageDecision(str, Enum):
    """Super Agent's decision on how to handle a query."""
    ANSWER = "answer"                    # Answer directly
    HANDOFF_TO_PLANNER = "handoff_to_planner"  # Needs multi-agent planning


@dataclass
class TriageResult:
    """Output from the Super Agent triage."""
    decision: TriageDecision
    answer_content: Optional[str] = None
    enriched_query: Optional[str] = None
    reason: str = ""


@dataclass
class TaskPlan:
    """A single task in the execution plan."""
    task_id: str
    agent_id: str
    query: str
    title: str
    depends_on: Optional[List[str]] = None  # task_ids this depends on

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ExecutionPlan:
    """Complete plan produced by the LLM Planner."""
    plan_id: str
    original_query: str
    enriched_query: str
    tasks: List[TaskPlan]
    reasoning: str = ""
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "original_query": self.original_query,
            "enriched_query": self.enriched_query,
            "tasks": [t.to_dict() for t in self.tasks],
            "reasoning": self.reasoning,
        }


@dataclass
class TaskResult:
    """Result of executing a single task."""
    task_id: str
    agent_id: str
    title: str
    status: str  # "completed", "failed"
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    execution_time: float = 0.0


class OrchestratorEventType(str, Enum):
    """Events emitted by the orchestrator."""
    TRIAGE_START = "triage_start"
    TRIAGE_RESULT = "triage_result"
    DIRECT_ANSWER = "direct_answer"
    PLAN_START = "plan_start"
    PLAN_READY = "plan_ready"
    TASK_START = "task_start"
    TASK_COMPLETE = "task_complete"
    TASK_FAILED = "task_failed"
    SYNTHESIS_START = "synthesis_start"
    SYNTHESIS_COMPLETE = "synthesis_complete"
    ERROR = "error"
    DONE = "done"


@dataclass
class OrchestratorEvent:
    """An event emitted during orchestration."""
    event_type: OrchestratorEventType
    timestamp: float = field(default_factory=time.time)
    message: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = {"event": self.event_type.value, "timestamp": self.timestamp}
        if self.message:
            d["message"] = self.message
        if self.data:
            d["data"] = self.data
        return d


# ---------------------------------------------------------------------------
# Conversation Store (in-memory, per-session)
# ---------------------------------------------------------------------------

@dataclass
class ConversationTurn:
    """A single turn in a conversation."""
    role: str  # "user", "assistant", "system"
    content: str
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


class ConversationStore:
    """
    In-memory conversation history for follow-up context.

    Tracks queries, plans, and results so the orchestrator can handle
    "tell me more about X" style follow-ups.
    """

    def __init__(self, max_turns: int = 20):
        self._conversations: Dict[str, List[ConversationTurn]] = {}
        self._max_turns = max_turns

    def get_or_create(self, conversation_id: str) -> List[ConversationTurn]:
        if conversation_id not in self._conversations:
            self._conversations[conversation_id] = []
        return self._conversations[conversation_id]

    def add_turn(self, conversation_id: str, role: str, content: str, **metadata):
        turns = self.get_or_create(conversation_id)
        turns.append(ConversationTurn(role=role, content=content, metadata=metadata))
        # Trim to max
        if len(turns) > self._max_turns:
            self._conversations[conversation_id] = turns[-self._max_turns:]

    def get_context_summary(self, conversation_id: str, max_turns: int = 6) -> str:
        """Get recent conversation as a text summary for LLM context."""
        turns = self.get_or_create(conversation_id)
        if not turns:
            return ""
        recent = turns[-max_turns:]
        lines = []
        for t in recent:
            prefix = "User" if t.role == "user" else "Assistant"
            lines.append(f"{prefix}: {t.content[:500]}")
        return "\n".join(lines)

    def has_context(self, conversation_id: str) -> bool:
        return bool(self._conversations.get(conversation_id))


# ---------------------------------------------------------------------------
# Super Agent
# ---------------------------------------------------------------------------

SUPER_AGENT_PROMPT = """You are the frontline triage agent for briefAI, a financial AI intelligence platform.

Your job: decide whether to answer a query directly or hand it off to specialist agents.

## Decision Rules

**Answer directly** when:
- Simple factual questions ("What does briefAI do?")
- Definitions or explanations ("What is a P/E ratio?")
- General knowledge that doesn't need real-time data
- Greetings or meta-questions about the system

**Hand off to planner** when:
- Stock analysis, price movements, market questions
- Multi-dimensional analysis (technical + fundamental + sentiment)
- Entity-specific deep research (companies, products, people)
- Questions requiring real-time or recent data
- Comparative analysis across companies/sectors
- Anything involving Chinese A-shares, funding rounds, or AI industry signals

## Context
{conversation_context}

## Available Agents
{agent_descriptions}

## Response Format
Return ONLY valid JSON:
{{
  "decision": "answer" | "handoff_to_planner",
  "answer_content": "Direct answer (only when decision=answer)",
  "enriched_query": "Enriched, structured query for the planner (only when decision=handoff_to_planner)",
  "reason": "Brief rationale"
}}

When enriching a query for handoff:
- Preserve the user's language (Chinese stays Chinese)
- Add structure: identify entities, ticker symbols, analysis dimensions
- Expand implicit context from conversation history
- Be specific about what needs to be analyzed"""


PLANNER_PROMPT = """You are the task planner for briefAI. Your job: decompose a complex analysis query into parallel tasks that can be handled by specialist agents.

## Available Agents
{agent_descriptions}

## Conversation Context
{conversation_context}

## Planning Rules
1. Each task goes to exactly ONE agent
2. Tasks should be parallelizable when possible (no unnecessary dependencies)
3. Keep task queries focused — one analysis dimension per task
4. Write task queries in the same language as the user's original query
5. Title should be concise (≤8 words English, ≤15 chars Chinese)
6. Only use agents from the available list above
7. For "what's trending/emerging" questions: use trend_detector for cross-source pattern detection
8. For "how is X evolving / what's the story" questions: use narrative_tracker for timeline analysis
9. For "what will happen / predictions" questions: use prediction engine
10. For entity research: use sentiment + adversarial (hypeman/skeptic) + sector context
11. For A-share analysis: use sentiment (news/social), sector (行业/板块), and adversarial pipeline
12. Usually 2-5 tasks. Don't over-split simple queries.

## Response Format
Return ONLY valid JSON:
{{
  "tasks": [
    {{
      "agent_id": "agent_id from available list",
      "query": "Focused query for this agent (in user's language)",
      "title": "Short title for this task"
    }}
  ],
  "reasoning": "Brief explanation of the decomposition strategy",
  "synthesis_prompt": "Instructions for combining results (in user's language)"
}}"""


SYNTHESIS_PROMPT = """You are synthesizing results from multiple specialist agents into a coherent analysis.

## Original Query
{original_query}

## Agent Results
{agent_results}

## Synthesis Instructions
{synthesis_instructions}

## Rules
- Respond in the same language as the original query
- Highlight key findings, conflicts between agents, and actionable insights
- Structure the response clearly with sections
- Note confidence levels and any data gaps
- Be concise but thorough — this is for an executive audience"""


class AgentOrchestrator:
    """
    Multi-agent orchestrator with Super Agent triage, LLM planning,
    parallel execution, and conversation context.
    """

    def __init__(
        self,
        registry: Optional[AgentRegistry] = None,
        conversation_store: Optional[ConversationStore] = None,
    ):
        self.registry = registry or AgentRegistry()
        self.conversations = conversation_store or ConversationStore()
        self._provider_switcher = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def process(
        self,
        query: str,
        conversation_id: Optional[str] = None,
    ) -> AsyncGenerator[OrchestratorEvent, None]:
        """
        Process a user query through the full orchestration pipeline.

        Yields OrchestratorEvents as the analysis progresses.

        Args:
            query: User's natural language query.
            conversation_id: Optional conversation ID for context continuity.
        """
        conversation_id = conversation_id or str(uuid.uuid4())[:12]

        # Record user turn
        self.conversations.add_turn(conversation_id, "user", query)

        try:
            # Phase 1: Super Agent triage
            yield OrchestratorEvent(
                OrchestratorEventType.TRIAGE_START,
                message="Analyzing query...",
            )

            triage = await self._triage(query, conversation_id)

            yield OrchestratorEvent(
                OrchestratorEventType.TRIAGE_RESULT,
                message=f"Decision: {triage.decision.value}",
                data={"decision": triage.decision.value, "reason": triage.reason},
            )

            if triage.decision == TriageDecision.ANSWER:
                # Direct answer
                answer = triage.answer_content or "I couldn't generate an answer."
                yield OrchestratorEvent(
                    OrchestratorEventType.DIRECT_ANSWER,
                    message=answer,
                    data={"answer": answer},
                )
                self.conversations.add_turn(conversation_id, "assistant", answer)
                yield OrchestratorEvent(OrchestratorEventType.DONE)
                return

            # Phase 2: Plan
            enriched = triage.enriched_query or query
            yield OrchestratorEvent(
                OrchestratorEventType.PLAN_START,
                message="Planning analysis strategy...",
                data={"enriched_query": enriched},
            )

            plan = await self._plan(enriched, conversation_id)

            yield OrchestratorEvent(
                OrchestratorEventType.PLAN_READY,
                message=f"Plan ready: {len(plan.tasks)} tasks",
                data=plan.to_dict(),
            )

            if not plan.tasks:
                yield OrchestratorEvent(
                    OrchestratorEventType.ERROR,
                    message="Planner produced no tasks",
                )
                yield OrchestratorEvent(OrchestratorEventType.DONE)
                return

            # Phase 3: Execute tasks in parallel
            task_results: List[TaskResult] = []

            # Group independent tasks for parallel execution
            async for event, result in self._execute_tasks(plan.tasks):
                yield event
                if result:
                    task_results.append(result)

            # Phase 4: Synthesize results
            if task_results:
                yield OrchestratorEvent(
                    OrchestratorEventType.SYNTHESIS_START,
                    message="Synthesizing findings...",
                )

                synthesis = await self._synthesize(
                    query, task_results, plan
                )

                yield OrchestratorEvent(
                    OrchestratorEventType.SYNTHESIS_COMPLETE,
                    message=synthesis,
                    data={"synthesis": synthesis, "task_count": len(task_results)},
                )

                self.conversations.add_turn(
                    conversation_id, "assistant", synthesis,
                    plan=plan.to_dict(),
                    task_results=[asdict(r) for r in task_results],
                )

            yield OrchestratorEvent(OrchestratorEventType.DONE)

        except Exception as e:
            logger.error(f"Orchestrator error: {e}")
            yield OrchestratorEvent(
                OrchestratorEventType.ERROR,
                message=f"Orchestration failed: {str(e)}",
            )
            yield OrchestratorEvent(OrchestratorEventType.DONE)

    # ------------------------------------------------------------------
    # Phase 1: Super Agent Triage
    # ------------------------------------------------------------------

    async def _triage(self, query: str, conversation_id: str) -> TriageResult:
        """Run Super Agent triage to decide: answer directly or plan."""
        agent_descs = self._format_agent_descriptions()
        context = self.conversations.get_context_summary(conversation_id)

        prompt = SUPER_AGENT_PROMPT.format(
            conversation_context=context or "(no prior conversation)",
            agent_descriptions=agent_descs,
        )

        try:
            response = self._query_llm(
                prompt=f"User query: {query}",
                system_prompt=prompt,
                max_tokens=1024,
                temperature=0.2,
            )

            decision_str = response.get("decision", "handoff_to_planner")
            decision = TriageDecision(decision_str) if decision_str in [d.value for d in TriageDecision] else TriageDecision.HANDOFF_TO_PLANNER

            return TriageResult(
                decision=decision,
                answer_content=response.get("answer_content"),
                enriched_query=response.get("enriched_query"),
                reason=response.get("reason", ""),
            )
        except Exception as e:
            logger.warning(f"Triage failed, defaulting to planner: {e}")
            return TriageResult(
                decision=TriageDecision.HANDOFF_TO_PLANNER,
                enriched_query=query,
                reason=f"Triage error, defaulting to planner: {e}",
            )

    # ------------------------------------------------------------------
    # Phase 2: LLM Planner
    # ------------------------------------------------------------------

    async def _plan(self, enriched_query: str, conversation_id: str) -> ExecutionPlan:
        """Use LLM to decompose query into agent tasks."""
        agent_descs = self._format_agent_descriptions()
        context = self.conversations.get_context_summary(conversation_id)

        prompt = PLANNER_PROMPT.format(
            agent_descriptions=agent_descs,
            conversation_context=context or "(no prior conversation)",
        )

        try:
            response = self._query_llm(
                prompt=f"Query to plan: {enriched_query}",
                system_prompt=prompt,
                max_tokens=2048,
                temperature=0.3,
            )

            tasks = []
            synthesis_prompt = response.get("synthesis_prompt", "")

            for i, t in enumerate(response.get("tasks", [])):
                agent_id = t.get("agent_id", "")
                # Validate agent exists
                if agent_id not in self.registry:
                    logger.warning(f"Planner referenced unknown agent: {agent_id}, skipping")
                    continue

                tasks.append(TaskPlan(
                    task_id=f"task_{i+1}",
                    agent_id=agent_id,
                    query=t.get("query", enriched_query),
                    title=t.get("title", f"Task {i+1}"),
                    depends_on=t.get("depends_on"),
                ))

            return ExecutionPlan(
                plan_id=str(uuid.uuid4())[:12],
                original_query=enriched_query,
                enriched_query=enriched_query,
                tasks=tasks,
                reasoning=response.get("reasoning", ""),
            )

        except Exception as e:
            logger.error(f"Planning failed: {e}")
            # Fallback: single task to the first available agent
            fallback_agents = self.registry.ids()
            if fallback_agents:
                return ExecutionPlan(
                    plan_id=str(uuid.uuid4())[:12],
                    original_query=enriched_query,
                    enriched_query=enriched_query,
                    tasks=[TaskPlan(
                        task_id="task_1",
                        agent_id=fallback_agents[0],
                        query=enriched_query,
                        title="Fallback analysis",
                    )],
                    reasoning=f"Planning failed ({e}), falling back to {fallback_agents[0]}",
                )
            return ExecutionPlan(
                plan_id=str(uuid.uuid4())[:12],
                original_query=enriched_query,
                enriched_query=enriched_query,
                tasks=[],
                reasoning=f"Planning failed and no agents available: {e}",
            )

    # ------------------------------------------------------------------
    # Phase 3: Async Task Executor
    # ------------------------------------------------------------------

    async def _execute_tasks(
        self, tasks: List[TaskPlan]
    ) -> AsyncGenerator[tuple[OrchestratorEvent, Optional[TaskResult]], None]:
        """Execute tasks in parallel, yielding events as they complete."""

        # Separate independent tasks from dependent ones
        independent = [t for t in tasks if not t.depends_on]
        dependent = [t for t in tasks if t.depends_on]

        # Run independent tasks concurrently
        if independent:
            results_map: Dict[str, TaskResult] = {}

            async def run_task(task: TaskPlan) -> tuple[TaskPlan, TaskResult]:
                agent = self.registry.get(task.agent_id)
                if not agent:
                    return task, TaskResult(
                        task_id=task.task_id,
                        agent_id=task.agent_id,
                        title=task.title,
                        status="failed",
                        error=f"Agent {task.agent_id} not found",
                    )

                agent_input = AgentInput(
                    entity_name=task.query,
                    context={"query": task.query, "title": task.title},
                )

                output = await agent.timed_run(agent_input)

                return task, TaskResult(
                    task_id=task.task_id,
                    agent_id=task.agent_id,
                    title=task.title,
                    status=output.status,
                    data=output.data,
                    error=output.error,
                    execution_time=output.execution_time,
                )

            # Emit start events
            for task in independent:
                yield OrchestratorEvent(
                    OrchestratorEventType.TASK_START,
                    message=f"Starting: {task.title}",
                    data={"task_id": task.task_id, "agent_id": task.agent_id, "title": task.title},
                ), None

            # Run all independent tasks concurrently
            coroutines = [run_task(t) for t in independent]
            for coro in asyncio.as_completed(coroutines):
                task, result = await coro
                results_map[task.task_id] = result

                event_type = (
                    OrchestratorEventType.TASK_COMPLETE
                    if result.status == "completed"
                    else OrchestratorEventType.TASK_FAILED
                )
                yield OrchestratorEvent(
                    event_type,
                    message=f"{'✅' if result.status == 'completed' else '❌'} {task.title} ({result.execution_time:.1f}s)",
                    data={
                        "task_id": task.task_id,
                        "agent_id": task.agent_id,
                        "title": task.title,
                        "status": result.status,
                        "execution_time": result.execution_time,
                    },
                ), result

            # Run dependent tasks (sequentially for now)
            for task in dependent:
                yield OrchestratorEvent(
                    OrchestratorEventType.TASK_START,
                    message=f"Starting: {task.title}",
                    data={"task_id": task.task_id, "agent_id": task.agent_id, "title": task.title},
                ), None

                # Inject dependency results into context
                dep_results = {}
                for dep_id in (task.depends_on or []):
                    if dep_id in results_map:
                        dep_results[dep_id] = results_map[dep_id].data

                agent = self.registry.get(task.agent_id)
                if not agent:
                    result = TaskResult(
                        task_id=task.task_id, agent_id=task.agent_id,
                        title=task.title, status="failed",
                        error=f"Agent {task.agent_id} not found",
                    )
                else:
                    agent_input = AgentInput(
                        entity_name=task.query,
                        context={"query": task.query, "dependencies": dep_results},
                    )
                    output = await agent.timed_run(agent_input)
                    result = TaskResult(
                        task_id=task.task_id, agent_id=task.agent_id,
                        title=task.title, status=output.status,
                        data=output.data, error=output.error,
                        execution_time=output.execution_time,
                    )

                results_map[task.task_id] = result
                event_type = (
                    OrchestratorEventType.TASK_COMPLETE
                    if result.status == "completed"
                    else OrchestratorEventType.TASK_FAILED
                )
                yield OrchestratorEvent(
                    event_type,
                    message=f"{'✅' if result.status == 'completed' else '❌'} {task.title}",
                    data={"task_id": task.task_id, "status": result.status},
                ), result

    # ------------------------------------------------------------------
    # Phase 4: Synthesis
    # ------------------------------------------------------------------

    async def _synthesize(
        self,
        original_query: str,
        results: List[TaskResult],
        plan: ExecutionPlan,
    ) -> str:
        """Synthesize all task results into a coherent analysis."""

        # Format results for the synthesis prompt
        results_text = []
        for r in results:
            status_icon = "✅" if r.status == "completed" else "❌"
            results_text.append(f"\n### {status_icon} {r.title} (Agent: {r.agent_id})")
            if r.status == "completed":
                # Summarize data
                data_str = json.dumps(r.data, ensure_ascii=False, indent=2, default=str)
                # Truncate very long outputs
                if len(data_str) > 3000:
                    data_str = data_str[:3000] + "\n... (truncated)"
                results_text.append(data_str)
            else:
                results_text.append(f"Error: {r.error}")

        prompt = SYNTHESIS_PROMPT.format(
            original_query=original_query,
            agent_results="\n".join(results_text),
            synthesis_instructions=plan.reasoning or "Combine all findings into a coherent analysis.",
        )

        try:
            # For synthesis, we want a text response, not JSON
            switcher = self._get_provider_switcher()
            response_text = switcher.query(
                prompt=f"Synthesize this analysis:\n\n{prompt}",
                system_prompt="You are a senior financial analyst synthesizing multi-source intelligence. Respond in the same language as the original query. Be structured, concise, and actionable.",
                max_tokens=4096,
                temperature=0.3,
            )
            return response_text
        except Exception as e:
            logger.error(f"Synthesis failed: {e}")
            # Fallback: simple concatenation
            parts = [f"## Analysis: {original_query}\n"]
            for r in results:
                parts.append(f"### {r.title}")
                if r.status == "completed":
                    parts.append(json.dumps(r.data, ensure_ascii=False, indent=2, default=str)[:1000])
                else:
                    parts.append(f"Failed: {r.error}")
            return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _format_agent_descriptions(self) -> str:
        """Format all registered agent cards as text for LLM prompts."""
        cards = self.registry.list_cards()
        if not cards:
            return "(no agents registered)"

        lines = []
        for card in cards:
            caps = ", ".join(card.capabilities) if card.capabilities else "general"
            lines.append(
                f"- **{card.agent_id}** ({card.name}): {card.description} "
                f"[capabilities: {caps}]"
            )
        return "\n".join(lines)

    def _get_provider_switcher(self):
        """Lazy-load provider switcher."""
        if self._provider_switcher is None:
            from utils.provider_switcher import ProviderSwitcher
            self._provider_switcher = ProviderSwitcher()
        return self._provider_switcher

    def _query_llm(
        self,
        prompt: str,
        system_prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.3,
    ) -> Dict[str, Any]:
        """Query LLM and parse JSON response."""
        switcher = self._get_provider_switcher()
        response_text = switcher.query(
            prompt=prompt,
            system_prompt=system_prompt + "\n\nIMPORTANT: Return your response as valid JSON only. No markdown, no code blocks, no comments.",
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return self._parse_json(response_text)

    @staticmethod
    def _parse_json(text: str) -> Dict[str, Any]:
        """Parse JSON from LLM response, handling code blocks."""
        try:
            if "```json" in text:
                start = text.find("```json") + 7
                end = text.find("```", start)
                text = text[start:end].strip()
            elif "```" in text:
                start = text.find("```") + 3
                end = text.find("```", start)
                text = text[start:end].strip()
            else:
                text = text.strip()
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse failed: {e}")
            logger.debug(f"Raw text: {text[:500]}")
            return {}
