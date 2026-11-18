"""Time- and distance-limited coordinate tracking; never teleports anyone."""
from __future__ import annotations
import math
from .observations import Position


class CoordinateTracker:
    def __init__(self, rules):
        self.rules = rules
        self.last_refresh = -1e12
        self.last_known: Position | None = None
        self.last_seen_at = -1e12

    def sample(self, seeker: Position, runner: Position, now: float) -> Position | None:
        if not self.rules.get('enabled', False):
            return None
        if now - self.last_refresh >= self.rules['cooldown_seconds']:
            self.last_refresh = now
            if seeker.distance(runner) <= self.rules['range_blocks']:
                self.last_known = runner
                self.last_seen_at = now
        if now - self.last_seen_at <= self.rules['last_known_seconds']:
            return self.last_known
        return None

    def message(self, seeker: Position, runner: Position, now: float) -> str | None:
        if now - self.last_refresh < self.rules['cooldown_seconds']:
            return None
        seen = self.sample(seeker, runner, now)
        if seen is None:
            return '[Tracker] Runner out of range or no recent trail.'
        if self.rules['reveal_exact_coordinates_to_hunter']:
            return f'[Tracker] Runner last seen near X {math.floor(seen.x)}, Y {math.floor(seen.y)}, Z {math.floor(seen.z)}'
        return f'[Tracker] Last seen {seeker.distance(seen):.0f} blocks away.'
