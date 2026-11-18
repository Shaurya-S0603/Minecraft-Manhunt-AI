from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set


class MatchPhase(str, Enum):
    SETUP = "SETUP"
    WORLD_READY = "WORLD_READY"
    HEAD_START = "HEAD_START"
    ACTIVE = "ACTIVE"
    FINISHED = "FINISHED"
    RESET = "RESET"


@dataclass(slots=True)
class MatchState:
    phase: MatchPhase = MatchPhase.SETUP
    head_start_seconds: int = 0
    winner: Optional[str] = None
    runner_survival_seconds: float = 0.0
    history: List[MatchPhase] = field(default_factory=list)

    _allowed: Dict[MatchPhase, Set[MatchPhase]] = field(
        default_factory=lambda: {
            MatchPhase.SETUP: {MatchPhase.WORLD_READY, MatchPhase.RESET},
            MatchPhase.WORLD_READY: {MatchPhase.HEAD_START, MatchPhase.RESET},
            MatchPhase.HEAD_START: {MatchPhase.ACTIVE, MatchPhase.RESET},
            MatchPhase.ACTIVE: {MatchPhase.FINISHED, MatchPhase.RESET},
            MatchPhase.FINISHED: {MatchPhase.RESET},
            MatchPhase.RESET: {MatchPhase.SETUP},
        },
        init=False,
    )

    def __post_init__(self) -> None:
        if not self.history:
            self.history = [self.phase]

    def transition_to(self, next_phase: MatchPhase | str) -> MatchPhase:
        target = MatchPhase(next_phase) if isinstance(next_phase, str) else next_phase
        if target not in self._allowed.get(self.phase, set()):
            raise ValueError(f"Invalid phase transition: {self.phase.value} -> {target.value}")
        self.phase = target
        self.history.append(target)
        if target == MatchPhase.FINISHED:
            self.winner = self.winner or "unknown"
        return self.phase

    def set_head_start(self, seconds: int) -> int:
        if seconds < 0:
            raise ValueError("Head start cannot be negative")
        self.head_start_seconds = seconds
        return seconds

    def mark_winner(self, winner: str) -> str:
        if winner not in {"hunter", "runner"}:
            raise ValueError("Winner must be 'hunter' or 'runner'")
        self.winner = winner
        self.phase = MatchPhase.FINISHED
        return winner

    def is_terminal(self) -> bool:
        return self.phase == MatchPhase.FINISHED
