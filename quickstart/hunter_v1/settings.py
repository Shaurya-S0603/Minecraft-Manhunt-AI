"""Strict validation for the public hunter configuration."""
import json
from pathlib import Path

DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "config" / "hunter_v1.json"
BOUNDS = {
    "game": {
        "win_mode": ("dragon", "hit"),
        "head_start_seconds": (0, 300),
        "time_limit_seconds": (15, 21600),
        "respawn_seconds": (5, 120),
        "hunter_respawns": (0, 25),
    },
    "tracking": {
        "range_blocks": (32, 2048), "sample_seconds": (2, 30),
        "visible_blocks": (5, 32), "trail_seconds": (5, 120),
    },
    "resources": {"enabled": bool, "crafting": bool, "safe_distance": (8, 128),
                  "build": bool, "water_bridge": bool, "lava_bridge": bool,
                  "allow_transfers": bool},
    "learning": {"enabled": bool, "rate": (0.01, 1.0), "max_entries": (16, 4096),
                 "exploration": (0.0, 2.0), "opening_seconds": (2, 30),
                 "tag_bonus_seconds": (10, 300)},
    "scoring": {"win": (0, 100), "loss": (0, 100), "first_tag": (0, 100)},
}


def load_settings(path=DEFAULT_CONFIG):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Manhunt config must be a JSON object")
    defaults = {"resources": {"water_bridge": False, "allow_transfers": False},
                "learning": {"opening_seconds": 9, "tag_bonus_seconds": 45},
                "scoring": {"win": 3, "loss": 0, "first_tag": 1}}
    data.setdefault("scoring", {})
    if data.keys() != BOUNDS.keys():
        raise ValueError("Config requires game, tracking, resources, learning and scoring objects")
    game = data["game"]
    if isinstance(game, dict) and game.pop("human_role", "runner") != "runner":
        raise ValueError("The human plays Runner in this release. Remove game.human_role from your config.")
    for section, values in defaults.items():
        if isinstance(data[section], dict):
            for key, value in values.items():
                data[section].setdefault(key, value)
    for section, fields in BOUNDS.items():
        values = data[section]
        if not isinstance(values, dict) or values.keys() != fields.keys():
            raise ValueError(f"Check config keys in {section} against config/hunter_v1.json")
        for key, bounds in fields.items():
            value = values[key]
            if bounds is bool:
                valid = type(value) is bool
            elif key == "win_mode":
                valid = value in bounds
            else:
                types = (int, float) if isinstance(bounds[0], float) else (int,)
                valid = type(value) in types and bounds[0] <= value <= bounds[1]
            if not valid:
                raise ValueError(f"Invalid {section}.{key}: {value!r}")
    if data["tracking"]["trail_seconds"] < data["tracking"]["sample_seconds"]:
        raise ValueError("Trail lifetime must be at least one compass sample interval")
    return data
