# Minecraft Manhunter v0.7.10 — Live Swim + Ladder Policy Transfer

This updates only the live Hunter/Runner control path. The independent trainer, training data schema, progress logs, and saved model files from v0.7.9 remain compatible and unchanged.

## Do not disrupt an active training run

If `TRAIN_ALL_SKILLS.bat` is still running, **let it finish in the old installation**. Do not move, delete, overwrite or open its runtime data with another training process. Once it finishes, keep a backup of the complete `runtime/movement_training/` folder. Extract this ZIP into a **new** directory. Copy over `runtime/server-data/` and `runtime/movement_training/` only when the old server has stopped, never while either is running.

No new real training data, epochs or success rates are bundled in this release.

## What is connected

- On every new Manhunt round, read `runtime/movement_training/skill_policy.json` as a **snapshot**.
- Only parameters marked validated by the trainer AND independently meeting >=8 actual selected-option attempts, >=6 selected-option wins, >=75% success are accepted.
- In horizontal underwater travel, add the learned swim look-target offset (possible values -0.35, 0.0, +0.35) only while air is healthy and no emergency ascent/surface goal is active.
- On detected ladder ascents, use learned aim height (+0.45, +0.95, +1.45); do not automatically transfer ladder training to vines or scaffold.
- When the bot fails to make progress on an active swim/climb route, disable that learned parameter for the rest of the round. Movement falls back to standard controls.
- Both roles share the same learned movement settings. No saved policy or training log is written during ordinary Manhunt.

## Check which skills activate

Run `reports/CHECK_LIVE_SKILLS.bat` after copying your completed training folder. In a normal game look for `[SKILL] Live movement settings: swim=... / climb=...`. If a setting is missing or undertrained it will use standard controls.

Manual opt-out (if policy transfer misbehaves): add `set MANHUNT_LIVE_SKILLS=0` before the `python -m quickstart.launch` command in your Manhunt .bat launcher, then start a fresh match.

## Verification scope

Unit and regression tests validate data validation, loading, ladder-only and horizontal-only application, low-air/vertical fallbacks, and stagnation rollback. **A live Minecraft match has not been run in this build environment.** Model eligibility is not a guarantee of performance on unseen terrain. Review the training report before raising safety limits.

## GitHub

Do not upload v0.7.10. The connected private repository stays at the previously user-approved ceiling of v0.6.
