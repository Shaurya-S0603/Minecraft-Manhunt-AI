# Phased implementation roadmap

Milestones are defined by observable results. Implement the minimum needed for each milestone before expanding the architecture.

## Stage 1: Foundation

M1: Install Java/Python/Node, start a 1.21.11 Fabric server, confirm adapter compatibility. M2: Receive one normalized observation and execute one acknowledged movement goal.

## Stage 2: Core autonomy

M3: Block-level navigation and no-progress recovery. M4: Hunter tracking/chase and Runner escape behaviors in a controlled environment.

## Stage 3: First playable match

M5: Server-authoritative role selection, head start, and survival win conditions. M6: One full human-versus-AI match with logging and restart.

## Stage 4: World intelligence

M7: Safe world archive/recreation; same-seed and new-seed trials. M8: Seed scoring, selection history, resource/inventory planning, and optional client UI.

## Stage 5: Full product

M9: More advanced Runner progression and dimension navigation. M10: Repeated regression matches, difficulty balancing, documentation, and distribution.

## Stop conditions

Do not proceed to Runner crafting or reinforcement learning while movement and reconnection remain unreliable. Prefer working vertical slices over unfinished abstractions.
