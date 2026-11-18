"""Bounded contextual bandit. World locations influence only re-observed portals."""
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile

SCHEMA = 1


@dataclass
class Play:
    trials: int
    value: float
    last_used: int


class Playbook:
    def __init__(self, path, rules, *, read_only=False):
        self.path = Path(path)
        self.rules = rules
        self.read_only = read_only
        self.entries = {}
        self.sequence = 0
        self.load_issue = None
        if rules["enabled"] and self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if data["schema"] != SCHEMA:
                    raise ValueError("unknown schema")
                entries = {key: Play(**value) for key, value in data["plays"].items()}
                if any(type(p.trials) is not int or p.trials < 1 or
                       type(p.last_used) is not int or p.last_used < 1 or
                       not math.isfinite(p.value) or not -1 <= p.value <= 1
                       for p in entries.values()):
                    raise ValueError("invalid play record")
                self.sequence = max((p.last_used for p in entries.values()), default=0)
                self.entries = entries
                self.trim()
            except (OSError, KeyError, TypeError, ValueError, AttributeError) as exc:
                self.load_issue = str(exc)
                self.read_only = True

    @staticmethod
    def runner_key(name):
        return hashlib.sha256(name.casefold().encode()).hexdigest()[:12]

    def choose(self, context, options):
        if not self.rules["enabled"]:
            return options[0]
        available = [(name, self.entries.get(f"{context}/{name}")) for name in options]
        if self.read_only:
            measured = [(name, play.value) for name, play in available if play is not None]
            return max(measured, key=lambda pair: pair[1])[0] if measured else options[0]
        if self.rules["exploration"] > 0:
            for name, play in available:
                if play is None:
                    return name
        total = sum(play.trials for _, play in available if play)
        def score(pair):
            _, play = pair
            if play is None:
                return 0.0
            bonus = self.rules["exploration"] * math.sqrt(math.log1p(total) / play.trials)
            return play.value + bonus
        return max(available, key=score)[0]

    def reward(self, context, option, outcome):
        if not self.rules["enabled"] or self.read_only:
            return
        self.sequence += 1
        key = f"{context}/{option}"
        play = self.entries.get(key, Play(0, 0.0, 0))
        value = max(-1.0, min(1.0, outcome))
        self.entries[key] = Play(play.trials + 1,
                                 play.value + self.rules["rate"] * (value - play.value),
                                 self.sequence)
        self.trim()

    def trim(self):
        excess = len(self.entries) - self.rules["max_entries"]
        if excess > 0:
            oldest = sorted(self.entries, key=lambda key: self.entries[key].last_used)
            for key in oldest[:excess]:
                del self.entries[key]

    def save(self):
        if not self.rules["enabled"] or self.read_only:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schema": SCHEMA, "plays": {key: vars(value) for key, value in self.entries.items()}}
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent,
                                         delete=False) as stream:
            temp = Path(stream.name)
            try:
                json.dump(payload, stream, indent=2, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
                stream.close()
                os.replace(temp, self.path)
            finally:
                temp.unlink(missing_ok=True)


class RouteMemory:
    """Keep successful and stalled local edges; the planner rechecks terrain."""
    def __init__(self, book, scope):
        self.book = book
        self.scope = scope
        self.reset()

    def reset(self, dimension=None):
        self.context = f"route/{self.scope}/{dimension}"
        self.edge = None

    @staticmethod
    def key(source, target):
        return f"{','.join(map(str, source))}>{','.join(map(str, target))}"

    def penalty(self, source, target):
        entry = self.book.entries.get(f"{self.context}/{self.key(source, target)}")
        return max(0.0, -entry.value) * .75 if entry and entry.trials >= 2 else 0.0

    def observe(self, source, target, grounded, now):
        if self.edge:
            a, b, since = self.edge
            if source == b and grounded:
                self.book.reward(self.context, self.key(a, b), 1)
                self.edge = None
            elif source == a and target == b and now - since > 2.4:
                self.book.reward(self.context, self.key(a, b), -1)
                self.edge = None
            elif target != b or (source != a and source != b):
                self.edge = None
        # Persist unusual segments and stalls. Ordinary every-block walking
        # would crowd out tactics in the bounded store without adding signal.
        if self.edge is None and target is not None and source != target:
            if sum(abs(a-b) for a, b in zip(source, target)) >= 2:
                self.edge = (source, target, now)
