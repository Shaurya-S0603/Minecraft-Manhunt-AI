"""Small auditable movement policy trained from *observed* Carpet trials.

Inspired by RL-env's state/action/reward methodology. This is a contextual
bandit trained with outcome feedback, NOT a downloaded PPO/DQN checkpoint.
The existing pathfinder's safety and proof-of-success limits always apply.
"""
from __future__ import annotations
import json
import math
from pathlib import Path
from typing import Iterable

OFFSETS=(0.12,0.20,0.28,0.36)
MIN_SUCCESS=4


def offset_bucket(v: float) -> float:
    return min(OFFSETS, key=lambda x: abs(x-v))


def _valid_trial(record: dict) -> bool:
    """Reject corrupt, synthetic, non-jump, and implausibly sparse records."""
    if record.get('skill') != 'sprint_jump' or type(record.get('success')) is not bool:
        return False
    if type(record.get('gap')) is not int or record['gap'] not in (1,2,3):
        return False
    if record.get('split','train')!='train':return False
    if record.get('source','minecraft') != 'minecraft':
        return False
    try:
        offset=float(record['launch_offset'])
        duration=float(record['duration_s'])
        trajectory=record['trajectory']
        if not (math.isfinite(offset) and -.05 <= offset <= .75 and
                math.isfinite(duration) and .2 <= duration <= 8.0 and
                isinstance(trajectory,list) and len(trajectory)>=2):
            return False
        if not all(isinstance(p,list) and len(p)==4 and all(math.isfinite(float(v)) for v in p)
                   for p in trajectory):
            return False
    except (TypeError,ValueError,KeyError,OverflowError):
        return False
    return True


def training_records(log_file: Path) -> Iterable[dict]:
    if not log_file.exists():
        return
    if log_file.stat().st_size > 512_000_000:
        raise ValueError('Movement log over training size limit; rotate older logs first')
    with log_file.open(encoding='utf-8') as f:
        for line in f:
            try:
                record=json.loads(line)
                if isinstance(record,dict) and _valid_trial(record):
                    yield record
            except (ValueError, TypeError):
                continue


def _score(wins: int, losses: int) -> float:
    n=wins+losses
    # Beta(1,1) posterior mean with a limited-sample uncertainty penalty.
    return (wins+1)/(n+2) - .15/math.sqrt(max(1,n))


def train_from_log(log_file: Path) -> dict:
    """Fit launch offsets from successful/failed real trials, not guesses.

    Emits safe metadata even with no data. Only a group with >=4 wins and
    >=75% empirical success can become eligible for live threshold selection.
    """
    groups={}
    rows=list(training_records(log_file))
    for gap in (1,2,3):
        attempts=[r for r in rows if r['gap']==gap]
        candidate=[]
        for offset in OFFSETS:
            nearby=[r for r in attempts if offset_bucket(float(r['launch_offset']))==offset]
            wins=sum(r['success'] for r in nearby)
            failures=len(nearby)-wins
            eligible=wins>=MIN_SUCCESS and wins/len(nearby)>=.75 if nearby else False
            candidate.append({'offset':offset,'wins':wins,'failures':failures,
                              'score':round(_score(wins,failures),5),'eligible':eligible})
        eligible=[c for c in candidate if c['eligible']]
        best=max(eligible,key=lambda c:(c['score'],c['wins'],-c['offset'])) if eligible else None
        groups[str(gap)]={'trials':len(attempts), 'candidates':candidate,
                          'selected_offset':best['offset'] if best else None}
    return {'schema':1,'source':'observed_minecraft_trials',
            'model':'beta_smoothed_contextual_bandit',
            'records':len(rows),'groups':groups}


def save_policy(policy: dict, path: Path):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(policy,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    tmp.replace(path)


def load_policy(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        d=json.loads(path.read_text(encoding='utf-8'))
        if d.get('schema')!=1 or d.get('source')!='observed_minecraft_trials':
            return None
        return d
    except (ValueError,KeyError,TypeError):
        return None


def offset_for_gap(policy: dict | None, gap: int, fallback: float) -> float:
    if not policy:
        return fallback
    try:
        group=policy['groups'][str(gap)]
        raw=group.get('selected_offset')
        if type(raw) in (int,float) and math.isfinite(raw) and raw in OFFSETS:
            return float(raw)
    except (KeyError,TypeError,ValueError):
        pass
    return fallback
