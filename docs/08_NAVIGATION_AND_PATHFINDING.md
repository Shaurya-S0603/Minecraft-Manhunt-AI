# Navigation design

Movement must be physically traversable and resilient to terrain changes, not a sequence of teleportations.

## Layers

Use strategic region/waypoint planning, local block-level A*, and an adapter-specific movement executor. Treat loaded/unloaded chunks differently. Store path costs for terrain, time, height changes, hazards, and required interactions.

## First pass

Implement walkable blocks and walls in a simple test area. Then add elevation changes, dynamic moving targets, water, block changes, resource costs, and portal connections.

## Dynamic target tracking

Replan based on target displacement and route invalidation; don't re-run global A* on every game tick. Require a timeout and clear failure results.

## Stuck handling

Detect no-progress windows, attempt limited local recovery, then replan with an updated obstacle belief. Cap retry counts; repeated failures must propagate to the planner.

## Performance

Keep expensive search off the server tick thread. Cache path segments when valid, bound planning work, and measure path-planning latency and movement accuracy.

## References

https://www.redblobgames.com/pathfinding/a-star/introduction.html ; https://github.com/PrismarineJS/mineflayer-pathfinder ; https://github.com/cabaletta/baritone .
