from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(slots=True)
class Event:
    """Simple typed event used to drive behavior transitions."""

    name: str
    payload: Dict[str, Any] = field(default_factory=dict)
    source: str = "system"
    tick: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "payload": dict(self.payload),
            "source": self.source,
            "tick": self.tick,
        }


@dataclass(slots=True)
class EventStream:
    events: List[Event] = field(default_factory=list)

    def push(self, event: Event) -> None:
        self.events.append(event)

    def latest(self) -> Optional[Event]:
        return self.events[-1] if self.events else None

    def clear(self) -> None:
        self.events.clear()
