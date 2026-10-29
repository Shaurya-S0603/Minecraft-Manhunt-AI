# v0.6 source audit and import instructions

## Source verification (2026-10-29)

The directly uploaded `Minecraft_Manhunter_1.21.11_v0.6_SWIM_MINE_HIT_BUILD(1).zip` was inspected in the build sandbox.

| Check | Result |
| --- | --- |
| Archive integrity | Passed (212 entries) |
| Python compilation | Passed |
| Quickstart gameplay/navigation tests | 87 passed |
| Original Python regression/contract tests | 8 passed |
| JavaScript adapter test | Passed |
| Bundled runtime history | Removed from import bundle |
| Live server testing in this session | Not performed |

The verified **source-only** import package includes 210 source/documentation files and a Windows PowerShell importer. It excludes RCON configuration, server data, world files, generated match history, installed third-party game binaries and caches.

### Important status

**The actual v0.6 source is not yet committed to this GitHub repository.** The GitHub connector can modify repository text files but does not accept a source-archive path from the build sandbox; the build sandbox cannot authenticate to GitHub by itself. A source-only import ZIP and a Windows Git-based uploader were prepared and provided in the corresponding ChatGPT conversation.

The importer:
1. Clones this **private** repository using the user's existing Git authentication.
2. Copies only the validated v0.6 source tree, preserving the repository's comprehensive `.gitignore`.
3. Reviews staged paths for secrets, worlds, binaries and generated logs.
4. Commits and pushes to `main`. It never uploads v0.7.

After the user runs that importer, rerun CI and verify its final commit before closing the import issue or creating a v0.6 tag.

**v0.7 remains local/chat-only until the owner explicitly authorizes a GitHub update.**
