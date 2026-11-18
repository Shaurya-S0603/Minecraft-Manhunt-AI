"""Bounded 3D A* on read-only, server-observed Minecraft blocks.

This is a receding-horizon planner: it plans short, traversable routes and
repeats as new terrain is observed. It does not mine, bridge or cross portals.
"""
from __future__ import annotations

from dataclasses import dataclass
import heapq
import itertools
import math
import time

from .observations import Position
from .terrain import TerrainSensor, TerrainUnavailable, terrain_type, LOWERED_SUPPORTS, climbable

Node = tuple[int, int, int]


class AirborneTransition(TerrainUnavailable):
    """Observed unsupported air: physical gravity must finish the jump/fall.

    Distinct from missing Scarpet sensor data or collision with hazardous or
    solid blocks. Do not apply the multi-second sensor-failure cooldown.
    """


@dataclass(frozen=True)
class PathStep:
    destination: Position
    jump: bool = False
    swimming: bool = False
    climb: bool = False
    sprint_jump: bool = False


@dataclass(frozen=True)
class RoutePlan:
    steps: tuple[PathStep, ...]
    reached_goal: bool
    expanded: int
    observed_blocks: int
    detour: bool = False  # Verified reachable sidestep, not a path to the opponent.


class BoundedAStar:
    """Conservative, small-window 3D walking/swimming planner.

    One block per horizontal grid step, +/-1 block ascent and up to 2 blocks
    descent. Unknown world cells are not treated as safe. A path may stop at
    the edge of the search window, where the next window is planned.
    """

    def __init__(self, sensor: TerrainSensor, radius: int = 6,
                 rise: int = 3, fall: int = 3, max_expanded: int = 350,
                 max_scan_blocks: int = 2000, clock=time.monotonic, max_gap: int = 1):
        if not 3 <= radius <= 10 or not 1 <= rise <= 5 or not 1 <= fall <= 5:
            raise ValueError('Unsupported search window')
        self.sensor = sensor
        self.radius, self.rise, self.fall = radius, rise, fall
        self.max_expanded = max_expanded
        self.max_scan_blocks = max_scan_blocks
        self.max_gap = max(1,min(int(max_gap),3))
        self.gap_risk: dict[int,float] = {}
        self.edge_penalty = None
        self.clock = clock
        self.blocked: dict[Node, float] = {}

    def clear(self):
        self.blocked.clear()

    def penalize(self, destination: Position, seconds: float = 14):
        p = (math.floor(destination.x), math.floor(destination.y), math.floor(destination.z))
        self.blocked[p] = self.clock() + seconds

    @staticmethod
    def _kind(blocks, x, y, z):
        """Return a block category, or UNKNOWN outside the sampled window.

        A* runs in a bounded grid. Targets near the boundary (including their
        overlapping hitbox neighbours) are allowed to be outside that grid.
        They must be treated as *unobserved*, not indexed blindly or assumed
        to be air. This also covers the vertical clearance layers.
        """
        observed = blocks.get((x,y,z))
        return terrain_type(observed) if observed is not None else 'unknown'

    def _passable(self, blocks, pos: Node):
        x,y,z = pos
        feet = self._kind(blocks,x,y,z)
        head = self._kind(blocks,x,y+1,z)
        ground = self._kind(blocks,x,y-1,z)
        if 'unknown' in (feet,head,ground):
            return None  # Never route through an unobserved collision cell.
        if 'hazard' in (feet,head,ground):
            return None
        if feet == 'solid' or head == 'solid':
            return None
        if (ground == 'air' and feet != 'water' and head != 'water'
                and not any(climbable(blocks[(x,k,z)]) for k in (y-1,y,y+1)
                            if (x,k,z) in blocks)):
            return None
        swimming = 'water' in (feet,head,ground)
        return swimming

    def _edge(self, blocks, src: Node, dst: Node):
        x,y,z = src
        nx,ny,nz = dst
        dy = ny-y
        if dy > 1 or dy < -2:
            return None
        swim = self._passable(blocks,dst)
        if swim is None:
            return None
        # Vertical movements are legitimate only in a water column or
        # against climbable blocks. Never allow flying up ordinary air.
        if nx == x and nz == z:
            if abs(dy) != 1:
                return None
            in_water = (self._kind(blocks,x,y,z)=='water' or
                        self._kind(blocks,x,y+1,z)=='water')
            destination_water = (self._kind(blocks,nx,ny,nz)=='water' or
                                 self._kind(blocks,nx,ny+1,nz)=='water')
            on_ladder = any(climbable(blocks[(x,k,z)])
                            for k in (y,y+1,ny,ny+1) if (x,k,z) in blocks)
            if not ((in_water and (destination_water or dy==1)) or on_ladder):
                return None
            if dy==1 and self._kind(blocks,x,y+2,z) in ('solid','hazard'):
                return None
            return swim or in_water, dy == 1, on_ladder
        # Rising one block needs space above the current player's head.
        if dy == 1 and self._kind(blocks,x,y+2,z) not in ('air','water'):
            return None
        # A direct diagonal moves the full player hitbox through a corner.
        # Require both cardinal corridors to be clear, not merely one L route.
        if x != nx and z != nz:
            for ox,oz in ((nx,z),(x,nz)):
                if (self._passable(blocks,(ox,y,oz)) is None
                        or self._passable(blocks,(ox,ny,oz)) is None):
                    return None
        return (swim, dy == 1, False)

    @staticmethod
    def _overlapping_cells(position: Position) -> list[Node]:
        """Columns touched by the player's ~0.6-block wide collision box.

        At the edge of a leaf canopy, the player's *centre* may be over air
        while their physical hitbox still rests on an adjacent leaf block.
        """
        x,y,z=map(math.floor,(position.x,position.y,position.z))
        xs=[x]
        zs=[z]
        if position.x-x < .30:
            xs.append(x-1)
        elif position.x-x > .70:
            xs.append(x+1)
        if position.z-z < .30:
            zs.append(z-1)
        elif position.z-z > .70:
            zs.append(z+1)
        return [(a,y,b) for a in xs for b in zs if (a,b)!=(x,z)]

    @staticmethod
    def _unsupported_air(blocks, pos: Node) -> bool:
        """True for confirmed free air, not solid clipping, water or ladders.

        A jump is allowed to be in progress while the character is in air,
        but an unsupported air cell must not become an A* walking origin.
        """
        x,y,z = pos
        if not all(BoundedAStar._kind(blocks,x,k,z) == 'air'
                   for k in (y-1,y,y+1)):
            return False  # Missing samples are not proof of safe freefall.
        return not any(climbable(blocks[(x,k,z)]) for k in (y-1,y,y+1))

    def is_airborne(self, origin: Position) -> bool:
        """Cheap, read-only start-state check before controlling physical motion."""
        x,y,z = map(math.floor,(origin.x,origin.y,origin.z))
        overlaps=self._overlapping_cells(origin)
        coords=[(a,k,c) for a,_,c in [(x,y,z),*overlaps] for k in (y-1,y,y+1)]
        blocks=self.sensor.read(coords)
        if not self._unsupported_air(blocks,(x,y,z)):
            return False
        # A real Minecraft collision box may rest on the adjacent tree leaf
        # even when its centre is on the empty side of a block boundary.
        return not any(self._passable(blocks,cell) is not None
                       for cell in overlaps)

    def _snap_to_walkable_cell(self, blocks, position: Position) -> Node:
        """Account for real feet Y on dirt paths and other lowered surfaces.

        At Y=63.9375 on a path block at 63, floor(Y) points INTO the
        ground, while the actual walking space is cell 64.
        """
        x, y, z = math.floor(position.x), math.floor(position.y), math.floor(position.z)
        original = (x, y, z)
        if self._passable(blocks, original) is not None:
            return original
        fraction = position.y - y
        if fraction >= 0.70 and blocks.get((x, y, z)) in LOWERED_SUPPORTS:
            raised = (x, y + 1, z)
            if self._passable(blocks, raised) is not None:
                return raised
        # If physical feet overlap an adjacent tree leaf/solid ledge, adopt
        # that supported column instead of treating a still-grounded player
        # as floating. This never invents support: blocks were observed.
        candidates=[cell for cell in self._overlapping_cells(position)
                    if self._passable(blocks,cell) is not None]
        if candidates:
            return min(candidates,key=lambda c:
                       (position.x-(c[0]+.5))**2+(position.z-(c[2]+.5))**2)
        return original

    def _grid(self, start: Node):
        sx,sy,sz = start
        # Square window makes axis-aligned and diagonal directions symmetrical.
        # Include supporting block below, two head-clearance layers above.
        coords = [(x,y,z) for x in range(sx-self.radius,sx+self.radius+1)
                  for z in range(sz-self.radius,sz+self.radius+1)
                  for y in range(sy-self.fall-1,sy+self.rise+3)]
        if len(coords) > self.max_scan_blocks:
            raise TerrainUnavailable('3D route scan exceeds configured block budget')
        return self.sensor.read(coords), len(coords)

    @staticmethod
    def _h(node: Node, goal: Node) -> float:
        return math.hypot(node[0]-goal[0],node[2]-goal[2]) + 0.7*abs(node[1]-goal[1])

    def _best_detour(self, visited: set[Node], start: Node, target: Node,
                     dist: dict[Node, float], exclude: frozenset[Node]) -> Node | None:
        """Choose a *reachable* alternate endpoint after local goal-gradient failure.

        A* can explore a wall's side corridor yet return no path because no
        observed node is strictly closer to the faraway opponent. This bounded
        sidestep is built solely from the already-verified A* predecessor graph.
        It never infers safe blocks outside the sensor window.
        """
        dx, dz = target[0]-start[0], target[2]-start[2]
        length = max(1.0, math.hypot(dx,dz))
        winner = None
        highest = float('-inf')
        for node in visited:
            if node == start or node not in dist:
                continue
            nx, nz = node[0]-start[0], node[2]-start[2]
            displacement = math.hypot(nx,nz)
            if not (2.0 <= displacement <= self.radius + .1):
                continue
            # Never attempt the same failed sidestep or a near-identical one.
            if any(math.hypot(node[0]-e[0],node[2]-e[2]) < 2.0 and
                   abs(node[1]-e[1]) <= 1 for e in exclude):
                continue
            sideways = abs(dx*nz - dz*nx) / length
            forward = (dx*nx + dz*nz) / length
            # Tangential exploration is necessary to round a long wall.
            # Path cost discourages risky jumps and needless vertical travel.
            score = (1.25*sideways + .35*forward + .20*displacement
                     - .22*dist[node] - .30*abs(node[1]-start[1]))
            if score > highest:
                winner, highest = node, score
        return winner

    def _best_escape(self, blocks, visited, start, threat, dist, exclude):
        """Choose an observed reachable endpoint, not a fabricated escape goal.

        Prefer meaningful separation and dry ground; lateral movement is
        allowed when terrain blocks a direct retreat. Use only A* predecessors.
        """
        old=math.hypot(start[0]+.5-threat.x,start[2]+.5-threat.z)
        choices=[]
        for node in sorted(visited):
            if node == start or node not in dist:
                continue
            x,y,z=node
            displacement=math.hypot(x-start[0],z-start[2])
            if displacement<2: continue
            if any(math.hypot(x-e[0],z-e[2])<2 and abs(y-e[1])<=1 for e in exclude):
                continue
            gain=math.hypot(x+.5-threat.x,z+.5-threat.z)-old
            wet=self._passable(blocks,node) is True
            score=2.0*gain+.35*displacement-.16*dist[node]-(1.4 if wet else 0)-.15*abs(y-start[1])
            choices.append((score,node))
        return max(choices)[1] if choices else None

    def plan(self, origin: Position, goal: Position, *, avoid_water: bool = False,
             allow_detour: bool = False,
             detour_exclude: frozenset[Node] = frozenset(),
             escape_from: Position | None = None) -> RoutePlan:
        observed_start = (math.floor(origin.x),math.floor(origin.y),math.floor(origin.z))
        target = (math.floor(goal.x),math.floor(goal.y),math.floor(goal.z))
        blocks, size = self._grid(observed_start)
        start = self._snap_to_walkable_cell(blocks, origin)
        # Only query target cells if inside the scanned terrain window.
        if (abs(target[0]-observed_start[0]) <= self.radius
                and abs(target[2]-observed_start[2]) <= self.radius
                and observed_start[1]-self.fall <= target[1] <= observed_start[1]+self.rise):
            target = self._snap_to_walkable_cell(blocks, goal)
        if start == target:
            return RoutePlan((),True,0,size)
        # Do not force a path if the bot is inside an observed solid block.
        # The caller may stop and re-run safe-spawn recovery.
        if self._passable(blocks,start) is None:
            if self._unsupported_air(blocks,start):
                raise AirborneTransition('Bot is airborne; waiting for a verified landing')
            raise TerrainUnavailable('Bot intersects an unsafe or unwalkable block; stopping navigation')
        self.blocked = {p:t for p,t in self.blocked.items() if t > self.clock()}
        frontier = []
        counter = itertools.count()
        heapq.heappush(frontier,(self._h(start,target),next(counter),start))
        dist = {start: 0.0}
        prev: dict[Node,tuple[Node,bool,bool,bool,bool]] = {}
        visited = set()
        best = start
        best_score = self._h(start,target)
        found = False
        sx,sy,sz=start
        while frontier and len(visited)<self.max_expanded:
            _,_,node=heapq.heappop(frontier)
            if node in visited:
                continue
            visited.add(node)
            # For goals in another window, retain best safe point on frontier.
            closeness=self._h(node,target)
            candidate_score=closeness + 0.05*dist[node]
            if candidate_score < best_score-1e-8:
                best,best_score=node,candidate_score
            if node==target:
                found=True
                best=node
                break
            x,y,z=node
            # Include true vertical movement for water and climbables, and
            # optional two-cell straight sprint jumps across one empty gap.
            for dx,dz in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1),
                          (0,0),*(offset for d in range(2,self.max_gap+2)
                                  for offset in ((d,0),(-d,0),(0,d),(0,-d)))):
                nx,nz=x+dx,z+dz
                if abs(nx-sx)>self.radius or abs(nz-sz)>self.radius:
                    continue
                long_jump = abs(dx)+abs(dz)>=2 and (dx==0 or dz==0)
                for dy in ((0,) if long_jump else (-1,1) if dx==0 and dz==0 else (0,1,-1,-2)):
                    ny=y+dy
                    if ny < sy-self.fall or ny > sy+self.rise:
                        continue
                    nxt=(nx,ny,nz)
                    if nxt in self.blocked:
                        continue
                    if long_jump:
                        # Long jump: every intermediate cell must be empty at
                        # support, feet, head and overhead levels, not merely
                        # the middle block. Longer gaps require real training.
                        cells=abs(dx)+abs(dz)
                        intermediates=[(x+dx*i//cells,y,z+dz*i//cells)
                                       for i in range(1,cells)]
                        src_ground=self._kind(blocks,x,y-1,z)
                        landing=self._passable(blocks,nxt)
                        if (src_ground in ('water','air','hazard','unknown')
                                or landing is not False
                                or self._kind(blocks,nx,ny+2,nz)!='air'
                                or any(self._kind(blocks,mx,level,mz)!='air'
                                       for mx,my,mz in intermediates
                                       for level in (y-1,y,y+1,y+2))):
                            continue
                        swim,jump,climb=False,True,False
                    else:
                        edge=self._edge(blocks,node,nxt)
                        if edge is None:
                            continue
                        swim,jump,climb=edge
                    # Climbing and sprint-jump edges need deliberate input and
                    # are expensive enough to prefer ordinary walking routes.
                    weight=(math.hypot(dx,dz) + 0.8*max(dy,0) + 0.55*max(-dy,0)
                            + (2.5 if swim and avoid_water else 1.1 if swim else 0)
                            + (1.8 if climb else 0)
                            + ((2.0+2.5*self.gap_risk.get(abs(dx)+abs(dz)-1,1.0))
                               if long_jump else 0))
                    # Tree leaves are solid collision blocks. Standing on top
                    # is possible, but normal Carpet movement/jumping on
                    # irregular canopies is fragile. Prefer a ground detour.
                    support=blocks.get((nx,ny-1,nz))
                    if support is None:
                        continue  # An unobserved landing can never be preferred.
                    if support.endswith('_leaves') or support.endswith('_wart_block'):
                        weight += 3.5
                    if self.edge_penalty is not None:
                        weight += self.edge_penalty(node, nxt)
                    nd=dist[node]+weight
                    if nd < dist.get(nxt,float('inf')):
                        dist[nxt]=nd
                        prev[nxt]=(node,jump,swim,climb,long_jump)
                        heapq.heappush(frontier,(nd + self._h(nxt,target),next(counter),nxt))
        used_detour = False
        if best == start and allow_detour:
            candidate = (self._best_escape(blocks,visited,start,escape_from,dist,detour_exclude)
                         if escape_from is not None else self._best_detour(visited,start,target,dist,detour_exclude))
            if candidate is not None:
                best = candidate
                used_detour = True
        if best==start:
            return RoutePlan((),False,len(visited),size)
        rev=[]
        cursor=best
        while cursor!=start:
            parent,jump,swim,climb,long_jump=prev[cursor]
            rev.append(PathStep(Position(cursor[0]+0.5,cursor[1],cursor[2]+0.5),jump,swim,climb,long_jump))
            cursor=parent
        rev.reverse()
        return RoutePlan(tuple(rev),found,len(visited),size,detour=used_detour)
