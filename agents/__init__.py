"""
Adversarial Intelligence Agents

Three-agent workflow for conviction scoring:
- HypeMan: Identifies breakout velocity and adoption signals
- Skeptic: Forensic analysis of commercial maturity and risk factors
- Arbiter: Synthesizes conflicting data into conviction score

Agent interface:
- BaseAgent: Abstract base class for all agents
- AgentInput/AgentOutput: Standardized I/O
- AgentCard: Capability descriptor for discovery
- AgentRegistry: Registration and lookup
"""

from agents.base import BaseAgent, AgentCard, AgentInput, AgentOutput, AgentRegistry
from agents.hypeman import HypeManAgent
from agents.skeptic import SkepticAgent
from agents.arbiter import ArbiterAgent
from agents.orchestrator import AgentOrchestrator, ConversationStore

__all__ = [
    # Interface
    "BaseAgent",
    "AgentCard",
    "AgentInput",
    "AgentOutput",
    "AgentRegistry",
    # Orchestrator
    "AgentOrchestrator",
    "ConversationStore",
    # Implementations
    "HypeManAgent",
    "SkepticAgent",
    "ArbiterAgent",
]
