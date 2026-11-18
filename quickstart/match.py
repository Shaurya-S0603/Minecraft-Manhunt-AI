"""Carpet fake-player Manhunt: verified hits, terrain-aware swim and mining."""
from __future__ import annotations
import math
import random
import time
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ai-controller' / 'src'))
from manhunt_ai.core.decision_loop import DecisionLoop
from manhunt_ai.core.observation import Observation
from .observations import Observer, Position, parse_player_list, validate_name
from .results import show_match_start, component
from .terrain import TerrainSensor, LocalNavigator, TerrainUnavailable
from .pathfinding3d import BoundedAStar, AirborneTransition
from .waypoint_following import reached_waypoint
from .safe_spawn import SafeSpawnFinder
from .hit_detection import HitDetector, HitDetectionError
from .swimming import WaterSurvival
from .block_breaking import BlockBreaker
from .combat import attack_line_clear
from .underwater import SurfacePlanner
from .movement_training import MovementTrainer
from .jump_control import VelocityTracker, SprintJumpController, JumpCorridor
from .waterdrop import WaterDropPlanner
from .terrain import terrain_type
from .live_skill_policy import LiveSkillPolicy
from .strategy import StrategyAdvisor
from .install import SERVER

BOT_NAME = 'ManhuntBot'


def command_ok(response: str) -> bool:
    lower = response.lower()
    return not any(phrase in lower for phrase in (
        'unknown or incomplete command', 'unknown command', 'incorrect argument',
        'no player was found', 'could not find', 'not allowed', 'unknown player',
    ))


class ManhuntMatch:
    def __init__(self, rcon, role: str, head_start: int = 20, survival_seconds: int = 180):
        if role not in ('hunter', 'runner'):
            raise ValueError('Role must be hunter or runner')
        if not 0 <= head_start <= 300 or not 15 <= survival_seconds <= 86400:
            raise ValueError('Invalid match durations')
        self.rcon, self.role = rcon, role
        self.ai_role = 'runner' if role == 'hunter' else 'hunter'
        self.brain = DecisionLoop(BOT_NAME, self.ai_role)
        self.strategy = StrategyAdvisor(self.ai_role)
        self.head_start, self.survival_seconds = head_start, survival_seconds
        self.observer = Observer(rcon)
        self.bot = BOT_NAME
        self.player = None
        self.moving = False
        self.attacking = False
        self.target = None
        self.last_bot_position = None
        self.last_progress = time.monotonic()
        self.last_jumped = 0.0
        self.random = random.Random()
        self.result_reason = None
        self.game_duration = 0.0
        self.hunter_was_spectator = False
        self.sensor = TerrainSensor(rcon)
        self.navigator = LocalNavigator(self.sensor)
        self.pathfinder = BoundedAStar(self.sensor)
        self.spawn_finder = SafeSpawnFinder(self.sensor)
        self.water = WaterSurvival(rcon, self.sensor, self.bot)
        self.surface_planner = SurfacePlanner(self.sensor)
        self.water_drop_planner = WaterDropPlanner(self.sensor)
        self.training = MovementTrainer()
        self.live_skills = LiveSkillPolicy(self.training.root / "skill_policy.json")
        self.motion = VelocityTracker()
        self.jump_controller = SprintJumpController()
        self.jump_corridor = JumpCorridor(self.sensor)
        self.jump_preflight_key = None
        self.pathfinder.max_gap = self.training.allowed_gap
        self.water_drop_active = False
        self.surface_goal = None
        self.surface_goal_at = 0.0
        self.sprinting = False
        self.climbing = False
        self.climb_key = None
        self.jump_key = None
        self.miner = BlockBreaker(rcon, self.sensor, self.bot)
        self.hit_detector = None
        self.last_attack = 0.0
        self.failed_routes = 0
        self.path = ()
        self.path_index = 0
        self.path_start = None
        self.waypoint_key = None
        self.waypoint_best_distance = float("inf")
        self.path_goal = None
        self.path_created_at = 0.0
        self.path_attempts = 0
        self.path_replans = 0
        self.spawn_retries = 0
        self.last_route_at = 0.0
        self.route = None
        self.recovery_until = 0.0
        self.last_recovery_at = 0.0
        self.recovery_attempts = 0
        self.warned_sensor = False
        self.nav_samples = 0
        self.nav_failures = 0
        self.sensor_retry_at = 0.0
        self.sensor_confirmed = False
        self.airborne = False
        self.airborne_since = 0.0
        self.last_jump_command_at = -1000.0
        # No-route recovery is distinct from physical stuck recovery: a bot
        # that has halted cannot trigger the moving-only stuck detector.
        self.empty_route_scans = 0
        self.detour_routes = 0
        self.detour_active = False
        self.detour_recent: dict[tuple[int,int,int],float] = {}
        self.detour_budget_start = 0.0
        self.detour_budget_goal: Position | None = None
        self.detour_budget_used = 0
        self.detour_exhausted_reported = False

    def players(self) -> list[str]:
        return parse_player_list(self.rcon.command('list'))

    def wait_for_player(self):
        print('\n[JOIN] Open Minecraft Java Edition 1.21.11 and join Multiplayer > Direct Connection > localhost:25565')
        print('[JOIN] Waiting for your Minecraft player. Press Ctrl+C to exit.')
        while True:
            others = [p for p in self.players() if p.lower() != self.bot.lower()]
            if others:
                self.player = validate_name(others[0])
                print(f'[JOIN] Human player detected: {self.player}')
                return
            time.sleep(2)

    def setup_bot(self):
        # The old v0.4 fixed ~5 ~ ~5 offset could be inside tree trunks,
        # caves or terrain at a very different height. Never use it here.
        self.sensor.at_entity = self.player  # sample in the human's dimension
        self.sensor.cache.clear()
        print('[SPAWN] Searching for a dry, naturally open 3x3 area near the human player...')
        while True:
            try:
                human = self.observer.position(self.player)
                spot = self.spawn_finder.find(human)
                break
            except TerrainUnavailable as exc:
                self.spawn_retries += 1
                print('[SPAWN WARNING]', exc)
                if self.spawn_retries == 1:
                    self.rcon.command(f'tellraw {self.player} {component("[Manhunt] Move onto open, level terrain to allow safe AI spawn.", "yellow")}')
                print('[SPAWN] Not risking suffocation. Move the human player to open land; retrying in 5 seconds. Ctrl+C exits.')
                time.sleep(5)
        x,y,z = spot.position.x,spot.position.y,spot.position.z
        print(f'[SPAWN] Validated open 3x3 at {x:.1f}, {y:.0f}, {z:.1f} ({spot.distance:.1f} blocks away).')
        if self.bot in self.players():
            self.rcon.command(f'player {self.bot} stop')
            result = self.rcon.command(f'execute at {self.player} run tp {self.bot} {x:.2f} {y:.2f} {z:.2f}')
        else:
            cmd = f'execute at {self.player} positioned {x:.2f} {y:.2f} {z:.2f} run player {self.bot} spawn in survival'
            result = self.rcon.command(cmd)
            if not command_ok(result):
                raise RuntimeError('Carpet fake-player spawn failed: ' + result)
            for _ in range(20):
                if self.bot in self.players():
                    break
                time.sleep(0.5)
            else:
                raise RuntimeError('ManhuntBot did not appear in /list. Check Carpet 1.21.11.')
        if not command_ok(result):
            raise RuntimeError('Could not move ManhuntBot to validated spawn: ' + result)
        self.rcon.command(f'player {self.bot} stop')
        # Verify the real in-game result, rather than trusting command success.
        self.sensor.at_entity = self.bot
        self.sensor.cache.clear()
        time.sleep(0.25)
        actual = self.observer.position(self.bot)
        if not self.spawn_finder.verify(actual):
            # No blind continuation on a failed position/terrain verification.
            # The area itself remains unchanged; this is a safe stop.
            self.rcon.command(f'player {self.bot} stop')
            raise RuntimeError('AI appeared in unsafe terrain after spawn; navigation disabled. Check spawn logs.')
        self.last_bot_position = None
        self.target = None
        self.navigator.clear()
        self.water.reset()
        self.live_skills.reload()
        print(f"[SKILL] Live movement settings: {self.live_skills.status()}")
        self.miner.stop()
        self.failed_routes = 0
        self.surface_goal = None
        self.water_drop_active = False
        self.sprinting = False
        self.climbing = False
        self.climb_key = None
        self.jump_key = None
        self.airborne = False
        self.airborne_since = 0.0
        self.last_jump_command_at = -1000.0
        self.pathfinder.clear()
        self.path = ()
        self.path_index = 0
        self.path_start = None
        self.waypoint_key = None
        self.waypoint_best_distance = float("inf")
        self.path_goal = None
        self.route = None
        self.detour_active = False
        self.detour_recent.clear()
        self.detour_budget_start = 0.0
        self.detour_budget_goal = None
        self.detour_budget_used = 0
        self.detour_exhausted_reported = False
        self.last_route_at = 0.0
        self.last_progress = time.monotonic()
        print('[SPAWN] Verified AI has safe ground and three clear blocks of headroom.')
        print('[BOT] ManhuntBot is in the world.')

    def stop(self):
        if hasattr(self, "water"):
            # /player stop cancels held jump/sneak as well. Reassert the
            # desired swim input on the next tick without losing air history.
            self.water.vertical_mode = None
        try:
            self.rcon.command(f'player {self.bot} stop')
        except Exception:
            pass
        self.moving = False
        self.attacking = False
        self.sprinting = False
        self.climbing = False

    def set_sprinting(self, active: bool):
        if active == self.sprinting:
            return
        result=self.rcon.command(f'player {self.bot} {"sprint" if active else "unsprint"}')
        if not command_ok(result):
            raise RuntimeError('Carpet sprint control failed: '+result)
        self.sprinting=active

    def climb_move(self, bot: Position, destination: Position):
        """Press into an observed wall bearing ladder/vines and ascend."""
        x,y,z=math.floor(bot.x),math.floor(bot.y),math.floor(bot.z)
        cells=[(x+dx,y,z+dz) for dx,dz in ((1,0),(-1,0),(0,1),(0,-1))]
        # The training arena is a ladder course. Only transfer its learned
        # aim height when an actual ladder is observed by the fake player.
        # Vines, scaffolding and unsupported surfaces use legacy controls.
        climb_cells=list(dict.fromkeys(cells + [(x,y,z)] +
                                           [(cx,y+1,cz) for cx,_,cz in cells] +
                                           [(x,y+1,z)]))
        blocks=self.sensor.read(climb_cells)
        ladder_nearby=any(blocks[cell]=='ladder' for cell in climb_cells)
        walls=[cell for cell in cells if terrain_type(blocks[cell])=='solid']
        if not walls:
            self.halt_movement()
            print('[CLIMB WARNING] No observed attachment wall; cannot climb blindly.')
            return
        wall=min(walls,key=lambda cell: (cell[0]+.5-bot.x)**2+(cell[2]+.5-bot.z)**2)
        if not self.climbing:
            self.stop()
            self.set_sprinting(False)
            self.climbing=True
            learned_height=(self.live_skills.value('climb') if ladder_nearby and
                            destination.y >= bot.y else None)
            aim_height=learned_height if learned_height is not None else 1.5
            self.rcon.command(f'player {self.bot} look at {wall[0]+.5:.2f} {bot.y+aim_height:.2f} {wall[2]+.5:.2f}')
            if learned_height is not None:
                print(f'[SKILL] Learned ladder aim +{aim_height:.2f} blocks applied.')
            if destination.y >= bot.y:
                self.rcon.command(f'player {self.bot} jump continuous')
            else:
                self.rcon.command(f'player {self.bot} sneak')
            self.rcon.command(f'player {self.bot} move forward')
            self.moving=True
            print('[CLIMB] Holding onto observed vine/ladder wall.')

    def look_and_move(self, dest: Position):
        pos = self.observer.position(self.bot)
        # Swim towards the actual waypoint depth. Walking still uses level
        # pitch; otherwise fake players cannot make horizontal swim progress.
        look_y = dest.y+0.5 if self.water.swimming else pos.y+1.6
        # Arena 'swim_horizontal' trained a small look-target offset. Do not
        # transfer it to dives, ascents or emergency surfacing: those use the
        # proven vertical/air-availability controls and must override a model.
        if (self.water.swimming and self.water.vertical_mode == 0 and
                self.water.last_air >= 165 and self.surface_goal is None):
            bias=self.live_skills.value('swim')
            if bias is not None:
                look_y=dest.y+0.7+bias
        command = f'player {self.bot} look at {dest.x:.2f} {look_y:.2f} {dest.z:.2f}'
        look_result = self.rcon.command(command)
        if not command_ok(look_result):
            raise RuntimeError(f'Carpet look command failed: {look_result}')
        if not self.moving:
            response = self.rcon.command(f'player {self.bot} move forward')
            if not command_ok(response):
                raise RuntimeError(f'Carpet movement command failed: {response}')
            self.moving = True
        self.attacking = False

    def attack_human(self, bot: Position, human: Position, now: float):
        """Use a physical fake-player attack; Scarpet verifies any actual damage."""
        if now-self.last_attack < 0.8:
            return
        self.last_attack = now
        self.halt_movement()
        self.rcon.command(f"player {self.bot} look at {human.x:.2f} {human.y+1.0:.2f} {human.z:.2f}")
        response = self.rcon.command(f"player {self.bot} attack once")
        if not command_ok(response):
            raise RuntimeError("Carpet attack command failed: " + response)
        self.attacking = True

    def halt_movement(self):
        if self.moving or self.attacking:
            self.stop()

    def escape_target(self, bot: Position, human: Position) -> Position:
        vx, vz = bot.x-human.x, bot.z-human.z
        norm = math.hypot(vx, vz)
        if norm < 0.01:
            angle = self.random.random()*math.tau
            vx, vz = math.cos(angle), math.sin(angle)
            norm = 1.0
        sideways = self.random.choice((-0.3,0.3))
        return Position(bot.x + 16*(vx/norm) - 8*(vz/norm)*sideways,
                        bot.y, bot.z + 16*(vz/norm) + 8*(vx/norm)*sideways)

    def report_stuck_obstacles(self, bot: Position):
        """Diagnostic-only sample; never edits terrain or guesses clearance."""
        if not self.path or self.path_index >= len(self.path):
            return
        dest = self.path[self.path_index].destination
        samples = [(math.floor(pos.x), math.floor(pos.y)+dy, math.floor(pos.z))
                   for pos in (bot, dest) for dy in (-1, 0, 1, 2)]
        try:
            blocks = self.sensor.read(samples)
            here = [blocks[xyz] for xyz in samples[:4]]
            ahead = [blocks[xyz] for xyz in samples[4:]]
            print(f'[NAV BLOCK] feet/support/head at bot={here}; waypoint={ahead}. '
                  'Particles are not part of Scarpet block observations.')
        except TerrainUnavailable as exc:
            print(f'[NAV BLOCK] Could not inspect terrain: {exc}')

    def _handle_airborne(self, bot: Position, now: float) -> bool:
        """Allow real jumping/falling to complete before starting ground A*.

        Do not infer a path from unsupported air or teleport the bot. A brief
        grace period preserves horizontal movement during deliberately issued
        jumps. When the player lands in water or on ground, replan immediately.
        """
        if not self.pathfinder.is_airborne(bot):
            if self.airborne:
                self.airborne=False
                self.path=()
                self.path_index=0
                self.path_created_at=0.0
                self.waypoint_key=None
                self.recovery_until=0.0
                self.sensor_retry_at=0.0
                self.last_progress=now
                print('[NAV AIR] Landing or water entry detected; replanning.')
            return False
        if not self.airborne:
            self.airborne=True
            self.airborne_since=now
            self.path_index=0
            self.waypoint_key=None
            self.last_progress=now
            # Don't interrupt a deliberate jump at its apex: hold the last
            # verified horizontal input briefly so it can reach its landing.
            if now - self.last_jump_command_at > 1.1:
                self.stop()
                self.path=()
            print('[NAV AIR] Bot temporarily airborne; awaiting real landing.')
        if now-self.last_jump_command_at > 1.1:
            # A long, uncontrolled fall is different from a path jump. Stop
            # steering instead of blindly sprinting off another ledge.
            if self.moving or self.climbing or self.sprinting:
                self.stop()
            self.path=()
        self.path_created_at=now
        self.last_progress=now
        return True

    def swim_waypoint_reached(self, bot: Position, step, previous) -> bool:
        """Treat a surface water cell as reached at its physical swim height.

        Walking waypoints still require the strict ground-level collision
        test; this exception is only for a verified water route while the
        swimmer has breathable air above its head.
        """
        if (step.swimming and self.water.swimming and not self.water.head_submerged
                and math.hypot(bot.x-step.destination.x, bot.z-step.destination.z) <= .57
                and abs(bot.y-step.destination.y) <= 1.15):
            return True
        return reached_waypoint(bot, step.destination, previous)

    def navigate(self, bot: Position, target: Position, now: float):
        """Follow rolling 3D A* waypoints using physical Carpet movement."""
        try:
            if self._handle_airborne(bot,now):
                return
        except TerrainUnavailable as exc:
            # A *real* failed read remains fail-closed, unlike observed air.
            self.nav_failures += 1
            self.sensor_retry_at = now + 5.0
            self.path = ()
            self.path_index = 0
            self.halt_movement()
            if not self.warned_sensor:
                print('[NAV WARNING] Airborne sensing failed; bot halted:',exc)
                self.warned_sensor=True
            return
        if self.miner.operation is not None:
            if self.miner.tick(now):
                return
            # Mine finished; force a new route through the edited terrain.
            self.path = ()
            self.path_created_at = 0.0
            self.sensor.cache.clear()
        if now < self.recovery_until:
            return
        if self.recovery_until:
            self.stop()
            self.recovery_until = 0.0
            self.path = ()
            self.route = None
        if self.moving and now - self.last_progress > 2.7 and now - self.last_recovery_at > 2.4:
            # A learned transfer setting should never strand the bot. Revert
            # it for the rest of this round if progress has stopped.
            if self.path and self.path_index < len(self.path):
                attempted=self.path[self.path_index]
                if attempted.climb:
                    self.live_skills.disable('climb','stalled on climb waypoint')
                elif attempted.swimming:
                    self.live_skills.disable('swim','stalled on swimming waypoint')
            failed = self.path[min(self.path_index, len(self.path)-1)].destination if self.path else None
            self.report_stuck_obstacles(bot)
            if failed:
                self.pathfinder.penalize(failed)
            self.sensor.cache.clear()  # Re-read blocks after physical collision
            self.navigator.mark_stuck(bot)
            self.last_recovery_at = now
            self.last_progress = now
            self.last_bot_position = bot
            self.recovery_attempts += 1
            self.failed_routes += 1
            if self.detour_active:
                self.detour_active = False
            self.path = ()
            self.waypoint_key = None
            self.route = None
            self.stop()
            # After repeated failures prefer a real, verified opening over
            # endlessly tracing the same blocked path. Mining stays limited to
            # ordinary, nearby materials and never edits blocks directly.
            if self.failed_routes >= 2 and not self.water.swimming:
                try:
                    if self.miner.try_start(bot,target,now,stop_movement=self.stop):
                        self.recovery_until=0.0
                        return
                except TerrainUnavailable:
                    pass
            # Stuck recovery must be collision-aware too. Blind /move backward
            # can drive the AI off a cliff or into lava.
            vx,vz=bot.x-target.x,bot.z-target.z
            magnitude=math.hypot(vx,vz)
            if magnitude < 0.1:
                vx,vz=1.,0.
                magnitude=1.
            retreat=Position(bot.x+5*vx/magnitude,bot.y,bot.z+5*vz/magnitude)
            # Recovery must obey the SAME 3D corridor checks as pursuit.
            # The old LocalNavigator chose a 2.4-block destination after only
            # probing two columns, which could still clip into leaf blocks.
            try:
                escape_plan=self.pathfinder.plan(bot,retreat,avoid_water=self.ai_role=='runner')
                candidate=escape_plan.steps[0] if escape_plan.steps else None
            except TerrainUnavailable:
                candidate=None
            if candidate is not None:
                self.look_and_move(candidate.destination)
                if candidate.jump or candidate.swimming:
                    self.rcon.command(f'player {self.bot} jump once')
                self.recovery_until=now+0.45
                print(f'[NAV] Stuck: recovery #{self.recovery_attempts}; A*-verified escape step.')
            else:
                self.recovery_until=now+0.5
                print(f'[NAV WARNING] Stuck: no safe escape direction; stopped to replan.')
            return
        # Follow cell centres rather than cutting corners as soon as a
        # waypoint is within 1.3 blocks (the v0.5.1 bug). Only allow a small
        # overshoot while still inside the same narrow route corridor.
        while self.path_index < len(self.path):
            previous = (self.path[self.path_index - 1].destination
                        if self.path_index else self.path_start)
            if not self.swim_waypoint_reached(bot, self.path[self.path_index], previous):
                break
            self.path_index += 1
            self.waypoint_key = None
        # Ended detours must be re-evaluated against the *real opponent*;
        # their temporary lateral goal is not proof of reaching the Runner.
        if self.detour_active and self.path and self.path_index >= len(self.path):
            self.detour_active = False
            self.path_created_at = 0.0
            print('[NAV DETOUR] Verified sidestep completed; resuming pursuit planning.')
        # Failed/no-route plans have a cooldown: repeated 1690-block scans on
        # every 0.16s movement tick can itself stall the Minecraft server.
        needs_plan = ((not self.path and now-self.path_created_at > 2.5)
                      or (self.path and self.path_index >= len(self.path))
                      or (self.path_goal is not None and self.path_goal.distance(target) > 3.5
                          and now-self.path_created_at > 1.6)
                      or now-self.path_created_at > 6.0)
        if needs_plan:
            self.path_attempts += 1
            try:
                if now < self.sensor_retry_at:
                    raise TerrainUnavailable('Scarpet checks in cooldown')
                self.pathfinder.max_gap = self.training.allowed_gap
                self.pathfinder.gap_risk = {
                    gap: 1.0-(wins/max(1,wins+fails))
                    for gap,(fails,wins) in self.training.results.items()}
                # Sideways exploration is ONLY considered after a normal
                # collision-checked scan has already returned zero steps.
                # Max four distinct detours per 30 seconds/goal region, and
                # never through unknown blocks, lava or unsafe cliff edges.
                if (self.detour_budget_start == 0.0 or
                        now-self.detour_budget_start >= 30.0 or
                        (self.detour_budget_goal is not None and
                         self.detour_budget_goal.distance(target) > 8.0)):
                    self.detour_budget_start = now
                    self.detour_budget_goal = target
                    self.detour_budget_used = 0
                    self.detour_exhausted_reported = False
                self.detour_recent = {node:expires for node,expires in self.detour_recent.items()
                                      if expires > now}
                detour_allowed = (self.failed_routes >= 1 and
                                  self.detour_budget_used < 4)
                plan = self.pathfinder.plan(
                    bot,target,avoid_water=self.ai_role=='runner',
                    allow_detour=detour_allowed,
                    detour_exclude=frozenset(self.detour_recent))
                self.path = plan.steps
                self.jump_controller.clear()
                self.jump_preflight_key=None
                if plan.detour:
                    self.detour_active = True
                    self.detour_routes += 1
                    self.detour_budget_used += 1
                    endpoint = plan.steps[-1].destination
                    node = (math.floor(endpoint.x),math.floor(endpoint.y),math.floor(endpoint.z))
                    self.detour_recent[node] = now + 45.0
                    print(f'[NAV DETOUR] No closer local path: trying {len(plan.steps)} '
                          f'verified side steps toward ({endpoint.x:.1f}, '
                          f'{endpoint.y:.1f}, {endpoint.z:.1f}); '
                          f'budget {self.detour_budget_used}/4.')
                    self.failed_routes += 1
                elif self.path:
                    self.detour_active = False
                    self.failed_routes = 0
                else:
                    self.detour_active = False
                    self.failed_routes += 1
                    self.empty_route_scans += 1
                self.path_index = 0
                self.path_start = bot
                self.path_goal = target
                self.path_created_at = now
                self.path_replans += 1
                self.nav_samples += 1
                self.route = None
                if self.sensor.active and not self.sensor_confirmed:
                    print('[NAV] Scarpet terrain sensing active; bounded 3D A* enabled.')
                    self.sensor_confirmed = True
                if self.path_attempts <= 3 or self.path_attempts % 12 == 0:
                    print(f'[NAV] A*: {len(plan.steps)} steps, expanded {plan.expanded}, '
                          f'goal reached={plan.reached_goal}; scanned {plan.observed_blocks} blocks.')
            except AirborneTransition:
                # The physical entity may have crossed a block boundary while
                # terrain sampling. The next tick will re-check its location.
                self._handle_airborne(bot,now)
                return
            except KeyError as exc:
                # Last-resort protection against any future out-of-window
                # indexing bug inside a path scan. A missing observed block
                # is NOT free space; stop and retry rather than letting the
                # exception unwind into launch.py and shut down the server.
                self.nav_failures += 1
                self.sensor_retry_at = now + 1.5
                self.path = ()
                self.path_index = 0
                self.path_created_at = now
                print(f'[NAV WARNING] Unobserved A* coordinate {exc}; '
                      'motion stopped; safe replanning scheduled.')
                self.halt_movement()
                return
            except TerrainUnavailable as exc:
                self.nav_failures += 1
                self.sensor_retry_at = now + 5
                self.path = ()
                self.path_index = 0
                if not self.warned_sensor:
                    print('[NAV WARNING] 3D route sensing unavailable; bot halted:', exc)
                    self.warned_sensor = True
                self.halt_movement()  # Never walk blindly into unseen lava/cliffs.
                return
            if not self.path:
                # A tactic that produced no playable path is NOT a failed
                # movement trial. Do not train the tactical policy on it.
                self.strategy.suspend_unroutable()
                if (self.detour_budget_used >= 4 and
                        not self.detour_exhausted_reported):
                    print('[NAV WARNING] Verified detour budget exhausted; '
                          'no safe route to opponent in observed local region. '
                          'Will retry when the goal region or terrain changes.')
                    self.detour_exhausted_reported = True
                # Water-landings are opt-in practice until three or more
                # real successful water-drop trials certify this skill.
                if ((self.training.practice or self.training.water_drop_ready)
                        and self.training.trial is None and target.y < bot.y-3
                        and not self.water.swimming):
                    try:
                        candidate=self.water_drop_planner.propose(bot,target)
                        if candidate is not None:
                            self.set_sprinting(True)
                            self.look_and_move(candidate.destination)
                            self.rcon.command(f'player {self.bot} jump once')
                            self.training.begin('water_drop',bot,candidate.destination,now,0)
                            self.water_drop_active=True
                            self.last_jump_command_at=now
                            print(f'[DROP] Attempting verified water landing at {candidate.destination}.')
                            return
                    except TerrainUnavailable:
                        pass
                # Two unsuccessful route scans permit a *physical*, bounded
                # attempt to clear an allowlisted obstruction. Never /setblock.
                if self.failed_routes >= 2 and not self.water.swimming:
                    try:
                        if self.miner.try_start(bot,target,now,stop_movement=self.stop):
                            self.path_created_at=now
                            return
                    except TerrainUnavailable as exc:
                        print('[MINE WARNING] Mining unavailable:', exc)
                # The old local-steering fallback sampled a point 2.4 blocks
                # away and drove toward it without confirming the swept
                # corridor. A* refusing a route is NOT permission to push
                # into leaves or an unobserved wall.
                if self.path_attempts <= 3 or self.path_attempts % 12 == 0:
                    print('[NAV] No verified 3D route or safe fresh detour in current window; stopped for replan.')
                self.halt_movement()
                return
        if not self.path or self.path_index >= len(self.path):
            self.halt_movement()
            return
        # Always steer to the next verified cell centre. Looking ahead even
        # on apparently straight paths risks cutting across a nearby leaf wall
        # when the fake player is physically off-centre.
        current = self.path[self.path_index]
        current_key = (self.path_index, current.destination)
        current_distance = bot.distance(current.destination)
        if current_key != self.waypoint_key:
            self.waypoint_key = current_key
            self.waypoint_best_distance = current_distance
            self.last_progress = now
        elif current_distance < self.waypoint_best_distance - 0.16:
            # Progress toward the selected waypoint, not just any movement;
            # walking sideways against a tree no longer resets stuck timer.
            self.waypoint_best_distance = current_distance
            self.last_progress = now
        if current.climb:
            self.set_sprinting(False)
            self.climb_move(bot, current.destination)
            return
        if (current.swimming and abs(current.destination.x-bot.x)<.45
                and abs(current.destination.z-bot.z)<.45):
            # Vertical water segments are controlled by WaterSurvival. Never
            # issue a global stop: that would cancel the held ascent and
            # restart the 0/+1 oscillation observed in the v0.7.13 run.
            self.set_sprinting(False)
            return
        if self.climbing:
            self.stop()  # Release continuous jump or sneak after climbing.
        # Sprint only along verified, straight, *grounded* corridor cells.
        # Near corners/obstacles retain slower cell-centre steering.
        run_to=current.destination
        sprint_allowed=False
        if (not current.swimming and not current.jump and
                not self.water.swimming and not current.sprint_jump):
            a=self.path_index
            if a+2 < len(self.path):
                one,two,three=self.path[a:a+3]
                if not any(p.swimming or p.jump or p.climb or p.sprint_jump for p in (one,two,three)):
                    previous=self.path[a-1].destination if a else self.path_start
                    if previous is not None:
                        dx=one.destination.x-previous.x
                        dz=one.destination.z-previous.z
                        straight=(all(abs(step.destination.y-bot.y)<.5 for step in (one,two,three))
                                  and abs(two.destination.x-one.destination.x-dx)<.01
                                  and abs(two.destination.z-one.destination.z-dz)<.01
                                  and abs(three.destination.x-two.destination.x-dx)<.01
                                  and abs(three.destination.z-two.destination.z-dz)<.01)
                        if straight:
                            sprint_allowed=True
                            run_to=three.destination
        if current.sprint_jump:
            key=(self.path_index,current.destination)
            takeoff=self.path[self.path_index-1].destination if self.path_index else self.path_start
            if takeoff is None:
                self.halt_movement()
                return
            gap=max(1,round(math.hypot(current.destination.x-takeoff.x,
                                       current.destination.z-takeoff.z))-1)
            if key != self.jump_preflight_key:
                try:
                    cleared=self.jump_corridor.verified(takeoff,current.destination)
                except (TerrainUnavailable, KeyError):
                    cleared=False
                if not cleared:
                    self.pathfinder.penalize(current.destination)
                    self.path=()
                    self.path_created_at=now
                    self.halt_movement()
                    print('[MOVE WARNING] Unverified jump corridor; declining gap and replanning.')
                    return
                self.jump_preflight_key=key
            speed=self.motion.speed_towards(takeoff,current.destination)
            decision=self.jump_controller.decide(
                key,bot,takeoff,current.destination,now,speed,
                self.training.launch_threshold_for(gap))
            if decision.command=='abort':
                self.pathfinder.penalize(current.destination)
                self.path=()
                self.path_created_at=now
                self.halt_movement()
                print('[MOVE WARNING] Jump aborted:',decision.reason)
                return
            self.set_sprinting(True)
            self.look_and_move(current.destination)
            if decision.command=='jump' and now-self.last_jump_command_at>.45:
                self.rcon.command(f'player {self.bot} jump once')
                self.training.begin('sprint_jump',bot,current.destination,now,gap,
                                    launch_offset=decision.distance_from_takeoff,
                                    approach_speed=speed)
                self.last_jump_command_at=now
                self.jump_key=key
                print(f'[MOVE] Timed sprint jump gap={gap} speed={speed:.2f} blocks/s; trial recording.')
        else:
            self.set_sprinting(sprint_allowed or current.swimming or self.water.swimming)
            self.look_and_move(run_to)
            # Do NOT add jump-once to a continuous swim column; this can
            # interrupt ascent. V0.7 WaterSurvival controls underwater pitch.
            # At the shallow-water edge, jumping onto verified higher ground
            # is valid; continuous underwater jump remains WaterSurvival's job.
            if (current.jump and (not current.swimming or not self.water.head_submerged)
                    and now-self.last_jumped > .8):
                self.rcon.command(f'player {self.bot} jump once')
                self.last_jump_command_at=now
                self.last_jumped=now

    def step(self):
        human = self.observer.position(self.player)
        bot = self.observer.position(self.bot)
        dist = bot.distance(human)
        now = time.monotonic()
        self.motion.observe(bot,now)  # Real observed positions, never guessed velocity.
        self.strategy.observe(bot,human,now)
        if self.training.trial is not None:
            # A true supported landing, or entering real water for a water drop.
            try:
                if self.training.trial.skill == 'water_drop':
                    c=(math.floor(bot.x),math.floor(bot.y),math.floor(bot.z))
                    observed=self.sensor.read([c])
                    grounded=(terrain_type(observed[c])=='water')
                else:
                    grounded=not self.pathfinder.is_airborne(bot)
                self.training.observe(bot,now,grounded=grounded)
            except TerrainUnavailable:
                pass
        if self.last_bot_position is None:
            self.last_progress = now
        self.last_bot_position = bot
        # Physical proximity is not a win. Only the Scarpet damage event can
        # confirm a hit from the actual Hunter against the actual Runner.
        if self.hit_detector is not None and self.hit_detector.hunter_hit(self.role):
            return 'hunter'
        try:
            submerged=False
            if self.hit_detector is not None:
                vertical=0  # Horizontal sprint-swimming by default, not bobbing.
                if self.path and self.path_index<len(self.path):
                    candidate=self.path[self.path_index]
                    if candidate.swimming and candidate.destination.y > bot.y+.55:
                        vertical=1
                    elif candidate.swimming and candidate.destination.y < bot.y-.55:
                        vertical=-1
                    elif candidate.swimming and abs(candidate.destination.y-bot.y)<.35:
                        vertical=0
                submerged=self.water.update(bot,now,stop_movement=self.stop,vertical=vertical)
                if submerged and self.water.stall_detected:
                    # Water-phase stuck detection uses actual XZ movement.
                    # Changing A* waypoints must not reset this watchdog.
                    if self.path and self.path_index < len(self.path):
                        self.pathfinder.penalize(self.path[self.path_index].destination,seconds=6)
                    self.path=()
                    self.path_index=0
                    self.path_goal=None
                    self.path_created_at=now-3.0
                    self.waypoint_key=None
                    self.failed_routes+=1
                    self.live_skills.disable('swim','no horizontal progress in water')
                    self.strategy.suspend_unroutable()
                    self.halt_movement()
                    print('[SWIM RECOVERY] No horizontal progress for 3.5s; '
                          'discarded water waypoint, temporarily excluded it, '
                          'and requested a new verified route.')
                if submerged and (self.water.last_air<165 or
                        (self.water.entered_at and now-self.water.entered_at>9)):
                    if self.surface_goal is None or now-self.surface_goal_at>2:
                        self.surface_goal=(self.surface_planner.find_air(bot)
                                           or self.surface_planner.ascend_waypoint(bot))
                        self.surface_goal_at=now
                    if self.surface_goal is not None:
                        self.navigate(bot,self.surface_goal,now)
                    else:
                        self.halt_movement()
                        print('[SWIM WARNING] No verified breathable path in observed range; retrying.')
                    return None
                if not submerged:
                    self.surface_goal=None
        except TerrainUnavailable as exc:
            # Never blindly advance after losing the sensor; keep the match up.
            self.halt_movement()
            if not self.warned_sensor:
                print('[SWIM WARNING] Air/water sensing unavailable:', exc)
                self.warned_sensor=True
            return None
        if self.ai_role == 'hunter' and dist <= 2.8:
            try:
                if attack_line_clear(self.sensor, bot, human):
                    self.attack_human(bot,human,now)
                    return None
            except TerrainUnavailable:
                # Unknown world is not a license to attack through a wall.
                self.halt_movement()
                return None
        opponent = 'runner' if self.ai_role == 'hunter' else 'hunter'
        decision = self.brain.handle_observation(Observation(
            player_id=self.bot,
            position=(bot.x, bot.y, bot.z),
            visible_entities={opponent: (human.x, human.y, human.z)},
        ))
        if self.ai_role == 'hunter':
            if decision is not None and decision.target is not None:
                # Strategic decisions adjust only the bounded *goal*. They do
                # not bypass A*, safety sampling, damage-hit checks, or air.
                tactical=self.strategy.hunt(bot,human,now)
                self.target=tactical.target
                self.navigate(bot,self.target,now)
            else:
                self.halt_movement()
        else:
            if self.target is None or bot.distance(self.target)<3 or now-self.last_progress>5:
                if decision is not None and decision.name=='retreat' and decision.target is not None:
                    baseline=Position.from_tuple(tuple(decision.target))
                else:
                    baseline=self.escape_target(bot,human)
                tactical=self.strategy.escape(bot,human,now,baseline)
                self.target=tactical.target
            self.navigate(bot,self.target,now)
        return None

    def movement_tick_delay(self) -> float:
        # Sprinting can cover ~0.8 blocks during the normal 0.16s loop.
        # Briefly target a faster observation/control cadence near a gap;
        # actual RCON latency remains measurable and may exceed this target.
        if (self.path and self.path_index < len(self.path)
                and self.path[self.path_index].sprint_jump):
            return .05
        return .16

    def run(self):
        self.wait_for_player()
        self.setup_bot()
        self.hit_detector = HitDetector(self.rcon, SERVER / "world", self.player, self.bot)
        self.hit_detector.setup()
        print(f'[MATCH] You are {self.role.upper()}; ManhuntBot is {self.ai_role.upper()}')
        print(f'[STRATEGY] Bounded tactical decisions: {self.strategy.status()}')
        print('[MATCH] Win condition: a confirmed Hunter melee hit, or Runner survives the timer.')
        initial_hunter_position = self.observer.position(self.player) if self.role == 'hunter' else None
        if self.role == 'hunter':
            self.rcon.command(f'gamemode spectator {self.player}')
            self.hunter_was_spectator = True
            print('[MATCH] Human Hunter is spectator during head start; position restored when it ends.')
        try:
            start = time.monotonic()
            end = start + self.head_start
            last_output = -1
            while time.monotonic() < end:
                remaining = max(0, math.ceil(end-time.monotonic()))
                if remaining != last_output and (remaining%5 == 0 or remaining <= 3):
                    print(f'[HEAD START] {remaining}s remaining')
                    self.rcon.command(f'title {self.player} actionbar {component(f"Head start: {remaining}s remaining", "yellow")}')
                    last_output = remaining
                if self.ai_role == 'runner':
                    self.step()  # Runner begins moving before human Hunter is released.
                time.sleep(self.movement_tick_delay())
            if self.role == 'hunter':
                assert initial_hunter_position is not None
                self.rcon.command(f'tp {self.player} {initial_hunter_position.x:.2f} {initial_hunter_position.y:.2f} {initial_hunter_position.z:.2f}')
                self.rcon.command(f'gamemode survival {self.player}')
                self.hunter_was_spectator = False
            self.hit_detector.reset()  # Ignore anything during head start.
            show_match_start(self.rcon, self.player, self.role)
            print('[MATCH] GO! The Hunter is now released.')
            game_start = time.monotonic()
            last_report = 0.0
            while True:
                if self.player not in self.players():
                    print('[MATCH] Human disconnected. Ending match.')
                    return 'disconnected'
                if self.bot not in self.players():
                    # A lethal human Hunter attack can remove the fake player
                    # before the next poll. Honor an already-confirmed hit.
                    if self.role == 'hunter' and self.hit_detector.hunter_hit(self.role):
                        self.result_reason = 'hit'
                        winner = 'hunter'
                        break
                    print('[MATCH] Fake player disconnected. Ending match.')
                    return 'bot_disconnected'
                elapsed = time.monotonic()-game_start
                if elapsed >= self.survival_seconds:
                    self.result_reason = 'survival'
                    winner = 'runner'
                    break
                winner = self.step()
                if winner:
                    self.result_reason = 'hit'
                    break
                if time.monotonic()-last_report > 8:
                    human = self.observer.position(self.player)
                    bot = self.observer.position(self.bot)
                    print(f'[MATCH] {int(elapsed)}s / {self.survival_seconds}s | separation {human.distance(bot):.1f} blocks')
                    last_report = time.monotonic()
                time.sleep(self.movement_tick_delay())
            self.game_duration = time.monotonic() - game_start
            print(f'\n[RESULT] {winner.upper()} wins the HIT MANHUNT!')
            print(f'[NAV] 3D plans={self.path_replans}, sensor failures={self.nav_failures}, stuck recoveries={self.recovery_attempts}, mined={self.miner.successes}, emergency-air={self.water.emergency_count}, spawn retries={self.spawn_retries}, zero-route={self.empty_route_scans}, verified-detours={self.detour_routes}, skipped-strategy-stationary={self.strategy.skipped_stationary}, skipped-strategy-unroutable={self.strategy.skipped_unroutable}')
            return winner
        finally:
            if self.training.trial is not None:
                try:
                    self.training.finish(False,self.observer.position(self.bot),time.monotonic())
                except Exception:
                    pass
            self.miner.stop()
            self.stop()
            if self.hunter_was_spectator and self.player:
                # Only restore after an interrupted head start; NEVER teleport
                # a Hunter back after a successfully completed match.
                try:
                    if initial_hunter_position is not None:
                        self.rcon.command(f'tp {self.player} {initial_hunter_position.x:.2f} {initial_hunter_position.y:.2f} {initial_hunter_position.z:.2f}')
                    self.rcon.command(f'gamemode survival {self.player}')
                except Exception:
                    pass
