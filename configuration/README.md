# Configuration plan

Actual values are intentionally absent. Placeholder `.toml` files contain comments only and are not a ready-to-run configuration.

## Ownership

The server owns match rule enforcement; the supervisor owns process and storage paths; the adapter owns bot network connections.

## Secrets

Keep secrets outside tracked configuration. Never embed Microsoft session credentials, passwords, or tokens.

## First implementation

Choose a consistent schema, then implement parsing, validation, sensible defaults, and documentation before enabling editing from the Fabric UI.
