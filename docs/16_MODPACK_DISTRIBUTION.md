# Modpack, server, and app distribution

A modpack is not the same thing as a Python application, Node bot, or dedicated game server.

## Client pack

Package only the compatible client-side Fabric dependencies, configuration, and interface assets. If the setup menu is client side, ensure it exists in the client mod distribution.

## Server pack

Package the Fabric bridge mod, matching Fabric API, and Carpet if used. Document which mods are required and which are optional.

## Python/Node applications

Distribute the AI controller and Mineflayer adapter with dependency installation instructions or later a purpose-built launcher. A Modrinth `.mrpack` alone does not install Python or Node.js programs.

## Legal and licensing

Do not bundle Minecraft's game JAR. Confirm each third-party mod/library license and redistribution terms. Choose your own project license before publishing.

## Release gate

Clean-machine installation test, matching version pins, server start, AI connect, one successful match, world reset, and log/backup retention check.
