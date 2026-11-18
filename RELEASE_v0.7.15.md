# Minecraft Manhunter v0.7.15 — Adaptive Curriculum and Research-Aware Weights

**Java 1.21.11 · source-only · no worlds / models / user credentials packaged · not published to GitHub.**

## Why rebuild the training scheduler?

The old launcher repeated 1,000 attempts **per course**, even when swimming and climbing were already reporting 100% and short-gap jumps were much weaker. Worse, a legacy successful trial could be confused with meaningful out-of-course skill transfer. Those labels do not constitute a general movement neural network.

V3 offers a **separate optional adaptive mode**: choose how to distribute a **total** Minecraft episode budget across jump, swim, climb courses. It penalizes uncertainty and frequent failure, limits excessive repeats of one skill, and explicitly rotates candidate controls. The old round-robin scripts remain available for compatibility.

## Recommended launchers (from root)

1. Preserve your old `runtime/` directory. Copy `runtime/server-data`, `runtime/training-server-data`, `runtime/movement_training`, and `runtime/strategy` from the old installation into a *new* v0.7.15 folder. Don't restore an old Parkour School world into the basic-course training server.
2. `training/launchers/REFIT_V3_FROM_LOGS.bat`: read-only access to your original logs + write a new v3 policy. The user-imported Mine AI evidence at `runtime/strategy/mine_ai_tools.jsonl` is used automatically; no download needed.
3. `training/launchers/TRAIN_ADAPTIVE_V3.bat`: a **total budget of 1,000 physical Minecraft episodes**, across five generated stages, with every fifth episode held out using an alternate lane/start. Requires one signed-in player joining `127.0.0.1:25566`, then Carpet shadow conversion. The main Manhunt server remains separate at `25565`.
4. `reports/RESEARCH_AND_MODEL_REPORT.bat`: inspect training and held-out attempts, V3 candidate weights, Mine AI tool breakdown and failure recommendations. Reports generated in `reports/generated/`.
5. Launch gameplay normally from `manhunt/`. V3 settings can affect live Manhunt **only when separately validated**; otherwise the previous certified settings or built-in safety controls remain in place.

Custom budget: `python -m quickstart.training_server --skills all --adaptive --budget 250 --validation-every 5`

Don't start by repeating 5,000 blind trials. Run a 50–100 attempt smoke test first. 1,000 is **one thousand physical game episodes**, not instant neural training epochs; it can take substantial real time.

## Training data and model files

- Historical jump data: `runtime/movement_training/trials.jsonl`.
- All historical/new arena episodes: `runtime/movement_training/arena_episodes.jsonl`.
- Old compatible policies: `policy.json`, `jump_policy_v2.json`, `skill_policy.json`.
- **New:** `runtime/movement_training/curriculum_policy_v3.json`, a small inspectable JSON **tabular model**, not a neural model or externally downloaded checkpoint.
- Mine AI import: `runtime/strategy/mine_ai_tools.jsonl` (imported separately from the published transcript).
- V3 scoring includes Wilson 95% lower bound, recent results, successes, time *on successful trials*, and distinct validation results. For live use: >=16 candidate train attempts, >=12 successes, >=12 separate validation attempts, >=75% validation success, and minimum confidence bounds. Failed/uncertain candidates never bypass A* or water/breathing safeguards.
- V3 held-out episodes shift the practice lane and shorten the runway. This is **same-arena variation**, not an independent transfer benchmark. Keep Parkour School out of training and use it as a separate final test when ready.
- Metadata from Mine AI never trains movement weights or certifies success. Its navigation/observation/error patterns can alter scheduler priority by at most **8%**, to inform where to collect actual Minecraft trials.

## Mine AI / Gemini research boundary

- [Mine AI MCP code](https://github.com/aibengineering/mine-ai-mcp) is MIT-licensed. The [playthrough dataset](https://huggingface.co/datasets/aibengineering/beat-the-game-minecraft) is CC BY 4.0 and reports 388 Minecraft MCP tool calls in a Minecraft 1.21.4 playthrough. The transcript gives tool requests and results, but the already-imported local metadata cannot prove parkour movement success. Source attribution required for redistribution of derived content; this ZIP contains no external transcript or proprietary model weights.
- [Gemini 4 Argon team paper](https://arxiv.org/abs/2610.22319) reports coordinated long-horizon Minecraft completion; no drop-in runnable Minecraft 1.21.11 movement weights are included here. The paper informs failure recovery and validation design only.

## Limitations

This release's code has offline unit/fixture tests and static checks. The bot's actual trials are **not executed here** because no live Carpet/Minecraft server is available in the build environment. Your existing >5,000 trials and Mine AI import are on your PC, not present in this source ZIP. The user-run refit is necessary to generate your actual new weights.

To opt out of learned live swimming/climbing: set `MANHUNT_LIVE_SKILLS=0`. Never edit policy JSON to artificially raise eligibility; the point is observed, reproducible behavior.
