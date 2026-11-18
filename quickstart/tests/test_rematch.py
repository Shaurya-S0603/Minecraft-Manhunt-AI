"""Offline tests for the v0.3 post-match lifecycle and Minecraft result overlay."""
import contextlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from quickstart.results import RoundResult, show_round_result, show_match_start
from quickstart.lobby import Lobby, parse_score
from quickstart.match import ManhuntMatch
from quickstart.observations import Position


class OverlayTests(unittest.TestCase):
    def test_victory_is_green_loss_is_red_both_have_replay_instructions(self):
        for role, winner, headline, color in [
            ('hunter', 'hunter', 'VICTORY!', 'green'),
            ('runner', 'hunter', 'DEFEAT!', 'red'),
            ('runner', 'runner', 'VICTORY!', 'green'),
            ('hunter', 'runner', 'DEFEAT!', 'red'),
        ]:
            with self.subTest(role=role,winner=winner):
                rcon=Mock()
                result=RoundResult(role, winner, 'Alex', 44, 'survival' if winner == 'runner' else 'tag')
                show_round_result(rcon, result)
                commands=[c.args[0] for c in rcon.command.call_args_list]
                self.assertTrue(any(x.startswith('title Alex times ') for x in commands))
                title=next(x for x in commands if x.startswith('title Alex title '))
                data=json.loads(title.partition(' title ')[2])
                self.assertEqual(data['text'], headline)
                self.assertEqual(data['color'], color)
                self.assertTrue(any('/trigger mh_replay' in x for x in commands))
                self.assertFalse(any(x.startswith('stop') for x in commands))

    def test_start_resets_result_overlay(self):
        rcon=Mock()
        show_match_start(rcon,'Alex','hunter')
        commands=[x.args[0] for x in rcon.command.call_args_list]
        self.assertIn('title Alex clear',commands)
        self.assertTrue(any('MANHUNT START!' in x for x in commands))

    def test_invalid_user_rejected(self):
        with self.assertRaises(ValueError):
            RoundResult('runner','runner','Alex; stop')


class LobbyTests(unittest.TestCase):
    def test_parse_score(self):
        self.assertEqual(parse_score('Alex has 1 [mh_replay]'),1)
        self.assertEqual(parse_score('Alex has 0 [mh_replay]'),0)
        self.assertIsNone(parse_score('No score for Alex'))

    def test_trigger_replay_from_minecraft(self):
        def server_response(command):
            if command.endswith('get Alex mh_replay'):
                return 'Alex has 1 [mh_replay]'
            return 'OK'
        rcon=Mock()
        rcon.command.side_effect=server_response
        lobby=Lobby(rcon)
        lobby.setup()
        lobby.prepare_player('Alex')
        action=lobby.wait_for_next_round('Alex',poll_seconds=0)
        self.assertEqual(action,'replay')
        calls=[x.args[0] for x in rcon.command.call_args_list]
        self.assertIn('scoreboard objectives add mh_replay trigger',calls)
        self.assertIn('scoreboard players enable Alex mh_replay',calls)
        self.assertFalse(any('mh_switch' in x for x in calls))
        self.assertFalse(any(x in ('stop','kill @a') for x in calls))

    def test_console_quit_intentionally_shuts_down(self):
        rcon=Mock()
        rcon.command.return_value='Alex has 0 [mh_replay]'
        lobby=Lobby(rcon)
        lobby.console_queue.put('q')
        self.assertEqual(lobby.poll_action('Alex'),'quit')

    def test_console_replay(self):
        rcon=Mock()
        rcon.command.return_value='Alex has 0 [mh_replay]'
        lobby=Lobby(rcon)
        lobby.console_queue.put('r')
        self.assertEqual(lobby.poll_action('Alex'),'replay')


class MatchCleanupTests(unittest.TestCase):
    def test_hunter_restoration_only_once_at_release(self):
        rcon=Mock()
        game=ManhuntMatch(rcon,'hunter',0,60)
        game.player='Alex'
        game.wait_for_player=Mock()
        game.setup_bot=Mock()
        game.players=lambda: ['Alex',game.bot]
        game.observer.position=lambda _: Position(3,64,2)
        game.step=Mock(return_value='hunter')
        with patch('quickstart.match.HitDetector') as detector:
            self.assertEqual(game.run(),'hunter')
            self.assertEqual(detector.return_value.reset.call_count,1)
        commands=[x.args[0] for x in rcon.command.call_args_list]
        self.assertEqual(sum(x.startswith('gamemode spectator Alex') for x in commands),1)
        self.assertEqual(sum(x.startswith('gamemode survival Alex') for x in commands),1)
        self.assertEqual(sum(x.startswith('tp Alex ') for x in commands),1)


class LauncherLifecycleTests(unittest.TestCase):
    def test_live_replay_runs_another_hunter_round_on_the_same_server(self):
        from quickstart.hunter_v1 import cli
        from quickstart.hunter_v1.game import Metrics

        proc = Mock()
        proc.poll.return_value = None
        rcon = Mock()
        rcon.command.return_value = "OK"
        match = Mock(player="Alex")
        match.players.return_value = ["Alex"]
        match.metrics = Metrics(result="hunter", reason="confirmed_hit", points={"hunter": 4, "runner": 0})
        lobby = Mock()
        lobby.poll_action.side_effect = ["replay", "quit"]
        with TemporaryDirectory() as temp:
            live = Path(temp)
            server = live / "server"
            (server / "logs").mkdir(parents=True)
            (server / "world").mkdir()
            (server / "logs" / "latest.log").write_text("Starting minecraft server version 1.21.11")
            with patch.multiple(cli, LIVE=live, local_port_open=Mock(return_value=False),
                                java_executable=Mock(return_value="java"), ensure_properties=Mock(return_value={}),
                                install_fabric=Mock(), install_mod=Mock(), eula_agreement=Mock(),
                                start_server=Mock(return_value=(proc, None)), wait_for_rcon=Mock(return_value=rcon),
                                stop_server=Mock(), HunterGame=Mock(return_value=match),
                                Lobby=Mock(return_value=lobby)), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(["play", "--runner", "Alex", "--win-mode", "hit"]), 0)
                self.assertEqual(cli.HunterGame.call_count, 2)
                self.assertTrue(all(call.kwargs["runner"] == "Alex" for call in cli.HunterGame.call_args_list))
                self.assertTrue(all(call.args[1]["game"]["win_mode"] == "hit"
                                    for call in cli.HunterGame.call_args_list))
                self.assertEqual(match.run_v1.call_count, 2)
                cli.start_server.assert_called_once()
                cli.stop_server.assert_called_once_with(proc)
            self.assertEqual(len((live / "rounds.jsonl").read_text().splitlines()), 2)

    def test_retired_role_option_is_rejected_by_both_launchers(self):
        from quickstart import launch
        from quickstart.hunter_v1 import cli

        for entry in (cli.main, lambda args: launch.main(args[1:])):
            with self.subTest(entry=entry), contextlib.redirect_stderr(io.StringIO()) as error:
                with self.assertRaises(SystemExit) as result:
                    entry(["play", "--role", "hunter"])
                self.assertEqual(result.exception.code, 2)
                self.assertIn("unrecognized arguments: --role hunter", error.getvalue())


class HistoryTests(unittest.TestCase):
    def test_writes_anonymous_rounds_with_session_score(self):
        from quickstart.history import MatchHistory
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as d:
            path=Path(d)/'rounds.jsonl'
            hist=MatchHistory(path)
            hist.record(RoundResult('hunter','hunter','Alex',33,'tag'))
            hist.record(RoundResult('runner','hunter','Alex',30,'tag'))
            self.assertEqual(hist.summary(),'You 1 | AI 1 | Rounds 2')
            records=[json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual(len(records),2)
            self.assertTrue(records[0]['victory'])
            self.assertFalse(records[1]['victory'])
            self.assertNotIn('Alex',path.read_text())
