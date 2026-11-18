from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Mapping, MutableMapping


DEFAULT_WEIGHTS = {
    "spawn_safety": 0.20,
    "resource_access": 0.20,
    "terrain_diversity": 0.20,
    "structure_quality": 0.15,
    "navigation": 0.15,
    "objective_access": 0.10,
}


@dataclass(slots=True)
class SeedScore:
    total: float
    breakdown: Dict[str, float]
    version: str = "1.0"


def score_seed(features: Mapping[str, float], weights: Mapping[str, float] | None = None) -> SeedScore:
    profile = dict(DEFAULT_WEIGHTS)
    if weights:
        for key, value in weights.items():
            profile[key] = value

    required = set(profile)
    missing = required - set(features)
    if missing:
        raise ValueError(f"Missing score features: {sorted(missing)}")

    breakdown: Dict[str, float] = {}
    total = 0.0
    for key, weight in profile.items():
        value = float(features[key])
        if value < 0.0 or value > 1.0:
            raise ValueError(f"Feature {key} must be between 0.0 and 1.0")
        breakdown[key] = value
        total += value * weight

    return SeedScore(total=round(total, 6), breakdown=breakdown)
