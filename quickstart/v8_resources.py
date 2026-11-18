"""Bounded gather objective: approach, physically harvest, verify pickup.
Minecraft remains authoritative; we never give items or edit inventory/world NBT.
"""
from __future__ import annotations
from dataclasses import dataclass
import math
from .terrain import TerrainUnavailable, terrain_type
from .observations import Position

@dataclass
class GatherGoal:
    block: tuple[int, int, int]
    name: str
    stand: Position
    expires: float
    baseline: int
    phase: str = 'approach'
    pickup_until: float = 0.0
    motion_anchor: Position | None = None
    motion_at: float = 0.0


class ResourceCollector:
    def __init__(self, inventory, miner, sensor, rules):
        self.inventory, self.miner, self.sensor, self.rules = inventory, miner, sensor, rules
        self.next_check = 0.0
        self.goal: GatherGoal | None = None
        self.attempts = self.confirmed = self.failed = self.aborted = 0
        self.reason = None
        self.last_notice = -1e12
        self.rejected = {}

    def notice(self, reason, now):
        if reason != self.reason or now-self.last_notice >= 20:
            print(f'[RESOURCE] {reason}')
            self.reason, self.last_notice = reason, now

    def ready(self, bot, human, role):
        return (self.rules.get('enabled', False) and self.inventory.available is True
                and self.rules.get(f'gather_when_{role}', False)
                and bot.distance(human) >= self.rules['minimum_distance_from_hunter'])

    def cancel(self, now, stop_movement, reason, *, failure=False):
        if self.goal is None:
            return
        if self.goal.phase == 'harvest':
            self.miner.stop()
        stop_movement()
        self.rejected[self.goal.block] = now+30
        self.goal = None
        self.next_check = now+self.rules['cooldown_seconds']
        if failure:
            self.failed += 1
        else:
            self.aborted += 1
        self.notice(reason, now)

    @staticmethod
    def dry_stand(blocks, x, y, z):
        return (terrain_type(blocks[(x,y-1,z)]) == 'solid'
                and all(terrain_type(blocks[(x,y+i,z)]) == 'air' for i in (0,1)))

    def find(self, bot, human, now):
        # Search several stand elevations: forest terrain rarely matches
        # the bot's exact foot height. Only use observed dry support and headroom.
        radius = int(self.rules.get('search_radius', 4))
        x,y,z = math.floor(bot.x),math.floor(bot.y),math.floor(bot.z)
        points = [(x+dx,y+dy,z+dz) for dx in range(-radius,radius+1)
                  for dz in range(-radius,radius+1) for dy in (-2,-1,0,1,2,3)]
        b = self.sensor.read(points)
        choices = []
        allowed = set(self.rules['allowed_blocks'])
        self.rejected = {p:t for p,t in self.rejected.items() if t>now}
        for (bx,by,bz), name in b.items():
            if not name.endswith('_log') or name not in allowed or (bx,by,bz) in self.rejected:
                continue
            support=b.get((bx,by-1,bz))
            if support is None or terrain_type(support) != 'solid' or support.endswith('_log'):
                continue
            for dx,dz in ((1,0),(-1,0),(0,1),(0,-1)):
                sx,sz = bx+dx,bz+dz
                for sy in (by,by-1):
                    if abs(sy-y)>1 or not all((sx,sy+i,sz) in b for i in (-1,0,1)):
                        continue
                    if not self.dry_stand(b,sx,sy,sz):
                        continue
                    stand=Position(sx+.5,float(sy),sz+.5)
                    if stand.distance(human)<self.rules['minimum_distance_from_hunter']:
                        continue
                    choices.append((bot.distance(stand)+.3*abs(sy-y), (bx,by,bz), name, stand))
        if not choices:
            return None
        _, block, name, stand = min(choices, key=lambda c:c[0])
        return GatherGoal(block,name,stand,now+float(self.rules.get('objective_timeout',18)),
                          self.inventory.count_suffix('_log'))

    def try_gather(self, bot, human, role, now, stop_movement, *, navigate=None, unsafe=False):
        """True while gathering owns this tick's controls. False resumes escape.
        The original API is retained; without a navigator we cannot approach.
        """
        if not self.ready(bot,human,role) or unsafe:
            if self.goal is not None:
                self.cancel(now,stop_movement,'Abandoned harvest: threat, water, or unavailable inventory.')
            elif self.rules.get('enabled') and self.rules.get(f'gather_when_{role}') and now>=self.next_check:
                self.next_check=now+3
                reason = ('Native inventory unavailable; collection disabled.' if self.inventory.available is not True else
                          'Water/airborne movement has priority.' if unsafe else
                          f'Hunter too close for gathering ({bot.distance(human):.1f} blocks).')
                self.notice(reason,now)
            return False
        if self.goal is None:
            if now<self.next_check or self.miner.operation is not None:
                return False
            self.next_check=now+self.rules['cooldown_seconds']
            if self.inventory.count_suffix('_log')>=self.rules['target_log_count']:
                self.notice('Log target reached; continuing escape.',now)
                return False
            if len(self.inventory.slots)>=36:
                self.notice('Inventory full; continuing escape.',now)
                return False
            try:
                self.goal=self.find(bot,human,now)
            except (TerrainUnavailable,KeyError):
                self.notice('Resource scan unavailable; continuing escape.',now)
                return False
            if self.goal is None:
                self.notice('No safe nearby log target; continuing escape.',now)
                return False
            self.notice(f'Target {self.goal.name} at {self.goal.block}; approaching.',now)
        g=self.goal
        try:
            if g.stand.distance(human)<self.rules['minimum_distance_from_hunter']:
                self.cancel(now,stop_movement,'Hunter approached gather destination; escaping.')
                return False
            if now>=g.expires:
                self.cancel(now,stop_movement,'Gather objective timed out; continuing escape.',failure=True)
                return False
            if g.phase=='approach':
                if g.motion_anchor is None or bot.distance(g.motion_anchor)>=.4:
                    g.motion_anchor,g.motion_at=bot,now
                if bot.distance(g.stand)>.65:
                    if now-g.motion_at>=4.0:
                        self.cancel(now,stop_movement,'Gather approach stalled; returning to escape.',failure=True)
                        return False
                    if navigate is None:
                        self.cancel(now,stop_movement,'No resource navigation available.',failure=True)
                        return False
                    navigate(bot,g.stand,now)
                    return True
                self.sensor.cache.pop(g.block,None)
                if self.sensor.read([g.block])[g.block]!=g.name or not self.miner.try_exact(bot,g.block,now,stop_movement=stop_movement,allowed_blocks={g.name}):
                    self.cancel(now,stop_movement,'Log no longer safely reachable; continuing escape.',failure=True)
                    return False
                g.phase='harvest'
                self.attempts+=1
                self.notice(f'Harvesting {g.name} physically.',now)
                return True
            if g.phase=='harvest':
                if self.miner.tick(now):
                    return True
                # Only a real removed block starts the pickup phase.
                self.sensor.cache.pop(g.block,None)
                if self.sensor.read([g.block])[g.block]==g.name:
                    self.cancel(now,stop_movement,'Harvest failed; continuing escape.',failure=True)
                    return False
                stop_movement()
                g.phase='pickup'
                g.pickup_until=now+4.0
                self.notice('Block cleared; waiting for native item pickup.',now)
            if g.phase=='pickup':
                self.inventory.snapshot(force=(now>=g.pickup_until))
                if self.inventory.available is True and self.inventory.count_suffix('_log')>g.baseline:
                    self.confirmed+=1
                    self.goal=None
                    self.next_check=now+self.rules['cooldown_seconds']
                    self.notice('Confirmed inventory log increase; resuming escape.',now)
                    return False
                if now>=g.pickup_until:
                    self.cancel(now,stop_movement,'No inventory increase after harvest; continuing escape.',failure=True)
                    return False
                # Step onto the cleared log cell ONLY if both head and feet
                # are clear and supported; otherwise remain safely adjacent.
                x,y,z=g.block
                pts=[(x,y+i,z) for i in (-1,0,1)]
                for p in pts:self.sensor.cache.pop(p,None)
                b=self.sensor.read(pts)
                pickup=Position(x+.5,float(y),z+.5)
                if navigate is not None and self.dry_stand(b,x,y,z) and bot.distance(pickup)>.5:
                    navigate(bot,pickup,now)
                else:
                    stop_movement()
                return True
        except (TerrainUnavailable,KeyError):
            self.cancel(now,stop_movement,'Terrain unavailable during gather; continuing escape.',failure=True)
            return False
        return False

    def status(self):
        return f'attempted={self.attempts}, confirmed={self.confirmed}, failed={self.failed}, aborted={self.aborted}'
