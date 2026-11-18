"""v0.7.14: water crossing must preserve horizontal steering and escape bobbing."""
from __future__ import annotations

import io
import time
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock

from quickstart.match import ManhuntMatch
from quickstart.observations import Position
from quickstart.pathfinding3d import PathStep
from quickstart.swimming import WaterSurvival
from quickstart.terrain import TerrainSensor
from quickstart.tests.test_v06 import SwimmingRcon

P = Position


class SurfaceControlTests(unittest.TestCase):
    def setUp(self):
        self.server=SwimmingRcon()
        self.sensor=TerrainSensor(self.server,ttl=0)
        self.water=WaterSurvival(self.server,self.sensor)
        self.stop=Mock()

    def test_shallow_one_block_water_does_not_engage_continuous_jump(self):
        self.server.set(0,64,0,'water')
        self.assertTrue(self.water.update(P(.5,64,.5),100,stop_movement=self.stop,vertical=1))
        self.assertFalse(self.water.head_submerged)
        self.assertEqual(self.water.vertical_mode,0)
        self.assertFalse(any(c.endswith('jump continuous') for c in self.server.calls))
        self.stop.assert_not_called()

    def test_shallow_to_land_retains_existing_forward_movement(self):
        self.server.set(0,64,0,'water')
        self.water.update(P(.5,64,.5),100,stop_movement=self.stop,vertical=0)
        self.server.set(0,64,0,'air')
        self.assertFalse(self.water.update(P(.5,64,.5),101,stop_movement=self.stop))
        self.stop.assert_not_called()
        self.assertFalse(self.water.swimming)

    def test_deep_swim_vertical_mode_hysteresis_avoids_rapid_full_stops(self):
        self.server.set(0,64,0,'water')
        self.server.set(0,65,0,'water')
        self.water.update(P(.5,64,.5),100,stop_movement=self.stop,vertical=1)
        self.water.update(P(.5,64,.5),100.2,stop_movement=self.stop,vertical=0)
        self.water.update(P(.5,64,.5),100.4,stop_movement=self.stop,vertical=1)
        self.assertEqual(self.water.vertical_mode,1)
        self.stop.assert_not_called()
        self.water.update(P(.5,64,.5),101.2,stop_movement=self.stop,vertical=0)
        self.assertEqual(self.water.vertical_mode,0)
        self.stop.assert_called_once()

    def test_surface_transition_cancels_held_ascent_once(self):
        self.server.set(0,64,0,'water')
        self.server.set(0,65,0,'water')
        self.water.update(P(.5,64,.5),100,stop_movement=self.stop,vertical=1)
        self.server.set(0,65,0,'air')
        self.water.update(P(.5,64,.5),100.2,stop_movement=self.stop,vertical=1)
        self.assertEqual(self.water.vertical_mode,0)
        self.water.update(P(.5,64,.5),100.4,stop_movement=self.stop,vertical=1)
        self.stop.assert_called_once()
        self.assertEqual(self.water.vertical_switches,2)

    def test_real_position_stall_tracking_not_reset_by_waypoints(self):
        self.server.set(0,64,0,'water')
        self.water.update(P(.5,64,.5),100,stop_movement=self.stop,vertical=0)
        self.water.update(P(.5,64.25,.5),102,stop_movement=self.stop,vertical=0)
        self.assertFalse(self.water.stall_detected)
        self.water.update(P(.5,64.5,.5),103.6,stop_movement=self.stop,vertical=0)
        self.assertTrue(self.water.stall_detected)
        self.assertEqual(self.water.stall_events,1)
        self.server.set(1,64,0,'water')
        self.water.update(P(1.0,64.5,.5),104,stop_movement=self.stop,vertical=0)
        self.assertFalse(self.water.stall_detected)
        self.assertEqual(self.water.horizontal_anchor,(1.0,.5))

    def test_real_vertical_climb_does_not_count_as_swim_stall(self):
        for y in range(64,69):
            self.server.set(0,y,0,'water')
        self.water.update(P(.5,64,.5),100,stop_movement=self.stop,vertical=1)
        self.water.update(P(.5,64.8,.5),102,stop_movement=self.stop,vertical=1)
        self.water.update(P(.5,65.4,.5),104,stop_movement=self.stop,vertical=1)
        self.assertFalse(self.water.stall_detected)
        self.assertEqual(self.water.stall_events,0)

    def test_low_air_overrides_surface_hysteresis_for_ascent(self):
        self.server.set(0,64,0,'water')
        self.water.update(P(.5,64,.5),100,stop_movement=self.stop,vertical=0)
        self.server.air=110
        self.water.update(P(.5,64,.5),101.2,stop_movement=self.stop,vertical=-1)
        self.assertEqual(self.water.vertical_mode,1)
        self.assertTrue(any(c.endswith('jump continuous') for c in self.server.calls))


class RouteControlTests(unittest.TestCase):
    def setUp(self):
        self.server=SwimmingRcon()
        self.game=ManhuntMatch(self.server,'hunter',0,40)

    def test_surface_water_arrival_accepts_nearby_height_difference(self):
        game=self.game
        game.water.swimming=True
        game.water.head_submerged=False
        step=PathStep(P(.5,65,.5),swimming=True)
        self.assertTrue(game.swim_waypoint_reached(P(.5,64,.5),step,P(.5,64,.5)))
        game.water.head_submerged=True
        self.assertFalse(game.swim_waypoint_reached(P(.5,64,.5),step,P(.5,64,.5)))
        game.water.head_submerged=False
        self.assertFalse(game.swim_waypoint_reached(P(.5,64,.5),PathStep(P(.5,65,.5)),None))

    def test_vertical_swimming_segment_does_not_cancel_upward_control(self):
        game=self.game
        game.path=(PathStep(P(.5,65,.5),swimming=True,jump=True),)
        game.path_start=P(.5,64,.5)
        game.path_goal=P(.5,65,.5)
        now=time.monotonic()
        game.path_created_at=now
        game.water.swimming=True
        game.water.head_submerged=True
        game.water.vertical_mode=1
        game.moving=True
        game.pathfinder.is_airborne=Mock(return_value=False)
        game.stop=Mock()
        with redirect_stdout(io.StringIO()):
            game.navigate(P(.5,64,.5),P(.5,65,.5),now)
        game.stop.assert_not_called()
        self.assertEqual(game.water.vertical_mode,1)

    def test_wading_crossing_keeps_forward_commands_through_waypoints(self):
        game=self.game
        self.server.set(0,64,0,'water')
        self.server.set(1,64,0,'water')
        self.server.set(2,64,0,'water')
        game.observer.position=lambda who: P(.5,64,.5)
        game.water.update(P(.5,64,.5),100,stop_movement=game.stop,vertical=1)
        self.assertEqual(game.water.vertical_mode,0)
        game.navigate(P(.5,64,.5),P(4.5,64,.5),100.)
        self.assertIn('player ManhuntBot move forward',self.server.calls)
        self.assertNotIn('player ManhuntBot jump continuous',self.server.calls)
        self.assertNotIn('player ManhuntBot stop',self.server.calls)

    def test_water_stall_triggers_safe_replan_and_disables_learned_offset(self):
        game=self.game
        game.player='Alex'
        game.hit_detector=Mock()
        game.hit_detector.hunter_hit.return_value=False
        game.observer.position=lambda who: P(.5,64,.5) if who==game.bot else P(8.5,64,.5)
        self.server.set(0,64,0,'water')
        game.water.update(P(.5,64,.5),100,stop_movement=game.stop,vertical=0)
        game.water.horizontal_progress_at=90.
        game.path=(PathStep(P(1.5,64,.5),swimming=True),)
        game.path_index=0
        game.path_created_at=99
        game.path_goal=P(8.5,64,.5)
        game.live_skills.selected['swim']=Mock()  # disabled when no progress
        game.pathfinder.penalize=Mock()
        game.pathfinder.is_airborne=Mock(return_value=False)
        # The test controls the clock without altering real Minecraft state.
        import unittest.mock
        with unittest.mock.patch('quickstart.match.time.monotonic',return_value=100.),redirect_stdout(io.StringIO()) as logs:
            game.step()
        self.assertIn('SWIM RECOVERY',logs.getvalue())
        self.assertGreaterEqual(game.water.stall_events,1)
        self.assertIsNone(game.live_skills.value('swim'))
        game.pathfinder.penalize.assert_called()


if __name__ == '__main__':
    unittest.main()
