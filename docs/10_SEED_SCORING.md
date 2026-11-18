# Seed suitability scoring

Seed scoring is a heuristic for good Manhunt gameplay, not an oracle about which world will guarantee an exciting match.

## Suggested dimensions

Spawn safety (20%), accessible early resources (20%), terrain diversity (20%), useful structures (15%), AI navigability (15%), and longer-run objective access (10%). Begin with these as *tunable assumptions*, not authoritative criteria.

## Input features

Record actual spawned location, nearby biomes and accessible terrain, optional structure distances, traversability estimates, and other factors relevant to selected game rules. A ruined portal is not equivalent to a completed portal.

## Candidate process

Generate candidates → gather low-cost estimates → score → shortlist → validate with a real 1.21.11 world → store results → randomly select among accepted candidates.

## Caution

World generation and structure prediction depend on game version and configuration. Keep Minecraft 1.21.11 fixed and compare predicted data with real server outcomes; don't assume a third-party map is always exact.

## Tools to study

https://github.com/Cubitect/cubiomes ; https://www.chunkbase.com/apps/seed-map ; https://modrinth.com/plugin/chunky .
