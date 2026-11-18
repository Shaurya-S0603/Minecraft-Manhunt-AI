"""Bounded, obstacle-aware search for breathable water surface cells.

This is an independent emergency target finder; ordinary 3D A* still
handles short water routes. Read-only Scarpet observations, no world edits.
"""
from __future__ import annotations
from collections import deque
import math
from .observations import Position
from .terrain import terrain_type


class SurfacePlanner:
    def __init__(self, sensor, horizontal_radius: int = 3, vertical_rise: int = 7):
        self.sensor = sensor
        self.radius = horizontal_radius
        self.rise = vertical_rise

    def find_air(self, position: Position) -> Position | None:
        x,y,z = map(math.floor, (position.x,position.y,position.z))
        # First try the simple case: a continuous open column directly above
        # the bot. This typically requires one Scarpet read rather than a
        # 500+ block underwater search.
        vertical=[(x,b,z) for b in range(y-1,y+self.rise+3)]
        column=self.sensor.read(vertical)
        for b in range(y,y+self.rise+1):
            if (all(terrain_type(column[(x,k,z)]) == 'water' for k in range(y,b+1))
                    and terrain_type(column[(x,b+1,z)]) == 'air'
                    and terrain_type(column[(x,b+2,z)]) == 'air'):
                return Position(x+.5,b+1.0,z+.5)
        # If covered by a roof, search a small water-connected neighbourhood.
        # Cached observations from the column can be reused.
        coords = [(a,b,c) for a in range(x-self.radius,x+self.radius+1)
                  for c in range(z-self.radius,z+self.radius+1)
                  for b in range(y-1,y+self.rise+3)]
        blocks = self.sensor.read(coords)
        def kind(node):
            return terrain_type(blocks[node])
        start = (x,y,z)
        if kind(start) != 'water':
            # Feet may be in a waterlogged partial cell; ascend only if the
            # immediately lower cell is water and the body is submerged.
            lower = (x,y-1,z)
            if kind(lower) != 'water':
                return None
            start = lower
        queue=deque([start]); seen={start}
        while queue:
            a,b,c=queue.popleft()
            # Air immediately over water is breathable if unobstructed.
            if kind((a,b+1,c))=='air' and kind((a,b+2,c))=='air':
                return Position(a+.5,b+1.0,c+.5)
            for next_node in ((a+1,b,c),(a-1,b,c),(a,b,c+1),(a,b,c-1),
                              (a,b+1,c),(a,b-1,c)):
                na,nb,nc=next_node
                if (next_node in seen or abs(na-x)>self.radius or
                    abs(nc-z)>self.radius or nb<y-1 or nb>y+self.rise):
                    continue
                if kind(next_node)!='water':
                    continue
                if kind((na,nb+1,nc)) in ('solid','hazard'):
                    continue
                seen.add(next_node)
                queue.append(next_node)
        return None

    def ascend_waypoint(self, position: Position) -> Position | None:
        """Verified vertical staging step when water extends beyond the scan."""
        x,y,z=map(math.floor,(position.x,position.y,position.z))
        height=min(3,self.rise)
        coords=[(x,y+i,z) for i in range(height+2)]
        blocks=self.sensor.read(coords)
        if any(terrain_type(blocks[(x,y+i,z)]) != 'water' for i in range(height+1)):
            return None
        if terrain_type(blocks[(x,y+height+1,z)]) in ('solid','hazard'):
            return None
        return Position(x+.5,y+height,z+.5)
