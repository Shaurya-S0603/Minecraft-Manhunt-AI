"""Scope information disclosure and choose rolling, reachable objectives."""
from dataclasses import dataclass
import math
from ..observations import Position
from ..terrain import TerrainUnavailable
from ..combat import attack_line_clear

DIMENSIONS = ("minecraft:overworld", "minecraft:the_nether", "minecraft:the_end")


def shift(pos, dx=0, dy=0, dz=0):
    return Position(pos.x + dx, pos.y + dy, pos.z + dz)


@dataclass(frozen=True)
class Guide:
    target: Position
    visible: Position | None = None
    bearing: int | None = None


class Compass:
    def __init__(self, rules):
        self.rules = rules
        self.reset()

    def reset(self):
        self.next_sample = 0.0
        self.hint = None
        self.last_visible = None
        self.last_visible_at = -math.inf

    def observe(self, bot, runner, now, sensor):
        """Only exact same-dimension LOS observations leave this boundary."""
        if runner is None:
            return None
        distance = bot.distance(runner)
        if distance <= self.rules["visible_blocks"]:
            try:
                if attack_line_clear(sensor, bot, runner):
                    self.last_visible, self.last_visible_at = runner, now
                    return Guide(runner, visible=runner)
            except TerrainUnavailable:
                pass
        if now >= self.next_sample:
            self.next_sample = now + self.rules["sample_seconds"]
            if distance <= self.rules["range_blocks"]:
                dx, dz = runner.x - bot.x, runner.z - bot.z
                if math.hypot(dx, dz) > 0.25:
                    sector = round(math.degrees(math.atan2(dz, dx)) / 15) % 24
                    self.hint = (sector, now)
        if self.last_visible and now - self.last_visible_at < 4:
            return Guide(self.last_visible)
        if self.hint and now - self.hint[1] <= self.rules["trail_seconds"]:
            sector, _ = self.hint
            angle = math.radians(sector * 15)
            return Guide(shift(bot, dx=10 * math.cos(angle), dz=10 * math.sin(angle)),
                         bearing=sector)
        if self.last_visible and now - self.last_visible_at <= self.rules["trail_seconds"]:
            phase = int((now - self.last_visible_at) / 6) * math.pi / 2
            return Guide(shift(self.last_visible, dx=6 * math.cos(phase), dz=6 * math.sin(phase)))
        return None


@dataclass
class Attempt:
    context: str
    tactic: str
    started: float
    distance: float
    origin: Position


class Pursuit:
    def __init__(self, playbook, runner_name):
        self.book = playbook
        self.runner = playbook.runner_key(runner_name)
        self.reset()

    def reset(self):
        self.previous = None
        self.velocity = (0., 0.)
        self.attempt = None

    def goal(self, bot, guide, dimension, now):
        runner = guide.visible
        if runner is None:
            self.reset()
            return guide.target
        speed_x, speed_z = self.velocity
        motion = "steady" if math.hypot(speed_x, speed_z) > 1.4 else "slow"
        if self.previous:
            prev, when = self.previous
            elapsed = now - when
            if 0.10 <= elapsed <= 1.0:
                vx, vz = (runner.x - prev.x) / elapsed, (runner.z - prev.z) / elapsed
                if vx * speed_x + vz * speed_z < -1:
                    motion = "turning"
                self.velocity = (0.55 * speed_x + 0.45 * vx, 0.55 * speed_z + 0.45 * vz)
        self.previous = (runner, now)
        context = f"{self.runner}/{dimension}/{motion}"
        distance = bot.distance(runner)
        if self.attempt and now - self.attempt.started >= 3:
            self.finish(bot, distance)
        if self.attempt is None:
            can_lead = distance >= 5 and math.hypot(*self.velocity) >= .7
            options = ("direct", "lead", "wide") if can_lead else ("direct",)
            self.attempt = Attempt(context, self.book.choose(context, options), now, distance, bot)
        tactic = self.attempt.tactic if distance >= 5 else "direct"
        vx, vz = self.velocity
        magnitude = math.hypot(vx, vz)
        if tactic == "direct" or magnitude < 0.7:
            return runner
        lead = min(3.0 if tactic == "lead" else 5.0, magnitude * .7)
        return shift(runner, dx=vx / magnitude * lead, dz=vz / magnitude * lead)

    def finish(self, bot, distance, caught=False):
        attempt, self.attempt = self.attempt, None
        if attempt and (caught or bot.distance(attempt.origin) > 1):
            reward = 1 if caught else (attempt.distance - distance) / 7
            self.book.reward(attempt.context, attempt.tactic, reward)
