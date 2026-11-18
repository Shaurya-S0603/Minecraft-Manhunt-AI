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
