"""Regression checks for match-level learning and inventory bounds."""
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock
import json

from quickstart.hunter_v1.director import HuntDirector, round_score
from quickstart.hunter_v1.game import Metrics
from quickstart.hunter_v1.inventory import drop, inspect_inventory, transfer
from quickstart.hunter_v1.learning import Playbook
from quickstart.hunter_v1.settings import load_settings
from quickstart.hunter_v1.supply import harvest_product


class ManhuntV12Tests(TestCase):
    def setUp(self):
        self.settings = load_settings()
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "policy.json"

    def test_completed_openings_explore_then_frozen_policy_uses_existing_evidence(self):
        rules = self.settings["learning"]
        book = Playbook(self.path, rules)
        press = HuntDirector(book, rules, "hit")
        press.start(0., Counter(), 20, True)
        self.assertEqual(press.action, "press")
        self.assertFalse(press.allows_supply(3., 20))
        self.assertTrue(press.allows_supply(3., 8))
        self.assertIsNone(press.finish(Metrics()))
        self.assertFalse(book.entries)
        self.assertEqual(press.finish(Metrics(result="runner")), -.7)
        gear = HuntDirector(book, rules, "hit")
        gear.start(0., Counter(), 20, True)
        self.assertEqual(gear.action, "gear")
        self.assertGreater(gear.finish(Metrics(result="hunter", first_hit_s=4)), .7)
        book.save()
        original = self.path.read_bytes()
        frozen = Playbook(self.path, rules, read_only=True)
        evaluation = HuntDirector(frozen, rules, "hit")
        evaluation.start(0., Counter(), 20, True)
        self.assertEqual(evaluation.action, "gear")
        evaluation.finish(Metrics(result="runner"))
        frozen.save()
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(frozen.choose("opening/hit/unarmed", ("unseen", "gear")), "gear")

    def test_fixed_opening_does_not_credit_the_bandit(self):
        rules = self.settings["learning"]
        book = Playbook(self.path, rules)
        fixed = HuntDirector(book, rules, "hit", "gear")
        fixed.start(0., Counter(), 20, True)
        self.assertEqual(fixed.action, "gear")
        self.assertIsNone(fixed.finish(Metrics(result="hunter", first_hit_s=3)))
        self.assertFalse(book.entries)

    def test_older_config_defaults_and_two_sided_scoring(self):
        self.settings.pop("scoring")
        self.settings["game"]["human_role"] = "runner"
        self.settings["learning"].pop("opening_seconds")
        self.settings["learning"].pop("tag_bonus_seconds")
        self.settings["resources"].pop("allow_transfers")
        self.path.write_text(json.dumps(self.settings))
        current = load_settings(self.path)
        self.assertNotIn("human_role", current["game"])
        score = current["scoring"]
        self.assertEqual(round_score(Metrics(), score), {})
        self.assertEqual(round_score(Metrics(result="runner", first_hit_s=4), score),
                         {"runner": 3, "hunter": 1})
        self.assertEqual(round_score(Metrics(result="hunter", first_hit_s=3), score),
                         {"runner": 0, "hunter": 4})

    def test_config_rejects_the_old_ai_runner_role(self):
        self.settings["game"]["human_role"] = "hunter"
        self.path.write_text(json.dumps(self.settings))
        with self.assertRaisesRegex(ValueError, "The human plays Runner"):
            load_settings(self.path)

    def test_inventory_audit_pages_native_slots_including_offhand(self):
        bridge = Mock()
        bridge.query.side_effect = ["0|ender_pearl|5|16;", "", "", "", "40|shield|1|1"]
        slots = inspect_inventory(bridge)
        self.assertEqual(slots[0].vanilla_stack_limit, 16)
        self.assertEqual(slots[40].item, "shield")
        self.assertEqual(bridge.query.call_count, 5)

    def test_operator_transfer_and_drop_require_a_real_receipt(self):
        bridge = Mock()
        bridge.query.return_value = "blocked"
        with self.assertRaisesRegex(ValueError, "distinct"):
            transfer(bridge, "ManhuntBot", "manhuntbot", 0, 1, 1)
        bridge.query.assert_not_called()
        with self.assertRaisesRegex(ValueError, "blocked"):
            transfer(bridge, "ManhuntBot", "BenchRunner", 0, 17, 1)
        bridge.query.return_value = "stone|1"
        self.assertEqual(transfer(bridge, "ManhuntBot", "BenchRunner", 0, 17, 1)["count"], 1)
        self.assertEqual(drop(bridge, 0, 1), {"item": "stone", "count": 1})
        self.assertEqual(harvest_product("grass_block"), "dirt")
        self.assertEqual(harvest_product("stone"), "cobblestone")
