# Cross-process data contracts

Implement an explicit, versioned exchange format before adding advanced AI. Documents in `contracts/` describe message shapes without providing JSON or implementation.

## Envelope

Each message needs contract version, message type, sender, match identifier, agent identifier when relevant, a unique request identifier, timestamp, and optional game tick. Reject unsupported versions and stale match identifiers.

## Observation

Include position and dimension, health/hunger, selected inventory summary, movement flags, nearby visible entities, local terrain information, and relevant recent events. Always distinguish unknown/hidden information from an empty observation.

## Action request

Use stable action names such as move-to, follow, look, jump, interact, equip, stop, or retreat. Every action includes preconditions, bounded duration, and correlation identifier. Explicitly distinguish high-level navigation goals from immediate movement commands.

## Action acknowledgment

Report accepted/rejected, execution started, succeeded, failed, cancelled, or timed out with a reason and fresh positional observation. One request should never silently trigger repeated irreversible actions.

## Heartbeat and disconnects

Periodic heartbeat reports identify live processes. Stale agents must stop executing queued actions; reconnecting agents need a fresh match-state snapshot before accepting commands.

## Security and validation

Accept messages only from trusted local processes or authenticated peers. Validate allowed actions by match state; never trust the Python process to decide if a waiting Hunter may move.
