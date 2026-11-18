"""v0.5.2: real leaves are solid; controller must not skip safe path corners."""
import io
import time
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock

from quickstart.match import ManhuntMatch
from quickstart.observations import Position
from quickstart.pathfinding3d import BoundedAStar, PathStep
from quickstart.terrain import TerrainSensor, terrain_type
from quickstart.waypoint_following import reached_waypoint
from quickstart.tests.test_navigation import FakeScarpet


class RealLeavesTests(unittest.TestCase):
    def test_leaf_litter_is_passable_but_real_leaves_are_solid(self):
        self.assertEqual(terrain_type('minecraft:leaf_litter[segment_amount=4]'), 'air')
        for material in ('oak_leaves','birch_leaves','cherry_leaves',
                         'pale_oak_leaves','azalea_leaves','mangrove_leaves'):
            with self.subTest(material=material):
                self.assertEqual(terrain_type(material), 'solid')

    def test_full_height_leaf_wall_gets_detour(self):
        world = FakeScarpet()
        for z in (-1,0,1):
            for y in (64,65,66,67):
                world.set(2,y,z,'oak_leaves')
        route = BoundedAStar(TerrainSensor(world)).plan(
            Position(.5,64,.5), Position(5.5,64,.5))
        self.assertTrue(route.reached_goal)
        self.assertTrue(any(abs(step.destination.z) > 1.5 for step in route.steps))
        for step in route.steps:
            self.assertFalse(step.destination.x == 2.5 and abs(step.destination.z) <= 1.5)

    def test_prefers_walking_around_short_leaf_block_over_hopping_on_it(self):
        world = FakeScarpet()
        world.set(2,64,0,'oak_leaves')
        route = BoundedAStar(TerrainSensor(world)).plan(
            Position(.5,64,.5), Position(4.5,64,.5))
        self.assertTrue(route.reached_goal)
        self.assertFalse(any(step.destination == Position(2.5,65,.5)
                             for step in route.steps))

    def test_leaf_litter_underfoot_doesnt_create_collision(self):
        world = FakeScarpet()
        for x in range(1,5):
            world.set(x,64,0,'leaf_litter')
        route=BoundedAStar(TerrainSensor(world)).plan(
            Position(.5,64,.5),Position(5.5,64,.5))
        self.assertTrue(route.reached_goal)
        self.assertTrue(route.steps)


class WaypointTests(unittest.TestCase):
    def test_one_block_distance_must_not_count_as_arrived(self):
        self.assertFalse(reached_waypoint(Position(.5,64,.5), Position(1.5,64,.5),
                                          Position(.5,64,.5)))

    def test_center_arrival_and_narrow_overshoot(self):
        self.assertTrue(reached_waypoint(Position(1.41,64,.62),Position(1.5,64,.5)))
        self.assertTrue(reached_waypoint(Position(1.92,64,.5), Position(1.5,64,.5),
                                         Position(.5,64,.5)))
        self.assertFalse(reached_waypoint(Position(1.92,64,1.2), Position(1.5,64,.5),
                                          Position(.5,64,.5)))

    def test_cannot_skip_corner_due_to_diagonal_proximity(self):
        game=ManhuntMatch(FakeScarpet(),'runner',0,60)
        game.player='Alex'
        now=time.monotonic()
        game.path=(PathStep(Position(1.5,64,.5)),PathStep(Position(1.5,64,1.5)))
        game.path_start=Position(.5,64,.5)
        game.path_goal=Position(1.5,64,1.5)
        game.path_created_at=now
        game.look_and_move=Mock()
        game.navigate(Position(.5,64,.5),Position(1.5,64,1.5),now)
        self.assertEqual(game.path_index,0)
        self.assertEqual(game.look_and_move.call_args.args[0],Position(1.5,64,.5))
        game.navigate(Position(1.47,64,.52),Position(1.5,64,1.5),now+.2)
        self.assertEqual(game.path_index,1)
        self.assertEqual(game.look_and_move.call_args.args[0],Position(1.5,64,1.5))

    def test_no_route_is_rate_limited_instead_of_scanning_every_tick(self):
        world=FakeScarpet()
        for x in range(-1,2):
            for z in range(-1,2):
                if x or z:
                    for y in (64,65,66):
                        world.set(x,y,z,'oak_leaves')
        game=ManhuntMatch(world,'runner',0,60)
        game.look_and_move=Mock()
        now=time.monotonic()
        game.navigate(Position(.5,64,.5),Position(10.5,64,.5),now)
        first_attempts=game.path_attempts
        first_calls=len(world.calls)
        game.navigate(Position(.5,64,.5),Position(10.5,64,.5),now+.16)
        self.assertEqual(game.path_attempts,first_attempts)
        self.assertEqual(len(world.calls),first_calls)
        game.navigate(Position(.5,64,.5),Position(10.5,64,.5),now+3)
        self.assertGreater(game.path_attempts,first_attempts)

    def test_stuck_report_identifies_leaf_blocks_without_particles(self):
        world=FakeScarpet()
        world.set(1,64,0,'oak_leaves')
        game=ManhuntMatch(world,'runner',0,60)
        game.path=(PathStep(Position(1.5,64,.5)),)
        game.path_index=0
        stream=io.StringIO()
        with redirect_stdout(stream):
            game.report_stuck_obstacles(Position(.5,64,.5))
        self.assertIn('oak_leaves',stream.getvalue())
        self.assertIn('[NAV BLOCK]',stream.getvalue())

    def test_when_astar_cannot_route_never_uses_old_local_fallback(self):
        world=FakeScarpet()
        for x in range(-1,2):
            for z in range(-1,2):
                if x != 0 or z != 0:
                    for y in (64,65,66):
                        world.set(x,y,z,'oak_leaves')
        game=ManhuntMatch(world,'runner',0,60)
        game.look_and_move=Mock()
        game.navigator.choose=Mock(side_effect=AssertionError('Unsafe fallback called'))
        game.navigate(Position(.5,64,.5),Position(10.5,64,.5),time.monotonic())
        game.look_and_move.assert_not_called()
        game.navigator.choose.assert_not_called()


if __name__=='__main__':
    unittest.main()
