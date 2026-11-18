"""Offline v0.4 navigation tests with synthetic Minecraft block observations."""
import math
import re
import unittest
from unittest.mock import Mock

from quickstart.terrain import (
    TerrainSensor, LocalNavigator, TerrainUnavailable, terrain_type,
)
from quickstart.observations import Position
from quickstart.results import RoundResult, show_round_result
from quickstart.match import ManhuntMatch


class FakeScarpet:
    """Emulates the output of Carpet's batched /script command."""
    POINTS = re.compile(r'str\(block\((-?\d+),(-?\d+),(-?\d+)\)\)')

    def __init__(self):
        self.blocks = {}
        self.calls = []

    def set(self, x, y, z, block):
        self.blocks[(x,y,z)] = block

    def at(self, x,y,z):
        if (x,y,z) in self.blocks:
            return self.blocks[(x,y,z)]
        return 'stone' if y <= 63 else 'air'

    def command(self, command):
        self.calls.append(command)
        if 'script run print(' not in command:
            return 'OK'
        coords=[tuple(map(int, p)) for p in self.POINTS.findall(command)]
        assert coords, command
        return 'MHNAV4:'+'|'.join(self.at(*p) for p in coords)+':ENDMH4'


def navigable():
    fake=FakeScarpet()
    sensor=TerrainSensor(fake,ttl=0,max_batch=21)
    nav=LocalNavigator(sensor)
    return fake,sensor,nav


class TerrainTests(unittest.TestCase):
    def test_batch_sensor_and_cache(self):
        server=FakeScarpet()
        now=[100.]
        sense=TerrainSensor(server,ttl=2.,max_batch=2,clock=lambda:now[0])
        loc=[(0,64,0),(0,63,0),(1,64,0)]
        self.assertEqual(sense.read(loc),{loc[0]:'air',loc[1]:'stone',loc[2]:'air'})
        self.assertEqual(len(server.calls),2)
        sense.read(loc)
        self.assertEqual(len(server.calls),2)
        now[0]=103.
        sense.read(loc)
        self.assertEqual(len(server.calls),4)
        self.assertTrue(sense.active)

    def test_sensor_rejects_missing_sentinel(self):
        remote=Mock()
        remote.command.return_value='Unknown command'
        with self.assertRaises(TerrainUnavailable):
            TerrainSensor(remote).read([(0,64,0)])

    def test_never_considers_lava_safe(self):
        self.assertEqual(terrain_type('lava'),'hazard')
        self.assertEqual(terrain_type('magma_block'),'hazard')
        self.assertEqual(terrain_type('oak_log'),'solid')
        self.assertEqual(terrain_type('water'),'water')
        self.assertEqual(terrain_type('air'),'air')

    def test_flat_moves_toward_target(self):
        server,sensor,nav=navigable()
        path=nav.choose(Position(0,64,0),Position(20,64,0))
        self.assertIsNotNone(path)
        self.assertGreater(path.destination.x,1.0)
        self.assertFalse(path.jump)
        self.assertFalse(path.swimming)
        self.assertTrue(all('script run' in call for call in server.calls))
        self.assertLessEqual(max(len(x) for x in server.calls),1300)

    def test_tree_two_blocks_tall_forces_detour(self):
        server,_,nav=navigable()
        for x in (1,2):
            for y in (64,65):
                server.set(x,y,0,'oak_log')
        choice=nav.choose(Position(0,64,0),Position(20,64,0))
        self.assertIsNotNone(choice)
        self.assertNotEqual(math.floor(choice.destination.z),0)

    def test_can_jump_one_block_step(self):
        server,_,nav=navigable()
        server.set(1,64,0,'stone')
        result=nav.choose(Position(0,64,0),Position(20,64,0))
        self.assertIsNotNone(result)
        self.assertTrue(result.jump)

    def test_avoids_dangerous_cliff(self):
        server,_,nav=navigable()
        for x in (1,2):
            for y in (63,62,61):
                server.set(x,y,0,'air')
        result=nav.choose(Position(0,64,0),Position(20,64,0))
        self.assertIsNotNone(result)
        self.assertNotEqual(math.floor(result.destination.z),0)

    def test_water_crossing_when_no_dry_choice(self):
        server,_,nav=navigable()
        # Water over a wide area with a floor below it.
        for x in range(-4,5):
            for z in range(-4,5):
                server.set(x,64,z,'water')
                server.set(x,63,z,'dirt')
        result=nav.choose(Position(0,64,0),Position(20,64,0),avoid_water=True)
        self.assertIsNotNone(result)
        self.assertTrue(result.swimming)

    def test_stuck_penalizes_previous_destination(self):
        server,_,nav=navigable()
        here=Position(0,64,0)
        target=Position(20,64,0)
        original=nav.choose(here,target)
        nav.mark_stuck(here)
        second=nav.choose(here,target)
        self.assertIsNotNone(second)
        self.assertNotEqual(
            (math.floor(original.destination.x),math.floor(original.destination.z)),
            (math.floor(second.destination.x),math.floor(second.destination.z)))

    def test_fully_surrounded_rejects_unsafe_terrain(self):
        server,_,nav=navigable()
        for x in range(-4,5):
            for z in range(-4,5):
                if x or z:
                    for y in (64,65,66):
                        server.set(x,y,z,'obsidian')
        self.assertIsNone(nav.choose(Position(0,64,0),Position(20,64,0)))


class GameplayTests(unittest.TestCase):
    def test_screen_is_four_seconds_not_28(self):
        rcon=Mock()
        show_round_result(rcon,RoundResult('hunter','hunter','Alex',40,'tag'))
        commands=[call.args[0] for call in rcon.command.call_args_list]
        self.assertIn('title Alex times 5t 60t 15t',commands)
        self.assertTrue(any('/trigger mh_replay' in cmd for cmd in commands))
        self.assertFalse(any(cmd.startswith('stop') for cmd in commands))

    def test_real_game_uses_terrain_waypoint(self):
        server=FakeScarpet()
        game=ManhuntMatch(server,'runner',0,60)
        game.player='Alex'
        game.observer.position=lambda name: Position(10,64,0) if name==game.bot else Position(25,64,0)
        game.look_and_move=Mock()
        self.assertIsNone(game.step())
        destination=game.look_and_move.call_args.args[0]
        self.assertGreater(destination.x,10)
        self.assertLess(destination.x,25)
        self.assertGreater(game.nav_samples,0)

    def test_recovery_moves_away_and_starts_replan(self):
        server=FakeScarpet()
        game=ManhuntMatch(server,'runner',0,60)
        game.player='Alex'
        game.observer.position=lambda name: Position(10,64,0) if name==game.bot else Position(25,64,0)
        game.look_and_move=Mock()
        game.step()
        game.last_progress-=5
        game.moving=True  # simulate the active Carpet movement driver
        self.assertIsNone(game.step())
        self.assertEqual(game.recovery_attempts,1)
        self.assertTrue(game.look_and_move.called)
        self.assertFalse(any('move backward' in call for call in server.calls))


if __name__=='__main__':
    unittest.main()
