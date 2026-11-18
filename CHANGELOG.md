# Release history

## Manhunt Hunter v1.2.1

- Use the AI Hunter in live games. The human plays Runner in first-hit and Dragon matches.
- Remove role selection and switching from launch and replay. Scripted runners power isolated benchmarks.
- Read Hunter-mode v1.2 configs and retain the existing playbook and metrics formats.

## Manhunt v1.2

- Learn whether to press or gear up from completed games, with frozen held-out runs and separately assignable controls.
- Add human Hunter and AI Runner escape, configurable points, and opening telemetry.
- Audit native inventory and enable guarded local-operator drops and handoffs on demand.
- Include the four development phases, fenced source, verification notes, and three video concepts.

## Hunter v1.1 traversal

- Build a single verified bridge lane across a span of up to six blocks, with per-block inventory and footing checks.
- Add optional water-bridge preference and benchmark-configured tests for dry, water, and lava lanes.
- Hold ladder and vine movement through a verified wall to an open ledge and let pillar placement finish during the jump.
- Record completed bridge crossings and wall ascents alongside existing round metrics.

## v8.0.2 — Clean source edition
- Removed obsolete docs, no-op scaffolds and duplicate/legacy launchers; consolidated current instructions.
- Preserved executable gameplay/training logic, model compatibility, all implemented tests and research provenance.
- Historical entries below describe the repository status and features at the time of those releases, not the current state.

## v8.0.2 | Resource objectives and Runner escape recovery
- Active approach/harvest/pickup state machine; safer aim, gather timeout and threat cancellation.
- Threat-aware verified detours and stale escape goal refresh.
- Native inventory status and resource summaries.
- 285 quickstart tests and 8 additional Python tests passed; live test pending.

## v8.0.1 | Head-start hotfix
- Remove duplicate local `component` import which shadowed the module-level text helper and crashed nonzero countdowns.
- Test the full default 20-second countdown in both roles, post-release human tracking, and interrupted Hunter restoration.
- No changes to inventory, resource collection, model files, or world formats.
- Offline verification: 276 quickstart tests, 8 original Python tests, JavaScript adapter checks. Live Fabric test pending.

## v8.0 | 2026-11-18
- Optional physical-resource collection from sensed nearby wood/soft blocks using Carpet fake-player attack.
- Read-only 36-slot native inventory mirror with atomic snapshots, delta journal, and optional Scarpet pickup/drop counters.
- Coordinate tracker with range, cooldown and last-known target, configurable head start/timer and append-only win scoring.
- Single v8 JSON config and new v8 Windows launchers; research and creator-script documentation.
- Existing v0.7.16 movement and tactical policies retained; no model data or save worlds bundled.
- Limitations: one human and one AI, no crafting automation, no cross-dimension tracking, no installed tracker compass.

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
