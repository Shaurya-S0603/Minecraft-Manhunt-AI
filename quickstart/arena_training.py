"""Autonomous physical parkour training for a Carpet fake player.

This module deliberately has NO ManhuntMatch dependency. Trials run in an
isolated training world, with reset, observed trajectories and no human target.
Minecraft controls use real fake-player inputs. No per-trial teleport may occur
between takeoff and result classification.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import argparse
from datetime import datetime, timezone
import secrets
import json
import math
import time
from typing import Callable

from .jump_control import JumpCorridor, SprintJumpController, VelocityTracker
from .movement_training import MovementTrainer, DATA_ROOT
from .observations import Observer, Position, parse_player_list, validate_name
from .terrain import TerrainSensor, TerrainUnavailable, terrain_type
from .movement_policy import train_from_log, save_policy
from .skill_policy import (train_skill_policy, choose_parameter, save_skill_policy, load_skill_policy)
from .jump_training_v2 import (zone_for_stage, classify_jump, fit_v2, save_v2,
                               load_v2, choose_training_action)
from .curriculum_v3 import (AdaptiveScheduler, validation_variant, read_research_profile,
                            fit_v3, save_v3, load_v3, choose_v3_action)
from .curriculum_v4 import (GenerationScheduler, choose_v4_action, fit_v4, save_v4, load_v4)

BOT = 'ManhuntBot'


@dataclass(frozen=True)
class ArenaStage:
    name: str
    skill: str
    start: Position
    target: Position
    takeoff: Position | None = None
    gap: int = 0
    seconds: float = 5.0
    # Landing rectangle: first landing block centre + forward length and width.
    landing_length: float = 0.9
    landing_half_width: float = 0.5

    def __post_init__(self):
        if self.skill not in ('sprint_jump', 'swim', 'climb'):
            raise ValueError('Unknown training skill: ' + self.skill)
        if not self.name or len(self.name)>60 or any(c in self.name for c in '\r\n'):
            raise ValueError('Invalid stage name')
        coordinates = (self.start,self.target) + ((self.takeoff,) if self.takeoff else ())
        if not all(math.isfinite(v) and -30_000_000 <= v <= 30_000_000
                   for p in coordinates for v in (p.x,p.y,p.z)):
            raise ValueError('Non-finite or out-of-world arena coordinates')
        if any(not -64<=p.y<=310 for p in coordinates):
            raise ValueError('Arena coordinates outside safe Minecraft world height')
        if not 2.0<=self.seconds<=20.0:
            raise ValueError('Training trial duration must be 2–20 seconds')
        if self.skill == 'sprint_jump':
            if self.gap not in (1,2,3) or self.takeoff is None:
                raise ValueError('Jump stages require gap 1–3 and takeoff position')
            dx=self.target.x-self.start.x
            dz=self.target.z-self.start.z
            if (abs(dx)>.01 and abs(dz)>.01) or (abs(dx)<1.5 and abs(dz)<1.5):
                raise ValueError('Jump course must be horizontal along one axis')
            if not (0.75<=self.landing_length<=32 and .3<=self.landing_half_width<=4):
                raise ValueError('Landing zone size is invalid')


def built_in_stages() -> tuple[ArenaStage,...]:
    result=[]
    for gap,z in ((1,0),(2,20),(3,40)):
        result.append(ArenaStage(f'gap_{gap}','sprint_jump',
            Position(1.5,220.,z+.5),Position(6.5+gap,220.,z+.5),
            Position(5.5,220.,z+.5),gap,5.5,landing_length=9.0-gap,landing_half_width=1.7))
    result.append(ArenaStage('swim_horizontal','swim',
        Position(1.5,217.,80.5),Position(15.5,217.,80.5),seconds=9.0))
    result.append(ArenaStage('ladder_up','climb',
        Position(5.5,220.,100.5),Position(5.5,226.,100.5),seconds=9.0))
    return tuple(result)


def read_stages(path: Path) -> tuple[ArenaStage,...]:
    if path.stat().st_size>100_000:
        raise ValueError('Arena config exceeds 100 KB')
    data=json.loads(path.read_text(encoding='utf-8'))
    if data.get('schema')!=1 or not isinstance(data.get('stages'),list):
        raise ValueError('Expected schema=1 and stages list')
    if not 1<=len(data['stages'])<=100:
        raise ValueError('Stage count must be 1–100')
    seen=set()
    stages=[]
    for entry in data['stages']:
        if not isinstance(entry,dict):
            raise ValueError('Invalid stage object')
        allowed={'name','skill','start','target','takeoff','gap','seconds','landing_length','landing_half_width'}
        if not set(entry)<=allowed:
            raise ValueError('Unknown stage field(s): '+str(set(entry)-allowed))
        name=str(entry['name'])
        if name in seen:
            raise ValueError('Stage names must be unique')
        seen.add(name)
        def point(value):
            if not isinstance(value,list) or len(value)!=3 or not all(type(x) in (int,float) for x in value):
                raise ValueError('Position must be an [x,y,z] numeric list')
            return Position(*map(float,value))
        stages.append(ArenaStage(name,entry['skill'],point(entry['start']),
                      point(entry['target']),point(entry['takeoff']) if 'takeoff' in entry else None,
                      entry.get('gap',0),float(entry.get('seconds',5.5)),float(entry.get('landing_length',.9)),float(entry.get('landing_half_width',.5))))
    return tuple(stages)


def write_stage_template(path: Path, stages: tuple[ArenaStage,...]):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return
    records=[]
    for s in stages:
        d={'name':s.name,'skill':s.skill,'start':[s.start.x,s.start.y,s.start.z],
           'target':[s.target.x,s.target.y,s.target.z],'seconds':s.seconds}
        if s.takeoff is not None:
            d.update(takeoff=[s.takeoff.x,s.takeoff.y,s.takeoff.z],gap=s.gap,landing_length=s.landing_length,landing_half_width=s.landing_half_width)
        records.append(d)
    path.write_text(json.dumps({'schema':1,'stages':records},indent=2)+'\n',encoding='utf-8')


def checked(rcon, command: str):
    reply=rcon.command(command)
    if any(t in reply.lower() for t in ('unknown or incomplete','unknown command',
         'incorrect argument','no player was found','could not find','not allowed','unknown player')):
        raise RuntimeError(f'Minecraft command failed: {command}: {reply[:170]}')
    return reply


class ArenaRunner:
    def __init__(self, rcon, data_root: Path=DATA_ROOT, *, bot: str=BOT,
                 clock: Callable=time.monotonic, sleep: Callable=time.sleep):
        self.rcon,self.bot=rcon,validate_name(bot)
        self.clock,self.sleep=clock,sleep
        self.observer=Observer(rcon)
        self.sensor=TerrainSensor(rcon)
        self.sensor.at_entity=bot
        self.corridor=JumpCorridor(self.sensor)
        self.trainer=MovementTrainer(data_root,practice=True)
        self.arena_log=Path(data_root)/'arena_episodes.jsonl'
        self.completed=0
        self.skill_policy=load_skill_policy(Path(data_root)/"skill_policy.json")
        self.jump_policy_v2=load_v2(Path(data_root)/'jump_policy_v2.json')
        self.policy_v3=load_v3(Path(data_root)/'curriculum_policy_v3.json')
        self.policy_v4=load_v4(Path(data_root)/'curriculum_policy_v4.json')
        self.active_session_id=None

    def _stop(self):
        checked(self.rcon,f'player {self.bot} stop')

    def reset(self, stage: ArenaStage):
        """Reset only *between* trials, then verify actual bot coordinates."""
        self._stop()
        checked(self.rcon,f'tp {self.bot} {stage.start.x:.3f} {stage.start.y:.3f} {stage.start.z:.3f}')
        self.sleep(.14)
        actual=self.observer.position(self.bot)
        if actual.distance(stage.start)>1.4:
            raise RuntimeError('Fake player did not appear at configured training start; stopping')
        self.sensor.cache.clear()
        return actual

    def _grounded(self,pos:Position):
        # Check actual support at or just below the feet, excluding water,
        # with block-state observations rather than trusting an animation.
        x,y,z=math.floor(pos.x),math.floor(pos.y),math.floor(pos.z)
        cells=[(x,y-1,z),(x,y,z)]
        blocks=self.sensor.read(cells)
        support=terrain_type(blocks[cells[0]])
        return support=='solid' and abs(pos.y-round(pos.y))<.32 and terrain_type(blocks[cells[1]])=='air'

    def _has_water(self,pos:Position):
        x,y,z=math.floor(pos.x),math.floor(pos.y),math.floor(pos.z)
        return terrain_type(self.sensor.read([(x,y,z)])[(x,y,z)])=='water'

    def _confirm_stage(self,stage:ArenaStage):
        # Jump safety preflight is compulsory for an auto training attempt.
        if stage.skill=='sprint_jump':
            self.sensor.cache.clear()
            if not self.corridor.verified(stage.takeoff,stage.target):
                raise RuntimeError(f'{stage.name}: observed jump clearance/support differs from config')
        elif stage.skill=='swim':
            if not self._has_water(stage.start) or not self._has_water(stage.target):
                raise RuntimeError('Configured swim course is not underwater at start and destination')
        elif stage.skill=='climb':
            # Fail closed on a missing ladder/vine; no blind jump against a wall.
            x,y,z=math.floor(stage.start.x),math.floor(stage.start.y),math.floor(stage.start.z)
            cells=[(x+dx,y+dy,z+dz) for dx,dz in ((0,0),(1,0),(-1,0),(0,1),(0,-1))
                   for dy in (0,1)]
            blocks=self.sensor.read(cells)
            if not any('ladder' in blocks[c] or 'vine' in blocks[c] for c in cells):
                raise RuntimeError('Configured climb start has no observed ladder or vine')

    def _initialize_bot(self,at:Position):
        """Verify the authenticated player's Carpet shadow before trials.

        The trainer never invents or looks up an unverified Minecraft profile.
        The original player must have joined the online-authenticated training
        server, and the server must have converted that session with /player shadow.
        """
        names=parse_player_list(self.rcon.command('list'))
        if self.bot.casefold() not in {name.casefold() for name in names}:
            raise RuntimeError(
                'Authenticated Carpet shadow player is not connected. '
                'Join the trainer with your signed-in Minecraft account and '
                'let the launcher convert your session before starting trials.')
        checked(self.rcon,f'player {self.bot} stop')

    def _record_misc(self,stage:ArenaStage,success:bool,reason:str,samples:list,offset:float|None=None,parameter:float|None=None,episode:int=0,brake_after:float|None=None,*,requested_offset:float|None=None,split:str='train',scheduler_version:int=2,base_stage:str|None=None):
        self.arena_log.parent.mkdir(parents=True,exist_ok=True)
        controls={'sprint_jump':['sprint','move forward','jump once (when measured)'],
                  'swim':['sprint','move forward','look at underwater goal'],
                  'climb':['jump continuous','move forward','look at ladder wall']}
        record={'schema':1,'source':'minecraft','stage':stage.name,'skill':stage.skill,
                'success':bool(success),'reason':reason,'samples':samples,
                'split':split,'scheduler_version':scheduler_version,'base_stage':base_stage or stage.name,
                'gap':stage.gap,'requested_offset':requested_offset,
                'start':[stage.start.x,stage.start.y,stage.start.z],
                'target':[stage.target.x,stage.target.y,stage.target.z],
                'controls':controls[stage.skill],
                'launch_offset':offset,'parameter':parameter,'episode':episode,
                'scorer_version':2 if stage.skill=='sprint_jump' else 1,
                'brake_after':brake_after, 'landing_zone_length':stage.landing_length,
                'duration_s':round(samples[-1][0]-samples[0][0],3) if len(samples)>=2 else 0}
        if scheduler_version==4:
            if not self.active_session_id:
                raise RuntimeError('V4 attempt must have a training session id')
            record['session_id']=self.active_session_id
            record['training_generation']=4
        with self.arena_log.open('a',encoding='utf-8') as stream:
            stream.write(json.dumps(record,separators=(',',':'))+'\n')

    def attempt(self,stage:ArenaStage,episode:int, *, offset:float=.20,parameter:float|None=None,
                brake_after:float|None=None,split:str='train',scheduler_version:int=2,base_stage:str|None=None) -> bool:
        if self.trainer.trial is not None:
            raise RuntimeError('Unexpected unfinished movement trial: reset needed')
        self.reset(stage)
        self._confirm_stage(stage)
        now=self.clock()
        if stage.skill == 'sprint_jump':
            checked(self.rcon,f'player {self.bot} look at {stage.target.x:.2f} {stage.start.y+1.6:.2f} {stage.target.z:.2f}')
            checked(self.rcon,f'player {self.bot} sprint')
            checked(self.rcon,f'player {self.bot} move forward')
            controller=SprintJumpController(min_speed=1.7)
            tracker=VelocityTracker()
        elif stage.skill=='swim':
            parameter = 0.0 if parameter is None else parameter
            checked(self.rcon,f'player {self.bot} look at {stage.target.x:.2f} {stage.target.y+0.7+parameter:.2f} {stage.target.z:.2f}')
            checked(self.rcon,f'player {self.bot} sprint')
            checked(self.rcon,f'player {self.bot} move forward')
            controller=tracker=None
        else:
            # Ladder face selection for configured ladder block. Look toward
            # the nearby wall, not the elevated goal directly.
            parameter = 0.95 if parameter is None else parameter
            checked(self.rcon,f'player {self.bot} look at {stage.start.x+1:.2f} {stage.start.y+parameter:.2f} {stage.start.z:.2f}')
            checked(self.rcon,f'player {self.bot} jump continuous')
            checked(self.rcon,f'player {self.bot} move forward')
            controller=tracker=None
        samples=[]
        jumped=False
        airborne=False
        reason='timeout'
        success=False
        at_takeoff=0.0
        launch_offset=None
        braked=False
        landing_zone=zone_for_stage(stage) if stage.skill=='sprint_jump' else None
        starting=self.clock()
        try:
            while self.clock()-starting<stage.seconds:
                t=self.clock()
                pos=self.observer.position(self.bot)
                if len(samples)<400:
                    samples.append([round(t,3),round(pos.x,3),round(pos.y,3),round(pos.z,3)])
                if stage.skill=='sprint_jump':
                    tracker.observe(pos,t)
                    grounded=self._grounded(pos)
                    if jumped and not grounded:
                        airborne=True
                    if not jumped:
                        speed=tracker.speed_towards(stage.takeoff,stage.target)
                        decision=controller.decide((stage.name,episode),pos,stage.takeoff,
                                    stage.target,t,speed,offset)
                        if decision.command=='abort':
                            reason='unsafe_or_missed_takeoff'
                            break
                        if decision.command=='jump':
                            # The success record begins at the actual takeoff
                            # action; reset teleport is excluded from trial.
                            checked(self.rcon,f'player {self.bot} jump once')
                            launch_offset=decision.distance_from_takeoff
                            at_takeoff=t
                            self.trainer.begin('sprint_jump',pos,stage.target,t,stage.gap,
                                               launch_offset=launch_offset,approach_speed=speed,
                                               scorer_version=2,brake_after=brake_after,split=split)
                            jumped=True
                    if jumped:
                        trial=self.trainer.trial
                        if trial is None:
                            raise RuntimeError('Jump recorder unexpectedly missing')
                        trial.samples.append([round(t,3),round(pos.x,3),round(pos.y,3),round(pos.z,3)])
                        if not grounded:
                            trial.airborne_seen=True
                        # Optional midair brake stops sprint-forward only after
                        # actually reaching a configurable landing approach.
                        # Each candidate is evaluated from observed results.
                        if (trial.airborne_seen and not braked and brake_after is not None
                                and landing_zone.progress(pos)>=brake_after):
                            checked(self.rcon,f'player {self.bot} stop')
                            braked=True
                        finished,won,label=classify_jump(landing_zone,pos,grounded=grounded,
                                                         airborne_seen=trial.airborne_seen,
                                                         duration=t-at_takeoff)
                        if finished:
                            success=won
                            reason=label
                            self.trainer.finish(success,pos,t,reason=label)
                            break
                elif stage.skill=='swim':
                    if not self._has_water(pos):
                        reason='left_water'
                        break
                    if pos.distance(stage.target)<1.2:
                        success=True
                        reason='arrived_underwater'
                        break
                    # Keep horizontal swimming. No jump-hold input during swim.
                else:
                    if pos.y>=stage.target.y-.5:
                        success=True
                        reason='climbed_to_height'
                        break
                self.sleep(.08)
            if stage.skill=='sprint_jump' and self.trainer.trial is not None:
                # Explicitly label any incomplete in-game launch as failure.
                pos=self.observer.position(self.bot)
                self.trainer.finish(False,pos,self.clock(),reason='jump_timeout')
                reason='jump_timeout' if reason=='timeout' else reason
            self._record_misc(stage,success,reason,samples,launch_offset,parameter,episode,brake_after,
                              requested_offset=offset,split=split,scheduler_version=scheduler_version,base_stage=base_stage)
            self.completed+=1
            print(f'[ARENA] {stage.name} trial {episode}: {"PASS" if success else "FAIL"} '
                  f'({reason}); {len(samples)} position samples')
            return success
        finally:
            # Release controls even on RCON/observation exceptions.
            try: self._stop()
            except Exception: pass

    def fit_all_policies(self):
        """Refit V4 from new generations, preserving archived checkpoints."""
        if self.active_session_id is not None:
            if self.arena_log.exists():
                research=read_research_profile(self.trainer.root.parent/'strategy'/'mine_ai_tools.jsonl')
                self.policy_v4=fit_v4(self.arena_log,research_profile=research)
                if self.policy_v4['current_episodes']:
                    save_v4(self.policy_v4,self.trainer.root/'curriculum_policy_v4.json')
            # Running V4 must not rewrite V1/V2/V3 model files with the
            # lifetime-mixed records we are deliberately retiring from selection.
            return
        if self.trainer.log_file.exists():
            jump=train_from_log(self.trainer.log_file)
            if jump['records']:
                save_policy(jump,self.trainer.root/'policy.json')
        if self.trainer.log_file.exists():
            self.jump_policy_v2=fit_v2(self.trainer.log_file)
            if self.jump_policy_v2['records']:
                save_v2(self.jump_policy_v2,self.trainer.root/'jump_policy_v2.json')
        if self.arena_log.exists():
            research_file=self.trainer.root.parent/'strategy'/'mine_ai_tools.jsonl'
            research=read_research_profile(research_file)
            self.policy_v3=fit_v3(self.arena_log,research_profile=research)
            if self.policy_v3['episodes']:
                save_v3(self.policy_v3,self.trainer.root/'curriculum_policy_v3.json')
            # V4 checkpoint is distinct from the legacy/score-mixed policies.
            # Never overwrite archived JSONL or manufacture a V4 model from
            # historical episodes alone.
            self.policy_v4=fit_v4(self.arena_log,research_profile=research)
            if self.policy_v4['current_episodes']:
                save_v4(self.policy_v4,self.trainer.root/'curriculum_policy_v4.json')
            self.skill_policy=train_skill_policy(self.arena_log)
            if self.skill_policy['episodes']:
                save_skill_policy(self.skill_policy,self.trainer.root/'skill_policy.json')

    def run_adaptive(self, stages:tuple[ArenaStage,...], budget:int, skills:set[str]|None=None,
                     *, report_every:int=50, validation_every:int=5):
        """Allocate a TOTAL physical episode budget to weak, uncertain courses.

        Validation episodes use a distinct lane/run-up and are never used for
        model fitting or retrospective long-jump certification.
        """
        if not 1<=budget<=10000:raise ValueError('Adaptive total budget must be 1..10000')
        selected=[s for s in stages if skills is None or s.skill in skills]
        if not selected:raise ValueError('No selected stages')
        self._initialize_bot(selected[0].start)
        research=read_research_profile(self.trainer.root.parent/'strategy'/'mine_ai_tools.jsonl')
        scheduler=GenerationScheduler(selected,self.arena_log,research_profile=research,
                                    validation_every=validation_every)
        summary={s.name:{'successes':0,'attempts':0,'validation':0} for s in selected}
        self.active_session_id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+secrets.token_hex(5)
        print('[SCHEDULER V4] New session:',self.active_session_id,'; history preserved.')
        print(f'[SCHEDULER V4] {budget} total episodes, {len(selected)} skills/stages, '
              f'validation every {validation_every} attempts.')
        print('[MINE AI] Observational records:',research['records'],
              'verified movement labels:',research['verified_movement_labels'])
        try:
            for completed in range(budget):
                base, episode, validation=scheduler.next()
                stage=validation_variant(base) if validation else base
                gap=base.gap if base.skill=='sprint_jump' else 0
                action=choose_v4_action(self.policy_v4,base.skill,gap,episode,validation=validation)
                offset,brake_after=action if base.skill=='sprint_jump' else (.20,None)
                parameter=action[0] if base.skill in ('swim','climb') else None
                success=self.attempt(stage,episode,offset=offset,brake_after=brake_after,
                                     parameter=parameter,split='validation' if validation else 'train',
                                     scheduler_version=4,base_stage=base.name)
                summary[base.name]['attempts']+=1
                summary[base.name]['successes']+=int(success)
                summary[base.name]['validation']+=int(validation)
                # A held-out trial must never influence scheduler's training
                # performance estimate or primary model scores.
                scheduler.record(base,success,validation=validation)
                if (completed+1)%max(1,report_every)==0:
                    self.fit_all_policies()
                    print(f'[SCHEDULER V4] Checkpoint {completed+1}/{budget}. '
                          'Trained movement settings saved; test/validation remains separate.')
            self.fit_all_policies()
            return summary
        finally:
            try:self.fit_all_policies()
            finally:
                self.active_session_id=None
                try:self._stop()
                except Exception:pass

    def run(self,stages:tuple[ArenaStage,...],episodes:int, skills:set[str]|None=None,
            *, interleave:bool=True,report_every:int=100):
        if not 1<=episodes<=10000:
            raise ValueError('Episodes must be 1 to 10000')
        selected=[s for s in stages if skills is None or s.skill in skills]
        if not selected:
            raise ValueError('No stages match requested skills')
        self._initialize_bot(selected[0].start)
        summary={s.name:{'successes':0,'attempts':0} for s in selected}
        schedule=((s,e) for e in range(1,episodes+1) for s in selected) if interleave else (
            (s,e) for s in selected for e in range(1,episodes+1))
        try:
            for stage,episode in schedule:
                # Each movement skill gets its own learned action choices.
                if stage.skill=='sprint_jump':
                    offset,brake_after=choose_training_action(self.jump_policy_v2,stage.gap,episode)
                else:
                    offset,brake_after=.20,None
                param=(choose_parameter(self.skill_policy,stage.skill,episode)
                       if stage.skill in ('swim','climb') else None)
                try:
                    success=self.attempt(stage,episode,offset=offset,parameter=param,brake_after=brake_after)
                except (RuntimeError,TerrainUnavailable) as error:
                    print(f'[ARENA WARNING] {stage.name} episode {episode}: {error}')
                    raise  # Fail closed on unknown world/driver state.
                summary[stage.name]['successes']+=int(success)
                summary[stage.name]['attempts']+=1
                if self.completed and self.completed%max(1,report_every)==0:
                    self.fit_all_policies()
                    print(f'[TRAIN] Checkpoint: {self.completed} total Minecraft episodes, '
                          f'policies saved to {self.trainer.root}')
            self.fit_all_policies()
            for name,stats in summary.items():
                print(f'[ARENA] {name}: {stats["successes"]}/{stats["attempts"]} successes')
            return summary
        finally:
            try:self.fit_all_policies()
            finally:
                try:self._stop()
                except Exception:pass
