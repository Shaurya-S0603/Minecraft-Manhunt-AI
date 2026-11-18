# v0.7.16 implementation status

- New V4 scheduler and policy: offline-tested, **not yet tested on a live Fabric server**.
- Historical JSONL, V1/V2/V3 model files, private strategy imports and ordinary Manhunt worlds: preserved.
- V4 event metadata: new generation=4 and unique session ID for adaptive attempts.
- V4 policy: one candidate chosen using recent training evidence; held-out success is the criterion for promotion. Until verified, ordinary controls are the fallback.
- Reports: rolling-100/rolling-500 comparable results, current V4 sessions and cumulative history are separately labeled.
- Mine AI MCP: bounded research/scheduling hints only, no imaginary pretrained model or movement reward.
- Minecraft 1.21.11, Parkour School excluded, GitHub frozen at v0.6.

# v0.7.14 implementation status

- **Existing Manhunt:** preserved, Hunter/Runner, 3D terrain navigation, real-hit win, water movement, block breaking and rematches.
- **Generated training arena:** one-, two-, three-block gaps, horizontal swim, ladder climb.
- **Episode scheduling:** default 1000 episodes per course; all courses interleaved in one session, with periodic policy saves.
- **Learner:** separate real-trial jump bandit, plus real-trial swim/climb control selection. **Not a pretrained neural model.**
- **Diagnostics:** stage/skill metrics with trend, failure taxonomy and suggested fixes; reports in Markdown/CSV/JSON.
- **Parkour School world:** intentionally removed. It can be used as an *unseen evaluation map* later, not as current training data.
- **Live full-session verification:** pending on the user's Windows Minecraft 1.21.11 server.
- **GitHub:** not updated beyond previously authorized v0.6.

- **Tactical strategy:** short bounded Hunter intercept, stable angled Runner escape, persistent per-role local separation-change scores. Not a pretrained LLM.
- **Research integrations:** optional safely stripped Mine AI MCP tool-use index; Gemini Argon research informs goal/memory design only. No external weights or gameplay traces bundled.
- **Opt-out:** `MANHUNT_STRATEGY=0` fully restores previous strategy target behavior; movement protection unchanged.

- **v0.7.13 live navigation:** bounded verified detours after repeated empty routes, maximum four per 30 seconds per goal region; no blind steering. Clean v2 local-strategy policy only scores periods with actual bot movement and valid routes. Offline regression-tested, live Minecraft testing pending.

- **v0.7.14 water control:** shallow-water movement, submerged ascent transitions, water-waypoint arrival, physical swim-stall recovery and diagnostic counters. Offline-tested only; await user live river test.
