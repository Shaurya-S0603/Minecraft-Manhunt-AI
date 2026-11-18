"""v0.7.4 movement physics preflight, observed bandit, synthetic isolation."""
import json
import tempfile
import unittest
from pathlib import Path
from quickstart.observations import Position
from quickstart.terrain import TerrainSensor
from quickstart.tests.test_navigation import FakeScarpet
from quickstart.jump_control import VelocityTracker,SprintJumpController,JumpCorridor
from quickstart.movement_policy import train_from_log,save_policy,load_policy,offset_for_gap
from quickstart.movement_training import MovementTrainer
from quickstart.parkour_sim import train_toy_policy
P=Position

class VelocityTests(unittest.TestCase):
    def test_estimates_projected_speed_not_just_movement(self):
        tracker=VelocityTracker()
        tracker.observe(P(.5,64,.5),1.)
        tracker.observe(P(.9,64,.5),1.2)
        self.assertAlmostEqual(tracker.speed_towards(P(.5,64,.5),P(3.5,64,.5)),2.0)
        self.assertAlmostEqual(tracker.speed_towards(P(.5,64,.5),P(.5,64,3.5)),0.)

    def test_teleport_and_old_samples_fail_closed(self):
        tracker=VelocityTracker()
        tracker.observe(P(.5,64,.5),1)
        tracker.observe(P(30.5,64,.5),1.1)
        self.assertEqual(tracker.speed_towards(P(.5,64,.5),P(3.5,64,.5)),0.)
        tracker.observe(P(31,64,.5),10)
        self.assertEqual(tracker.speed_towards(P(.5,64,.5),P(33.5,64,.5)),0.)

class JumpControlTests(unittest.TestCase):
    def test_waits_for_real_speed_and_lip_position(self):
        j=SprintJumpController(min_speed=1.7)
        key=('jump',1)
        self.assertEqual(j.decide(key,P(.5,64,.5),P(.5,64,.5),P(3.5,64,.5),1,0.,.12).command,'approach')
        self.assertEqual(j.decide(key,P(.9,64,.5),P(.5,64,.5),P(3.5,64,.5),1.2,0.,.12).command,'approach')
        self.assertEqual(j.decide(key,P(.9,64,.5),P(.5,64,.5),P(3.5,64,.5),1.3,2.1,.12).command,'jump')
        self.assertEqual(j.decide(key,P(.99,64,.5),P(.5,64,.5),P(3.5,64,.5),1.4,2.5,.12).command,'hold')

    def test_abort_if_outside_corridor_or_past_takeoff_window(self):
        j=SprintJumpController()
        self.assertEqual(j.decide(1,P(.8,64,1.4),P(.5,64,.5),P(3.5,64,.5),1,3.,.12).command,'abort')
        j.clear()
        self.assertEqual(j.decide(1,P(1.12,64,.5),P(.5,64,.5),P(3.5,64,.5),1,3.,.12).command,'abort')

    def test_full_clearance_and_real_gap(self):
        server=FakeScarpet()
        server.set(1,63,0,'air')
        c=JumpCorridor(TerrainSensor(server,ttl=0))
        self.assertTrue(c.verified(P(.5,64,.5),P(2.5,64,.5)))
        server.set(1,66,0,'oak_leaves')
        self.assertFalse(c.verified(P(.5,64,.5),P(2.5,64,.5)))

    def test_rejects_unobserved_or_non_cardinal_landings(self):
        server=FakeScarpet()
        c=JumpCorridor(TerrainSensor(server,ttl=0))
        self.assertFalse(c.verified(P(.5,64,.5),P(2.5,64,2.5)))
        self.assertFalse(c.verified(P(.5,64,.5),P(8.5,64,.5)))
        server.set(2,63,0,'water')
        self.assertFalse(c.verified(P(.5,64,.5),P(2.5,64,.5)))

class LearnedPolicyTests(unittest.TestCase):
    @staticmethod
    def record(offset,success,source='minecraft',gap=2):
        return {'skill':'sprint_jump','gap':gap,'success':success,
                'source':source,'launch_offset':offset,'approach_speed':3.0,
                'duration_s':.8,'trajectory':[[1.,.5,64,.5],[1.8,3.5,64,.5]]}

    def test_trains_from_real_labeled_trials_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'trials.jsonl'
            rows=[self.record(.20,True) for _ in range(4)]+[self.record(.12,False) for _ in range(3)]
            rows.append(self.record(.36,True,source='toy_simulation_ONLY_NOT_LIVE'))
            p.write_text('\n'.join(json.dumps(x) for x in rows)+'\n')
            model=train_from_log(p)
            self.assertEqual(model['records'],7)
            self.assertEqual(model['groups']['2']['selected_offset'],.20)
            save_policy(model,Path(tmp)/'policy.json')
            loaded=load_policy(Path(tmp)/'policy.json')
            self.assertEqual(offset_for_gap(loaded,2,.12),.20)
            trainer=MovementTrainer(Path(tmp),practice=False)
            self.assertEqual(trainer.launch_threshold_for(2),.20)
            self.assertEqual(trainer.max_trained_gap,1)  # Gap 1 not certified.

    def test_does_not_train_from_missing_or_corrupt_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'trials.jsonl'
            self.assertEqual(train_from_log(p)['records'],0)
            p.write_text('{bad json}\n'+json.dumps(self.record(.20,True,source='toy'))+'\n')
            self.assertEqual(train_from_log(p)['records'],0)

    def test_no_unverified_checkpoint_can_control_live_bot(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'policy.json'
            p.write_text(json.dumps({'schema':1,'source':'toy_simulation_ONLY_NOT_LIVE',
                                     'groups':{'2':{'selected_offset':.36}}}))
            self.assertIsNone(load_policy(p))
            self.assertEqual(MovementTrainer(Path(tmp),practice=False).launch_threshold_for(2),.12)

    def test_four_real_wins_certify_gap_and_learn_timing(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'trials.jsonl'
            rows=[self.record(.28,True,gap=1) for _ in range(4)]
            rows +=[self.record(.28,True,gap=2) for _ in range(4)]
            p.write_text('\n'.join(json.dumps(x) for x in rows)+'\n')
            save_policy(train_from_log(p),Path(tmp)/'policy.json')
            t=MovementTrainer(Path(tmp),practice=False)
            self.assertEqual(t.max_trained_gap,2)
            self.assertEqual(t.launch_threshold_for(2),.28)

class ControlCadenceTests(unittest.TestCase):
    def test_fast_loop_only_near_sprint_jump(self):
        from quickstart.match import ManhuntMatch
        from quickstart.pathfinding3d import PathStep
        from quickstart.tests.test_navigation import FakeScarpet
        bot=ManhuntMatch(FakeScarpet(),'runner',0,30)
        self.assertEqual(bot.movement_tick_delay(),.16)
        bot.path=(PathStep(P(3.5,64,.5),sprint_jump=True),)
        bot.path_index=0
        self.assertEqual(bot.movement_tick_delay(),.05)
        bot.path=(PathStep(P(1.5,64,.5),jump=False),)
        self.assertEqual(bot.movement_tick_delay(),.16)

class ToyRLTests(unittest.TestCase):
    def test_training_repeatable_and_never_labeled_minecraft(self):
        a=train_toy_policy(1000,seed=42)
        b=train_toy_policy(1000,seed=42)
        self.assertEqual(a,b)
        self.assertEqual(a['source'],'toy_simulation_ONLY_NOT_LIVE')
        self.assertEqual(a['evaluation']['episodes'],3000)
        self.assertEqual(len(a['policy']),6)

if __name__=='__main__':unittest.main()
