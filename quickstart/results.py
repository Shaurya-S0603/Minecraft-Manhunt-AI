"""In-game feedback for completed hit-Manhunt rounds.

Uses vanilla /title, /tellraw, and /playsound-like text only; no client mod is required.
Minecraft 1.21.11 accepts text components with SNBT-compatible object syntax.
"""
from __future__ import annotations
import json
from dataclasses import dataclass
from .observations import validate_name


def component(text: str, color: str = 'white', bold: bool = False) -> str:
    """Build a safe text component with no arbitrary commands embedded."""
    return json.dumps({'text': text, 'color': color, 'bold': bold}, separators=(',', ':'))


@dataclass(frozen=True)
class RoundResult:
    human_role: str
    winner: str
    human_player: str
    elapsed_seconds: float = 0.0
    reason: str = 'hit'

    def __post_init__(self):
        if self.human_role not in ('hunter', 'runner'):
            raise ValueError('Invalid human role')
        if self.winner not in ('hunter', 'runner'):
            raise ValueError('Invalid winner')
        validate_name(self.human_player)

    @property
    def is_victory(self) -> bool:
        return self.winner == self.human_role

    @property
    def headline(self) -> str:
        return 'VICTORY!' if self.is_victory else 'DEFEAT!'

    @property
    def description(self) -> str:
        if self.reason == 'survival':
            return 'The Runner survived until time expired.'
        return 'The Hunter landed a confirmed hit on the Runner.'


def show_round_result(rcon, result: RoundResult, session_score: str | None = None) -> None:
    """Display a large center-screen win/loss overlay and useful rematch instructions."""
    name = validate_name(result.human_player)
    color = 'green' if result.is_victory else 'red'
    # 0.25s fade-in, 3s display, 0.75s fade-out (4s total).
    # The title clears itself. Rematch instructions remain available in chat.
    rcon.command(f'title {name} times 5t 60t 15t')
    rcon.command(f'title {name} subtitle {component(result.description, "gold")}')
    rcon.command(f'title {name} title {component(result.headline, color, True)}')
    rcon.command(f'tellraw {name} {component("[Manhunt] " + result.headline + " " + result.description, color, True)}')
    if session_score:
        rcon.command(f'tellraw {name} {component("[SESSION] " + session_score, "yellow")}')
    rcon.command(f'tellraw {name} {component("Play again with /trigger mh_replay", "aqua")}')
    rcon.command(f'tellraw {name} {component("The server stays running. Your world is not reset between rounds.", "gray")}')


def show_match_start(rcon, player: str, human_role: str):
    player = validate_name(player)
    rcon.command(f'title {player} clear')
    rcon.command(f'title {player} times 5t 45t 10t')
    rcon.command(f'title {player} subtitle {component("You are the " + human_role.upper(), "yellow")}')
    rcon.command(f'title {player} title {component("MANHUNT START!", "gold", True)}')
