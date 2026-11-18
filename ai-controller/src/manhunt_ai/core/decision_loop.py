from __future__ import annotations

from typing import Optional

from ..agents.agent_factory import build_agent
from ..core.action import Action
from ..core.agent_context import AgentContext
from ..core.observation import Observation


class DecisionLoop:
    """Minimal observe -> decide -> act loop."""

    def __init__(self, player_id: str, role: str, difficulty: str = "normal"):
        self.context = AgentContext(
            player_id=player_id,
            role=role,
            difficulty=difficulty,
            phase="SETUP",
        )
        self.policy = build_agent(role, difficulty)

    def handle_observation(self, observation: Observation) -> Optional[Action]:
        # Remember the opponent, not the AI's own position.
        opponent = "runner" if self.context.role == "hunter" else "hunter"
        for name, position in observation.visible_entities.items():
            if opponent in name.lower():
                self.context.last_known_position = position
                break
        self.context.phase = self.context.phase or "SETUP"
        action = self.policy.decide(observation, self.context)
        if action is not None:
            self.context.last_action = action.name
        return action

    def update_phase(self, phase: str) -> None:
        self.context.phase = phase
