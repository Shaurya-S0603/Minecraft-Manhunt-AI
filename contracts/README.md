# Message contract catalog

These specifications describe structured messages between Python, Node, and Java. No executable JSON Schema or generated API is included.

## Consistency

Every transport implementation must interpret coordinates, dimensions, ticks, item identifiers, units, and status names identically.

## Versioning

Assign a contract version and negotiate it on startup. Reject incompatible versions instead of misreading data.

## Documents

Read the observation, action, acknowledgment, match-event, and heartbeat specifications before writing transport code.
