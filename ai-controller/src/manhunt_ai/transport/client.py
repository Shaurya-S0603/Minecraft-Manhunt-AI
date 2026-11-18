from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any, Callable, Deque, Mapping
import uuid

from .protocol_validation import Envelope, validate_message


@dataclass(frozen=True, slots=True)
class ConnectionConfig:
    endpoint: str = "memory://adapter"
    sender: str = "ai-controller"
    match_id: str = ""
    expected_peer: str | None = None


class AdapterClient:
    """Transport-neutral client with an in-memory queue for local integration tests."""

    def __init__(self, config: ConnectionConfig):
        if not config.match_id:
            raise ValueError("match_id is required")
        self.config = config
        self.connected = False
        self._incoming: Deque[Envelope] = deque()
        self._outgoing: Deque[dict[str, Any]] = deque()
        self._listeners: list[Callable[[Envelope], None]] = []

    def connect(self) -> None:
        self.connected = True

    def close(self) -> None:
        self.connected = False
        self._incoming.clear()

    def add_listener(self, listener: Callable[[Envelope], None]) -> None:
        self._listeners.append(listener)

    def send(self, message_type: str, payload: Mapping[str, Any], *, tick: int | None = None) -> dict[str, Any]:
        if not self.connected:
            raise ConnectionError("Adapter client is not connected")
        message = {
            "contract_version": "1",
            "message_type": message_type,
            "sender": self.config.sender,
            "match_id": self.config.match_id,
            "request_id": str(uuid.uuid4()),
            "payload": dict(payload),
        }
        if tick is not None:
            message["tick"] = tick
        validate_message(message, expected_match_id=self.config.match_id)
        self._outgoing.append(message)
        return message

    def receive(self, message: Mapping[str, Any]) -> Envelope:
        if not self.connected:
            raise ConnectionError("Adapter client is not connected")
        envelope = validate_message(
            message,
            expected_match_id=self.config.match_id,
            expected_sender=self.config.expected_peer,
        )
        self._incoming.append(envelope)
        for listener in self._listeners:
            listener(envelope)
        return envelope

    def drain_outgoing(self) -> list[dict[str, Any]]:
        messages = list(self._outgoing)
        self._outgoing.clear()
        return messages

    def drain_incoming(self) -> list[Envelope]:
        messages = list(self._incoming)
        self._incoming.clear()
        return messages
