# Component boundaries and ownership

Modules must have one clear responsibility so they can be tested separately.

## AI controller

Reads normalized observations; updates the Hunter or Runner world model; chooses the next behavior; submits abstract action requests; times out and recovers from unacknowledged actions. It does not call Minecraft internals or delete saves.

## Mineflayer adapter

Owns network player authentication, connection lifecycle, low-level movement, item actions, protocol/version concerns, and observation collection. Never implements match victory rules.

## Carpet adapter

Alternative backend for a Fabric/Carpet fake player. Owns command requests and feedback but cannot assume every Mineflayer capability exists.

## Fabric bridge

Reads game events, enforces permissions, handles client configuration requests, validates action authority, and forwards immutable snapshots. World changes happen only on the correct Minecraft thread.

## Supervisor and seed service

Supervisor owns server start/stop and match phase transitions. Seed service owns candidate scoring and storage. Only supervisor-controlled, shutdown-confirmed operations may replace saved worlds.
