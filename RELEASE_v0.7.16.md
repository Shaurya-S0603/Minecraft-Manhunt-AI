# v0.7.16: Generation-Aware Scheduler and Model Certification

## Main change

Older Minecraft training episodes remain in the original append-only
`runtime/movement_training/arena_episodes.jsonl` and `trials.jsonl`.
No existing model file, trial row, survival world, RCON password, or
Mine AI MCP research import needs to be deleted or re-created.

Earlier reports combined legacy point-target jumping with platform-scored
jumping and displayed lifetime percentages as though they were current
performance. V4 introduces **separate session and generation tags** for new
adaptive trials, and separately reports lifetime, recent comparable,
and latest-session performance. Its adaptive scheduler does **not** initialize
skill strength from all historical successes. It uses the latest 100 new
training attempts per course, with at most three effective observations from
older comparable records to establish an exploration prior.

## What counts as new V4 evidence

Every trial from `TRAIN_ADAPTIVE_V4.bat` carries
`"training_generation":4`, `"scheduler_version":4`, a `session_id`, and a
`split` of `train` or `validation`. Existing pre-V4 rows are not modified and
are **not** retrospectively assigned fake session IDs. Old jump records must
have `scorer_version=2` even to qualify as a small historical prior.

`curriculum_policy_v4.json` is a **new checkpoint**. The scheduler and V4
fitter use actual observed Minecraft episodes only, and Mine AI metadata is
limited to bounded course-priority hints. No Mine AI tool trace is treated as a
successful parkour jump or a pretrained movement model.

A V4 candidate is chosen using current TRAINING results only. To qualify for
live use, that candidate must then have, among other numerical checks, at
least **25 recent matching training trials**, **20 recent matching held-out
trials**, **80% held-out success**, and conservative 95% lower bounds.
A different candidate cannot win merely because it looks better on the held-out
set. The held-out lane is a slight variant of the generated basic arena; it is
**not an independent-world evaluation**.

When a V4 checkpoint exists, Manhunt loads only certified V4 settings for
swimming, ladder aim, and jump takeoff timing. Uncertified skills use the
original controls. Multi-block gap permission still requires sequential
validated gap 2 then gap 3, plus the existing terrain-safety checks.
Jump braking remains training-only. Old V1–V3 checkpoints remain available
on disk for diagnostics but do not override a V4 fallback.

## Launchers

- `training/launchers/TRAIN_ADAPTIVE_V4.bat`: 1,000 *total* real Minecraft
  trials across jump gaps 1/2/3, swimming, and ladder climbing. For a quick
  test, run `python -m quickstart.training_server --skills all --adaptive --budget 25`.
- `training/launchers/REFIT_V4_FROM_LOGS.bat`: refresh only V4 from saved
  V4 trials; does **not** write the old checkpoint formats. Running it before
  any V4 trials will not certify anything.
- `reports/RESEARCH_AND_MODEL_REPORT.bat`: writes the historical
  `training_summary.csv` plus **`training_current_summary.csv`**; the Markdown
  and JSON reports show recent comparable windows, latest V4 session,
  scorer/generation counts, and candidate-specific train/validation status.
- `reports/CHECK_LIVE_SKILLS.bat`: check which settings are enabled in normal
  Manhunt. `MANHUNT_LIVE_SKILLS=0` disables learned swim/climb settings.

Old V3 launcher names redirect to V4 to prevent accidental use of the
cumulative scheduler. Older nonadaptive training scripts are still provided
for compatibility; they do **not** create V4 session records.

## Installation

1. **Stop both servers** and back up the complete `runtime/` folder.
2. Extract this source-only ZIP into a **new** folder; do not overwrite the
   installation with active training logs.
3. Copy the complete previous `runtime/movement_training/`, `runtime/strategy/`,
   `runtime/server-data/` and optionally `runtime/training-server-data/` into
   the corresponding new `runtime/` locations. Keep all original JSONL rows.
4. Run `reports/RESEARCH_AND_MODEL_REPORT.bat`. With no V4 training yet,
   corrected-score history will be shown as the current comparable baseline.
5. Run a **small real trial** using
   `python -m quickstart.training_server --skills all --adaptive --budget 25`.
   Join `127.0.0.1:25566` with the signed-in Minecraft 1.21.11 client and
   allow Carpet to convert your session to its authenticated shadow player.
6. Review the report and `reports/CHECK_LIVE_SKILLS.bat`. Then run the 1,000
   physical-trial V4 launcher only after the small batch is successful.

## Limits and verification

The previous 8,775-episode summary and 388 Mine AI observations are only
**aggregate reports** in this chat. The actual local JSONL was not provided;
therefore this ZIP contains no trained checkpoint generated from those logs.
The tests use synthetic mock data to validate scoring and migration, not to
claim any in-game improvement. Live river, climbing, parkour transfer,
and exact training duration must be validated on your Minecraft server.
Private GitHub must remain unchanged; this release is chat-only.
