"""Regression tests: fake player name lookup must not abort autonomous training."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from quickstart.arena_training import ArenaRunner
from quickstart.observations import Position
from quickstart.training_server import training_properties


class TickClock:
    def __init__(self):
        self.now=100.0
    def __call__(self):
        return self.now
    def sleep(self,sec):
        self.now += sec


class AuthenticatedRcon:
    def __init__(self, name='VerifiedPlayer'):
        self.name=name
        self.commands=[]
    def command(self, command):
        self.commands.append(command)
        if command=='list':
            if self.name:
                return f'There are 1 of a max of 4 players online: {self.name}'
            return 'There are 0 of a max of 4 players online:'
        return 'OK'


class SpawnTests(unittest.TestCase):
    def test_authenticated_shadow_can_be_controlled(self):
        rcon=AuthenticatedRcon()
        with tempfile.TemporaryDirectory() as tmp:
            runner=ArenaRunner(rcon,Path(tmp),bot='VerifiedPlayer')
            runner._initialize_bot(Position(1.5,220,.5))
        self.assertEqual(rcon.commands,['list','player VerifiedPlayer stop'])

    def test_missing_shadow_refuses_to_start_training(self):
        rcon=AuthenticatedRcon(name='')
        with tempfile.TemporaryDirectory() as tmp:
            runner=ArenaRunner(rcon,Path(tmp),bot='VerifiedPlayer')
            with self.assertRaisesRegex(RuntimeError,'Authenticated Carpet shadow player is not connected'):
                runner._initialize_bot(Position(1.5,220,.5))
            self.assertFalse((Path(tmp)/'trials.jsonl').exists())
        self.assertFalse(any('spawn' in c for c in rcon.commands))

    def test_trainer_keeps_online_auth_and_loopback_even_if_config_tampered(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp)/'training-server-data'
            d.mkdir()
            (d/'server.properties').write_text('server-ip=0.0.0.0\nonline-mode=false\nrcon.password=my-unique-secret\n')
            props=training_properties(d)
            self.assertEqual(props['server-ip'],'127.0.0.1')
            self.assertEqual(props['online-mode'],'true')
            self.assertEqual(props['rcon.password'],'my-unique-secret')

    def test_invalid_fake_player_name_rejected_before_command_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                ArenaRunner(AuthenticatedRcon(),Path(tmp),bot='invalid;op')

if __name__=='__main__': unittest.main()

class AuthenticatedShadowTests(unittest.TestCase):
    def test_converts_only_authenticated_single_player_without_disabling_auth(self):
        from quickstart.training_server import authenticated_shadow_player
        rcon=Mock()
        calls=[]
        def response(cmd):
            calls.append(cmd)
            if cmd=='list':
                return ('There are 0 of a max of 4 players online:'
                        if calls.count('list')==1 else
                        'There are 1 of a max of 4 players online: RealOwner')
            return 'OK'
        rcon.command.side_effect=response
        clock=TickClock()
        self.assertEqual(authenticated_shadow_player(rcon,clock=clock,sleep=clock.sleep),'RealOwner')
        self.assertIn('player RealOwner shadow',calls)
        self.assertFalse(any('online-mode' in c or 'ManhuntBot spawn' in c for c in calls))

    def test_shadow_rejects_multiple_connected_players(self):
        from quickstart.training_server import authenticated_shadow_player
        rcon=Mock()
        rcon.command.return_value='There are 2 of a max of 4 players online: PersonA, PersonB'
        with self.assertRaisesRegex(RuntimeError,'exactly one'):
            authenticated_shadow_player(rcon,clock=TickClock(),sleep=lambda _:None)
        self.assertFalse(any('shadow' in c.args[0] for c in rcon.command.call_args_list))

    def test_shadow_does_not_proceed_when_no_one_joins(self):
        from quickstart.training_server import authenticated_shadow_player
        rcon=Mock()
        rcon.command.return_value='There are 0 of a max of 4 players online:'
        clock=TickClock()
        with self.assertRaisesRegex(RuntimeError,'No authenticated player joined'):
            authenticated_shadow_player(rcon,clock=clock,sleep=clock.sleep,timeout=2)
        self.assertFalse(any('shadow' in c.args[0] for c in rcon.command.call_args_list))
