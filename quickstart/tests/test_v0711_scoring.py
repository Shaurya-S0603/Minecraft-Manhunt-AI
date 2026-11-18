"""v0.7.11 regression: real platform landings, not point-based success labels."""
import json
import tempfile
import unittest
from pathlib import Path
from quickstart.observations import Position as P
from quickstart.arena_training import built_in_stages,read_stages,write_stage_template
from quickstart.jump_training_v2 import (zone_for_stage,classify_jump,fit_v2,load_v2,
                                          save_v2,choose_training_action)
from quickstart.movement_training import MovementTrainer

class GeometryAndScoring(unittest.TestCase):
    def test_all_generated_jumps_use_entire_verified_platform(self):
        for s in built_in_stages()[:3]:
            zone=zone_for_stage(s)
            self.assertTrue(zone.contains(P(10.5,220,s.target.z)))
            self.assertFalse(zone.contains(P(6.2,220,s.target.z)))
            self.assertFalse(zone.contains(P(16.1,220,s.target.z)))

    def test_one_block_jump_lands_farther_than_old_point_and_still_succeeds(self):
        zone=zone_for_stage(built_in_stages()[0])
        # Old classifier rejected this despite it landing on the safe platform.
        self.assertGreater(P(9.5,220,.5).distance(built_in_stages()[0].target),.72)
        self.assertEqual(classify_jump(zone,P(9.5,220,.5),grounded=True,
                                       airborne_seen=True,duration=.7),
                         (True,True,'landed'))

    def test_undershoot_and_overshoot_are_not_confused(self):
        zone=zone_for_stage(built_in_stages()[1])
        self.assertEqual(classify_jump(zone,P(6.5,220,20.5),grounded=True,
                                       airborne_seen=True,duration=.5)[2],'undershoot')
        self.assertEqual(classify_jump(zone,P(16.6,220,20.5),grounded=True,
                                       airborne_seen=True,duration=.5)[2],'overshoot')
        self.assertEqual(classify_jump(zone,P(9,220,25),grounded=True,
                                       airborne_seen=True,duration=.5)[2],'lateral_miss')

    def test_aerial_pass_through_is_not_a_success(self):
        zone=zone_for_stage(built_in_stages()[0])
        self.assertEqual(classify_jump(zone,P(9.5,220,.5),grounded=False,
                                       airborne_seen=True,duration=.5)[0],False)
        self.assertEqual(classify_jump(zone,P(9.5,218,.5),grounded=False,
                                       airborne_seen=True,duration=.5)[2],'fell_below_platform')
        self.assertEqual(classify_jump(zone,P(9.5,220,.5),grounded=True,
                                       airborne_seen=False,duration=.5)[0],False)

    def test_landing_zone_roundtrips_through_course_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest=Path(tmp)/'course.json'; write_stage_template(dest,built_in_stages())
            self.assertEqual(read_stages(dest),built_in_stages())

class PolicyTests(unittest.TestCase):
    @staticmethod
    def row(gap=1,offset=.20,brake_after=.6,success=True,version=2):
        return {'skill':'sprint_jump','gap':gap,'source':'minecraft',
                'success':success,'scorer_version':version,
                'platform_scoring_v2':version==2,'landing_verified':success and version==2,
                'launch_offset':offset,'brake_after':brake_after,
                'duration_s':.6,'trajectory':[[0,0,220,0],[.3,1,221,0],[.6,3,220,0]]}

    def test_old_and_toy_results_do_not_train_platform_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'trials.jsonl'
            a=self.row(version=1)
            b=self.row();b['source']='toy_simulation_ONLY_NOT_LIVE'
            p.write_text(json.dumps(a)+'\n'+json.dumps(b)+'\n')
            self.assertEqual(fit_v2(p)['records'],0)

    def test_positive_and_negative_trials_select_better_braking(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'trials.jsonl'
            rows=[self.row(success=True) for _ in range(12)]
            rows += [self.row(brake_after=None,success=False) for _ in range(15)]
            rows += [self.row(version=1,success=True) for _ in range(200)]
            p.write_text(''.join(json.dumps(x)+'\n' for x in rows))
            model=fit_v2(p)
            self.assertEqual(model['records'],27)
            self.assertEqual(model['groups']['1']['selected'],{'offset':.20,'brake_after':.6})
            self.assertIsNone(model['groups']['2']['selected'])
            dst=Path(tmp)/'jump_policy_v2.json';save_v2(model,dst)
            self.assertEqual(load_v2(dst),model)
            self.assertEqual(choose_training_action(model,1,21),(.20,.6))
            self.assertEqual(choose_training_action(model,1,20),(.28,.6))

    def test_v2_certification_uses_corrected_trials_not_old_ones(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'trials.jsonl'
            data=[self.row(gap=1,version=1) for _ in range(30)]
            data += [self.row(gap=2,version=1) for _ in range(30)]
            data += [self.row(gap=2,success=False) for _ in range(10)]
            p.write_text(''.join(json.dumps(x)+'\n' for x in data))
            trainer=MovementTrainer(Path(tmp),practice=False)
            self.assertEqual(trainer.max_trained_gap,1)

if __name__=='__main__':unittest.main()

class OfflineIntegrationTests(unittest.TestCase):
    def test_corrected_trial_logs_grounded_platform_and_braking(self):
        from unittest.mock import Mock
        from quickstart.arena_training import ArenaRunner
        class Clock:
            now=100.
            def __call__(self):return self.now
            def sleep(self,d):self.now+=d
        with tempfile.TemporaryDirectory() as tmp:
            clock=Clock()
            rcon=Mock();rcon.command.return_value='OK'
            runner=ArenaRunner(rcon,Path(tmp),clock=clock,sleep=clock.sleep)
            stage=built_in_stages()[0]
            # A 1-block gap landing that originally failed because it was
            # nearly 3 blocks past the single goal point but on stone.
            xs=[1.5,1.5,1.8,2.2,2.5,2.9,3.3,3.7,4.1,4.5,4.9,5.2,5.5,5.75,6.0,6.4,6.8,7.2,7.7,8.4,9.2,9.6]
            poses=[P(x,220.,.5) for x in xs[:14]] + [
                P(6.,220.3,.5),P(6.4,220.8,.5),P(6.8,221.,.5),
                P(7.2,221.,.5),P(7.7,220.8,.5),P(8.4,220.45,.5),
                P(9.2,220.15,.5),P(9.6,220.,.5)]
            ix=[0]
            def sensor(_):
                k=min(ix[0],len(poses)-1);ix[0]+=1;return poses[k]
            runner.observer.position=sensor
            runner._grounded=lambda p: p.y==220.
            runner._confirm_stage=lambda _:None
            self.assertTrue(runner.attempt(stage,1,offset=.2,brake_after=.6))
            data=json.loads((Path(tmp)/'trials.jsonl').read_text().strip())
            self.assertEqual(data['scorer_version'],2)
            self.assertTrue(data['platform_scoring_v2'])
            self.assertTrue(data['landing_verified'])
            self.assertEqual(data['reason'],'landed')
            self.assertEqual(data['brake_after'],.6)
            self.assertTrue(any('player ManhuntBot stop' in c.args[0] for c in rcon.command.call_args_list))
            self.assertEqual(fit_v2(Path(tmp)/'trials.jsonl')['records'],1)

    def test_reports_separate_uncorrected_and_corrected_jump_labels(self):
        from quickstart.arena_report import build_report,export_report
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            rows=[]
            for version in (1,2):
                row=PolicyTests.row(version=version)
                row.update(stage='gap_1',samples=row['trajectory'],episode=1,
                           parameter=None,reason='landed' if version==2 else 'missed_or_timed_out')
                rows.append(row)
            (root/'arena_episodes.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in rows))
            (root/'trials.jsonl').write_text(json.dumps(PolicyTests.row())+'\n')
            report=build_report(root/'arena_episodes.jsonl')
            self.assertEqual(report['jump_diagnostics']['legacy_episodes'],1)
            self.assertEqual(report['jump_diagnostics']['corrected_episodes'],1)
            export_report(report,root/'output')
            self.assertIn('Legacy point-target records',(root/'output/training_report.md').read_text(encoding='utf-8'))
