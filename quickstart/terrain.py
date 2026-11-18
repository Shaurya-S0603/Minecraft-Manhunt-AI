"""v0.4 nearby terrain sensing and collision-aware local steering.

Uses Scarpet's *read-only* ``block()`` in short batches. No world editing,
forced movement, or all-world chunk scans. The server may not support /script;
that condition is reported as TerrainUnavailable rather than treating unknown
terrain as safe. Coordinates passed to Scarpet are derived from live positions.
"""
from __future__ import annotations
from dataclasses import dataclass
from collections import deque
import math
import re
import time
from .observations import Position, validate_name


class TerrainUnavailable(RuntimeError):
    pass


# A conservative list of blocks with no obstructing full-player collision.
# Minecraft 1.21.5 introduced leaf litter, wildflowers, dry grasses, bushes.
# Unknown/modded blocks remain SOLID, never guessed safe.
_PASSABLE = frozenset("""air cave_air void_air short_grass grass tall_grass fern large_fern
 dead_bush dandelion poppy blue_orchid allium azure_bluet red_tulip orange_tulip
 white_tulip pink_tulip oxeye_daisy cornflower lily_of_the_valley
 torch wall_torch redstone_torch redstone_wall_torch soul_torch soul_wall_torch
 brown_mushroom red_mushroom vine ladder glow_lichen nether_sprouts
 crimson_roots warped_roots hanging_roots weeping_vines twisting_vines
 small_dripleaf big_dripleaf_stem sugar_cane snow scaffolding
 leaf_litter wildflowers pink_petals bush firefly_bush short_dry_grass tall_dry_grass
 pale_hanging_moss pale_moss_carpet moss_carpet spore_blossom
 lilac peony rose_bush sunflower torchflower pitcher_plant cactus_flower
 wheat carrots potatoes beetroots nether_wart melon_stem pumpkin_stem
 attached_melon_stem attached_pumpkin_stem""".split())
# Carpets sit slightly above their supporting block, but shouldn't make
# walking impossible. They are NOT safe ground by themselves.
_WATER = frozenset('water bubble_column seagrass tall_seagrass kelp kelp_plant'.split())
_HAZARD = frozenset("""lava fire soul_fire magma_block campfire soul_campfire
 cactus sweet_berry_bush wither_rose powder_snow pointed_dripstone""".split())
# A player's actual foot Y may be below the next integer while standing on
# these valid supporting blocks. Never snap upward through arbitrary solids.
LOWERED_SUPPORTS = frozenset('dirt_path farmland mud soul_sand'.split())
_ID = re.compile(r'^(?:minecraft:)?([a-z0-9_./-]+)(?:\[[^\]]*\])?$')
_SENTINEL_START = 'MHNAV4:'
_SENTINEL_END = ':ENDMH4'


def normalize_block(value: str) -> str:
    value = value.strip().strip("'\" ")
    match = _ID.fullmatch(value)
    if not match:
        raise TerrainUnavailable(f'Unexpected Scarpet block identifier: {value[:90]!r}')
    return match.group(1)


CLIMBABLE = frozenset(('vine', 'ladder', 'weeping_vines', 'twisting_vines', 'scaffolding'))


def climbable(block: str) -> bool:
    return normalize_block(block) in CLIMBABLE


def terrain_type(block: str) -> str:
    # The live sensor returns simple names, but handle namespaced/state names
    # as well so a future bridge needn't use exactly the Scarpet string format.
    if ':' in block or '[' in block:
        block = normalize_block(block)
    if block in _HAZARD:
        return 'hazard'
    if block in _WATER:
        return 'water'
    if (block in _PASSABLE or block.endswith('_flower')
            or block.endswith('_sapling') or block.endswith('_carpet')):
        return 'air'
    return 'solid'


class TerrainSensor:
    """Read a small number of nearby world blocks via a single Carpet command.

    Scarpet's `print()` is routed to the RCON command source; delimiters let
    us reject unexpected server feedback. Caches short-lived block observations
    to avoid excessive server queries. This protocol needs a live verification.
    """
    def __init__(self, rcon, ttl: float = 3.0, max_batch: int = 24, clock=time.monotonic, at_entity: str | None = None):
        self.rcon = rcon
        self.at_entity = validate_name(at_entity) if at_entity else None
        self.ttl = ttl
        self.max_batch = max(1, min(32, max_batch))
        self.clock = clock
        self.cache: dict[tuple[int,int,int], tuple[float,str]] = {}
        self.active: bool | None = None

    def read(self, coords: list[tuple[int,int,int]]) -> dict[tuple[int,int,int], str]:
        now = self.clock()
        result = {}
        missing = []
        for xyz in dict.fromkeys(coords):
            cached = self.cache.get(xyz)
            if cached and now - cached[0] < self.ttl:
                result[xyz] = cached[1]
            else:
                missing.append(xyz)
        for start in range(0, len(missing), self.max_batch):
            batch = missing[start:start+self.max_batch]
            expressions = ','.join(f'str(block({x},{y},{z}))' for x,y,z in batch)
            command = ("script run print('" + _SENTINEL_START + "' + join('|',[" +
                       expressions + "]) + '" + _SENTINEL_END + "')")
            if self.at_entity:
                command = f'execute at {validate_name(self.at_entity)} run {command}'
            response = self.rcon.command(command)
            if not isinstance(response, str):
                response = str(response)
            a = response.find(_SENTINEL_START)
            b = response.find(_SENTINEL_END, a + len(_SENTINEL_START)) if a >= 0 else -1
            if b < 0:
                self.active = False
                raise TerrainUnavailable('Scarpet /script block observation unavailable: ' + response[:180])
            raw = response[a+len(_SENTINEL_START):b].split('|')
            if len(raw) != len(batch):
                self.active = False
                raise TerrainUnavailable('Scarpet returned an unexpected number of blocks')
            for xyz,value in zip(batch, raw):
                block = normalize_block(value)
                result[xyz] = block
                self.cache[xyz] = (now,block)
        self.active = True
        # Avoid retaining stale terrain forever.
        if len(self.cache) > 1600:
            self.cache = {k:v for k,v in self.cache.items() if now-v[0] <= self.ttl}
        return result


@dataclass(frozen=True)
class StepChoice:
    destination: Position
    jump: bool = False
    swimming: bool = False
    vertical_change: int = 0
    score: float = 0.0


class LocalNavigator:
    """Five-direction lookahead: steer around solid blocks and dangerous drops.

    It is intentionally NOT global A*. Small winding mazes, complicated cliffs,
    doors, and underground routes will need a future server-side nav graph.
    """
    def __init__(self, sensor: TerrainSensor, clock=time.monotonic):
        self.sensor = sensor
        self.clock = clock
        self.last_heading: float | None = None
        self.blocked_until: dict[tuple[int,int],float] = {}
        self.visited = deque(maxlen=16)
        self.last_choice: StepChoice | None = None

    def clear(self):
        self.last_heading = None
        self.blocked_until.clear()
        self.visited.clear()
        self.last_choice = None

    def mark_stuck(self, pos: Position):
        """Penalize the previous waypoint without modifying terrain."""
        if self.last_choice:
            p=self.last_choice.destination
            self.blocked_until[(math.floor(p.x),math.floor(p.z))] = self.clock()+14
        self.last_heading = None
        self.visited.append((math.floor(pos.x), math.floor(pos.z)))

    @staticmethod
    def _landing(blocks: dict, x: int, y: int, z: int):
        """Return (delta Y, jump, swim, penalty), or None for unsafe terrain."""
        def kind(dy):
            return terrain_type(blocks[(x,y+dy,z)])
        # Prefer flat routes, then one-block climbs, then gentle drops.
        for delta,penalty in ((0,0.), (1,0.8), (-1,0.65), (-2,1.8)):
            feet, head, ground = kind(delta),kind(delta+1),kind(delta-1)
            if 'hazard' in (feet,head,ground):
                continue
            if feet == 'solid' or head == 'solid':
                continue
            if ground == 'air' and feet != 'water':
                continue  # no support / deep pit
            # No jumping into ceilings. Water travel is allowed but expensive.
            swim = feet == 'water' or ground == 'water'
            return delta,delta > 0,swim,penalty+(1.8 if swim else 0.)
        return None

    def choose(self, origin: Position, target: Position, *, avoid_water: bool=False) -> StepChoice | None:
        vx,vz = target.x-origin.x,target.z-origin.z
        length=math.hypot(vx,vz)
        if length < 0.5:
            return StepChoice(target, score=100)
        base=math.atan2(vz,vx)
        # Sidestepping is allowed to move temporarily away from the goal.
        angles=(0, math.radians(45), -math.radians(45),
                math.radians(90), -math.radians(90),
                math.radians(135), -math.radians(135))
        y=math.floor(origin.y)
        columns=[]
        headings=[]
        for turn in angles:
            angle=base+turn
            # Probe a near cell so that moving a long distance can't skip a tree.
            near=(math.floor(origin.x+1.1*math.cos(angle)),
                  math.floor(origin.z+1.1*math.sin(angle)))
            far=(math.floor(origin.x+2.4*math.cos(angle)),
                 math.floor(origin.z+2.4*math.sin(angle)))
            headings.append((angle,near,far,turn))
            columns.extend((near,far))
        columns=list(dict.fromkeys(columns))
        coords=[(x,y+dy,z) for x,z in columns for dy in (-3,-2,-1,0,1,2,3)]
        blocks=self.sensor.read(coords)
        now=self.clock()
        best=None
        for angle,near,far,turn in headings:
            first=self._landing(blocks,*((near[0],y,near[1])))
            last=self._landing(blocks,*((far[0],y,far[1])))
            if first is None or last is None:
                continue
            delta,jump,swim,cost=last
            # A 2-block rise between sampled columns isn't a valid single jump.
            if abs(last[0]-first[0]) > 1:
                continue
            jump = jump or first[1]
            swim = swim or first[2]
            if avoid_water and swim:
                cost += 2.5
            blocked = self.blocked_until.get(far,0)>now
            if blocked:
                continue
            dest=Position(far[0]+0.5, y+delta, far[1]+0.5)
            improvement=length-math.hypot(target.x-dest.x,target.z-dest.z)
            turn_penalty=abs(turn)*0.85
            heading_penalty=(abs(math.atan2(math.sin(angle-self.last_heading),
                                            math.cos(angle-self.last_heading)))*0.22
                             if self.last_heading is not None else 0)
            visited_penalty=1.5 if far in self.visited else 0.
            score=improvement*3.2-cost-turn_penalty-heading_penalty-visited_penalty
            candidate=StepChoice(dest,jump,swim,delta,score)
            if best is None or candidate.score > best.score:
                best=candidate
                best_heading=angle
                best_cell=far
        if best is not None:
            self.last_heading=best_heading
            self.visited.append(best_cell)
            self.last_choice=best
        return best
