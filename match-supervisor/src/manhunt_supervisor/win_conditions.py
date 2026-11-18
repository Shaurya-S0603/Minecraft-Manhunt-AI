from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(slots=True)
class WinResult:
    winner: Optional[str]
    reason: str
    finished: bool


def evaluate_win_condition(
    *,
    runner_survival_seconds: float,
    required_survival_seconds: float,
    runner_alive: bool,
    hunter_capture: bool,
    runner_completion: bool,
    hunter_disconnected: bool = False,
) -> WinResult:
    if hunter_capture and runner_alive:
        return WinResult(winner="hunter", reason="capture", finished=True)
    if runner_completion:
        return WinResult(winner="runner", reason="objective-complete", finished=True)
    if runner_survival_seconds >= required_survival_seconds and runner_alive:
        return WinResult(winner="runner", reason="survival-time", finished=True)
    if hunter_disconnected and runner_alive:
        return WinResult(winner="runner", reason="hunter-disconnected", finished=True)
    return WinResult(winner=None, reason="in-progress", finished=False)
