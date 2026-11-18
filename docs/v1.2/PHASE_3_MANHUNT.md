# Phase 3 — Manhunter script and learning

## Install and run

Use Python 3.10+, Java 21, and the Minecraft Java **1.21.11** client. Fabric and Carpet are installed by the existing launcher when needed. Extract the whole ZIP to a new directory first. Review the EULA and start the server using the commands from the archive's top-level README.

```powershell
python -m quickstart.hunter_v1.cli play --player YourMinecraftName
python -m quickstart.hunter_v1.cli play --player YourMinecraftName --win-mode hit
```

Join `localhost:25565`. Use the first command for the configured win mode or the second for first-hit rules. Both modes put you in the Runner role and use a Carpet fake player as the AI Hunter. The launcher validates your Minecraft username. The Hunter waits during your head start, and the hit counter resets at release.

## Rules and tracking

- **First hit.** The hunter wins on the first positive damage event against the assigned runner. A runner death without a confirmed hit aborts the round. The runner wins by surviving the timer or exhausting the hunter's respawn allowance.
- **Dragon.** The runner wins by completing Free the End, surviving the timer, or exhausting the AI hunter's respawn allowance. The hunter wins when the runner dies. A disconnect ends a round without score or match-level learning.
- **Scoring.** Defaults are 3 points for a win, 0 for a loss and a separate 1-point first-tag bonus for the hunter. Completed rounds add to the local `mh_points` scoreboard and record both deltas in JSONL. Use `/trigger mh_replay` after a round to play again.
- **Tracking.** The hunter sees exact positions only with checked line of sight within the configured visible range. Outside that range the compass supplies a quantized bearing from a bounded sample, and its trail expires. Cross-dimension pursuit can go to a portal already seen by the AI.
- **Configuration.** All public options are in `config/hunter_v1.json`. The sections are `game`, `tracking`, `resources`, `learning`, and `scoring`. The code supplies defaults for newly added keys in older configuration files.

## What the hunter learns

A match director picks **press** or **gear** once, when tracking starts and the hunter is unarmed or low on food. Press delays optional supplies during the opening. Gear gives the existing collector an opportunity to act safely. The director never changes hit verification, sensing limits, movement safety or inventory rules.

Opening trials share experience across seeds within the same rule mode and readiness category. Complete outcomes give the chosen opening feedback. The reward adds the match result, a bounded bonus for a faster verified tag, and a penalty for hunter deaths. Independent route, close-interception and observed-portal memories keep their existing feedback. No label is written for an aborted round.

Train mode updates the saved playbook using bounded upper-confidence exploration. Held-out mode uses the best observed choice and freezes policy writes. `baseline` preserves the previous supply schedule, while `press` and `gear` can be assigned as fixed opening controls. Compare the same fixture and seed with both policies in held-out mode. Different benchmark seeds give separate world instances, but the scripted arena layout itself is held constant. Also vary runner scenarios or use real human rounds before drawing a conclusion.

```powershell
python -m quickstart.hunter_v1.cli scenario --scenario supplies --seed 7442 --split train --rounds 12
python -m quickstart.hunter_v1.cli scenario --scenario turns --seed 9001 --split held-out --policy learned --rounds 12
python -m quickstart.hunter_v1.cli scenario --scenario turns --seed 9001 --split held-out --policy baseline --rounds 12
python -m quickstart.hunter_v1.cli report --scenario turns --split held-out --policy learned
python -m quickstart.hunter_v1.cli report --scenario turns --split held-out --policy baseline
```

The controller records the opening, context, outcome and score in each applicable row. Compare tag fraction, match outcome, time to tag, and resource evidence. Median time among successful tags omits untagged rounds and should be read together with the tag fraction. A small smoke run proves that updates and evaluation work. It does not establish stronger play.

See [the fenced source listing](PHASE_2_AND_3_SOURCE.md) for complete updated gameplay and inventory modules. The ZIP also includes all supporting runnable code, configuration, launchers, and tests.

## v1.2 learning and inventory checks on Java 1.21.11

| Fixture | Split and opening | First verified hit |
|---|---|---|
| supplies seed 7442 | train / press | 10.2 s |
| supplies seed 7442 | train / gear | 15.9 s |
| turns seed 9001 | held-out / press | 11.9 s |
| turns seed 9001 | held-out / baseline | 11.6 s |

The gear opening picked up one oak log and crafted four planks and four sticks. The held-out matches left the policy file byte-identical.
A separate inventory test verified a physical drop, a partial stack transfer, preserved equipment damage, refusal of an occupied slot, and playerdata persistence across a full server restart.
The smoke tests used scripted local players. Human-match performance and gains against the baseline still need a larger evaluation.

See [the Hunter-only retest](../v1/TESTING.md#v121-hunter-only-smoke-tests) for the v1.2.1 checks.
