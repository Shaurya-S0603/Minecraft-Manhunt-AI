from __future__ import annotations

from collections import deque
from typing import Deque, Dict, Iterable, List, Optional, Tuple

from .observation import Observation


class WorldMemory:
    """Bounded memory of recent observations and inferred target state."""

    def __init__(self, max_items: int = 64):
        self.max_items = max_items
        self._observations: Deque[Observation] = deque(maxlen=max_items)
        self._last_known_positions: Dict[str, Tuple[float, float, float]] = {}
        self.route: List[Tuple[int, int]] = []

    def remember(self, observation: Observation) -> None:
        self._observations.append(observation)
        if observation.player_id:
            self._last_known_positions[observation.player_id] = observation.position

    def last_known_position(self, player_id: str) -> Optional[Tuple[float, float, float]]:
        return self._last_known_positions.get(player_id)

    def recent_observations(self, limit: Optional[int] = None) -> List[Observation]:
        items = list(self._observations)
        if limit is not None:
            return items[-limit:]
        return items

    def set_route(self, route: Iterable[Tuple[int, int]]) -> None:
        self.route = list(route)

    def clear(self) -> None:
        self._observations.clear()
        self._last_known_positions.clear()
        self.route.clear()
