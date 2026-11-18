"""Regression for v8.0's nonzero head-start UnboundLocalError."""
import json
import unittest
from unittest.mock import Mock, patch

from quickstart.match import ManhuntMatch
from quickstart.observations import Position


class FakeClock:
    def __init__(self):
        self.now = 100.0

    def monotonic(self):
        return self.now

    def sleep(self, _):
        self.now += 1.0  # deterministic simulated second per main-loop iteration


class CountdownRegression(unittest.TestCase):
    def make_game(self, role):
        rcon = Mock()
        game = ManhuntMatch(rcon, role, 20, 180)
        game.player = 'Alex'
        game.wait_for_player = Mock()
        game.setup_bot = Mock()
        game.players = lambda: ['Alex', game.bot]
        game.observer.position = lambda _: Position(3, 64, 2)
        game.last_human_position = Position(3, 64, 2)
        game.last_bot_position = Position(10, 64, 2)
        return game, rcon

    def test_full_countdown_and_tracking_for_both_roles(self):
        for role in ('hunter', 'runner'):
            with self.subTest(role=role):
                game, rcon = self.make_game(role)
                clock = FakeClock()
                head_steps = []

                def step():
                    if clock.now < 120:
                        head_steps.append(clock.now)
                        return None
                    return 'hunter'

                game.step = step
                with patch('quickstart.match.time.monotonic', clock.monotonic), \
                     patch('quickstart.match.time.sleep', clock.sleep), \
                     patch('quickstart.match.HitDetector') as detector:
                    self.assertEqual(game.run(), 'hunter')
                    detector.return_value.reset.assert_called_once()
                commands = [c.args[0] for c in rcon.command.call_args_list]
                countdown = [json.loads(c.split(' actionbar ', 1)[1])['text']
                             for c in commands if c.startswith('title Alex actionbar ')]
                self.assertEqual(countdown, [f'Head start: {s}s remaining' for s in (20,15,10,5,3,2,1)])
                self.assertTrue(any('MANHUNT START!' in c for c in commands))
                if role == 'hunter':
                    self.assertEqual(len(head_steps), 20)
                    self.assertIn('gamemode spectator Alex', commands)
                    self.assertEqual(commands.count('gamemode survival Alex'), 1)
                    self.assertTrue(any(c.startswith('tellraw Alex ') and '[Tracker]' in c for c in commands))
                else:
                    self.assertFalse(head_steps)
                    self.assertFalse(any(c.startswith('gamemode spectator Alex') for c in commands))

    def test_interrupt_during_countdown_restores_hunter(self):
        game, rcon = self.make_game('hunter')
        clock = FakeClock()
        game.step = Mock(side_effect=KeyboardInterrupt)
        with patch('quickstart.match.time.monotonic', clock.monotonic), \
             patch('quickstart.match.HitDetector'):
            with self.assertRaises(KeyboardInterrupt):
                game.run()
        commands = [c.args[0] for c in rcon.command.call_args_list]
        self.assertEqual(commands.count('gamemode survival Alex'), 1)
        self.assertEqual(sum(c.startswith('tp Alex ') for c in commands), 1)


if __name__ == '__main__':
    unittest.main()
