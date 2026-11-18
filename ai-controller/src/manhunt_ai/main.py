from __future__ import annotations

import argparse
import signal
import sys
from typing import Optional

from .behavior.state_machine import MatchPhase, StateMachine
from .core.action import Action
from .core.decision_loop import DecisionLoop
from .core.observation import Observation


class ControllerRuntime:
    """Minimal runtime that can be started in tests or local runs."""

    def __init__(self, player_id: str = "ai-1", role: str = "runner", difficulty: str = "normal"):
        self.loop = DecisionLoop(player_id, role, difficulty)
        self.state_machine = StateMachine(MatchPhase.SETUP)
        self._shutdown_requested = False

    def on_signal(self, signum, frame) -> None:
        self._shutdown_requested = True

    def run_once(self, observation: Optional[Observation] = None) -> Optional[Action]:
        if observation is None:
            observation = Observation(
                tick=0,
                player_id=self.loop.context.player_id,
                position=(0.0, 64.0, 0.0),
                dimension="overworld",
                visible_entities={},
            )
        return self.loop.handle_observation(observation)

    def shutdown(self) -> None:
        self.state_machine.transition_to(MatchPhase.RESET)
        self._shutdown_requested = True


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Minecraft Manhunt AI controller")
    parser.add_argument("--player-id", default="ai-1")
    parser.add_argument("--role", choices=["hunter", "runner"], default="runner")
    parser.add_argument("--difficulty", default="normal")
    args = parser.parse_args(argv)

    runtime = ControllerRuntime(args.player_id, args.role, args.difficulty)
    signal.signal(signal.SIGINT, runtime.on_signal)
    signal.signal(signal.SIGTERM, runtime.on_signal)

    try:
        runtime.state_machine.transition_to(MatchPhase.WORLD_READY)
        runtime.state_machine.transition_to(MatchPhase.HEAD_START)
        runtime.state_machine.transition_to(MatchPhase.ACTIVE)
        runtime.run_once()
    finally:
        runtime.shutdown()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
