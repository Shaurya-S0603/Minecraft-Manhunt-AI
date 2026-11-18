"""v0.7.1: jumping off tree canopy and falling into water are not sensor errors."""
import io
import time
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock

from quickstart.match import ManhuntMatch
from quickstart.observations import Position
from quickstart.pathfinding3d import BoundedAStar, AirborneTransition
from quickstart.terrain import TerrainSensor, TerrainUnavailable
from quickstart.tests.test_navigation import FakeScarpet


class FallingTransitionTests(unittest.TestCase):
    def setUp(self):
        self.world = FakeScarpet()
        self.world.set(0,69,0,'oak_leaves')  # supported treetop at y70
        for y in range(64,68):
            self.world.set(1,y,0,'water')    # river beneath adjacent air column

    def test_tree_is_supported_but_air_above_water_is_transition(self):
        planner=BoundedAStar(TerrainSensor(self.world,ttl=0))
        self.assertFalse(planner.is_airborne(Position(.5,70,.5)))
        self.assertTrue(planner.is_airborne(Position(1.5,70,.5)))
        self.assertFalse(planner.is_airborne(Position(1.5,67,.5)))

    def test_near_edge_of_leaf_is_still_supported_by_hitbox(self):
        planner=BoundedAStar(TerrainSensor(self.world,ttl=0))
        # Centre is in x=1 (air below), but 0.6-wide hitbox crosses the
        # boundary and still rests on the leaf in x=0.
        supported=Position(1.12,70,.5)
        self.assertFalse(planner.is_airborne(supported))
        blocks,_=planner._grid((1,70,0))
        self.assertEqual(planner._snap_to_walkable_cell(blocks,supported),(0,70,0))
        # Centre farther from the edge no longer overlaps the leaves.
        self.assertTrue(planner.is_airborne(Position(1.42,70,.5)))

    def test_planner_distinguishes_fall_from_unreadable_or_solid(self):
        planner=BoundedAStar(TerrainSensor(self.world,ttl=0))
        with self.assertRaises(AirborneTransition):
            planner.plan(Position(1.5,70,.5),Position(3.5,64,.5))
        # A colliding block is not classified as a harmless falling state.
        self.world.set(3,70,0,'oak_log')
        self.assertFalse(planner.is_airborne(Position(3.5,70,.5)))
        with self.assertRaises(TerrainUnavailable) as caught:
            planner.plan(Position(3.5,70,.5),Position(5.5,70,.5))
        self.assertNotIsInstance(caught.exception,AirborneTransition)

    def test_temporarily_falling_no_cooldown_and_water_replans(self):
        game=ManhuntMatch(self.world,'runner',0,60)
        now=time.monotonic()
        game.moving=True
        game.last_progress=now-10
        with redirect_stdout(io.StringIO()) as stream:
            game.navigate(Position(1.5,70,.5),Position(5.5,67,.5),now)
        self.assertTrue(game.airborne)
        self.assertIn('[NAV AIR]',stream.getvalue())
        self.assertNotIn('3D route sensing unavailable',stream.getvalue())
        self.assertFalse(game.moving)
        self.assertEqual(game.path_attempts,0)
        self.assertEqual(game.sensor_retry_at,0.0)
        self.assertEqual(game.recovery_attempts,0)
        with redirect_stdout(io.StringIO()) as landing:
            game.navigate(Position(1.5,67,.5),Position(5.5,67,.5),now+.3)
        self.assertFalse(game.airborne)
        self.assertIn('Landing or water entry',landing.getvalue())
        self.assertEqual(game.path_attempts,1)
        self.assertEqual(game.sensor_retry_at,0.0)
        self.assertEqual(game.recovery_attempts,0)

    def test_full_step_tree_fall_then_water_enters_swim_without_nav_warning(self):
        from quickstart.tests.test_v06 import SwimmingRcon
        server=SwimmingRcon()
        server.set(0,69,0,'oak_leaves')
        for y in range(64,68):
            server.set(1,y,0,'water')
        game=ManhuntMatch(server,'runner',0,60)
        game.player='Alex'
        game.hit_detector=Mock()
        game.hit_detector.hunter_hit.return_value=False
        position=[Position(1.5,70,.5)]
        game.observer.position=lambda who: (position[0] if who==game.bot
                                            else Position(8.5,64,.5))
        with redirect_stdout(io.StringIO()) as out:
            self.assertIsNone(game.step())
            self.assertTrue(game.airborne)
            self.assertFalse(game.warned_sensor)
            position[0]=Position(1.5,67,.5)
            self.assertIsNone(game.step())
        self.assertFalse(game.airborne)
        self.assertTrue(game.water.swimming)
        self.assertIn('Landing or water entry',out.getvalue())
        self.assertNotIn('3D route sensing unavailable',out.getvalue())

    def test_grace_for_deliberate_jump_before_halting_long_fall(self):
        game=ManhuntMatch(self.world,'runner',0,60)
        now=time.monotonic()
        game.moving=True
        game.last_jump_command_at=now-0.2
        game.path=(Mock(destination=Position(2.5,70,.5)),)
        game.navigate(Position(1.5,70,.5),Position(5.5,70,.5),now)
        self.assertTrue(game.moving)
        self.assertTrue(game.airborne)
        self.assertTrue(game.path)
        game.navigate(Position(1.5,69,.5),Position(5.5,70,.5),now+1.2)
        self.assertFalse(game.moving)
        self.assertFalse(game.path)

    def test_unavailable_sensor_is_still_fail_closed(self):
        game=ManhuntMatch(self.world,'runner',0,60)
        game.pathfinder.is_airborne=Mock(side_effect=TerrainUnavailable('sensor offline'))
        game.moving=True
        with redirect_stdout(io.StringIO()) as log:
            game.navigate(Position(1.5,70,.5),Position(5.5,70,.5),time.monotonic())
        self.assertIn('Airborne sensing failed',log.getvalue())
        self.assertFalse(game.moving)


if __name__=='__main__':
    unittest.main()
