# Minecraft Manhunt Hunter v1.2.1

**Minecraft Java Edition 1.21.11 · Fabric server · Carpet 1.4.194 · Python 3.10+ · Java 21**

Play as the Runner against a single Survival-mode hunter. Dragon is the default format. Set `win_mode` to `hit` for the quick first-damage format. The controller runs on the same machine as the server. A stock 1.21.11 Java client can join.

## Manhunt learning

The hunter learns whether to press or gear up during the opening, with results logged by match. You play the Runner in every live round. Use the inventory command to inspect real slots or explicitly hand off supplies. See [Phase 1 research](docs/v1.2/PHASE_1_RESEARCH.md), [Phase 2 inventory](docs/v1.2/PHASE_2_INVENTORY.md), [Phase 3 script and training](docs/v1.2/PHASE_3_MANHUNT.md), and [Phase 4 creator scripts](docs/v1.2/PHASE_4_VIDEO_CONCEPTS.md).

## Traversal update

The hunter can commit to a single flat bridge lane for up to six blocks. It checks for a reachable bank, clear headroom and enough usable blocks before starting. It places each block with normal Survival inputs, checks the block and inventory cost, then walks onto it before placing the next one. Vines and ladders have a held ascent with a checked exit onto the ledge. Pillaring stays active during the jump so a close target cannot interrupt block placement in mid-air.

## Install and play

1. Extract this ZIP into a new folder and open a terminal there. Make sure `java -version` reports Java 21 and Python is on PATH.
2. Run `python -m quickstart.hunter_v1.cli play --setup-only` to download the version-targeted Fabric launcher and verify Carpet's download checksum. First launch may download additional Mojang and Fabric runtime libraries. The controller runs from source. To rebuild the distribution ZIP, run `python build_v1.py`.
3. Run `python -m quickstart.hunter_v1.cli play --runner YourMinecraftName`. On Windows, double-click `manhunt/START_HUNTER_V1.bat` for automatic Runner selection, or pass `--runner YourMinecraftName` to it.
4. Review and accept the Minecraft EULA when prompted. Join `localhost:25565` in a Java 1.21.11 client. Start on open Overworld ground. The default head start is 20 seconds.
5. After a result, `/trigger mh_replay` or console `R` starts another round. Console `Q` or Ctrl+C stops the server. If a Runner has already completed Free the End in this world, stop the server and move its `world` folder to a backup location before starting another dragon campaign.

The normal server resides at `runtime/hunter-v1/server/`, uses authenticated human logins, and binds to localhost. It uses game port 25565 and local RCON port 25575. Stop an older Manhunt server before opening the same ports. The movement trainer is documented in [training/README.md](training/README.md). To reuse your existing movement calibration, copy the old `runtime/movement_training/` into this extraction while the old server is stopped. The hunter reads certified settings when present. With the server stopped, copy your backed-up playbook and world into the same runtime paths in this extraction. The bundled config defaults water bridging to off. If your v1.2 config selected the human Hunter role, delete the old `game.human_role` key before reusing it.

## Architecture

| Module | Role |
|---|---|
| `hunter_v1/cli.py` and `settings.py` | Install, launch, local lobby, isolated benchmarks, validated config and metrics reporting. |
| `hunter_v1/game.py` | Round objective, head start, death/respawn, progress metadata and behavior priority. |
| `hunter_v1/bridge.py` and `mh_hunter_v1.sc` | Carpet controls, read-only world/player sensing, pickup events and guarded same-tick item transactions. |
| `hunter_v1/director.py` and `inventory.py` | Opening policy, round points, inventory views, and verified handoffs. |
| `hunter_v1/pursuit.py` and `learning.py` | Bearing/LOS boundary, rolling goals, verified interception and route feedback, atomic versioned playbook. |
| `hunter_v1/supply.py` and `recipes.py` | Native food, gear, local visible gathering/mob/dropped-item objectives and a limited recipe catalogue. |
| `hunter_v1/traverse.py` | Committed bridge lanes, physical pillar placement, ladder and vine ascent, observed portals, and dimension handoff. |
| Existing `quickstart/match.py`, `pathfinding3d.py`, `terrain.py`, `swimming.py` and `jump_control.py` | Rolling 3D search, physically calibrated sprint-jumps, climbing, short detours, water and air safety. |
| `hunter_v1/scenarios.py` | Disposable fixed-seed fixtures and a scripted Survival runner. |
| `quickstart/tests/test_hunter_v1.py` | Offline checks covering information limits, learning, crafting, build guards and metrics. |

Normal action priorities are emergency air, an ongoing wall ascent or pillar jump, close melee, bridge or portal traversal, bounded provisioning, then rolling chase. Coordinates go to pursuit only from close, terrain-checked sight; the compass outside sight supplies a quantized heading. Both reuse the rolling A* planner and native movement. Runner progression uses vanilla advancements and the current dimension. The hunter uses its actual carried items and the same damage, gravity and hunger mechanics as a Survival player.

Carpet lacks a full native crafting GUI controller. For the small supported recipe list, Scarpet checks real input slots and amounts and an empty output slot before updating them in one server call. Recipes requiring a crafting table check a nearby table. Slot swaps preserve stack components. The standard 2×2 recipes produce sticks, planks, tables and flint and steel. Table recipes cover wooden and stone tools and leather armor. Harvest, pickup, placement, melee and food use are physical Minecraft actions.

## Configuration

Edit `config/hunter_v1.json` or supply `--config path/to/hunter.json`.

| Section | Options and defaults |
|---|---|
| Game | `win_mode=dragon`, `head_start_seconds=20`, `time_limit_seconds=3600`, `respawn_seconds=12`, `hunter_respawns=5`. Dragon mode ends on the Runner's Free the End advancement, Runner death, hunter respawn limit or time limit. Hit mode scores the first verified hunter damage, or the Runner wins on timeout or exhausted hunter respawns. Runner death before a hit aborts hit mode. |
| Tracking | `range_blocks=512`, `sample_seconds=4`, `visible_blocks=24`, `trail_seconds=32`. Compass-style samples use 15° headings in the current dimension. A visible Runner may be pursued precisely. Terrain checks, occlusion and policy scope still apply. This is an AI sensor, so no custom player compass item is installed. |
| Resources | `enabled=true`, `crafting=true`, `safe_distance=22`, `build=true`, `water_bridge=false`, `lava_bridge=false`, `allow_transfers=false`. The last setting enables local operator transfers and drops. Enable water bridging to prefer a checked bridge over swimming when approaching a suitable lane. Lava bridging requires a full span of carried nonflammable blocks. |
| Learning | `enabled=true`, `rate=0.20`, `max_entries=256`, `exploration=0.25`, `opening_seconds=9`, `tag_bonus_seconds=45`. Set `enabled=false` for the same controller without the playbook or `exploration=0` to prefer measured values. |
| Scoring | `win=3`, `loss=0`, `first_tag=1`. Scores are separated by role. |

Normal play uses no catch-up teleport, force-loaded tracking chunks, health buffs or free supplies. The controller places the bot at a checked start, and a confirmed death allows a delayed respawn at the same round anchor. The scripted fixture setup explicitly edits only its own disposable world and repositions the bot before play. The craft transaction is limited to cost-checked recipes and can be disabled in config.

## Learning and metrics

The live playbook is `runtime/hunter-v1/playbook.json`. Benchmark train and held-out runs use `runtime/hunter-v1-benchmark/playbook.json`. Held-out runs read it without updating it. Schema 1 maps context and action to trial count, exponentially averaged value and last-use order. Contexts include hunter opening readiness, an observed runner motion pattern, a local route edge, or a re-observed portal scoped to its world and dimension. World locations are never navigated from the playbook alone. It stores no executable code. Scores are bounded, old records are pruned and replacement is atomic. An unreadable or unfamiliar schema is preserved.

To reset a playbook, stop the associated controller and rename its `playbook.json` to a backup name. This leaves match logs and movement calibration available. To run a fresh A/B comparison, archive the benchmark JSONL and start a new series with the same held-out inputs and a configuration copy with learning switched off.

Each round appends one schema 1 row to `rounds.jsonl` in its data folder. It records the winner/reason, first verified hit time, sampled physical hunter distance, observed pickup counts, crafted items, deaths, respawns, confirmed placed blocks, completed bridge crossings and wall ascents, portal transfers, navigation failures, opening decisions, and points. Pickup counts come from Carpet's native pickup event. Crafted items are recorded separately. Aborted rounds are reported outside the completed-round win rate.

## Training and tests

```sh
python -m unittest discover -s quickstart/tests -q
python -m quickstart.hunter_v1.cli scenario --scenario turns --seed 7442 --split train --rounds 3
python -m quickstart.hunter_v1.cli scenario --scenario turns --seed 9001 --split held-out --rounds 3
python -m quickstart.hunter_v1.cli report --split held-out --scenario turns --mode hit
```

The scenario server uses local ports 25567/25577 and generates a fresh disposable world per invocation. The scripted runner is a benchmark fixture. The fixture runner and the AI Hunter use offline IDs in that isolated process. Fixtures cover straight pursuit, turns, a one-block gap, a river, ladders, vines, pillaring, supplies, dry/water/lava bridges, and a Nether portal. The `water-bridge` and `lava-bridge` fixtures enable their respective settings for that benchmark only. The physical movement trainer is available through `training/launchers/TRAIN_ADAPTIVE_V4.bat` or its documented CLI. Benchmark training updates chase tactics and route feedback, while the movement arena calibrates physical controls. [Test protocol and pass criteria](docs/v1/TESTING.md) · [Baseline review](docs/v1/BASELINE.md)

## Version details and limits

This release uses 1.21.11 Java commands, read-only player state, Carpet fake-player movement and Scarpet inventory callbacks. Examples for earlier versions often use pre-component item NBT, older equipment commands, and old gamerule names. The 1.21.11 fixtures use `minecraft:spawn_mobs` and `minecraft:advance_time`. Fabric 1.21.11 still uses its remapped mod ecosystem. Earlier 1.21.x builds, Paper/Spigot and 26.x are outside the tested target. [Mojang 1.21.11 release notes](https://www.minecraft.net/en-us/article/minecraft-java-edition-1-21-11) · [Fabric 1.21.11 notes](https://fabricmc.net/2025/12/05/12111.html) · [Carpet release](https://modrinth.com/mod/carpet)

Long pursuits use rolling local A*, so large walls and complex cave networks can still lose the trail. Automatic bridging is limited to straight, same-height lanes with a visible landing predicted from local blocks. The held ascent applies to short ladder or vine walls with a checked ledge. Portal following uses seen entrances. Autonomous Stronghold discovery and the full Nether technology chain remain future work. It does not yet support bows, shield tactics, furnaces, container looting, multi-hunter coordination or learned ambush placement. The baseline review describes references that already offer some of these features. Live physics coverage and remaining release work are recorded in [TESTING.md](docs/v1/TESTING.md).
