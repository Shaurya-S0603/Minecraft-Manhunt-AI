from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(slots=True)
class AgentContext:
    """Snapshot of the agent's current state and working memory."""

    player_id: str
    role: str = "runner"
    difficulty: str = "normal"
    match_id: Optional[str] = None
    phase: str = "SETUP"
    last_known_position: Optional[tuple[float, float, float]] = None
    last_action: Optional[str] = None
    memory: Dict[str, Any] = field(default_factory=dict)
    recent_events: List[str] = field(default_factory=list)

    def update_memory(self, key: str, value: Any) -> None:
        self.memory[key] = value

    def set_last_known_position(self, position: tuple[float, float, float]) -> None:
        self.last_known_position = position
