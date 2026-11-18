"""v0.7.13 regression: don't freeze behind obstacles or learn from no-op tactics."""
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from quickstart.match import ManhuntMatch
from quickstart.observations import Position
from quickstart.pathfinding3d import BoundedAStar
from quickstart.strategy import StrategyAdvisor
from quickstart.terrain import TerrainSensor
from quickstart.tests.test_navigation import FakeScarpet


def walled_world():
    server = FakeScarpet()
    # Tall 13-block-wide wall, just in front of the hunter. Within the
    # 6-block observed radius, ALL reachable cells fail to approach the goal.
    for z in range(-6, 7):
        for y in (64,65,66):
            server.set(1,y,z,'obsidian')
    return server


class VerifiedDetourTests(unittest.TestCase):
    def test_wall_failure_gets_verified_sideways_route(self):
        server=walled_world()
        planner=BoundedAStar(TerrainSensor(server,ttl=0))
        bot=Position(.5,64,.5); goal=Position(20.5,64,.5)
        ordinary=planner.plan(bot,goal)
        self.assertEqual(ordinary.steps,())
        self.assertFalse(ordinary.reached_goal)
        recovered=planner.plan(bot,goal,allow_detour=True)
        self.assertTrue(recovered.detour)
        self.assertTrue(recovered.steps)
        self.assertFalse(recovered.reached_goal)
        self.assertGreaterEqual(abs(recovered.steps[-1].destination.z-bot.z),2.)
        # No unknown/solid cells crossed: every move exists in A* predecessor graph.
        for step in recovered.steps:
            self.assertLess(step.destination.x,1.)

    def test_exclusion_selects_distinct_lateral_alternative(self):
        server=walled_world()
        planner=BoundedAStar(TerrainSensor(server))
        bot=Position(.5,64,.5); goal=Position(20.5,64,.5)
        first=planner.plan(bot,goal,allow_detour=True)
        endpoint=first.steps[-1].destination
        excluded=frozenset({(int(endpoint.x),int(endpoint.y),int(endpoint.z))})
        second=planner.plan(bot,goal,allow_detour=True,detour_exclude=excluded)
        self.assertTrue(second.detour)
        self.assertGreaterEqual(second.steps[-1].destination.distance(endpoint),2.)

    def test_fully_enclosed_bot_remains_stopped(self):
        server=FakeScarpet()
        for x,z in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)):
            for y in (64,65,66):
                server.set(x,y,z,'obsidian')
        planner=BoundedAStar(TerrainSensor(server))
        route=planner.plan(Position(.5,64,.5),Position(20.5,64,.5),allow_detour=True)
        self.assertEqual(route.steps,())
        self.assertFalse(route.detour)

    def test_match_recovers_from_empty_route_without_safety_bypass(self):
        server=walled_world()
        game=ManhuntMatch(server,'runner',0,180)
        game.look_and_move=lambda pos: setattr(game,'last_controlled_target',pos)
        bot=Position(.5,64,.5); goal=Position(20.5,64,.5)
        with redirect_stdout(io.StringIO()):
            game.navigate(bot,goal,100.0)
        self.assertEqual(game.empty_route_scans,1)
        self.assertFalse(game.detour_active)
        with redirect_stdout(io.StringIO()):
            game.navigate(bot,goal,103.0)
        self.assertEqual(game.detour_routes,1)
        self.assertTrue(game.detour_active)
        self.assertLess(game.last_controlled_target.x,1)
        self.assertFalse(game.nav_failures)
        self.assertEqual(game.detour_budget_used,1)

    def test_detour_budget_ends_exploration(self):
        server=walled_world()
        game=ManhuntMatch(server,'runner',0,180)
        game.look_and_move=lambda pos: None
        game.failed_routes=3
        game.detour_budget_start=100.0
        game.detour_budget_goal=Position(20.5,64,.5)
        game.detour_budget_used=4
        with redirect_stdout(io.StringIO()) as log:
            game.navigate(Position(.5,64,.5),Position(20.5,64,.5),105.0)
        self.assertFalse(game.detour_active)
        self.assertEqual(game.detour_budget_used,4)
        self.assertEqual(game.detour_routes,0)
        self.assertIn('detour budget exhausted',log.getvalue())


class TacticalLearningTests(unittest.TestCase):
    def test_still_bot_no_false_positive_when_human_approaches(self):
        with tempfile.TemporaryDirectory() as d:
            s=StrategyAdvisor('hunter',Path(d))
            b=Position(0,64,0)
            s.hunt(b,Position(10,64,0),1)
            s.observe(b,Position(7,64,0),3.6)
            self.assertEqual(s.trials,0)
            self.assertEqual(s.skipped_stationary,1)
            self.assertFalse((Path(d)/'tactical_policy_hunter_v2.json').exists())

    def test_no_route_discards_pending_tactical_choice(self):
        with tempfile.TemporaryDirectory() as d:
            s=StrategyAdvisor('hunter',Path(d))
            b=Position(0,64,0); h=Position(10,64,0)
            s.hunt(b,h,1)
            s.suspend_unroutable()
            s.observe(b,Position(5,64,0),4)
            self.assertEqual(s.trials,0)
            self.assertEqual(s.skipped_unroutable,1)
            self.assertIsNone(s.current)

    def test_observed_physical_progress_still_learns(self):
        with tempfile.TemporaryDirectory() as d:
            s=StrategyAdvisor('hunter',Path(d))
            h=Position(10,64,0)
            s.hunt(Position(0,64,0),h,1)
            s.observe(Position(2,64,0),h,4)
            self.assertEqual(s.trials,1)
            self.assertEqual(s.counters['direct_pursuit']['success'],2)


class PolicyMigrationAndRuntimeTests(unittest.TestCase):
    def test_bad_legacy_feedback_never_seeds_clean_v2(self):
        import json
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            old=root/'tactical_policy_hunter.json'
            old.write_text(json.dumps({
                'schema':1,'role':'hunter','trials':400,
                'actions':{'direct_pursuit':{'success':1,'failure':399},
                           'short_intercept':{'success':1,'failure':1}},
            }),encoding='utf8')
            s=StrategyAdvisor('hunter',root)
            self.assertEqual(s.trials,0)
            self.assertEqual(s.counters['direct_pursuit'],{'success':1,'failure':1})
            s.hunt(Position(0,64,0),Position(10,64,0),1)
            s.observe(Position(2,64,0),Position(10,64,0),4)
            self.assertTrue((root/'tactical_policy_hunter_v2.json').is_file())
            self.assertEqual(json.loads(old.read_text())['trials'],400)

    def test_route_refusal_cancels_tactical_reward(self):
        server=walled_world()
        game=ManhuntMatch(server,'runner',0,180)
        bot=Position(.5,64,.5); human=Position(20.5,64,.5)
        with tempfile.TemporaryDirectory() as d:
            game.strategy=StrategyAdvisor('hunter',Path(d))
            game.strategy.hunt(bot,human,100)
            self.assertIsNotNone(game.strategy.current)
            with redirect_stdout(io.StringIO()):
                game.navigate(bot,human,100)
            self.assertIsNone(game.strategy.current)
            self.assertEqual(game.strategy.skipped_unroutable,1)
            self.assertEqual(game.strategy.trials,0)


if __name__ == '__main__':
    unittest.main()
