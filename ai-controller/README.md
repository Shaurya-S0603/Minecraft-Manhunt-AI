# AI controller: Python

The controller consumes normalized observations and returns bounded, adapter-neutral
actions. The initial vertical slice includes:

- `manhunt_ai.core`: observations, actions, agent context, memory, and the decision loop.
- `manhunt_ai.agents`: deterministic Hunter and Runner policies.
- `manhunt_ai.navigation`: bounded grid A* planning.
- `manhunt_ai.transport`: versioned envelopes, validation, heartbeat monitoring, and an
  in-memory adapter client for contract/integration tests.

## Order of work

The implemented order is observation/action contracts, transport/client, a decision
loop, Hunter behavior, Runner escape, and local navigation. The next integration step
is connecting the client to a concrete Mineflayer or Carpet adapter.

## Design rule

No direct Mineflayer API calls, Carpet commands, RCON, Minecraft game internals, or save-folder mutation from policy code.
