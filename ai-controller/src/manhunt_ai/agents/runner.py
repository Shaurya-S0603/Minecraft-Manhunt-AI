from __future__ import annotations

from typing import Optional

from ..core.action import Action
from ..core.agent_context import AgentContext
from ..core.observation import Observation


class RunnerPolicy:
    """Simple risk-aware runner policy."""

    def __init__(self, difficulty: str = "normal"):
        self.difficulty = difficulty

    def decide(self, observation: Observation, context: Optional[AgentContext] = None) -> Optional[Action]:
        target_position = None
        for entity_name, position in observation.visible_entities.items():
            if "hunter" in entity_name.lower():
                target_position = position
                break

        if target_position is not None:
            distance = observation.distance_to(target_position)
            if distance <= 18:
                # Retreat in the opposite horizontal direction, rather than a fixed diagonal.
                dx = observation.position[0] - target_position[0]
                dz = observation.position[2] - target_position[2]
                length = max((dx * dx + dz * dz) ** 0.5, 0.01)
                safe_position = (
                    observation.position[0] + 16 * dx / length,
                    observation.position[1],
                    observation.position[2] + 16 * dz / length,
                )
                return Action(
                    name="retreat",
                    target=safe_position,
                    duration=1.0,
                    priority=200,
                    metadata={"reason": "threat-nearby"},
                )


        return Action(
            name="wait",
            duration=0.25,
            priority=5,
            metadata={"reason": "safe"},
        )
