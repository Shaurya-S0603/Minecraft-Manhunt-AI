from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple


@dataclass(slots=True)
class Observation:
    """Normalized observation of a player state and the local environment."""

    tick: int = 0
    player_id: str = "unknown"
    position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    dimension: str = "overworld"
    health: float = 20.0
    hunger: float = 20.0
    inventory: Dict[str, int] = field(default_factory=dict)
    visible_entities: Dict[str, Tuple[float, float, float]] = field(default_factory=dict)
    terrain: Dict[str, Any] = field(default_factory=dict)
    events: List[str] = field(default_factory=list)
    timestamp: float = 0.0
    known: bool = True

    def distance_to(self, other: Tuple[float, float, float]) -> float:
        x1, y1, z1 = self.position
        x2, y2, z2 = other
        return ((x1 - x2) ** 2 + (y1 - y2) ** 2 + (z1 - z2) ** 2) ** 0.5

    def as_dict(self) -> Dict[str, Any]:
        return {
            "tick": self.tick,
            "player_id": self.player_id,
            "position": list(self.position),
            "dimension": self.dimension,
            "health": self.health,
            "hunger": self.hunger,
            "inventory": dict(self.inventory),
            "visible_entities": {k: list(v) for k, v in self.visible_entities.items()},
            "terrain": dict(self.terrain),
            "events": list(self.events),
            "timestamp": self.timestamp,
            "known": self.known,
        }
