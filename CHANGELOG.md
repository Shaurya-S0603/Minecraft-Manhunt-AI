## v0.7.16 — Generation-aware training and model certification
- Append session and generation metadata to new adaptive real Minecraft attempts.
- V4 scheduler uses recent scorer-compatible outcomes and only a bounded historical prior, rather than all cumulative rates.
- Separate V4 training and held-out validation; certification uses current candidate-specific results, never legacy episodes or Mine AI metadata.
- Fail closed to standard movement controls if the V4 checkpoint does not certify a setting; preserve all V1–V3 checkpoints.
- Report current rolling 100/500 and latest session alongside all-time historical results, without editing original JSONL.
- Add V4 Windows launchers, 11 generation/migration tests, and separate current-performance CSV.
- Source-only local release. Original private GitHub and normal world unchanged.

## v0.7.15 — Adaptive scheduler, research hints, and conservative V3 movement policies
- Adaptive total-budget physical trials and held-out stage variants.
- V3 evidence-weighted parameters, explicit train/validation separation, live fallback gates.
- Mine AI MCP observational metadata profile and detailed diagnostic report.
- All user runtime worlds and model logs are preserved.

## v0.7.14.1 — Windows report-test encoding

- Specify UTF-8 for report test reads to remove locale-dependent mojibake and a false test failure.
- No gameplay, policy, or data changes.

## v0.7.14 — Swim surface and control stability (2026-10-30)

- Preserve forward movement when entering/leaving shallow water instead of overusing Carpet global `stop`.
- Stabilize vertical swim control with surface detection and hysteresis.
- Accept nearby-height water waypoints at breathable surfaces; keep strict ground waypoints.
- Add physical water-stall detection, safe rerouting, and live swim-policy rollback.
- 11 new focused offline tests; no map, saved world, or model data included.
- GitHub remains frozen at v0.6.

## v0.7.13 — Empty-route recovery / feedback hygiene

- Add verified sideways A* detours when no observed node improves the direct goal distance.
- Add per-region exploration budget, repeated-detour exclusions, no-route counters, and navigation diagnostics.
- Skip tactical rewards on immobile bots or rejected navigation goals; preserve old tactical v1 policy data, learn fresh under v2 schema.
- Add synthetic wall, safe-path, blocked-space, exclusion, budget, and policy-migration regression tests.
- No real server sessions or trained policy snapshots included. GitHub frozen at v0.6.

# Changelog

## v0.7.12 — Bounded tactical strategy and external action-evidence index (2026-10-30)

- Maintain short tactical goals instead of reevaluating every game tick: bounded Hunter intercept and Runner angled escape choices.
- Persist separate role-specific separation-change observations to local private runtime files; original gameplay remains usable with `MANHUNT_STRATEGY=0`.
- Provide an optional **read-only, non-executing** Mine AI MCP trace-to-metadata importer, with explicit dataset attribution and confidence labels.
- Extract the architectural principles of persistent plans and observed-action verification from Mine AI MCP and Gemini 4 Argon research; no pretrained weights or external code are imported.
- Add a read-only strategy status report, tests and source documentation.
- Keep the established movement trainer and GitHub v0.6 freeze unchanged.


## v0.7.11 — Platform scoring and jump calibration (2026-10-30)

- Replace point-target jump success with confirmed airborne-to-grounded landing inside the actual platform rectangle.
- Correct per-course landing platform dimensions (different landing lengths for gaps 1–3).
- Introduce controlled midair braking experiments and a separate platform-scored v2 timing+braking bandit.
- Preserve legacy training logs, but only corrected v2 trials can certify new v2 candidate settings.
- Add scoring-version audit, differentiated failure reasons and a dedicated 300-trial diagnostic launcher.
- Research open-source Minecraft-completion runtimes and distinguish published code from hosted model weights.
- Swimming, climbing, Manhunt, safe server config and version freeze unchanged.


## v0.7.10 — Live skill transfer (2026-10-30)

- The verified swim-horizontal pitch parameter from `skill_policy.json` is now loaded for normal Manhunt, only for level underwater travel with adequate air.
- The verified ladder aim-height parameter is now loaded for ladder climbing. Vine/scaffolding control remains unchanged until appropriately trained.
- Fail-closed validation, low-air/surface safety fallbacks, per-round stall rollback, and `MANHUNT_LIVE_SKILLS=0` manual opt-out.
- Read-only policy eligibility checker in `reports/CHECK_LIVE_SKILLS.bat`.
- No new saved policies or fake trained outcomes distributed; fully backward compatible with v0.7.9 training logs and model files.
- GitHub remains frozen at user-approved v0.6.


## v0.7.9 — Basic multi-skill training and project reorganization (2026-10-30)

- Separate `manhunt/` launchers, `training/launchers/`, and `reports/`.
- Remove the installed legacy/converted Parkour School world, its metadata, catalogue, and specialized import/calibration scripts. No copy is packaged.
- Train 1000 **physical episodes per course** by default. All five built-in courses interleave for 5000 attempts total.
- Train separate outcome-based swim and climb action parameter policies alongside jump timing; checkpoints every 100 episodes and at end.
- Detailed Markdown/CSV/JSON diagnostic reports: outcome reasons, 95% confidence intervals, early vs recent comparisons, timings and actionable troubleshooting recommendations.
- Keep server data and trained real policies in private runtime dirs; no bundled synthetic checkpoint.
- Existing Manhunt game code and rule system retained. GitHub not updated.

Previous release notes are intentionally not duplicated. Original build history is available in older release archives.
