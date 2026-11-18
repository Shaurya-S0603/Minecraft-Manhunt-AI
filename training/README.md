# Recommended V4 training workflow

Use `training/launchers/TRAIN_ADAPTIVE_V4.bat` for **1,000 total** physical Minecraft attempts distributed across the 5 built-in courses. Each run generates a new ID, appends its trials to the original JSONL and holds out every fifth attempt. No older evidence is removed. For a short smoke test: `python -m quickstart.training_server --skills all --adaptive --budget 25`.

`REFIT_V4_FROM_LOGS.bat` refits V4 **only** from already-saved V4 episodes, leaving old checkpoints untouched. Running it before your first V4 session will not produce a new certified model. `TRAIN_ADAPTIVE_V3.bat` and `REFIT_V3_FROM_LOGS.bat` are deprecated aliases that redirect to V4. Other launchers remain historical nonadaptive batch modes, and their observations are not new V4 certification evidence.

V4 uses recent per-course training outcomes and a maximum of **three effective older comparable examples** for scheduler and ranking priors. The prior contributes **zero** to live certification. New controlled settings need at least 25 recent training and 20 matching held-out observations, 80% held-out success, and conservative confidence limits. Mine AI metadata can slightly alter training priorities, but cannot supply movement rewards. Existing movement data is always preserved.

# Training

`training/launchers/` contains the Windows scripts. `arena_config.example.json` records the five default courses in generic stage format. No third-party map is included.

## Batch sizing

Training scripts default to **1000 in-game episodes per selected course**. All-skills runs 5 courses, 5000 episodes total. Jump-only runs 3 courses, 3000 total. Use `--episodes 25` or `--episodes 50` in a terminal for an early smoke test. Unlike a CPU/GPU training epoch, each in-game episode requires actual game ticks and RCON interaction. Running 5000 episodes can take hours; larger numbers do not automatically make learning faster.

The all-skills batch interleaves gap_1, gap_2, gap_3, swim_horizontal, ladder_up, repeating this order. This reduces overtraining one skill while others are never practiced.

## Real-trial learning

- `runtime/movement_training/trials.jsonl`: observed real sprint jumps and trajectories.
- `runtime/movement_training/arena_episodes.jsonl`: successes/failures, all five course names, durations and action parameters.
- `runtime/movement_training/policy.json`: safe jump takeoff-time parameters fitted from observed jumps.
- `runtime/movement_training/skill_policy.json`: separate swim-pitch and climbing aim-height bandits fitted from observed trials. Each skill compares 3 candidate control choices, including continued exploration (one trial every 10 episodes).

All three use **actual Minecraft outcomes only**. No simulation model or downloaded neural-network weights are bundled. The jump timing policy can influence live Manhunt within its safety limits. The swim/climb policy guides future training sessions but must be validated independently before applying it to normal Manhunt gameplay.

## Reports

Run `reports/VIEW_REPORT.bat`; see `reports/README.md`. These show early/recent success, confidence intervals, failure reasons, and changes worth trying. An empty report means no actual Minecraft trials have been recorded.

## Server protection

The autonomous generator only edits `runtime/training-server-data/world`; it refuses known custom-world marker files. **Do not restore an old custom training world into the new generated arena**. Preserve `runtime/server-data` and back up `runtime/movement_training` separately.
