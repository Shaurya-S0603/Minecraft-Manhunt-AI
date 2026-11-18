"""v0.7.2: goal/collision-box sampling must never crash bounded A*."""
import io
import time
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock

from quickstart.observations import Position
from quickstart.pathfinding3d import BoundedAStar
from quickstart.terrain import TerrainSensor, TerrainUnavailable
from quickstart.match import ManhuntMatch
from quickstart.tests.test_navigation import FakeScarpet


class SampleWindowBoundaryTests(unittest.TestCase):
    def test_exact_reported_outside_sample_cell_at_positive_x_edge(self):
        world=FakeScarpet()
        for x in range(80,90):
            for z in range(170,173):
                world.set(x,65,z,'grass_block')
        # A narrow supported ledge/unsupported drop at the edge of the
        # sensor window, with the goal collision box crossing into x=89.
        world.set(88,65,171,'air')
        planner=BoundedAStar(TerrainSensor(world,ttl=0))
        start=Position(82.5,66,171.5)
        target=Position(88.82,66,171.5)
        blocks,size=planner._grid((82,66,171))
        self.assertNotIn((89,66,171),blocks)
        self.assertIsNone(planner._passable(blocks,(89,66,171)))
        self.assertEqual(planner._kind(blocks,89,66,171),'unknown')
        # This used to raise KeyError from _snap_to_walkable_cell.
        self.assertEqual(planner._snap_to_walkable_cell(blocks,target),(88,66,171))
        plan=planner.plan(start,target)
        self.assertGreater(plan.expanded,0)
        for step in plan.steps:
            self.assertLessEqual(step.destination.x,88.5)

    def test_negative_x_z_boundary_diagonal_overlap_outside_grid(self):
        world=FakeScarpet()
        # Origin center supported. Target is just inside negative window
        # edge, but the collision box overlaps 3 unsampled neighbour cells.
        world.set(-6,63,-6,'air')
        planner=BoundedAStar(TerrainSensor(world,ttl=0))
        goal=Position(-5.92,64,-5.92)
        blocks,_=planner._grid((0,64,0))
        for neighbor in ((-7,64,-6),(-6,64,-7),(-7,64,-7)):
            self.assertNotIn(neighbor,blocks)
            self.assertIsNone(planner._passable(blocks,neighbor))
        self.assertEqual(planner._snap_to_walkable_cell(blocks,goal),(-6,64,-6))
        self.assertIsNotNone(planner.plan(Position(.5,64,.5),goal))

    def test_out_of_grid_head_and_support_fail_closed(self):
        planner=BoundedAStar(TerrainSensor(FakeScarpet()))
        blocks,_=planner._grid((0,64,0))
        self.assertIsNone(planner._passable(blocks,(0,69,0)))
        self.assertIsNone(planner._passable(blocks,(0,60,0)))
        self.assertIsNone(planner._passable(blocks,(7,64,0)))
        self.assertFalse(planner._unsupported_air(blocks,(7,64,0)))
        self.assertIsNone(planner._edge(blocks,(6,64,0),(7,64,0)))

    def test_goal_at_vertical_and_horizontal_window_edge(self):
        world=FakeScarpet()
        planner=BoundedAStar(TerrainSensor(world))
        start=Position(.5,64,.5)
        # Should replan a safe partial path or decline, never index an
        # unobserved support/head/edge cell.
        for x,z,y in ((6.85,.85,67),(-5.95,-5.96,67),
                      (6.85,6.82,61),(-5.97,.95,61)):
            with self.subTest(x=x,z=z,y=y):
                route=planner.plan(start,Position(x,y,z))
                self.assertIsNotNone(route)

    def test_match_navigation_does_not_close_server_on_missing_goal_sample(self):
        world=FakeScarpet()
        for x in range(80,90):
            world.set(x,65,171,'grass_block')
        world.set(88,65,171,'air')
        game=ManhuntMatch(world,'runner',0,180)
        game.target=Position(88.82,66,171.5)
        game.look_and_move=Mock()  # FakeScarpet is terrain-only, not an entity observer.
        with redirect_stdout(io.StringIO()) as out:
            game.navigate(Position(82.5,66,171.5),game.target,time.monotonic())
        self.assertEqual(game.nav_failures,0)
        self.assertNotIn('3D route sensing unavailable',out.getvalue())

    def test_future_unexpected_astar_keyerror_does_not_kill_match_loop(self):
        world=FakeScarpet()
        game=ManhuntMatch(world,'runner',0,180)
        game.pathfinder.plan=Mock(side_effect=KeyError((88,66,171)))
        game.moving=True
        now=time.monotonic()
        with redirect_stdout(io.StringIO()) as log:
            game.navigate(Position(.5,64,.5),Position(6.5,64,.5),now)
        self.assertEqual(game.nav_failures,1)
        self.assertEqual(game.path,())
        self.assertFalse(game.moving)
        self.assertGreater(game.sensor_retry_at,now)
        self.assertIn('Unobserved A* coordinate',log.getvalue())

    def test_missing_real_sensor_observation_still_raises(self):
        class IncompleteSensor:
            def read(self,coords):
                return {}  # violates the strict TerrainSensor contract
        planner=BoundedAStar(IncompleteSensor())
        # Empty data must be treated as unavailable/unsafe and NOT crash.
        with self.assertRaises(TerrainUnavailable):
            planner.plan(Position(.5,64,.5),Position(2.5,64,.5))

if __name__=='__main__':
    unittest.main()
