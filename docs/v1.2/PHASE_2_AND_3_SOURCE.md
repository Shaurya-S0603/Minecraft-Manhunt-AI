# Phases 2 and 3 — Source listing

This listing shows the complete modules for the requested interfaces. Use the runnable source files and their supporting modules in the ZIP when starting the server.

## Phase 2 — Resource collection and inventory

### quickstart/hunter_v1/inventory.py

```python
"""Server-authoritative audit views and operator-controlled item handoffs."""
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import tempfile

from ..observations import validate_name

MAIN_SLOTS = 36
TOTAL_SLOTS = 41
BOT = "ManhuntBot"


@dataclass(frozen=True)
class StackView:
    slot: int
    item: str
    count: int
    vanilla_stack_limit: int


def inspect_inventory(bridge, player=BOT):
    """Read in small pages so RCON replies stay below its packet boundary."""
    player = validate_name(player)
    slots = {}
    for start in range(0, TOTAL_SLOTS, 10):
        end = min(TOTAL_SLOTS, start + 10)
        reply = bridge.query(f"mh_inventory('{player}',{start},{end})", at=False)
        if reply == "missing":
            raise ValueError(f"{player} must be online to inspect inventory")
        for record in filter(None, reply.split(";")):
            index, item, count, cap = record.split("|")
            item = StackView(int(index), item, int(count), int(cap))
            if not start <= item.slot < end or item.slot in slots or min(item.count, item.vanilla_stack_limit) < 1:
                raise ValueError("Invalid native inventory observation")
            slots[item.slot] = item
    return slots


def round_inventory_events(bridge):
    drops, stacks, transferred, verified_drops = (int(value) for value in bridge.query("mh_inventory_events()", at=False).split("|"))
    return {"single_drop_requests": drops, "stack_drop_requests": stacks,
            "verified_transferred_items": transferred, "verified_dropped_items": verified_drops}


def archive_snapshot(path, bridge, player=BOT):
    """A diagnostic mirror only. Restart persistence is vanilla playerdata."""
    path = Path(path)
    slots = inspect_inventory(bridge, player)
    payload = {"schema": 1, "player": player, "slots": [asdict(item) for item in slots.values()]}
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as stream:
        temp = Path(stream.name)
    try:
        temp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def transfer(bridge, sender, recipient, source_slot, dest_slot, count):
    """Delegate the complete validated transaction to one Scarpet server tick."""
    sender, recipient = validate_name(sender), validate_name(recipient)
    if sender.casefold() == recipient.casefold() or BOT.casefold() not in {sender.casefold(), recipient.casefold()}:
        raise ValueError("Transfer requires the bot and one distinct player")
    if (any(type(value) is not int for value in (source_slot, dest_slot, count))
            or not 0 <= source_slot < MAIN_SLOTS or not 0 <= dest_slot < MAIN_SLOTS or not 1 <= count <= 64):
        raise ValueError("Use main slots 0–35 and a quantity from 1 through 64")
    reply = bridge.query(f"mh_transfer('{sender}','{recipient}',{source_slot},{dest_slot},{count})", at=False)
    if reply == "blocked":
        raise ValueError("Transfer blocked. Check distance, dimension, source count, and empty destination")
    item, actual = reply.split("|")
    if int(actual) != count:
        raise RuntimeError("Unexpected native transfer receipt")
    return {"item": item, "count": int(actual), "sender": sender, "recipient": recipient}


def drop(bridge, slot, count):
    if type(slot) is not int or type(count) is not int or not 0 <= slot < MAIN_SLOTS or not 1 <= count <= 64:
        raise ValueError("Use a main slot from 0–35 and a quantity from 1 through 64")
    reply = bridge.query(f"mh_drop('{BOT}',{slot},{count})", at=False)
    if reply == "blocked":
        raise ValueError("Drop blocked. Check that the bot is online and has the requested items")
    item, actual = reply.split("|")
    if int(actual) != count:
        raise RuntimeError("Unexpected native drop receipt")
    return {"item": item, "count": int(actual)}
```

### quickstart/hunter_v1/supply.py

```python
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
```

### quickstart/hunter_v1/recipes.py

```python
"""Small, deterministic survival recipe catalogue. Quantities are vanilla costs."""
from collections import Counter
from dataclasses import dataclass

WOODS = ("oak", "spruce", "birch", "jungle", "acacia", "dark_oak", "mangrove", "cherry", "pale_oak")
LOGS = {wood + "_log": wood + "_planks" for wood in WOODS}
PLANKS = tuple(LOGS.values())
STONE = ("cobblestone", "cobbled_deepslate", "blackstone")
BLOCKS = ("dirt", "cobblestone", "cobbled_deepslate", "blackstone", "netherrack", *PLANKS)
FIREPROOF = frozenset({"cobblestone", "cobbled_deepslate", "blackstone", "netherrack"})
FOOD = ("cooked_beef", "cooked_porkchop", "cooked_mutton", "cooked_chicken",
        "bread", "baked_potato", "apple", "carrot", "beef", "porkchop", "mutton", "potato")
WEAPONS = tuple(f"{tier}_{tool}" for tier in ("netherite", "diamond", "iron", "stone", "golden", "wooden")
                for tool in ("sword", "axe"))
PICKS = tuple(tier + "_pickaxe" for tier in ("netherite", "diamond", "iron", "stone", "golden", "wooden"))
ARMOR_TYPES = ("boots", "leggings", "chestplate", "helmet")
ARMOR_TIER = ("netherite", "diamond", "iron", "chainmail", "golden", "leather")
PORTAL_ITEMS = ("obsidian", "flint", "iron_ingot", "flint_and_steel", "ender_pearl", "blaze_rod", "ender_eye")


@dataclass(frozen=True)
class Recipe:
    outputs: str
    quantity: int
    inputs: tuple
    table: bool = False


def counts(slots):
    inventory = Counter()
    for stack in slots.values():
        inventory[stack["id"].removeprefix("minecraft:")] += stack["count"]
    return inventory


def plan(recipe, slots):
    """Reserve exact input amounts and an already empty destination."""
    empty = next((slot for slot in range(36) if slot not in slots), None)
    if empty is None:
        return None
    used = {}
    for choices, need in recipe.inputs:
        for slot, stack in sorted(slots.items()):
            name = stack["id"].removeprefix("minecraft:")
            prior = used.get(slot, (name, 0))[1]
            if name in choices and stack["count"] > prior:
                amount = min(need, stack["count"] - prior)
                used[slot] = (name, prior + amount)
                need -= amount
                if need == 0:
                    break
        if need:
            return None
    return [(slot, item, amount) for slot, (item, amount) in used.items()], empty


def recipes(inv, worn):
    if not any(inv[name] for name in PICKS if name.startswith(("stone", "iron", "diamond", "netherite"))):
        yield Recipe("stone_pickaxe", 1, ((STONE, 3), (("stick",), 2)), True)
    if not any(inv[name] for name in WEAPONS if not name.startswith(("wooden", "golden"))):
        yield Recipe("stone_sword", 1, ((STONE, 2), (("stick",), 1)), True)
    if not any(inv[name] for name in PICKS):
        yield Recipe("wooden_pickaxe", 1, ((PLANKS, 3), (("stick",), 2)), True)
    if not any(inv[name] for name in WEAPONS):
        yield Recipe("wooden_sword", 1, ((PLANKS, 2), (("stick",), 1)), True)
    for piece, cost in zip(ARMOR_TYPES, (4, 7, 8, 5)):
        if piece not in worn and not any(inv[f"{tier}_{piece}"] for tier in ARMOR_TIER):
            yield Recipe(f"leather_{piece}", 1, ((("leather",), cost),), True)
    if not inv["flint_and_steel"]:
        yield Recipe("flint_and_steel", 1, ((("flint",), 1), (("iron_ingot",), 1)))
    if inv["stick"] < 3:
        yield Recipe("stick", 4, ((PLANKS, 2),))
    if not inv["crafting_table"]:
        yield Recipe("crafting_table", 1, ((PLANKS, 4),))
    if sum(inv[name] for name in PLANKS) < 12:
        for log, plank in LOGS.items():
            yield Recipe(plank, 4, (((log,), 1),))
```

### quickstart/hunter_v1/bridge.py

```python
"""Scarpet/RCON adapter for exact-version player sensing and inventory actions."""
import math
from pathlib import Path
import re

from ..observations import Position, parse_position, validate_name
from ..terrain import TerrainUnavailable
from .pursuit import DIMENSIONS

APP = "mh_hunter_v1"
ITEM = re.compile(r"[a-z0-9_]+")
NUMBER = re.compile(r"-?(?:\d+(?:\.\d*)?|\.\d+)")


class Bridge:
    def __init__(self, rcon, bot):
        self.rcon = rcon
        self.bot = validate_name(bot)

    def install(self, world_dir):
        directory = Path(world_dir) / "scripts"
        path = directory / f"{APP}.sc"
        if Path(world_dir).is_symlink() or directory.is_symlink() or path.is_symlink():
            raise ValueError("Refusing a symlinked Scarpet script path")
        directory.mkdir(parents=True, exist_ok=True)
        source = Path(__file__).with_name(f"{APP}.sc").read_text(encoding="utf-8")
        if path.exists():
            self.rcon.command(f"script unload {APP}")
        path.write_text(source, encoding="utf-8")
        self.rcon.command(f"script load {APP}")
        if self.query("mh_api()") != "1":
            raise RuntimeError("Hunter v1 Scarpet app did not load correctly")

    def query(self, expression, *, at=None):
        prefix = "" if at is False else f"execute at {validate_name(at) if at else self.bot} run "
        command = f"{prefix}script in {APP} run print('MHV1:' + str({expression}) + ':ENDV1')"
        response = self.rcon.command(command)
        match = re.search(r"MHV1:(.*?):ENDV1", response, flags=re.S)
        if not match:
            raise TerrainUnavailable(f"Scarpet hunter query failed: {response[:180]}")
        return match[1]

    def state(self, name):
        name = validate_name(name)
        payload = self.query(f"mh_state('{name}')")
        if payload == "missing":
            return None
        dim, mode, hunger, health, grounded, coords = payload.split("|", 5)
        if ":" not in dim:
            dim = "minecraft:" + dim
        if dim not in DIMENSIONS or not NUMBER.fullmatch(health) or not NUMBER.fullmatch(hunger):
            raise TerrainUnavailable("Unexpected player state")
        return dim, mode, float(hunger), float(health), grounded in {"1", "true"}, Position.from_tuple(parse_position(coords))

    def entities(self):
        payload = self.query("mh_entities()")
        entities = []
        for record in payload.split(";"):
            if not record:
                continue
            kind, item, coords = record.split("|", 2)
            if ITEM.fullmatch(kind) and ITEM.fullmatch(item or "none"):
                entities.append((kind, item, Position.from_tuple(parse_position(coords))))
        return entities

    def action(self, action):
        response = self.rcon.command(f"player {self.bot} {action}")
        if any(term in response.lower() for term in ("unknown", "incorrect", "no such", "could not", "failed")):
            raise TerrainUnavailable(f"Carpet {action!r} failed: {response[:120]}")

    def look(self, target):
        if not all(math.isfinite(n) for n in (target.x, target.y, target.z)):
            raise ValueError("Non-finite look target")
        self.action(f"look at {target.x:.3f} {target.y:.3f} {target.z:.3f}")

    def hold(self, slots, item):
        """Select an existing stack. Move a main inventory stack by a checked swap."""
        candidates = [slot for slot, stack in slots.items() if stack["id"] == "minecraft:" + item]
        if not candidates or not ITEM.fullmatch(item):
            return False
        slot = min(candidates)
        if slot > 8:
            dest = next((slot for slot in range(9) if slot not in slots), 8)
            if self.query(f"mh_swap('{self.bot}',{slot},{dest},'{item}')") != "ok":
                return False
            slot = dest
        self.action(f"hotbar {slot + 1}")
        return True

    def craft(self, inputs, output_slot, item, amount, table):
        if not ITEM.fullmatch(item) or any(not ITEM.fullmatch(name) for _, name, _ in inputs):
            raise ValueError("Invalid recipe item")
        args = ",".join(f"[{slot},'{name}',{count}]" for slot, name, count in inputs)
        station = "null" if table is None else "[" + ",".join(str(value) for value in table) + "]"
        return self.query(f"mh_craft('{self.bot}',[{args}],{output_slot},'{item}',{amount},{station})") == "ok"
```

### quickstart/hunter_v1/mh_hunter_v1.sc

```text
// Private, operator-only app. The Python controller supplies allowlisted recipes.
__config() -> {'scope' -> 'global'};

mh_api() -> 1;

mh_state(name) -> (
    p = player(name);
    if(p == null, return('missing'));
    join('|', [p~'dimension', p~'gamemode', p~'hunger', p~'health', p~'on_ground', str(p~'pos')])
);

_mh_record(e) -> (
    item = e~'item';
    (e~'type') + '|' + if(item != null, item:0, '') + '|' + str(e~'pos')
);

mh_entities() -> (
    drops = entity_selector('@e[type=minecraft:item,distance=..7,sort=nearest,limit=8]');
    animals = filter(entity_selector('@e[type=!minecraft:player,distance=..7,sort=nearest,limit=30]'),
        (_~'type') == 'cow' || (_~'type') == 'pig' || (_~'type') == 'chicken' || (_~'type') == 'sheep');
    join(';', map(drops, _mh_record(_))) + ';' + join(';', map(animals, _mh_record(_)))
);

mh_swap(name, from_slot, to_slot, expected) -> (
    p = player(name);
    if(p == null || from_slot < 9 || from_slot >= 36 || to_slot < 0 || to_slot > 8,
        return('blocked'));
    a = inventory_get(p, from_slot);
    b = inventory_get(p, to_slot);
    if(a == null || a:0 != expected, return('blocked'));
    inventory_set(p, to_slot, a:1, a:0, a:2);
    if(b == null, inventory_set(p, from_slot, 0),
        inventory_set(p, from_slot, b:1, b:0, b:2));
    'ok'
);

_mh_input_ok(p, row) -> (
    slot = row:0;
    stack = inventory_get(p, slot);
    slot >= 0 && slot < 36 && stack != null && stack:0 == row:1 && stack:1 >= row:2 && row:2 > 0
);

_mh_far(pos, station) -> (
    dx = pos:0 - station:0 - 0.5;
    dy = pos:1 - station:1 - 0.5;
    dz = pos:2 - station:2 - 0.5;
    dx*dx + dy*dy + dz*dz > 12.25
);

mh_craft(name, inputs, dst, output, count, station) -> (
    p = player(name);
    if(p == null || dst < 0 || dst >= 36 || count <= 0 || count > 4 ||
        inventory_get(p, dst) != null, return('blocked'));
    if(station != null && (str(block(station)) != 'crafting_table' ||
        _mh_far(p~'pos', station)), return('blocked'));
    if(length(filter(inputs, _mh_input_ok(p, _))) != length(inputs) ||
        length(filter(inputs, _:0 == dst)) != 0, return('blocked'));
    for(inputs, (
        slot = _:0;
        old = inventory_get(p, slot);
        inventory_set(p, slot, old:1 - _:2)
    ));
    inventory_set(p, dst, count, output);
    'ok'
);

global_pickups = {};
__on_player_picks_up_item(p, item) -> (
    if((p~'name') == 'ManhuntBot',
        name = item:0;
        put(global_pickups, name, if(has(global_pickups, name), global_pickups:name, 0) + item:1)
    )
);
mh_pickups() -> join('|', map(keys(global_pickups), _ + '=' + global_pickups:_));
mh_armor() -> (
    p = player('ManhuntBot');
    join('|', map(range(36,40), stack = inventory_get(p,_); if(stack == null,'-',stack:0)))
);

global_deaths = {};
__on_player_dies(p) -> (
    name = p~'name';
    put(global_deaths, name, if(has(global_deaths, name), global_deaths:name, 0) + 1)
);
mh_deaths(name) -> if(has(global_deaths, name), global_deaths:name, 0);

// Quantity changes are owned by Minecraft. Drop callbacks record requests,
// which can fire even if there is no item to drop.
global_drop_requests = 0;
global_stack_drop_requests = 0;
global_transfer_count = 0;
global_verified_drops = 0;
__on_player_drops_item(p) -> (
    if((p~'name') == 'ManhuntBot', global_drop_requests += 1)
);
__on_player_drops_stack(p) -> (
    if((p~'name') == 'ManhuntBot', global_stack_drop_requests += 1)
);
mh_inventory_events() -> join('|', [global_drop_requests, global_stack_drop_requests, global_transfer_count, global_verified_drops]);

_mh_audit_slot(p, i) -> (
    item = inventory_get(p, i);
    if(item == null, '', join('|', [i, item:0, item:1, stack_limit(item:0)]))
);

mh_inventory(name, start, end) -> (
    p = player(name);
    if(p == null, return('missing'));
    join(';', map(range(start, end), _mh_audit_slot(p, _)))
);

// A separate operator action, never called by the pursuit policy.
// Verify the receiver and capacity before moving any item; only empty slots
// are supported so there is no component-merging ambiguity.
mh_transfer(sender, recipient, src, dst, count) -> (
    a = player(sender);
    b = player(recipient);
    if(a == null || b == null || a == b || (a~'dimension') != (b~'dimension') ||
        src < 0 || src >= 36 || dst < 0 || dst >= 36 || count < 1 || count > 64 ||
        inventory_get(b, dst) != null, return('blocked'));
    p = a~'pos';
    q = b~'pos';
    dx = p:0 - q:0; dy = p:1 - q:1; dz = p:2 - q:2;
    if(dx*dx + dy*dy + dz*dz > 9, return('blocked'));
    old = inventory_get(a, src);
    if(old == null || count > old:1, return('blocked'));
    inventory_set(b, dst, count, old:0, old:2);
    received = inventory_get(b, dst);
    if(received == null || received:0 != old:0 || received:1 != count,
        inventory_set(b, dst, 0); return('blocked'));
    inventory_set(a, src, old:1 - count);
    remainder = inventory_get(a, src);
    if((count == old:1 && remainder != null) ||
        (count < old:1 && (remainder == null || remainder:0 != old:0 || remainder:1 != old:1 - count)),
        inventory_set(a, src, old:1, old:0, old:2);
        inventory_set(b, dst, 0); return('blocked'));
    if(sender == 'ManhuntBot' || recipient == 'ManhuntBot', global_transfer_count += count);
    old:0 + '|' + str(count)
);

// Use the native item toss, and keep its confirmed quantity separate from input requests.
mh_drop(name, slot, count) -> (
    p = player(name);
    if(p == null || name != 'ManhuntBot' || slot < 0 || slot >= 36 || count < 1 || count > 64,
        return('blocked'));
    stack = inventory_get(p, slot);
    if(stack == null || count > stack:1, return('blocked'));
    dropped = drop_item(p, slot, count);
    if(dropped != count, return('blocked'));
    global_verified_drops += dropped;
    stack:0 + '|' + str(dropped)
);
```

### quickstart/v8_inventory.py

```python
"""Read-only mirror of the REAL Minecraft inventory, not a second bag.

Minecraft owns pickup, stacking, crafting, dropping and transfer. The mirror
observes item-count changes; it never awards items or edits the player NBT.
"""
from __future__ import annotations
import json
import os
import re
import time
from collections import Counter
from pathlib import Path
from .observations import validate_name

FIELD_ID = re.compile(r'(?:^|,)\s*(?:id|"id")\s*:\s*"?(minecraft:[a-z0-9_./-]+)"?')
FIELD_COUNT = re.compile(r'(?:^|,)\s*(?:count|Count|"count")\s*:\s*(\d+)[bBsS]?')
FIELD_SLOT = re.compile(r'(?:^|,)\s*(?:Slot|slot|"Slot")\s*:\s*(-?\d+)[bBsS]?')


def _compound_objects(snbt: str):
    """Isolate top-level NBT compounds without breaking nested components."""
    begin = snbt.find('[')
    if begin < 0:
        raise ValueError('Minecraft did not return an inventory list')
    depth, quoted, escaped, start = 0, False, False, None
    for i in range(begin + 1, len(snbt)):
        c = snbt[i]
        if escaped:
            escaped = False
            continue
        if c == "\\" and quoted:
            escaped = True
            continue
        if c == '"':
            quoted = not quoted
            continue
        if quoted:
            continue
        if c == '{':
            if depth == 0:
                start = i
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0 and start is not None:
                yield snbt[start+1:i]
                start = None
        elif c == ']' and depth == 0:
            return


def _top_level_fields(obj: str) -> list[str]:
    """Split only commas outside quoted strings and nested NBT structures."""
    chunks, begin, depth, quoted, escaped = [], 0, 0, False, False
    for i, char in enumerate(obj):
        if escaped:
            escaped = False
            continue
        if quoted and char == "\\":
            escaped = True
            continue
        if char == '"':
            quoted = not quoted
        elif not quoted:
            if char in '[{':
                depth += 1
            elif char in ']}':
                depth -= 1
            elif char == ',' and depth == 0:
                chunks.append(obj[begin:i].strip())
                begin = i + 1
    chunks.append(obj[begin:].strip())
    return chunks


def parse_inventory(text: str, slots: int = 36) -> dict[int, dict]:
    """Parse actual main-inventory NBT; ignore armor and offhand slots."""
    if any(term in text.lower() for term in (
            "unknown command", "no player was found", "cannot modify player", "could not find")):
        raise ValueError('Cannot read Carpet player Inventory NBT')
    result = {}
    for obj in _compound_objects(text):
        top = "," + ",".join(segment for segment in _top_level_fields(obj)
                               if not segment.lstrip('"').startswith('components'))
        mslot, mid, mcount = FIELD_SLOT.search(top), FIELD_ID.search(top), FIELD_COUNT.search(top)
        if not (mslot and mid and mcount):
            continue
        slot, count = int(mslot.group(1)), int(mcount.group(1))
        if not 0 <= slot < slots:  # Armor (100+), offhand (40) are not bag slots.
            continue
        if not 1 <= count <= 99:
            raise ValueError('Invalid inventory stack count')
        if slot in result:
            raise ValueError('Duplicate inventory slot')
        result[slot] = {'id': mid.group(1), 'count': count}
    return result


def total_items(slots: dict[int, dict]) -> Counter:
    result = Counter()
    for item in slots.values():
        result[item['id']] += item['count']
    return result


def inventory_deltas(before: dict, after: dict) -> list[dict]:
    old, new = total_items(before), total_items(after)
    return [{'item': item, 'delta': new[item] - old[item],
             'kind': 'inventory_increase' if new[item] > old[item] else 'inventory_decrease',
             'source': 'inferred_from_inventory_snapshot'}
            for item in sorted(set(old) | set(new)) if new[item] != old[item]]


class InventoryMonitor:
    def __init__(self, rcon, bot: str, directory: Path, poll_seconds=2.5, clock=time.monotonic, persist=True):
        self.rcon = rcon
        self.bot = validate_name(bot)
        self.directory = Path(directory)
        self.poll_seconds = float(poll_seconds)
        self.clock = clock
        self.last_poll = -1e12
        self.slots = {}
        self.initialized = False
        self.available = None
        self.observations = 0
        self.persist = bool(persist)
        self.directory.mkdir(parents=True, exist_ok=True)

    def snapshot(self, force=False) -> list[dict]:
        now = self.clock()
        if not force and now - self.last_poll < self.poll_seconds:
            return []
        self.last_poll = now
        try:
            text = self.rcon.command(f'data get entity {self.bot} Inventory')
            slots = parse_inventory(text)
        except (ValueError, OSError) as exc:
            if self.available is not False:
                print('[INVENTORY WARNING] Native inventory unreadable; collection decisions disabled:', exc)
            self.available = False
            return []
        self.available = True
        deltas = inventory_deltas(self.slots, slots) if self.initialized else []
        self.slots = slots
        self.initialized = True
        self.observations += 1
        if deltas and self.persist:
            with self.directory.joinpath('inventory_events.jsonl').open('a', encoding='utf-8') as stream:
                for event in deltas:
                    stream.write(json.dumps({'timestamp': time.time(), 'event': event}, sort_keys=True) + '\n')
        if self.persist:
            self.save()
        return deltas

    def drop_selected_one(self) -> bool:
        """Ask Carpet to PHYSICALLY drop one item from the selected hotbar slot.

        This operation does not create an item or guarantee a recipient.
        The actual outcome is confirmed by the next inventory observation.
        Only invoke deliberately; it is never used automatically by Manhunt.
        """
        if self.available is not True:
            return False
        result = str(self.rcon.command(f'player {self.bot} drop'))
        if any(error in result.lower() for error in
               ('unknown command', 'incorrect argument', 'not allowed', 'failed')):
            return False
        self.snapshot(force=True)
        return True

    def offer_transfer(self, bot_position, receiver_position) -> bool:
        """Physical drop near receiver; Minecraft owns any eventual pickup.

        True means a drop command was accepted, NOT a completed transfer.
        Recheck the receiver's native inventory to verify completion.
        """
        if bot_position.distance(receiver_position) > 2.5:
            return False
        return self.drop_selected_one()

    def count(self, item: str) -> int:
        return total_items(self.slots).get(item, 0)

    def count_suffix(self, suffix: str) -> int:
        return sum(amount for item, amount in total_items(self.slots).items() if item.endswith(suffix))

    def save(self):
        """Atomic diagnostic snapshot; NEVER reapply an old snapshot to Minecraft."""
        target = self.directory / 'inventory_snapshot.json'
        temp = target.with_suffix('.json.tmp')
        data = {'schema': 1, 'bot': self.bot, 'observations': self.observations,
                'timestamp': time.time(), 'slots': self.slots, 'authoritative': False}
        temp.write_text(json.dumps(data, indent=2), encoding='utf-8')
        os.replace(temp, target)
```

## Phase 3 — Core Manhunter script

### quickstart/hunter_v1/director.py

```python
"""A match-level contextual bandit over legal Hunter openings."""

from .recipes import WEAPONS


class HuntDirector:
    """One decision per round so complete outcomes have clear credit.

    This changes whether provisioning may take control during the opening.
    It never issues movement, changes inventory, or bypasses safety gates.
    """
    def __init__(self, book, rules, mode, policy="learned"):
        self.book = book
        self.rules = rules
        self.mode = mode
        self.policy = policy
        self.action = None
        self.context = None
        self.learnable = False
        self.started = 0.

    def start(self, elapsed, inventory, hunger, resources_enabled):
        if self.action is not None:
            return
        self.started = elapsed
        needs_gear = hunger <= 10 or not any(inventory[name] for name in WEAPONS)
        if self.policy == "baseline" or not self.rules["enabled"]:
            self.action = "baseline"
        elif not resources_enabled or not needs_gear:
            self.action = "press"
        elif self.policy in {"press", "gear"}:
            self.action = self.policy
        else:
            readiness = "low_food" if hunger <= 10 else "unarmed"
            self.context = f"opening/{self.mode}/{readiness}"
            self.action = self.book.choose(self.context, ("press", "gear"))
            self.learnable = True
        print(f"[TACTICS] Opening: {self.action}")

    def in_opening(self, elapsed):
        return self.action is not None and elapsed - self.started < self.rules["opening_seconds"]

    def allows_supply(self, elapsed, hunger):
        """Critical hunger can always trigger the existing safe supply policy."""
        if self.action != "press" or hunger <= 8:
            return True
        return not self.in_opening(elapsed)

    def finish(self, metrics):
        if not self.learnable or metrics.result not in {"hunter", "runner"}:
            return None
        horizon = self.rules["tag_bonus_seconds"]
        time_to_tag = metrics.first_hit_s
        tag_reward = 0.0 if time_to_tag is None else .30 * max(0., 1. - time_to_tag / horizon)
        outcome = .70 if metrics.result == "hunter" else -.70
        value = round(max(-1., min(1., outcome + tag_reward - .10 * metrics.hunter_deaths)), 4)
        self.book.reward(self.context, self.action, value)
        return value


def round_score(metrics, scoring):
    if metrics.result not in {"hunter", "runner"}:
        return {}
    points = {role: scoring["win"] if metrics.result == role else scoring["loss"]
              for role in ("hunter", "runner")}
    if metrics.first_hit_s is not None:
        points["hunter"] += scoring["first_tag"]
    return points
```

### quickstart/hunter_v1/learning.py

```python
"""Bounded contextual bandit. World locations influence only re-observed portals."""
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile

SCHEMA = 1


@dataclass
class Play:
    trials: int
    value: float
    last_used: int


class Playbook:
    def __init__(self, path, rules, *, read_only=False):
        self.path = Path(path)
        self.rules = rules
        self.read_only = read_only
        self.entries = {}
        self.sequence = 0
        self.load_issue = None
        if rules["enabled"] and self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if data["schema"] != SCHEMA:
                    raise ValueError("unknown schema")
                entries = {key: Play(**value) for key, value in data["plays"].items()}
                if any(type(p.trials) is not int or p.trials < 1 or
                       type(p.last_used) is not int or p.last_used < 1 or
                       not math.isfinite(p.value) or not -1 <= p.value <= 1
                       for p in entries.values()):
                    raise ValueError("invalid play record")
                self.sequence = max((p.last_used for p in entries.values()), default=0)
                self.entries = entries
                self.trim()
            except (OSError, KeyError, TypeError, ValueError, AttributeError) as exc:
                self.load_issue = str(exc)
                self.read_only = True

    @staticmethod
    def runner_key(name):
        return hashlib.sha256(name.casefold().encode()).hexdigest()[:12]

    def choose(self, context, options):
        if not self.rules["enabled"]:
            return options[0]
        available = [(name, self.entries.get(f"{context}/{name}")) for name in options]
        if self.read_only:
            measured = [(name, play.value) for name, play in available if play is not None]
            return max(measured, key=lambda pair: pair[1])[0] if measured else options[0]
        if self.rules["exploration"] > 0:
            for name, play in available:
                if play is None:
                    return name
        total = sum(play.trials for _, play in available if play)
        def score(pair):
            _, play = pair
            if play is None:
                return 0.0
            bonus = self.rules["exploration"] * math.sqrt(math.log1p(total) / play.trials)
            return play.value + bonus
        return max(available, key=score)[0]

    def reward(self, context, option, outcome):
        if not self.rules["enabled"] or self.read_only:
            return
        self.sequence += 1
        key = f"{context}/{option}"
        play = self.entries.get(key, Play(0, 0.0, 0))
        value = max(-1.0, min(1.0, outcome))
        self.entries[key] = Play(play.trials + 1,
                                 play.value + self.rules["rate"] * (value - play.value),
                                 self.sequence)
        self.trim()

    def trim(self):
        excess = len(self.entries) - self.rules["max_entries"]
        if excess > 0:
            oldest = sorted(self.entries, key=lambda key: self.entries[key].last_used)
            for key in oldest[:excess]:
                del self.entries[key]

    def save(self):
        if not self.rules["enabled"] or self.read_only:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schema": SCHEMA, "plays": {key: vars(value) for key, value in self.entries.items()}}
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent,
                                         delete=False) as stream:
            temp = Path(stream.name)
            try:
                json.dump(payload, stream, indent=2, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
                stream.close()
                os.replace(temp, self.path)
            finally:
                temp.unlink(missing_ok=True)


class RouteMemory:
    """Keep successful and stalled local edges; the planner rechecks terrain."""
    def __init__(self, book, scope):
        self.book = book
        self.scope = scope
        self.reset()

    def reset(self, dimension=None):
        self.context = f"route/{self.scope}/{dimension}"
        self.edge = None

    @staticmethod
    def key(source, target):
        return f"{','.join(map(str, source))}>{','.join(map(str, target))}"

    def penalty(self, source, target):
        entry = self.book.entries.get(f"{self.context}/{self.key(source, target)}")
        return max(0.0, -entry.value) * .75 if entry and entry.trials >= 2 else 0.0

    def observe(self, source, target, grounded, now):
        if self.edge:
            a, b, since = self.edge
            if source == b and grounded:
                self.book.reward(self.context, self.key(a, b), 1)
                self.edge = None
            elif source == a and target == b and now - since > 2.4:
                self.book.reward(self.context, self.key(a, b), -1)
                self.edge = None
            elif target != b or (source != a and source != b):
                self.edge = None
        # Persist unusual segments and stalls. Ordinary every-block walking
        # would crowd out tactics in the bounded store without adding signal.
        if self.edge is None and target is not None and source != target:
            if sum(abs(a-b) for a, b in zip(source, target)) >= 2:
                self.edge = (source, target, now)
```

### quickstart/hunter_v1/pursuit.py

```python
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
```

### quickstart/hunter_v1/game.py

```python
"""Online round supervisor and priority loop over the existing Carpet executor."""
from dataclasses import dataclass, field
import math
import time

from ..hit_detection import APP as HIT_APP, HitDetector
from ..live_skill_policy import LiveSkillPolicy
from ..lobby import parse_score
from ..match import ManhuntMatch, command_ok
from ..movement_training import DATA_ROOT, MovementTrainer
from ..observations import validate_name
from ..results import show_match_start
from ..terrain import TerrainUnavailable
from ..v8_config import load_config
from ..v8_inventory import InventoryMonitor
from .bridge import Bridge
from .director import HuntDirector, round_score
from .inventory import archive_snapshot, round_inventory_events
from .recipes import counts
from .learning import Playbook, RouteMemory
from .pursuit import Compass, Pursuit
from .supply import Supply, cell
from .traverse import Builder, Climber, Portals

DEATHS = "mh_v1_deaths"
ADVANCEMENTS = (
    ("dragon", "minecraft:end/kill_dragon"),
    ("end", "minecraft:end/root"),
    ("stronghold", "minecraft:story/follow_ender_eye"),
    ("nether", "minecraft:nether/root"),
)


@dataclass
class Metrics:
    result: str = "aborted"
    reason: str = "interrupted"
    duration_s: float = 0.
    first_hit_s: float | None = None
    blocks_traveled: float = 0.
    min_visible_separation: float | None = None
    runner_stage: str = "overworld"
    hunter_deaths: int = 0
    respawns: int = 0
    blocks_placed: int = 0
    bridges_crossed: int = 0
    climbs_completed: int = 0
    portal_transitions: int = 0
    navigation_plans: int = 0
    terrain_failures: int = 0
    items_picked_up: dict | None = None
    items_crafted: dict = field(default_factory=dict)
    inventory_events: dict = field(default_factory=dict)
    human_role: str = "runner"
    opening_policy: str = "learned"
    opening: str | None = None
    opening_context: str | None = None
    opening_reward: float | None = None
    points: dict = field(default_factory=dict)


class HunterGame(ManhuntMatch):
    def __init__(self, rcon, settings, world_dir, data_dir, scope, *, runner=None, held_out=False, policy="learned"):
        old_config = load_config()
        old_config["inventory"]["enabled"] = False
        rules = settings["game"]
        super().__init__(rcon, "runner", rules["head_start_seconds"],
                         rules["time_limit_seconds"], old_config)
        self.settings = settings
        self.world_dir = world_dir
        self.data_dir = data_dir
        self.requested_runner = validate_name(runner) if runner else None
        self.water.rescue_effect = False
        # Consume certified physical settings from the existing trainer, without
        # updating its checkpoint or enabling its exploratory match mode.
        skill_root = data_dir / "movement_training" if held_out else DATA_ROOT
        self.training = MovementTrainer(root=skill_root, practice=False)
        self.training.enabled = False
        self.live_skills = LiveSkillPolicy(skill_root / "skill_policy.json")
        self.bridge = Bridge(rcon, self.bot)
        self.book = Playbook(data_dir / "playbook.json", settings["learning"], read_only=held_out)
        self.director = HuntDirector(self.book, settings["learning"], rules["win_mode"], policy)
        self.routes = RouteMemory(self.book, scope)
        self.pathfinder.edge_penalty = self.routes.penalty
        self.compass = Compass(settings["tracking"])
        self.builder = Builder(self)
        self.climber = Climber(self)
        self.portals = Portals(self, self.book, scope)
        self.supply = Supply(self)
        self.metrics = Metrics(opening_policy=policy)
        self.grounded = False
        self.last_dim = None
        self.previous = None
        self.warning_at = -math.inf
        self.initial_spawn = None
        self.respawn_at = None
        self.respawn_deadline = None
        self.stage_at = -math.inf
        self.portal_search = None
        self.portal_search_since = None
        self.hunter_deaths = 0
        self.bot_missing_since = None

    def wait_for_player(self):
        if not self.requested_runner:
            return super().wait_for_player()
        print(f"[JOIN] Waiting for human runner {self.requested_runner} on the local server")
        while self.requested_runner not in self.players():
            time.sleep(1)
        self.player = self.requested_runner

    def _death(self, name):
        response = self.rcon.command(f"scoreboard players get {name} {DEATHS}")
        score = parse_score(response)
        event_count = int(self.bridge.query(f"mh_deaths('{validate_name(name)}')", at=False))
        # Carpet can remove a fake player's connection before the vanilla
        # scoreboard criterion has incremented. Keep the native event too.
        return max(score or 0, event_count)

    def _advancement(self, advancement):
        # The query divulges progress only. Coordinates are handled separately.
        selector = f"@a[name={self.player},advancements={{{advancement}=true}},limit=1]"
        response = self.rcon.command(f"execute if entity {selector}")
        if "Test passed" in response:
            return True
        if "Test failed" in response:
            return False
        raise RuntimeError(f"Unexpected advancement response: {response[:140]}")

    def _progress(self, now):
        if now < self.stage_at:
            return
        self.stage_at = now + 2.5
        for stage, advancement in ADVANCEMENTS:
            if self._advancement(advancement):
                order = ("overworld", "nether", "stronghold", "end", "dragon")
                if order.index(stage) > order.index(self.metrics.runner_stage):
                    self.metrics.runner_stage = stage
                break

    def _stop_controls(self):
        self.builder.cancel()
        self.climber.cancel()
        self.supply.cancel(time.monotonic())
        self.miner.stop()
        self.stop()
        self.invalidate_route()

    def _switch_dimension(self, new_dim):
        self._stop_controls()
        self.sensor.cache.clear()
        self.pathfinder.clear()
        self.navigator.clear()
        self.motion.samples.clear()
        self.water.reset()
        self.surface_goal = None
        self.airborne = False
        self.previous = None
        self.grounded = False
        self.supply.blocked.clear()
        self.pursuit.reset()
        self.compass.reset()
        self.routes.reset(new_dim)
        self.failed_routes = 0
        self.last_bot_position = None
        self.portals.next_scan = 0.
        if self.last_dim is not None:
            self.portals.crossed(self.last_dim, new_dim)
            print(f"[PORTAL] Hunter entered {new_dim}")
        self.last_dim = new_dim

    def _respawn(self, now, bot_online):
        if self.respawn_at is None:
            return False
        if self.respawn_deadline is not None:
            if bot_online:
                self.respawn_deadline = self.respawn_at = None
                self.metrics.respawns += 1
                self.last_dim = None
                self._switch_dimension(self.initial_spawn[0])
                self.inventory.initialized = False
                return False
            if now > self.respawn_deadline:
                raise RuntimeError("Carpet did not respawn the hunter. Check the server profile lookup log.")
            return True
        if now < self.respawn_at or bot_online:
            return True
        dimension, spot = self.initial_spawn
        text = self.rcon.command(f"execute in {dimension} positioned {spot.x:.3f} {spot.y:.3f} {spot.z:.3f} "
                                 f"run player {self.bot} spawn in survival")
        if not command_ok(text):
            raise RuntimeError(f"Carpet rejected hunter respawn: {text[:160]}")
        self.respawn_deadline = now + 12
        return True

    def _surface(self, bot, now):
        vertical = 0
        if self.path and self.path_index < len(self.path):
            step = self.path[self.path_index]
            if step.swimming:
                dy = step.destination.y - bot.y
                vertical = (1 if dy > .55 else -1 if dy < -.55 else 0)
        immersed = self.water.update(bot, now, stop_movement=self.stop, vertical=vertical)
        if immersed and self.water.stall_detected:
            if self.path and self.path_index < len(self.path):
                self.pathfinder.penalize(self.path[self.path_index].destination, seconds=6)
            self.invalidate_route()
            self.live_skills.disable("swim", "physical stall in water")
        if not immersed:
            self.surface_goal = None
        if immersed and self.water.head_submerged and (
                self.water.last_air < 165 or now - self.water.entered_at > 9):
            self.builder.cancel()
            self.climber.cancel()
            self.supply.cancel(now)
            self.pursuit.reset()
            if self.surface_goal is None or now - self.surface_goal_at > 2:
                self.surface_goal = (self.surface_planner.find_air(bot) or
                                     self.surface_planner.ascend_waypoint(bot))
                self.surface_goal_at = now
            if self.surface_goal:
                self.navigate(bot, self.surface_goal, now)
            else:
                self.halt_movement()
            return True
        return False

    def _set_cross_dimension_goal(self, bot, now):
        if self.portal_search_since is None:
            self.portal_search_since = now
            self.portal_search = self.compass.last_visible
        if self.portal_search and now - self.portal_search_since <= 20 and bot.distance(self.portal_search) > 1:
            self.navigate(bot, self.portal_search, now)
        else:
            self.halt_movement()

    def tick_v1(self, bot_state, runner_state, now, elapsed):
        dimension, _, hunger, _, grounded, bot = bot_state
        active_runner = (runner_state and runner_state[1] in {"survival", "adventure"}
                         and runner_state[3] > 0)
        runner_dim = runner_state[0] if active_runner else None
        runner = runner_state[-1] if active_runner and runner_dim == dimension else None
        if self.last_dim != dimension:
            self._switch_dimension(dimension)
        self.grounded = grounded
        if self.previous:
            displacement = bot.distance(self.previous)
            if displacement < 24:
                self.metrics.blocks_traveled += displacement
        self.previous = bot
        self.last_bot_position = bot
        self.motion.observe(bot, now)
        self.inventory.snapshot()
        if self._surface(bot, now):
            self.routes.reset(dimension)
            return

        if runner_dim is None:
            self._stop_controls()
            return
        guide = self.compass.observe(bot, runner, now, self.sensor)
        visible = guide.visible if guide else None
        dist = bot.distance(visible) if visible is not None else math.inf
        if visible is not None:
            old_dist = self.metrics.min_visible_separation
            self.metrics.min_visible_separation = dist if old_dist is None else min(old_dist, dist)
            self.portals.observe(dimension, bot, visible, now)
        crossed = runner_dim != dimension
        if crossed:
            self.builder.cancel()
            self.climber.cancel()
        elif self.climber.tick(bot, now) or (self.builder.job and self.builder.job.kind == "pillar"
                                              and self.builder.tick(bot, now)):
            return
        if dist <= 2.8:
            self.builder.cancel()
            self.supply.cancel(now)
            self.miner.stop()
            if now - self.last_attack >= .8:
                self.supply.hold_weapon()
                self.attack_human(bot, visible, now)
            return

        if not crossed and self.builder.tick(bot, now):
            return
        if crossed:
            self.pursuit.reset()
            self.supply.cancel(now)
            if self.portals.follow(dimension, runner_dim, bot, now):
                return
        else:
            self.portal_search = self.portal_search_since = None
            self.portals.entered = None
        rules = self.settings["resources"]
        safe_to_gather = (dist > rules["safe_distance"] and grounded and not self.water.swimming
                          and (not self.miner.operation or self.supply.harvest is not None))
        if not crossed and self.metrics.runner_stage in {"stronghold", "end"} and hunger > 12:
            safe_to_gather = False
        # Allow limited provisioning even while following a distant compass
        # bearing. Release the movement budget to the chase on every cycle.
        if self.director.action is None and guide is not None:
            inv = counts(self.inventory.slots) if self.inventory.available else None
            if inv is not None:
                self.director.start(elapsed, inv, hunger, rules["enabled"] and rules["crafting"])
        gearing_up = self.director.action == "gear" and self.director.in_opening(elapsed)
        if (guide or crossed) and elapsed % 30 >= 9 and hunger > 8 and not gearing_up:
            safe_to_gather = False
        if not crossed and not self.director.allows_supply(elapsed, hunger):
            safe_to_gather = False
        if self.supply.tick(bot, hunger, now, safe=safe_to_gather, portal_needed=crossed):
            self.routes.reset(dimension)
            self.pursuit.reset()
            return
        if crossed:
            self._set_cross_dimension_goal(bot, now)
            return
        if guide is None:
            self.pursuit.reset()
            self.halt_movement()
            return
        target = self.pursuit.goal(bot, guide, dimension, now)
        if self.climber.start(bot, target, now):
            self.pursuit.reset()
            return
        waypoint = (cell(self.path[self.path_index].destination)
                    if self.path and self.path_index < len(self.path) else None)
        self.routes.observe(cell(bot), waypoint, grounded, now)
        blocked = (self.failed_routes >= 1 and (self.detour_active or self.path_index >= len(self.path)))
        high_goal = target.y - bot.y >= 2 and math.hypot(bot.x - target.x, bot.z - target.z) < 1.8
        wet_ahead = rules["water_bridge"] and any(
            step.swimming and bot.distance(step.destination) < 1.75
            for step in self.path[self.path_index:self.path_index + 2]
        )
        if blocked or high_goal or wet_ahead:
            if self.builder.start(bot, target, now):
                self.pursuit.reset()
                return
        self.navigate(bot, target, now)

    def run_v1(self, driver=None):
        self.wait_for_player()
        self.pursuit = Pursuit(self.book, self.player)
        if self.book.load_issue:
            print(f"[LEARNING] Existing playbook was preserved. Updates disabled: {self.book.load_issue}")
        if self.settings["game"]["win_mode"] == "dragon" and self._advancement(ADVANCEMENTS[0][1]):
            raise RuntimeError("Runner already has Free the End. Start dragon mode in a fresh world.")
        self.setup_bot()
        self.inventory = InventoryMonitor(self.rcon, self.bot, self.data_dir / "inventory", poll_seconds=.7,
                                          persist=False)
        self.inventory.snapshot(force=True)
        self.bridge.install(self.world_dir)
        if (self.world_dir / "scripts" / f"{HIT_APP}.sc").exists():
            self.rcon.command(f"script unload {HIT_APP}")
        self.hit_detector = HitDetector(self.rcon, self.world_dir, self.player, self.bot)
        self.hit_detector.setup()
        self.rcon.command(f"scoreboard objectives add {DEATHS} deathCount")
        for name in (self.bot, self.player):
            self.rcon.command(f"scoreboard players set {name} {DEATHS} 0")
            self._death(name)
        initial_state = self.bridge.state(self.bot)
        if initial_state is None:
            raise RuntimeError("Hunter entity missing after setup")
        self.initial_spawn = (initial_state[0], initial_state[-1])
        if initial_state[0] != "minecraft:overworld":
            raise RuntimeError("Start the round with the runner on safe terrain in the Overworld")
        print(f"[HEAD START] {self.head_start}s. Hunter tags score after release.")
        start = None
        try:
            head_start_at = time.monotonic()
            while time.monotonic() - head_start_at < self.head_start:
                if driver:
                    driver.tick()
                time.sleep(.10)
            self.hit_detector.reset()
            show_match_start(self.rcon, self.player, "runner")
            start = time.monotonic()
            while True:
                if driver:
                    driver.tick()
                now = time.monotonic()
                elapsed = now - start
                connected = self.players()
                # Death counters remain readable after a Carpet fake player is removed.
                runner_deaths = self._death(self.player)
                hunter_deaths = self._death(self.bot)
                hit = self.hit_detector.hunter_hit("runner")
                if hit and self.metrics.first_hit_s is None:
                    self.metrics.first_hit_s = elapsed
                    if self.previous:
                        self.pursuit.finish(self.previous, 0, caught=True)
                mode = self.settings["game"]["win_mode"]
                self.metrics.hunter_deaths = hunter_deaths
                self._progress(now)
                if mode == "hit" and hit:
                    self.metrics.result, self.metrics.reason = "hunter", "confirmed_hit"
                    break
                if runner_deaths:
                    self.metrics.result = "hunter" if mode == "dragon" else "aborted"
                    self.metrics.reason = "runner_death"
                    break
                if mode == "dragon" and self.metrics.runner_stage == "dragon":
                    self.metrics.result, self.metrics.reason = "runner", "dragon_advancement"
                    break
                if self.player not in connected:
                    self.metrics.reason = "runner_disconnected"
                    break
                if elapsed >= self.survival_seconds:
                    self.metrics.result, self.metrics.reason = "runner", "timeout"
                    break
                if hunter_deaths > self.hunter_deaths:
                    self.hunter_deaths = hunter_deaths
                    self.previous = None
                    self._stop_controls()
                    if hunter_deaths > self.settings["game"]["hunter_respawns"]:
                        self.metrics.result, self.metrics.reason = "runner", "hunter_respawns_exhausted"
                        break
                    self.respawn_at = now + self.settings["game"]["respawn_seconds"]
                    print(f"[DEATH] Hunter will respawn in {self.settings['game']['respawn_seconds']}s")
                if self._respawn(now, self.bot in connected):
                    time.sleep(.18)
                    continue
                if self.bot not in connected:
                    if self.bot_missing_since is None:
                        self.bot_missing_since = now
                    if now - self.bot_missing_since < 1.5:
                        time.sleep(.15)
                        continue
                    self.metrics.reason = "hunter_disconnected"
                    break
                self.bot_missing_since = None
                try:
                    bot_state = self.bridge.state(self.bot)
                    human_state = self.bridge.state(self.player)
                    if bot_state and bot_state[3] > 0:
                        self.tick_v1(bot_state, human_state, now, elapsed)
                except TerrainUnavailable as exc:
                    self.metrics.terrain_failures += 1
                    self._stop_controls()
                    if now >= self.warning_at:
                        print("[SENSOR]", exc)
                        self.warning_at = now + 6
                    time.sleep(.15)
                delay = .055 if self.builder.active else self.movement_tick_delay()
                time.sleep(delay)
            return self.metrics
        finally:
            if start is not None:
                self.metrics.duration_s = time.monotonic() - start
            try:
                self._stop_controls()
                self.metrics.items_picked_up = self._pickups()
            except (OSError, RuntimeError, ValueError) as exc:
                print("[ROUND] Cleanup or pickup metrics unavailable:", exc)
            try:
                self.metrics.inventory_events = round_inventory_events(self.bridge)
                if self.bot in self.players():
                    archive_snapshot(self.data_dir / "inventory" / "latest.json", self.bridge, self.bot)
            except (OSError, RuntimeError, ValueError) as exc:
                print("[INVENTORY] Audit unavailable:", exc)
            self.metrics.items_crafted = dict(self.supply.crafted)
            self.metrics.blocks_placed = self.builder.placed
            self.metrics.bridges_crossed = self.builder.crossed
            self.metrics.climbs_completed = self.climber.completed
            self.metrics.portal_transitions = self.portals.transitions
            self.metrics.navigation_plans = self.path_replans
            self.metrics.terrain_failures += self.nav_failures
            self.metrics.opening = self.director.action
            self.metrics.opening_context = self.director.context
            self.metrics.opening_reward = self.director.finish(self.metrics)
            self.metrics.points = round_score(self.metrics, self.settings["scoring"])
            if self.metrics.result in {"hunter", "runner"}:
                try:
                    self.book.save()
                except OSError as exc:
                    print("[LEARNING] Could not save playbook:", exc)

    def _pickups(self):
        payload = self.bridge.query("mh_pickups()", at=False)
        return {item: int(count) for item, count in (record.split("=") for record in payload.split("|") if record)}
```

### quickstart/hunter_v1/cli.py

```python
"""Start local Manhunt, run isolated physical benchmarks, and summarize metrics."""
import argparse
from dataclasses import asdict
import json
import re
from pathlib import Path
import statistics
import sys
import time
import uuid

from ..install import MINECRAFT_VERSION, ROOT, SetupError, ensure_properties, eula_agreement, install_fabric, install_mod, java_executable
from ..launch import local_port_open, start_server, stop_server, wait_for_rcon
from ..lobby import Lobby
from ..rcon import RconClient, RconError
from .bridge import Bridge
from .inventory import BOT, drop, inspect_inventory, transfer
from ..results import component
from .game import HunterGame
from .scenarios import HUNTER_START, RUNNER, SCENARIOS, ScriptedRunner
from .settings import DEFAULT_CONFIG, load_settings

RUNTIME = ROOT / "runtime"
LIVE = RUNTIME / "hunter-v1"
BENCH = RUNTIME / "hunter-v1-benchmark"
CARPET_VERSION = "1.4.194"


def write_metrics(path, game, mode, split, seed, scenario):
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"schema": 1, "round_id": uuid.uuid4().hex, "time": int(time.time()), "mode": mode,
           "split": split, "seed": seed, "scenario": scenario, **asdict(game.metrics)}
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, sort_keys=True) + "\n")
    print(f"[RESULT] {row['result']} / {row['reason']} -- distance {row['blocks_traveled']:.1f} blocks")
    print(f"[METRICS] {path}")


def summarize(path, *, split=None, scenario=None, mode=None, policy=None):
    if not path.exists():
        raise ValueError(f"No match metrics at {path}")
    rows = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            try:
                row = json.loads(line)
                if row.get("schema") != 1:
                    raise ValueError("unsupported schema")
            except (AttributeError, ValueError) as exc:
                raise ValueError(f"Invalid metric row {line_number}: {exc}") from exc
            if ((split is None or row["split"] == split) and (scenario is None or row["scenario"] == scenario)
                    and (mode is None or row["mode"] == mode)
                    and (policy is None or row.get("opening_policy") == policy)):
                rows.append(row)
    completed = [row for row in rows if row["result"] in ("hunter", "runner")]
    tagged = [row["first_hit_s"] for row in completed if row["first_hit_s"] is not None]
    picked = [sum(row["items_picked_up"].values()) for row in completed if row["items_picked_up"] is not None]
    by_opening = {}
    for row in completed:
        action = row.get("opening") or "unassigned"
        bucket = by_opening.setdefault(action, {"rounds": 0, "hunter_wins": 0, "tags": 0})
        bucket["rounds"] += 1
        bucket["hunter_wins"] += row["result"] == "hunter"
        bucket["tags"] += row["first_hit_s"] is not None
    return {
        "openings": by_opening,
        "points": {role: sum(row.get("points", {}).get(role, 0) for row in completed)
                   for role in ("hunter", "runner")},
        "rounds": len(rows), "completed": len(completed), "aborted": len(rows) - len(completed),
        "hunter_wins": sum(row["result"] == "hunter" for row in completed),
        "hunter_win_rate": (sum(row["result"] == "hunter" for row in completed) / len(completed)
                            if completed else None),
        "blocks_placed": sum(row.get("blocks_placed", 0) for row in rows),
        "bridges_crossed": sum(row.get("bridges_crossed", 0) for row in rows),
        "climbs_completed": sum(row.get("climbs_completed", 0) for row in rows),
        "tagged_rounds": len(tagged), "median_first_hit_s": statistics.median(tagged) if tagged else None,
        "mean_blocks_traveled": (statistics.mean(row["blocks_traveled"] for row in completed) if completed else None),
        "pickup_observed_rounds": len(picked), "mean_items_picked_up": statistics.mean(picked) if picked else None,
    }


class ScenarioGame(HunterGame):
    def setup_bot(self):
        super().setup_bot()
        self.rcon.command(f"clear {self.bot}")
        p = HUNTER_START
        result = self.rcon.command(f"execute in minecraft:overworld run tp {self.bot} {p.x} {p.y} {p.z}")
        self.sensor.cache.clear()
        if "Teleported" not in result or not self.spawn_finder.verify(self.observer.position(self.bot)):
            raise RuntimeError(f"Unsafe or unavailable benchmark hunter start: {result[:135]}")


def play(args):
    settings = load_settings(args.config)
    benchmark = args.command == "scenario"
    data_dir = BENCH if benchmark else LIVE
    run_id = uuid.uuid4().hex[:12]
    server = (data_dir / "sessions" / run_id) if benchmark else (data_dir / "server")
    ports = (25567, 25577) if benchmark else (25565, 25575)
    proc = rcon = None
    if args.win_mode:
        settings["game"]["win_mode"] = args.win_mode
    if benchmark:
        settings["game"]["head_start_seconds"] = args.head_start
        settings["game"]["time_limit_seconds"] = args.seconds
        bridge_option = SCENARIOS[args.scenario].bridge_option
        if bridge_option:
            settings["resources"][bridge_option] = True
    if not args.setup_only and any(map(local_port_open, ports)):
        raise SetupError(f"Stop any prior server listening on {ports[0]} or {ports[1]}")
    overrides = {"online-mode": "false", "enforce-secure-profile": "false",
                 "level-seed": str(args.seed), "generate-structures": "false"} if benchmark else None
    java = java_executable()
    props = ensure_properties(server, game_port=ports[0], rcon_port=ports[1], overrides=overrides)
    install_fabric(server)
    install_mod("carpet", "Carpet fake players", server, version=CARPET_VERSION)
    if args.setup_only:
        print("[READY] Fabric and Carpet are ready for the next play launch.")
        return 0
    eula_agreement(server)
    try:
        proc, _ = start_server(java, server, game_port=ports[0])
        rcon = wait_for_rcon(proc, props, command_timeout=15.0 if benchmark else 4.0)
        bootlog = (server / "logs" / "latest.log").read_text(encoding="utf-8", errors="replace")
        version = re.search(r"Starting minecraft server version (\S+)", bootlog)
        if version is None or version[1] != MINECRAFT_VERSION:
            raise SetupError(f"Hunter v1 needs exactly Minecraft Java {MINECRAFT_VERSION}. Check the server launcher.")
        reply = rcon.command("carpet allowSpawningOfflinePlayers true")
        if any(term in reply.lower() for term in ("unknown", "incorrect", "failed")):
            raise SetupError(f"Carpet 1.21.11 rules unavailable: {reply[:150]}")
        rcon.command("carpet allowListingFakePlayers true")
        world = server / "world"
        identity = world / "mh_v1_world_id"
        if not identity.exists():
            identity.write_text(uuid.uuid4().hex, encoding="ascii")
        world_id = identity.read_text(encoding="ascii").strip()
        if not benchmark and len(world_id) != 32:
            raise SetupError("Invalid hunter v1 world identity file")
        lobby = Lobby(rcon)
        if not benchmark:
            lobby.setup()
            lobby.start_console()
        rounds = args.rounds if benchmark else None
        while proc.poll() is None and (rounds is None or rounds > 0):
            if benchmark:
                driver = ScriptedRunner(rcon, SCENARIOS[args.scenario])
                driver.setup()
            else:
                driver = None
            game_type = ScenarioGame if benchmark else HunterGame
            seed = args.seed if benchmark else props.get("level-seed") or None
            scope = f"bench-{args.scenario}-{seed}" if benchmark else world_id
            game = game_type(rcon, settings, server / "world", data_dir, scope,
                             runner=RUNNER if benchmark else args.runner,
                             held_out=benchmark and args.split == "held-out", policy=args.policy)
            try:
                game.run_v1(driver)
            except (OSError, ValueError, RuntimeError):
                game.metrics.result, game.metrics.reason = "aborted", "runtime_error"
                raise
            finally:
                try:
                    if driver:
                        driver.stop()
                finally:
                    write_metrics(data_dir / "rounds.jsonl", game, settings["game"]["win_mode"],
                                  args.split if benchmark else "live", seed,
                                  args.scenario if benchmark else None)
            if benchmark:
                rounds -= 1
                continue
            result = game.metrics.result
            reason = game.metrics.reason.replace("_", " ")
            points = game.metrics.points
            if points:
                rcon.command("scoreboard objectives add mh_points dummy")
                for role, value in points.items():
                    rcon.command(f"scoreboard players add {role.capitalize()} mh_points {value}")
            if game.player not in game.players():
                continue
            score = f" | Hunter +{points['hunter']}, Runner +{points['runner']}" if points else ""
            message = f"[Manhunt] {result.capitalize()} | {reason}{score}. Replay with /trigger mh_replay."
            rcon.command(f"tellraw {game.player} {component(message, 'gold')}")
            lobby.clear_pending_console()
            lobby.prepare_player(game.player)
            print("[LOBBY] R or /trigger mh_replay plays again. Q stops the server.")
            while proc.poll() is None:
                action = lobby.poll_action(game.player)
                if action == "quit":
                    return 0
                if action == "replay":
                    break
                time.sleep(.4)
        if benchmark:
            print(json.dumps(summarize(BENCH / "rounds.jsonl", split=args.split,
                                       scenario=args.scenario, mode=args.win_mode, policy=args.policy), indent=2))
        return 0
    finally:
        if rcon:
            rcon.close()
        if proc:
            stop_server(proc)


def manage_inventory(args):
    settings = load_settings(args.config)
    props = {}
    path = LIVE / "server" / "server.properties"
    for line in path.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if separator and key in {"rcon.port", "rcon.password"}:
            props[key] = value
    if not props.get("rcon.password"):
        raise ValueError("Start a live Manhunt round before inspecting inventory")
    if (args.to or args.drop) and not settings["resources"]["allow_transfers"]:
        raise ValueError("Enable resources.allow_transfers before making an operator inventory change")
    if args.to and None in (args.source_slot, args.dest_slot):
        raise ValueError("Transfer requires --source-slot and --dest-slot")
    if args.drop and (args.player != BOT or args.source_slot is None or args.dest_slot is not None):
        raise ValueError("Drop requires the bot and --source-slot")
    if not (args.to or args.drop) and (args.source_slot is not None or args.dest_slot is not None):
        raise ValueError("Slot arguments require --to or --drop")
    client = RconClient("127.0.0.1", int(props.get("rcon.port", 25575)), props["rcon.password"])
    try:
        bridge = Bridge(client, BOT)
        if args.to:
            result = transfer(bridge, args.player, args.to, args.source_slot, args.dest_slot, args.count)
        elif args.drop:
            result = drop(bridge, args.source_slot, args.count)
        else:
            result = [asdict(stack) for stack in inspect_inventory(bridge, args.player).values()]
        print(json.dumps(result, indent=2))
        return 0
    finally:
        client.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Hunter-only Manhunt v1.2.1 for Minecraft Java 1.21.11")
    sub = parser.add_subparsers(dest="command", required=True)
    live = sub.add_parser("play")
    policies = ("learned", "baseline", "press", "gear")
    live.add_argument("--runner", "--player", dest="runner", help="Minecraft username of the human runner")
    live.add_argument("--win-mode", choices=("hit", "dragon"))
    live.add_argument("--policy", choices=policies, default="learned")
    live.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    live.add_argument("--setup-only", action="store_true")
    bench = sub.add_parser("scenario")
    bench.add_argument("--scenario", choices=SCENARIOS, required=True)
    bench.add_argument("--seed", type=int, required=True)
    bench.add_argument("--rounds", type=int, default=1)
    bench.add_argument("--split", choices=("train", "held-out"), default="held-out")
    bench.add_argument("--seconds", type=int, default=45)
    bench.add_argument("--head-start", type=int, default=3)
    bench.add_argument("--win-mode", choices=("hit", "dragon"), default="hit")
    bench.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    bench.add_argument("--policy", choices=policies, default="learned")
    bench.set_defaults(setup_only=False)
    report = sub.add_parser("report")
    report.add_argument("--file", type=Path, default=BENCH / "rounds.jsonl")
    report.add_argument("--split", choices=("train", "held-out", "live"))
    report.add_argument("--scenario", choices=SCENARIOS)
    report.add_argument("--mode", choices=("hit", "dragon"))
    report.add_argument("--policy", choices=policies)
    inventory = sub.add_parser("inventory", help="Inspect or transfer inventory on the live server")
    inventory.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    inventory.add_argument("--player", default=BOT)
    action = inventory.add_mutually_exclusive_group()
    action.add_argument("--to")
    action.add_argument("--drop", action="store_true")
    inventory.add_argument("--source-slot", type=int)
    inventory.add_argument("--dest-slot", type=int)
    inventory.add_argument("--count", type=int, default=1)
    args = parser.parse_args(argv)
    if args.command == "scenario" and not (1 <= args.rounds <= 100 and 15 <= args.seconds <= 900
            and 0 <= args.head_start <= 60 and -(2**63) <= args.seed < 2**63):
        parser.error("Use 1-100 rounds, 15-900 seconds, 0-60s head start and a signed 64-bit seed")
    try:
        if args.command == "report":
            print(json.dumps(summarize(args.file, split=args.split, scenario=args.scenario,
                                       mode=args.mode, policy=args.policy), indent=2))
            return 0
        if args.command == "inventory":
            return manage_inventory(args)
        return play(args)
    except (SetupError, RconError, OSError, ValueError, RuntimeError) as exc:
        print("[ERROR]", exc, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
```

### quickstart/hunter_v1/settings.py

```python
"""Strict validation for the public hunter configuration."""
import json
from pathlib import Path

DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "config" / "hunter_v1.json"
BOUNDS = {
    "game": {
        "win_mode": ("dragon", "hit"),
        "head_start_seconds": (0, 300),
        "time_limit_seconds": (15, 21600),
        "respawn_seconds": (5, 120),
        "hunter_respawns": (0, 25),
    },
    "tracking": {
        "range_blocks": (32, 2048), "sample_seconds": (2, 30),
        "visible_blocks": (5, 32), "trail_seconds": (5, 120),
    },
    "resources": {"enabled": bool, "crafting": bool, "safe_distance": (8, 128),
                  "build": bool, "water_bridge": bool, "lava_bridge": bool,
                  "allow_transfers": bool},
    "learning": {"enabled": bool, "rate": (0.01, 1.0), "max_entries": (16, 4096),
                 "exploration": (0.0, 2.0), "opening_seconds": (2, 30),
                 "tag_bonus_seconds": (10, 300)},
    "scoring": {"win": (0, 100), "loss": (0, 100), "first_tag": (0, 100)},
}


def load_settings(path=DEFAULT_CONFIG):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Manhunt config must be a JSON object")
    defaults = {"resources": {"water_bridge": False, "allow_transfers": False},
                "learning": {"opening_seconds": 9, "tag_bonus_seconds": 45},
                "scoring": {"win": 3, "loss": 0, "first_tag": 1}}
    data.setdefault("scoring", {})
    if data.keys() != BOUNDS.keys():
        raise ValueError("Config requires game, tracking, resources, learning and scoring objects")
    game = data["game"]
    if isinstance(game, dict) and game.pop("human_role", "runner") != "runner":
        raise ValueError("The human plays Runner in this release. Remove game.human_role from your config.")
    for section, values in defaults.items():
        if isinstance(data[section], dict):
            for key, value in values.items():
                data[section].setdefault(key, value)
    for section, fields in BOUNDS.items():
        values = data[section]
        if not isinstance(values, dict) or values.keys() != fields.keys():
            raise ValueError(f"Check config keys in {section} against config/hunter_v1.json")
        for key, bounds in fields.items():
            value = values[key]
            if bounds is bool:
                valid = type(value) is bool
            elif key == "win_mode":
                valid = value in bounds
            else:
                types = (int, float) if isinstance(bounds[0], float) else (int,)
                valid = type(value) in types and bounds[0] <= value <= bounds[1]
            if not valid:
                raise ValueError(f"Invalid {section}.{key}: {value!r}")
    if data["tracking"]["trail_seconds"] < data["tracking"]["sample_seconds"]:
        raise ValueError("Trail lifetime must be at least one compass sample interval")
    return data
```

### quickstart/hit_detection.py

```python
"""Server-authoritative hit-to-win using Carpet Scarpet's damage event.

A successful hit is recorded *when damage is dealt*, not when players are
nearby, a swing animation occurs, or health decreases for unrelated reasons.
"""
from __future__ import annotations
import re
from pathlib import Path
from .observations import validate_name
from .lobby import parse_score

OBJECTIVE = 'mh_hit'
APP = 'mh_hitwatch'

class HitDetectionError(RuntimeError):
    pass

class HitDetector:
    def __init__(self, rcon, world_dir: Path, player: str, bot: str = 'ManhuntBot'):
        self.rcon = rcon
        self.world_dir = Path(world_dir)
        self.player = validate_name(player)
        self.bot = validate_name(bot)
        self.ready = False

    def script(self) -> str:
        # Validated player identifiers are safe in the generated Scarpet app.
        return f'''// Generated by Manhunter. Event-based PvP scoring: no proximity wins.
__config() -> {{'scope' -> 'global'}};
__on_player_deals_damage(attacker, amount, victim) -> (
    if (amount > 0 && victim~'type' == 'player',
        if (attacker~'name' == '{self.bot}' && victim~'name' == '{self.player}',
            scoreboard('{OBJECTIVE}', '#AI', scoreboard('{OBJECTIVE}', '#AI') + 1)
        );
        if (attacker~'name' == '{self.player}' && victim~'name' == '{self.bot}',
            scoreboard('{OBJECTIVE}', '#HUMAN', scoreboard('{OBJECTIVE}', '#HUMAN') + 1)
        )
    )
);
'''

    def setup(self):
        # Previous games may have installed objective; "already exists" is fine.
        result = self.rcon.command(f'scoreboard objectives add {OBJECTIVE} dummy')
        if any(s in result.lower() for s in ('unknown command', 'incorrect argument')):
            raise HitDetectionError('Unable to register hit scoreboard: '+result)
        path = self.world_dir / 'scripts' / f'{APP}.sc'
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_symlink() or path.parent.is_symlink():
            raise HitDetectionError('Refusing to write into a symlinked Scarpet directory')
        path.write_text(self.script(), encoding='utf-8')
        response = self.rcon.command(f'script load {APP}')
        if any(s in response.lower() for s in (
            'unknown or incomplete', 'unknown command', 'error', 'failed', 'could not', 'not found',
            'unrecognized', 'exception')):
            raise HitDetectionError('Scarpet damage listener failed to load: '+response)
        self.reset()
        self.ready = True
        print('[HIT] Scarpet damage listener loaded. Only confirmed Hunter damage wins.')

    def reset(self):
        for scorer in ('#AI', '#HUMAN'):
            response = self.rcon.command(f'scoreboard players set {scorer} {OBJECTIVE} 0')
            if any(s in response.lower() for s in ('unknown', 'incorrect argument', 'failed')):
                raise HitDetectionError('Unable to reset damage scoreboard: '+response)

    def hunter_hit(self, human_role: str) -> bool:
        if not self.ready:
            raise HitDetectionError('Damage listener is not initialized')
        scorer = '#HUMAN' if human_role == 'hunter' else '#AI'
        response = self.rcon.command(f'scoreboard players get {scorer} {OBJECTIVE}')
        score = parse_score(response)
        if score is None:
            raise HitDetectionError('Could not read damage scoreboard: '+response[:180])
        return score > 0
```

### config/hunter_v1.json

```json
{
  "game": {
    "win_mode": "dragon",
    "head_start_seconds": 20,
    "time_limit_seconds": 3600,
    "respawn_seconds": 12,
    "hunter_respawns": 5
  },
  "tracking": {
    "range_blocks": 512,
    "sample_seconds": 4,
    "visible_blocks": 24,
    "trail_seconds": 32
  },
  "resources": {
    "enabled": true,
    "crafting": true,
    "safe_distance": 22,
    "build": true,
    "water_bridge": false,
    "lava_bridge": false,
    "allow_transfers": false
  },
  "learning": {
    "enabled": true,
    "rate": 0.2,
    "max_entries": 256,
    "exploration": 0.25,
    "opening_seconds": 9,
    "tag_bonus_seconds": 45
  },
  "scoring": {
    "win": 3,
    "loss": 0,
    "first_tag": 1
  }
}
```
