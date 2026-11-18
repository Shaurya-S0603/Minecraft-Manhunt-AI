"""Regression suite for the map-free, multi-skill 1000-episode trainer."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from quickstart.skill_policy import choose_parameter,train_skill_policy,load_skill_policy,save_skill_policy
from quickstart.arena_training import ArenaRunner,built_in_stages
from quickstart.arena_report import build_report,export_report,wilson
from quickstart.training_server import main as training_main


def episode(skill, stage, success, parameter=0., duration=1., reason=None):
    return {'schema':1,'source':'minecraft','skill':skill,'stage':stage,
            'success':success,'parameter':parameter,
            'reason':reason or ('arrived_underwater' if success and skill=='swim' else 'timeout'),
            'duration_s':duration,'samples':[[100.,0.,220.,0.],[101.,1.,220.,0.]]}

class MultiSkillTests(unittest.TestCase):
    def test_no_training_when_no_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            policy=train_skill_policy(root/'missing.jsonl')
            self.assertEqual(policy['episodes'],0)
            self.assertIsNone(policy['groups']['swim']['selected_parameter'])
            self.assertIsNone(policy['groups']['climb']['selected_parameter'])

    def test_policy_uses_only_minecraft_trials_and_skills_separately(self):
        with tempfile.TemporaryDirectory() as tmp:
            log=Path(tmp)/'arena_episodes.jsonl'
            rows=[episode('swim','swim_horizontal',True,.35) for _ in range(15)]
            rows += [episode('swim','swim_horizontal',False,0.) for _ in range(10)]
            rows += [episode('climb','ladder_up',True,1.45) for _ in range(15)]
            rows += [episode('climb','ladder_up',False,.45) for _ in range(10)]
            rows += [{**episode('swim','swim_horizontal',True,0.),'source':'toy'} for _ in range(70)]
            log.write_text(''.join(json.dumps(r)+'\n' for r in rows))
            policy=train_skill_policy(log)
            self.assertEqual(policy['episodes'],50)
            self.assertEqual(policy['groups']['swim']['selected_parameter'],.35)
            self.assertEqual(policy['groups']['climb']['selected_parameter'],1.45)
            self.assertTrue(policy['groups']['swim']['validated_for_live'])
            output=Path(tmp)/'skill_policy.json'
            save_skill_policy(policy,output)
            self.assertEqual(load_skill_policy(output),policy)

    def test_exploration_does_not_disappear(self):
        p={'groups':{'swim':{'selected_parameter':0.35}}}
        self.assertEqual(choose_parameter(p,'swim',1),-.35)
        self.assertEqual(choose_parameter(p,'swim',20),0.0)  # periodic deliberate exploration
        self.assertEqual(choose_parameter(p,'swim',21),.35)

    def test_1000_episodes_per_course_and_interleave(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner=ArenaRunner(Mock(),Path(tmp))
            runner._initialize_bot=lambda at: None
            runner.reset=lambda stage: None
            runner._confirm_stage=lambda stage: None
            calls=[]
            def attempt(stage,e,**kw):
                calls.append((stage.name,e,kw.get('parameter')))
                runner.completed+=1
                return True
            runner.attempt=attempt
            runner.fit_all_policies=lambda: None
            stages=built_in_stages()[3:]
            results=runner.run(stages,1000,interleave=True)
            self.assertEqual(len(calls),2000)
            self.assertEqual(calls[0][:2],('swim_horizontal',1))
            self.assertEqual(calls[1][:2],('ladder_up',1))
            self.assertEqual(calls[2][:2],('swim_horizontal',2))
            self.assertEqual(calls[-1][:2],('ladder_up',1000))
            self.assertEqual(results['swim_horizontal']['attempts'],1000)
            self.assertEqual(results['ladder_up']['successes'],1000)

    def test_full_multi_skill_report_and_guidance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            rows=[episode('swim','swim_horizontal',False,0.,2.,'left_water') for _ in range(50)]
            rows += [episode('swim','swim_horizontal',True,.35,1.) for _ in range(50)]
            rows += [episode('climb','ladder_up',True,1.45,2.) for _ in range(40)]
            (root/'arena_episodes.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
            sp=train_skill_policy(root/'arena_episodes.jsonl')
            save_skill_policy(sp,root/'skill_policy.json')
            result=build_report(root/'arena_episodes.jsonl',root/'policy.json',root/'skill_policy.json')
            self.assertEqual(result['total_episodes'],140)
            self.assertGreater(result['stages']['swim_horizontal']['progress']['change_percentage_points'],50)
            self.assertTrue(any('Swim trials leave water' in s for s in result['stages']['swim_horizontal']['recommendations']))
            files=export_report(result,root/'reports')
            self.assertTrue(all(x.exists() for x in files))
            self.assertIn('Early → recent',(root/'reports/training_report.md').read_text(encoding='utf-8'))
            self.assertIn('left_water',(root/'reports/training_summary.csv').read_text(encoding='utf-8'))
            self.assertIn('Early → recent', (root/'reports/training_report.md').read_bytes().decode('utf-8'))

    def test_confidence_intervals_bounded(self):
        self.assertEqual(wilson(0,0),(0,1))
        for n,w in ((20,20),(100,75),(100,0)):
            low,high=wilson(w,n)
            self.assertTrue(0<=low<=high<=1)
            self.assertTrue(low-1e-9<=w/n<=high+1e-9)

if __name__=='__main__': unittest.main()
