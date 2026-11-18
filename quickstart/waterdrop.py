"""Conservative observation-only ravine water-landing detector.

Detects a fully sampled vertical column and >=2 blocks of water below.
Does NOT guarantee the physical trajectory: the active movement skill must
still validate actual landing. Rejects unknown/hazardous cells.
"""
from __future__ import annotations
from dataclasses import dataclass
import math
from .observations import Position
from .terrain import terrain_type

@dataclass(frozen=True)
class WaterDrop:
    destination: Position
    depth: int
    horizontal: int

class WaterDropPlanner:
    def __init__(self,sensor,max_depth:int=10,max_horizontal:int=3):
        self.sensor,self.max_depth,self.max_horizontal=sensor,max_depth,max_horizontal

    def propose(self,bot:Position,desired:Position) -> WaterDrop | None:
        x,y,z=map(math.floor,(bot.x,bot.y,bot.z))
        # Need solid takeoff support. Do not try jumping while already in air.
        ground=self.sensor.read([(x,y-1,z),(x,y,z),(x,y+1,z)])
        if not (terrain_type(ground[(x,y-1,z)])=='solid'
                and terrain_type(ground[(x,y,z)])=='air'
                and terrain_type(ground[(x,y+1,z)])=='air'):
            return None
        ux,uz=desired.x-bot.x,desired.z-bot.z
        magnitude=math.hypot(ux,uz)
        if magnitude<.5: return None
        dx,dz=ux/magnitude,uz/magnitude
        options=[]
        for distance in range(1,self.max_horizontal+1):
            tx,tz=math.floor(bot.x+dx*distance),math.floor(bot.z+dz*distance)
            # Sample full drop column, including entry and deep water landing.
            coords=[(tx,k,tz) for k in range(y-self.max_depth-2,y+3)]
            blocks=self.sensor.read(coords)
            for lower in range(y-3,y-self.max_depth-1,-1):
                if not (terrain_type(blocks[(tx,lower,tz)])=='water'
                        and terrain_type(blocks[(tx,lower-1,tz)])=='water'):
                    continue
                if any(terrain_type(blocks[(tx,k,tz)])!='air' for k in range(lower+1,y+3)):
                    continue
                # Require a 3x3, two-block-deep pool. A one-block puddle
                # doesn't give the fake player's collision box any meaningful
                # landing margin when timed movements are still uncalibrated.
                footprint=[(tx+ox,level,tz+oz) for ox in (-1,0,1)
                           for oz in (-1,0,1) for level in (lower,lower-1)]
                landing_blocks=self.sensor.read(footprint)
                if any(terrain_type(landing_blocks[cell])!='water' for cell in footprint):
                    continue
                # The pool must be below the launch edge and avoid solids in
                # the outward horizontal path. No 'visible water' guesswork.
                corridor=[(math.floor(bot.x+dx*f),y,math.floor(bot.z+dz*f))
                          for f in [i*.25 for i in range(1,distance*4+1)]]
                nearby=self.sensor.read(list(dict.fromkeys(corridor)))
                if any(terrain_type(nearby[c])!='air' for c in corridor):
                    continue
                options.append(WaterDrop(Position(tx+.5,lower+1,tz+.5),y-lower,distance))
                break
        if not options: return None
        return min(options,key=lambda p:(p.horizontal, p.depth))
