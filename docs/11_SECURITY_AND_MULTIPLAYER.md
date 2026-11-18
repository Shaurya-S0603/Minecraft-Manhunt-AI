# Security and multiplayer boundaries

The initial architecture targets an isolated local/private server. Do not turn a development proof of concept into an unprotected public service.

## Authentication

Mineflayer network bots may require valid authenticated accounts. Carpet fake players are server-managed. Do not disable online authentication or server protections to avoid solving legitimate bot login requirements.

## Networking

Bind development WebSocket/TCP and RCON interfaces to loopback by default. Authenticate control messages, validate payload sizes and timeouts, and reject unauthorized match-control actions.

## Secrets and source control

Store RCON credentials, account tokens, and local paths in an untracked secret store or environment variables. Before initializing a git repository, create a real ignore file excluding those values and backups. No secrets are supplied here.

## Human-player privacy

Store gameplay observations needed for the match without collecting real-world personal identifiers. Define log retention and redact authentication details before sharing logs.

## Authoritative enforcement

The server validates role, phase, and actions. Client menus only request changes; they do not decide who has won or whether a waiting player can act.
