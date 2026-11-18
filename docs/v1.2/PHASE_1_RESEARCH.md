# Phase 1 — Research

## Video references

| Title | Summary | Adopt |
|---|---|---|
| [Minecraft Speedrunner VS 5 Hunters FINALE — Dream](https://www.youtube.com/watch?v=44wLAzydRFU) | Dream’s official episode demonstrates the asymmetric race between completing Minecraft and preventing the runner from finishing. The published description identifies the participants and the format. | Use asymmetric win conditions and tell the story through changes in pressure. Use our own footage and credited participant perspectives. |
| [Tutorial: How To Make a Tracking Compass Like in Minecraft Manhunt!](https://www.youtube.com/watch?v=88-8PpPIAvQ) | The tutorial demonstrates a player-tracking compass from a creator’s point of view. It is a reference for explaining tracking to players and viewers. | Present a compact direction cue, a refresh timer and a clear signal when the trail has expired. |

## Academic and design references

| Title | Summary | Adopt |
|---|---|---|
| [To Asymmetry and Beyond! — Harris and Hancock, CHI 2019](https://uwaterloo.ca/touchlab/references/asymmetry-and-beyond-improving-social-connectedness) | The study evaluates asymmetric **cooperative** play and finds that changing the timing and direction of dependence affects the experience. Its findings describe cooperation and offer design hypotheses for our competitive mode. | Give each role a clear information boundary and release time. Treat rule variations as testable choices. |
| [A graph search algorithm for indoor pursuit/evasion](https://www.sciencedirect.com/science/article/pii/S0895717709002398) | This paper models a mobile evader and pursuers moving on a graph with bounded visibility. Its search is internal, so pursuers physically traverse edges. | Use recent contact and traversable routes as evidence. Keep portal locations scoped to observed entrances. |
| [A Contextual-Bandit Approach to Personalized News Article Recommendation — Li et al.](https://arxiv.org/abs/1003.0146) | The paper learns which action to take given context and observes feedback for the selected action. It demonstrates contextual exploration and discusses the conditions for offline evaluation. | Log the selected opening and its actual outcome. Freeze policy during held-out tests and run a deliberately assigned baseline. The v1.2 implementation uses a small tabular upper-confidence bound. |

## Open-source implementations

| Title | Summary | Adopt |
|---|---|---|
| [ManhuntButItWorks](https://github.com/Riqqqque/ManhuntButItWorks) | This Paper plugin offers target cycling, countdown and persistence, including a Nether portal fallback. Its compass is deliberately protected from accidental inventory actions. | Keep an explicit target and use an observed portal as a fallback. Our Python/Carpet server retains its own tracking implementation. |
| [Minecraft Manhunt Compass Mod — AdyTech99](https://github.com/AdyTech99/minecraft-manhunt-mod) | The repository implements a tracking compass as a mod and documents support for multiple players. Its nearest-runner selection illustrates a readable approach in team play. | Keep role and target selection explicit, and show the human hunter a readable direction cue. |

## Community and wiki references

| Title | Summary | Adopt |
|---|---|---|
| [Inventory — Minecraft Wiki](https://minecraft.wiki/w/Inventory) | The wiki documents the player’s hotbar, main storage, equipment areas and ordinary stack interactions. It also describes distinct UI rules for partial stacks and full stacks. | Observe the 36 main slots, include the native per-item limit and mirror armor and offhand independently. Preserve item components on moves. |
| [Compass — Minecraft Wiki](https://minecraft.wiki/w/Compass) | A native compass points toward a world location horizontally. When its target cannot be found, the needle becomes unreliable. | Treat the compass as bearing, with an explicit stale state and separate line-of-sight confirmation. |
| [Manhunt with only 7 Command Blocks — r/MinecraftCommands](https://www.reddit.com/r/MinecraftCommands/comments/oojwmm) | This community build demonstrates an Overworld-only compass built using vanilla commands. It points to the last known location when the runner leaves the Overworld. | Test stale tracking at dimension changes and communicate uncertainty rather than exposing cross-dimension coordinates. |
| [Scarpet events — Fabric Carpet](https://github.com/gnembon/fabric-carpet/blob/master/docs/scarpet/api/Events.md) | The event reference distinguishes action requests from events that occur after an action finishes. Pickup supplies an item stack, while drop requests need separate observation to establish the quantity lost. | Journal event types separately. Give transfers their own verified receipt and retain vanilla player data as the inventory source of truth. |

## Decisions for v1.2

- Keep the working controls, crafting, and physical survival inventory. Add auditability and a bounded operator transfer.
- Give the hunter a choice between pressing immediately and spending a short window gearing up. Let completed matches drive the choice, with visible range, cooldowns, hit verification and movement safety enforced by the existing controller.
- Put scoring, tracking and learning limits in one config. The human Runner can face the AI Hunter under first-hit or Dragon rules.
