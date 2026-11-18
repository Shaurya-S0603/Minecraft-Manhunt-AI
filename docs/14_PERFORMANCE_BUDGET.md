# Performance budget and metrics

Minecraft server simulation generally targets 20 ticks per second. AI strategy can run less frequently than movement updates.

## Initial cadence hypotheses

Movement observations: up to 10–20 times per second; local replanning: on meaningful changes or roughly 2–5 times per second; high-level decisions: roughly 1–2 times per second. Measure actual costs rather than treating these as guarantees.

## Monitoring

Record per-stage latency, communication queue size, action timeouts, stuck fraction, distance to target, and server tick performance. Add match identifiers to logs for debugging.

## Scaling

Use bounded local observations, event-driven updates, hierarchical routes, and caching. Avoid inspecting the entire world or rerunning full-world search every tick.
