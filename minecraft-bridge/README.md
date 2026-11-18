# Fabric bridge: Java

Java files are explanation-only placeholders. This is a directory layout, not a compilable mod project.

## How to turn it into a mod

Use the official 1.21.11 Fabric project generator to create build scripts, wrapper and mod metadata. Then implement these server/client classes against the template. Do not copy obsolete Java tutorials blindly.

## Server vs client

`src/main/java` describes server-authoritative gameplay and networking; `src/client/java` describes the optional local settings UI/HUD. Align source sets with your generated Fabric template.

## Mod identity

A proposed namespace is `dev.manhunt.bridge` and a proposed mod ID is `manhunt_bridge`; choose your own stable identifiers before writing mod metadata.
