"""Bounded survival objectives. Scavenging and harvesting use player actions."""
from collections import Counter
from dataclasses import dataclass
import math

from ..combat import attack_line_clear
from ..observations import Position
from ..terrain import terrain_type
from .pursuit import shift
from .recipes import (ARMOR_TIER, ARMOR_TYPES, BLOCKS, FOOD, LOGS, PICKS,
                      PORTAL_ITEMS, STONE, WEAPONS, counts, plan, recipes)

STONE_BLOCKS = ("stone", "deepslate", "blackstone")
ARMOR = tuple(f"{tier}_{piece}" for piece in ARMOR_TYPES for tier in ARMOR_TIER)
WANTED = frozenset((*BLOCKS, *LOGS, *FOOD, *WEAPONS, *PICKS, *ARMOR, *PORTAL_ITEMS,
                    "leather", "stick", "crafting_table"))


def cell(pos):
    return math.floor(pos.x), math.floor(pos.y), math.floor(pos.z)


def centre(block):
    x, y, z = block
    return Position(x + .5, y + .5, z + .5)


@dataclass
class Harvest:
    block: tuple
    name: str
    started: float
    stand: Position
    before: int
    broken_at: float | None = None


def harvest_product(block):
    return {"grass_block": "dirt", "stone": "cobblestone",
            "deepslate": "cobbled_deepslate"}.get(block, block)


class Supply:
    def __init__(self, game):
        self.game = game
        self.rules = game.settings["resources"]
        self.harvest = None
        self.next_scan = 0.
        self.action_until = 0.
        self.eating = False
        self.worn = {}
        self.crafted = Counter()
        self.task = None
        self.task_until = 0.
        self.refresh_at = 0.
        self.blocked = {}

    def cancel(self, now):
        if not (self.harvest or self.eating or self.task or now < self.action_until):
            return
        self.game.miner.stop()
        self.game.stop()
        self.game.invalidate_route()
        self.harvest = self.task = None
        self.eating = False
        self.action_until = 0.
        self.next_scan = now + 4

    def _hold(self, item):
        bag = self.game.inventory
        if self.game.bridge.hold(bag.slots, item):
            bag.snapshot(force=True)
            return True
        return False

    def hold_weapon(self):
        bag = self.game.inventory
        inv = counts(bag.slots) if bag.available else Counter()
        weapon = next((name for name in WEAPONS if inv[name]), None)
        if weapon:
            self._hold(weapon)

    def _food_or_armor(self, bot, hunger, inv, now):
        g = self.game
        food = next((name for name in FOOD if inv[name]), None)
        if food and hunger <= 16 and self._hold(food):
            g.stop()
            g.bridge.look(shift(bot, dy=6))
            g.bridge.action("use continuous")
            self.action_until = now + 1.9
            self.eating = True
            return True
        for piece in ARMOR_TYPES:
            if piece in self.worn:
                continue
            item = next((f"{tier}_{piece}" for tier in ARMOR_TIER if inv[f"{tier}_{piece}"]), None)
            if item and self._hold(item):
                g.stop()
                g.bridge.look(shift(bot, dy=6))
                g.bridge.action("use once")
                self.action_until = now + .3
                return True
        return False

    def _table(self, bot, inv, now):
        g = self.game
        x, y, z = cell(bot)
        cells = [(x + dx, y - 1 + dy, z + dz)
                 for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)) for dy in (0, 1, 2)]
        blocks = g.sensor.read(cells)
        for target, material in blocks.items():
            if material == "crafting_table" and bot.distance(centre(target)) < 2.1:
                return target
        if now < self.action_until or not inv["crafting_table"] or not g.grounded:
            return None
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            below = (x + dx, y - 1, z + dz)
            target = (x + dx, y, z + dz)
            if (blocks[target] == "air" and terrain_type(blocks[below]) == "solid"
                    and self._hold("crafting_table")):
                g.stop()
                g.bridge.look(shift(centre(below), dy=.47))
                g.bridge.action("use once")
                g.sensor.cache.pop(target, None)
                self.action_until = now + .4
                return None
        return None

    def _craft(self, bot, inv, now):
        if not self.rules["crafting"] or not self.game.grounded:
            return False
        g = self.game
        for recipe in recipes(inv, self.worn):
            allocation = plan(recipe, g.inventory.slots)
            if allocation is None:
                continue
            station = self._table(bot, inv, now) if recipe.table else None
            if now < self.action_until:
                return True
            if recipe.table and station is None:
                continue
            if g.bridge.craft(*allocation, recipe.outputs, recipe.quantity, station):
                self.crafted[recipe.outputs] += recipe.quantity
                g.inventory.snapshot(force=True)
                return True
        return False

    def _grounded_stand(self, block, bot):
        sensor = self.game.sensor
        x, y, z = block
        by = math.floor(bot.y)
        candidates = [(x + dx, yy, z + dz) for dx, dz in ((1, 0), (0, 1), (-1, 0), (0, -1))
                      for yy in (by, by + 1, by - 1) if abs(yy - y) <= 2]
        around = sensor.read([(sx, sy + offset, sz) for sx, sy, sz in candidates for offset in (-1, 0, 1)])
        usable = [Position(sx + .5, sy, sz + .5) for sx, sy, sz in candidates
                  if terrain_type(around[sx, sy - 1, sz]) == "solid"
                  and all(terrain_type(around[sx, sy + offset, sz]) == "air" for offset in (0, 1))]
        return min(usable, key=bot.distance, default=None)

    def _visible_face(self, bot, block):
        x, y, z = block
        faces = []
        if bot.x < x or bot.x > x + 1:
            faces.append(Position(x - .03 if bot.x < x else x + 1.03, y - .42, z + .5))
        if bot.z < z or bot.z > z + 1:
            faces.append(Position(x + .5, y - .42, z - .03 if bot.z < z else z + 1.03))
        if bot.y + 1.5 > y + 1:
            faces.append(Position(x + .5, y + .03, z + .5))
        return any(attack_line_clear(self.game.sensor, bot, face) for face in faces)

    def _start_harvest(self, bot, inv, now, portal_needed):
        wanted = set()
        if sum(inv[name] for name in LOGS) < 3 and (not self.rules["crafting"] or
                sum(inv[name] for name in BLOCKS) < 14 or not any(inv[name] for name in WEAPONS)):
            wanted.update(LOGS)
        if sum(inv[name] for name in BLOCKS) < 8:
            wanted.update(("dirt", "grass_block", "netherrack"))
        if any(inv[name] for name in PICKS) and sum(inv[name] for name in STONE) < 4:
            wanted.update(STONE_BLOCKS)
        if portal_needed and not (inv["flint_and_steel"] or inv["flint"]):
            wanted.add("gravel")
        if not wanted:
            return False
        x, y, z = cell(bot)
        cells = [(x + dx, y + dy, z + dz) for dx in range(-3, 4) for dz in range(-3, 4)
                 for dy in (0, 1, -1) if (dx or dz) and dx * dx + dz * dz <= 10]
        blocks = self.game.sensor.read(cells)
        targets = [p for p in cells if blocks[p] in wanted and self.blocked.get(p, 0) <= now
                   and self._visible_face(bot, p)]
        need_wood = not any(inv[name] for name in (*LOGS, *WEAPONS))
        def priority(p):
            return (need_wood and blocks[p] not in LOGS, bot.distance(centre(p)))
        for block in sorted(targets, key=priority)[:5]:
            stand = self._grounded_stand(block, bot)
            if stand is not None:
                material = blocks[block]
                before = inv[harvest_product(material)] + (inv["flint"] if material == "gravel" else 0)
                self.harvest = Harvest(block, material, now, stand, before)
                return True
        return False

    def _mine(self, bot, now):
        g = self.game
        goal = self.harvest
        if now - goal.started > 10:
            self.blocked[goal.block] = now + 24
            self.cancel(now)
            return False
        if goal.broken_at is not None:
            inv = counts(g.inventory.slots)
            found = inv[harvest_product(goal.name)] + (inv["flint"] if goal.name == "gravel" else 0)
            if found > goal.before or now - goal.broken_at > 2.2:
                self.cancel(now)
                return False
            x, y, z = goal.block
            cells = [(x, y + offset, z) for offset in (-1, 0, 1)]
            blocks = g.sensor.read(cells)
            if (abs(bot.y - y) < 1.25 and terrain_type(blocks[cells[0]]) == "solid"
                    and all(terrain_type(blocks[p]) == "air" for p in cells[1:])):
                target = Position(x + .5, y, z + .5)
                if bot.distance(target) > .30:
                    g.navigate(bot, target, now)
                    return True
            g.halt_movement()
            return True
        if g.miner.operation is not None:
            successes = g.miner.successes
            if g.miner.tick(now):
                return True
            if g.miner.successes > successes:
                goal.broken_at = now
                g.invalidate_route()
                return True
            self.cancel(now)
            return False
        if bot.distance(goal.stand) > .65:
            g.navigate(bot, goal.stand, now)
            return True
        if goal.name in STONE_BLOCKS:
            inv = counts(g.inventory.slots)
            pick = next((name for name in PICKS if inv[name]), None)
            if pick is None or not self._hold(pick):
                self.cancel(now)
                return False
        if g.miner.try_exact(bot, goal.block, now, stop_movement=g.stop,
                             allowed_blocks={goal.name}, extra_blocks=STONE_BLOCKS):
            return True
        self.blocked[goal.block] = now + 24
        self.cancel(now)
        return False

    def tick(self, bot, hunger, now, *, safe, portal_needed=False):
        g = self.game
        if not self.rules["enabled"] or not g.inventory.available or not safe:
            self.cancel(now)
            return False
        if now < self.action_until:
            return True
        if self.eating:
            self.eating = False
            g.stop()
            g.inventory.snapshot(force=True)
        if self.harvest:
            return self._mine(bot, now)
        inv = counts(g.inventory.slots)
        if now >= self.next_scan:
            equipment = g.bridge.query("mh_armor()").split("|")
            self.worn = {suffix: item for item in equipment for suffix in ARMOR_TYPES
                         if item.endswith("_" + suffix)}
        if self._food_or_armor(bot, hunger, inv, now) or self._craft(bot, inv, now):
            g.halt_movement()
            return True
        if now >= self.next_scan:
            self.next_scan = now + 3
            self.blocked = {p: expiry for p, expiry in self.blocked.items() if expiry > now}
            self.task = None
            entities = g.bridge.entities()
            visible = [(kind, item, pos) for kind, item, pos in entities
                       if attack_line_clear(g.sensor, bot, shift(pos, dy=-.45))]
            drops = [(kind, item, pos) for kind, item, pos in visible if kind == "item" and item in WANTED]
            animals = [(kind, item, pos) for kind, item, pos in visible if kind in {"cow", "pig", "sheep"}
                       and (sum(inv[name] for name in FOOD) < 3 or (kind == "cow" and inv["leather"] < 5))]
            need_wood = self.rules["crafting"] and not any(inv[name] for name in (*LOGS, *WEAPONS))
            if need_wood and not drops and self._start_harvest(bot, inv, now, portal_needed):
                return self._mine(bot, now)
            if drops or animals:
                self.task = min(drops or animals, key=lambda record: bot.distance(record[2]))
                self.task_until = now + 2.8
                self.refresh_at = now + .5
            elif not need_wood and self._start_harvest(bot, inv, now, portal_needed):
                return self._mine(bot, now)
        if self.task and now < self.task_until:
            kind, _, pos = self.task
            if kind != "item" and now >= self.refresh_at:
                options = [(k, n, p) for k, n, p in g.bridge.entities() if k == kind
                           and attack_line_clear(g.sensor, bot, shift(p, dy=-.45))]
                self.refresh_at = now + .5
                if not options:
                    self.cancel(now)
                    return False
                self.task = min(options, key=lambda record: pos.distance(record[2]))
                kind, _, pos = self.task
            if kind != "item" and bot.distance(pos) <= 2.4:
                if now - g.last_attack >= .85:
                    self.hold_weapon()
                    g.stop()
                    g.bridge.look(shift(pos, dy=.7))
                    g.bridge.action("attack once")
                    g.last_attack = now
            elif kind == "item" and bot.distance(pos) < .55:
                g.halt_movement()
            else:
                g.navigate(bot, pos, now)
            return True
        self.task = None
        return False
