# Minecraft Manhunter v0.7.11 — Calibrated Platform Landings

## Why this update exists

The previous training report had 0/1,010 successes on one-block gaps but 665/1,010 on three-block gaps. The original scorer required a landing within **0.72 blocks of one target coordinate**, despite the generated landing platform being several blocks long. That criterion could mark real successful jumps as failures. The previous reports cannot be relabeled confidently because the historical trajectory data does not include confirmed support/collision state for every sample.

## What's changed

1. **Platform-based landings:** A landing is successful only after an actual airborne interval followed by observed grounded movement inside the measured landing rectangle, at the same platform level. Merely flying across a target point never scores success.
2. **Failure categories:** Reports distinguish **underjump, overshoot, lateral miss, fell below platform, takeoff abort and timeout**, instead of collapsing every failure into a vague missed landing. The full jump samples remain logged locally.
3. **Braking experiments:** Jump trials rotate among no brake, a 0.6-block post-platform-start brake and a 1.5-block brake, crossed with four launch offsets. Real, supervised results are used to pick qualified candidates.
4. **New v2 policy:** `runtime/movement_training/jump_policy_v2.json` stores a separately validated, platform-scored bandit. Earlier potentially mis-scored jump logs remain intact but cannot certify new v2 launch thresholds once corrected data exists.
5. **Safer testing:** `training/launchers/TRAIN_CORRECTED_JUMPS.bat` runs 100 trials each on one-, two- and three-block gaps. The full multi-skill trainer is unchanged.
6. **Better reports:** New jump-label audit in `reports/generated/training_report.md` and additional failure categories in the CSV. Legacy and corrected success percentages must not be compared as if the measurement method stayed constant.

## Install without losing training

1. Stop training and Manhunt. Keep a backup of `runtime/server-data/`, `runtime/training-server-data/`, and most importantly `runtime/movement_training/`.
2. Extract this ZIP into a **new folder** and copy those local runtime folders into it.
3. Keep the same generated training world. This code does not remove or rebuild it if it has the generated-arena marker.
4. Run `training/launchers/TRAIN_CORRECTED_JUMPS.bat`. Join the private training server using your normal authenticated Minecraft Java 1.21.11 client, then allow Carpet shadow training to continue.
5. Run `reports/VIEW_REPORT.bat` and review `training_report.md`. Keep your full data folder for comparison.

## What the model has and hasn't learned

- v2 evaluates a **two-dimensional action choice**: jump takeoff offset and whether/when to stop forward motion after crossing the landing edge.
- A candidate requires **at least 8 recorded trials, 6 successes, and a 75% win rate** before being recommended. The corrected policy will not certify longer gaps from historical v1 scorer labels.
- Real attempts must occur in Minecraft. This release doesn't contain your local training logs or a trained v2 checkpoint. Unit tests exercise correctness, not physical jump success.
- v2 may inform live takeoff thresholds once validated; **live in-air braking remains training-only** until it has a verified transfer test.
- Swimming and climbing training and v0.7.10 live-policy integration remain in place; neither is replaced by an externally downloaded AI.

## Minecraft-completion agent research

Reviewed current source projects (no models imported):

- `https://github.com/aibengineering/mine-ai-mcp` — MIT-licensed runtime with an agent-reported Ender Dragon completion and full trace at `https://huggingface.co/datasets/aibengineering/beat-the-game-minecraft`. Uses an external LLM, not downloadable motion-policy weights. Closest to our Minecraft version (1.21.4 vs 1.21.11).
- `https://github.com/rmalde/minecraft-agent` — published Mineflayer game-agent source but depends on separately hosted Astra/JEV models, with a demonstrated pre-surveyed 1.16.5 Peaceful run. Not a standalone downloadable pretrained movement checkpoint.
- `https://arxiv.org/abs/2610.22319` — reported Gemini multi-agent Ender Dragon completion; research report, not a released pretrained parkour model.

We should study telemetry, tool-boundary design and reproducible scenario tests before attempting any code integration. These are not drop-in Carpet motor models.

## Verification

Run `RUN_TESTS.bat`. The offline test suite covers v1 compatibility, v2 geometry, false success prevention, training policy selection, and game regressions. In-game training and checkpoint effectiveness must be verified on the user's Windows server.

**Private GitHub repo remains at the user-authorized v0.6 ceiling.**
