**v0.7.16:** New recommended workflow: `training/launchers/TRAIN_ADAPTIVE_V4.bat` (1,000 total real trials; session-aware training). Run `reports/RESEARCH_AND_MODEL_REPORT.bat` for current/rolling vs lifetime results, and `reports/CHECK_LIVE_SKILLS.bat` to inspect held-out eligibility. **Do not delete existing `runtime/` history.** Read [v0.7.16 instructions](RELEASE_v0.7.16.md).

**v0.7.15:** Run `training/launchers/REFIT_V3_FROM_LOGS.bat`, then `training/launchers/TRAIN_ADAPTIVE_V3.bat`. Read [release instructions](RELEASE_v0.7.15.md). Do not overwrite the existing `runtime/` folder.

# Start here — v0.7.14

- For movement training use `training/launchers/TRAIN_ALL_SKILLS.bat`.
- For a first smoke test without a full 5000-episode batch, run `python -m quickstart.training_server --skills all --episodes 10 --interleave` from this folder.
- Join `127.0.0.1:25566` once with your authenticated Minecraft 1.21.11 client, then let Carpet shadow your account.
- For Manhunt choose `manhunt/START_AS_RUNNER.bat` or `manhunt/START_AS_HUNTER.bat`.
- For success/failure reports run `reports/VIEW_REPORT.bat`.
- This release contains **no Parkour School world or files**. New trainer builds its own courses.

- v0.7.14 fixes a water-surface control loop. For a real test, play as Hunter and observe the bot attempting to cross water.

Details are in `README.md`, `DIRECTORY_MAP.md`, `training/README.md` and `reports/README.md`.

- New tactical planning (`MANHUNT_STRATEGY=1`, on by default) adjusts **goal coordinates only**. You can disable it via `set MANHUNT_STRATEGY=0` in Command Prompt before launching.
- Inspect learned local tactical choices using `reports/STRATEGY_REPORT.bat`.
- Research-only Mine AI MCP metadata import is explained in `research/strategy/README.md`.

## After a match with zero-route warnings

- v0.7.13 retries through verified side corridors when A* cannot improve distance to the target. An enclosed bot still refuses unsafe movement.
- The end-of-round log shows `zero-route` and `verified-detours` for debugging.
- Old `tactical_policy_*` (v1) results are retained but ignored because the bot's movement was not verified. Fresh trials go to `tactical_policy_*_v2.json` in `runtime/strategy`.
- Keep your `runtime/strategy/mine_ai_tools.jsonl` research import; it is still research-only.
- See `RELEASE_v0.7.13.md`.

## River / swimming diagnostics

- `[SWIM] Mode=+0, head_submerged=False` means shallow-water horizontal crossing; the bot should continue forward.
- `[SWIM] Mode=+1, head_submerged=True` means a submerged ascent.
- `[SWIM RECOVERY]` means no meaningful movement for 3.5 seconds, after which the blocked waypoint is temporarily excluded for replanning.
- Check final `swim-stalls` and `swim-mode-switches` counters. See `RELEASE_v0.7.14.md`.
