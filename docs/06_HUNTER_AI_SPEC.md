# Hunter AI behavior specification

Hunter aims to track and catch Runner while managing path quality, resources, and safety.

## States

WAITING, PREPARE, TRACK, CHASE, ENGAGE, SEARCH, RECOVER. Define explicit entry conditions, exit conditions, and a maximum time budget for each state.

## Tracking policies

Perfect tracking for integration tests; compass/delayed last-known-location for normal mode; observation-only information for harder difficulty. Treat location age and dimension transitions as first-class fields.

## Decision order

Respect match phase → respond to immediate environmental hazards → evaluate target knowledge → choose chase/search/preparation → submit bounded action → re-evaluate after events.

## Fairness

Do not read hidden opponent inventory, undiscovered structures, or exact cross-dimension coordinates unless explicitly enabled by chosen game mode.

## Acceptance

With known line of sight, Hunter follows a moving Runner without spamming conflicting commands. When Runner is lost, Hunter switches to an explicit SEARCH behavior instead of pretending the old coordinate is current.
