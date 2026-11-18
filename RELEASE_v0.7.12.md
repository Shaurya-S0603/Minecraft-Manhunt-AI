# Minecraft Manhunter v0.7.12 — Tactical Strategy and Evidence Research

## Change summary

This is an **incremental strategic planning prototype** layered on the last working v0.7.11 movement system. It does **not** replace movement policies, integrate an external runtime, or claim to train on unpublished weights.

- **Hunter:** uses locally observed velocity for a short, capped interception goal when the runner is in range. Maximum prediction displacement: 3 blocks, and only when observation velocity is plausible. Otherwise direct pursuit.
- **Runner:** chooses between the proven escape direction and a modest lateral variation, always directed away from the observed Hunter.
- **Goal persistence:** hold tactical choice for a ~2.5-second observation window to prevent goal thrashing.
- **Evidence-based local adaptation:** record whether separation improved over each observation window. The results are saved in independent files for Hunter and Runner; this is a small online tactic selector, NOT a large language model, a full RL policy or a reliable causality estimate.
- **Game protections retained:** only 3D A*, sensor-backed terrain, safe water and climbing controls, physical hit validation and standard match outcomes issue actual movement commands. Strategy can nominate a coordinate but cannot bypass any hazard or spawn check.
- **Opt out:** set `MANHUNT_STRATEGY=0` in your Windows shell before starting a Manhunt launcher. The previous target-selection behavior remains available.

## Source research and availability

| Source | Available and verified | Used in v0.7.12 | Not available for direct integration |
| --- | --- | --- | --- |
| Mine AI MCP | MIT runtime + CC BY 4.0 recorded Minecraft 1.21.4 completion run | Architecture of observable actions, persistent outcome memory; optional safe trace importer | Trained Manhunt motor weights |
| Gemini 4 Argon Minecraft research, Oct 2026 | Public paper about four agents and long-horizon plans | Goal continuity, failures and bounded re-evaluation principles | Public game-completion model weights and complete action trace not verified |

Sources:
- https://github.com/aibengineering/mine-ai-mcp
- https://huggingface.co/datasets/aibengineering/beat-the-game-minecraft
- https://arxiv.org/abs/2610.22319

No external model executable or source code is copied into this package. The local approach is independently implemented from general design ideas.

## Optional trace import — not live-policy training

The Mine AI MCP dataset contains published tool interactions from a different task (defeating Minecraft), not recorded Manhunt sprint or jump rewards. This build deliberately does **not** treat those success/failure signals as Manhunt policy rewards.

If you separately download the CC BY 4.0 `transcript.jsonl` into a local file:

```powershell
python -m quickstart.strategy_import --input "C:\path\to\transcript.jsonl"
python -m quickstart.strategy_report
```

The source transcript cannot be downloaded from the isolated build environment. The importer keeps only safe, categorized tool names, hashed tool IDs and error flags, not raw tool output, code, prompts, coordinates, reasoning text or executable instructions. It is a research index for later manual tactic design, not a machine-learning checkpoint.

## Reports

Run `reports/STRATEGY_REPORT.bat`. Once you have played a few matches with strategy enabled, it displays how often each tactic improved separation (a proxy metric only). The policy snapshots live in:

- `runtime/strategy/tactical_policy_hunter.json`
- `runtime/strategy/tactical_policy_runner.json`

Keep `runtime/strategy/` when upgrading, as well as existing `runtime/movement_training/` and `runtime/server-data/` directories.

## Installation

1. Stop the existing v0.7.11 Manhunt session.
2. Back up your existing `runtime/server-data`, `runtime/training-server-data` and `runtime/movement_training` (plus `runtime/strategy`, if present).
3. Extract the ZIP to a fresh directory. Copy the runtime directories you wish to retain into the matching positions. Do not copy externally downloaded third-party programs into the runtime.
4. Launch Manhunt from `manhunt/START_AS_RUNNER.bat` or `manhunt/START_AS_HUNTER.bat`.
5. Watch for `[STRATEGY] Bounded tactical decisions` in the launcher logs. You can disable this layer without changing the game by setting `MANHUNT_STRATEGY=0`.
6. View the report after a few matches. Test on a duplicate world before relying on the new interception choices.

## Verification and limitations

- Offline unit and regression tests check bounding, false-velocity rejection, independent per-role saved state, old behavior when disabled, and malicious-text stripping from imported transcripts.
- A green offline suite **does not mean the strategic decisions actually improve win rates**. Only in-game comparisons with matched seeds and opponents can establish that.
- Minecraft Java 1.21.11 / Carpet support remains based on the existing v0.7.11 release; external Mine AI MCP's documented runtime targets Java 1.21.4.
- Single Manhunter bot does not gain Gemini's four-agent coordination or a Gemini 4 API integration.
- No changes to the private GitHub repository. The user-authorized ceiling remains v0.6.
