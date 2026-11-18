# Version compatibility and verification log

Game version is fixed at **Minecraft Java Edition 1.21.11**. Library and loader patch releases should be selected through official download pages and tested together.

## Version baseline

Minecraft: 1.21.11; Java: JDK 21; Python: 3.12/3.13 as confirmed by packages; Node: a supported LTS release; Fabric Loader/API: 1.21.11-compatible builds; Mineflayer: a release that explicitly includes 1.21.11; Carpet: 1.21.11 build if using fake players. Avoid hardcoded speculative version numbers.

The initial Node adapter dependency selection is:

- Node.js 24.22.0 (local verification; satisfies Mineflayer's `>=22` engine requirement).
- Mineflayer 4.39.0.
- mineflayer-pathfinder 2.4.5.
- minecraft-data 3.114.0, installed transitively by Mineflayer.

The npm metadata for Mineflayer 4.39.0 requires Node.js 22 or newer. The
Minecraft 1.21.11 protocol/data smoke check is still required before treating
this combination as production-compatible.

## Compatibility matrix to complete

| Component | Selected version | Source | Status |
|---|---:|---|---|
| Minecraft Java | 1.21.11 | Project target | Required target |
| Node.js | 24.22.0 | Local runtime | Installed |
| Mineflayer | 4.39.0 | npm registry | Installed; server login pending |
| mineflayer-pathfinder | 2.4.5 | npm registry | Installed; movement smoke test pending |
| minecraft-data | 3.114.0 | npm registry, transitive | Must contain 1.21.11 data |

Record the server startup result, bot login result, pathfinding test result,
inventory interaction result, and modpack packaging result after the local
Minecraft server is available. Treat "works with Minecraft 1.21" as insufficient
evidence of "works with 1.21.11".

The current dependency install reports six moderate transitive npm audit
findings in Mineflayer's authentication chain. The automatic npm remediation
offers Mineflayer 1.4.0 as a major downgrade, so it was not applied. Revisit
this after Mineflayer publishes a compatible dependency update.

## Migration strategy

Maintain adapters behind stable contracts. To migrate later, first update the server and Fabric dependency set in a branch; then verify bot protocol compatibility, recompile the Fabric bridge, rerun integration tests, and only then update AI dependencies.

## Recommended sources

https://fabricmc.net/develop/ ; https://docs.fabricmc.net/ ; https://github.com/PrismarineJS/mineflayer ; https://github.com/gnembon/fabric-carpet ; https://github.com/cabaletta/baritone .
