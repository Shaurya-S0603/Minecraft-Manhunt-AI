"""Generation-aware movement curriculum and conservative held-out model.

All earlier observations remain in the original append-only JSONL logs. V4's
scheduler prioritizes *recent comparable Minecraft episodes*, never cumulative
legacy-success totals. Only new V4 training/validation trials can certify a
new setting for ordinary Manhunt; Mine AI metadata is scheduling advice only.
"""
from __future__ import annotations
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
import json
import math
from pathlib import Path
from typing import Iterable

from .curriculum_v3 import ACTION_GRIDS, _wilson_lower
from .skill_policy import read_episodes

GENERATION = 4
MODEL = 'generation_aware_heldout_curriculum_v4'
RECENT_TRAIN = 100
RECENT_VALIDATION = 40
PRIOR_LIMIT = 40
PRIOR_EFFECTIVE_CAP = 3.0
TRAIN_MIN = 25
VALIDATION_MIN = 20


def current_episode(row: dict) -> bool:
    """Old rows are retained but never mislabeled as V4 experience."""
    return (row.get('source') == 'minecraft' and
            row.get('scheduler_version') == GENERATION and
            row.get('training_generation') == GENERATION and
            isinstance(row.get('session_id'), str) and
            8 <= len(row['session_id']) <= 80)


def comparable(row: dict) -> bool:
    """Physics-comparable history, not necessarily certified V4 evidence."""
    return (row.get('skill') in ACTION_GRIDS and
            (row.get('skill') != 'sprint_jump' or row.get('scorer_version') == 2))


def action_for(row: dict):
    skill = row.get('skill')
    if skill not in ACTION_GRIDS or not comparable(row):
        return None
    value = row.get('requested_offset') if skill == 'sprint_jump' else row.get('parameter')
    if type(value) not in (int, float) or not math.isfinite(float(value)):
        return None
    brake = row.get('brake_after') if skill == 'sprint_jump' else None
    if brake is not None and (type(brake) not in (int,float) or not math.isfinite(float(brake))):
        return None
    key = (round(float(value), 5), brake)
    # Do not relabel historical unknown control settings as known candidates.
    return key if key in ACTION_GRIDS[skill] else None


def validated_candidate(candidate: dict) -> bool:
    """Recheck all stored numerical gates before activating an action."""
    if not isinstance(candidate,dict): return False
    n,w,vn,vw=(candidate.get('current_train_trials'), candidate.get('current_train_wins'),
                candidate.get('current_validation_trials'), candidate.get('current_validation_wins'))
    if any(type(x) is not int for x in (n,w,vn,vw)): return False
    if not (n>=TRAIN_MIN and vn>=VALIDATION_MIN and 0<=w<=n and 0<=vw<=vn):return False
    if w/n<.75 or vw/vn<.80:return False
    if _wilson_lower(w,n)<.60 or _wilson_lower(vw,vn)<.58:return False
    # Current training success and current held-out success, not historical pseudo-evidence.
    return True


def fit_v4(log: Path, *, research_profile: dict | None=None) -> dict:
    """Fit ranking from current real trials + capped *historical prior*.

    Candidate choice uses TRAINING observations only. Independent validation
    labels are used solely to accept/reject that prechosen action. A history
    of 1,000 old wins cannot certify a V4 candidate without new tests.
    """
    bucket=defaultdict(lambda:{'train':[],'validation':[],'prior':[]})
    excluded=Counter()
    history_count=0;current_count=0
    sessions=set()
    for row in read_episodes(log,include_validation=True):
        action=action_for(row)
        if action is None:
            excluded['legacy_or_unrecognized_action']+=1
            continue
        skill=row['skill'];gap=row.get('gap',0) if skill=='sprint_jump' else 0
        if skill=='sprint_jump' and gap not in (1,2,3):
            excluded['invalid_gap']+=1;continue
        split=row.get('split','train')
        if split not in ('train','validation'):
            excluded['invalid_split']+=1;continue
        series=bucket[(skill,gap,action)]
        if current_episode(row):
            series[split].append(row)
            sessions.add(row['session_id'])
            current_count+=1
        elif split=='train':
            series['prior'].append(row)
            history_count+=1
        else:
            excluded['old_validation_not_valid_for_v4']+=1
    groups={}
    for skill,actions in ACTION_GRIDS.items():
        for gap in ((1,2,3) if skill=='sprint_jump' else (0,)):
            candidates=[]
            for action in actions:
                data=bucket[(skill,gap,action)]
                recent=data['train'][-RECENT_TRAIN:]
                valid=data['validation'][-RECENT_VALIDATION:]
                prior=data['prior'][-PRIOR_LIMIT:]
                n=len(recent); w=sum(r['success'] for r in recent)
                vn=len(valid);vw=sum(r['success'] for r in valid)
                prior_n=len(prior);prior_w=sum(r['success'] for r in prior)
                prior_rate=prior_w/prior_n if prior_n else None
                prior_eff=min(PRIOR_EFFECTIVE_CAP,prior_n*.10)
                # Historical data is at most 3 effective examples for ranking,
                # and zero examples for live certification.
                blended=(w + (prior_rate or 0)*prior_eff)/(n+prior_eff) if n+prior_eff else 0.
                lower=_wilson_lower(w,n)
                v_lower=_wilson_lower(vw,vn)
                recent_duration=[float(r['duration_s']) for r in recent if r['success']]
                mean_duration=sum(recent_duration)/len(recent_duration) if recent_duration else None
                score=(.60*lower+.32*blended+.08*(prior_rate or 0)
                       - .025*min(1.,(mean_duration or 9.)/9.)) if n else 0.03*(prior_rate or 0)
                failures=Counter(str(r.get('reason','unknown')) for r in recent if not r['success'])
                candidate={
                    'offset_or_parameter':action[0],'brake_after':action[1],
                    'current_train_trials':n,'current_train_wins':w,
                    'current_train_rate':round(w/n,4) if n else None,
                    'current_train_lower_95':round(lower,4),
                    'current_validation_trials':vn,'current_validation_wins':vw,
                    'current_validation_rate':round(vw/vn,4) if vn else None,
                    'current_validation_lower_95':round(v_lower,4),
                    'historical_comparable_trials':len(data['prior']),
                    'historical_prior_examples_used':round(prior_eff,2),
                    'rolling_train_window':RECENT_TRAIN,
                    'rolling_validation_window':RECENT_VALIDATION,
                    'successful_attempt_mean_seconds':round(mean_duration,3) if mean_duration is not None else None,
                    'train_score':round(score,5),
                    'recent_failures':dict(failures.most_common(4)),
                }
                candidate['live_eligible']=validated_candidate(candidate)
                candidates.append(candidate)
            # Avoid validation-set selection bias: choose the one strongest
            # current TRAINING candidate before looking at validation labels.
            trained=[c for c in candidates if c['current_train_trials']>=TRAIN_MIN]
            best=max(trained,key=lambda c:(c['train_score'],c['current_train_trials'],
                                            -actions.index((c['offset_or_parameter'],c['brake_after'])))) if trained else None
            accepted=best if best and best['live_eligible'] else None
            if best is None:
                status='insufficient_current_training'
            elif not accepted:
                status=('insufficient_recent_validation' if best['current_validation_trials']<VALIDATION_MIN
                        else 'heldout_or_training_threshold_failed')
            else:
                status='certified_on_current_train_and_heldout'
            groups[f'{skill}:{gap}']={
                'skill':skill,'gap':gap,'selected':({'offset_or_parameter':accepted['offset_or_parameter'],
                                                    'brake_after':accepted['brake_after']} if accepted else None),
                'training_candidate':({'offset_or_parameter':best['offset_or_parameter'],
                                       'brake_after':best['brake_after']} if best else None),
                'validated_for_live':bool(accepted),'status':status,
                'candidates':candidates,'current_train_trials':sum(c['current_train_trials'] for c in candidates),
                'current_validation_trials':sum(c['current_validation_trials'] for c in candidates),
            }
    return {
        'schema':4,'model':MODEL,'source':'observed_minecraft_trials',
        'generation':4,'current_episodes':current_count,'historical_comparable_episodes':history_count,
        'sessions':len(sessions),'groups':groups,'excluded':dict(excluded),
        'research':{'records':int((research_profile or {}).get('records',0)),
                    'role':'bounded_scheduler_hint_only'},
        'eligibility':('Action selected by current training results; live activation requires '
                       '25 recent training trials and 20 recent separate validation trials, '
                       '>=80% held-out success and Wilson lower bound >=58%. '
                       'Old scores are limited to three effective ranking observations '
                       'and never count toward certification.')
    }


def save_v4(policy:dict,path:Path):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(policy,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    tmp.replace(path)


def load_v4(path:Path)->dict|None:
    try:
        if path.stat().st_size>2_000_000:return None
        data=json.loads(path.read_text(encoding='utf-8'))
        if (isinstance(data,dict) and data.get('schema')==4 and
            data.get('model')==MODEL and data.get('source')=='observed_minecraft_trials' and
            isinstance(data.get('groups'),dict)):
            return data
    except (OSError,ValueError,TypeError,AttributeError):
        pass
    return None


def choose_v4_action(policy:dict|None,skill:str,gap:int,episode:int,*,validation:bool=False):
    """Select held-out action only using current TRAINING scores (no leakage)."""
    actions=ACTION_GRIDS[skill]
    group=(policy or {}).get('groups',{}).get(f'{skill}:{gap}',{})
    candidates=group.get('candidates',[])
    contenders=[c for c in candidates if c.get('current_train_trials',0)>=6]
    if validation and contenders:
        c=max(contenders,key=lambda c:(c.get('train_score',0),c.get('current_train_trials',0)))
        action=(c['offset_or_parameter'],c['brake_after'])
        if action in actions:return action
    # Guaranteed coverage for untested actions, without treating old records
    # as if they were current successful episodes.
    if not candidates or episode%5==0:
        return actions[(episode-1)%len(actions)]
    table={(c['offset_or_parameter'],c['brake_after']):c for c in candidates}
    if episode%3==0:
        return min(actions,key=lambda a:(table.get(a,{}).get('current_train_trials',0),actions.index(a)))
    return max(actions,key=lambda a: (table.get(a,{}).get('train_score',0) +
                                    .30/math.sqrt(table.get(a,{}).get('current_train_trials',0)+1),
                                    -actions.index(a)))


@dataclass
class _Stats:
    current: deque=field(default_factory=lambda:deque(maxlen=RECENT_TRAIN))
    prior:deque=field(default_factory=lambda:deque(maxlen=PRIOR_LIMIT))

    def rate(self)->float:
        n=len(self.current)
        prior_rate=sum(self.prior)/len(self.prior) if self.prior else .5
        prior_n=min(PRIOR_EFFECTIVE_CAP,len(self.prior)*.10)
        return (sum(self.current)+prior_rate*prior_n)/(n+prior_n) if n+prior_n else .5

    def evidence(self)->float:
        return len(self.current)+min(PRIOR_EFFECTIVE_CAP,len(self.prior)*.10)


class GenerationScheduler:
    """Recent V4 performance dominates; older corrected history weakly warms up."""
    def __init__(self, stages, history:Path,*, research_profile:dict|None=None,
                 validation_every:int=5):
        if not 2<=validation_every<=20:raise ValueError('Validation cadence out of range')
        self.stages=tuple(stages)
        if not self.stages:raise ValueError('No selected stages')
        self.profile=research_profile or {}
        self.validation_every=validation_every
        self.stats={s.name:_Stats() for s in self.stages}
        self.attempts={s.name:0 for s in self.stages}  # chronological index incl old rows
        self.session_attempts={s.name:0 for s in self.stages}
        self.total=0;self.previous=None;self.streak=0
        for row in read_episodes(history,include_validation=True):
            name=row.get('base_stage',row.get('stage'))
            if name not in self.stats:continue
            self.attempts[name]+=1
            if row.get('split','train')!='train':continue
            if not comparable(row):continue
            if current_episode(row):
                self.stats[name].current.append(int(row['success']))
            else:
                self.stats[name].prior.append(int(row['success']))

    def record(self,stage,success:bool,*,validation:bool=False):
        self.attempts[stage.name]+=1
        self.session_attempts[stage.name]+=1
        if not validation:self.stats[stage.name].current.append(int(bool(success)))
        self.total+=1
        self.streak=self.streak+1 if self.previous==stage.name else 1
        self.previous=stage.name

    def next(self):
        bias=self.profile.get('curriculum_bias',{})
        scores=[]
        for stage in self.stages:
            state=self.stats[stage.name]
            evidence=state.evidence()
            rate=state.rate()
            need=.62*(1.-rate)+.38/math.sqrt(evidence+1.)+.10/(evidence+1.)
            if self.previous==stage.name:
                need*=.15 if self.streak>=3 else .73
            research_bias=bias.get(stage.skill,0.)
            if type(research_bias) not in (int,float) or not math.isfinite(float(research_bias)):
                research_bias=0.
            need*=1+min(.08,max(0.,float(research_bias)))
            scores.append((need,-len(state.current),-self.stages.index(stage),stage))
        quota=math.floor((self.total+1)*min(.10,.60/len(self.stages)))
        deficit=[s for s in self.stages if self.session_attempts[s.name]<quota]
        chosen=(min(deficit,key=lambda s:(self.session_attempts[s.name],self.stages.index(s))) if deficit
                else max(scores,key=lambda x:x[:3])[3])
        validation=(self.total+1)%self.validation_every==0
        return chosen,self.attempts[chosen.name]+1,validation
