import pytest

from manhunt_ai.transport.client import AdapterClient, ConnectionConfig
from manhunt_ai.transport.heartbeat import Heartbeat, HeartbeatMonitor
from manhunt_ai.transport.protocol_validation import ProtocolError, validate_message


def test_message_round_trip_and_match_guard():
    client = AdapterClient(ConnectionConfig(match_id="match-1", expected_peer="adapter"))
    client.connect()
    outgoing = client.send("action_request", {"action": "stop"}, tick=4)
    assert outgoing["contract_version"] == "1"
    incoming = {
        "contract_version": "1",
        "message_type": "action_ack",
        "sender": "adapter",
        "match_id": "match-1",
        "request_id": "req-1",
        "payload": {"status": "succeeded"},
    }
    assert client.receive(incoming).payload["status"] == "succeeded"
    with pytest.raises(ProtocolError):
        client.receive({**incoming, "match_id": "other-match"})


def test_protocol_rejects_unknown_type_and_oversized_payload():
    message = {
        "contract_version": "1",
        "message_type": "unknown",
        "sender": "adapter",
        "match_id": "match-1",
        "request_id": "req-1",
        "payload": {},
    }
    with pytest.raises(ProtocolError):
        validate_message(message)
    with pytest.raises(ProtocolError):
        validate_message({**message, "message_type": "heartbeat", "payload": {"x": "y" * 100}}, max_bytes=32)


def test_heartbeat_monitor_ages_out():
    monitor = HeartbeatMonitor(timeout_seconds=2.0)
    heartbeat = Heartbeat(process_id="adapter-1", match_id="match-1", timestamp=10.0)
    monitor.record(heartbeat, received_at=10.0)
    assert monitor.is_healthy(now=12.0)
    assert not monitor.is_healthy(now=12.01)
