"""Adaptive, evidence-separated training for the Minecraft Manhunter.

V3 movement weights are learned ONLY from local Minecraft physics outcomes.
Mine AI MCP data contains research observations, not movement labels: it can
modestly affect which skill to examine next, never certify a control setting.
"""
from __future__ import annotations
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
import json
import math
from pathlib import Path
from .skill_policy import read_episodes, OPTIONS
from .jump_training_v2 import OFFSETS, BRAKE_AFTER

MODEL = 'conservative_curriculum_bandit_v3'
ACTION_GRIDS = {
    'sprint_jump': tuple((offset, brake) for offset in OFFSETS for brake in BRAKE_AFTER),
    'swim': tuple((v, None) for v in OPTIONS['swim']),
    'climb': tuple((v, None) for v in OPTIONS['climb']),
}
RESEARCH_SOURCE = 'aibengineering/beat-the-game-minecraft'
CATEGORIES = {'navigation', 'world_observation', 'combat', 'resource_planning', 'memory', 'other_minecraft_action'}


def read_research_profile(path: Path, *, max_bytes: int = 32_000_000) -> dict:
    """Safe aggregate of user-imported Mine AI tool metadata, not episode rewards."""
    counts = Counter()
    actions = Counter()
    errors = Counter()
    if not path.is_file():
        return {'source': RESEARCH_SOURCE, 'records': 0, 'errors': 0, 'categories': {},
                'verified_movement_labels': 0, 'status': 'not_imported', 'curriculum_bias': {},
                'top_tools': {}, 'category_errors': {}}
    if path.stat().st_size > max_bytes:
        raise ValueError('Imported Mine AI metadata exceeds bounded analysis limit')
    with path.open(encoding='utf-8') as stream:
        for index, line in enumerate(stream):
            if index >= 100_000 or len(line) > 10000:
                raise ValueError('Mine AI metadata record limit exceeded')
            try: record = json.loads(line)
            except (ValueError, TypeError): continue
            if not isinstance(record, dict) or record.get('schema') != 1 or record.get('source') != RESEARCH_SOURCE:
                continue
            category, status = record.get('category'), record.get('result_status')
            if category not in CATEGORIES or status not in ('error', 'unverified_result'):
                continue
            action = record.get('action')
            if not isinstance(action,str) or not 1 <= len(action) <= 130 or not action.replace('_','').isalnum():
                continue
            counts[category] += 1
            actions[(category,action)] += 1
            if status == 'error':
                counts['errors'] += 1
                errors[category] += 1
            counts['records'] += 1
    total = counts['records']
    # Bounded observation-based curriculum hints, not pseudo-successful trials.
    # Even 10,000 observed navigation requests can change scheduling by <= 8%.
    nav_share = counts['navigation'] / total if total else 0
    obs_share = counts['world_observation'] / total if total else 0
    error_share = counts['errors'] / total if total else 0
    nav_error_share=errors['navigation']/max(1,counts['navigation'])
    bias = {'sprint_jump': round(min(.08, .07 * nav_share + .02 * nav_error_share + .01 * error_share), 4),
            'swim': round(min(.06, .055 * nav_share + .02 * obs_share), 4),
            'climb': round(min(.06, .05 * nav_share + .02 * error_share), 4)} if total else {}
    return {'source': RESEARCH_SOURCE, 'records': total, 'errors': counts['errors'],
            'categories': {key: counts[key] for key in sorted(CATEGORIES) if counts[key]},
            'verified_movement_labels': 0,
            'status': 'observational_metadata_only' if total else 'empty', 'curriculum_bias': bias,
            'top_tools': {f'{k[0]}:{k[1]}':v for k,v in actions.most_common(8)},
            'category_errors': dict(errors)}


def _action(episode: dict):
    skill = episode.get('skill')
    if skill not in ACTION_GRIDS: return None
    if skill == 'sprint_jump':
        if episode.get('scorer_version') != 2: return None
        offset = episode.get('requested_offset', episode.get('launch_offset'))
        brake = episode.get('brake_after')
        if type(offset) not in (int,float) or not math.isfinite(offset): return None
        # Historic observed offsets can be between candidate values; only
        # v3 explicitly selected actions are mapped to controls exactly.
        if episode.get('scheduler_version') == 3:
            action = (round(float(offset), 5), brake)
            return action if action in ACTION_GRIDS[skill] else None
        return (min(OFFSETS, key=lambda v: abs(v - offset)), brake) if brake in BRAKE_AFTER else None
    param = episode.get('parameter')
    if type(param) not in (int,float) or not math.isfinite(param): return None
    action = (float(param), None)
    return action if action in ACTION_GRIDS[skill] else None


def _wilson_lower(wins: int, n: int) -> float:
    if not n: return 0.
    z = 1.96
    p = wins/n
    return max(0., (p + z*z/(2*n) - z*math.sqrt((p*(1-p)+z*z/(4*n))/n))/(1+z*z/n))


def _bounded_float(value: object) -> float | None:
    if type(value) not in (int,float): return None
    value = float(value)
    return value if math.isfinite(value) else None


def fit_v3(log: Path, *, research_profile: dict | None = None) -> dict:
    """Evidence-weighted multi-skill model with held-out control validation.

    Training and validation rows are disjoint. Historic data without a split
    can inform exploration, but CANNOT supply new validation certification.
    """
    buckets = defaultdict(lambda: {'train': [], 'validation': []})
    rejected = Counter()
    total = 0
    for row in read_episodes(log,include_validation=True):
        action = _action(row)
        if action is None:
            rejected['unknown_action_or_legacy_jump_scoring'] += 1
            continue
        split = row.get('split', 'train')
        if split not in ('train', 'validation'):
            rejected['invalid_split'] += 1
            continue
        if split == 'validation' and row.get('scheduler_version') != 3:
            rejected['unverified_validation_origin'] += 1
            continue
        buckets[(row['skill'], row.get('gap', 0) if row['skill']=='sprint_jump' else 0, action)][split].append(row)
        total += 1
    groups = {}
    for skill, actions in ACTION_GRIDS.items():
        gaps = (1,2,3) if skill == 'sprint_jump' else (0,)
        for gap in gaps:
            candidates = []
            for action in actions:
                vals = buckets[(skill,gap,action)]
                train, valid = vals['train'], vals['validation']
                n, wins = len(train), sum(bool(x['success']) for x in train)
                vn, vw = len(valid), sum(bool(x['success']) for x in valid)
                recent = train[-min(30,n):]
                recent_rate = sum(x['success'] for x in recent)/len(recent) if recent else 0.
                mean_success_duration = (sum(float(x['duration_s']) for x in train if x['success']) / wins) if wins else None
                lower = _wilson_lower(wins,n)
                v_lower = _wilson_lower(vw,vn)
                # Conservative ranking: penalize uncertainty, late regressions,
                # and duration of *successful* attempts only. No false speed wins.
                score = (.59*lower + .26*recent_rate + .15*(wins+1)/(n+2)
                         - .03*min(1., (mean_success_duration or 9.)/9.)) if n else 0.
                validated = (n>=16 and wins>=12 and vn>=12 and vw/vn>=.75
                             and v_lower>=.48 and lower>=.62)
                candidates.append({'offset_or_parameter': action[0], 'brake_after': action[1],
                                   'train_trials': n, 'train_wins': wins,
                                   'train_rate': round(wins/n, 4) if n else None,
                                   'train_lower_95': round(lower, 4),
                                   'recent_rate': round(recent_rate, 4) if recent else None,
                                   'validation_trials': vn, 'validation_wins': vw,
                                   'validation_rate': round(vw/vn,4) if vn else None,
                                   'validation_lower_95': round(v_lower,4),
                                   'avg_success_seconds': round(mean_success_duration,3) if mean_success_duration is not None else None,
                                   'score': round(score, 5), 'live_eligible': bool(validated),
                                   'top_failures': dict(Counter(str(x.get('reason','unknown')) for x in train if not x['success']).most_common(3))})
            eligible = [c for c in candidates if c['live_eligible']]
            selected = max(eligible,key=lambda c:(c['score'],c['validation_lower_95'])) if eligible else None
            groups[f'{skill}:{gap}'] = {'skill':skill, 'gap':gap, 'candidates':candidates,
                                      'selected': {'offset_or_parameter':selected['offset_or_parameter'],
                                                   'brake_after':selected['brake_after']} if selected else None,
                                      'validated_for_live': selected is not None,
                                      'train_trials':sum(c['train_trials'] for c in candidates),
                                      'validation_trials':sum(c['validation_trials'] for c in candidates)}
    return {'schema':3,'model':MODEL,'source':'observed_minecraft_trials',
            'episodes':total,'groups':groups, 'excluded':dict(rejected),
            'research':{'records':int((research_profile or {}).get('records',0)),
                        'role':'bounded_curriculum_priority_only; never movement labels'},
            'eligibility':'At least 16 training + 12 separate same-course variant validation episodes, 75% validation and conservative training bounds. Parkour School remains external transfer evaluation.'}


def save_v3(policy: dict, path: Path):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp = path.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(policy,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    tmp.replace(path)


def load_v3(path: Path) -> dict | None:
    try:
        if path.stat().st_size > 1_000_000:return None
        value=json.loads(path.read_text(encoding='utf-8'))
        if value.get('schema')==3 and value.get('model')==MODEL and value.get('source')=='observed_minecraft_trials':
            return value
    except (OSError,ValueError,TypeError,AttributeError):pass
    return None


def choose_v3_action(policy: dict | None, skill: str, gap: int, episode: int, *, validation: bool=False) -> tuple[float, float | None]:
    """Uncertainty-sensitive exploration without assuming an old 'winner' is safe."""
    actions=ACTION_GRIDS[skill]
    group=(policy or {}).get('groups',{}).get(f'{skill}:{gap}',{})
    candidates=group.get('candidates',[])
    # Validation explores a promising TRAINING action without using held-out
    # results for action selection. This avoids data leakage from validation.
    if validation and candidates:
        contenders=[c for c in candidates if c.get('train_trials',0)>=8]
        if contenders:
            c=max(contenders,key=lambda c:(c.get('score',0),c.get('train_trials',0)))
            action=(c['offset_or_parameter'],c['brake_after'])
            if action in actions:return action
    # Exploration floor: ensure ALL candidate actions receive coverage.
    if not candidates or episode%5==0:
        return actions[(episode-1)%len(actions)]
    by_action = {(c['offset_or_parameter'],c['brake_after']):c for c in candidates}
    if episode % 3 == 0:
        return min(actions,key=lambda a:(by_action.get(a,{}).get('train_trials',0),actions.index(a)))
    scored=[]
    for a in actions:
        c=by_action.get(a,{})
        n=c.get('train_trials',0)
        optimistic=(c.get('score',0.) + .34/math.sqrt(n+1))
        scored.append((optimistic,-actions.index(a),a))
    return max(scored)[2]


@dataclass
class _StageStats:
    trials: int=0
    wins: int=0
    recent: deque | None=None
    def __post_init__(self):
        if self.recent is None:self.recent=deque(maxlen=40)


class AdaptiveScheduler:
    """Bounded stage allocation: prioritize poor/uncertain skills; prevent starvation.

    One `budget` unit = one physical Minecraft episode across ALL stages.
    Validation rows are held out of fitting and use a *variation* of each
    training lane. The final Parkour School test remains a separate world.
    """
    def __init__(self, stages, history: Path, *, research_profile: dict | None=None,
                 validation_every: int=5):
        if not 2<=validation_every<=20:raise ValueError('Validation cadence out of range')
        self.stages=tuple(stages)
        if not self.stages:raise ValueError('No training stages supplied')
        self.profile=research_profile or {}
        self.validation_every=validation_every
        self.stats={s.name:_StageStats() for s in self.stages}
        self.total=0
        self.attempts={s.name:0 for s in self.stages}
        self.session_attempts={s.name:0 for s in self.stages}
        self.previous=None
        self.streak=0
        for row in read_episodes(history,include_validation=True):
            name=row.get('base_stage',row.get('stage'))
            if name in self.stats:
                self.attempts[name]+=1
                if row.get('split','train')=='train':
                    self._observe(name,bool(row['success']),history=True)

    def _observe(self,name,success,*,history=False):
        s=self.stats[name]
        s.trials+=1;s.wins+=int(success);s.recent.append(int(success))
        if not history:
            self.total+=1
            self.streak=self.streak+1 if self.previous==name else 1
            self.previous=name

    def record(self, stage, success: bool, *, validation: bool=False):
        self.attempts[stage.name]+=1
        self.session_attempts[stage.name]+=1
        if validation:
            self.total+=1
            self.streak=self.streak+1 if self.previous==stage.name else 1
            self.previous=stage.name
        else:
            self._observe(stage.name,bool(success))

    def next(self):
        bias=self.profile.get('curriculum_bias',{})
        # Prioritize under-tested skills, uncertainty and observed failure.
        # Keep a minimum frequency so 100%-success skills get rechecked.
        scores=[]
        for stage in self.stages:
            s=self.stats[stage.name]
            rate=sum(s.recent)/len(s.recent) if s.recent else .5
            need=0.62*(1-rate) + 0.38/math.sqrt(s.trials+1)
            need += .1/(s.trials+1)
            if self.previous==stage.name:
                need*=.15 if self.streak>=3 else .73
            need*=1+min(.08,max(0.,float(bias.get(stage.skill,0.))))
            scores.append((need,-s.trials,-self.stages.index(stage),stage))
        # Never starve a mastered skill: every selected course must retain
        # at least 10% of the new session's physical trials for regression
        # monitoring. This quota is independent of previous 5k episodes.
        minimum=math.floor((self.total+1)*min(.10,.60/len(self.stages)))
        deficit=[stage for stage in self.stages if self.session_attempts[stage.name]<minimum]
        if deficit:
            stage=min(deficit,key=lambda st:(self.session_attempts[st.name],self.stages.index(st)))
        else:
            stage=max(scores,key=lambda x:x[:3])[3]
        validation=(self.total+1)%self.validation_every==0
        episode=self.attempts[stage.name]+1
        return stage,episode,validation


def validation_variant(stage):
    """Alternate lane/shorter runup within existing verified training arena."""
    from .arena_training import ArenaStage
    from .observations import Position
    def shifted(p, *, dz=1.):return Position(p.x,p.y,p.z+dz)
    if stage.skill=='sprint_jump':
        return ArenaStage(stage.name+'_validation',stage.skill,
                          Position(stage.start.x+1,stage.start.y,stage.start.z+1),
                          shifted(stage.target),shifted(stage.takeoff),stage.gap,stage.seconds,
                          stage.landing_length,.65)
    if stage.skill=='swim':
        return ArenaStage(stage.name+'_validation','swim',
                          Position(stage.start.x+2,stage.start.y,stage.start.z+1),
                          Position(stage.target.x-1,stage.target.y,stage.target.z+1),
                          seconds=stage.seconds)
    return ArenaStage(stage.name+'_validation','climb',stage.start,
                      type(stage.target)(stage.target.x,stage.target.y-.4,stage.target.z),
                      seconds=stage.seconds)
