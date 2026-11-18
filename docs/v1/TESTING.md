# Verification and benchmark plan

## Offline suite

Run from the extracted project root.

```sh
python -m compileall -q quickstart
python -m unittest discover -s quickstart/tests -q
```

The offline suite requires Python. On Windows, run `RUN_TESTS.bat` from the project root. Tests cover tracker information limits, real-quantity recipe allocation, placement guards, persistence and schema migration safety, cross-dimension reset, rescue-effect suppression and metric denominators. Offline checks use simulated server responses.

## Human login and replay smoke test

1. From the project root, launch a first-hit round. Replace the example name with your Minecraft username.

   ```sh
   python -m quickstart.hunter_v1.cli play --player YourMinecraftName --win-mode hit
   ```

2. Join `localhost:25565` on Minecraft Java 1.21.11 and stand on open Overworld ground. The AI Hunter should spawn nearby and wait for the default 20-second lead to expire.
3. Run across open ground, turn behind solid cover, then let the Hunter make contact. Check that the round ends only after a hit deals damage. The console should print `hunter / confirmed_hit` and the latest row in `runtime/hunter-v1/rounds.jsonl` should contain a positive `first_hit_s`.
4. Enter `/trigger mh_replay`. Check that the server stays up and starts a new round with you as Runner. After the second result, type `Q` in the launcher console and verify the server saves and exits.

For a Dragon objective check, use a fresh world, pass `--win-mode dragon` instead, and complete the vanilla Free the End advancement as the Runner. The report should record `runner / dragon_advancement`.

## Physical suite on 1.21.11

Stop anything listening on 25567 or 25577. Use Java 21. Run one scenario per invocation; each suite starts a fresh server, generates a world with that seed, and rebuilds the same arena ahead of each round.

```sh
python -m quickstart.hunter_v1.cli scenario --scenario straight --seed 7442 --split train --rounds 3
python -m quickstart.hunter_v1.cli scenario --scenario straight --seed 9001 --split held-out --rounds 5
python -m quickstart.hunter_v1.cli scenario --scenario portal --seed 9001 --split held-out --win-mode dragon --seconds 90
python -m quickstart.hunter_v1.cli scenario --scenario bridge --seed 7442 --split held-out
python -m quickstart.hunter_v1.cli scenario --scenario water-bridge --seed 7442 --split held-out
python -m quickstart.hunter_v1.cli scenario --scenario lava-bridge --seed 7442 --split held-out
python -m quickstart.hunter_v1.cli scenario --scenario vines --seed 7442 --split held-out
python -m quickstart.hunter_v1.cli scenario --scenario ladder --seed 7442 --split held-out
python -m quickstart.hunter_v1.cli scenario --scenario pillar --seed 7442 --split held-out
python -m quickstart.hunter_v1.cli report --scenario bridge --split held-out --mode hit
```

Use disjoint seeds across train and held-out and keep the same settings for each comparison. Structure-free elevated fixtures intentionally isolate individual mechanics. For live terrain coverage, repeat the scenarios manually in generated biomes using a human Runner and inspect `runtime/hunter-v1/rounds.jsonl`. Keep lobby time and connection startup out of time-to-hit comparisons.

| Test | Proposed acceptance check |
|---|---|
| `straight`, `turns` | Confirm timed play and physical chase in five rounds each. At least four straight rounds should record verified damage; turns should never score attacks through the fixture wall. |
| `gap` | Observe a legal takeoff and landing over the one-block gap. Test two- and three-block gaps in the retained movement arena and promote settings only after held-out physical results. |
| `river`, `ladder`, `vines` | Verify native water traversal and confirm each wall ascent ends with physical footing on the ledge. Repeat river tests with low air and tight overhead clearance. |
| `supplies` | See genuine harvested/mob-drop pickups. Confirm hunger changes only after eating and recipe inputs are paid. Verify armor with the real equipment view and compare reported pickup totals with native events. |
| `bridge`, `water-bridge`, `lava-bridge` | Five placements in one lane, each validated by block identity and inventory debit. Count a crossing only once the hunter reaches the far bank. The liquid fixtures enable their respective options for the isolated benchmark. |
| `pillar` | Confirm the hunter placed at least two blocks directly below itself while jumping and resumed pursuit. |
| `portal` | Slow the runner if needed to let the hunter see the entrance. Verify that a seen doorway is approached and dimensional entry is native. Repeat with an unseen, extinguished and relit portal. Confirm no matching against raw destination coordinates across dimensions. |
| Win rules and death | In Dragon, verify Runner death, hunter death/drop/delayed rejoin, and the Runner's Free the End advancement. In Hit, verify real damage, environmental deaths and disconnect attribution separately. |
| Learning | Confirm the train file changes on verified outcomes and remains byte-identical after held-out. Run at least 20 comparable held-out rounds per condition before interpreting win rate and first-hit median. |

A fixed seed and scripted inputs improve repeatability. Minecraft tick load, mob behavior, authentication and Carpet movement can still vary. The proposed checks are pass criteria for future runs, not claims of benchmark performance.

## Release smoke tests

The test server ran Minecraft Java 1.21.11 with Fabric Loader 0.20.1 and Carpet 1.4.194.

| Check | Observed in the disposable test server |
|---|---|
| Straight chase | Two completed hit-mode rounds at seed 7442. Both ended with a native Hunter hit. Median first-hit time was 8.2 seconds and mean measured travel was 38.6 blocks. |
| Provisioning | At seed 9001, the hunter broke an oak log, picked it up, crafted four planks and four sticks, and scored a confirmed hit. An isolated inventory check verified that a short input was refused, a valid craft consumed one log, and two physical apples reached the pickup metric. |
| Portal | At seed 9001, the hunter entered the Nether after observing the approach. The first confirmed hit was 13.1 seconds into the round. The Dragon-mode fixture ended on its fixed 36-second timeout. |
| v1 dry bridge baseline | Three native block placements were confirmed against inventory consumption at seed 9001. The five-block fixture ended on timeout. |
| Death and respawn | On the disposable server, actual lethal damage produced one recorded hunter death, one delayed respawn, and resumed play. Carpet's administrative `/kill` path for fake players disconnects them. Use actual lethal damage when testing death. |

The smoke tests ran against scripted Carpet players. Human account login and a complete dragon campaign were outside this verification. These sample sizes do not establish a win-rate advantage or a learning improvement.

## v1.1 traversal smoke tests

The release candidate ran each fixture once at seed 7442 using Fabric and Carpet on Minecraft Java 1.21.11.
All tests used scripted runners and normal Survival movement and combat after fixture setup.

| Fixture | Verified traversal | First confirmed hit |
|---|---|---|
| `bridge` | Five placements confirmed and far bank reached | 9.3 s |
| `water-bridge` | Five placements confirmed and far bank reached | 8.8 s |
| `lava-bridge` | Five placements confirmed and far bank reached | 9.1 s |
| `vines` | Climbed five blocks and reached the ledge | 8.0 s |
| `ladder` | Climbed five blocks and reached the ledge | 8.1 s |
| `pillar` | 3 pillar placements confirmed | 4.8 s |
| `straight` | Flat-chase regression | 8.3 s |

Dry, water, lava, vine, and pillar mechanics also passed smoke checks at seed 9001 during development.
These fixtures validate specific movements. They do not establish pursuit reliability on natural terrain or at reduced tick rates.

## v1.2.1 Hunter-only smoke tests

The 311-test offline suite checks launcher argument rejection, old config migration, and replay using the same server and Hunter role. Five scripted first-hit rounds ran on Java 1.21.11 with Fabric and Carpet.

| Fixture | Policy | Verified server result |
|---|---|---|
| `supplies`, seed 7442 | Train, press then gear | First hits after 10.2 s and 16.4 s. Both outcomes updated the opening model. |
| `turns`, seed 9001 | Held-out, learned then baseline | First hits after 11.8 s and 11.9 s. |
| `bridge`, seed 9001 | Held-out, learned | Five confirmed placements, one completed crossing, and a hit after 12.3 s. |

The playbook checksum stayed identical across held-out rounds. The supplies rounds did not record pickups or crafting. A separate server check recorded two physical apple pickups, verified that crafting four planks consumed one log, and confirmed that an undersupplied recipe left inventory unchanged. Authenticated client login and a full Dragon campaign remain manual checks. These results cover the observed code paths with a small sample.

## Next implementation work

1. Measure traversal under lower tick rates and compound terrain such as moving observers, irregular cliffs, and flooded headroom.
2. Add collision-shape and short-region cache profiling before expanding navigation beyond the current search window.
3. Expand survival supplies with found-container access, smelting and a complete portal material chain. Keep source and consumption visible in metrics.
4. Add shield and ranged combat, plus tested ambush opportunities scoped to observed terrain. Compare learned behavior against the same policy with learning disabled.
