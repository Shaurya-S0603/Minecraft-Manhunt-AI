"""Generation-aware learning: historical archives are retained, never certified."""
import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from quickstart.arena_report import build_report, export_report
from quickstart.arena_training import ArenaRunner, built_in_stages
from quickstart.curriculum_v4 import (GenerationScheduler, current_episode, fit_v4,
                                      save_v4, load_v4, choose_v4_action)
from quickstart.live_skill_policy import LiveSkillPolicy
from quickstart.movement_training import MovementTrainer
from quickstart.skill_policy import save_skill_policy, train_skill_policy

SID1='20261105T110000Z-aabbccdde1'
SID2='20261105T130000Z-aabbccdde2'


def row(skill, stage, success, *, gap=0, offset=.28, parameter=.35,
        brake=None, session=None, split='train', scorer=2, version=None, reason=None):
    rec={'schema':1,'source':'minecraft','skill':skill,'stage':stage,'gap':gap,
         'success':success,'reason':reason or ('landed' if success else 'undershoot'),
         'requested_offset':offset,'parameter':parameter,'brake_after':brake,
         'scorer_version':scorer,'split':split,'base_stage':stage.replace('_validation',''),
         'duration_s':1.,'samples':[[0.,1.,220.,1.],[1.,2.,220.,1.]]}
    if version is not None:rec['scheduler_version']=version
    if session is not None:
        rec['training_generation']=4
        rec['scheduler_version']=4
        rec['session_id']=session
    return rec


def save(path,rows):
    path.write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf-8')


class GenerationModelTests(unittest.TestCase):
    def test_historic_wins_cannot_certify_a_failed_current_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'arena_episodes.jsonl'
            save(path,[row('sprint_jump','gap_2',True,gap=2)]*400 +
                 [row('sprint_jump','gap_2',False,gap=2,session=SID1)]*30 +
                 [row('sprint_jump','gap_2_validation',True,gap=2,split='validation',session=SID1)]*25)
            p=fit_v4(path);group=p['groups']['sprint_jump:2']
            self.assertEqual(p['historical_comparable_episodes'],400)
            self.assertEqual(p['current_episodes'],55)
            self.assertFalse(group['validated_for_live'])
            candidate=next(c for c in group['candidates'] if c['offset_or_parameter']==.28 and c['brake_after'] is None)
            self.assertEqual((candidate['current_train_wins'],candidate['historical_comparable_trials']),(0,400))
            self.assertLessEqual(candidate['historical_prior_examples_used'],3.)

    def test_current_training_and_current_holdout_can_certify(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'arena_episodes.jsonl'
            save(path,[row('sprint_jump','gap_2',True,gap=2,offset=.28,session=SID1)]*30 +
                 [row('sprint_jump','gap_2_validation',True,gap=2,offset=.28,session=SID1,split='validation')]*20)
            p=fit_v4(path)
            self.assertEqual(p['groups']['sprint_jump:2']['selected'],{'offset_or_parameter':.28,'brake_after':None})
            self.assertEqual(p['sessions'],1)
            save_v4(p,Path(directory)/'curriculum_policy_v4.json')
            self.assertEqual(load_v4(Path(directory)/'curriculum_policy_v4.json'),p)
            movement=MovementTrainer(Path(directory))
            self.assertEqual(movement.max_trained_gap,2)
            self.assertEqual(movement.launch_threshold_for(2),.28)

    def test_older_v3_holdout_rows_cannot_certify_new_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'arena_episodes.jsonl'
            save(path,[row('swim','swim_horizontal',True,session=SID1)]*35 +
                 [row('swim','swim_horizontal_validation',True,split='validation',version=3)]*900)
            p=fit_v4(path)
            self.assertFalse(p['groups']['swim:0']['validated_for_live'])
            self.assertEqual(p['groups']['swim:0']['current_validation_trials'],0)

    def test_holdout_result_cannot_choose_among_training_candidates(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'arena_episodes.jsonl'
            rows=([row('swim','swim_horizontal',True,session=SID1,parameter=.35)]*30 +
                  [row('swim','swim_horizontal',True,session=SID1,parameter=0.)]*25 +
                  [row('swim','swim_horizontal',False,session=SID1,parameter=0.)]*5 +
                  [row('swim','swim_horizontal_validation',False,split='validation',session=SID1,parameter=.35)]*20 +
                  [row('swim','swim_horizontal_validation',True,split='validation',session=SID1,parameter=0.)]*20)
            save(path,rows)
            p=fit_v4(path);g=p['groups']['swim:0']
            self.assertEqual(g['training_candidate']['offset_or_parameter'],.35)
            self.assertIsNone(g['selected'])
            self.assertFalse(g['validated_for_live'])

    def test_v4_checkpoint_disables_legacy_unvalidated_live_skill(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/'arena_episodes.jsonl'
            save(path,[row('swim','swim_horizontal',True,session=SID1,parameter=-.35)]*30)
            save_v4(fit_v4(path),root/'curriculum_policy_v4.json')
            legacy=train_skill_policy(path)
            legacy['groups']['swim']['validated_for_live']=True
            legacy['groups']['swim']['selected_parameter']=-.35
            legacy['groups']['swim']['options']['-0.35']['wins']=200
            legacy['groups']['swim']['options']['-0.35']['trials']=200
            save_skill_policy(legacy,root/'skill_policy.json')
            self.assertIsNone(LiveSkillPolicy(root/'skill_policy.json').value('swim'))
            save(path,[row('swim','swim_horizontal',True,session=SID1,parameter=-.35)]*30 +
                 [row('swim','swim_horizontal_validation',True,split='validation',session=SID1,parameter=-.35)]*20)
            save_v4(fit_v4(path),root/'curriculum_policy_v4.json')
            self.assertEqual(LiveSkillPolicy(root/'skill_policy.json').value('swim'),-.35)

    def test_action_selection_ignores_old_trial_count_in_v4(self):
        g={'groups':{'swim:0':{'candidates':[{'offset_or_parameter':.35,'brake_after':None,
                                            'current_train_trials':20,'train_score':.9},
                                           {'offset_or_parameter':0.,'brake_after':None,
                                            'current_train_trials':0,'train_score':.1}]}}}
        self.assertEqual(choose_v4_action(g,'swim',0,42,validation=True),(.35,None))


class ScheduleAndReportingTests(unittest.TestCase):
    def test_older_1000_wins_have_at_most_3_effective_prior_samples(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'arena_episodes.jsonl'
            save(path,[row('sprint_jump','gap_1',True,gap=1,offset=.28)]*1000+
                 [row('sprint_jump','gap_1',False,gap=1,session=SID1)]*30)
            schedule=GenerationScheduler((built_in_stages()[0],),path)
            state=schedule.stats['gap_1']
            self.assertEqual(len(state.current),30)
            self.assertLess(state.rate(),.10)
            self.assertLessEqual(state.evidence(),33)

    def test_adaptive_run_writes_its_session_without_refitting_legacy_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            old=root/'skill_policy.json'
            old.write_text('{"original":"preserve-me"}\n',encoding='utf-8')
            runner=ArenaRunner(Mock(),root)
            runner._initialize_bot=lambda at:None
            runner._stop=lambda:None
            def attempt(stage,episode,**kwargs):
                runner._record_misc(stage,True,'arrived_underwater',
                                     [[1.,1.,217.,80.],[2.,12.,217.,80.]],
                                     offset=kwargs.get('offset'),
                                     parameter=kwargs.get('parameter'),
                                     requested_offset=kwargs.get('offset'),
                                     split=kwargs['split'],
                                     scheduler_version=kwargs['scheduler_version'],
                                     base_stage=kwargs['base_stage'],
                                     brake_after=kwargs.get('brake_after'),episode=episode)
                runner.completed+=1
                return True
            runner.attempt=attempt
            stage=(built_in_stages()[3],)
            result=runner.run_adaptive(stage,25,report_every=10)
            self.assertEqual(result['swim_horizontal']['attempts'],25)
            self.assertEqual(old.read_text(encoding='utf-8'),'{"original":"preserve-me"}\n')
            policy=load_v4(root/'curriculum_policy_v4.json')
            self.assertIsNotNone(policy)
            self.assertEqual(policy['current_episodes'],25)
            lines=[json.loads(x) for x in (root/'arena_episodes.jsonl').read_text(encoding='utf-8').splitlines()]
            self.assertEqual(len(set(r['session_id'] for r in lines)),1)
            self.assertEqual(sum(r['split']=='validation' for r in lines),5)

    def test_session_id_and_generation_written_to_new_attempts(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            runner=ArenaRunner(Mock(),root)
            runner.active_session_id=SID1
            runner._record_misc(built_in_stages()[3],True,'arrived_underwater',
                                [[1.,1.,217.,80.],[2.,12.,217.,80.]],
                                parameter=.35, scheduler_version=4)
            written=json.loads((root/'arena_episodes.jsonl').read_text(encoding='utf-8'))
            self.assertTrue(current_episode(written))
            self.assertEqual(written['session_id'],SID1)
            self.assertEqual(written['training_generation'],4)

    def test_report_prioritizes_comparable_v4_latest_session_without_deleting_history(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);log=root/'arena_episodes.jsonl'
            historical=[row('sprint_jump','gap_1',False,gap=1,scorer=1)]*40
            older_correct=[row('sprint_jump','gap_1',False,gap=1,scorer=2)]*20
            earlier=[row('sprint_jump','gap_1',False,gap=1,session=SID1)]*10
            recent=[row('sprint_jump','gap_1',True,gap=1,session=SID2)]*12
            val=[row('sprint_jump','gap_1_validation',True,gap=1,session=SID2,split='validation')]*4
            save(log,historical+older_correct+earlier+recent+val)
            data=build_report(log)
            self.assertEqual(data['total_episodes'],82)
            self.assertEqual(data['latest_session_id'],SID2)
            self.assertEqual(data['current_windows']['gap_1']['rolling_100']['attempts'],22)
            self.assertEqual(data['current_windows']['gap_1']['rolling_100']['success_pct'],54.55)
            self.assertEqual(data['current_windows']['gap_1']['latest_session_train']['success_pct'],100.)
            self.assertEqual(data['current_windows']['gap_1']['latest_session_validation']['attempts'],4)
            self.assertEqual(data['historical_version_counts']['legacy_point_target_jumps'],40)
            paths=export_report(data,root/'reports')
            self.assertEqual(len(paths),4)
            content=(root/'reports/training_report.md').read_text(encoding='utf-8')
            self.assertIn('Current comparable performance',content)
            self.assertIn(SID2,content)
            with (root/'reports/training_current_summary.csv').open(encoding='utf-8',newline='') as stream:
                table=list(csv.DictReader(stream))
            self.assertEqual(table[0]['basis'],'v4_generation')
            self.assertEqual(table[0]['latest_session_train_pct'],'100.0')
            self.assertEqual(len(log.read_text(encoding='utf-8').splitlines()),86)

    def test_before_first_v4_session_corrected_scorer_used_for_window(self):
        with tempfile.TemporaryDirectory() as directory:
            log=Path(directory)/'arena_episodes.jsonl'
            save(log,[row('sprint_jump','gap_3',True,gap=3,scorer=1)]*100+
                 [row('sprint_jump','gap_3',False,gap=3,scorer=2)]*15)
            report=build_report(log)
            self.assertIsNone(report['latest_session_id'])
            self.assertEqual(report['current_windows']['gap_3']['rolling_100']['success_pct'],0.)
            self.assertEqual(report['stages']['gap_3']['attempts'],115)
