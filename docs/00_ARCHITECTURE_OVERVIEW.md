# Architecture overview

The game simulation, bot locomotion, Python cognition, and match lifecycle are separate concerns. Keep them separate even in the first implementation.

## Component diagram (text)

Human player ⇄ Minecraft Java 1.21.11 dedicated server ⇄ bot player (Mineflayer or Carpet). The Python AI controller exchanges observations and actions with the bot adapter. A Fabric bridge enforces match rules and reports authoritative game events. The Python match supervisor starts and stops server processes, selects roles, and requests seed/world operations. The seed manager scores candidates and records metadata.

## Why two adapters?

Mineflayer can supply useful navigation and inventory primitives, but connecting as a real protocol client may require an authenticated bot identity. Carpet fake players are server-managed and avoid that requirement, but expose different controls. The AI should not need to change if one integration is replaced.

## Recommended default

Prototype with Mineflayer if connection, interaction, and authentication are confirmed on 1.21.11. Keep Carpet as a fully documented fallback. Do not run both as simultaneous authorities over the same agent.

## Authority

Minecraft server owns real entity positions, damage, victory events, and allowed actions. The Fabric bridge enforces start delays and match rules. The AI owns goals and plans, not world state. The supervisor owns process transitions and safe reset coordination.

## Minimum viable product

One human and one AI-controlled player, either role selected, a configurable Runner head start, simple chase/escape, and restartable survival matches. Full Ender Dragon completion is a later milestone.
