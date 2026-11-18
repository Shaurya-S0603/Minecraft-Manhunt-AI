# Windows + VS Code setup plan

Follow this setup guide if you are developing on Windows. This folder can be opened directly in VS Code, but none of the placeholders are runnable yet.

## Editors and language tools

Install Visual Studio Code; install Microsoft's Extension Pack for Java, the Python extension, and an appropriate Java build tool extension. Install JDK 21 and ensure VS Code detects it. Install Python 3.12/3.13 if library support allows it, a maintained Node.js LTS runtime, and Git. Use official installers and verify each tool independently.

## Java and Fabric

Use the Fabric template generator for Minecraft Java Edition 1.21.11 to create the real Gradle build files and Fabric metadata after studying the Java comment placeholders. The supplied `minecraft-bridge` folder is not yet a Gradle project. Choose Mojang or the mapping set recommended for your exact template, and record the choice.

## Minecraft server

Set up a dedicated Java server in a location outside the git project and runtime backups. Start it once to accept the official EULA and generate required files, then install matching Fabric Loader and Fabric API. Use a private, authenticated server and whitelist where supported.

## Node adapter

Once confirmed against 1.21.11, create the real Node package manifest and install Mineflayer plus the navigation dependencies you actually need. The package manifest in this scaffold is documentation only; package managers cannot install from it.

## Python projects

Create isolated Python virtual environments for AI control, match supervision, and seed tooling if dependencies diverge; one shared project environment is acceptable initially. Implement actual package metadata only after selecting dependencies. Don't mix local environments into the zip or source control.

## VS Code tasks

After completing one vertical slice, create local launch configurations for the Python AI, Node adapter, and Fabric development server. Each process requires independent logs and a predictable startup/shutdown order. `.vscode` contains planning documents rather than active tasks.

## Security

Store account secrets, RCON passwords, and private server settings outside git; create a real ignore policy before committing. Avoid reusing the main account's credentials in application configuration. Keep any raw RCON listener limited to localhost.
