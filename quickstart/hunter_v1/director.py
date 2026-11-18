"""A match-level contextual bandit over legal Hunter openings."""

from .recipes import WEAPONS


class HuntDirector:
    """One decision per round so complete outcomes have clear credit.

    This changes whether provisioning may take control during the opening.
    It never issues movement, changes inventory, or bypasses safety gates.
    """
    def __init__(self, book, rules, mode, policy="learned"):
        self.book = book
        self.rules = rules
        self.mode = mode
        self.policy = policy
        self.action = None
        self.context = None
        self.learnable = False
        self.started = 0.

    def start(self, elapsed, inventory, hunger, resources_enabled):
        if self.action is not None:
            return
        self.started = elapsed
        needs_gear = hunger <= 10 or not any(inventory[name] for name in WEAPONS)
        if self.policy == "baseline" or not self.rules["enabled"]:
            self.action = "baseline"
        elif not resources_enabled or not needs_gear:
            self.action = "press"
        elif self.policy in {"press", "gear"}:
            self.action = self.policy
        else:
            readiness = "low_food" if hunger <= 10 else "unarmed"
            self.context = f"opening/{self.mode}/{readiness}"
            self.action = self.book.choose(self.context, ("press", "gear"))
            self.learnable = True
        print(f"[TACTICS] Opening: {self.action}")

    def in_opening(self, elapsed):
        return self.action is not None and elapsed - self.started < self.rules["opening_seconds"]

    def allows_supply(self, elapsed, hunger):
        """Critical hunger can always trigger the existing safe supply policy."""
        if self.action != "press" or hunger <= 8:
            return True
        return not self.in_opening(elapsed)

    def finish(self, metrics):
        if not self.learnable or metrics.result not in {"hunter", "runner"}:
            return None
        horizon = self.rules["tag_bonus_seconds"]
        time_to_tag = metrics.first_hit_s
        tag_reward = 0.0 if time_to_tag is None else .30 * max(0., 1. - time_to_tag / horizon)
        outcome = .70 if metrics.result == "hunter" else -.70
        value = round(max(-1., min(1., outcome + tag_reward - .10 * metrics.hunter_deaths)), 4)
        self.book.reward(self.context, self.action, value)
        return value


def round_score(metrics, scoring):
    if metrics.result not in {"hunter", "runner"}:
        return {}
    points = {role: scoring["win"] if metrics.result == role else scoring["loss"]
              for role in ("hunter", "runner")}
    if metrics.first_hit_s is not None:
        points["hunter"] += scoring["first_tag"]
    return points
