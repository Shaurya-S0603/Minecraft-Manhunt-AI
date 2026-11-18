# Engineering and learning rules

1. Keep the Minecraft target at **1.21.11** until the first playable release.
2. Implement source logic yourself. Every language-specific file here is comments-only by design.
3. Use one canonical observation/action format regardless of whether the bot uses Mineflayer or Carpet.
4. Make match rules server-authoritative. A bot must not decide when its own head start ends.
5. Use clear failure results, not silent retries or infinite loops.
6. Don't expose undiscovered game data to an AI unless the selected difficulty explicitly permits it.
7. Never mutate a live world folder. World resets require confirmed server shutdown.
8. Never commit credentials, private tokens, or user-specific server paths.
9. Keep authenticated multiplayer support enabled; don't bypass authentication just to connect a bot.
10. Record version compatibility from successful experiments rather than assuming all 1.21.x packages interoperate.
11. Keep AI inference and path planning off the Minecraft main server thread.
12. Store no identifying information about human players beyond what is necessary for the current local match.
