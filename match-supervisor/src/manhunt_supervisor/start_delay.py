from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(slots=True)
class StartDelay:
    seconds: int = 0
    remaining: int = 0
    active: bool = False

    def validate(self) -> None:
        if self.seconds < 0:
            raise ValueError("Start delay cannot be negative")

    def start(self) -> int:
        self.validate()
        self.active = True
        self.remaining = self.seconds
        return self.remaining

    def tick(self) -> int:
        if not self.active:
            return self.remaining
        self.remaining = max(0, self.remaining - 1)
        if self.remaining == 0:
            self.active = False
        return self.remaining


def compute_delay(seconds: int) -> StartDelay:
    delay = StartDelay(seconds=seconds, remaining=seconds)
    delay.validate()
    return delay
