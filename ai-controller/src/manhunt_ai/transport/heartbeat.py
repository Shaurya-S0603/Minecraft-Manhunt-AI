from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any


@dataclass(frozen=True, slots=True)
class Heartbeat:
    process_id: str
    match_id: str
    agent_id: str | None = None
    last_known_tick: int = 0
    timestamp: float = 0.0
    health: str = "healthy"

    def as_payload(self) -> dict[str, Any]:
        return {
            "process_id": self.process_id,
            "match_id": self.match_id,
            "agent_id": self.agent_id,
            "last_known_tick": self.last_known_tick,
            "timestamp": self.timestamp,
            "health": self.health,
        }


class HeartbeatMonitor:
    def __init__(self, timeout_seconds: float = 5.0, clock=time.monotonic):
        if timeout_seconds <= 0:
            raise ValueError("Heartbeat timeout must be positive")
        self.timeout_seconds = timeout_seconds
        self._clock = clock
        self.last_received: float | None = None
        self.last_heartbeat: Heartbeat | None = None

    def record(self, heartbeat: Heartbeat, received_at: float | None = None) -> None:
        self.last_heartbeat = heartbeat
        self.last_received = self._clock() if received_at is None else received_at

    def is_healthy(self, now: float | None = None) -> bool:
        if self.last_received is None:
            return False
        current = self._clock() if now is None else now
        return current - self.last_received <= self.timeout_seconds

    @property
    def status(self) -> str:
        return "healthy" if self.is_healthy() else "stale"
