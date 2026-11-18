"""Minimal Minecraft RCON client using only the Python standard library.

Security: intended for 127.0.0.1 only. RCON is unencrypted.
"""
from __future__ import annotations

import socket
import struct
from threading import RLock


class RconError(RuntimeError):
    pass


class RconClient:
    def __init__(self, host: str, port: int, password: str, timeout: float = 4.0):
        if host not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError("This prototype only allows local RCON connections")
        self.host, self.port, self.password = host, int(port), password
        self.timeout = timeout
        self.sock: socket.socket | None = None
        self.seq = 100
        self.lock = RLock()

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *_):
        self.close()

    def connect(self):
        self.close()
        self.sock = socket.create_connection((self.host, self.port), self.timeout)
        self.sock.settimeout(self.timeout)
        req = self._packet(3, self.password)
        # Servers may emit an empty response before the actual auth response.
        for _ in range(4):
            response_id, response_type, _ = self._read_packet()
            if response_id == -1:
                self.close()
                raise RconError("RCON login rejected. Check the local password.")
            if response_id == req and response_type == 2:
                return
        self.close()
        raise RconError("No RCON authentication response")

    def close(self):
        if self.sock is not None:
            try:
                self.sock.close()
            finally:
                self.sock = None

    def _recv_exact(self, n: int) -> bytes:
        assert self.sock is not None
        data = bytearray()
        while len(data) < n:
            chunk = self.sock.recv(n - len(data))
            if not chunk:
                raise RconError("RCON server closed the connection")
            data.extend(chunk)
        return bytes(data)

    def _read_packet(self):
        (length,) = struct.unpack('<i', self._recv_exact(4))
        if not 10 <= length <= 1024 * 1024:
            raise RconError(f"Invalid RCON packet length: {length}")
        content = self._recv_exact(length)
        req, packet_type = struct.unpack('<ii', content[:8])
        if content[-2:] != b'\x00\x00':
            raise RconError("Invalid RCON packet terminator")
        return req, packet_type, content[8:-2].decode('utf-8', errors='replace')

    def _packet(self, packet_type: int, value: str) -> int:
        assert self.sock is not None
        self.seq += 1
        req = self.seq
        body = struct.pack('<ii', req, packet_type) + value.encode('utf-8') + b'\x00\x00'
        self.sock.sendall(struct.pack('<i', len(body)) + body)
        return req

    def command(self, command: str) -> str:
        if not command or '\n' in command or '\r' in command:
            raise ValueError("RCON commands must be a single line")
        with self.lock:
            if self.sock is None:
                self.connect()
            try:
                req = self._packet(2, command.lstrip('/'))
                for _ in range(4):
                    response_id, _, text = self._read_packet()
                    if response_id == req:
                        return text
                raise RconError("RCON response did not match request")
            except (OSError, RconError):
                self.close()
                raise
