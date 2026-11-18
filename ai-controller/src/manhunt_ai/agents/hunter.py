from __future__ import annotations

from typing import Any, Optional

from ..core.action import Action
from ..core.agent_context import AgentContext
from ..core.observation import Observation


class HunterPolicy:
    """Simple but deterministic hunting policy."""

    def __init__(self, difficulty: str = "normal"):
        self.difficulty = difficulty

    def decide(self, observation: Observation, context: Optional[AgentContext] = None) -> Optional[Action]:
        target_position = None
        for entity_name, position in observation.visible_entities.items():
            if "runner" in entity_name.lower():
                target_position = position
                break

        if target_position is None and context is not None and context.last_known_position is not None:
            target_position = context.last_known_position

        if target_position is not None:
            return Action(
                name="move-to",
                target=target_position,
                duration=1.0,
                priority=100,
                metadata={"reason": "track-target"},
            )

        return Action(
            name="search",
            duration=2.0,
            priority=10,
            metadata={"reason": "lost-target"},
        )
