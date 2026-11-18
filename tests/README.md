# Test plan and fixtures

Every `.py` test file is comments-only. The integration tests require a disposable Minecraft 1.21.11 server with no personal saves.

## Test ordering

Unit tests → adapter contract tests → movement integration tests → head start and reset tests → end-to-end survival match.

## Isolation

Never point reset tests at an existing user world. Create a separate, allowlisted root for destructive tests.
