from __future__ import annotations

from typing import Any

from .hunter import HunterPolicy
from .runner import RunnerPolicy

SUPPORTED_ROLES = {"hunter", "runner"}


def build_agent(role: str, difficulty: str = "normal") -> Any:
    normalized = str(role).strip().lower()
    if normalized == "hunter":
        return HunterPolicy(difficulty=difficulty)
    if normalized == "runner":
        return RunnerPolicy(difficulty=difficulty)
    raise ValueError(f"Unsupported role: {role!r}")
