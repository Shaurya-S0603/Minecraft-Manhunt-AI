# Architecture decision: Mineflayer or Carpet?

Keep the first integration choice reversible. Both implementations should serve the same Python policy layer.

## Mineflayer advantages

Bot-like features, protocol client, existing navigation/interaction APIs, no need to implement player controls from scratch. Caveats: Node runtime, possible dedicated authenticated bot account, and version-specific bugs.

## Carpet advantages

Runs simulated players inside a Fabric server and may not need a separate authenticated client identity. Caveats: command-style control can be limiting; a more advanced Fabric bridge may be needed.

## Decision experiment

On your real 1.21.11 server, test connect/spawn, move, pathfinding, inventory, interaction, server restarts, and failure recovery. Choose the adapter that passes the required tasks. Do not assume mere successful startup demonstrates compatibility.

## Current provisional decision

Start with Mineflayer because of its existing bot APIs; retain Carpet as a fallback. After the connection experiment, record actual results and lock one adapter for milestone 2.
