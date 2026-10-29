# Minecraft Manhunt AI

**Private** Minecraft Java 1.21.11 Manhunt AI project. Python controller, Fabric/Carpet fake-player adapter, and Hunter/Runner gameplay.

## Repository state

**Setup complete, working v0.6 source import pending.** The v0.6 release ZIP is listed in the project Library but its raw archive bytes are not available for import here. The other currently mounted ZIP is an old, explanation-only scaffold, not the user's working v0.6 build. This repository is **not yet a runnable v0.6 release**.

## Approved baseline and freeze

- **GitHub version ceiling:** v0.6, until explicitly changed by the owner.
- **v0.7:** Build and test outside GitHub; deliver directly in ChatGPT. **Do not upload v0.7 code, branches, tags or releases without explicit permission.**
- Tag v0.6 only after importing and validating the actual working release.

## Technical approach

- Human may be Hunter or Runner; one real Minecraft account plus a Carpet fake player.
- Physical walking, swimming, mining and attacks; 3D pathfinding and world observation.
- Safe initial and rematch spawns, persistent local server, short victory title.
- Damage-event-confirmed Hunter victory rather than proximity.
- Future work: full movement controller, telemetry, opponent modelling and a lawful Manhunt video strategy index.

See [Roadmap](docs/ROADMAP.md), [Architecture](docs/ARCHITECTURE.md) and [Repository Policy](docs/REPOSITORY_POLICY.md).

**Never commit worlds, server credentials, Minecraft binaries, Java runtimes, raw third-party videos or generated gameplay logs.**
