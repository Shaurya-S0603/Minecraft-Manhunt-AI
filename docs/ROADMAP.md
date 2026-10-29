# Roadmap

## v0.6: approved GitHub ceiling
- Existing working source: import pending.
- Server lifecycle and Hunter/Runner rules; result overlay and rematches.
- Terrain-aware 3D A* and safe spawn; initial water and block-breaking behavior.
- Verified damage-based Hunter victory.
- Upload actual source and run tests **before** tagging v0.6.

## v0.7: movement and terrain overhaul, outside GitHub
- Fix scientific notation in Minecraft position parsing (e.g. `6.654859864959756E-4d`).
- Sprint, sprint jump, headroom and landing clearance.
- Climb vines/ladders and safely exit the top.
- Underwater movement, tracking air and surfacing.
- Two-block obstacles: find a route or physically break safe blocks.
- Movement-state-specific recovery, regression and real-game testing.

**No v0.7 GitHub changes until the user expressly authorizes them.**

## Later milestones, only after approval
- v0.8: record our own match observations and decisions.
- v0.9: independent annotations of Manhunt footage with source URLs and timestamps.
- v1.0+: utility-driven tactics, traps, opponent models and evaluated self-play.
- Resource/inventory planning and full Minecraft goals only when movement is stable.
