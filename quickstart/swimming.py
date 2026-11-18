"""Carpet water control with continuous ascent and an air emergency safeguard."""
from __future__ import annotations
import math
import re
import time
from .observations import Position
from .terrain import terrain_type, TerrainUnavailable

_AIR_PATTERN = re.compile(r'MHAIR:(-?[0-9]+):END')

class WaterSurvival:
    def __init__(self, rcon, sensor, bot: str = 'ManhuntBot', clock=time.monotonic, *, rescue_effect=True):
        self.rcon, self.sensor, self.bot, self.clock = rcon, sensor, bot, clock
        self.rescue_effect = rescue_effect
        self.swimming = False
        self.last_air_check = 0.0
        self.last_air = 300
        self.last_insurance = 0.0
        self.last_surface = 0.0
        self.emergency_count = 0
        self.vertical_mode = None
        self.entered_at = 0.0
        self.head_submerged = False
        self.vertical_changed_at = -1000.0
        self.vertical_switches = 0
        self.horizontal_anchor = None
        self.horizontal_progress_at = 0.0
        self.vertical_progress_anchor = 0.0
        self.stall_detected = False
        self.stall_events = 0

    def reset(self):
        self.swimming = False
        self.last_air_check = 0.
        self.last_air = 300
        self.last_insurance = 0.
        self.last_surface = 0.
        self.vertical_mode = None
        self.entered_at = 0.
        self.head_submerged = False
        self.vertical_changed_at = -1000.0
        self.vertical_switches = 0
        self.horizontal_anchor = None
        self.horizontal_progress_at = 0.0
        self.vertical_progress_anchor = 0.0
        self.stall_detected = False
        self.stall_events = 0

    def read_air(self, now: float) -> int:
        if now-self.last_air_check < 1.0:
            return self.last_air
        response = self.rcon.command(
            f"script run print('MHAIR:' + str(player('{self.bot}')~'air') + ':END')")
        match = _AIR_PATTERN.search(response)
        if not match:
            raise TerrainUnavailable('Unable to read bot air from Scarpet: '+response[:130])
        self.last_air=int(match.group(1))
        self.last_air_check=now
        return self.last_air

    def update(self, pos: Position, now: float, *, stop_movement, vertical: int = 1):
        """Returns True while immersed. Level travel is normally horizontal.

        Hold jump only for verified ascent/low air, sneak for descent; normal
        swimming maintains horizontal motion without vertical bouncing.
        On very low air, gives a *temporary* water-breathing emergency rescue.
        This is intentionally logged rather than concealing a failed route.
        """
        x,y,z=math.floor(pos.x),math.floor(pos.y),math.floor(pos.z)
        blocks=self.sensor.read([(x,y+i,z) for i in (0,1,2)])
        feet_water = terrain_type(blocks[(x,y,z)]) == 'water'
        self.head_submerged = terrain_type(blocks[(x,y+1,z)]) == 'water'
        immersed = feet_water or self.head_submerged
        if not immersed:
            if self.swimming:
                # A level swimmer has no held jump/sneak to release. Calling
                # Carpet's global /stop here would also kill forward motion.
                if self.vertical_mode in (1, -1):
                    stop_movement()
                self.swimming=False
                self.vertical_mode=None
                self.horizontal_anchor = None
                self.horizontal_progress_at = 0.0
                self.vertical_progress_anchor = 0.0
                self.stall_detected = False
                print('[SWIM] Left water; vertical swim controls released.')
            return False
        air=self.read_air(now)
        if not self.swimming:
            self.swimming=True
            self.entered_at=now
            self.horizontal_anchor=(pos.x,pos.z)
            self.horizontal_progress_at=now
            self.vertical_progress_anchor=pos.y
        # Track *physical displacement*, not changing A* waypoint keys.
        # Constantly replanning a 1-cell swim path previously masked stalls.
        self.stall_detected = False
        if self.horizontal_anchor is not None:
            displacement=math.hypot(pos.x-self.horizontal_anchor[0],
                                    pos.z-self.horizontal_anchor[1])
            vertical_gain = ((self.vertical_mode == 1 and
                              pos.y - self.vertical_progress_anchor >= .6) or
                             (self.vertical_mode == -1 and
                              self.vertical_progress_anchor - pos.y >= .6))
            if displacement >= .42 or vertical_gain:
                # Climbing a real water column is progress even without XZ
                # movement. Surface bobbing (small up/down changes) is not.
                if displacement >= .42:
                    self.horizontal_anchor=(pos.x,pos.z)
                if vertical_gain:
                    self.vertical_progress_anchor=pos.y
                self.horizontal_progress_at=now
            elif now-self.horizontal_progress_at >= 3.5:
                self.stall_detected=True
                self.stall_events+=1
                self.horizontal_progress_at=now
        # Critically low air overrides pursuit or deliberate diving.
        if air < 140:
            vertical=1
        vertical=max(-1,min(1,vertical))
        emergency = air < 140
        # Standing/wading at a breathable surface is NOT a vertical swim.
        # Otherwise a one-block-up A* waypoint makes the fake player bob,
        # repeatedly interrupting forward motion instead of leaving water.
        if not self.head_submerged and not emergency and vertical > 0:
            vertical = 0
        if (self.vertical_mode is not None and self.vertical_mode != vertical
                and not emergency and not (not self.head_submerged and vertical == 0)
                and now - self.vertical_changed_at < 1.1):
            # Hysteresis: a fluctuating surface/waypoint height must not
            # switch continuous Carpet controls every few game ticks.
            vertical = self.vertical_mode
        if self.vertical_mode != vertical:
            # Carpet has no independent "unjump" command. Stop first to
            # release the previous continuous input before switching axes.
            if self.vertical_mode in (1, -1):
                # Carpet cannot release a continuous jump independently of
                # the other controls. One stop is necessary when changing
                # from a *held* vertical action; the caller resumes forward
                # movement in the same navigation tick.
                stop_movement()
            if vertical > 0:
                self.rcon.command(f'player {self.bot} jump continuous')
            elif vertical < 0:
                self.rcon.command(f'player {self.bot} sneak')
            # A level segment explicitly holds neither vertical control.
            self.vertical_mode=vertical
            self.vertical_changed_at=now
            self.vertical_switches += 1
            print(f'[SWIM] Mode={vertical:+d}, head_submerged={self.head_submerged}, air={air}.')
        # A short effect is a controlled fail-safe, NOT proof of successful swimming.
        # At 20 ticks/s, 65 ticks gives time to turn around before drowning.
        if self.rescue_effect and air < 65 and now-self.last_insurance>10:
            response=self.rcon.command(f'effect give {self.bot} minecraft:water_breathing 12 0 true')
            if 'unknown' not in response.lower() and 'failed' not in response.lower():
                self.emergency_count+=1
                print('[SWIM WARNING] Air critically low: temporary water-breathing rescue applied.')
            self.last_insurance=now
        # If submerged under a solid roof, don't keep blindly driving forward.
        if terrain_type(blocks[(x,y+2,z)])=='solid' and now-self.last_surface>3:
            print('[SWIM] Overhead obstruction detected; prioritizing surface clearance.')
            self.last_surface=now
        return True
