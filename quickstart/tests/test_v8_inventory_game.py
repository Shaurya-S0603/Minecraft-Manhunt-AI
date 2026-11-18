"""Offline regression tests for v8. Live Fabric checks remain necessary."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from quickstart.v8_config import load_config
from quickstart.v8_inventory import parse_inventory, total_items, inventory_deltas, InventoryMonitor
from quickstart.v8_tracking import CoordinateTracker
from quickstart.v8_score import record_v8_score
from quickstart.observations import Position
from quickstart.results import RoundResult
from quickstart.v8_resources import ResourceCollector
from quickstart.v8_inventory_events import InventoryEventBridge


def nbt(*stacks):
    return 'ManhuntBot has the following entity data: [' + ', '.join(
        '{Slot: %db, count: %d, id: "minecraft:%s"}' % x for x in stacks) + ']'


class InventoryTests(unittest.TestCase):
    def test_empty_inventory(self):
        self.assertEqual(parse_inventory('ManhuntBot has the following entity data: []'), {})

    def test_36_slot_stacks(self):
        self.assertEqual(parse_inventory(nbt((0,64,'oak_log'), (35,1,'iron_pickaxe')))[35]['count'], 1)

    def test_components_have_nested_metadata(self):
        value='[{Slot: 0b, count: 1, components: {"minecraft:custom_name": {text:"hello"}}, id:"minecraft:dirt"}]'
        self.assertEqual(parse_inventory(value)[0]['id'],'minecraft:dirt')

    def test_armor_offhand_excluded(self):
        self.assertEqual(parse_inventory(nbt((40,1,'shield'),(101,1,'chestplate'),(3,2,'apple'))),
                         {3: {'id':'minecraft:apple','count':2}})

    def test_duplicate_slot_rejected(self):
        with self.assertRaises(ValueError):
            parse_inventory(nbt((0,1,'stone'),(0,1,'apple')))

    def test_invalid_observation_rejected(self):
        with self.assertRaises(ValueError):
            parse_inventory('Unknown command')

    def test_inventory_deltas_not_mislabeled_as_pickups(self):
        a=parse_inventory(nbt((0,5,'oak_log')))
        b=parse_inventory(nbt((0,3,'oak_log'),(1,2,'apple')))
        events=inventory_deltas(a,b)
        self.assertEqual([(e['item'],e['delta']) for e in events],
                         [('minecraft:apple',2),('minecraft:oak_log',-2)])
        self.assertTrue(all(e['kind'].startswith('inventory_') for e in events))


    def test_drop_command_requires_real_inventory_and_does_not_give(self):
        with tempfile.TemporaryDirectory() as d:
            fake=Mock(command=Mock(return_value='Dropped one item'))
            mon=InventoryMonitor(fake,'ManhuntBot',Path(d),clock=lambda:1)
            self.assertFalse(mon.drop_selected_one())
            mon.available=True
            mon.snapshot=Mock(return_value=[])
            self.assertTrue(mon.drop_selected_one())
            fake.command.assert_called_with('player ManhuntBot drop')

    def test_transfer_offer_is_not_claimed_as_pickup(self):
        with tempfile.TemporaryDirectory() as d:
            fake=Mock(command=Mock(return_value='Dropped one item'))
            mon=InventoryMonitor(fake,'ManhuntBot',Path(d),clock=lambda:1)
            mon.available=True
            mon.snapshot=Mock(return_value=[])
            self.assertFalse(mon.offer_transfer(Position(0,64,0),Position(5,64,0)))
            self.assertTrue(mon.offer_transfer(Position(0,64,0),Position(1,64,0)))

    def test_scarpet_event_names_are_documented(self):
        bridge=InventoryEventBridge(Mock(),Path('world'),'ManhuntBot')
        script=bridge.script()
        self.assertIn('__on_player_picks_up_item', script)
        self.assertIn('__on_player_drops_item', script)
        self.assertIn('__on_player_drops_stack', script)

    def test_monitor_initial_snapshot_has_no_false_event(self):
        with tempfile.TemporaryDirectory() as d:
            fake=Mock()
            fake.command.side_effect=[nbt((0,2,'oak_log')),nbt((0,3,'oak_log'))]
            monitor=InventoryMonitor(fake,'ManhuntBot',Path(d),clock=lambda:100,poll_seconds=0.5)
            self.assertEqual(monitor.snapshot(force=True), [])
            self.assertEqual(monitor.snapshot(force=True)[0]['delta'], 1)
            saved=json.loads((Path(d)/'inventory_snapshot.json').read_text())
            self.assertFalse(saved['authoritative'])
            self.assertEqual(saved['slots']['0']['count'],3)

    def test_unreadable_inventory_disables_monitor(self):
        with tempfile.TemporaryDirectory() as d:
            fake=Mock(command=lambda _: 'Unknown command')
            monitor=InventoryMonitor(fake,'ManhuntBot',Path(d))
            self.assertEqual(monitor.snapshot(force=True),[])
            self.assertFalse(monitor.available)

class TrackingTests(unittest.TestCase):
    def setUp(self):
        self.rules={'enabled':True,'range_blocks':50,'cooldown_seconds':5,
                    'last_known_seconds':12,'reveal_exact_coordinates_to_hunter':True}
        self.a=Position(0,64,0)

    def test_range_and_expiry(self):
        track=CoordinateTracker(self.rules)
        self.assertEqual(track.sample(self.a,Position(5,64,0),0),Position(5,64,0))
        self.assertEqual(track.sample(self.a,Position(80,64,0),6),Position(5,64,0))
        self.assertIsNone(track.sample(self.a,Position(80,64,0),18))

    def test_coordinate_message_is_rate_limited(self):
        track=CoordinateTracker(self.rules)
        self.assertIn('X 5',track.message(self.a,Position(5,64,0),0))
        self.assertIsNone(track.message(self.a,Position(5,64,0),2))
        self.assertIsNotNone(track.message(self.a,Position(5,64,0),5))

class ConfigAndScoringTests(unittest.TestCase):
    def test_default_loads(self):
        self.assertEqual(load_config()['tracking']['mode'],'coordinates')

    def test_bad_allowlist_rejected(self):
        rules=load_config()
        rules['resources']['allowed_blocks']=['minecraft:command_block']
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'cfg.json'
            f.write_text(json.dumps(rules))
            with self.assertRaises(ValueError):
                load_config(f)

    def test_score_rounds(self):
        with tempfile.TemporaryDirectory() as d:
            rule=load_config()['scoring']
            r=RoundResult('hunter','runner','PlayerName',180.0,'survival')
            out=record_v8_score(r,rule,Path(d)/'scores.jsonl')
            self.assertEqual(out['points'],130)

    def test_only_real_results_score(self):
        with tempfile.TemporaryDirectory() as d:
            r=RoundResult('runner','hunter','PlayerName',32.0,'hit')
            out=record_v8_score(r,load_config()['scoring'],Path(d)/'scores.jsonl')
            self.assertEqual(out['points'],100)

class ResourcesTests(unittest.TestCase):
    def test_no_harvest_without_valid_inventory(self):
        inv=Mock(available=False)
        miner=Mock(operation=None)
        sensor=Mock()
        rules=load_config()['resources']
        collector=ResourceCollector(inv, miner, sensor, rules)
        self.assertFalse(collector.try_gather(Position(0,64,0),Position(100,64,0),'runner',100,lambda:None))
        sensor.read.assert_not_called()

    def test_hunter_nearby_prevents_resource_detour(self):
        inv=Mock(available=True)
        miner=Mock(operation=None)
        sensor=Mock()
        collector=ResourceCollector(inv,miner,sensor,load_config()['resources'])
        self.assertFalse(collector.try_gather(Position(0,64,0),Position(5,64,0),'runner',100,lambda:None))
        sensor.read.assert_not_called()

if __name__=='__main__': unittest.main()
