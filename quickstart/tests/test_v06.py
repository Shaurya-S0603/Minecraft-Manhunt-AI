"""v0.6 offline validations. Live Fabric/Carpet testing still required."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from quickstart.hit_detection import HitDetector, HitDetectionError
from quickstart.block_breaking import BlockBreaker, mineable
from quickstart.swimming import WaterSurvival
from quickstart.terrain import TerrainSensor
from quickstart.observations import Position
from quickstart.match import ManhuntMatch
from quickstart.combat import attack_line_clear
from quickstart.tests.test_navigation import FakeScarpet


class HitRcon:
    def __init__(self):
        self.commands=[]
        self.ai=0
        self.human=0
        self.fail_load=False
    def command(self, cmd):
        self.commands.append(cmd)
        if cmd=='script load mh_hitwatch' and self.fail_load:
            return 'Error: bad app'
        if cmd.startswith('scoreboard players get #AI mh_hit'):
            return f'#AI has {self.ai} [mh_hit]'
        if cmd.startswith('scoreboard players get #HUMAN mh_hit'):
            return f'#HUMAN has {self.human} [mh_hit]'
        if cmd.startswith('scoreboard players set #AI'):
            self.ai=0
        if cmd.startswith('scoreboard players set #HUMAN'):
            self.human=0
        return 'OK'

class EventScoringTests(unittest.TestCase):
    def test_listener_scoped_to_real_opponents_and_positive_damage(self):
        rcon=HitRcon()
        with tempfile.TemporaryDirectory() as tmp:
            detection=HitDetector(rcon,Path(tmp),'Alex')
            detection.setup()
            code=(Path(tmp)/'scripts/mh_hitwatch.sc').read_text()
            self.assertIn('__on_player_deals_damage',code)
            self.assertIn('amount > 0',code)
            self.assertIn("victim~'name' == 'Alex'",code)
            self.assertIn("attacker~'name' == 'Alex'",code)
            self.assertFalse(detection.hunter_hit('runner'))
            self.assertFalse(detection.hunter_hit('hunter'))
            rcon.ai=1
            self.assertTrue(detection.hunter_hit('runner'))
            self.assertFalse(detection.hunter_hit('hunter'))
            rcon.human=1
            self.assertTrue(detection.hunter_hit('hunter'))
            detection.reset()
            self.assertFalse(detection.hunter_hit('hunter'))
            self.assertFalse(detection.hunter_hit('runner'))

    def test_listener_error_is_fail_closed(self):
        rcon=HitRcon()
        rcon.fail_load=True
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(HitDetectionError):
                HitDetector(rcon,Path(tmp),'Alex').setup()

    def test_names_validated(self):
        with self.assertRaises(ValueError):
            HitDetector(HitRcon(), Path('.'), 'Alex;kill @a')

class SwimmingRcon(FakeScarpet):
    def __init__(self):
        super().__init__()
        self.air=300
    def command(self, cmd):
        if 'MHAIR:' in cmd:
            self.calls.append(cmd)
            return f'MHAIR:{self.air}:END'
        return super().command(cmd)

class SwimTests(unittest.TestCase):
    def test_water_holds_jump_and_releases_on_land(self):
        rcon=SwimmingRcon()
        rcon.set(0,64,0,'water')
        rcon.set(0,65,0,'water')
        sense=TerrainSensor(rcon,ttl=0)
        swim=WaterSurvival(rcon,sense,clock=lambda:50.)
        stop=Mock()
        self.assertTrue(swim.update(Position(.5,64,.5),50.,stop_movement=stop))
        self.assertTrue(swim.swimming)
        self.assertIn('player ManhuntBot jump continuous',rcon.calls)
        swim.update(Position(.5,64,.5),50.2,stop_movement=stop)
        self.assertEqual(rcon.calls.count('player ManhuntBot jump continuous'),1)
        rcon.set(0,64,0,'air')
        rcon.set(0,65,0,'air')
        self.assertFalse(swim.update(Position(.5,64,.5),50.4,stop_movement=stop))
        stop.assert_called_once()

    def test_low_air_activates_temporary_rescue(self):
        rcon=SwimmingRcon()
        rcon.air=45
        rcon.set(0,64,0,'water')
        swim=WaterSurvival(rcon,TerrainSensor(rcon,ttl=0))
        self.assertTrue(swim.update(Position(.5,64,.5),100.,stop_movement=Mock()))
        self.assertIn('effect give ManhuntBot minecraft:water_breathing 12 0 true',rcon.calls)
        self.assertEqual(swim.emergency_count,1)

    def test_no_water_no_emergency_buff(self):
        rcon=SwimmingRcon()
        swim=WaterSurvival(rcon,TerrainSensor(rcon))
        self.assertFalse(swim.update(Position(.5,64,.5),100.,stop_movement=Mock()))
        self.assertFalse(any('effect give' in c for c in rcon.calls))

class MiningTests(unittest.TestCase):
    def test_wood_leaf_and_dirt_allowed_but_stone_and_hazards_not(self):
        for block in ('dirt','oak_log','spruce_leaves','grass_block','sand'):
            self.assertTrue(mineable(block))
        for block in ('stone','bedrock','lava','chest','water','magma_block'):
            self.assertFalse(mineable(block))

    def test_mines_real_block_then_confirms_changed(self):
        rcon=FakeScarpet()
        rcon.set(1,64,0,'oak_log')
        sense=TerrainSensor(rcon,ttl=0)
        miner=BlockBreaker(rcon,sense)
        stop=Mock()
        self.assertTrue(miner.try_start(Position(.5,64,.5),Position(5.5,64,.5),100.,stop_movement=stop))
        stop.assert_called_once()
        self.assertTrue(any('attack continuous' in c for c in rcon.calls))
        self.assertTrue(miner.tick(100.2))
        rcon.set(1,64,0,'air')
        self.assertFalse(miner.tick(101.))
        self.assertEqual(miner.successes,1)
        self.assertIsNone(miner.operation)
        self.assertFalse(any('setblock' in c for c in rcon.calls))

    def test_stops_at_hazard_above_candidate(self):
        rcon=FakeScarpet()
        rcon.set(1,64,0,'dirt')
        rcon.set(1,66,0,'lava')
        miner=BlockBreaker(rcon,TerrainSensor(rcon,ttl=0))
        self.assertFalse(miner.try_start(Position(.5,64,.5),Position(5,64,.5),100.,stop_movement=Mock()))

    def test_mining_times_out(self):
        rcon=FakeScarpet()
        rcon.set(1,64,0,'dirt')
        miner=BlockBreaker(rcon,TerrainSensor(rcon,ttl=0))
        self.assertTrue(miner.try_start(Position(.5,64,.5),Position(5,64,.5),100.,stop_movement=Mock()))
        self.assertFalse(miner.tick(105.))
        self.assertEqual(miner.failures,1)

class LineOfSightTests(unittest.TestCase):
    def test_wall_prevents_attack_but_leaf_litter_does_not(self):
        world=FakeScarpet()
        sensor=TerrainSensor(world,ttl=0)
        first=Position(.5,64,.5)
        second=Position(2.5,64,.5)
        self.assertTrue(attack_line_clear(sensor,first,second))
        world.set(1,65,0,'oak_log')
        self.assertFalse(attack_line_clear(sensor,first,second))
        world.set(1,65,0,'leaf_litter')
        self.assertTrue(attack_line_clear(sensor,first,second))

class HitGameplayTests(unittest.TestCase):
    def test_proximity_not_a_win_ai_attacks_instead(self):
        rcon=FakeScarpet()
        game=ManhuntMatch(rcon,'runner',0,60)
        game.player='Alex'
        game.hit_detector=Mock()
        game.hit_detector.hunter_hit.return_value=False
        game.water.update=Mock(return_value=False)
        game.observer.position=lambda name: Position(1.5,64,.5) if name=='Alex' else Position(.5,64,.5)
        self.assertIsNone(game.step())
        self.assertTrue(any('attack once' in cmd for cmd in rcon.calls))
        self.assertTrue(game.hit_detector.hunter_hit.called)

    def test_confirmed_event_wins_before_navigation(self):
        game=ManhuntMatch(Mock(),'hunter',0,60)
        game.player='Alex'
        game.hit_detector=Mock()
        game.hit_detector.hunter_hit.return_value=True
        game.observer.position=lambda _: Position(2,64,2)
        self.assertEqual(game.step(),'hunter')

if __name__=='__main__':
    unittest.main()
