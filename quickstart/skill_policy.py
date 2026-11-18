"""Small multi-skill, tabular outcome-learning policy for physical Minecraft trials.

No fake/synthetic results accepted. Options are independent within each real skill.
This is not a general neural network; it learns reproducible action settings.
"""
from __future__ import annotations
from collections import defaultdict
import json
import math
from pathlib import Path

OPTIONS = {
    'swim': (-0.35, 0.0, 0.35),  # eye-target pitch bias (blocks)
    'climb': (0.45, 0.95, 1.45),  # aim height relative to bot feet (blocks)
}


def valid_episode(item: dict) -> bool:
    if not isinstance(item, dict) or item.get('source') != 'minecraft':
        return False
    if item.get('skill') not in ('sprint_jump', 'swim', 'climb') or type(item.get('success')) is not bool:
        return False
    try:
        samples=item['samples']
        duration=float(item['duration_s'])
        if not (isinstance(samples,list) and len(samples)>=2 and 0<=duration<=25 and math.isfinite(duration)):
            return False
        if not all(isinstance(p,list) and len(p)==4 and all(math.isfinite(float(v)) for v in p) for p in samples):
            return False
        return isinstance(item.get('stage'),str) and 0<len(item['stage'])<=60
    except (ValueError,TypeError,KeyError,OverflowError):
        return False


def read_episodes(path:Path, *, include_validation:bool=False):
    if not path.exists():
        return
    if path.stat().st_size>512_000_000:
        raise ValueError('Training log over 512 MB; rotate before loading')
    with path.open(encoding='utf-8') as f:
        for line in f:
            try:
                item=json.loads(line)
                if valid_episode(item) and (include_validation or item.get('split','train')=='train'):
                    yield item
            except (ValueError,TypeError):
                continue


def train_skill_policy(path:Path) -> dict:
    counts=defaultdict(lambda:defaultdict(lambda:[0,0,0.0]))
    total=0
    for item in read_episodes(path):
        total+=1
        skill=item['skill']
        if skill not in OPTIONS:
            continue
        try:
            option=float(item['parameter'])
        except (TypeError,ValueError,KeyError):
            continue
        if option not in OPTIONS[skill]:
            continue
        key=str(option)
        entry=counts[skill][key]
        entry[0]+=int(item['success'])
        entry[1]+=1
        entry[2]+=float(item['duration_s'])
    groups={}
    for skill,opts in OPTIONS.items():
        arms={}
        for o in opts:
            wins,n,elapsed=counts[skill][str(o)]
            # Conservative Laplace-smoothed score; faster successful trials win ties.
            score=(wins+1)/(n+2)-0.12/math.sqrt(n+1)
            arms[str(o)]={'wins':wins,'trials':n,'avg_seconds':round(elapsed/n,3) if n else None,
                          'score':round(score,5)}
        eligible=[(o,arms[str(o)]) for o in opts if arms[str(o)]['trials']>=8]
        selected=max(eligible,key=lambda t:(t[1]['score'],-(t[1]['avg_seconds'] or 99)))[0] if eligible else None
        groups[skill]={'options':arms,'selected_parameter':selected,
                       'validated_for_live': bool(selected is not None and arms[str(selected)]['wins']>=6 and
                                                  arms[str(selected)]['wins']/arms[str(selected)]['trials']>=0.75)}
    return {'schema':1,'source':'observed_minecraft_trials',
            'model':'per_skill_beta_smoothed_bandit','episodes':total,'groups':groups}


def choose_parameter(policy:dict|None,skill:str,episode:int) -> float:
    opts=OPTIONS[skill]
    # Maintain exploration for better evidence, instead of overfitting a few trials.
    if episode<=len(opts)*4 or episode%10==0:
        return opts[(episode-1)%len(opts)]
    chosen=(policy or {}).get('groups',{}).get(skill,{}).get('selected_parameter')
    if type(chosen) in (int,float) and float(chosen) in opts:
        return float(chosen)
    return opts[(episode-1)%len(opts)]


def save_skill_policy(policy:dict,path:Path):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(policy,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    tmp.replace(path)


def load_skill_policy(path:Path):
    try:
        d=json.loads(path.read_text(encoding='utf-8'))
        if d.get('schema')==1 and d.get('source')=='observed_minecraft_trials':
            return d
    except (OSError,ValueError,TypeError,AttributeError):
        pass
    return None
