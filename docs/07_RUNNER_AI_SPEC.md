# Runner AI behavior specification

The Runner has dual goals: survive the Hunter and progress toward its configured victory condition.

## States

ESCAPE, EXPLORE, GATHER, CRAFT, TRAVEL, SURVIVE, PROGRESS, RECOVER. Make threat response interrupt routine gathering or travel.

## First prototype

In survival mode, maintain safe separation, choose traversable escape locations, avoid environmental hazards, and handle loss of direct visibility. No crafting or portal traversal is required for the first milestone.

## Extended progression

Add a dependency graph for resources, crafting, inventory, portals, and completion objectives. Each subtask should have preconditions, success evidence, and a recovery path.

## Planning quality

Avoid actions that are individually sensible but incompatible with the overall goal, such as repeatedly entering a resource area when a nearby Hunter makes it unsafe.

## Acceptance

Runner escapes when threatened, returns to routine tasks when safe, and never loops indefinitely between two failed destinations.
