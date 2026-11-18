# Carpet adapter: alternative fake players

Use this instead of the Mineflayer adapter when server-managed fake players are more appropriate.

## First experiment

Verify Carpet compatibility with Minecraft 1.21.11, spawn a fake player, test bounded movement, and find a reliable way to observe position and action results.

## Limitations

RCON commands alone are not a general high-rate full world-observation API. Expect a Fabric-side bridge for fine-grained control and game-state snapshots.
