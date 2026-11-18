# World reset and seed safety

Only a supervising process should create, archive, or replace world folders. The seed manager never deletes an active save.

## Reset transaction

Complete/end the match → prevent new match starts → request server save and clean stop → confirm process has exited → archive existing save → write intended seed/world settings → start fresh server → verify generated world and spawn → release match state.

## Safety requirements

Require a dedicated data root, canonicalize paths, reject symlink escapes or paths outside the allowed root, protect against deleting non-project folders, and keep last-known-good backups. Use bounded retries and an operator-readable failure log.

## Repeat same seed

Reusing a numeric seed is not enough if an existing world folder remains. Recreate the world only after archiving/removing the old generated save and ensuring all world-generation settings match.

## New seed

Generate a candidate, evaluate it, record its Minecraft version and world-generation settings, and only then launch a clean world. Preserve a seed registry so an interesting world can be revisited.

## Recovery

If the new server fails to boot or initial validation fails, preserve diagnostic logs and offer restoration of the previous archived world instead of deleting all backups.
