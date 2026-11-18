# Testing strategy

A working bot is not one that happens to succeed once. Automate repeatable checks against known seeds and controlled maps.

## Unit tests

Check state transitions, navigation heuristics, seed scoring, configuration validation, action timeouts, and win-condition logic independently of Minecraft.

## Contract tests

Both Mineflayer and Carpet implementations must produce the same observation semantics and acknowledge actions using the same statuses.

## Integration tests

Use a dedicated test server to validate connection, movement, line-of-sight observations, server-side head-start restrictions, and failure/reconnection behavior.

## End-to-end tests

Start a match with a known seed, let the Runner move first, release the Hunter after the configured delay, verify tracking/escape behavior, finish a match, then reset safely.

## Performance

Measure game tick stability, action latency, AI decision time, pathfinding time, navigation failures, and recovery frequency. Collect statistics across multiple worlds.
