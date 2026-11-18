"""Guarded physical bridge/pillar actions and replay-safe portal following."""
from dataclasses import dataclass
import hashlib
import math

from ..combat import attack_line_clear
from ..observations import Position
from ..terrain import terrain_type
from .pursuit import shift
from .recipes import BLOCKS, FIREPROOF, counts
from .supply import cell, centre

REPLACEABLE = {"air", "cave_air", "void_air", "water", "lava"}
PORTALS = {"nether_portal", "end_portal"}
FULL_SUPPORT = set(BLOCKS) | {"grass_block", "stone", "deepslate", "sandstone", "obsidian",
                             "gravel", "sand", "end_stone", "bricks", "stone_bricks"}


@dataclass
class Placement:
    kind: str
    support: tuple
    target: tuple
    item: str
    started: float
    before: int
    direction: tuple = (0, 0)
    last_use: float = -math.inf


@dataclass
class Crossing:
    cells: tuple[tuple[int, int, int], ...]
    direction: tuple[int, int]
    materials: tuple[str, ...]
    index: int
    deadline: float


class Builder:
    MAX_SPAN = 6
    AIR = {"air", "cave_air", "void_air"}

    def __init__(self, game):
        self.game = game
        self.job = None
        self.crossing = None
        self.next_try = 0.
        self.last_probe = None
        self.placed = 0
        self.crossed = 0

    @property
    def active(self):
        return self.job is not None or self.crossing is not None

    def cancel(self):
        if self.active:
            self.job = self.crossing = None
            self.game.stop()
            self.game.invalidate_route()

    @staticmethod
    def _column(support):
        x, y, z = support
        return [(x, y + dy, z) for dy in (0, 1, 2)]

    def _observe(self, cells):
        sensor = self.game.sensor
        for pos in cells:
            sensor.cache.pop(pos, None)
        return sensor.read(cells)

    def _clear_column(self, blocks, support):
        return all(blocks[p] in self.AIR for p in self._column(support)[1:])

    def _plan_crossing(self, support, direction, inventory):
        """Commit only to a flat, fully observed lane with a reachable bank."""
        sx, sz = direction
        x, y, z = support
        lane = [(x + i * sx, y, z + i * sz) for i in range(self.MAX_SPAN + 2)]
        blocks = self._observe([p for base in lane for p in self._column(base)])
        rules = self.game.settings["resources"]
        spans_lava = False
        for i, base in enumerate(lane[1:], start=1):
            if not self._clear_column(blocks, base):
                return None
            material = blocks[base]
            if material == "lava":
                if not rules["lava_bridge"]:
                    return None
                spans_lava = True
            if material not in REPLACEABLE:
                if i == 1 or material not in FULL_SUPPORT:
                    return None
                materials = tuple(name for name in BLOCKS if not spans_lava or name in FIREPROOF)
                if sum(inventory[name] for name in materials) < i - 1:
                    return None
                return tuple(lane[:i + 1]), materials
        return None

    def start(self, bot, target, now):
        g = self.game
        if (self.active or not g.settings["resources"]["build"] or not g.inventory.available
                or now < self.next_try or not g.grounded or g.water.swimming or g.miner.operation):
            return False
        x, y, z = cell(bot)
        below = (x, y - 1, z)
        inv = counts(g.inventory.slots)
        if abs(bot.y - y) > .11 or not any(inv[name] for name in BLOCKS):
            return False
        dx, dz = target.x - bot.x, target.z - bot.z
        distance = math.hypot(dx, dz)
        overhead = [(x, y + dy, z) for dy in (0, 1, 2, 3)]
        blocks = self._observe([below, *overhead])
        if blocks[below] not in FULL_SUPPORT or not self._clear_column(blocks, below):
            return False
        if (target.y - bot.y > 1.35 and distance < 2.6
                and abs(bot.x - x - .5) < .2 and abs(bot.z - z - .5) < .2
                and all(blocks[p] in self.AIR for p in overhead)):
            item = next(name for name in BLOCKS if inv[name])
            if not g.bridge.hold(g.inventory.slots, item):
                return False
            g.stop()
            g.invalidate_route()
            g.bridge.action("look down")
            g.bridge.action("jump once")
            self.job = Placement("pillar", below, overhead[0], item, now, inv[item])
            print(f"[BUILD] pillar attempt at {self.job.target} with {item}.")
            return True
        if distance <= 1.4:
            return False
        direction = ((1 if dx > 0 else -1, 0) if abs(dx) > abs(dz) else (0, 1 if dz > 0 else -1))
        probe = (below, direction)
        if self.last_probe and probe == self.last_probe[0] and now < self.last_probe[1]:
            return False
        self.last_probe = (probe, now + .65)
        planned = self._plan_crossing(below, direction, inv)
        if planned is None:
            return False
        cells, materials = planned
        g.stop()
        g.invalidate_route()
        g.bridge.action("sneak")
        self.crossing = Crossing(cells, direction, materials, 0, now + 2.5)
        print(f"[BUILD] Committed to a {len(cells) - 2}-block crossing toward {cells[-1]}.")
        return True

    def _walk_crossing(self, bot, now):
        g = self.game
        crossing = self.crossing
        base = crossing.cells[crossing.index]
        target = shift(centre(base), dy=.5)
        blocks = self._observe(self._column(base))
        sx, sz = crossing.direction
        lateral = abs((bot.x - target.x) * sz - (bot.z - target.z) * sx)
        if (now >= crossing.deadline or not g.grounded or abs(bot.y - target.y) > .13
                or bot.distance(target) > 1.3 or lateral > .52
                or blocks[base] not in FULL_SUPPORT or not self._clear_column(blocks, base)):
            self.cancel()
            return False
        if bot.distance(target) > .16:
            g.bridge.look(Position(target.x, bot.y + 1.27, target.z))
            g.bridge.action("move forward")
            return True
        if crossing.index == len(crossing.cells) - 1:
            self.crossed += 1
            print(f"[BUILD] Reached the far bank at {base}.")
            self.cancel()
            return True

        next_cell = crossing.cells[crossing.index + 1]
        blocks = self._observe(self._column(next_cell))
        material = blocks[next_cell]
        if not self._clear_column(blocks, next_cell):
            self.cancel()
            return False
        if material in FULL_SUPPORT:
            crossing.index += 1
            crossing.deadline = now + 2.5
            return True
        if (material not in REPLACEABLE or (material == "lava" and not
                (g.settings["resources"]["lava_bridge"] and all(name in FIREPROOF for name in crossing.materials)))):
            self.cancel()
            return False
        g.inventory.snapshot(force=True)
        inv = counts(g.inventory.slots) if g.inventory.available else {}
        item = next((name for name in crossing.materials if inv.get(name, 0)), None)
        if item is None or not g.bridge.hold(g.inventory.slots, item):
            self.cancel()
            return False
        g.stop()
        g.bridge.action("sneak")
        g.bridge.look(shift(bot, dx=-2 * sx, dy=1.27, dz=-2 * sz))
        g.bridge.action("move backward")
        self.job = Placement("bridge", base, next_cell, item, now, inv[item], crossing.direction)
        print(f"[BUILD] bridge attempt at {next_cell} with {item}.")
        return True

    def tick(self, bot, now):
        g = self.game
        if g.water.swimming and self.active:
            self.cancel()
            return False
        job = self.job
        if job is None:
            return self._walk_crossing(bot, now) if self.crossing else False
        blocks = self._observe([job.support, *self._column(job.target)])
        material = blocks[job.target]
        if job.last_use > -math.inf and material == job.item:
            g.inventory.snapshot(force=True)
            if not g.inventory.available or counts(g.inventory.slots)[job.item] >= job.before:
                self.cancel()
                return False
            self.placed += 1
            print(f"[BUILD] Confirmed {job.kind} placement at {job.target}.")
            if self.crossing:
                self.job = None
                self.crossing.index += 1
                self.crossing.deadline = now + 2.5
                g.stop()
                g.bridge.action("sneak")
            else:
                self.cancel()
            self.next_try = now + .25
            return True
        if (now - job.started > 1.8 or material not in REPLACEABLE
                or blocks[job.support] not in FULL_SUPPORT or not self._clear_column(blocks, job.target)):
            self.cancel()
            return False
        foot_y = job.support[1] + 1
        if job.kind == "pillar":
            if bot.y - foot_y > 1.01 and now - job.last_use > .10:
                g.bridge.action("use once")
                job.last_use = now
            return True
        sx, sz = job.direction
        projected = (bot.x - (job.support[0] + .5)) * sx + (bot.z - (job.support[2] + .5)) * sz
        if bot.y < foot_y - .12:
            self.cancel()
            return False
        if projected > .51 and now - job.last_use > .16:
            g.bridge.look(shift(centre(job.support), dx=.49 * sx, dz=.49 * sz))
            g.bridge.action("use once")
            job.last_use = now
        return True


@dataclass
class Ascent:
    base: tuple[int, int, int]
    ledge: Position
    best_y: float
    progressed_at: float
    deadline: float


class Climber:
    """Hold real climb controls through a verified wall and onto its ledge."""
    SURFACES = {"ladder", "vine"}

    def __init__(self, game):
        self.game = game
        self.ascent = None
        self.completed = 0
        self.last_probe = None

    def cancel(self):
        if self.ascent:
            self.ascent = None
            self.game.stop()
            self.game.invalidate_route()

    def start(self, bot, target, now):
        g = self.game
        if (self.ascent or g.water.swimming or g.miner.operation
                or target.y - bot.y < 1.45 or math.hypot(target.x - bot.x, target.z - bot.z) > 6):
            return False
        x, y, z = cell(bot)
        base = (x, y, z)
        if self.last_probe and base == self.last_probe[0] and now < self.last_probe[1]:
            return False
        self.last_probe = (base, now + .5)
        neighbours = [(x + dx, y, z + dz) for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1))]
        ground = g.sensor.read([base, *neighbours])
        kind = ground[base]
        walls = [p for p in neighbours if ground[p] in FULL_SUPPORT]
        if kind not in self.SURFACES or len(walls) != 1:
            return False
        wx, _, wz = walls[0]
        if (wx - x) * (target.x - bot.x) + (wz - z) * (target.z - bot.z) <= 0:
            return False

        face = [(wx, y + i, wz) for i in range(10)]
        column = [(x, y + i, z) for i in range(9)]
        blocks = g.sensor.read(face + column)
        for rise in range(1, 9):
            if blocks[column[rise - 1]] != kind:
                return False
            material = blocks[face[rise]]
            if material in FULL_SUPPORT:
                continue
            if (material not in Builder.AIR or blocks[face[rise + 1]] not in Builder.AIR
                    or blocks[column[rise]] not in Builder.AIR or rise < 2):
                return False
            ledge = Position(wx + .5, y + rise, wz + .5)
            g.stop()
            g.invalidate_route()
            g.bridge.look(Position(ledge.x, bot.y + 1.62, ledge.z))
            g.bridge.action("jump continuous")
            g.bridge.action("move forward")
            self.ascent = Ascent(base, ledge, bot.y, now, now + 9)
            print(f"[CLIMB] Holding {kind} to the observed ledge at {ledge}.")
            return True
        return False

    def tick(self, bot, now):
        climb = self.ascent
        if not climb:
            return False
        g = self.game
        ledge = climb.ledge
        lx, ly, lz = cell(ledge)
        if bot.y >= ledge.y - .9:
            floor, foot, head = [(lx, ly + dy, lz) for dy in (-1, 0, 1)]
            for pos in (floor, foot, head):
                g.sensor.cache.pop(pos, None)
            blocks = g.sensor.read([floor, foot, head])
            if (blocks[floor] not in FULL_SUPPORT or blocks[foot] not in Builder.AIR
                    or blocks[head] not in Builder.AIR):
                self.cancel()
                return False
        if (g.grounded and bot.y >= ledge.y - .10 and
                (math.floor(bot.x), math.floor(bot.z)) == (lx, lz)):
            self.completed += 1
            print(f"[CLIMB] Reached the ledge at {ledge}.")
            self.cancel()
            return True
        if bot.y > climb.best_y + .16:
            climb.best_y = bot.y
            climb.progressed_at = now
        if (now >= climb.deadline or now - climb.progressed_at > 1.85 or g.water.swimming
                or bot.y < climb.base[1] - .25 or math.hypot(bot.x - ledge.x, bot.z - ledge.z) > 1.75):
            self.cancel()
            return False
        return True


class Portals:
    def __init__(self, game, book, scope):
        self.game = game
        self.book = book
        self.scope = scope
        self.known = {}
        self.next_scan = 0.
        self.entered = None
        self.cooldowns = {}
        self.transitions = 0
        self.next_ignite = 0.

    def observe(self, dimension, bot, runner, now):
        if bot.distance(runner) > 12 or now < self.next_scan:
            return
        self.next_scan = now + 1.8
        x, y, z = cell(runner)
        coordinates = [(x + dx, y + dy, z + dz)
                       for dx in range(-2, 3) for dz in range(-2, 3) for dy in (-1, 0, 1)
                       if dx*dx + dz*dz <= 5]
        for p, block in self.game.sensor.read(coordinates).items():
            pos = centre(p)
            if block in PORTALS and attack_line_clear(self.game.sensor, bot, shift(pos, dy=-1.0)):
                self.known[dimension, p] = (block, now)
        self.known = {key: record for key, record in self.known.items() if now - record[1] <= 120}

    def context(self, dimension):
        return f"portal/{self.scope}/{dimension}"

    @staticmethod
    def key(p):
        return hashlib.sha256(str(p).encode()).hexdigest()[:12]

    def crossed(self, old_dimension, new_dimension):
        if self.entered:
            p, origin, _, expected = self.entered
            if old_dimension == origin:
                self.book.reward(self.context(origin), self.key(p), 1 if new_dimension == expected else -.5)
        self.entered = None
        self.transitions += 1

    def follow(self, dimension, runner_dim, bot, now):
        g = self.game
        if self.entered and self.entered[1] == dimension and self.entered[3] == runner_dim:
            p, _, started, _ = self.entered
            if now - started > 30:
                self.book.reward(self.context(dimension), self.key(p), -1)
                self.cooldowns[dimension, p] = now + 20
                self.entered = None
            else:
                return self._approach(bot, p, now)
        self.entered = None
        kind = "end_portal" if "minecraft:the_end" in (dimension, runner_dim) else "nether_portal"
        candidates = [p for (dim, p), (block, seen) in self.known.items()
                      if dim == dimension and block == kind and now - seen < 90
                      and bot.distance(centre(p)) < 96 and self.cooldowns.get((dim, p), 0) <= now]
        if not candidates:
            return False
        candidates.sort(key=lambda p: bot.distance(centre(p)))
        candidates = candidates[:3]
        selected = self.book.choose(self.context(dimension), [self.key(p) for p in candidates])
        target = next(p for p in candidates if self.key(p) == selected)
        self.entered = (target, dimension, now, runner_dim)
        return self._approach(bot, target, now)

    def _approach(self, bot, portal, now):
        g = self.game
        target = centre(portal)
        distance = math.hypot(bot.x - target.x, bot.z - target.z)
        current = cell(bot)
        feet = (current[0], current[1] - 1, current[2])
        if distance < 1.15 and abs(bot.y - target.y) < 1.6:
            g.sensor.cache.pop(portal, None)
            blocks = g.sensor.read([portal, current, feet])
            if blocks[portal] not in PORTALS:
                bottom = (portal[0], portal[1] - 1, portal[2])
                if (now >= self.next_ignite and blocks[portal] == "air" and g.grounded
                        and g.settings["resources"]["enabled"] and g.inventory.available
                        and g.sensor.read([bottom])[bottom] == "obsidian"
                        and g.bridge.hold(g.inventory.slots, "flint_and_steel")):
                    g.stop()
                    g.bridge.look(shift(centre(bottom), dy=.48))
                    g.bridge.action("use once")
                    self.next_ignite = now + 3
                    return True
                return False
            if blocks[current] in PORTALS or blocks[feet] == "end_portal":
                g.halt_movement()
                return True
            # This is a short explicit interaction with a verified open portal.
            # Normal A* never treats the unknown space below it as safe ground.
            if abs(bot.y - target.y) < .8 and blocks[portal] == "nether_portal":
                g.look_and_move(shift(target, dy=-.5))
                return True
            if (blocks[portal] == "end_portal" and target.y - .6 <= bot.y <= target.y + 1.55
                    and g.grounded):
                g.look_and_move(shift(target, dy=-.5))
                return True
        g.navigate(bot, shift(target, dy=-.5), now)
        return True
