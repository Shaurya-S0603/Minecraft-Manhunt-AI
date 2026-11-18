# Phase 2 — Resource collection and inventory

## Resource decisions

| Resource | Acquisition | Use |
|---|---|---|
| Logs and planks | Identify an exposed log near a grounded working position. Mine with a normal Carpet attack, approach the drop, and confirm the matching item was picked up. | Planks, sticks, crafting table, starter weapons and bridge stock. |
| Dirt, grass blocks, netherrack, and stone equivalents | Gather suitable nearby blocks, using a pick for stone. Survival determines the drop. Look for cobblestone after mining stone and dirt after mining grass. | Bridging, pillars, stone tools and swords. |
| Food and leather | Walk to visible drops or use ordinary melee against nearby eligible animals when pressure allows. | Eat using native controls and craft leather armor when there is space and a table. |
| Portal supplies and useful equipment | Pick up visible resources, including weapons, armor, and portal items. Seek gravel when a portal is needed and ignition supplies are missing. | Equip useful gear and use flint plus iron to craft flint and steel. |

Provisioning maintains the existing terrain checks, proximity gate and action ownership. The opening policy can defer provisioning, and urgent hunger still follows the safe supply rules.

## Storage and stacking

Minecraft owns equipment, item counts, pickups, the crafting action, and persistence. The Python decision cache uses a dictionary keyed by native main slot, with item ID and count. Main slots **0–35** include hotbar **0–8** and backpack **9–35**. The audit additionally inspects armor **36–39** and offhand **40**. Ender chest and cursor inventory are outside the collector.

Pickup stacking follows Minecraft's component matching and item limits. The audit includes the default stack limit as metadata, usually 64, 16, or 1. Custom components remain on the native stack. A transfer takes at most 64 items and at most the verified source count. It uses a distinct nearby player and an **empty** main slot, so there is no merge ambiguity. It reuses the exact source item data.

## Events and triggers

| Event | Trigger and verification |
|---|---|
| Pickup | Carpet's native completed pickup callback records item ID and quantity for the bot. Mining confirmation now requires the expected drop, including flint as a valid gravel result. |
| Drop one / drop stack | Carpet callbacks count input requests. These are reported as requests because empty-hand drops can produce no item. A deliberate operator drop uses the server’s normal item toss and records the confirmed quantity separately. |
| Hotbar movement | The controller checks the expected source item, then swaps the existing slots within one server call. |
| Transfer | A deliberate local operator command requests a move. The server checks both players, same dimension, three-block range, available source quantity and empty destination. It verifies both sides before recording a receipt. |
| Craft | The existing server transaction checks real ingredients, output space and table proximity when required. Crafted output is recorded separately from pickup quantity. |

Operator transfers and drops are disabled by default. Enabling them is an operator choice, and the AI never offers items to its opponent automatically.

## Persistence and code

Minecraft playerdata saves native items and components between server sessions. During the round the Python cache is refreshed for decisions. On round completion the archive saves a diagnostic slot mirror as `runtime/hunter-v1/inventory/latest.json`. Benchmark runs use the benchmark runtime folder. The round event counts are appended with the match row in `rounds.jsonl`. The mirror is never loaded to replace a player's equipment.

The complete implementation and comments are in `quickstart/hunter_v1/inventory.py`, `supply.py`, `recipes.py`, `bridge.py`, and `mh_hunter_v1.sc`. See [the fenced source listing](PHASE_2_AND_3_SOURCE.md).

```powershell
python -m quickstart.hunter_v1.cli inventory --player ManhuntBot
python -m quickstart.hunter_v1.cli inventory --drop --source-slot 0 --count 1
python -m quickstart.hunter_v1.cli inventory --player ManhuntBot --to YourMinecraftName --source-slot 0 --dest-slot 17 --count 1
```
