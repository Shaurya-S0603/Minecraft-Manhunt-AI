"""Velocity measured jump control and Mineflayer-inspired swept-footprint checks.

No third-party movement implementation is copied. Collision geometry is
server-observed and unknown/out-of-bounds cells are always rejected.
"""
from __future__ import annotations
from collections import deque
from dataclasses import dataclass
import math
from .observations import Position
from .terrain import terrain_type


class VelocityTracker:
    def __init__(self):
        self.samples=deque(maxlen=8)

    def observe(self, pos: Position, timestamp: float):
        if self.samples and timestamp <= self.samples[-1][0]:
            return
        self.samples.append((timestamp,pos))

    def speed_towards(self, source: Position, target: Position) -> float:
        if len(self.samples)<2: return 0.
        now=self.samples[-1][0]
        eligible=[(t,p) for t,p in self.samples if now-t<=.70]
        if len(eligible)<2: return 0.
        first_t,first_p=eligible[0]
        last_t,last_p=eligible[-1]
        dt=last_t-first_t
        if dt<.08: return 0.
        dx,dz=target.x-source.x,target.z-source.z
        magnitude=math.hypot(dx,dz)
        if magnitude<.5: return 0.
        projected=((last_p.x-first_p.x)*dx+(last_p.z-first_p.z)*dz)/magnitude/dt
        # Clamp bad samples, teleport displacement, and transient RCON jitter.
        if not math.isfinite(projected) or projected>8.5: return 0.
        return max(0.,projected)


@dataclass(frozen=True)
class JumpDecision:
    command: str  # approach, jump, hold, abort
    distance_from_takeoff: float
    approach_speed: float
    reason: str=''


class SprintJumpController:
    def __init__(self, min_speed: float=1.7, max_offset: float=.56):
        self.min_speed,self.max_offset=min_speed,max_offset
        self.key=None
        self.fired=False
        self.started=0.

    def clear(self):
        self.key=None
        self.fired=False
        self.started=0.

    def decide(self, key, current: Position, takeoff: Position, landing: Position,
               now: float, approach_speed: float, launch_threshold: float) -> JumpDecision:
        if key != self.key:
            self.key=key
            self.fired=False
            self.started=now
        dx,dz=landing.x-takeoff.x,landing.z-takeoff.z
        magnitude=math.hypot(dx,dz)
        if magnitude<1.5:
            return JumpDecision('abort',0.,approach_speed,'not a real gap')
        along=((current.x-takeoff.x)*dx+(current.z-takeoff.z)*dz)/magnitude
        perpendicular=abs((current.x-takeoff.x)*dz-(current.z-takeoff.z)*dx)/magnitude
        if perpendicular>.35:
            return JumpDecision('abort',along,approach_speed,'outside verified launch corridor')
        if self.fired:
            return JumpDecision('hold',along,approach_speed)
        if along>self.max_offset or now-self.started>2.8:
            return JumpDecision('abort',along,approach_speed,'no safe takeoff window')
        if along>=launch_threshold and approach_speed>=self.min_speed:
            self.fired=True
            return JumpDecision('jump',along,approach_speed)
        return JumpDecision('approach',along,approach_speed)


class JumpCorridor:
    """Read-only head/feet/swept-collision preflight, no world modifications."""
    def __init__(self,sensor):
        self.sensor=sensor

    def verified(self,takeoff:Position,landing:Position) -> bool:
        # Only same-elevation cardinal sprint jumps. Upward climbs remain A*.
        if abs(takeoff.y-landing.y)>.05: return False
        dx,dz=landing.x-takeoff.x,landing.z-takeoff.z
        horizontal=math.hypot(dx,dz)
        if not 1.5<=horizontal<=4.1: return False
        if abs(dx)>.1 and abs(dz)>.1: return False
        y=math.floor(takeoff.y)
        ux,uz=dx/horizontal,dz/horizontal
        steps=math.ceil(horizontal/.25)
        coords=set()
        for i in range(steps+1):
            t=i/steps
            px,pz=takeoff.x+t*dx,takeoff.z+t*dz
            # Full 0.6-block player width, conservatively checking overlap.
            for offset in (-.31,0,.31):
                x=math.floor(px-uz*offset)
                z=math.floor(pz+ux*offset)
                for level in (y,y+1,y+2): coords.add((x,level,z))
        takeoff_ground=(math.floor(takeoff.x),y-1,math.floor(takeoff.z))
        landing_ground=(math.floor(landing.x),y-1,math.floor(landing.z))
        coords.update((takeoff_ground,landing_ground))
        observed=self.sensor.read(sorted(coords))
        # Unknown samples are NEVER clearance; missing cells must not crash
        # navigation (the v0.7.2 A* boundary failure regression).
        if any(p not in observed for p in coords):
            return False
        if any(terrain_type(observed[p])!='air' for p in coords
               if p not in (takeoff_ground,landing_ground)):
            return False
        return (terrain_type(observed[takeoff_ground])=='solid'
                and terrain_type(observed[landing_ground])=='solid')
