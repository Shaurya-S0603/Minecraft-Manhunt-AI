"""Geometry-aware parkour evaluation and bounded learned jump settings.

v2 labels require a real *grounded* landing inside the actual platform.
Older point-target labels remain available for auditing, but cannot certify
this corrected scorer. No synthetic outcomes can create a live policy.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from collections import defaultdict
import json, math
from .observations import Position

OFFSETS=(0.12,0.20,0.28,0.36)
BRAKE_AFTER=(None,0.6,1.5)  # relative to near edge of landing platform


@dataclass(frozen=True)
class LandingZone:
    start: Position  # first block centre on landing platform
    direction_x: float
    direction_z: float
    length: float = 0.9  # 0.9 = default single landing block
    half_width: float = 0.5

    def progress(self, p: Position):
        return ((p.x-self.start.x)*self.direction_x +
                (p.z-self.start.z)*self.direction_z)

    def sideways(self,p: Position):
        return abs((p.x-self.start.x)*self.direction_z-
                   (p.z-self.start.z)*self.direction_x)

    def contains(self,p: Position):
        # Feet centre >= 0.20 inside the first block and at least 0.20 before
        # the far lip (body width 0.6); no point-only landing labels.
        return (-0.20 <= self.progress(p) <= self.length-0.30 and
                self.sideways(p) <= self.half_width and
                abs(p.y-self.start.y) <= .25)

    def classification(self,p:Position):
        if p.y < self.start.y-0.5: return 'fell_below_platform'
        if self.sideways(p)>self.half_width:return 'lateral_miss'
        along=self.progress(p)
        if along < -0.20:return 'undershoot'
        if along > self.length-0.30:return 'overshoot'
        return 'landed' if abs(p.y-self.start.y)<=.25 else 'wrong_elevation'


def zone_for_stage(stage):
    dx=stage.target.x-stage.takeoff.x
    dz=stage.target.z-stage.takeoff.z
    magnitude=math.hypot(dx,dz)
    if magnitude<=0:return None
    return LandingZone(stage.target,dx/magnitude,dz/magnitude,
                       stage.landing_length,stage.landing_half_width)


def classify_jump(zone:LandingZone,pos:Position,*,grounded:bool,airborne_seen:bool,
                  duration:float,lower_limit:float=0.75):
    """Returns (finished, success, reason) based on observed physics."""
    if not airborne_seen: return (False,False,'in_flight')
    if grounded and duration >= .2:
        reason=zone.classification(pos)
        return (True, reason=='landed', reason)
    if pos.y < zone.start.y-lower_limit:
        return (True,False,'fell_below_platform')
    return (False,False,'in_flight')


def read_v2_trials(path:Path):
    if not path.is_file():return
    if path.stat().st_size>512_000_000:
        raise ValueError('Movement log too large for training; rotate old logs')
    with path.open(encoding='utf8') as stream:
        for line in stream:
            try:
                d=json.loads(line)
                if (d.get('split','train')=='train' and d.get('scorer_version')==2 and d.get('source')=='minecraft' and
                    d.get('skill')=='sprint_jump' and type(d.get('success')) is bool and
                    type(d.get('gap')) is int and d['gap'] in (1,2,3) and
                    d.get('platform_scoring_v2') is True and
                    isinstance(d.get('trajectory'),list) and len(d['trajectory'])>=3 and
                    d.get('brake_after') in (None,0.6,1.5) and
                    type(d.get('launch_offset')) in (int,float) and
                    math.isfinite(d['launch_offset'])):
                    yield d
            except (ValueError,TypeError,AttributeError):
                continue


def fit_v2(path:Path):
    """Empirical contextual bandit over launch offset AND midair braking.

    Validates >=6 successes and >=75% success per candidate. Each gap uses
    independent evidence; doesn't self-certify from legacy point scoring.
    """
    rows=list(read_v2_trials(path))
    stats=defaultdict(lambda:[0,0,0.])
    for row in rows:
        gap=row['gap']; offset=min(OFFSETS,key=lambda v:abs(v-row['launch_offset']))
        brake=row['brake_after']
        key=(gap,offset,brake)
        stats[key][0]+=int(row['success'])
        stats[key][1]+=1
        stats[key][2]+=float(row.get('duration_s') or 0)
    groups={}
    for gap in (1,2,3):
        candidates=[]
        for offset in OFFSETS:
            for brake in BRAKE_AFTER:
                wins,n,seconds=stats[(gap,offset,brake)]
                eligible=n>=8 and wins>=6 and wins/n>=.75
                # Conservative posterior ranking and small sample penalty.
                quality=(wins+1)/(n+2)-0.2/math.sqrt(n+1)
                candidates.append({'offset':offset,'brake_after':brake,'wins':wins,'trials':n,
                                   'score':round(quality,5),'eligible':eligible})
        permitted=[c for c in candidates if c['eligible']]
        best=max(permitted,key=lambda c:(c['score'],c['wins'])) if permitted else None
        groups[str(gap)]={'trials':sum(c['trials'] for c in candidates),
                          'selected':{'offset':best['offset'],'brake_after':best['brake_after']} if best else None,
                          'candidates':candidates}
    return {'schema':2,'model':'platform_verified_jump_bandit','source':'observed_minecraft_trials',
            'records':len(rows),'groups':groups,
            'limitations':'Only v2 platform-verified observations count; historical labels excluded.'}


def choose_training_action(policy:dict|None,gap:int,episode:int):
    pairs=[(a,b) for a in OFFSETS for b in BRAKE_AFTER]
    # 1 in 5 trials explores, all other trials use any eligible best policy.
    if episode%5==0 or not policy:
        return pairs[(episode-1)%len(pairs)]
    selected=(policy.get('groups') or {}).get(str(gap),{}).get('selected')
    if (isinstance(selected,dict) and
        (selected.get('offset'),selected.get('brake_after')) in pairs):
        return selected['offset'],selected['brake_after']
    return pairs[(episode-1)%len(pairs)]


def save_v2(policy:dict,path:Path):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(policy,indent=2,sort_keys=True)+'\n',encoding='utf8')
    tmp.replace(path)


def load_v2(path:Path):
    if not path.is_file():return None
    try:
        policy=json.loads(path.read_text(encoding='utf8'))
        if (policy.get('schema')==2 and policy.get('model')=='platform_verified_jump_bandit' and
                policy.get('source')=='observed_minecraft_trials'):
            return policy
    except (ValueError,TypeError,AttributeError):
        pass
    return None
