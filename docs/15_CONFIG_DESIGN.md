# Configuration design

Use human-readable TOML or JSON for initial settings, but **do not** commit real passwords or account details.

## Match settings

Role: runner or hunter; head start in seconds; survival vs completion objective; win duration where applicable; tracking mode; difficulty; allowed deaths/respawn behavior; world reset policy.

## Controller settings

Transport endpoint, bounded reconnection attempts, command deadlines, heartbeat intervals, and logging verbosity.

## Seed settings

Candidate count, quality threshold, weighting profile, evaluation radius, validation policy, and maximum retained backups.

## Validation

Reject unknown required roles, negative timers, malformed seeds, inconsistent modes, impossible match settings, and unapproved filesystem paths. Distinguish config parsing from game-rule enforcement.

## UI migration

Later, a Fabric client screen writes requests to the server, which validates and stores selected settings. Provide a preview and confirmation before a destructive world reset.
