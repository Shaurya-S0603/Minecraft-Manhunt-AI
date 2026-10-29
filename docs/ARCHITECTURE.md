# Architecture

## Version baseline
The user-confirmed working v0.6 release is a Python-controlled Fabric/Carpet Minecraft Java 1.21.11 Manhunt prototype. Its original source archive has **not yet been imported** into GitHub.

```
Strategic / tactical decision layer (future)
                 |
Skill and movement executor (v0.7 target, local only)
                 |
3D pathfinding, observations and safe spawn (v0.6)
                 |
Python localhost RCON controller
                 |
Fabric + Carpet fake player, Minecraft 1.21.11
```

The working baseline includes both human roles, authenticated local-server setup, replay and role switching, physical walking, basic swimming and mining, safe spawn and confirmed-hit victory. The full code and compatibility tests must be taken from the actual v0.6 ZIP, never improvised from this design document.

## Engineering principles
Physical movement instead of navigation teleports, fail-closed unknown terrain, permission-controlled RCON, no copied game binaries, reproducible test seeds and explicit separation between strategy research and runtime commands.
