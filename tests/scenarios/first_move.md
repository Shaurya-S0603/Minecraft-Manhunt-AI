# Manual test: first AI move

The initial vertical slice validates the architecture end to end.

## Setup

Run a private Minecraft 1.21.11 server with one human and one selected AI adapter. Use a flat, safe area.

## Procedure

Connect bot → capture its position → issue a short walk goal → observe progress → verify arrival → disconnect and reconnect → repeat.

## Pass criteria

Target arrival confirmed from independent observation, no teleportation, coherent action status, and no stuck pending commands after reconnect.
