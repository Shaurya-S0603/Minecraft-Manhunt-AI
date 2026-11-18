from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple, Union
import uuid

Position = Union[Tuple[float, float, float], Tuple[int, int], str]


@dataclass(slots=True)
class Action:
    """Bounded action request for an AI or human-controlled player."""

    name: str
    target: Optional[Position] = None
    duration: float = 0.0
    priority: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: str = "pending"

    def with_status(self, status: str) -> "Action":
        self.status = status
        return self

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "target": self.target,
            "duration": self.duration,
            "priority": self.priority,
            "metadata": dict(self.metadata),
            "request_id": self.request_id,
            "status": self.status,
        }

    def as_payload(self) -> Dict[str, Any]:
        return self.as_dict()


@dataclass(slots=True)
class ActionAck:
    request_id: str
    status: str
    reason: str = ""
    observation: Optional[Dict[str, Any]] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "status": self.status,
            "reason": self.reason,
            "observation": self.observation,
        }
