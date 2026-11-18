# Mineflayer adapter: Node.js

The adapter owns the Minecraft client session and translates between Mineflayer
objects and the versioned controller contract. The local implementation includes:

- validated protocol envelopes in `src/protocol.js`;
- injectable bot lifecycle management in `src/bot_connection.js`;
- normalized observations in `src/observation_publisher.js`;
- bounded action dispatch and acknowledgments in `src/action_dispatcher.js`;
- pathfinder isolation in `src/pathfinding_plugin.js`;
- an in-memory transport boundary for contract tests.

The bot factory and Pathfinder module are injected deliberately. This keeps local
contract tests independent of Minecraft while preventing the project from claiming
support for an unverified Mineflayer release.

## First experiment

Confirm login to authenticated Minecraft 1.21.11 server, position reporting, basic movement, item interaction, and reconnect behavior. Record the Mineflayer/plugin versions used.

## Dependencies

Create a real Node package manifest yourself, using official Mineflayer and Pathfinder documentation. `package.json.plan.md` is not an installable manifest.

After selecting versions that have been smoke-tested against Minecraft 1.21.11,
provide a `createBot` function from Mineflayer and a configured Pathfinder module
to `createAdapter` in `src/index.js`.

Current install note: `npm audit --omit=dev` reports six moderate transitive
advisories in the Mineflayer authentication dependency chain, including the
known `uuid` buffer-bounds advisory. npm's proposed automatic fix downgrades
Mineflayer to 1.4.0, which is not an acceptable compatibility fix for this
Minecraft target. Do not run `npm audit fix --force` until a compatible upstream
Mineflayer release resolves the chain.

## Important

Do not use offline-mode or authentication bypass as a development shortcut. If an extra bot identity is unavailable, evaluate Carpet.
