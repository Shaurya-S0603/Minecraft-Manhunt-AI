"""Fixed-seed physical fixtures. World editing is restricted to benchmark setup."""
from dataclasses import dataclass
import time

from ..match import command_ok
from ..observations import Observer, Position, parse_player_list
from .bridge import Bridge

RUNNER = "BenchRunner"
Y = 92
START = Position(4.5, Y, .5)
HUNTER_START = Position(-5.5, Y, .5)
BUILD_SUPPLIES = 'summon minecraft:item -5.5 92 0.5 {Item:{id:"minecraft:cobblestone",count:20}}'
FLOOR = "fill -14 91 -10 52 91 12 minecraft:stone"


@dataclass(frozen=True)
class Scenario:
    commands: tuple
    route: tuple
    jump_at: float | None = None
    start: Position = START
    bridge_option: str | None = None


SCENARIOS = {
    "straight": Scenario((), ((44, 92, .5), (5, 92, .5), (45, 92, .5))),
    "turns": Scenario(("fill 11 92 -2 12 94 6 minecraft:stone",),
                      ((8, 92, -6), (19, 92, -6), (19, 92, 8), (43, 92, 8))),
    "gap": Scenario(("fill 14 88 -10 14 91 12 minecraft:air",), ((43, 92, .5),), 13.05),
    "river": Scenario(("fill 13 91 -10 20 91 12 minecraft:water",
                       "fill 13 90 -10 20 90 12 minecraft:stone"), ((44, 92, .5),)),
    "ladder": Scenario(("fill 21 92 -10 26 96 12 minecraft:stone",
                        "fill 20 92 0 20 96 0 minecraft:ladder[facing=west]"), (),
                       start=Position(21.35, 97, .5)),
    "bridge": Scenario(("fill 8 88 -10 12 91 12 minecraft:air",
                        "fill 1 92 -4 2 93 -3 minecraft:dirt",
                        BUILD_SUPPLIES), (), start=Position(18.5, Y, .5)),
    "water-bridge": Scenario(("fill 8 90 -10 12 90 12 minecraft:stone",
                              "fill 8 91 -10 12 91 12 minecraft:water", BUILD_SUPPLIES), (),
                             start=Position(18.5, Y, .5), bridge_option="water_bridge"),
    "lava-bridge": Scenario(("fill 8 90 -10 12 90 12 minecraft:stone",
                             "fill 8 91 -10 12 91 12 minecraft:lava", BUILD_SUPPLIES), (),
                            start=Position(18.5, Y, .5), bridge_option="lava_bridge"),
    "vines": Scenario(("fill 21 92 -10 26 96 12 minecraft:stone",
                       "fill 20 92 -1 20 96 1 minecraft:vine[east=true]"), (),
                      start=Position(21.35, 97, .5)),
    "pillar": Scenario(("fill 8 92 -10 12 95 12 minecraft:stone", BUILD_SUPPLIES), (),
                       start=Position(8.25, 96, .5)),
    "supplies": Scenario(("fill -8 92 2 -8 94 2 minecraft:oak_log",
                         "fill -12 92 -4 -11 93 -3 minecraft:dirt",
                         "summon minecraft:cow -5 92 3",
                         "summon minecraft:pig -8 92 -3"), (),
                         start=Position(44.5, Y, .5)),
    "portal": Scenario(("fill 29 91 -1 29 95 2 minecraft:obsidian",
                        "fill 29 92 0 29 94 1 minecraft:nether_portal[axis=z]"),
                       ((29.55, 92, .5),)),
}


class ScriptedRunner:
    def __init__(self, rcon, scenario):
        self.rcon = rcon
        self.scenario = scenario
        self.bridge = Bridge(rcon, RUNNER)
        self.observer = Observer(rcon)
        self.index = 0
        self.launched = False
        self.next_tick = 0.
        self.finished = False

    def command(self, command):
        reply = self.rcon.command(command)
        if not command_ok(reply) or any(phrase in reply.lower() for phrase in
                                       ("outside", "not loaded", "cannot", "failed")):
            raise RuntimeError(f"Scenario setup command failed: {command} ({reply[:180]})")

    def setup(self):
        for name in (RUNNER, "ManhuntBot"):
            if name in parse_player_list(self.rcon.command("list")):
                self.command(f"player {name} stop")
                self.command(f"player {name} kill")
        self.command("forceload add -16 -16 52 12")
        # One disposable world per invocation. Reset only the elevated arena
        # between rounds. Vanilla AI movement runs after all edits are finished.
        self.command("fill -14 88 -10 52 98 12 minecraft:air")
        self.rcon.command("kill @e[type=!minecraft:player,x=-14,y=87,z=-10,dx=66,dy=11,dz=22]")
        for command in (FLOOR, *self.scenario.commands):
            self.command(command)
        self.command("setworldspawn 4 92 0")
        self.command("gamerule minecraft:spawn_mobs false")
        self.command("gamerule minecraft:advance_time false")
        self.command("time set 1000")
        anchor = self.scenario.start
        self.command(f"execute in minecraft:overworld positioned {anchor.x} {anchor.y} {anchor.z} "
                     f"run player {RUNNER} spawn in survival")
        deadline = time.monotonic() + 15
        while RUNNER not in parse_player_list(self.rcon.command("list")):
            if time.monotonic() > deadline:
                raise RuntimeError("Scripted runner failed to spawn. Check Carpet profile resolution in latest.log.")
            time.sleep(.2)
        self.command(f"clear {RUNNER}")
        self.command(f"advancement revoke {RUNNER} everything")
        self.finished = not self.scenario.route

    def tick(self):
        now = time.monotonic()
        if self.finished or now < self.next_tick:
            return
        self.next_tick = now + .075
        where = self.rcon.command(f"execute as {RUNNER} at @s if dimension minecraft:overworld")
        if "Test passed" not in where:
            self.stop()
            return
        pos = self.observer.position(RUNNER)
        x, y, z = self.scenario.route[self.index]
        distance = pos.distance(Position(x, y, z))
        tolerance = .25 if x == 29.55 else .95
        if distance < tolerance:
            self.index += 1
            if self.index == len(self.scenario.route):
                self.stop()
                return
            x, y, z = self.scenario.route[self.index]
        self.bridge.look(Position(x, pos.y + 1.62, z))
        self.bridge.action("move forward")
        if self.scenario.jump_at is not None and not self.launched and pos.x >= self.scenario.jump_at:
            self.bridge.action("jump once")
            self.launched = True
        if y > pos.y + 2:
            self.bridge.action("jump continuous")

    def stop(self):
        if not self.finished and RUNNER in parse_player_list(self.rcon.command("list")):
            self.bridge.action("stop")
        self.finished = True
