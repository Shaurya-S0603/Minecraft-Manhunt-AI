"""v0.7 movement, climbing, underwater routes, sprint-gap and SNBT regression tests."""
import math
import time
import unittest
from unittest.mock import Mock

from quickstart.observations import Observer, Position, parse_position
from quickstart.pathfinding3d import BoundedAStar, PathStep
from quickstart.terrain import TerrainSensor, climbable, terrain_type
from quickstart.underwater import SurfacePlanner
from quickstart.swimming import WaterSurvival
from quickstart.match import ManhuntMatch
from quickstart.block_breaking import BlockBreaker
from quickstart.waypoint_following import reached_waypoint
from quickstart.tests.test_navigation import FakeScarpet


class PositionFormatTests(unittest.TestCase):
    def test_exact_reported_marker_snbt(self):
        result=('Marker has the following entity data: '
                '[6.654859864959756E-4d, 117.02442408821369d, '
                '-12.041634896814966d]')
        x,y,z=parse_position(result)
        self.assertAlmostEqual(x,0.0006654859864959756,places=16)
        self.assertEqual(y,117.02442408821369)
        self.assertEqual(z,-12.041634896814966)

    def test_signed_exponents_decimal_short_forms_and_suffixes(self):
        self.assertEqual(parse_position('Pos: [+1.25e+2D, -.5f, 4E-2d]'),(125.,-.5,.04))
        self.assertEqual(parse_position('Pos: [0, 64, -2]'),(0.,64.,-2.))

    def test_broken_or_non_finite_vectors_rejected(self):
        for value in ('[5E-, 64, 2]','[NaN, 64, 2]','[Infinity, 64, 2]',
                      '[1, 2, 3, 4]','[]'):
            with self.subTest(value=value),self.assertRaises(ValueError):
                parse_position('Marker has '+value)

    def test_observer_uses_direct_response_without_marker_fallback(self):
        rcon=Mock()
        rcon.command.return_value='Alex has the following entity data: [1.2E-3d, 64.0d, -2.0d]'
        result=Observer(rcon).position('Alex')
        self.assertAlmostEqual(result.x,.0012)
        self.assertEqual(len(rcon.command.call_args_list),1)


class VerticalRouteTests(unittest.TestCase):
    def test_vertical_underwater_path_advances(self):
        world=FakeScarpet()
        for y in range(64,68):
            world.set(0,y,0,'water')
        plan=BoundedAStar(TerrainSensor(world)).plan(Position(.5,64,.5),Position(.5,67,.5))
        self.assertTrue(plan.reached_goal)
        self.assertTrue(plan.steps)
        self.assertTrue(all(step.swimming for step in plan.steps))
        self.assertEqual(plan.steps[-1].destination.y,67.)

    def test_climbing_vines_up_unsupported_air_column(self):
        world=FakeScarpet()
        for y in range(64,68):
            world.set(0,y,0,'vine')
            world.set(1,y,0,'oak_log')
        plan=BoundedAStar(TerrainSensor(world)).plan(Position(.5,64,.5),Position(.5,67,.5))
        self.assertTrue(plan.reached_goal)
        self.assertTrue(any(step.climb for step in plan.steps))
        self.assertEqual(plan.steps[-1].destination.y,67.)

    def test_climbing_ladder_recognized_as_non_solid(self):
        self.assertEqual(terrain_type('minecraft:ladder[facing=north]'),'air')
        self.assertTrue(climbable('minecraft:ladder[facing=north]'))

    def test_vertical_free_flight_is_not_an_astar_edge(self):
        world=FakeScarpet()
        planner=BoundedAStar(TerrainSensor(world))
        blocks,_=planner._grid((0,64,0))
        self.assertIsNone(planner._edge(blocks,(0,64,0),(0,65,0)))

    def test_one_block_gap_allows_verified_sprint_jump(self):
        world=FakeScarpet()
        for y in range(59,64):
            world.set(1,y,0,'air')
        # Constrain the path to a corridor so it must cross the gap.
        for x in (-1,0,1,2,3,4):
            for z in (-1,1):
                for y in range(64,67):
                    world.set(x,y,z,'oak_log')
        plan=BoundedAStar(TerrainSensor(world)).plan(Position(.5,64,.5),Position(3.5,64,.5))
        self.assertTrue(plan.steps)
        self.assertTrue(any(step.sprint_jump for step in plan.steps))

    def test_two_block_wall_cannot_be_jumped_normally(self):
        world=FakeScarpet()
        for y in (64,65):
            world.set(1,y,0,'oak_log')
        planner=BoundedAStar(TerrainSensor(world))
        blocks,_=planner._grid((0,64,0))
        self.assertIsNone(planner._edge(blocks,(0,64,0),(1,66,0)))

    def test_jump_requires_vertical_waypoint_arrival(self):
        self.assertFalse(reached_waypoint(Position(.5,64,.5),Position(.5,65,.5)))
        self.assertTrue(reached_waypoint(Position(.5,64.7,.5),Position(.5,65,.5)))


class AirRouteTests(unittest.TestCase):
    def test_finds_air_above_water_column(self):
        world=FakeScarpet()
        for y in (64,65,66):
            world.set(0,y,0,'water')
        target=SurfacePlanner(TerrainSensor(world)).find_air(Position(.5,64,.5))
        self.assertEqual(target,Position(.5,67.,.5))

    def test_air_under_solid_roof_is_not_accepted(self):
        world=FakeScarpet()
        for x in range(-3,4):
            for z in range(-3,4):
                for y in range(64,68):
                    world.set(x,y,z,'water')
                world.set(x,68,z,'stone')
        self.assertIsNone(SurfacePlanner(TerrainSensor(world)).find_air(Position(.5,64,.5)))

    def test_sideways_exit_under_overhang(self):
        world=FakeScarpet()
        for x in range(0,4):
            for y in (64,65):
                world.set(x,y,0,'water')
        for x in (0,1):
            world.set(x,66,0,'stone')
        route=SurfacePlanner(TerrainSensor(world)).find_air(Position(.5,64,.5))
        self.assertIsNotNone(route)
        self.assertGreater(route.x,1.5)

    def test_deep_water_returns_verified_staging_ascent(self):
        world=FakeScarpet()
        for y in range(64,78):
            world.set(0,y,0,'water')
        planner=SurfacePlanner(TerrainSensor(world))
        self.assertIsNone(planner.find_air(Position(.5,64,.5)))
        self.assertEqual(planner.ascend_waypoint(Position(.5,64,.5)),
                         Position(.5,67.,.5))

    def test_staging_ascent_refuses_rock_ceiling(self):
        world=FakeScarpet()
        for y in range(64,67):
            world.set(0,y,0,'water')
        world.set(0,67,0,'stone')
        planner=SurfacePlanner(TerrainSensor(world))
        self.assertIsNone(planner.ascend_waypoint(Position(.5,64,.5)))

    def test_air_sense_never_returns_solid_cell(self):
        world=FakeScarpet()
        world.set(0,64,0,'water')
        world.set(0,65,0,'oak_log')
        world.set(0,66,0,'oak_log')
        target=SurfacePlanner(TerrainSensor(world)).find_air(Position(.5,64,.5))
        self.assertIsNone(target)


class MiningSafetyTests(unittest.TestCase):
    def test_does_not_open_wall_with_lava_behind(self):
        server=FakeScarpet()
        server.set(1,64,0,'dirt')
        server.set(2,64,0,'lava')
        miner=BlockBreaker(server,TerrainSensor(server,ttl=0))
        self.assertFalse(miner.try_start(Position(.5,64,.5),Position(7.5,64,.5),
                                         100.,stop_movement=Mock()))
        self.assertFalse(any('attack continuous' in cmd for cmd in server.calls))

    def test_mining_refuses_falling_gravel_ceiling(self):
        server=FakeScarpet()
        server.set(1,64,0,'dirt')
        server.set(1,65,0,'gravel')
        server.set(1,66,0,'gravel')
        miner=BlockBreaker(server,TerrainSensor(server,ttl=0))
        self.assertFalse(miner.try_start(Position(.5,64,.5),Position(7.5,64,.5),
                                         100.,stop_movement=Mock()))

class MovementControlTests(unittest.TestCase):
    def test_sprint_commands_are_idempotent(self):
        server=FakeScarpet()
        game=ManhuntMatch(server,'hunter',0,30)
        game.set_sprinting(True)
        game.set_sprinting(True)
        game.set_sprinting(False)
        self.assertEqual(server.calls.count('player ManhuntBot sprint'),1)
        self.assertEqual(server.calls.count('player ManhuntBot unsprint'),1)

    def test_climbing_pushes_into_observed_wall(self):
        server=FakeScarpet()
        server.set(1,64,0,'stone')
        game=ManhuntMatch(server,'hunter',0,30)
        game.climb_move(Position(.5,64,.5),Position(.5,65,.5))
        self.assertIn('player ManhuntBot jump continuous',server.calls)
        self.assertIn('player ManhuntBot move forward',server.calls)
        self.assertTrue(game.climbing)

    def test_sprint_jump_step_sends_one_jump_not_repeat(self):
        server=FakeScarpet()
        server.set(1,63,0,'air')  # Real observed gap, not a solid-ground shortcut.
        game=ManhuntMatch(server,'hunter',0,30)
        game.look_and_move=Mock()
        game.path=(PathStep(Position(2.5,64,.5),sprint_jump=True),)
        game.path_start=Position(.5,64,.5)
        game.path_goal=Position(2.5,64,.5)
        now=time.monotonic()
        game.path_created_at=now
        game.motion.observe(Position(.5,64,.5),now)
        game.navigate(Position(.5,64,.5),game.path_goal,now)
        self.assertEqual(server.calls.count('player ManhuntBot jump once'),0)
        # Physics-aware execution waits for REAL observed forward speed.
        game.motion.observe(Position(.9,64,.5),now+.2)
        game.navigate(Position(.9,64,.5),game.path_goal,now+.2)
        game.navigate(Position(.9,64,.5),game.path_goal,now+.3)
        self.assertEqual(server.calls.count('player ManhuntBot jump once'),1)
        self.assertEqual(server.calls.count('player ManhuntBot sprint'),1)

    def test_low_air_forces_ascent_instead_of_dive(self):
        from quickstart.tests.test_v06 import SwimmingRcon
        server=SwimmingRcon()
        server.air=100
        server.set(0,64,0,'water')
        swimming=WaterSurvival(server,TerrainSensor(server,ttl=0))
        swimming.update(Position(.5,64,.5),100.,stop_movement=Mock(),vertical=-1)
        self.assertIn('player ManhuntBot jump continuous',server.calls)
        self.assertNotIn('player ManhuntBot sneak',server.calls)

if __name__=='__main__':
    unittest.main()
