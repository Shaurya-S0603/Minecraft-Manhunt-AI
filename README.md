**Current release: v0.7.16.** The recommended adaptive trainer is `training/launchers/TRAIN_ADAPTIVE_V4.bat`. Unlike the older cumulative V3 scheduler, it labels each new session, weighs recent comparable trials heavily, retains every old JSONL record, and requires current held-out validation for new live settings. The old `TRAIN_ALL_SKILLS.bat` is a legacy nonadaptive batch. Reports include `training_current_summary.csv`; see [v0.7.16 release notes](RELEASE_v0.7.16.md).

**New v0.7.15:** [Adaptive Curriculum and Research-Aware Weights](RELEASE_v0.7.15.md). Optional `training/launchers/TRAIN_ADAPTIVE_V3.bat` performs 1,000 **total** physical episodes. Mine AI metadata informs bounded scheduling, not movement rewards.

# Minecraft Manhunter AI — v0.7.14 Water Traversal Hotfix

Minecraft **Java 1.21.11** · Windows · Python · Fabric/Carpet fake-player controller.

This build **does not include Parkour School** or any third-party Minecraft world. The training server creates a basic isolated practice arena. Ordinary Manhunt is unchanged.

## New in v0.7.14: stable water traversal

- Suppress continuous jump in shallow, breathable water; preserve forward movement as the bot wades onto shore.
- Stop cancelling held ascent during a vertical swim waypoint; apply switching hysteresis when submerged.
- Fix surface-water waypoint arrival so slight differences in floating height do not trigger hundreds of one-step replans.
- Add a real-position swim stall watchdog (3.5s) and safe replanning; the live learned swim offset is disabled on a detected stall.
- End-of-match logs now include `swim-stalls` and `swim-mode-switches`. See `RELEASE_v0.7.14.md`.
- Offline-tested only; does not imply the bot has already passed a real Minecraft river or ocean test.

## New in v0.7.13: escape empty-route deadlocks without blind movement

- An A* scan can visit many safe cells but return **0 steps** when none is closer to the current target (for example, behind a broad wall). After one empty scan, the next plan may take a *verified sideways detour* through previously observed, walkable cells.
- Each detour uses the existing collision and hazard checks, and attempted detour endpoints are temporarily blacklisted. The planner limits attempts to **four distinct detours per 30-second/goal region**. If nothing safe exists, it still stops.
- `zero-route`, `verified-detours`, and tactical-feedback skip counters are included in end-of-match navigation diagnostics.
- The strategy learner discards unexecutable targets and ignores separation changes if the bot itself moved less than 0.6 blocks. **Legacy v1 tactical policy scores are preserved but not trusted.** Verified feedback saves as `runtime/strategy/tactical_policy_hunter_v2.json` or `tactical_policy_runner_v2.json`.
- Existing real movement trial policies, imported Mine AI research records, and map/world files are unchanged. Run `reports/STRATEGY_REPORT.bat` to inspect fresh v2 learning.
- This recovery is a short-horizon local detour, **not** global obstacle navigation or long-range terrain mapping. Real Minecraft validation is still required.

## Retained from v0.7.12: bounded strategic AI

- Hunter can use short, observed-velocity interception; Runner can use stable, angled escapes. Existing terrain, movement and combat guardrails remain authoritative.
- Each role learns a conservative **local separation-change** tactic score from your own matches, stored in `runtime/strategy/`.
- A safe, **optional** import tool creates an observational index of Mine AI MCP's published action traces (CC BY 4.0); **no pretrained movement weights** are included or claimed.
- Gemini 4 Argon's public Minecraft research informs goal persistence and error-recovery design, but **no public model or training trace was imported**.
- `MANHUNT_STRATEGY=0` disables these new target choices. See `RELEASE_v0.7.12.md` and `research/strategy/README.md`.

## Start here

| Goal | Launcher |
| --- | --- |
| All five basic courses (1000 real episodes/course) | `training/launchers/TRAIN_ALL_SKILLS.bat` |
| **Corrected jump diagnostics (100 each)** | **`training/launchers/TRAIN_CORRECTED_JUMPS.bat`** |
| One-, two-, three-block jumps | `training/launchers/TRAIN_JUMPING.bat` |
| Basic underwater swimming | `training/launchers/TRAIN_SWIMMING.bat` |
| Ladder climbing | `training/launchers/TRAIN_CLIMBING.bat` |
| Fit all learned parameters from recorded trials | `training/launchers/TRAIN_MODEL.bat` |
| Detailed progress/diagnostics | `reports/VIEW_REPORT.bat` |
| Inspect strategy learning | `reports/STRATEGY_REPORT.bat` |
| Import public Minecraft agent trace (research-only) | `training/launchers/IMPORT_MINEAI_TRACE.bat` |
| Manhunt, you are Runner | `manhunt/START_AS_RUNNER.bat` |
| Manhunt, you are Hunter | `manhunt/START_AS_HUNTER.bat` |
| Run offline tests | `RUN_TESTS.bat` |


## New in v0.7.11: Corrected platform scoring and experimental braking

- The jump trainer now scores **actual grounded landings anywhere within the verified landing platform**, not only near the first block's centre.
- Reports distinguish **legacy point-scored records** from corrected v2 trials, and classify overshoots, undershoots, lateral misses, missed takeoff and falling below the platform.
- Platform-aware jump timing+braking candidates are learned from **new real Minecraft trials** and saved in `runtime/movement_training/jump_policy_v2.json`. The previous 5050 trial records remain untouched for auditing.
- Run `training/launchers/TRAIN_CORRECTED_JUMPS.bat` for **100 new trials on each of the 3 gap courses**; then run `reports/VIEW_REPORT.bat`.
- Keep the old policies: corrected trials are required for new certification. **Braking is currently training-only**; tested takeoff offsets can be used after validation.
- See `RELEASE_v0.7.11.md` for installation steps and verified open-source Minecraft-completion-agent research.

## Retained from v0.7.10: live Manhunt transfer of validated swimming and climbing settings

- No extra training command is required: the all-skills trainer periodically writes `skill_policy.json` from real completed episodes. The Manhunt controller loads the latest complete snapshot when a match starts.
- **Horizontal swimming only:** the learned look-target pitch offset is applied on level swim segments with healthy air. Emergency surfacing, low air, and vertical ascent/descent always use existing safety controls.
- **Ladders only:** the learned climbing aim height is applied when a real ladder is detected in the observed nearby blocks. Vines and other climbing blocks keep their original settings until trained separately.
- Stuck recovery disables the relevant learned setting for the current match, reverting to standard controls. Training data and model files are never changed during a Manhunt game.
- `reports/CHECK_LIVE_SKILLS.bat` displays the eligibility of the actual checkpoint you installed. For urgent manual rollback, set `MANHUNT_LIVE_SKILLS=0` before launching Manhunt.
- **Do not interrupt an ongoing training session.** After its 1,000-episode courses complete, stop the training server, back up `runtime/movement_training`, then copy that directory into this new version. Start a new Manhunt round to load the completed checkpoint.
- **Offline validation only:** successful training on a basic swim or ladder arena does not guarantee transfer to wild terrain. Retain your training report for analysis.

## Training setup

1. Run `manhunt/INSTALL_SERVER_ONLY.bat` if Minecraft Fabric/Carpet is not installed yet.
2. Start `training/launchers/TRAIN_ALL_SKILLS.bat`.
3. Join **127.0.0.1:25566** with your authenticated Minecraft Java 1.21.11 account. Carpet switches your player to an AI-controllable shadow player; your client disconnects once. This is expected.
4. The trainer cycles through 3 gap courses, 1 swim course and 1 ladder course, **1000 attempts each = 5000 physical attempts**. It records true Minecraft positions. `Ctrl+C` interrupts safely.
5. The system updates its skill policies every 100 attempts and at the end. Use `reports/VIEW_REPORT.bat` after a run.

**Episodes vs epochs:** One physical episode means one actual Minecraft attempt. A model-training epoch means replaying recorded data through a learning algorithm. The current controller uses outcome-based contextual bandits, so 1000 genuine trials per course is the useful parameter, not 1000 arbitrary gradient epochs. Thousands of physical attempts are **not instant** and may take several hours; trial duration, RCON and world tick speed dominate.

You may use CLI commands instead to start a shorter experiment:

```powershell
python -m quickstart.training_server --skills all --episodes 50 --interleave
python -m quickstart.training_server --skills all --episodes 1000 --interleave
python -m quickstart.arena_report
```

## Model and reports

- Real data: `runtime/movement_training/trials.jsonl` (jump trajectories), `runtime/movement_training/arena_episodes.jsonl` (all skills).
- Fitted jump timing: `runtime/movement_training/policy.json` (live Manhunt may use verified gap/offset thresholds).
- Fitted swim/climb action parameters: `runtime/movement_training/skill_policy.json` (read-only snapshot loaded by normal Manhunt **only if** each trained skill passes >=8 eligible attempts, >=6 successes and >=75% selected-option success). Otherwise standard controls are used.
- Reports: `reports/generated/training_report.md`, `training_report.json`, `training_summary.csv`.
- Each report includes early vs recent success rates, 95% intervals, failure causes, mean attempt time, model settings and specific improvement recommendations.

See `training/README.md`, `reports/README.md` and `DIRECTORY_MAP.md`.

## Safety and scope

Training runs on **127.0.0.1:25566**, separate from normal Manhunt **127.0.0.1:25565**. The training world is generated in `runtime/training-server-data/world` and never alters `runtime/server-data` or saved Manhunt worlds. Minecraft is run with online authentication; RCON is local-only.

The release contains **no trained live checkpoints or pre-recorded gameplay results**. Policies are generated using your own game sessions. Back up `runtime/movement_training/` before updating.

**GitHub is not updated.** v0.7.14 is a chat-only experimental build; the approved GitHub version ceiling remains v0.6.
