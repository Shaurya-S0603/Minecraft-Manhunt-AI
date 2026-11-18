from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional, Set


class MatchPhase(str, Enum):
    SETUP = "SETUP"
    WORLD_READY = "WORLD_READY"
    HEAD_START = "HEAD_START"
    ACTIVE = "ACTIVE"
    FINISHED = "FINISHED"
    RESET = "RESET"


class StateMachine:
    """Small match-state machine for game phases and transition safety."""

    ALLOWED_TRANSITIONS: Dict[MatchPhase, Set[MatchPhase]] = {
        MatchPhase.SETUP: {MatchPhase.WORLD_READY, MatchPhase.RESET},
        MatchPhase.WORLD_READY: {MatchPhase.HEAD_START, MatchPhase.RESET},
        MatchPhase.HEAD_START: {MatchPhase.ACTIVE, MatchPhase.RESET},
        MatchPhase.ACTIVE: {MatchPhase.FINISHED, MatchPhase.RESET},
        MatchPhase.FINISHED: {MatchPhase.RESET},
        MatchPhase.RESET: {MatchPhase.SETUP},
    }

    def __init__(self, initial_phase: MatchPhase | str = MatchPhase.SETUP):
        self.phase = MatchPhase(initial_phase) if isinstance(initial_phase, str) else initial_phase
        self.history: List[MatchPhase] = [self.phase]
        self.head_start_seconds = 0

    def transition_to(self, phase: MatchPhase | str) -> MatchPhase:
        next_phase = MatchPhase(phase) if isinstance(phase, str) else phase
        if next_phase == self.phase:
            return self.phase
        if next_phase not in self.ALLOWED_TRANSITIONS.get(self.phase, set()):
            raise ValueError(f"Invalid phase transition from {self.phase.value} to {next_phase.value}")
        self.phase = next_phase
        self.history.append(next_phase)
        if next_phase == MatchPhase.HEAD_START:
            self.head_start_seconds = max(self.head_start_seconds, 0)
        return self.phase

    def start_head_start(self, seconds: int = 0) -> MatchPhase:
        if seconds < 0:
            raise ValueError("Head-start seconds cannot be negative")
        self.head_start_seconds = seconds
        return self.transition_to(MatchPhase.HEAD_START)

    def finish(self) -> MatchPhase:
        return self.transition_to(MatchPhase.FINISHED)

    def reset(self) -> MatchPhase:
        self.head_start_seconds = 0
        return self.transition_to(MatchPhase.RESET)

    def can_move(self) -> bool:
        return self.phase in {MatchPhase.HEAD_START, MatchPhase.ACTIVE, MatchPhase.FINISHED}

    def current(self) -> MatchPhase:
        return self.phase
