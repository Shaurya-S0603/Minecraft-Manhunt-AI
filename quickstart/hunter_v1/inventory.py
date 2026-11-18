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
