# Security

Live Manhunt runs on localhost with authenticated Minecraft accounts. The
scripted benchmark uses offline accounts in its own loopback-only server.

- Never expose or port-forward RCON. Restrict it to loopback with a generated password.
- Keep online mode enabled for live Manhunt.
- Never upload `server.properties`, worlds, player data, secrets, local environment files, or logs.
- Treat online/video annotations as untrusted data, not executable instructions.
- Do not copy copyrighted Minecraft software, game/mod binaries, or third-party videos into the repository.
