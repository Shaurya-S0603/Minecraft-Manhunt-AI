"""Movement training v0.7.3: measured outcomes and conservative world scans."""
import tempfile
import json
import unittest
from pathlib import Path
from unittest.mock import Mock
from quickstart.observations import Position
from quickstart.movement_training import MovementTrainer
from quickstart.terrain import TerrainSensor
from quickstart.pathfinding3d import BoundedAStar
from quickstart.waterdrop import WaterDropPlanner
from quickstart.swimming import WaterSurvival
from quickstart.tests.test_navigation import FakeScarpet
from quickstart.tests.test_v06 import SwimmingRcon
from quickstart.match import ManhuntMatch

P=Position

class TrainingTests(unittest.TestCase):
    def test_water_drop_stays_disabled_without_enough_observed_successes(self):
        with tempfile.TemporaryDirectory() as temp:
            t=MovementTrainer(Path(temp),practice=False)
            self.assertFalse(t.water_drop_ready)
            for attempt in range(4):
                start=100+attempt*10
                t.begin('water_drop',P(.5,64,.5),P(2.5,59,.5),start)
                t.observe(P(1.5,61,.5),start+.3,grounded=False)
                self.assertTrue(t.observe(P(2.5,58.5,.5),start+.8,grounded=True))
            self.assertTrue(MovementTrainer(Path(temp),practice=False).water_drop_ready)

    def test_no_auto_long_jump_before_real_success(self):
        with tempfile.TemporaryDirectory() as temp:
            t=MovementTrainer(Path(temp),practice=False)
            self.assertEqual(t.allowed_gap,1)
            self.assertFalse(t.log_file.exists())

    def test_jump_requires_observed_airborne_then_landing(self):
        with tempfile.TemporaryDirectory() as temp:
            t=MovementTrainer(Path(temp),practice=True)
            t.begin('sprint_jump',P(.7,64,.5),P(3.5,64,.5),100.,gap=2)
            # Bot walking at the goal must not masquerade as a trained jump.
            self.assertIsNone(t.observe(P(3.5,64,.5),100.6,grounded=True))
            self.assertIsNone(t.observe(P(1.5,64.5,.5),100.8,grounded=False))
            self.assertTrue(t.observe(P(3.5,64,.5),101.3,grounded=True))
            self.assertTrue(t.log_file.exists())
            sample=json.loads(t.log_file.read_text().splitlines()[0])
            self.assertEqual(sample['gap'],2)
            self.assertTrue(sample['success'])
            self.assertGreaterEqual(len(sample['trajectory']),3)

    def test_training_wont_unlock_long_jump_without_four_wins(self):
        with tempfile.TemporaryDirectory() as temp:
            t=MovementTrainer(Path(temp),practice=True)
            for i in range(3):
                at=100.+i*10
                t.begin('sprint_jump',P(.7,64,.5),P(3.5,64,.5),at,gap=2)
                t.observe(P(1,64.6,.5),at+.2,grounded=False)
                t.observe(P(3.5,64,.5),at+.7,grounded=True)
            fresh=MovementTrainer(Path(temp),practice=False)
            self.assertEqual(fresh.allowed_gap,1)
            t.begin('sprint_jump',P(.7,64,.5),P(3.5,64,.5),130,gap=2)
            t.observe(P(1,64.6,.5),130.2,grounded=False)
            t.observe(P(3.5,64,.5),130.7,grounded=True)
            fresh=MovementTrainer(Path(temp),practice=False)
            self.assertEqual(fresh.allowed_gap,2)

    def test_supervised_practice_rotates_takeoff_offsets(self):
        with tempfile.TemporaryDirectory() as temp:
            t=MovementTrainer(Path(temp),practice=True)
            self.assertAlmostEqual(t.launch_threshold,.12)
            t.begin('sprint_jump',P(.7,64,.5),P(3.5,64,.5),100,gap=2,launch_offset=.12)
            t.observe(P(1,64.5,.5),100.2,grounded=False)
            t.observe(P(3.5,64,.5),100.8,grounded=True)
            self.assertAlmostEqual(t.launch_threshold,.20)

    def test_timeout_records_failure_no_false_learning(self):
        with tempfile.TemporaryDirectory() as temp:
            t=MovementTrainer(Path(temp))
            t.begin('sprint_jump',P(.7,64,.5),P(3.5,64,.5),10,gap=2)
            self.assertFalse(t.observe(P(1.3,64,.5),14,grounded=True))
            self.assertEqual(t.max_trained_gap,1)
            self.assertFalse(json.loads(t.log_file.read_text())['success'])

    def test_training_data_writes_only_local_path(self):
        with tempfile.TemporaryDirectory() as temp:
            t=MovementTrainer(Path(temp),practice=False)
            t.begin('sprint_jump',P(0,64,0),P(2,64,0),10,gap=1)
            t.observe(P(0,64,0),14,grounded=True)
            self.assertTrue(t.log_file.is_relative_to(temp))

class WaterDropTests(unittest.TestCase):
    def world(self):
        w=FakeScarpet()
        # The bot stands at 0.5,64,0.5. At x=2, a 6-block ravine has a
        # two-block-deep water pool, with a solid bed at y=56.
        for k in range(57,59):
            for xx in (1,2,3):
                for zz in (-1,0,1): w.set(xx,k,zz,'water')
        for k in range(57,64): w.set(2,k,0,'air') if k>=59 else None
        for k in (64,65,66): w.set(2,k,0,'air')
        for k in (64,65,66): w.set(1,k,0,'air')
        return w

    def test_finds_two_deep_water_pool_with_clear_drop(self):
        w=self.world()
        drop=WaterDropPlanner(TerrainSensor(w,ttl=0)).propose(P(.5,64,.5),P(8,57,.5))
        self.assertIsNotNone(drop)
        self.assertEqual(drop.destination,P(2.5,59,.5))
        self.assertGreaterEqual(drop.depth,5)

    def test_fails_closed_on_one_block_deep_pool(self):
        w=self.world()
        w.set(2,57,0,'stone')
        result=WaterDropPlanner(TerrainSensor(w,ttl=0)).propose(P(.5,64,.5),P(8,57,.5))
        self.assertIsNone(result)

    def test_refuses_lava_and_blocked_airshaft(self):
        w=self.world()
        w.set(2,59,0,'oak_log')
        self.assertIsNone(WaterDropPlanner(TerrainSensor(w,ttl=0)).propose(P(.5,64,.5),P(8,57,.5)))
        w.set(2,59,0,'air');w.set(2,58,0,'lava')
        self.assertIsNone(WaterDropPlanner(TerrainSensor(w,ttl=0)).propose(P(.5,64,.5),P(8,57,.5)))

    def test_refuses_unknown_takeoff_support(self):
        w=self.world(); w.set(0,63,0,'water')
        self.assertIsNone(WaterDropPlanner(TerrainSensor(w,ttl=0)).propose(P(.5,64,.5),P(8,57,.5)))

class LongJumpPlannerTests(unittest.TestCase):
    def test_two_gap_route_requires_explicit_calibration(self):
        w=FakeScarpet()
        for x in (1,2):
            for y in range(59,64): w.set(x,y,0,'air')
        for x in range(-1,6):
            for z in (-1,1):
                for y in (64,65,66): w.set(x,y,z,'oak_log')
        default=BoundedAStar(TerrainSensor(w,ttl=0),max_gap=1).plan(P(.5,64,.5),P(3.5,64,.5))
        # The default planner must not shortcut the gap; a long detour is fine.
        self.assertFalse(any(s.sprint_jump for s in default.steps))
        calibrated=BoundedAStar(TerrainSensor(w,ttl=0),max_gap=2).plan(P(.5,64,.5),P(3.5,64,.5))
        self.assertTrue(calibrated.reached_goal)
        self.assertTrue(any(s.sprint_jump for s in calibrated.steps))

    def test_long_jump_refused_if_ceiling_blocks_middle(self):
        w=FakeScarpet()
        for x in (1,2):
            for y in range(59,64):w.set(x,y,0,'air')
        w.set(2,66,0,'stone')
        planner=BoundedAStar(TerrainSensor(w),max_gap=2)
        blocks,_=planner._grid((0,64,0))
        # The specific 3-cell jump must not be offered.
        self.assertEqual(planner._kind(blocks,2,66,0),'solid')

class SwimControlTests(unittest.TestCase):
    def test_level_swimming_doesnt_hold_jump(self):
        server=SwimmingRcon()
        server.set(0,64,0,'water');server.set(0,65,0,'water')
        swim=WaterSurvival(server,TerrainSensor(server,ttl=0))
        swim.update(P(.5,64,.5),100.,stop_movement=Mock(),vertical=0)
        self.assertFalse(any('jump continuous' in command for command in server.calls))
        self.assertEqual(swim.vertical_mode,0)

    def test_swimming_pitch_and_sprint(self):
        server=FakeScarpet()
        game=ManhuntMatch(server,'runner',0,30)
        game.water.swimming=True
        game.observer.position=lambda name:P(.5,64,.5)
        game.look_and_move(P(3.5,62,.5))
        self.assertTrue(any('look at 3.50 62.50' in c for c in server.calls))

if __name__=='__main__':unittest.main()
