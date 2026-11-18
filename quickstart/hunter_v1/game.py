"""Online round supervisor and priority loop over the existing Carpet executor."""
from dataclasses import dataclass, field
import math
import time

from ..hit_detection import APP as HIT_APP, HitDetector
from ..live_skill_policy import LiveSkillPolicy
from ..lobby import parse_score
from ..match import ManhuntMatch, command_ok
from ..movement_training import DATA_ROOT, MovementTrainer
from ..observations import validate_name
from ..results import show_match_start
from ..terrain import TerrainUnavailable
from ..v8_config import load_config
from ..v8_inventory import InventoryMonitor
from .bridge import Bridge
from .director import HuntDirector, round_score
from .inventory import archive_snapshot, round_inventory_events
from .recipes import counts
from .learning import Playbook, RouteMemory
from .pursuit import Compass, Pursuit
from .supply import Supply, cell
from .traverse import Builder, Climber, Portals

DEATHS = "mh_v1_deaths"
ADVANCEMENTS = (
    ("dragon", "minecraft:end/kill_dragon"),
    ("end", "minecraft:end/root"),
    ("stronghold", "minecraft:story/follow_ender_eye"),
    ("nether", "minecraft:nether/root"),
)


@dataclass
class Metrics:
    result: str = "aborted"
    reason: str = "interrupted"
    duration_s: float = 0.
    first_hit_s: float | None = None
    blocks_traveled: float = 0.
    min_visible_separation: float | None = None
    runner_stage: str = "overworld"
    hunter_deaths: int = 0
    respawns: int = 0
    blocks_placed: int = 0
    bridges_crossed: int = 0
    climbs_completed: int = 0
    portal_transitions: int = 0
    navigation_plans: int = 0
    terrain_failures: int = 0
    items_picked_up: dict | None = None
    items_crafted: dict = field(default_factory=dict)
    inventory_events: dict = field(default_factory=dict)
    human_role: str = "runner"
    opening_policy: str = "learned"
    opening: str | None = None
    opening_context: str | None = None
    opening_reward: float | None = None
    points: dict = field(default_factory=dict)


class HunterGame(ManhuntMatch):
    def __init__(self, rcon, settings, world_dir, data_dir, scope, *, runner=None, held_out=False, policy="learned"):
        old_config = load_config()
        old_config["inventory"]["enabled"] = False
        rules = settings["game"]
        super().__init__(rcon, "runner", rules["head_start_seconds"],
                         rules["time_limit_seconds"], old_config)
        self.settings = settings
        self.world_dir = world_dir
        self.data_dir = data_dir
        self.requested_runner = validate_name(runner) if runner else None
        self.water.rescue_effect = False
        # Consume certified physical settings from the existing trainer, without
        # updating its checkpoint or enabling its exploratory match mode.
        skill_root = data_dir / "movement_training" if held_out else DATA_ROOT
        self.training = MovementTrainer(root=skill_root, practice=False)
        self.training.enabled = False
        self.live_skills = LiveSkillPolicy(skill_root / "skill_policy.json")
        self.bridge = Bridge(rcon, self.bot)
        self.book = Playbook(data_dir / "playbook.json", settings["learning"], read_only=held_out)
        self.director = HuntDirector(self.book, settings["learning"], rules["win_mode"], policy)
        self.routes = RouteMemory(self.book, scope)
        self.pathfinder.edge_penalty = self.routes.penalty
        self.compass = Compass(settings["tracking"])
        self.builder = Builder(self)
        self.climber = Climber(self)
        self.portals = Portals(self, self.book, scope)
        self.supply = Supply(self)
        self.metrics = Metrics(opening_policy=policy)
        self.grounded = False
        self.last_dim = None
        self.previous = None
        self.warning_at = -math.inf
        self.initial_spawn = None
        self.respawn_at = None
        self.respawn_deadline = None
        self.stage_at = -math.inf
        self.portal_search = None
        self.portal_search_since = None
        self.hunter_deaths = 0
        self.bot_missing_since = None

    def wait_for_player(self):
        if not self.requested_runner:
            return super().wait_for_player()
        print(f"[JOIN] Waiting for human runner {self.requested_runner} on the local server")
        while self.requested_runner not in self.players():
            time.sleep(1)
        self.player = self.requested_runner

    def _death(self, name):
        response = self.rcon.command(f"scoreboard players get {name} {DEATHS}")
        score = parse_score(response)
        event_count = int(self.bridge.query(f"mh_deaths('{validate_name(name)}')", at=False))
        # Carpet can remove a fake player's connection before the vanilla
        # scoreboard criterion has incremented. Keep the native event too.
        return max(score or 0, event_count)

    def _advancement(self, advancement):
        # The query divulges progress only. Coordinates are handled separately.
        selector = f"@a[name={self.player},advancements={{{advancement}=true}},limit=1]"
        response = self.rcon.command(f"execute if entity {selector}")
        if "Test passed" in response:
            return True
        if "Test failed" in response:
            return False
        raise RuntimeError(f"Unexpected advancement response: {response[:140]}")

    def _progress(self, now):
        if now < self.stage_at:
            return
        self.stage_at = now + 2.5
        for stage, advancement in ADVANCEMENTS:
            if self._advancement(advancement):
                order = ("overworld", "nether", "stronghold", "end", "dragon")
                if order.index(stage) > order.index(self.metrics.runner_stage):
                    self.metrics.runner_stage = stage
                break

    def _stop_controls(self):
        self.builder.cancel()
        self.climber.cancel()
        self.supply.cancel(time.monotonic())
        self.miner.stop()
        self.stop()
        self.invalidate_route()

    def _switch_dimension(self, new_dim):
        self._stop_controls()
        self.sensor.cache.clear()
        self.pathfinder.clear()
        self.navigator.clear()
        self.motion.samples.clear()
        self.water.reset()
        self.surface_goal = None
        self.airborne = False
        self.previous = None
        self.grounded = False
        self.supply.blocked.clear()
        self.pursuit.reset()
        self.compass.reset()
        self.routes.reset(new_dim)
        self.failed_routes = 0
        self.last_bot_position = None
        self.portals.next_scan = 0.
        if self.last_dim is not None:
            self.portals.crossed(self.last_dim, new_dim)
            print(f"[PORTAL] Hunter entered {new_dim}")
        self.last_dim = new_dim

    def _respawn(self, now, bot_online):
        if self.respawn_at is None:
            return False
        if self.respawn_deadline is not None:
            if bot_online:
                self.respawn_deadline = self.respawn_at = None
                self.metrics.respawns += 1
                self.last_dim = None
                self._switch_dimension(self.initial_spawn[0])
                self.inventory.initialized = False
                return False
            if now > self.respawn_deadline:
                raise RuntimeError("Carpet did not respawn the hunter. Check the server profile lookup log.")
            return True
        if now < self.respawn_at or bot_online:
            return True
        dimension, spot = self.initial_spawn
        text = self.rcon.command(f"execute in {dimension} positioned {spot.x:.3f} {spot.y:.3f} {spot.z:.3f} "
                                 f"run player {self.bot} spawn in survival")
        if not command_ok(text):
            raise RuntimeError(f"Carpet rejected hunter respawn: {text[:160]}")
        self.respawn_deadline = now + 12
        return True

    def _surface(self, bot, now):
        vertical = 0
        if self.path and self.path_index < len(self.path):
            step = self.path[self.path_index]
            if step.swimming:
                dy = step.destination.y - bot.y
                vertical = (1 if dy > .55 else -1 if dy < -.55 else 0)
        immersed = self.water.update(bot, now, stop_movement=self.stop, vertical=vertical)
        if immersed and self.water.stall_detected:
            if self.path and self.path_index < len(self.path):
                self.pathfinder.penalize(self.path[self.path_index].destination, seconds=6)
            self.invalidate_route()
            self.live_skills.disable("swim", "physical stall in water")
        if not immersed:
            self.surface_goal = None
        if immersed and self.water.head_submerged and (
                self.water.last_air < 165 or now - self.water.entered_at > 9):
            self.builder.cancel()
            self.climber.cancel()
            self.supply.cancel(now)
            self.pursuit.reset()
            if self.surface_goal is None or now - self.surface_goal_at > 2:
                self.surface_goal = (self.surface_planner.find_air(bot) or
                                     self.surface_planner.ascend_waypoint(bot))
                self.surface_goal_at = now
            if self.surface_goal:
                self.navigate(bot, self.surface_goal, now)
            else:
                self.halt_movement()
            return True
        return False

    def _set_cross_dimension_goal(self, bot, now):
        if self.portal_search_since is None:
            self.portal_search_since = now
            self.portal_search = self.compass.last_visible
        if self.portal_search and now - self.portal_search_since <= 20 and bot.distance(self.portal_search) > 1:
            self.navigate(bot, self.portal_search, now)
        else:
            self.halt_movement()

    def tick_v1(self, bot_state, runner_state, now, elapsed):
        dimension, _, hunger, _, grounded, bot = bot_state
        active_runner = (runner_state and runner_state[1] in {"survival", "adventure"}
                         and runner_state[3] > 0)
        runner_dim = runner_state[0] if active_runner else None
        runner = runner_state[-1] if active_runner and runner_dim == dimension else None
        if self.last_dim != dimension:
            self._switch_dimension(dimension)
        self.grounded = grounded
        if self.previous:
            displacement = bot.distance(self.previous)
            if displacement < 24:
                self.metrics.blocks_traveled += displacement
        self.previous = bot
        self.last_bot_position = bot
        self.motion.observe(bot, now)
        self.inventory.snapshot()
        if self._surface(bot, now):
            self.routes.reset(dimension)
            return

        if runner_dim is None:
            self._stop_controls()
            return
        guide = self.compass.observe(bot, runner, now, self.sensor)
        visible = guide.visible if guide else None
        dist = bot.distance(visible) if visible is not None else math.inf
        if visible is not None:
            old_dist = self.metrics.min_visible_separation
            self.metrics.min_visible_separation = dist if old_dist is None else min(old_dist, dist)
            self.portals.observe(dimension, bot, visible, now)
        crossed = runner_dim != dimension
        if crossed:
            self.builder.cancel()
            self.climber.cancel()
        elif self.climber.tick(bot, now) or (self.builder.job and self.builder.job.kind == "pillar"
                                              and self.builder.tick(bot, now)):
            return
        if dist <= 2.8:
            self.builder.cancel()
            self.supply.cancel(now)
            self.miner.stop()
            if now - self.last_attack >= .8:
                self.supply.hold_weapon()
                self.attack_human(bot, visible, now)
            return

        if not crossed and self.builder.tick(bot, now):
            return
        if crossed:
            self.pursuit.reset()
            self.supply.cancel(now)
            if self.portals.follow(dimension, runner_dim, bot, now):
                return
        else:
            self.portal_search = self.portal_search_since = None
            self.portals.entered = None
        rules = self.settings["resources"]
        safe_to_gather = (dist > rules["safe_distance"] and grounded and not self.water.swimming
                          and (not self.miner.operation or self.supply.harvest is not None))
        if not crossed and self.metrics.runner_stage in {"stronghold", "end"} and hunger > 12:
            safe_to_gather = False
        # Allow limited provisioning even while following a distant compass
        # bearing. Release the movement budget to the chase on every cycle.
        if self.director.action is None and guide is not None:
            inv = counts(self.inventory.slots) if self.inventory.available else None
            if inv is not None:
                self.director.start(elapsed, inv, hunger, rules["enabled"] and rules["crafting"])
        gearing_up = self.director.action == "gear" and self.director.in_opening(elapsed)
        if (guide or crossed) and elapsed % 30 >= 9 and hunger > 8 and not gearing_up:
            safe_to_gather = False
        if not crossed and not self.director.allows_supply(elapsed, hunger):
            safe_to_gather = False
        if self.supply.tick(bot, hunger, now, safe=safe_to_gather, portal_needed=crossed):
            self.routes.reset(dimension)
            self.pursuit.reset()
            return
        if crossed:
            self._set_cross_dimension_goal(bot, now)
            return
        if guide is None:
            self.pursuit.reset()
            self.halt_movement()
            return
        target = self.pursuit.goal(bot, guide, dimension, now)
        if self.climber.start(bot, target, now):
            self.pursuit.reset()
            return
        waypoint = (cell(self.path[self.path_index].destination)
                    if self.path and self.path_index < len(self.path) else None)
        self.routes.observe(cell(bot), waypoint, grounded, now)
        blocked = (self.failed_routes >= 1 and (self.detour_active or self.path_index >= len(self.path)))
        high_goal = target.y - bot.y >= 2 and math.hypot(bot.x - target.x, bot.z - target.z) < 1.8
        wet_ahead = rules["water_bridge"] and any(
            step.swimming and bot.distance(step.destination) < 1.75
            for step in self.path[self.path_index:self.path_index + 2]
        )
        if blocked or high_goal or wet_ahead:
            if self.builder.start(bot, target, now):
                self.pursuit.reset()
                return
        self.navigate(bot, target, now)

    def run_v1(self, driver=None):
        self.wait_for_player()
        self.pursuit = Pursuit(self.book, self.player)
        if self.book.load_issue:
            print(f"[LEARNING] Existing playbook was preserved. Updates disabled: {self.book.load_issue}")
        if self.settings["game"]["win_mode"] == "dragon" and self._advancement(ADVANCEMENTS[0][1]):
            raise RuntimeError("Runner already has Free the End. Start dragon mode in a fresh world.")
        self.setup_bot()
        self.inventory = InventoryMonitor(self.rcon, self.bot, self.data_dir / "inventory", poll_seconds=.7,
                                          persist=False)
        self.inventory.snapshot(force=True)
        self.bridge.install(self.world_dir)
        if (self.world_dir / "scripts" / f"{HIT_APP}.sc").exists():
            self.rcon.command(f"script unload {HIT_APP}")
        self.hit_detector = HitDetector(self.rcon, self.world_dir, self.player, self.bot)
        self.hit_detector.setup()
        self.rcon.command(f"scoreboard objectives add {DEATHS} deathCount")
        for name in (self.bot, self.player):
            self.rcon.command(f"scoreboard players set {name} {DEATHS} 0")
            self._death(name)
        initial_state = self.bridge.state(self.bot)
        if initial_state is None:
            raise RuntimeError("Hunter entity missing after setup")
        self.initial_spawn = (initial_state[0], initial_state[-1])
        if initial_state[0] != "minecraft:overworld":
            raise RuntimeError("Start the round with the runner on safe terrain in the Overworld")
        print(f"[HEAD START] {self.head_start}s. Hunter tags score after release.")
        start = None
        try:
            head_start_at = time.monotonic()
            while time.monotonic() - head_start_at < self.head_start:
                if driver:
                    driver.tick()
                time.sleep(.10)
            self.hit_detector.reset()
            show_match_start(self.rcon, self.player, "runner")
            start = time.monotonic()
            while True:
                if driver:
                    driver.tick()
                now = time.monotonic()
                elapsed = now - start
                connected = self.players()
                # Death counters remain readable after a Carpet fake player is removed.
                runner_deaths = self._death(self.player)
                hunter_deaths = self._death(self.bot)
                hit = self.hit_detector.hunter_hit("runner")
                if hit and self.metrics.first_hit_s is None:
                    self.metrics.first_hit_s = elapsed
                    if self.previous:
                        self.pursuit.finish(self.previous, 0, caught=True)
                mode = self.settings["game"]["win_mode"]
                self.metrics.hunter_deaths = hunter_deaths
                self._progress(now)
                if mode == "hit" and hit:
                    self.metrics.result, self.metrics.reason = "hunter", "confirmed_hit"
                    break
                if runner_deaths:
                    self.metrics.result = "hunter" if mode == "dragon" else "aborted"
                    self.metrics.reason = "runner_death"
                    break
                if mode == "dragon" and self.metrics.runner_stage == "dragon":
                    self.metrics.result, self.metrics.reason = "runner", "dragon_advancement"
                    break
                if self.player not in connected:
                    self.metrics.reason = "runner_disconnected"
                    break
                if elapsed >= self.survival_seconds:
                    self.metrics.result, self.metrics.reason = "runner", "timeout"
                    break
                if hunter_deaths > self.hunter_deaths:
                    self.hunter_deaths = hunter_deaths
                    self.previous = None
                    self._stop_controls()
                    if hunter_deaths > self.settings["game"]["hunter_respawns"]:
                        self.metrics.result, self.metrics.reason = "runner", "hunter_respawns_exhausted"
                        break
                    self.respawn_at = now + self.settings["game"]["respawn_seconds"]
                    print(f"[DEATH] Hunter will respawn in {self.settings['game']['respawn_seconds']}s")
                if self._respawn(now, self.bot in connected):
                    time.sleep(.18)
                    continue
                if self.bot not in connected:
                    if self.bot_missing_since is None:
                        self.bot_missing_since = now
                    if now - self.bot_missing_since < 1.5:
                        time.sleep(.15)
                        continue
                    self.metrics.reason = "hunter_disconnected"
                    break
                self.bot_missing_since = None
                try:
                    bot_state = self.bridge.state(self.bot)
                    human_state = self.bridge.state(self.player)
                    if bot_state and bot_state[3] > 0:
                        self.tick_v1(bot_state, human_state, now, elapsed)
                except TerrainUnavailable as exc:
                    self.metrics.terrain_failures += 1
                    self._stop_controls()
                    if now >= self.warning_at:
                        print("[SENSOR]", exc)
                        self.warning_at = now + 6
                    time.sleep(.15)
                delay = .055 if self.builder.active else self.movement_tick_delay()
                time.sleep(delay)
            return self.metrics
        finally:
            if start is not None:
                self.metrics.duration_s = time.monotonic() - start
            try:
                self._stop_controls()
                self.metrics.items_picked_up = self._pickups()
            except (OSError, RuntimeError, ValueError) as exc:
                print("[ROUND] Cleanup or pickup metrics unavailable:", exc)
            try:
                self.metrics.inventory_events = round_inventory_events(self.bridge)
                if self.bot in self.players():
                    archive_snapshot(self.data_dir / "inventory" / "latest.json", self.bridge, self.bot)
            except (OSError, RuntimeError, ValueError) as exc:
                print("[INVENTORY] Audit unavailable:", exc)
            self.metrics.items_crafted = dict(self.supply.crafted)
            self.metrics.blocks_placed = self.builder.placed
            self.metrics.bridges_crossed = self.builder.crossed
            self.metrics.climbs_completed = self.climber.completed
            self.metrics.portal_transitions = self.portals.transitions
            self.metrics.navigation_plans = self.path_replans
            self.metrics.terrain_failures += self.nav_failures
            self.metrics.opening = self.director.action
            self.metrics.opening_context = self.director.context
            self.metrics.opening_reward = self.director.finish(self.metrics)
            self.metrics.points = round_score(self.metrics, self.settings["scoring"])
            if self.metrics.result in {"hunter", "runner"}:
                try:
                    self.book.save()
                except OSError as exc:
                    print("[LEARNING] Could not save playbook:", exc)

    def _pickups(self):
        payload = self.bridge.query("mh_pickups()", at=False)
        return {item: int(count) for item, count in (record.split("=") for record in payload.split("|") if record)}
