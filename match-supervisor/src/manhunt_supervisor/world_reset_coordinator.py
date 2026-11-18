from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class ResetPlan:
    world_root: Path
    archive_path: Path
    ready: bool
    reason: str = ""


class WorldResetCoordinator:
    def __init__(self, root_dir: str, archive_dir: str):
        self.root_dir = Path(root_dir).resolve()
        self.archive_dir = Path(archive_dir).resolve()

    def validate(self, world_name: str) -> ResetPlan:
        if not self.root_dir.exists():
            raise FileNotFoundError(f"Root directory does not exist: {self.root_dir}")
        candidate = (self.root_dir / world_name).resolve()
        if self.root_dir not in candidate.parents and candidate != self.root_dir:
            raise ValueError("World path escapes the allowed root")
        archive = (self.archive_dir / f"{world_name}.bak").resolve()
        return ResetPlan(world_root=candidate, archive_path=archive, ready=True)

    def prepare_reset(self, world_name: str) -> ResetPlan:
        return self.validate(world_name)
