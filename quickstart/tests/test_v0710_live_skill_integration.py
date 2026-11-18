"""v0.7.10: transfer only actual validated swim/ladder settings to Manhunt."""
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from quickstart.live_skill_policy import LiveSkillPolicy
from quickstart.skill_policy import train_skill_policy, save_skill_policy
from quickstart.match import ManhuntMatch
from quickstart.observations import Position
from quickstart.pathfinding3d import PathStep
from quickstart.tests.test_navigation import FakeScarpet


def episode(skill, option, success=True):
    return {'schema':1,'source':'minecraft','skill':skill,
            'stage':'swim_horizontal' if skill=='swim' else 'ladder_up',
            'parameter':option,'success':success,'duration_s':1.5,
            'samples':[[1,0,64,0],[2,1,64,0]]}


def checked_profile(root):
    records=([episode('swim',.35,True)]*14+
             [episode('swim',0.,False)]*12+
             [episode('climb',1.45,True)]*12+
             [episode('climb',.45,False)]*12)
    log=root/'arena_episodes.jsonl'
    log.write_text(''.join(json.dumps(v)+'\n' for v in records))
    policy=train_skill_policy(log)
    path=root/'skill_policy.json'
    save_skill_policy(policy,path)
    return path


class LiveSkillGateTests(unittest.TestCase):
    def test_missing_checkpoint_does_not_enable_untrained_skills(self):
        with tempfile.TemporaryDirectory() as td:
            live=LiveSkillPolicy(Path(td)/'none.json')
            self.assertIsNone(live.value('swim'))
            self.assertIsNone(live.value('climb'))

    def test_verified_real_trial_snapshot_loads_both_skills(self):
        with tempfile.TemporaryDirectory() as td:
            path=checked_profile(Path(td))
            before=path.read_bytes()
            live=LiveSkillPolicy(path)
            self.assertEqual(live.value('swim'),.35)
            self.assertEqual(live.value('climb'),1.45)
            self.assertEqual(path.read_bytes(),before,'Manhunt must not modify trained policy')
            self.assertTrue(live.disable('swim','unit test stall'))
            self.assertIsNone(live.value('swim'))
            self.assertEqual(live.value('climb'),1.45)
            live.reload()
            self.assertEqual(live.value('swim'),.35)

    def test_insufficient_evidence_must_not_activate_even_if_flag_forged(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'skill_policy.json'
            data={'schema':1,'source':'observed_minecraft_trials',
                  'model':'per_skill_beta_smoothed_bandit',
                  'groups':{'swim':{'validated_for_live':True,
                                    'selected_parameter':-.35,
                                    'options':{'-0.35':{'wins':1,'trials':2}}},
                            'climb':{'validated_for_live':True,
                                     'selected_parameter':999,
                                     'options':{'999.0':{'wins':12,'trials':12}}}}}
            path.write_text(json.dumps(data))
            live=LiveSkillPolicy(path)
            self.assertEqual(live.selected,{})

    def test_manual_opt_out_keeps_built_in_controls(self):
        with tempfile.TemporaryDirectory() as td:
            path=checked_profile(Path(td))
            with patch.dict('os.environ',{'MANHUNT_LIVE_SKILLS':'0'}):
                live=LiveSkillPolicy(path)
                self.assertEqual(live.selected,{})

    def test_read_only_status_checker(self):
        from quickstart.live_skill_status import main
        with tempfile.TemporaryDirectory() as td:
            checked_profile(Path(td))
            self.assertEqual(main(['--data',td]),0)

    def test_real_training_outputs_reload_only_after_snapshot_refresh(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'skill_policy.json'
            live=LiveSkillPolicy(path)
            self.assertIsNone(live.value('swim'))
            checked_profile(Path(td))
            self.assertIsNone(live.value('swim'))
            live.reload()
            self.assertEqual(live.value('swim'),.35)


class LiveSkillControllerTests(unittest.TestCase):
    def setUp(self):
        self.server=FakeScarpet()
        self.game=ManhuntMatch(self.server,'runner',0,60)
        self.game.live_skills.selected={'swim':.35,'climb':1.45}
        self.game.live_skills.disabled.clear()
        self.game.observer.position=lambda name:Position(.5,64,.5)

    def test_horizontal_swim_applies_bias_to_real_look_command(self):
        game=self.game
        game.water.swimming=True
        game.water.vertical_mode=0
        game.water.last_air=300
        game.look_and_move(Position(3.5,62,.5))
        self.assertIn('player ManhuntBot look at 3.50 63.05 0.50',self.server.calls)

    def test_low_air_disables_learned_swim_for_emergency_ascent(self):
        game=self.game
        game.water.swimming=True
        game.water.vertical_mode=0
        game.water.last_air=120
        game.look_and_move(Position(3.5,62,.5))
        self.assertIn('player ManhuntBot look at 3.50 62.50 0.50',self.server.calls)

    def test_vertical_swim_and_surface_goal_use_safe_fixed_controls(self):
        game=self.game
        game.water.swimming=True
        game.water.last_air=300
        game.water.vertical_mode=1
        game.look_and_move(Position(3.5,62,.5))
        self.assertIn('player ManhuntBot look at 3.50 62.50 0.50',self.server.calls)
        self.server.calls.clear()
        game.water.vertical_mode=0
        game.surface_goal=Position(1.5,65,.5)
        game.look_and_move(Position(3.5,62,.5))
        self.assertIn('player ManhuntBot look at 3.50 62.50 0.50',self.server.calls)

    def test_ladder_aim_uses_learned_parameter(self):
        self.server.set(1,64,0,'stone')
        self.server.set(0,64,0,'ladder')
        self.game.climb_move(Position(.5,64,.5),Position(.5,67,.5))
        self.assertTrue(any('look at 1.50 65.45 0.50' in x for x in self.server.calls))
        self.assertIn('player ManhuntBot jump continuous',self.server.calls)

    def test_vines_keep_original_aim_because_only_ladders_were_trained(self):
        self.server.set(1,64,0,'stone')
        self.server.set(0,64,0,'vine')
        self.game.climb_move(Position(.5,64,.5),Position(.5,67,.5))
        self.assertTrue(any('look at 1.50 65.50 0.50' in x for x in self.server.calls))

    def test_no_climb_data_preserves_original_commands(self):
        self.server.set(1,64,0,'stone')
        self.server.set(0,64,0,'ladder')
        self.game.live_skills.selected.clear()
        self.game.climb_move(Position(.5,64,.5),Position(.5,67,.5))
        self.assertTrue(any('look at 1.50 65.50 0.50' in x for x in self.server.calls))

    def test_stall_disables_active_live_setting_without_writing_file(self):
        game=self.game
        now=time.monotonic()
        game.moving=True
        game.last_progress=now-5
        game.last_recovery_at=now-5
        game.path=(PathStep(Position(3.5,64,.5),swimming=True),)
        game.path_goal=Position(3.5,64,.5)
        game.path_start=Position(.5,64,.5)
        game.path_created_at=now
        game.navigate(Position(.5,64,.5),Position(3.5,64,.5),now)
        self.assertIsNone(game.live_skills.value('swim'))
        self.assertEqual(game.live_skills.value('climb'),1.45)

if __name__=='__main__': unittest.main()
