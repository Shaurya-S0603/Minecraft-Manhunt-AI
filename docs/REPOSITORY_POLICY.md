# Private repository and version policy

- **Visibility: private.**
- Approved repository content: working game source **up to v0.6 only**, plus documentation/research schemas.
- Development builds **v0.7 and above remain outside GitHub** until the owner explicitly permits uploading them.
- Do not silently replace the verified v0.6 release with scaffold code or tag a baseline that has not been imported.
- Before every push, inspect diffs, secrets, binaries and data licenses.
- Exclude `runtime/server-data/`, saved worlds, passwords in `server.properties`, credentials, installed mods, Java runtimes, `node_modules/`, videos, copyrighted frames, and generated logs.
- Run quickstart tests, original Python regressions, and Node adapter tests where present. Distinguish mocked tests from live Minecraft verification.
- Prefer atomic commits and source-only releases.
