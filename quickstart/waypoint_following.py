"""Collision-conscious waypoint arrival rules for Carpet physical walking.

Never consider a path corner reached when the bot is over a block away;
that would send the bot diagonally across adjacent tree leaves or a wall.
The overshoot case is restricted to the same narrow path corridor.
"""
from __future__ import annotations
import math
from .observations import Position


def reached_waypoint(actual: Position, destination: Position,
                     previous: Position | None = None,
                     radius: float = 0.52) -> bool:
    """Check arrival at the *centre* of a walking waypoint.

    A small along-segment overshoot is allowed for normal tick-based motion;
    moving diagonally away from the planned segment never counts as arrival.
    """
    if abs(actual.y - destination.y) > 0.62:
        return False
    horizontal = math.hypot(actual.x-destination.x, actual.z-destination.z)
    if horizontal <= radius:
        return True
    if previous is None:
        return False
    dx, dz = destination.x-previous.x, destination.z-previous.z
    length = math.hypot(dx, dz)
    if length < 0.25:
        return False
    px, pz = actual.x-previous.x, actual.z-previous.z
    along = (px*dx + pz*dz) / length
    side = abs(px*dz-pz*dx) / length
    # Require reaching/passing the waypoint *along the safe corridor*.
    return length <= along <= length + 0.8 and side <= 0.30
