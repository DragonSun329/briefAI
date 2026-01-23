"""
Adversarial Intelligence Agents

Three-agent workflow for conviction scoring:
- HypeMan: Identifies breakout velocity and adoption signals
- Skeptic: Forensic analysis of commercial maturity and risk factors
- Arbiter: Synthesizes conflicting data into conviction score
"""

from agents.hypeman import HypeManAgent
from agents.skeptic import SkepticAgent
from agents.arbiter import ArbiterAgent

__all__ = ["HypeManAgent", "SkepticAgent", "ArbiterAgent"]
