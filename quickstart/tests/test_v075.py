"""v0.7.5: no-match autonomous arena, safety, repeatability, real trial labels."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from quickstart.observations import Position
from quickstart.arena_training import ArenaRunner,ArenaStage,built_in_stages,read_stages,write_stage_template
from quickstart.training_server import training_properties,install_training_server,generate_arena
from quickstart.movement_policy import train_from_log

P=Position


class ConfigTests(unittest.TestCase):
    def test_generated_courses_cover_three_jumps_swim_and_climb(self):
        stages=built_in_stages()
        self.assertEqual([x.name for x in stages],['gap_1','gap_2','gap_3','swim_horizontal','ladder_up'])
        self.assertEqual([x.gap for x in stages[:3]],[1,2,3])
        self.assertEqual(stages[3].skill,'swim')
        self.assertEqual(stages[4].skill,'climb')

    def test_json_template_roundtrip(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'arena.json'
            write_stage_template(path,built_in_stages())
            self.assertEqual(read_stages(path),built_in_stages())
            before=path.read_bytes()
            write_stage_template(path,built_in_stages())
            self.assertEqual(path.read_bytes(),before)

    def test_invalid_and_non_cardinal_stages_rejected(self):
        with self.assertRaises(ValueError):
            ArenaStage('bad','sprint_jump',P(0,220,0),P(3,220,3),P(1,220,0),2)
        with self.assertRaises(ValueError):
            ArenaStage('bad','swim',P(float('nan'),220,0),P(3,220,3))
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'config.json'
            p.write_text(json.dumps({'schema':1,'stages':[{'name':'x','skill':'swim',
                     'start':[0,220,0],'target':[1,220,0],'evil_option':True}]}))
            with self.assertRaises(ValueError): read_stages(p)


class IsolationTests(unittest.TestCase):
    def test_training_properties_uses_new_ports_and_preserves_secret(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'training-server-data'
            props=training_properties(folder)
            self.assertEqual(props['server-port'],'25566')
            self.assertEqual(props['rcon.port'],'25576')
            self.assertEqual(props['server-ip'],'127.0.0.1')
            self.assertEqual(props['online-mode'],'true')
            self.assertNotEqual(props['rcon.password'],'password')
            again=training_properties(folder)
            self.assertEqual(props['rcon.password'],again['rcon.password'])
            self.assertEqual(again['level-name'],'world')

    def test_installer_copies_binary_only_never_world_or_secret(self):
        with tempfile.TemporaryDirectory() as tmp:
            main=Path(tmp)/'server-data'
            training=Path(tmp)/'training-server-data'
            (main/'mods').mkdir(parents=True)
            (main/'fabric-server.jar').write_bytes(b'fabric')
            (main/'mods/carpet.jar').write_bytes(b'carpet')
            (main/'world').mkdir()
            (main/'world/user-builds').write_bytes(b'user data')
            (main/'server.properties').write_text('rcon.password=secret-not-to-copy\n')
            (main/'eula.txt').write_text('eula=true\n')
            install_training_server(main,training)
            self.assertTrue((training/'mods/carpet.jar').exists())
            self.assertFalse((training/'world').exists())
            self.assertNotIn('secret-not-to-copy',(training/'server.properties').read_text())
            self.assertEqual((main/'world/user-builds').read_bytes(),b'user data')

    def test_generator_stops_on_wrong_world_and_never_regenerates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'training-server-data'
            world=root/'world'
            world.mkdir(parents=True)
            server=Mock()
            server.command.return_value='OK'
            self.assertTrue(generate_arena(server,world))
            commands=[c.args[0] for c in server.command.call_args_list]
            self.assertTrue(any('fill 0 219 -2 5 219 2 stone' in cmd for cmd in commands))
            self.assertTrue(any('ladder[facing=west]' in cmd for cmd in commands))
            self.assertIn('gamerule minecraft:fall_damage false',commands)
            self.assertIn('gamerule minecraft:advance_time false',commands)
            self.assertIn('forceload add -16 -16 32 112',commands)
            self.assertTrue(any('fill 0 216 77 17 218 83 water' in cmd for cmd in commands))
            self.assertFalse(generate_arena(server,world))
            self.assertEqual(len(server.command.call_args_list),len(commands))
            with self.assertRaises(ValueError): generate_arena(server,root/'other-world')

    def test_custom_map_never_cleared(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'training-server-data'
            world=root/'world'
            world.mkdir(parents=True)
            (root/'.custom_map_installed').write_text('yes')
            server=Mock()
            with self.assertRaises(RuntimeError): generate_arena(server,world)
            server.command.assert_not_called()


class Clock:
    def __init__(self):self.now=100.0
    def __call__(self):return self.now
    def sleep(self,d):self.now+=d


class TrialTests(unittest.TestCase):
    def test_single_jump_records_true_trajectory_and_no_midair_teleport(self):
        with tempfile.TemporaryDirectory() as tmp:
            clock=Clock()
            rcon=Mock()
            rcon.command.return_value='OK'
            runner=ArenaRunner(rcon,Path(tmp),clock=clock,sleep=clock.sleep)
            stage=built_in_stages()[1]
            # Position samples: first for spawn-reset verification, then
            # accelerate, take off, become airborne, and land on far platform.
            poses=[stage.start]+[P(x,220,20.5) for x in
                   (1.5,1.8,2.2,2.5,2.9,3.3,3.7,4.1,4.5,4.9,5.2,5.5,5.75)]+[
                   P(6.,220.35,20.5),P(6.4,220.8,20.5),P(6.8,221.,20.5),
                   P(7.2,220.85,20.5),P(7.7,220.5,20.5),P(8.4,220.,20.5)]
            calls=[0]
            def position(_):
                idx=min(calls[0],len(poses)-1)
                calls[0]+=1
                return poses[idx]
            runner.observer.position=position
            runner._grounded=lambda p: p.y == 220.
            runner._confirm_stage=lambda s: None
            ok=runner.attempt(stage,1,offset=.2)
            self.assertTrue(ok)
            cmds=[c.args[0] for c in rcon.command.call_args_list]
            self.assertTrue(any('jump once' in c for c in cmds))
            self.assertEqual(sum(c.startswith('tp ') for c in cmds),1)
            self.assertLess(cmds.index(next(c for c in cmds if c.startswith('tp '))),
                            cmds.index(next(c for c in cmds if 'jump once' in c)))
            data=[json.loads(s) for s in (Path(tmp)/'trials.jsonl').read_text().splitlines()]
            self.assertEqual(len(data),1)
            self.assertTrue(data[0]['success'])
            self.assertEqual(data[0]['source'],'minecraft')
            self.assertEqual(data[0]['gap'],2)
            self.assertGreater(len(data[0]['trajectory']),2)
            model=train_from_log(Path(tmp)/'trials.jsonl')
            self.assertEqual(model['records'],1)
            self.assertIsNone(model['groups']['2']['selected_offset'])

    def test_no_jump_does_not_pretend_model_was_trained(self):
        with tempfile.TemporaryDirectory() as tmp:
            clock=Clock();rcon=Mock();rcon.command.return_value='OK'
            runner=ArenaRunner(rcon,Path(tmp),clock=clock,sleep=clock.sleep)
            stage=built_in_stages()[0]
            runner._confirm_stage=lambda s: None
            runner.observer.position=lambda n: stage.start
            runner._grounded=lambda p: True
            self.assertFalse(runner.attempt(stage,1))
            self.assertFalse((Path(tmp)/'trials.jsonl').exists())
            episodes=[json.loads(x) for x in (Path(tmp)/'arena_episodes.jsonl').read_text().splitlines()]
            self.assertEqual(episodes[0]['reason'],'unsafe_or_missed_takeoff')

    def test_swim_and_climb_record_separately_without_jump_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            clock=Clock();rcon=Mock();rcon.command.return_value='OK'
            runner=ArenaRunner(rcon,Path(tmp),clock=clock,sleep=clock.sleep)
            runner._confirm_stage=lambda s: None
            for stage in built_in_stages()[3:]:
                seq=iter([stage.start,stage.start,stage.target])
                runner.observer.position=lambda _name,seq=seq:next(seq)
                runner._has_water=lambda p: True
                self.assertTrue(runner.attempt(stage,1))
            records=[json.loads(line) for line in (Path(tmp)/'arena_episodes.jsonl').read_text().splitlines()]
            self.assertEqual([x['skill'] for x in records],['swim','climb'])
            self.assertTrue(all(x['success'] for x in records))
            self.assertFalse((Path(tmp)/'policy.json').exists())

if __name__=='__main__':unittest.main()
