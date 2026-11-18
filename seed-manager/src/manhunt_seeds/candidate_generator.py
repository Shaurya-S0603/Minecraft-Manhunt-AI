from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Sequence


@dataclass(slots=True)
class CandidateSeed:
    value: int
    source: str = "random"


def generate_candidates(count: int, *, start_seed: int = 0, seed_history: Optional[Sequence[int]] = None) -> List[int]:
    if count < 0:
        raise ValueError("Candidate count cannot be negative")
    if count == 0:
        return []

    history = set(seed_history or [])
    generated: List[int] = []
    current = int(start_seed)
    while len(generated) < count:
        if current not in history:
            generated.append(current)
            history.add(current)
        current += 1
    return generated


def generate_random_candidates(count: int, *, rand: Optional[random.Random] = None) -> List[int]:
    rng = rand or random.Random()
    return [rng.randint(-2**31, 2**31 - 1) for _ in range(count)]
