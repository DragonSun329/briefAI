"""
Base Agent Interface

Defines the contract for all briefAI agents. Agents are independent units
of LLM-powered analysis that can be:
  - Run standalone (python -m agents.hypeman)
  - Composed in pipelines (adversarial pipeline)
  - Registered for discovery and remote invocation
  - Swapped without touching orchestrator code

Usage:
    from agents.base import BaseAgent, AgentInput, AgentOutput, AgentCard

    class MyAgent(BaseAgent):
        @property
        def card(self) -> AgentCard:
            return AgentCard(
                agent_id="my_agent",
                name="My Agent",
                description="Does smart analysis",
                input_schema={"entity_name": "str", "signals": "dict"},
                output_schema={"score": "int", "thesis": "str"},
            )

        async def run(self, input: AgentInput) -> AgentOutput:
            # ... do work ...
            return AgentOutput(agent_id="my_agent", status="completed", data={...})
"""

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
from loguru import logger


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class AgentCard:
    """
    Describes an agent's capabilities — used for discovery, registration,
    and planner selection.
    """
    agent_id: str
    name: str
    description: str
    version: str = "1.0.0"
    input_schema: Dict[str, str] = field(default_factory=dict)
    output_schema: Dict[str, str] = field(default_factory=dict)
    capabilities: List[str] = field(default_factory=list)
    # Which model task this agent should use (maps to config/models.yaml tasks)
    model_task: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AgentInput:
    """
    Standardized input to any agent.

    Args:
        entity_name: Primary entity being analyzed.
        signals: Pre-gathered signal data (optional, agent can gather its own).
        context: Additional context from the orchestrator or other agents.
        params: Agent-specific parameters (temperature override, etc.).
    """
    entity_name: str
    signals: Dict[str, Any] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)
    params: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AgentOutput:
    """
    Standardized output from any agent.

    Args:
        agent_id: Which agent produced this output.
        status: "completed", "failed", "partial".
        data: The agent's actual output (scores, thesis, signals, etc.).
        execution_time: How long the agent took (seconds).
        error: Error message if status is "failed".
        metadata: Extra info (model used, tokens consumed, etc.).
    """
    agent_id: str
    status: str = "completed"
    data: Dict[str, Any] = field(default_factory=dict)
    execution_time: float = 0.0
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @property
    def succeeded(self) -> bool:
        return self.status == "completed"


# ---------------------------------------------------------------------------
# Base Agent
# ---------------------------------------------------------------------------

class BaseAgent(ABC):
    """
    Abstract base class for all briefAI agents.

    Subclasses must implement:
        - card (property): AgentCard describing capabilities
        - run(input): async method that processes input and returns output

    Provides:
        - Model config integration via get_model_config()
        - LLM client helpers
        - JSON response parsing
        - Timed execution wrapper
    """

    def __init__(self, llm_client=None):
        self._llm_client = llm_client
        self._provider_switcher = None

    # ---- Abstract interface ----

    @property
    @abstractmethod
    def card(self) -> AgentCard:
        """Agent's capability card for discovery/registration."""
        ...

    @abstractmethod
    async def run(self, input: AgentInput) -> AgentOutput:
        """
        Execute the agent's analysis.

        Args:
            input: Standardized agent input.

        Returns:
            AgentOutput with results.
        """
        ...

    # ---- Sync adapter (backward compat) ----

    def run_sync(self, input: AgentInput) -> AgentOutput:
        """Synchronous wrapper for run(). Use async variant when possible."""
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            # We're already in an async context — use nest_asyncio or run in thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, self.run(input)).result()
        except RuntimeError:
            return asyncio.run(self.run(input))

    # ---- Model config ----

    def get_model_config(self):
        """Get this agent's model config from config/models.yaml."""
        try:
            from utils.model_config import get_model_config
            task = self.card.model_task
            if task:
                return get_model_config(task=task)
            return get_model_config()
        except Exception as e:
            logger.debug(f"Could not load model config: {e}")
            return None

    # ---- LLM helpers ----

    def _get_llm_client(self):
        """Lazy load LLM client."""
        if self._llm_client is None:
            from utils.llm_client import LLMClient
            self._llm_client = LLMClient(enable_caching=True)
        return self._llm_client

    def _get_provider_switcher(self):
        """Lazy load provider switcher with fallback."""
        if self._provider_switcher is None:
            from utils.provider_switcher import ProviderSwitcher
            self._provider_switcher = ProviderSwitcher()
        return self._provider_switcher

    def _query_llm(
        self,
        prompt: str,
        system_prompt: str,
        max_tokens: int = 4096,
        temperature: float = 0.3,
        use_switcher: bool = True,
    ) -> Dict[str, Any]:
        """
        Query LLM and parse JSON response.

        Args:
            prompt: User message.
            system_prompt: System prompt.
            max_tokens: Max tokens.
            temperature: Temperature.
            use_switcher: Use ProviderSwitcher with fallback (default True).

        Returns:
            Parsed JSON dict from LLM response.
        """
        system_prompt_full = system_prompt + "\n\nIMPORTANT: Return your response as valid JSON format."

        if use_switcher:
            switcher = self._get_provider_switcher()
            response_text = switcher.query(
                prompt=prompt,
                system_prompt=system_prompt_full,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            logger.debug(f"[LLM Raw] First 300 chars: {response_text[:300] if response_text else 'EMPTY'}")
            logger.debug(f"[LLM Raw] Last 200 chars: {response_text[-200:] if response_text else 'EMPTY'}")
            return self._parse_json_response(response_text)
        else:
            client = self._get_llm_client()
            return client.chat_structured(
                system_prompt=system_prompt,
                user_message=prompt,
                temperature=temperature,
            )

    @staticmethod
    def _parse_json_response(response_text: str) -> Dict[str, Any]:
        """Parse JSON from LLM response, handling code blocks, thinking tags, and reasoning prefixes."""
        import re
        try:
            text = response_text

            # Strip DeepSeek R1 <think>...</think> blocks
            text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()

            # Extract from code blocks first (handles ```json ... ``` wrapping)
            if "```json" in text:
                start = text.find("```json") + 7
                end = text.find("```", start)
                if end > start:
                    text = text[start:end].strip()
            elif "```" in text:
                # Could be ```\n{json}\n``` or ```python etc
                start = text.find("```") + 3
                # Skip language identifier on same line
                newline = text.find("\n", start)
                if newline > start and newline - start < 20:
                    start = newline + 1
                end = text.find("```", start)
                if end > start:
                    text = text[start:end].strip()

            # Find matching JSON object/array with brace counting
            def _extract_json(s: str) -> Dict[str, Any]:
                # Find first { or [
                json_start = -1
                for i, c in enumerate(s):
                    if c in ('{', '['):
                        json_start = i
                        break
                if json_start < 0:
                    return json.loads(s)  # last resort

                s = s[json_start:]
                open_char = s[0]
                close_char = '}' if open_char == '{' else ']'
                depth = 0
                in_string = False
                escape = False
                for i, c in enumerate(s):
                    if escape:
                        escape = False
                        continue
                    if c == '\\' and in_string:
                        escape = True
                        continue
                    if c == '"' and not escape:
                        in_string = not in_string
                        continue
                    if in_string:
                        continue
                    if c == open_char:
                        depth += 1
                    elif c == close_char:
                        depth -= 1
                        if depth == 0:
                            return json.loads(s[:i+1])
                # If we didn't find matching close, try whole thing
                return json.loads(s)

            return _extract_json(text)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON response: {e}")
            logger.warning(f"Unparseable text (first 500 chars): {text[:500]}")
            logger.warning(f"Unparseable text (last 300 chars): {text[-300:]}")
            return {}

    # ---- Execution helpers ----

    async def timed_run(self, input: AgentInput) -> AgentOutput:
        """Run with automatic timing and error handling."""
        t0 = time.time()
        try:
            output = await self.run(input)
            output.execution_time = time.time() - t0
            return output
        except Exception as e:
            logger.error(f"Agent {self.card.agent_id} failed: {e}")
            return AgentOutput(
                agent_id=self.card.agent_id,
                status="failed",
                error=str(e),
                execution_time=time.time() - t0,
            )


# ---------------------------------------------------------------------------
# Agent Registry
# ---------------------------------------------------------------------------

class AgentRegistry:
    """
    Registry for agent implementations.

    Usage:
        registry = AgentRegistry()
        registry.register(HypeManAgent())
        registry.register(SkepticAgent())

        agent = registry.get("hypeman")
        cards = registry.list_cards()
    """

    def __init__(self):
        self._agents: Dict[str, BaseAgent] = {}

    def register(self, agent: BaseAgent) -> None:
        """Register an agent instance."""
        aid = agent.card.agent_id
        if aid in self._agents:
            logger.warning(f"Overwriting registered agent: {aid}")
        self._agents[aid] = agent
        logger.info(f"Registered agent: {aid} ({agent.card.name})")

    def get(self, agent_id: str) -> Optional[BaseAgent]:
        """Get an agent by ID."""
        return self._agents.get(agent_id)

    def list_cards(self) -> List[AgentCard]:
        """Get all registered agent cards."""
        return [a.card for a in self._agents.values()]

    def ids(self) -> List[str]:
        """Get all registered agent IDs."""
        return list(self._agents.keys())

    def all(self) -> List[BaseAgent]:
        """Get all registered agents."""
        return list(self._agents.values())

    def __contains__(self, agent_id: str) -> bool:
        return agent_id in self._agents

    def __len__(self) -> int:
        return len(self._agents)
