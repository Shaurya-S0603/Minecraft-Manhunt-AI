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
