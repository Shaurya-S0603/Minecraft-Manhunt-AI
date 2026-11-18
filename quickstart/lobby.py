"""A server-resident post-match lobby with no client mod or OP permissions needed.

Players use vanilla /trigger to request another round or switch roles.
Console can accept R (replay), S (switch), or Q (shut down).
"""
from __future__ import annotations
import queue
import re
import sys
import threading
import time
from .observations import validate_name
from .results import component

REPLAY = 'mh_replay'
SWITCH = 'mh_switch'
_SCORE_RE = re.compile(r'\bhas\s+(-?\d+)\s+\[')


def parse_score(response: str) -> int | None:
    """Parse vanilla Java's scoreboard players get output (or return None)."""
    match = _SCORE_RE.search(response)
    return int(match.group(1)) if match else None


class Lobby:
    def __init__(self, rcon):
        self.rcon = rcon
        self.console_queue = queue.Queue()
        self._console_thread = None

    def start_console(self):
        if self._console_thread is not None:
            return
        def read_lines():
            for line in sys.stdin:
                self.console_queue.put(line.strip().lower())
        self._console_thread = threading.Thread(target=read_lines, daemon=True, name='manhunt-console')
        self._console_thread.start()

    def setup(self):
        # If this server has already hosted a Manhunt session, the objectives exist.
        for objective in (REPLAY, SWITCH):
            self.rcon.command(f'scoreboard objectives add {objective} trigger')

    def prepare_player(self, player: str):
        player = validate_name(player)
        for objective in (REPLAY, SWITCH):
            # Zero the previous session's score before re-enabling the trigger.
            self.rcon.command(f'scoreboard players set {player} {objective} 0')
            self.rcon.command(f'scoreboard players enable {player} {objective}')

    def clear_pending_console(self):
        while True:
            try:
                self.console_queue.get_nowait()
            except queue.Empty:
                return

    def poll_action(self, player: str) -> str | None:
        player = validate_name(player)
        for objective, action in ((SWITCH, 'switch'), (REPLAY, 'replay')):
            try:
                score = parse_score(self.rcon.command(f'scoreboard players get {player} {objective}'))
            except (OSError, ValueError):
                score = None
            if score is not None and score >= 1:
                self.rcon.command(f'scoreboard players set {player} {objective} 0')
                return action
        try:
            choice = self.console_queue.get_nowait()
        except queue.Empty:
            return None
        return {'r':'replay','replay':'replay', 's':'switch', 'switch':'switch', 'q':'quit', 'quit':'quit'}.get(choice)

    def wait_for_next_round(self, player: str, server_proc=None, poll_seconds: float = 1.0) -> str:
        player = validate_name(player)
        print('\n[LOBBY] Match ended, Minecraft server remains ONLINE.')
        print('[LOBBY] IN GAME: /trigger mh_replay   OR   /trigger mh_switch')
        print('[LOBBY] IN CONSOLE: R replay, S switch sides, Q gracefully stop server.')
        last_reminder = time.monotonic()
        while True:
            if server_proc is not None and server_proc.poll() is not None:
                return 'quit'
            result = self.poll_action(player)
            if result:
                return result
            if time.monotonic() - last_reminder > 40:
                # Only the action bar is refreshed; the central result screen can fade normally.
                try:
                    self.rcon.command(f'title {player} actionbar {component("/trigger mh_replay  |  /trigger mh_switch", "aqua")}')
                except OSError:
                    pass
                last_reminder = time.monotonic()
            time.sleep(poll_seconds)
