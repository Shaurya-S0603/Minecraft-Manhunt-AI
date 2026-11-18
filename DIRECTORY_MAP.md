# Folder map — v0.7.16

```text
Minecraft_Manhunt_AI_1.21.11/
├── manhunt/                    normal Manhunt launchers (Hunter/Runner/setup/reset)
├── training/
│   ├── launchers/             jump, swim, climb, combined, and policy fitting
│   ├── launchers/IMPORT_MINEAI_TRACE.bat
│   ├── arena_config.example.json
│   └── README.md
├── reports/
│   ├── VIEW_REPORT.bat
│   ├── STRATEGY_REPORT.bat
│   ├── CHECK_LIVE_SKILLS.bat
│   ├── README.md
│   └── generated/             automatically created report outputs
├── quickstart/                shared Python runtime, physics, trainer and read-only live skill bridge
│   └── tests/
├── runtime/                   created/retained locally; never commit worlds
│   ├── server-data/           ordinary Manhunt world (not bundled)
│   ├── training-server-data/  generated training arena (not bundled)
│   ├── movement_training/     local real-trial logs and policy checkpoints
│   └── strategy/              local role-specific strategy scores and optional trace metadata
├── docs/, contracts/          technical references
├── bot-adapter-mineflayer/     experimental JavaScript adapter and tests
├── tests/                     original Python regression tests
├── README.md
├── START_HERE.md
└── RUN_TESTS.bat
```

Experimental scaffolding under `ai-controller/`, `match-supervisor/`, `seed-manager/`, `bot-adapter-carpet/` and `minecraft-bridge/` is preserved for existing tests and development. The **active** Python game and trainer remain in `quickstart/`; moving this package would break existing relative imports.

V4 adaptive training uses `training/launchers/TRAIN_ADAPTIVE_V4.bat`.
The new checkpoint is `runtime/movement_training/curriculum_policy_v4.json`,
while prior checkpoints and the append-only episode JSONL remain in place.
The report renderer also creates `reports/generated/training_current_summary.csv`,
in addition to the historical CSV and the Markdown/JSON reports.
