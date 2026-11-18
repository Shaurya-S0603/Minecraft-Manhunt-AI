from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


CONTRACT_VERSION = "1"
MAX_MESSAGE_BYTES = 64 * 1024
MESSAGE_TYPES = {"observation", "action_request", "action_ack", "heartbeat", "match_state"}


class ProtocolError(ValueError):
    """Raised when a wire message violates the adapter contract."""


@dataclass(frozen=True, slots=True)
class Envelope:
    contract_version: str
    message_type: str
    sender: str
    match_id: str
    request_id: str
    payload: dict[str, Any]
    tick: int | None = None
    timestamp: float | None = None

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "contract_version": self.contract_version,
            "message_type": self.message_type,
            "sender": self.sender,
            "match_id": self.match_id,
            "request_id": self.request_id,
            "payload": dict(self.payload),
        }
        if self.tick is not None:
            result["tick"] = self.tick
        if self.timestamp is not None:
            result["timestamp"] = self.timestamp
        return result


def validate_message(
    message: Mapping[str, Any],
    *,
    expected_match_id: str | None = None,
    expected_sender: str | None = None,
    max_bytes: int = MAX_MESSAGE_BYTES,
) -> Envelope:
    if not isinstance(message, Mapping):
        raise ProtocolError("Message must be a mapping")
    required = ("contract_version", "message_type", "sender", "match_id", "request_id", "payload")
    missing = [field for field in required if field not in message]
    if missing:
        raise ProtocolError(f"Missing required fields: {', '.join(missing)}")
    if message["contract_version"] != CONTRACT_VERSION:
        raise ProtocolError(f"Unsupported contract version: {message['contract_version']!r}")
    message_type = message["message_type"]
    if message_type not in MESSAGE_TYPES:
        raise ProtocolError(f"Unsupported message type: {message_type!r}")
    for field in ("sender", "match_id", "request_id"):
        if not isinstance(message[field], str) or not message[field].strip():
            raise ProtocolError(f"{field} must be a non-empty string")
    if expected_match_id is not None and message["match_id"] != expected_match_id:
        raise ProtocolError("Message belongs to a different match")
    if expected_sender is not None and message["sender"] != expected_sender:
        raise ProtocolError("Message sender is not authorized")
    if not isinstance(message["payload"], Mapping):
        raise ProtocolError("payload must be an object")
    if len(repr(dict(message)).encode("utf-8")) > max_bytes:
        raise ProtocolError("Message exceeds the maximum size")
    if "tick" in message and (not isinstance(message["tick"], int) or message["tick"] < 0):
        raise ProtocolError("tick must be a non-negative integer")
    if "timestamp" in message and not isinstance(message["timestamp"], (int, float)):
        raise ProtocolError("timestamp must be numeric")
    return Envelope(
        contract_version=message["contract_version"],
        message_type=message_type,
        sender=message["sender"],
        match_id=message["match_id"],
        request_id=message["request_id"],
        payload=dict(message["payload"]),
        tick=message.get("tick"),
        timestamp=message.get("timestamp"),
    )


def validate_envelope(message: Mapping[str, Any], **kwargs: Any) -> Envelope:
    return validate_message(message, **kwargs)
