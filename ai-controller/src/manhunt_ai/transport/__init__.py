"""Versioned, adapter-neutral transport primitives."""

from .client import AdapterClient, ConnectionConfig
from .heartbeat import Heartbeat, HeartbeatMonitor
from .protocol_validation import (
    CONTRACT_VERSION,
    Envelope,
    ProtocolError,
    validate_envelope,
    validate_message,
)

__all__ = [
    "AdapterClient",
    "CONTRACT_VERSION",
    "ConnectionConfig",
    "Envelope",
    "Heartbeat",
    "HeartbeatMonitor",
    "ProtocolError",
    "validate_envelope",
    "validate_message",
]
