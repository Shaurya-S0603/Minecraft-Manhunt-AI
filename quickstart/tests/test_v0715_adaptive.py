"""V3: real evidence, separate validation, curriculum and imported research bounds."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from quickstart.arena_training import ArenaRunner,built_in_stages
from quickstart.curriculum_v3 import (AdaptiveScheduler, ACTION_GRIDS, fit_v3,load_v3,save_v3,
                                       read_research_profile,choose_v3_action,validation_variant)
from quickstart.live_skill_policy import LiveSkillPolicy
from quickstart.movement_training import MovementTrainer


def record(skill,stage,success, *, gap=0, parameter=.35, offset=.20, brake=None,
           split='train', version=3, reason=None):
    return {'schema':1,'source':'minecraft','skill':skill,'stage':stage,'gap':gap,
            'success':success,'parameter':parameter,'requested_offset':offset,
            'brake_after':brake,'scorer_version':2 if skill=='sprint_jump' else 1,
            'split':split,'scheduler_version':version,'base_stage':stage.replace('_validation',''),
            'reason':reason or ('landed' if success else 'timeout'),'duration_s':1.,
            'samples':[[10.,1.,220.,1.],[11.,2.,220.,1.]]}


def write(path, rows):
    path.write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf-8')


class EvidenceTests(unittest.TestCase):
    def test_never_train_from_unverified_mine_ai_observations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); research=root/'mine_ai_tools.jsonl'; log=root/'episodes.jsonl'
            raw={'schema':1,'source':'aibengineering/beat-the-game-minecraft',
                 'category':'navigation','action':'navigate_to','result_status':'unverified_result'}
            write(research,[raw]*100)
            write(log,[{**record('swim','swim_horizontal',True),'source':'aibengineering/beat-the-game-minecraft'}]*100)
            profile=read_research_profile(research)
            model=fit_v3(log,research_profile=profile)
            self.assertEqual(profile['records'],100)
            self.assertEqual(profile['verified_movement_labels'],0)
            self.assertLessEqual(profile['curriculum_bias']['swim'],.08)
            self.assertEqual(model['episodes'],0)
            self.assertFalse(model['groups']['swim:0']['validated_for_live'])

    def test_untrusted_metadata_rejected_without_exec(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'research.jsonl'
            write(path,[{'schema':1,'source':'evil','category':'navigation','action':'navigate',
                         'result_status':'unverified_result'},
                        {'schema':1,'source':'aibengineering/beat-the-game-minecraft',
                         'category':'navigation','action':'__import__("os")',
                         'result_status':'unverified_result'}])
            self.assertEqual(read_research_profile(path)['records'],0)

    def test_no_validation_no_certification_despite_500_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'arena.jsonl'
            write(path,[record('swim','swim_horizontal',True)]*500)
            result=fit_v3(path)
            self.assertEqual(result['episodes'],500)
            self.assertIsNone(result['groups']['swim:0']['selected'])

    def test_holdout_does_not_leak_into_train_stats(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'arena.jsonl'
            rows=[record('swim','swim_horizontal',False)]*20
            rows += [record('swim','swim_horizontal_validation',True,split='validation')]*50
            write(path,rows)
            result=fit_v3(path)
            arm=[x for x in result['groups']['swim:0']['candidates'] if x['offset_or_parameter']==.35][0]
            self.assertEqual((arm['train_wins'],arm['validation_wins']), (0,50))
            self.assertFalse(arm['live_eligible'])

    def test_validated_but_not_perfect_arm_certifies(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'arena.jsonl'
            rows=[record('climb','ladder_up',True,parameter=1.45)]*45
            rows += [record('climb','ladder_up_validation',True,parameter=1.45,split='validation')]*16
            write(path,rows)
            p=fit_v3(path)
            self.assertTrue(p['groups']['climb:0']['validated_for_live'])
            save_v3(p,Path(tmp)/'curriculum_policy_v3.json')
            self.assertEqual(load_v3(Path(tmp)/'curriculum_policy_v3.json'),p)
            live=LiveSkillPolicy(Path(tmp)/'skill_policy.json')
            self.assertEqual(live.value('climb'),1.45)

    def test_jump_old_scorer_cannot_train_new_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'arena.jsonl'
            old=[{**record('sprint_jump','gap_1',True,gap=1),'scorer_version':1}]*150
            write(path,old)
            self.assertEqual(fit_v3(path)['episodes'],0)

    def test_manual_opt_out_falls_back_even_if_v3_valid(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'arena.jsonl'
            rows=[record('swim','swim_horizontal',True)]*40 + [record('swim','swim_horizontal_validation',True,split='validation')]*15
            write(path,rows)
            save_v3(fit_v3(path),Path(tmp)/'curriculum_policy_v3.json')
            with patch.dict('os.environ',{'MANHUNT_LIVE_SKILLS':'0'}):
                self.assertEqual(LiveSkillPolicy(Path(tmp)/'skill_policy.json').selected,{})

    def test_jump_selection_uses_only_verified_v3(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'arena_episodes.jsonl'
            rows=[record('sprint_jump','gap_2',True,gap=2,offset=.28,brake=.6)]*40
            rows += [record('sprint_jump','gap_2_validation',True,gap=2,offset=.28,brake=.6,split='validation')]*16
            write(path,rows)
            save_v3(fit_v3(path),Path(tmp)/'curriculum_policy_v3.json')
            trainer=MovementTrainer(Path(tmp),practice=False)
            self.assertEqual(trainer.launch_threshold_for(2),.28)
            self.assertEqual(trainer.max_trained_gap,1)  # v3 timing cannot unlock unsafe jumps alone


class SchedulerTests(unittest.TestCase):
    def test_budget_counts_total_not_per_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner=ArenaRunner(Mock(),Path(tmp))
            runner._initialize_bot=lambda at:None
            runner._stop=lambda:None
            calls=[]
            def attempt(stage, episode, **kwargs):
                calls.append((stage.name,kwargs.get('split')))
                runner.completed+=1
                return stage.skill!='sprint_jump'
            runner.attempt=attempt
            runner.fit_all_policies=lambda:None
            result=runner.run_adaptive(built_in_stages(),40,report_every=20)
            self.assertEqual(len(calls),40)
            self.assertEqual(sum(r['attempts'] for r in result.values()),40)
            self.assertEqual(sum(r['validation'] for r in result.values()),8)
            self.assertEqual(sum(split=='validation' for _,split in calls),8)
            self.assertGreater(sum(r['attempts'] for k,r in result.items() if k.startswith('gap')),20)

    def test_mastered_skills_still_receive_regression_trials(self):
        with tempfile.TemporaryDirectory() as tmp:
            schedule=AdaptiveScheduler(built_in_stages(),Path(tmp)/'missing.jsonl')
            for _ in range(1000):
                stage,_,validation=schedule.next()
                schedule.record(stage,stage.skill!='sprint_jump',validation=validation)
            self.assertGreaterEqual(schedule.session_attempts['swim_horizontal'],95)
            self.assertGreaterEqual(schedule.session_attempts['ladder_up'],95)
            self.assertGreater(sum(schedule.session_attempts[x] for x in ('gap_1','gap_2','gap_3')),500)

    def test_validation_is_alternate_runup_and_lateral_lane(self):
        base=built_in_stages()[1]
        shifted=validation_variant(base)
        self.assertNotEqual(base.start,shifted.start)
        self.assertEqual(base.gap,shifted.gap)
        self.assertEqual(shifted.skill,'sprint_jump')
        self.assertEqual(shifted.start.z-base.start.z,1)

    def test_history_counts_ignore_validation_outcomes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'episodes.jsonl'; stages=built_in_stages()[3:4]
            write(path,[record('swim','swim_horizontal',False)]*7 +
                  [record('swim','swim_horizontal_validation',True,split='validation')]*12)
            s=AdaptiveScheduler(stages,path)
            self.assertEqual(s.stats['swim_horizontal'].trials,7)
            self.assertEqual(s.attempts['swim_horizontal'],19)
            self.assertEqual(s.next()[1],20)

    def test_action_exploration_and_validation_preference(self):
        group={'groups':{'swim:0':{'candidates':[{'offset_or_parameter':.35,'brake_after':None,
                                               'train_trials':20,'score':.80},
                                             {'offset_or_parameter':0.,'brake_after':None,
                                               'train_trials':5,'score':.10}]}}}
        self.assertEqual(choose_v3_action(group,'swim',0,10,validation=True),(.35,None))
        self.assertIn(choose_v3_action(group,'swim',0,5),ACTION_GRIDS['swim'])
