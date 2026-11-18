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
