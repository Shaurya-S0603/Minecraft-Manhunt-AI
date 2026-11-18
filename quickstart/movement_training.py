"""Experience-driven movement calibration; real Carpet outcomes, not synthetic labels.

The built-in route planner allows short gaps by default. Longer gap actions
are enabled only after repeated *observed* successes at that exact length.
For supervised experiments use MANHUNT_MOVEMENT_PRACTICE=1; it is NOT
recommended for survival matches near unprotected drops.
"""
from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
import json, math, os, time
from .observations import Position
from .movement_policy import load_policy, offset_for_gap, train_from_log, save_policy
from .jump_training_v2 import load_v2,fit_v2,save_v2
from .curriculum_v3 import load_v3
from .curriculum_v4 import load_v4, validated_candidate

DATA_ROOT=Path(__file__).resolve().parents[1]/'runtime'/'movement_training'

@dataclass
class MovementTrial:
    skill: str
    takeoff: Position
    destination: Position
    started: float
    gap: int
    launch_offset: float = 0.12
    approach_speed: float = 0.0
    samples: list[list[float]]=field(default_factory=list)
    airborne_seen: bool=False
    scorer_version: int = 1
    brake_after: float|None = None
    split: str = 'train'

class MovementTrainer:
    def __init__(self, root: Path | None=None, enabled: bool=True, practice: bool | None=None):
        self.root=Path(root) if root is not None else DATA_ROOT
        self.enabled=enabled
        self.practice = (os.environ.get('MANHUNT_MOVEMENT_PRACTICE') == '1'
                         if practice is None else practice)
        self.trial: MovementTrial | None = None
        self.results=defaultdict(lambda: [0,0])
        self.water_successes=0
        self.water_attempts=0
        self.jump_attempt_count=0
        self.success_offsets=[]
        self.policy=None
        self.policy_v2=None
        self.policy_v3=None
        self.policy_v4=None
        self.v2_stats=defaultdict(lambda:[0,0])
        if enabled:
            self._load()
            self.policy=load_policy(self.root/'policy.json')
            self.policy_v2=load_v2(self.root/'jump_policy_v2.json')
            self.policy_v3=load_v3(self.root/'curriculum_policy_v3.json')
            self.policy_v4=load_v4(self.root/'curriculum_policy_v4.json')

    @property
    def log_file(self):
        return self.root/'trials.jsonl'

    def _load(self):
        if not self.log_file.is_file():
            return
        for line in self.log_file.read_text(encoding='utf-8').splitlines()[-10000:]:
            try:
                d=json.loads(line)
                if d.get('source','minecraft')!='minecraft' or d.get('split','train')!='train':
                    continue
                if d.get('skill')=='sprint_jump' and d.get('gap') in (1,2,3):
                    self.jump_attempt_count+=1
                    self.results[d['gap']][int(bool(d.get('success')))] += 1
                    if d.get('scorer_version')==2 and d.get('platform_scoring_v2') is True:
                        self.v2_stats[d['gap']][int(bool(d.get('success')))] += 1
                    if d.get('success') and isinstance(d.get('launch_offset'),(int,float)):
                        self.success_offsets.append(float(d['launch_offset']))
                elif d.get('skill')=='water_drop':
                    self.water_attempts+=1
                    self.water_successes+=int(bool(d.get('success')))
            except (ValueError,TypeError,KeyError):
                continue

    @property
    def max_trained_gap(self):
        # Offline tests or guessed values cannot grant a long jump.
        allowed=1
        if self.policy_v4 is not None:
            # Live gap permission is certified by new V4 held-out evidence,
            # never by accumulated success rates from old scoring versions.
            for gap in (2,3):
                group=self.policy_v4.get('groups',{}).get(f'sprint_jump:{gap}',{})
                selected=group.get('selected')
                candidate=(next((c for c in group.get('candidates',[]) if
                           isinstance(selected,dict) and
                           c.get('offset_or_parameter')==selected.get('offset_or_parameter') and
                           c.get('brake_after')==selected.get('brake_after')),None)
                           if isinstance(selected,dict) else None)
                if group.get('validated_for_live') is True and validated_candidate(candidate):
                    allowed=gap
                else:
                    break
            return allowed
        # Once corrected platform-verified labels exist, legacy point-target
        # successes cannot certify difficult jumps. Keep old logs for audit.
        counts=self.v2_stats if any(sum(v) for v in self.v2_stats.values()) else self.results
        for gap in (2,3):
            fails,successes=counts[gap]
            if successes >= (6 if counts is self.v2_stats else 4) and successes/(successes+fails)>=.75:
                allowed=gap
            else:
                break
        return allowed

    @property
    def water_drop_ready(self):
        return self.water_successes>=4 and self.water_successes/max(1,self.water_attempts)>=.75

    @property
    def allowed_gap(self):
        return 2 if self.practice else self.max_trained_gap

    @property
    def launch_threshold(self):
        # Rotate candidate takeoff positions while supervised. Learned
        # threshold is median of observed SUCCESSFUL jump offsets, never
        # an offline or predicted location.
        if self.practice:
            return (0.12,0.20,0.28,0.36)[self.jump_attempt_count%4]
        if len(self.success_offsets)>=4:
            values=sorted(self.success_offsets[-20:])
            return max(.10,min(.38,values[len(values)//2]))
        return .12

    def launch_threshold_for(self, gap: int) -> float:
        # A recorded policy can tune timing but NEVER grant unproven gaps.
        if self.practice:
            return self.launch_threshold
        if self.policy_v4 is not None:
            group=self.policy_v4.get('groups',{}).get(f'sprint_jump:{gap}',{})
            selected=group.get('selected')
            if isinstance(selected,dict) and group.get('validated_for_live') is True:
                candidate=next((c for c in group.get('candidates',[]) if
                                c.get('offset_or_parameter')==selected.get('offset_or_parameter') and
                                c.get('brake_after')==selected.get('brake_after')),None)
                if validated_candidate(candidate):
                    offset=selected.get('offset_or_parameter')
                    if type(offset) in (int,float) and offset in (.12,.20,.28,.36):
                        return float(offset)
            return .12  # No fallthrough to unvalidated historical timing.
        if self.policy_v3:
            group=self.policy_v3.get('groups',{}).get(f'sprint_jump:{gap}',{})
            selected=group.get('selected')
            if group.get('validated_for_live') is True and isinstance(selected,dict):
                offset=selected.get('offset_or_parameter')
                candidate=next((c for c in group.get('candidates',[]) if
                                c.get('offset_or_parameter')==offset and
                                c.get('brake_after')==selected.get('brake_after')),None)
                if (type(offset) in (int,float) and offset in (.12,.20,.28,.36)
                        and isinstance(candidate,dict) and candidate.get('live_eligible') is True
                        and candidate.get('validation_trials',0)>=12 and candidate.get('validation_wins',0)>=9
                        and candidate.get('train_lower_95',0)>=.62):
                    return float(offset)
        if self.policy_v2:
            group=self.policy_v2.get('groups',{}).get(str(gap),{})
            selected=group.get('selected')
            if isinstance(selected,dict) and selected.get('offset') in (.12,.20,.28,.36):
                return selected['offset']
        # Once corrected trials exist, do not fall back to timings learned
        # from potentially misclassified legacy point-landings.
        if any(sum(v) for v in self.v2_stats.values()):
            return .12
        return offset_for_gap(self.policy,gap,self.launch_threshold)

    def begin(self, skill: str, pos: Position, destination: Position, now: float, gap:int=0, launch_offset:float=0.12, approach_speed: float=0.0,
              scorer_version:int=1,brake_after:float|None=None,split:str='train'):
        if not self.enabled or self.trial is not None:
            return
        self.trial=MovementTrial(skill,pos,destination,now,gap,launch_offset,approach_speed,
                                 [[round(now,3),round(pos.x,3),round(pos.y,3),round(pos.z,3)]],
                                 scorer_version=scorer_version,brake_after=brake_after,split=split)
        if skill=='sprint_jump':
            self.jump_attempt_count+=1

    def observe(self, pos: Position, now: float, grounded: bool | None=None):
        trial=self.trial
        if trial is None: return None
        if len(trial.samples)<60:
            trial.samples.append([round(now,3),round(pos.x,3),round(pos.y,3),round(pos.z,3)])
        if grounded is False:
            trial.airborne_seen=True
        if trial.skill=='water_drop' and pos.y<trial.takeoff.y-2.0:
            trial.airborne_seen=True
        horizontal=math.hypot(pos.x-trial.destination.x,pos.z-trial.destination.z)
        vertical_tolerance=1.5 if trial.skill=='water_drop' else .85
        success=(trial.airborne_seen and grounded is True and horizontal<=.72 and abs(pos.y-trial.destination.y)<vertical_tolerance
                 and now-trial.started>=.28)
        failure=(now-trial.started>3.0 or (grounded is True and now-trial.started>1.0
                                      and horizontal>2.4))
        if success or failure:
            self.finish(success,pos,now)
            return success
        return None

    def finish(self, success: bool, pos: Position, now: float,reason:str|None=None):
        trial=self.trial
        if trial is None: return
        d={'skill':trial.skill,'gap':trial.gap,'success':bool(success),
           'source':'minecraft','split':trial.split,'approach_speed':round(trial.approach_speed,3),
           'duration_s':round(now-trial.started,3),
           'launch_offset':round(trial.launch_offset,3),
           'start':[trial.takeoff.x,trial.takeoff.y,trial.takeoff.z],
           'goal':[trial.destination.x,trial.destination.y,trial.destination.z],
           'end':[pos.x,pos.y,pos.z], 'trajectory':trial.samples,
           'scorer_version':trial.scorer_version,'brake_after':trial.brake_after,
           'platform_scoring_v2': trial.scorer_version==2,
           'landing_verified': trial.scorer_version==2 and bool(success) and reason=='landed',
           'reason':reason or ('landed' if success else 'unknown')}
        if self.enabled:
            self.root.mkdir(parents=True,exist_ok=True)
            with self.log_file.open('a',encoding='utf-8') as f:
                f.write(json.dumps(d,separators=(',',':'))+'\n')
            if trial.split=='train' and trial.skill=='sprint_jump' and trial.gap in (1,2,3):
                self.results[trial.gap][int(bool(success))]+=1
                if success:
                    self.success_offsets.append(trial.launch_offset)
                if trial.scorer_version==2:
                    self.v2_stats[trial.gap][int(bool(success))] += 1
                # Update the real-outcome bandit periodically after complete
                # jump episodes. Does not accept simulation checkpoints.
                if self.jump_attempt_count and self.jump_attempt_count%100==0:
                    self.policy=train_from_log(self.log_file)
                    save_policy(self.policy,self.root/'policy.json')
                    self.policy_v2=fit_v2(self.log_file)
                    if self.policy_v2['records']:
                        save_v2(self.policy_v2,self.root/'jump_policy_v2.json')
                    print('[MODEL] Updated real-trial policies; platform-verified v2 records:',
                          self.policy_v2['records'])
            elif trial.split=='train' and trial.skill=='water_drop':
                self.water_attempts+=1
                self.water_successes+=int(bool(success))
        print(f'[TRAIN] {trial.skill} gap={trial.gap}: {"SUCCESS" if success else "FAILED"} '
              f'({now-trial.started:.1f}s). Validated gap allowance={self.max_trained_gap}.')
        self.trial=None


def report(root: Path=DATA_ROOT):
    trainer=MovementTrainer(root)
    print('Recorded movement results (success/failure, not a pretrained model):')
    for gap in (1,2,3):
        fail,success=trainer.results[gap]
        print(f'Gap {gap}: successes={success}, failures={fail}')
    print('Currently certified automatic gap:',trainer.max_trained_gap)
    print('Successful water-drop landings:',trainer.water_successes)
    print('Calibrated takeoff offset:', round(trainer.launch_threshold,3))
    print('Training file:',trainer.log_file)
    print('Learned policy loaded:', bool(trainer.policy))
    if trainer.policy:
        for gap in (1,2,3):
            print(f'Gap {gap} learned takeoff offset:',trainer.policy['groups'].get(str(gap),{}).get('selected_offset'))

if __name__=='__main__':
    report()
