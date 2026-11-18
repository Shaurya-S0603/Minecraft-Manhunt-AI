"""Policy and integration guards independent of the Minecraft process."""
from dataclasses import asdict
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock

from quickstart.hunter_v1.bridge import Bridge
from quickstart.hunter_v1.cli import summarize
from quickstart.hunter_v1.game import HunterGame, Metrics
from quickstart.hunter_v1.learning import Playbook, RouteMemory
from quickstart.hunter_v1.pursuit import Compass, Guide, Pursuit
from quickstart.hunter_v1.recipes import PLANKS, Recipe, plan
from quickstart.hunter_v1.settings import load_settings
from quickstart.hunter_v1.supply import Supply
from quickstart.hunter_v1.traverse import Builder, Climber, Portals
from quickstart.observations import Position
from quickstart.swimming import WaterSurvival

OVERWORLD = "minecraft:overworld"
NETHER = "minecraft:the_nether"


class Sensor:
    def __init__(self, cells=None, default="air"):
        self.cells = cells or {}
        self.cache = {}
        self.default = default

    def read(self, keys):
        return {key: self.cells.get(key, self.default) for key in keys}


class HunterV1Tests(unittest.TestCase):
    def setUp(self):
        self.rules = load_settings()
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.data = Path(directory.name)
        self.book_path = self.data / "playbook.json"

    def book(self, **kwargs):
        return Playbook(self.book_path, self.rules["learning"], **kwargs)

    def test_compass_never_reveals_wall_hidden_location_or_exact_far_range(self):
        tracker = Compass(self.rules["tracking"])
        bot = Position(.5, 64, .5)
        far = tracker.observe(bot, Position(110, 80, .5), 1, Sensor())
        self.assertEqual(far.target, Position(10.5, 64, .5))
        self.assertIsNone(far.visible)
        hidden = tracker.observe(bot, Position(8.5, 64, .5), 2, Sensor(default="stone"))
        self.assertIsNone(hidden.visible)
        self.assertIsNone(tracker.observe(bot, Position(900, 80, .5), 50, Sensor()))

    def test_visible_runner_and_lost_trail(self):
        tracker = Compass(self.rules["tracking"])
        bot = Position(.5, 64, .5)
        runner = Position(5, 64, .5)
        self.assertEqual(tracker.observe(bot, runner, 1, Sensor()).visible, runner)
        self.assertEqual(tracker.observe(bot, runner, 3, Sensor(default="stone")).target, runner)
        self.assertIsNone(tracker.observe(bot, None, 4, Sensor()))

    def test_playbook_persistence_bounds_and_held_out_read_only(self):
        self.rules["learning"]["max_entries"] = 16
        book = self.book()
        for i in range(20):
            book.reward("ctx", str(i), -.8 if i % 2 else .6)
        book.save()
        raw = self.book_path.read_bytes()
        frozen = self.book(read_only=True)
        self.assertEqual(len(frozen.entries), 16)
        self.assertNotIn("ctx/0", frozen.entries)
        frozen.reward("ctx", "new", 1)
        frozen.save()
        self.assertEqual(raw, self.book_path.read_bytes())

    def test_unknown_schema_is_preserved(self):
        self.book_path.write_text('{"schema":9}', encoding="utf-8")
        playbook = self.book()
        self.assertTrue(playbook.load_issue)
        playbook.reward("a", "b", 1)
        playbook.save()
        self.assertEqual(self.book_path.read_text(), '{"schema":9}')

    def test_pursuit_does_not_score_stationary_or_lost_sight(self):
        agent = Pursuit(self.book(), "Runner")
        bot = Position(0, 64, 0)
        runner = Position(10, 64, 0)
        guide = Guide(runner, visible=runner)
        agent.goal(bot, guide, OVERWORLD, 0)
        agent.goal(bot, guide, OVERWORLD, 4)
        agent.goal(bot, Guide(runner), OVERWORLD, 4.5)
        self.assertFalse(agent.book.entries)
        agent.goal(bot, guide, OVERWORLD, 5)
        agent.goal(Position(4, 64, 0), guide, OVERWORLD, 9)
        self.assertGreater(next(iter(agent.book.entries.values())).value, 0)

    def test_route_bias_is_world_dimension_scoped(self):
        book = self.book()
        memory = RouteMemory(book, "test")
        memory.reset(OVERWORLD)
        source, target = (0, 64, 0), (2, 64, 0)
        for t in (1, 5):
            memory.observe(source, target, True, t)
            memory.observe(source, target, True, t + 3.)
        self.assertGreater(memory.penalty(source, target), 0)
        memory.reset(NETHER)
        self.assertEqual(memory.penalty(source, target), 0)

    def test_recipe_reserves_cost_across_stacks_and_refuses_full_inventory(self):
        recipe = Recipe("crafting_table", 1, ((PLANKS, 4),))
        slots = {0: {"id": "minecraft:oak_planks", "count": 3},
                 31: {"id": "minecraft:birch_planks", "count": 4}}
        self.assertEqual(plan(recipe, slots), ([(0, "oak_planks", 3), (31, "birch_planks", 1)], 1))
        self.assertIsNone(plan(recipe, {i: slots[0] for i in range(36)}))
        self.assertIsNone(plan(recipe, {0: slots[0]}))

    def test_craft_bridge_serializes_numeric_allocations(self):
        rcon = Mock()
        rcon.command.return_value = "MHV1:ok:ENDV1"
        commands = Bridge(rcon, "ManhuntBot")
        self.assertTrue(commands.craft([(3, "stick", 2), (7, "oak_planks", 3)], 4,
                                       "wooden_pickaxe", 1, (0, 62, -1)))
        payload = rcon.command.call_args.args[0]
        self.assertIn("mh_craft('ManhuntBot',[[3,'stick',2],[7,'oak_planks',3]],4,'wooden_pickaxe',1,[0,62,-1])", payload)
        self.assertNotIn("give ", payload)

    def test_water_safety_does_not_grant_effect_in_v1(self):
        rcon = Mock()
        rcon.command.return_value = "MHAIR:20:END"
        water = WaterSurvival(rcon, Sensor(default="water"), rescue_effect=False)
        water.update(Position(.5, 64, .5), 20, stop_movement=Mock(), vertical=0)
        actions = [call.args[0] for call in rcon.command.call_args_list]
        self.assertIn("player ManhuntBot jump continuous", actions)
        self.assertFalse(any(action.startswith("effect ") for action in actions))

    def bridge_fixture(self, first="air"):
        game = Mock()
        game.settings = self.rules
        game.miner.operation = None
        game.water.swimming = False
        game.grounded = game.inventory.available = True
        game.inventory.slots = {0: {"id": "minecraft:dirt", "count": 10}}
        game.sensor = Sensor({(0, 63, 0): "stone", (1, 63, 0): first, (3, 63, 0): "stone"})
        return game, Builder(game), Position(.5, 64, .5), Position(5.5, 64, .5)

    def test_lava_bridge_requires_opt_in_and_fireproof_block(self):
        game, builder, loc, goal = self.bridge_fixture("lava")
        self.assertFalse(builder.start(loc, goal, 3))
        self.rules["resources"]["lava_bridge"] = True
        self.assertFalse(builder.start(loc, goal, 6))
        game.inventory.slots = {0: {"id": "minecraft:cobblestone", "count": 10}}
        self.assertTrue(builder.start(loc, goal, 10))
        self.assertTrue(builder.tick(loc, 10.05))
        self.assertLess(game.bridge.look.call_args.args[0].x, loc.x)
        game.sensor.cells[1, 63, 0] = "cobblestone"
        builder.tick(loc, 10.5)
        self.assertEqual(builder.placed, 0)  # No first use, so no placement credit.

    def test_bridge_uses_a_single_corridor_and_confirms_each_placement(self):
        game, builder, loc, goal = self.bridge_fixture()
        self.assertTrue(builder.start(loc, goal, 3))
        self.assertTrue(builder.tick(loc, 3.1))
        for x in (1, 2):
            overhang = Position(x + .05, 64, .5)
            self.assertTrue(builder.tick(overhang, 3 + x))
            game.sensor.cells[x, 63, 0] = "dirt"
            game.inventory.slots[0]["count"] -= 1
            self.assertTrue(builder.tick(overhang, 3.1 + x))
            self.assertTrue(builder.tick(overhang, 3.2 + x))
            self.assertAlmostEqual(game.bridge.look.call_args.args[0].x, x + .5)
            self.assertTrue(builder.tick(Position(x + .5, 64, .5), 3.3 + x))
        self.assertTrue(builder.tick(Position(3.5, 64, .5), 5.9))
        self.assertEqual((builder.placed, builder.crossed), (2, 1))
        self.assertFalse(builder.active)

    def test_bridge_rejects_a_missing_bank_or_insufficient_stock(self):
        game, builder, loc, goal = self.bridge_fixture()
        game.inventory.slots[0]["count"] = 1
        self.assertFalse(builder.start(loc, goal, 3))
        game.inventory.slots[0]["count"] = 10
        del game.sensor.cells[3, 63, 0]
        self.assertFalse(builder.start(loc, goal, 6))

    def test_bridge_stops_when_a_previously_observed_column_becomes_blocked(self):
        game, builder, loc, goal = self.bridge_fixture()
        self.assertTrue(builder.start(loc, goal, 3))
        game.sensor.cells[1, 64, 0] = "stone"
        self.assertFalse(builder.tick(loc, 3.2))
        self.assertFalse(builder.active)
        self.assertFalse(any(c.args == ("use once",) for c in game.bridge.action.call_args_list))

    def climb_fixture(self):
        game = Mock()
        game.grounded = True
        game.miner.operation = None
        game.water.swimming = False
        game.sensor = Sensor({(x, y, 0): material for x, material in ((0, "vine"), (1, "stone"))
                              for y in range(64, 69)})
        return game, Climber(game), Position(.5, 64, .5), Position(2.5, 69, .5)

    def test_climb_finishes_only_on_verified_ground_at_the_ledge(self):
        game, climber, loc, goal = self.climb_fixture()
        self.assertTrue(climber.start(loc, goal, 3))
        game.grounded = False
        self.assertTrue(climber.tick(Position(.7, 68.7, .5), 4.5))
        self.assertEqual(climber.completed, 0)
        game.grounded = True
        self.assertTrue(climber.tick(Position(1.4, 69., .5), 5))
        self.assertEqual(climber.completed, 1)
        self.assertIsNone(climber.ascent)

    def test_climb_cancels_when_the_ledge_becomes_blocked(self):
        game, climber, loc, goal = self.climb_fixture()
        self.assertTrue(climber.start(loc, goal, 3))
        game.sensor.cells[1, 69, 0] = "stone"
        self.assertFalse(climber.tick(Position(.7, 68.7, .5), 4))
        self.assertEqual(climber.completed, 0)
        self.assertIsNone(climber.ascent)

    def test_portal_policy_never_uses_stale_or_unobserved_coordinates(self):
        game = Mock()
        portals = Portals(game, self.book(), "test")
        loc = Position(.5, 64, .5)
        self.assertFalse(portals.follow(OVERWORLD, NETHER, loc, 30))
        portals.known[OVERWORLD, (12, 64, 0)] = ("nether_portal", 2)
        self.assertFalse(portals.follow(OVERWORLD, NETHER, loc, 200))
        portals.known[OVERWORLD, (12, 64, 0)] = ("nether_portal", 200)
        self.assertTrue(portals.follow(OVERWORLD, NETHER, loc, 201))
        game.navigate.assert_called_once()

    def test_dimension_transition_invalidates_route_and_does_not_expose_runner_position(self):
        g = HunterGame(Mock(), self.rules, self.data, self.data, "world")
        g.inventory = Mock()
        g._surface = Mock(return_value=False)
        g.pursuit = Mock()
        g.portals = Mock()
        g.portals.follow.return_value = True
        g.supply = Mock(wraps=Supply(g))
        g.supply.blocked = {}
        g.previous = Position(100, 64, 100)
        g.last_dim = OVERWORLD
        bot = (NETHER, "survival", 20, 20, True, Position(1, 64, 1))
        human = (OVERWORLD, "survival", 20, 20, True, Position(444, 90, 555))
        g.tick_v1(bot, human, 5, 4)
        self.assertEqual(g.metrics.blocks_traveled, 0)
        g.portals.follow.assert_called_once_with(NETHER, OVERWORLD, bot[-1], 5)
        g.pursuit.goal.assert_not_called()

    def test_harvest_aim_uses_the_exposed_face_instead_of_looking_through_the_log(self):
        g = Mock()
        g.settings = self.rules
        g.sensor = Sensor({(2, 64, 0): "oak_log", (2, 65, 0): "oak_log"})
        supply = Supply(g)
        self.assertTrue(supply._visible_face(Position(.5, 64, .5), (2, 64, 0)))
        g.sensor.cells[1, 64, 0] = g.sensor.cells[1, 65, 0] = "stone"
        self.assertFalse(supply._visible_face(Position(.5, 64, .5), (2, 64, 0)))

    def test_reporting_keeps_aborted_rounds_out_of_win_rate(self):
        path = self.data / "rounds.jsonl"
        rows = [Metrics(result="hunter", first_hit_s=12, items_picked_up={"dirt": 3}),
                Metrics(result="runner", blocks_traveled=10), Metrics()]
        path.write_text("".join(json.dumps({"schema": 1, "split": "held-out", "scenario": "gap",
                                           "mode": "hit", **asdict(row)}) + "\n" for row in rows))
        report = summarize(path, split="held-out", scenario="gap", mode="hit")
        self.assertEqual(report["hunter_win_rate"], .5)
        self.assertEqual(report["aborted"], 1)
        self.assertEqual(report["median_first_hit_s"], 12)
        self.assertEqual(report["mean_items_picked_up"], 3)


if __name__ == "__main__":
    unittest.main()
