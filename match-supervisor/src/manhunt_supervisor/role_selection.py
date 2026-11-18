from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(slots=True)
class RoleAssignment:
    human: str
    ai: str
    resolved: Dict[str, str]


def assign_roles(human_role: Optional[str], ai_role: Optional[str], *, allow_ai_vs_ai: bool = False) -> RoleAssignment:
    normalized_human = (human_role or "").strip().lower()
    normalized_ai = (ai_role or "").strip().lower()

    if not normalized_human and not normalized_ai:
        raise ValueError("At least one role must be supplied")
    if normalized_human not in {"hunter", "runner"}:
        raise ValueError(f"Invalid human role: {human_role!r}")
    if normalized_ai and normalized_ai not in {"hunter", "runner"}:
        raise ValueError(f"Invalid AI role: {ai_role!r}")

    if normalized_human == normalized_ai and not allow_ai_vs_ai:
        raise ValueError("Human and AI roles must not be identical unless AI-vs-AI is explicitly enabled")

    resolved = {"human": normalized_human}
    if normalized_ai:
        resolved["ai"] = normalized_ai
    return RoleAssignment(human=normalized_human, ai=normalized_ai, resolved=resolved)
