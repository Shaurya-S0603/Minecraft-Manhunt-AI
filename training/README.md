# Movement training — V4

Use `launchers/TRAIN_ADAPTIVE_V4.bat` for **1,000 total physical Minecraft attempts** across five built-in courses (gap 1/2/3, horizontal swimming and ladder ascent). Each run appends tagged session observations and reserves every fifth attempt for validation. Connect once to `127.0.0.1:25566` with your authenticated player when prompted. Carpet shadows that player. Ctrl+C stops safely.

From the project root, short and focused runs are available without additional batch files:

```powershell
python -m quickstart.training_server --skills all --adaptive --budget 25
python -m quickstart.training_server --skills jump --adaptive --budget 300
python -m quickstart.training_server --skills swim --adaptive --budget 100
python -m quickstart.training_server --skills climb --adaptive --budget 100
```

Use `--validation-every 5` explicitly if desired. Budget is shared among selected stages, not per course. Historical fixed-episode mode remains available through the CLI (`--skills jump --episodes 100 --interleave`, without `--adaptive`), but its new results are not V4 live-certification evidence. Prefer adaptive mode for current training.

`launchers/REFIT_V4_FROM_LOGS.bat` refits only V4 from saved V4 episodes; it does not rewrite older checkpoints. The modern learner uses recent comparable outcomes and a small historical prior for ranking, and current candidate-specific held-out evidence for certification. Held-out variants are in the same basic arena, not independent Parkour School transfer tests.

`runtime/movement_training/` holds all prior trials, arena episode JSONL, legacy timing/control policies and `curriculum_policy_v4.json`. Preserve the whole folder. The generator only edits the isolated training world and refuses known custom-world markers. Do not restore a Parkour School world into the training directory.

For Mine AI MCP import, drag a downloaded `transcript.jsonl` onto `launchers/IMPORT_MINEAI_TRACE.bat`. External metadata influences bounded training priorities, not movement rewards or validation. See `research/strategy/README.md` from the project root.

After training, run `reports/RESEARCH_AND_MODEL_REPORT.bat` and `reports/CHECK_LIVE_SKILLS.bat`.
