# v0.7.13 — Verified Local Detours and Strategy Feedback Fix

## Reported user test (v0.7.12)

Round 1: Hunter hit Runner after about 8 seconds; confirms match, chase and hit detection work on open terrain.
Round 2: Bot closed from 77.4 to 8.2 blocks, later stalled around 24.3 blocks. Repeated A* results said **0 steps, expanded 65, reached_goal=False**, while the game showed **0 stuck recoveries** and the old strategy layer continued counting failures.

The direct cause in code: ordinary bounded A* returns the empty route when every **observed reachable node** fails to improve its distance-to-goal heuristic. As long as `self.moving` is false, movement-stall recovery cannot fire. A stationary agent also previously accumulated strategy outcomes based on how the opponent moved. The exact physical obstruction is not identifiable from the log without a terrain snapshot.

## Fix

- Reuse the observed, A*-verified reachable-node graph to select a sideways or slightly backward detour when the ordinary path is empty.
- Only try a detour after an empty scan. Start with normal collision-checked route planning; do not invent unsupported blocks or teleport.
- Remember and temporarily exclude recently attempted detour endpoints. Maximum 4 detours per 30-second/goal region; after exhaustion, stop safely until the goal region or time window changes.
- Resume direct pursuit planning when a detour waypoint sequence finishes.
- Record `zero-route` and `verified-detours` at round end.
- Do not score a tactical choice if the bot moved fewer than 0.6 blocks during its observation window; discard an active choice when navigation rejects the route.
- Store new movement-verified Hunter/Runner tactical policies in separate `tactical_policy_*_v2.json` files. **Preserve but do not load** existing `tactical_policy_*.json` (v1).

## Install

1. Stop Minecraft server and back up your v0.7.12 folder.
2. Extract v0.7.13 into a NEW folder.
3. Copy your previous `runtime/server-data`, `runtime/movement_training`, and `runtime/strategy` directories into v0.7.13. This preserves worlds, trained jump/swim/climb policies, and the imported Mine AI MCP index. No external gameplay data is supplied in this ZIP.
4. Start `manhunt/START_AS_RUNNER.bat` or `manhunt/START_AS_HUNTER.bat`.
5. Test against obstacles and observe `[NAV DETOUR]` messages. Run `reports/STRATEGY_REPORT.bat` afterward.

## Boundaries and verification

This is not a global search, pathfinding neural network, or new RL checkpoint. It makes conservative attempts to move around obstacles using already-sensed Minecraft blocks. An enclosure without reachable side corridors continues to halt; no clipping or blind jumping is authorized. Prior v1 scores and untouched movement policies remain available.

Offline Python, JS, and ZIP checks cover the behavior; actual in-game obstacle recovery has **not** been verified. GitHub remains untouched.
