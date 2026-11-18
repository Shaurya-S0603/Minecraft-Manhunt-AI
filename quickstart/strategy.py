"""Small, inspectable long-horizon strategy layer for the local Manhunt bot.

Design ideas: Mine AI MCP's observed-action/evidence separation and persistent notes;
Gemini Argon's explicit shared task progress and failure recovery. Neither
source supplies a compatible pretrained Manhunt policy. This module updates a
conservative *local* outcome table only from our own gameplay observations.

The game's existing 3D A* and collision/hazard checks remain authoritative.
"""
from __future__ import annotations
import json
import math
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from .observations import Position

MAX_LEAD = 3.0
SAMPLE_WINDOW = 2.5
ALTERNATIVES = {'hunter': ('direct_pursuit', 'short_intercept'),
                'runner': ('direct_escape', 'angled_escape')}


@dataclass(frozen=True)
class TacticalChoice:
    action: str
    target: Position
    reason: str


class StrategyAdvisor:
    """Goal persistence, short pursuit prediction and bounded online feedback.

    Scores evaluate *separation changes*, not actual combat wins. Selection
    is an experiment and should not be misrepresented as an RL model.
    """
    def __init__(self, role: str, root: Optional[Path] = None, enabled: Optional[bool] = None):
        if role not in ALTERNATIVES:
            raise ValueError('Unsupported Manhunt strategy role')
        self.role = role
        self.enabled = (os.environ.get('MANHUNT_STRATEGY', '1') != '0'
                        if enabled is None else bool(enabled))
        self.root = Path(root) if root is not None else Path(__file__).resolve().parents[1] / 'runtime' / 'strategy'
        # v1 did not verify that the bot moved; preserve it for audit but
        # never seed the corrected movement-verified strategy learner.
        self.store_path = self.root / f'tactical_policy_{role}_v2.json'
        self.legacy_path = self.root / f'tactical_policy_{role}.json'
        self.counters = {action: {'success': 1, 'failure': 1} for action in ALTERNATIVES[role]}
        self.trials = 0
        self._load()
        self.last_human: Optional[Position] = None
        self.last_seen_at: Optional[float] = None
        self.velocity = (0., 0.)
        self.current: Optional[TacticalChoice] = None
        self.selected_at = 0.0
        self.selection_distance = 0.0
        self.selection_bot: Optional[Position] = None
        self.skipped_stationary = 0
        self.skipped_unroutable = 0
        self.last_reported: Optional[str] = None
        self.episodes = 0

    def _load(self):
        if not self.store_path.is_file() or not self.enabled:
            return
        try:
            if self.store_path.stat().st_size > 64_000:
                return
            data = json.loads(self.store_path.read_text(encoding='utf-8'))
            if data.get('schema') != 2 or data.get('role') != self.role:
                return
            self.trials = min(int(data.get('trials', 0)), 1_000_000)
            for name in ALTERNATIVES[self.role]:
                entry = data.get('actions', {}).get(name, {})
                s, f = entry.get('success'), entry.get('failure')
                if type(s) is int and type(f) is int and 1 <= s <= 1_000_000 and 1 <= f <= 1_000_000:
                    self.counters[name] = {'success': s, 'failure': f}
        except (OSError, ValueError, TypeError, AttributeError):
            # Bad local policy must never crash Manhunt or authorize unsafe actions.
            pass

    def _save(self):
        if not self.enabled:
            return
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            payload = {'schema': 2, 'role': self.role, 'trials': self.trials,
                       'actions': self.counters,
                       'metric': 'separation change over 2.5 seconds conditional on >=0.6 blocks bot movement; not causal proof',
                       'origin': 'local_minecraft_only'}
            target = self.store_path.with_suffix('.json.tmp')
            target.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')
            os.replace(target, self.store_path)
        except OSError as exc:
            if self.last_reported != str(exc):
                print('[STRATEGY WARNING] Could not save local policy:', exc)
                self.last_reported = str(exc)

    @staticmethod
    def _distance(a: Position, b: Position) -> float:
        return math.hypot(a.x-b.x, a.z-b.z)

    def observe(self, bot: Position, human: Position, now: float):
        if not self.enabled:
            return
        if self.last_human is not None and self.last_seen_at is not None:
            dt = now - self.last_seen_at
            if .07 < dt <= 2.0:
                vx = (human.x-self.last_human.x)/dt
                vz = (human.z-self.last_human.z)/dt
                if math.isfinite(vx) and math.isfinite(vz) and math.hypot(vx, vz) <= 9:
                    self.velocity = (.6 * self.velocity[0] + .4 * vx,
                                     .6 * self.velocity[1] + .4 * vz)
                else:
                    self.velocity = (0., 0.)
            elif dt > 2.0 or dt <= 0:
                self.velocity = (0., 0.)
        self.last_human, self.last_seen_at = human, now
        if self.current is not None and now-self.selected_at >= SAMPLE_WINDOW:
            new_dist = self._distance(bot, human)
            change = (self.selection_distance-new_dist if self.role == 'hunter'
                      else new_dist-self.selection_distance)
            # Do not confuse the *human's* movement with agent competence.
            # In particular, if the navigator returned zero steps, assigning
            # repeated failures (or successes) would contaminate the policy.
            moved = (self._distance(bot,self.selection_bot)
                     if self.selection_bot is not None else 0.0)
            if moved < 0.60:
                self.skipped_stationary += 1
            elif math.isfinite(change):
                field = 'success' if change >= .4 else 'failure'
                self.counters[self.current.action][field] += 1
                self.trials += 1
                self._save()
                if self.trials % 10 == 0:
                    print(f'[STRATEGY] {self.role} observations={self.trials}; recent {field} ({change:+.2f} blocks).')
            self.current = None
            self.selection_bot = None

    def suspend_unroutable(self):
        """Discard unexecuted choices when collision-checked navigation refuses a route."""
        if self.current is not None:
            self.skipped_unroutable += 1
            self.current = None
            self.selection_bot = None

    def _preferred(self, available: tuple[str, ...]) -> str:
        # Small, bounded deterministic exploration. Never enough to bypass the
        # hard movement/terrain guards; exploratory tactics only change goals.
        if self.trials % 5 == 4 and len(available)>1:
            return min(available, key=lambda x: self.counters[x]['success'] + self.counters[x]['failure'])
        def score(name):
            count = self.counters[name]
            return count['success'] / (count['success']+count['failure'])
        return max(available, key=score)

    def _commit(self, action: str, target: Position, reason: str,
                bot: Position, human: Position, now: float) -> TacticalChoice:
        choice = TacticalChoice(action, target, reason)
        self.current = choice
        self.selected_at = now
        self.selection_distance = self._distance(bot, human)
        self.selection_bot = bot
        self.episodes += 1
        return choice

    def hunt(self, bot: Position, human: Position, now: float) -> TacticalChoice:
        if not self.enabled:
            return TacticalChoice('direct_pursuit', human, 'strategy_disabled')
        # Hold the same objective for a short window; no goal thrashing.
        if (self.current is not None and now-self.selected_at < SAMPLE_WINDOW
                and self._distance(human, self.current.target) <= 3.5
                and self._distance(bot, human) > 6):
            return self.current
        distance = self._distance(bot, human)
        vx, vz = self.velocity
        speed = math.hypot(vx, vz)
        alternatives = ('direct_pursuit',)
        # Never infer a route from predicted positions: A* verifies it later.
        if 5 <= distance <= 36 and .5 <= speed <= 7 and abs(human.y-bot.y) <= 3:
            alternatives += ('short_intercept',)
        selected = self._preferred(alternatives)
        if selected == 'short_intercept':
            lead = min(1.1, distance / max(4., 2.*speed))
            lx, lz = vx*lead, vz*lead
            scale = min(1., MAX_LEAD/max(math.hypot(lx, lz), 1e-6))
            aim = Position(human.x+lx*scale, human.y, human.z+lz*scale)
            return self._commit(selected, aim, 'bounded_velocity_prediction', bot, human, now)
        return self._commit('direct_pursuit', human, 'observed_opponent_position', bot, human, now)

    def escape(self, bot: Position, human: Position, now: float,
               baseline: Position) -> TacticalChoice:
        if not self.enabled:
            return TacticalChoice('direct_escape', baseline, 'strategy_disabled')
        if self.current is not None and now-self.selected_at < SAMPLE_WINDOW:
            return self.current
        dx, dz = bot.x-human.x, bot.z-human.z
        length = math.hypot(dx, dz)
        if length < .1:
            # Caller already knows how to handle this zero-distance case.
            return self._commit('direct_escape', baseline, 'zero_distance_baseline',bot,human,now)
        ax, az = dx/length, dz/length
        selected = self._preferred(ALTERNATIVES['runner'])
        if selected == 'angled_escape':
            # 28 degree lateral offset; component away from Hunter > 0.
            parity = -1 if self.episodes%2 else 1
            lateral = .36*parity
            vx, vz = ax-lateral*az, az+lateral*ax
            norm = math.hypot(vx, vz)
            target = Position(bot.x+16*vx/norm, bot.y, bot.z+16*vz/norm)
            return self._commit('angled_escape', target, 'escape_with_lateral_variation',bot,human,now)
        # Keep existing fixed-distance retreat as baseline, no new risky jump.
        return self._commit('direct_escape', baseline, 'existing_escape_behavior',bot,human,now)

    def status(self) -> dict:
        return {'enabled': self.enabled, 'role': self.role, 'trials': self.trials,
                'skipped_stationary': self.skipped_stationary,
                'skipped_unroutable': self.skipped_unroutable,
                'actions': {key: {**v, 'observed_success_rate': round(v['success']/(v['success']+v['failure']), 3)}
                            for key, v in self.counters.items()}}
