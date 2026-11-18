"""v0.5 tests: 3D A*, spawn clearance, recovery and actual game integration."""
from __future__ import annotations
import math
import unittest
from unittest.mock import Mock
from quickstart.terrain import TerrainSensor, TerrainUnavailable
from quickstart.pathfinding3d import BoundedAStar
from quickstart.safe_spawn import SafeSpawnFinder
from quickstart.observations import Position
from quickstart.match import ManhuntMatch
from quickstart.tests.test_navigation import FakeScarpet


def routeworld(radius=6):
    server=FakeScarpet()
    sensor=TerrainSensor(server,ttl=4,max_batch=24)
    return server,sensor,BoundedAStar(sensor,radius=radius)


class PathfindingTests(unittest.TestCase):
    def test_flat_path_advances_toward_far_target(self):
        _,_,planner=routeworld()
        plan=planner.plan(Position(0.5,64,0.5),Position(45,64,0))
        self.assertFalse(plan.reached_goal)
        self.assertGreaterEqual(len(plan.steps),4)
        self.assertLessEqual(max(abs(s.destination.x) for s in plan.steps),6.5)
        self.assertGreater(plan.steps[-1].destination.x,3)

    def test_navigates_around_three_block_wall(self):
        server,_,planner=routeworld()
        for z in (-1,0,1):
            for y in (64,65,66):
                server.set(2,y,z,'oak_log')
        plan=planner.plan(Position(0.5,64,0.5),Position(5.5,64,0.5))
        self.assertTrue(plan.reached_goal)
        self.assertTrue(any(abs(s.destination.z) > 1.5 for s in plan.steps))
        self.assertTrue(all(not(2 <= s.destination.x < 3 and abs(s.destination.z)<2) for s in plan.steps))

    def test_one_block_hill_marks_jump(self):
        server,_,planner=routeworld()
        for x in (1,2,3):
            for z in range(-6,7):
                server.set(x,64,z,'stone')
        plan=planner.plan(Position(0.5,64,0.5),Position(3.5,65,0.5))
        self.assertTrue(plan.reached_goal)
        self.assertTrue(any(s.jump for s in plan.steps))
        self.assertEqual(plan.steps[-1].destination.y,65)

    def test_avoids_lava_and_void(self):
        server,_,planner=routeworld()
        server.set(1,64,0,'lava')
        for z in (-1,0,1):
            server.set(2,63,z,'air')
            server.set(2,62,z,'air')
            server.set(2,61,z,'air')
        plan=planner.plan(Position(.5,64,.5),Position(5.5,64,.5))
        for step in plan.steps:
            x,z=math.floor(step.destination.x),math.floor(step.destination.z)
            self.assertNotEqual((x,z),(1,0))
            self.assertFalse(x==2 and abs(z)<=1)

    def test_water_can_be_used_if_needed(self):
        server,_,planner=routeworld()
        for z in range(-6,7):
            server.set(1,64,z,'water')
        plan=planner.plan(Position(.5,64,.5),Position(4.5,64,.5))
        self.assertTrue(plan.reached_goal)
        self.assertTrue(any(s.swimming for s in plan.steps))

    def test_prevents_corner_cutting(self):
        server,_,planner=routeworld()
        for x,z in ((1,0),(0,1)):
            for y in (64,65,66):
                server.set(x,y,z,'obsidian')
        plan=planner.plan(Position(.5,64,.5),Position(3.5,64,3.5))
        self.assertFalse(plan.steps and plan.steps[0].destination == Position(1.5,64,1.5))

    def test_blocked_until_replan_avoids_previous_cell(self):
        _,_,planner=routeworld()
        p=Position(.5,64,.5)
        goal=Position(10,64,0)
        plan=planner.plan(p,goal)
        bad=plan.steps[0].destination
        planner.penalize(bad)
        revised=planner.plan(p,goal)
        self.assertNotEqual(revised.steps[0].destination,bad)

    def test_fails_closed_when_terrain_is_unknown(self):
        bad=Mock()
        bad.command.return_value='Unknown command'
        with self.assertRaises(TerrainUnavailable):
            BoundedAStar(TerrainSensor(bad)).plan(Position(0,64,0),Position(5,64,0))

    def test_scan_budget_is_bounded(self):
        remote,_,planner=routeworld()
        plan=planner.plan(Position(0,64,0),Position(100,64,0))
        self.assertLessEqual(plan.observed_blocks,2000)
        self.assertLessEqual(plan.expanded,350)
        self.assertTrue(all(len(cmd)<1300 for cmd in remote.calls))


class SpawnSafetyTests(unittest.TestCase):
    def test_finds_open_ground_and_three_clear_levels(self):
        remote=FakeScarpet()
        spot=SafeSpawnFinder(TerrainSensor(remote)).find(Position(.5,64,.5))
        self.assertGreaterEqual(spot.distance,4)
        self.assertEqual(spot.position.y,64)
        self.assertTrue(SafeSpawnFinder(TerrainSensor(remote)).verify(spot.position))

    def test_refuses_entirely_blocked_spawn_area(self):
        remote=FakeScarpet()
        # A low roof blocks air at all candidate elevations.
        for x in range(-17,18):
            for z in range(-17,18):
                for y in range(64,71):
                    remote.set(x,y,z,'stone')
        with self.assertRaisesRegex(TerrainUnavailable, 'No verified open'):
            SafeSpawnFinder(TerrainSensor(remote)).find(Position(0,64,0))

    def test_rejects_tree_and_leaves_at_head_height(self):
        remote=FakeScarpet()
        for y in (64,65,66):
            remote.set(5,y,5,'oak_leaves')
        sensor=TerrainSensor(remote)
        spawn=SafeSpawnFinder(sensor).find(Position(.5,64,.5))
        self.assertNotEqual((math.floor(spawn.position.x),math.floor(spawn.position.z)),(5,5))
        self.assertTrue(SafeSpawnFinder(sensor).verify(spawn.position))

    def test_rejects_lava_and_water_as_spawn_support(self):
        remote=FakeScarpet()
        for x,z in ((5,5),(4,5),(5,4)):
            remote.set(x,63,z,'lava' if x==5 else 'water')
        spawn=SafeSpawnFinder(TerrainSensor(remote)).find(Position(.5,64,.5))
        self.assertNotIn((math.floor(spawn.position.x),math.floor(spawn.position.z)),[(5,5),(4,5),(5,4)])

    def test_detects_post_spawn_suffocation(self):
        remote=FakeScarpet()
        remote.set(7,65,7,'oak_log')
        self.assertFalse(SafeSpawnFinder(TerrainSensor(remote)).verify(Position(7.5,64,7.5)))

    def test_dimension_context_uses_actual_player(self):
        remote=FakeScarpet()
        sensor=TerrainSensor(remote,at_entity='Alex')
        sensor.read([(0,64,0)])
        self.assertTrue(remote.calls[-1].startswith('execute at Alex run script run'))


class GameIntegrationTests(unittest.TestCase):
    def test_hunter_routes_physically_without_tp(self):
        remote=FakeScarpet()
        game=ManhuntMatch(remote,'runner',0,60)
        game.player='Alex'
        game.observer.position=lambda name: Position(0.5,64,0.5) if name=='gamehuman' else Position(10.5,64,0.5)
        # Set bot position (10.5) and human (25.5) independently.
        game.observer.position=lambda name: Position(10.5,64,.5) if name==game.bot else Position(25.5,64,.5)
        game.look_and_move=Mock()
        game.step()
        self.assertTrue(game.look_and_move.called)
        self.assertGreater(game.path_replans,0)
        self.assertFalse(any('run tp ' in s for s in remote.calls))

    def test_no_blind_drive_when_sensor_fails(self):
        remote=Mock()
        remote.command.return_value='Unknown command'
        game=ManhuntMatch(remote,'runner',0,60)
        game.player='Alex'
        game.observer.position=lambda name: Position(10,64,0) if name==game.bot else Position(25,64,0)
        game.look_and_move=Mock()
        game.step()
        game.look_and_move.assert_not_called()
        self.assertGreater(game.nav_failures,0)

    def test_existing_bot_reposition_uses_verified_safe_spot(self):
        remote=FakeScarpet()
        game=ManhuntMatch(remote,'runner',0,60)
        game.player='Alex'
        game.players=lambda:['Alex',game.bot]
        game.observer.position=lambda name: Position(.5,64,.5) if name=='Alex' else Position(5.5,64,5.5)
        game.setup_bot()
        self.assertTrue(any('run tp ManhuntBot ' in c for c in remote.calls))
        self.assertTrue(any('execute at Alex run script run ' in c for c in remote.calls))


if __name__=='__main__':
    unittest.main()
