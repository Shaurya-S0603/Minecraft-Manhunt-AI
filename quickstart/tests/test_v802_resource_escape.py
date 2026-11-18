"""v8.0.2 resource ownership and threat-aware escape regressions.
These fixtures exercise the control flow; they do not simulate Minecraft physics.
"""
import unittest
from unittest.mock import Mock, patch
from quickstart.block_breaking import BlockBreaker
from quickstart.match import ManhuntMatch
from quickstart.observations import Position
from quickstart.pathfinding3d import BoundedAStar
from quickstart.terrain import TerrainSensor
from quickstart.v8_config import load_config
from quickstart.v8_resources import ResourceCollector
from quickstart.tests.test_navigation import FakeScarpet
from quickstart.tests.test_v0713_detour import walled_world

class Inventory:
    available=True
    def __init__(self):
        self.slots={}
        self.logs=0
    def count_suffix(self, suffix): return self.logs
    def snapshot(self, force=False): return []

class GatheringTests(unittest.TestCase):
    def setUp(self):
        self.server=FakeScarpet()
        self.server.set(3,64,0,'oak_log')
        self.server.set(3,65,0,'oak_log')
        self.inv=Inventory()
        self.sensor=TerrainSensor(self.server,ttl=0)
        self.miner=BlockBreaker(self.server,self.sensor)
        self.rules=load_config()['resources']
        self.c=ResourceCollector(self.inv,self.miner,self.sensor,self.rules)
        self.h=Position(-40,64,.5)
        self.start=Position(.5,64,.5)
        self.stop=Mock();self.nav=Mock()

    def test_approach_then_mine_then_native_pickup_confirmation(self):
        self.assertTrue(self.c.try_gather(self.start,self.h,'runner',100,self.stop,navigate=self.nav))
        g=self.c.goal
        self.nav.assert_called_with(self.start,g.stand,100)
        self.assertIsNone(self.miner.operation)
        self.assertTrue(self.c.try_gather(g.stand,self.h,'runner',101,self.stop,navigate=self.nav))
        self.assertEqual(g.phase,'harvest')
        self.assertIsNotNone(self.miner.operation)
        self.assertIn('player ManhuntBot attack continuous',self.server.calls)
        self.assertTrue(self.c.try_gather(g.stand,self.h,'runner',102,self.stop,navigate=self.nav))
        self.server.set(*g.block,'air')
        self.assertTrue(self.c.try_gather(g.stand,self.h,'runner',103,self.stop,navigate=self.nav))
        self.assertEqual(g.phase,'pickup')
        self.assertEqual(self.c.confirmed,0)
        self.inv.logs=1
        self.assertFalse(self.c.try_gather(g.stand,self.h,'runner',104,self.stop,navigate=self.nav))
        self.assertEqual(self.c.confirmed,1)
        self.assertIsNone(self.c.goal)
        self.assertFalse(any(' give ' in c or c.startswith(('give ','setblock ','item replace ')) for c in self.server.calls))

    def test_hunter_approach_interrupts_held_mining(self):
        self.c.try_gather(self.start,self.h,'runner',100,self.stop,navigate=self.nav)
        stand=self.c.goal.stand
        self.c.try_gather(stand,self.h,'runner',101,self.stop,navigate=self.nav)
        self.assertIsNotNone(self.miner.operation)
        self.assertFalse(self.c.try_gather(stand,stand,'runner',102,self.stop,navigate=self.nav))
        self.assertIsNone(self.miner.operation)
        self.assertIsNone(self.c.goal)
        self.assertEqual(self.c.aborted,1)
        self.assertEqual(self.c.confirmed,0)

    def test_stalled_resource_approach_releases_objective(self):
        self.c.try_gather(self.start,self.h,'runner',100,self.stop,navigate=self.nav)
        self.assertFalse(self.c.try_gather(self.start,self.h,'runner',104.1,self.stop,navigate=self.nav))
        self.assertIsNone(self.c.goal)
        self.assertEqual(self.c.failed,1)
        self.stop.assert_called()

    def test_nearby_tree_at_different_elevation(self):
        self.server.set(3,64,0,'air');self.server.set(3,65,0,'air')
        self.server.set(3,64,1,'dirt');self.server.set(3,65,1,'birch_log')
        goal=self.c.find(self.start,self.h,100)
        self.assertEqual(goal.block,(3,65,1))

    def test_no_pickup_is_not_success(self):
        self.c.try_gather(self.start,self.h,'runner',100,self.stop,navigate=self.nav)
        g=self.c.goal
        self.c.try_gather(g.stand,self.h,'runner',101,self.stop,navigate=self.nav)
        self.server.set(*g.block,'air')
        self.c.try_gather(g.stand,self.h,'runner',102,self.stop,navigate=self.nav)
        self.assertFalse(self.c.try_gather(g.stand,self.h,'runner',107,self.stop,navigate=self.nav))
        self.assertEqual(self.c.failed,1)
        self.assertEqual(self.c.confirmed,0)

    def test_match_step_keeps_collection_ownership_while_miner_busy(self):
        game=ManhuntMatch(self.server,'hunter',0,180)
        game.player='Alex'
        game.inventory=self.inv;game.collector=self.c;game.miner=self.miner
        game.navigate=Mock()
        bot=[self.start]
        game.observer.position=lambda who: bot[0] if who==game.bot else self.h
        with patch('quickstart.match.time.monotonic',return_value=100): game.step()
        g=self.c.goal; self.assertIsNotNone(g)
        bot[0]=g.stand
        with patch('quickstart.match.time.monotonic',return_value=101): game.step()
        self.assertIsNotNone(self.miner.operation)
        self.server.set(*g.block,'air')
        with patch('quickstart.match.time.monotonic',return_value=103): game.step()
        self.assertEqual(g.phase,'pickup')
        self.inv.logs=1
        with patch('quickstart.match.time.monotonic',return_value=104): game.step()
        self.assertEqual(self.c.confirmed,1)
        self.assertIsNone(self.c.goal)
        self.assertEqual(game.navigate.call_args.kwargs['escape_from'],self.h)

    def test_spectator_camera_does_not_chase_away_gatherer(self):
        game=ManhuntMatch(self.server,'hunter',20,180)
        game.player='Alex';game.collector=self.c;game.miner=self.miner
        game.inventory=self.inv;game.navigate=Mock()
        game.headstart_origin=self.h
        game.observer.position=lambda who: self.start # camera directly over bot
        with patch('quickstart.match.time.monotonic',return_value=100): game.step()
        self.assertIsNotNone(self.c.goal)

class EscapeTests(unittest.TestCase):
    def test_runner_blocked_escape_recovers_away_from_actual_threat(self):
        planner=BoundedAStar(TerrainSensor(walled_world(),ttl=0))
        bot=Position(.5,64,.5);blocked=Position(20.5,64,.5);threat=Position(.5,64,4.5)
        route=planner.plan(bot,blocked,allow_detour=True,escape_from=threat,avoid_water=True)
        self.assertTrue(route.detour)
        self.assertGreater(route.steps[-1].destination.distance(threat),bot.distance(threat)+2)
        self.assertTrue(all(p.destination.x<1 for p in route.steps))

    def test_stale_goal_replaced_when_hunter_gets_ahead(self):
        game=ManhuntMatch(FakeScarpet(),'hunter',0,180)
        game.player='Alex';game.navigate=Mock()
        bot=Position(.5,64,.5);hunter=Position(12.5,64,.5)
        game.target=Position(16.5,64,.5)
        game.escape_last_choice=90
        game.observer.position=lambda who: bot if who==game.bot else hunter
        with patch('quickstart.match.time.monotonic',return_value=100): game.step()
        self.assertLess(game.target.x,bot.x)
        self.assertEqual(game.navigate.call_args.kwargs['escape_from'],hunter)
        self.assertEqual(game.escape_replans,1)

if __name__=='__main__': unittest.main()
