# v0.7.14: Water traversal / bobbing hotfix

## Observed bug

In the first v0.7.13 Runner match, entering water produced repeated `Vertical control=+0` / `+1` changes, roughly 200 small A* plans, and prolonged near-zero horizontal movement. Swimming controls kept cancelling movement while attempting to satisfy water waypoints at slightly different heights. This release corrects those controls; it does **not** claim a successful live water crossing yet.

## Changes

1. **Breathable shallow water:** water at the feet with air at the head now counts as a wading/surface state. Full-air vertical-up requests are suppressed; forward steering and existing certified swim pitch remain available.
2. **Carpet input stability:** no `/player stop` is sent for a level-water-to-land transition; vertical-input switches only stop when an existing continuous jump/sneak must actually be released. Deep-water height changes use a 1.1-second hysteresis, except immediate air safety or confirmed surface transitions.
3. **Waypoint handling:** an observed water waypoint at the surface can be accepted when reached horizontally and within 1.15 blocks vertically. Ordinary land waypoints retain strict arrival rules. Vertical swim segments no longer call `/player stop` and cancel their own ascent.
4. **Safe shallow exits:** when a verified climbing step leaves breathable water, normal single-jump traversal may operate; continuously held underwater jump remains managed by WaterSurvival.
5. **Movement watchdog:** measure actual displacement, not the number of new A* plans. After 3.5 seconds without meaningful horizontal *or legitimate upward/downward* progress, expire the blocked water waypoint for six seconds, disable the learned swim offset for this match, and request a verified replan. Never steer through unseen terrain.
6. **Diagnostics:** final round now includes water-stall count and vertical control switch count. Water messages report `head_submerged` to diagnose future water transitions.

## How to install

1. Stop the current server (use `Q` in the match lobby); back up the existing installation.
2. Extract v0.7.14 into its own new folder. **Do not overwrite the live server folder.**
3. With both servers stopped, copy `runtime/server-data` (ordinary world), `runtime/movement_training` (learned skills), `runtime/strategy` (local tactics / Mine AI index), and optionally `runtime/training-server-data` if you need to retain the isolated training world. No runtime data is bundled in this source release.
4. Run `manhunt/START_AS_HUNTER.bat` to have the Runner AI cross a river while you chase it. A shallow crossing followed by a deep-water ascent are the most useful live checks.
5. Observe `[SWIM] Mode`, `[SWIM RECOVERY]`, and the final `swim-stalls` / `swim-mode-switches` counters. Share the new console log if the swimmer remains stationary.

Normal Hunter melee-hit verification, authenticated Carpet, the protected movement-policy files, and the separate training server are unchanged. The `MANHUNT_LIVE_SKILLS=0` environment override remains available for comparing default vs learned swim pitch. This release is **offline-tested only**; actual Minecraft physics, RCON latency, and custom river/shoreline geometry require a live Windows/Fabric run.

**GitHub remains unchanged at v0.6.** Parkour School and any real world/model data are excluded from this ZIP.
