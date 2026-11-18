"""Find a natural, open, dry spawn for a Carpet fake player.

Never edit terrain, guess a safe coordinate, or spawn on the human player.
If there is no verified location, fail closed with an actionable message.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

from .observations import Position
from .terrain import TerrainSensor, TerrainUnavailable, terrain_type, LOWERED_SUPPORTS

# A strict whitelist avoids slabs, fences, leaves, unstable vegetation and
# other deceptively solid blocks that are unsuitable spawn supports.
SAFE_GROUND = frozenset('''grass_block dirt coarse_dirt rooted_dirt podzol mycelium
 stone cobblestone mossy_cobblestone deepslate cobbled_deepslate tuff
 granite diorite andesite sandstone red_sandstone sand red_sand gravel
 clay mud packed_mud mud_bricks moss_block bedrock blackstone netherrack
 basalt smooth_basalt calcite dirt_path farmland snow_block terracotta soul_sand'''.split())


@dataclass(frozen=True)
class SpawnSpot:
    position: Position
    clearance: int
    distance: float


class SafeSpawnFinder:
    def __init__(self, sensor: TerrainSensor, radius: int = 12, min_distance: float = 4):
        if not 5 <= radius <= 16:
            raise ValueError('Spawn search radius must be 5..16')
        self.sensor=sensor
        self.radius=radius
        self.min_distance=min_distance

    @staticmethod
    def _valid(blocks, x, y, z):
        if blocks[(x,y-1,z)] not in SAFE_GROUND:
            return False
        return all(terrain_type(blocks[(x,y+dy,z)]) == 'air' for dy in (0,1,2))

    def find(self, near: Position) -> SpawnSpot:
        ox,oy,oz=math.floor(near.x),math.floor(near.y),math.floor(near.z)
        # Favor a position diagonally offset from the human, but search in
        # every direction; no reliance on the chunk spawn-point heightmap.
        offsets=[(dx,dz) for dx in range(-self.radius,self.radius+1)
                 for dz in range(-self.radius,self.radius+1)
                 if self.min_distance <= math.hypot(dx,dz) <= self.radius]
        offsets.sort(key=lambda p:(math.hypot(p[0]-5,p[1]-5),math.hypot(*p)))
        # Scan centers first, then inspect 3x3 openness only for promising spots.
        # Bounded to avoid stalling initial match setup or loading distant chunks.
        offsets=offsets[:200]
        centers=[(ox+dx,oy+dy,oz+dz) for dx,dz in offsets for dy in (0,1,-1,2,-2,3,-3)]
        coarse=[(x,y+d,z) for x,y,z in centers for d in (-1,0,1,2)]
        blocks=self.sensor.read(coarse)
        candidates=[]
        for x,y,z in centers:
            if not self._valid(blocks,x,y,z):
                continue
            d=math.hypot(x+0.5-near.x,z+0.5-near.z)
            candidates.append((d+0.7*abs(y-near.y),x,y,z))
        candidates.sort()
        for _,x,y,z in candidates[:48]:
            vicinity=[(x+dx,y+dy,z+dz) for dx in (-1,0,1)
                      for dz in (-1,0,1) for dy in (-1,0,1,2)]
            observed=self.sensor.read(vicinity)
            if not all(terrain_type(observed[(x+dx,y+height,z+dz)])=='air'
                       for dx in (-1,0,1) for dz in (-1,0,1) for height in (0,1,2)):
                continue
            solid_neighbors=sum(observed[(x+dx,y-1,z+dz)] in SAFE_GROUND
                                for dx in (-1,0,1) for dz in (-1,0,1))
            if solid_neighbors < 7:
                continue
            return SpawnSpot(Position(x+0.5,y,z+0.5),clearance=3,distance=math.hypot(x+0.5-near.x,z+0.5-near.z))
        raise TerrainUnavailable(
            'No verified open 3x3 spawn within 12 blocks. Move to open, level land and replay. '
            'The bot was NOT spawned inside blocks.')

    def verify(self, actual: Position) -> bool:
        x,y,z=math.floor(actual.x),math.floor(actual.y),math.floor(actual.z)
        samples=[(x,y+i,z) for i in (-1,0,1,2,3)]
        blocks=self.sensor.read(samples)
        if self._valid(blocks,x,y,z):
            return True
        # On dirt paths/farmland/mud, physics may settle the bot 1/16-1/8
        # below nominal Y. Only allow the specific recognized lower supports,
        # never wood, stone, leaves or other blocks where clipping is unsafe.
        fraction=actual.y-y
        if (fraction>=0.70 and blocks[(x,y,z)] in LOWERED_SUPPORTS
                and blocks[(x,y,z)] in SAFE_GROUND):
            return self._valid(blocks,x,y+1,z)
        return False
