"""Simple live position observations using Minecraft's administrative commands."""
from __future__ import annotations
import re
import math
from dataclasses import dataclass

PLAYER_NAME = re.compile(r'^[A-Za-z0-9_]{3,16}$')
# SNBT double coordinates may be written as 6.65E-4d, -2.1e+2d or .5f.
# Keep the exponent and strip the optional numeric type suffix only.
_NUMBER = r'[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?'
VECTOR = re.compile(r'\[\s*(' + _NUMBER + r')[dDfF]?\s*,\s*('
                    + _NUMBER + r')[dDfF]?\s*,\s*('
                    + _NUMBER + r')[dDfF]?\s*\]')


def validate_name(name: str) -> str:
    if not PLAYER_NAME.fullmatch(name):
        raise ValueError("Minecraft player name must contain 3–16 letters, digits or underscores")
    return name


def parse_position(result: str) -> tuple[float, float, float]:
    match = VECTOR.search(result)
    if match is None:
        raise ValueError(f"No position in Minecraft response: {result[:120]}")
    position = tuple(float(value) for value in match.groups())
    if not all(math.isfinite(value) for value in position):
        raise ValueError('Non-finite Minecraft coordinate is unsafe')
    return position


def parse_player_list(result: str) -> list[str]:
    # Vanilla response, e.g. There are 2 of a max of 20 players online: Alex, ManhuntBot
    if ':' not in result:
        return []
    names = result.split(':', 1)[1].strip()
    return [n.strip() for n in names.split(',') if PLAYER_NAME.fullmatch(n.strip())]


@dataclass(frozen=True)
class Position:
    x: float
    y: float
    z: float

    @classmethod
    def from_tuple(cls, p: tuple[float, float, float]):
        return cls(*p)

    def distance(self, other: 'Position') -> float:
        return ((self.x - other.x)**2 + (self.y - other.y)**2 + (self.z - other.z)**2)**0.5


class Observer:
    def __init__(self, rcon):
        self.rcon = rcon

    def position(self, name: str) -> Position:
        validate_name(name)
        response = self.rcon.command(f'data get entity {name} Pos')
        try:
            return Position.from_tuple(parse_position(response))
        except ValueError:
            # Version-specific command restrictions may reject direct player-NBT reads.
            # The marker fallback works from a server command context for local testing.
            tag = f'manhunt_probe_{name.lower()}'
            self.rcon.command(f'execute at {name} run summon minecraft:marker ~ ~ ~ {{Tags:["{tag}"]}}')
            try:
                response = self.rcon.command(
                    f'execute at {name} run data get entity '
                    f'@e[type=minecraft:marker,tag={tag},sort=nearest,limit=1,distance=..2] Pos'
                )
                return Position.from_tuple(parse_position(response))
            finally:
                self.rcon.command(
                    f'execute at {name} run kill '
                    f'@e[type=minecraft:marker,tag={tag},sort=nearest,limit=1,distance=..2]'
                )
