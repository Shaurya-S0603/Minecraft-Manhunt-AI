# Testing and troubleshooting

## Smoke test before 1000 episodes/course

```powershell
python -m quickstart.training_server --skills all --episodes 10 --interleave
python -m quickstart.arena_report
```

Join `127.0.0.1:25566` with your signed-in Minecraft Java 1.21.11 account. Carpet shadows the player after authentication. Trainer never changes `online-mode` to false.

If the fake player does not spawn, inspect Carpet rule and authenticated `shadow` log messages. Do not disable authentication on normal Manhunt.

For training world errors, stop the server, back up the training folder, and clear *only* `runtime/training-server-data` when you want to generate new lanes. Never remove your ordinary `runtime/server-data` world.

When training fails repeatedly, check `reports/generated/training_report.md` for dominant failure reasons. If a path cannot be verified, the trainer refuses to infer that it succeeded. A smooth offline simulation does not demonstrate real Minecraft movement competence.

When moving from a previous release, copy **only** `runtime/server-data` and `runtime/movement_training`; do NOT copy the previous custom training world. The new release includes no Parkour School data.

## Manhunter stops at water after v0.7.14

Check the console for `[SWIM] Mode`, `head_submerged`, and `[SWIM RECOVERY]`. A shallow-water crossing should show mode `+0` and continue moving. Deep underwater ascent may show `+1`. A 3.5-second movement stall should trigger waypoint exclusion and safe replanning, not a new fake player or world reset. End-of-round stats contain `swim-stalls` and `swim-mode-switches`. If the learned pitch interferes, set `MANHUNT_LIVE_SKILLS=0` in the same shell **before** launching a new match, then compare logs. If repeated safe replan attempts fail, supply the new log; no blind water movement is permitted.
