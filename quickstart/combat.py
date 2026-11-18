"""Conservative line-of-sight check before issuing fake-player in-game hits."""
from __future__ import annotations
import math
from .terrain import terrain_type
from .observations import Position


def attack_line_clear(sensor, attacker: Position, victim: Position) -> bool:
    # Attack from near eye height toward the opponent torso. Discretized
    # ray samples prevent repeated hitting of walls through short proximity.
    ax,ay,az=attacker.x,attacker.y+1.5,attacker.z
    bx,by,bz=victim.x,victim.y+1.0,victim.z
    length=math.sqrt((bx-ax)**2+(by-ay)**2+(bz-az)**2)
    if length < .01:
        return True
    coords=[]
    count=max(1,math.ceil(length/.22))
    for index in range(1,count):
        t=index/count
        block=(math.floor(ax+(bx-ax)*t),math.floor(ay+(by-ay)*t),math.floor(az+(bz-az)*t))
        if block not in coords:
            coords.append(block)
    if not coords:
        return True
    blocks=sensor.read(coords)
    return all(terrain_type(blocks[c]) != 'solid' and terrain_type(blocks[c]) != 'hazard' for c in coords)
