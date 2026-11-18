"""Append-only v8 round scoring. All points derive from actual match results."""
from __future__ import annotations
import json
import math
import time
from pathlib import Path


def record_v8_score(result, scoring: dict, path: Path) -> dict:
    # Only a completed, verified hit or timer survival earns points.
    if result.winner == 'hunter':
        points = int(scoring['hunter_hit_points'])
    elif result.winner == 'runner':
        points = int(scoring['runner_survival_points']) + max(0, int(result.elapsed_seconds // 30)) * int(scoring['runner_survival_bonus_per_30_seconds'])
    else:
        raise ValueError('Cannot score an incomplete match')
    payload = {'when': time.time(), 'human_role': result.human_role,
               'winner': result.winner, 'seconds': round(result.elapsed_seconds, 2),
               'reason': result.reason, 'points': points}
    target = Path(path)
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('a',encoding='utf-8') as file:
        file.write(json.dumps(payload,sort_keys=True)+'\n')
    return payload
