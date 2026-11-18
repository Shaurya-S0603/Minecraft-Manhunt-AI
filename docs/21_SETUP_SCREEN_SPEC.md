# Fabric client setup screen specification

The first implementation can use a configuration file. Build a native in-game menu only after the server match state is reliable.

## Controls

Select human role (Hunter or Runner), game objective, AI difficulty, tracking policy, head-start duration, world seed mode, and reset confirmation.

## Validation

Show current configuration; reject negative delays, unavailable modes, and role conflicts. Send requested values to server authority and display its accepted or rejected response.

## Access

Permit only local host/operator to change match-wide settings. Ordinary clients may inspect the active rules but may not reset worlds.

## Usability

Explain when settings take effect, especially seed changes that require a full server restart. Surface errors rather than silently ignoring requests.
