"""Bounded, physical Carpet obstacle mining. Never edits world with setblock."""
from __future__ import annotations
from dataclasses import dataclass
import math
import time
from .observations import Position
from .terrain import TerrainUnavailable, terrain_type

# Conservative whitelist: no stone, containers, player machinery, or hard ores.
SOFT_BLOCKS = frozenset('''dirt grass_block coarse_dirt rooted_dirt podzol
sand red_sand gravel clay mud moss_block snow_block
netherrack crimson_nylium warped_nylium
'''.split())
WOOD_SUFFIXES = ('_log','_wood','_leaves','_planks')


def mineable(block: str) -> bool:
    return block in SOFT_BLOCKS or block.endswith(WOOD_SUFFIXES)

@dataclass
class MiningOperation:
    block: tuple[int,int,int]
    original: str
    started: float
    timeout: float

class BlockBreaker:
    def __init__(self, rcon, sensor, bot: str='ManhuntBot', clock=time.monotonic):
        self.rcon, self.sensor, self.bot, self.clock = rcon, sensor, bot, clock
        self.operation: MiningOperation | None = None
        self.cooldown_until = 0.0
        self.successes = 0
        self.failures = 0

    def stop(self):
        if self.operation is not None:
            self.rcon.command(f'player {self.bot} stop')
        self.operation = None

    def _candidates(self, bot: Position, goal: Position):
        dx,dz=goal.x-bot.x,goal.z-bot.z
        length=math.hypot(dx,dz)
        if length < .5:
            return []
        y=math.floor(bot.y)
        cells=[]
        for dist in (1.0,1.6,2.2):
            x=math.floor(bot.x+dist*dx/length)
            z=math.floor(bot.z+dist*dz/length)
            for yy in (y,y+1):
                if (x,yy,z) not in cells:
                    cells.append((x,yy,z))
        return cells

    def try_start(self, bot: Position, goal: Position, now: float, *, stop_movement, allowed_blocks=None, exact=None, extra_blocks=()) -> bool:
        if self.operation or now < self.cooldown_until:
            return False
        cells=[exact] if exact is not None else self._candidates(bot,goal)
        if not cells:
            return False
        # Confirm surroundings, support and potential falling liquids above.
        # Inspect the cavity *behind* the proposed opening as well as the
        # block above it. Mining into flowing water/lava or destabilizing a
        # sand/gravel ceiling can turn a valid route into a hazard.
        direction_x=1 if goal.x>bot.x+.5 else -1 if goal.x<bot.x-.5 else 0
        direction_z=1 if goal.z>bot.z+.5 else -1 if goal.z<bot.z-.5 else 0
        coords=list(dict.fromkeys(xyz for x,y,z in cells for xyz in (
            (x,y,z), (x,y+1,z), (x,y+2,z), (x,y-1,z),
            (x+direction_x,y,z+direction_z),
            (x+direction_x,y+1,z+direction_z))))
        blocks=self.sensor.read(coords)
        for x,y,z in cells:
            block=blocks[(x,y,z)]
            if not (mineable(block) or block in extra_blocks) or (allowed_blocks is not None and block not in allowed_blocks):
                continue
            if math.sqrt((x+.5-bot.x)**2+(y+.5-(bot.y+1.6))**2+(z+.5-bot.z)**2)>3.5:
                continue
            surround=[terrain_type(blocks[(x,k,z)]) for k in (y-1,y+1,y+2)]
            exposed = [terrain_type(blocks[(x+direction_x,k,z+direction_z)])
                       for k in (y,y+1)]
            if ('hazard' in surround or 'water' in surround or
                    'hazard' in exposed or 'water' in exposed):
                continue
            if (blocks[(x,y+1,z)] in ('sand','red_sand','gravel') or
                    blocks[(x,y+1,z)].endswith('_concrete_powder')):
                continue
            if terrain_type(blocks[(x,y-1,z)]) == 'air':
                continue
            aim=(x+.5,y+.5,z+.5)
            if exact is not None:
                # Aim just inside an exposed side face rather than at the
                # block centre. A downward ray to the centre of a bottom log
                # can hit the log immediately above it first.
                a=(bot.x,bot.y+1.62,bot.z)
                candidates=[]
                if bot.x < x: candidates.append((x+.03,y+.62,z+.5))
                if bot.x > x+1: candidates.append((x+.97,y+.62,z+.5))
                if bot.z < z: candidates.append((x+.5,y+.62,z+.03))
                if bot.z > z+1: candidates.append((x+.5,y+.62,z+.97))
                candidates.append(aim)
                aim=None
                for b in candidates:
                    n=max(2,math.ceil(math.dist(a,b)/.10))
                    ray=list(dict.fromkeys(tuple(math.floor(a[j]+(b[j]-a[j])*i/n) for j in range(3)) for i in range(1,n)))
                    ray=[p for p in ray if p!=(x,y,z)]
                    observed=self.sensor.read(ray)
                    if all(terrain_type(observed[p])=='air' for p in ray):
                        aim=b
                        break
                if aim is None:
                    continue
            stop_movement()
            self.rcon.command(f'player {self.bot} look at {aim[0]:.2f} {aim[1]:.2f} {aim[2]:.2f}')
            result=self.rcon.command(f'player {self.bot} attack continuous')
            if any(term in result.lower() for term in ('unknown', 'incorrect argument', 'failed')):
                raise TerrainUnavailable('Carpet mining action unavailable: '+result)
            timeout=8.0 if block.endswith(('_log','_wood')) else 4.0
            self.operation=MiningOperation((x,y,z), block, now, timeout)
            print(f'[MINE] Breaking obstructing {block} at {(x,y,z)} (time limit {timeout:g}s).')
            return True
        self.cooldown_until=now+3.
        return False

    def try_exact(self, bot, block, now, *, stop_movement, allowed_blocks, extra_blocks=()):
        x,y,z=block
        return self.try_start(bot,Position(x+.5,float(y),z+.5),now,
                              stop_movement=stop_movement,allowed_blocks=allowed_blocks,exact=block,extra_blocks=extra_blocks)

    def tick(self, now: float) -> bool:
        """True while mining owns controls, False when bot can navigate again."""
        op=self.operation
        if op is None:
            return False
        # Avoid too many block reads; only check after the first 0.7 seconds.
        if now-op.started<0.7:
            return True
        self.sensor.cache.pop(op.block,None)
        current=self.sensor.read([op.block])[op.block]
        if current != op.original:
            self.rcon.command(f'player {self.bot} stop')
            self.operation=None
            self.cooldown_until=now+.5
            self.successes+=1
            print(f'[MINE] Block cleared: {op.original} at {op.block}. Replanning.')
            return False
        if now-op.started>op.timeout:
            self.rcon.command(f'player {self.bot} stop')
            self.operation=None
            self.cooldown_until=now+6.
            self.failures+=1
            print(f'[MINE WARNING] Mining timed out for {op.original}; waiting before retry.')
            return False
        return True
