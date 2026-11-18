# Match supervisor

The supervisor coordinates processes, match phases and safe world lifecycle operations.

## Critical rule

The supervisor is the only component allowed to modify world data during a reset, and only after Minecraft has stopped and the process exit is verified.

## Authority

The Fabric bridge remains authoritative about in-game permissions and victories. The supervisor consumes these facts and coordinates external processes.
