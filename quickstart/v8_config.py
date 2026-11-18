"""Validated single-file v8 configuration. No credentials stored here."""
from __future__ import annotations
import json
import re
from pathlib import Path

DEFAULT = Path(__file__).resolve().parents[1] / "config" / "manhunt_v8.json"


def load_config(path: Path | str = DEFAULT) -> dict:
    source = Path(path)
    data = json.loads(source.read_text(encoding="utf-8"))
    for section in ("game", "tracking", "inventory", "resources", "scoring"):
        if not isinstance(data.get(section), dict):
            raise ValueError(f"Missing v8 config section: {section}")
    game, track, inv, resources = (data[k] for k in ("game", "tracking", "inventory", "resources"))
    if game.get('default_human_role') not in ('hunter', 'runner'):
        raise ValueError('default_human_role must be hunter or runner')
    if game.get('hit_to_win') is not True:
        raise ValueError('v8 currently supports hit-to-win only')
    if not isinstance(inv.get('save_between_matches'), bool):
        raise ValueError('save_between_matches must be a boolean')
    if not (0 <= game["head_start_seconds"] <= 300 and 15 <= game["survival_seconds"] <= 86400):
        raise ValueError("Invalid game duration")
    if track["mode"] != "coordinates":
        raise ValueError("v8 supports coordinates tracking only; compass writes are not implemented")
    if not (5 <= track["range_blocks"] <= 2048 and 1 <= track["cooldown_seconds"] <= 120
            and 0 <= track["last_known_seconds"] <= 300):
        raise ValueError("Invalid tracking limits")
    if inv["slots"] != 36 or not 0.5 <= inv["poll_seconds"] <= 60:
        raise ValueError("v8 mirrors 36 vanilla main inventory slots")
    if not (4 <= resources["cooldown_seconds"] <= 3600 and
            5 <= resources["minimum_distance_from_hunter"] <= 1000 and
            1 <= resources["target_log_count"] <= 64):
        raise ValueError("Invalid resource settings")
    if not 2 <= resources.get("search_radius",4) <= 5 or not 8 <= resources.get("objective_timeout",18) <= 30:
        raise ValueError("Invalid resource objective limits")
    from .block_breaking import mineable
    if not isinstance(resources["allowed_blocks"], list) or not resources["allowed_blocks"]:
        raise ValueError("allowed_blocks must be a nonempty list")
    if any(not isinstance(s, str) or not re.fullmatch(r"[a-z0-9_]+", s) or not mineable(s) for s in resources["allowed_blocks"]):
        raise ValueError("Unsafe/non-mineable resource in config")
    return data
