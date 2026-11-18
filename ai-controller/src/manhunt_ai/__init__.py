"""Minecraft Manhunt AI package."""

from .behavior.state_machine import MatchPhase, StateMachine
from .core.action import Action, ActionAck
from .core.agent_context import AgentContext
from .core.observation import Observation
from .navigation.astar import AStarPlanner, a_star, astar

__all__ = [
    "Action",
    "ActionAck",
    "AgentContext",
    "AStarPlanner",
    "MatchPhase",
    "Observation",
    "StateMachine",
    "a_star",
    "astar",
]
# Responsibility: Mark this folder as the Python AI package.
# Expected inputs: No runtime input.
# Expected outputs: Module namespace for AI components.
# Constraints: Keep imports lightweight and avoid side effects during import.
# Implementation: write the full source yourself after consulting the relevant docs.
# Testing: add meaningful unit or integration tests before marking complete.
