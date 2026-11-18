# Role selection, game rules and head start

The game controller should treat Human-as-Hunter and Human-as-Runner as symmetric match setups.

## Setup

The human chooses a role, AI difficulty, tracking mode, head-start duration, win condition, seed policy, and optional spectator testing mode. Persist settings before launch, but validate them server-side.

## Phases

SETUP → WORLD_READY → HEAD_START → ACTIVE → FINISHED → RESET. Prevent actions inappropriate to each phase. Match phase transitions should be idempotent and logged.

## Head start

Runner starts immediately while the Hunter remains constrained. The delay applies whether the Hunter is human or AI. Countdown authority belongs to Minecraft server state, not local wall-clock assumptions in Python.

## Win conditions

Survival mode: the Runner wins after a configurable valid survival duration, and Hunter wins upon the configured elimination/capture condition. Completion mode: Runner achieves the agreed endgame objective, typically the Ender Dragon; define deaths, respawns, disconnections, and tie rules before coding.

## Two-AI test mode

Add an optional AI-versus-AI spectator mode to test both policies. Normal play only needs the selected opposing AI, even though the architecture supports both autonomous player types.

## UI

Provide a local config first, then an in-game client screen whose choices are sent to the authoritative server. Non-host clients must not change match-wide settings.
