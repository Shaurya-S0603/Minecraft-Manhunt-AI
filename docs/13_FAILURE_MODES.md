# Failure recovery catalog

Design recovery before implementing complex behavior; otherwise every edge case becomes an infinite chase loop or server hang.

## Bot disconnect

Invalidate pending commands, mark actor unavailable, pause or end match according to policy, and require a fresh snapshot after reconnect.

## Bridge unavailable

Stop transmitting actions and report a clear fault. Never assume commands succeeded without acknowledgement.

## Navigation stuck

Mark route invalid, run finite recovery attempts, then surface a failure to goal planning. Record surroundings for debugging.

## World reset interrupted

Check whether the server process is truly stopped and whether backup/archive stage succeeded. Never repeat deletion blindly.

## Partial installation

If Fabric, Carpet, Mineflayer, or protocol versions fail compatibility tests, record an explicit unsupported state and switch adapter only after the alternative has passed contract tests.
