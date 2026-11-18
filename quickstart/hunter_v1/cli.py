"""Start local Manhunt, run isolated physical benchmarks, and summarize metrics."""
import argparse
from dataclasses import asdict
import json
import re
from pathlib import Path
import statistics
import sys
import time
import uuid

from ..install import MINECRAFT_VERSION, ROOT, SetupError, ensure_properties, eula_agreement, install_fabric, install_mod, java_executable
from ..launch import local_port_open, start_server, stop_server, wait_for_rcon
from ..lobby import Lobby
from ..rcon import RconClient, RconError
from .bridge import Bridge
from .inventory import BOT, drop, inspect_inventory, transfer
from ..results import component
from .game import HunterGame
from .scenarios import HUNTER_START, RUNNER, SCENARIOS, ScriptedRunner
from .settings import DEFAULT_CONFIG, load_settings

RUNTIME = ROOT / "runtime"
LIVE = RUNTIME / "hunter-v1"
BENCH = RUNTIME / "hunter-v1-benchmark"
CARPET_VERSION = "1.4.194"


def write_metrics(path, game, mode, split, seed, scenario):
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"schema": 1, "round_id": uuid.uuid4().hex, "time": int(time.time()), "mode": mode,
           "split": split, "seed": seed, "scenario": scenario, **asdict(game.metrics)}
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, sort_keys=True) + "\n")
    print(f"[RESULT] {row['result']} / {row['reason']} -- distance {row['blocks_traveled']:.1f} blocks")
    print(f"[METRICS] {path}")


def summarize(path, *, split=None, scenario=None, mode=None, policy=None):
    if not path.exists():
        raise ValueError(f"No match metrics at {path}")
    rows = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            try:
                row = json.loads(line)
                if row.get("schema") != 1:
                    raise ValueError("unsupported schema")
            except (AttributeError, ValueError) as exc:
                raise ValueError(f"Invalid metric row {line_number}: {exc}") from exc
            if ((split is None or row["split"] == split) and (scenario is None or row["scenario"] == scenario)
                    and (mode is None or row["mode"] == mode)
                    and (policy is None or row.get("opening_policy") == policy)):
                rows.append(row)
    completed = [row for row in rows if row["result"] in ("hunter", "runner")]
    tagged = [row["first_hit_s"] for row in completed if row["first_hit_s"] is not None]
    picked = [sum(row["items_picked_up"].values()) for row in completed if row["items_picked_up"] is not None]
    by_opening = {}
    for row in completed:
        action = row.get("opening") or "unassigned"
        bucket = by_opening.setdefault(action, {"rounds": 0, "hunter_wins": 0, "tags": 0})
        bucket["rounds"] += 1
        bucket["hunter_wins"] += row["result"] == "hunter"
        bucket["tags"] += row["first_hit_s"] is not None
    return {
        "openings": by_opening,
        "points": {role: sum(row.get("points", {}).get(role, 0) for row in completed)
                   for role in ("hunter", "runner")},
        "rounds": len(rows), "completed": len(completed), "aborted": len(rows) - len(completed),
        "hunter_wins": sum(row["result"] == "hunter" for row in completed),
        "hunter_win_rate": (sum(row["result"] == "hunter" for row in completed) / len(completed)
                            if completed else None),
        "blocks_placed": sum(row.get("blocks_placed", 0) for row in rows),
        "bridges_crossed": sum(row.get("bridges_crossed", 0) for row in rows),
        "climbs_completed": sum(row.get("climbs_completed", 0) for row in rows),
        "tagged_rounds": len(tagged), "median_first_hit_s": statistics.median(tagged) if tagged else None,
        "mean_blocks_traveled": (statistics.mean(row["blocks_traveled"] for row in completed) if completed else None),
        "pickup_observed_rounds": len(picked), "mean_items_picked_up": statistics.mean(picked) if picked else None,
    }


class ScenarioGame(HunterGame):
    def setup_bot(self):
        super().setup_bot()
        self.rcon.command(f"clear {self.bot}")
        p = HUNTER_START
        result = self.rcon.command(f"execute in minecraft:overworld run tp {self.bot} {p.x} {p.y} {p.z}")
        self.sensor.cache.clear()
        if "Teleported" not in result or not self.spawn_finder.verify(self.observer.position(self.bot)):
            raise RuntimeError(f"Unsafe or unavailable benchmark hunter start: {result[:135]}")


def play(args):
    settings = load_settings(args.config)
    benchmark = args.command == "scenario"
    data_dir = BENCH if benchmark else LIVE
    run_id = uuid.uuid4().hex[:12]
    server = (data_dir / "sessions" / run_id) if benchmark else (data_dir / "server")
    ports = (25567, 25577) if benchmark else (25565, 25575)
    proc = rcon = None
    if args.win_mode:
        settings["game"]["win_mode"] = args.win_mode
    if benchmark:
        settings["game"]["head_start_seconds"] = args.head_start
        settings["game"]["time_limit_seconds"] = args.seconds
        bridge_option = SCENARIOS[args.scenario].bridge_option
        if bridge_option:
            settings["resources"][bridge_option] = True
    if not args.setup_only and any(map(local_port_open, ports)):
        raise SetupError(f"Stop any prior server listening on {ports[0]} or {ports[1]}")
    overrides = {"online-mode": "false", "enforce-secure-profile": "false",
                 "level-seed": str(args.seed), "generate-structures": "false"} if benchmark else None
    java = java_executable()
    props = ensure_properties(server, game_port=ports[0], rcon_port=ports[1], overrides=overrides)
    install_fabric(server)
    install_mod("carpet", "Carpet fake players", server, version=CARPET_VERSION)
    if args.setup_only:
        print("[READY] Fabric and Carpet are ready for the next play launch.")
        return 0
    eula_agreement(server)
    try:
        proc, _ = start_server(java, server, game_port=ports[0])
        rcon = wait_for_rcon(proc, props, command_timeout=15.0 if benchmark else 4.0)
        bootlog = (server / "logs" / "latest.log").read_text(encoding="utf-8", errors="replace")
        version = re.search(r"Starting minecraft server version (\S+)", bootlog)
        if version is None or version[1] != MINECRAFT_VERSION:
            raise SetupError(f"Hunter v1 needs exactly Minecraft Java {MINECRAFT_VERSION}. Check the server launcher.")
        reply = rcon.command("carpet allowSpawningOfflinePlayers true")
        if any(term in reply.lower() for term in ("unknown", "incorrect", "failed")):
            raise SetupError(f"Carpet 1.21.11 rules unavailable: {reply[:150]}")
        rcon.command("carpet allowListingFakePlayers true")
        world = server / "world"
        identity = world / "mh_v1_world_id"
        if not identity.exists():
            identity.write_text(uuid.uuid4().hex, encoding="ascii")
        world_id = identity.read_text(encoding="ascii").strip()
        if not benchmark and len(world_id) != 32:
            raise SetupError("Invalid hunter v1 world identity file")
        lobby = Lobby(rcon)
        if not benchmark:
            lobby.setup()
            lobby.start_console()
        rounds = args.rounds if benchmark else None
        while proc.poll() is None and (rounds is None or rounds > 0):
            if benchmark:
                driver = ScriptedRunner(rcon, SCENARIOS[args.scenario])
                driver.setup()
            else:
                driver = None
            game_type = ScenarioGame if benchmark else HunterGame
            seed = args.seed if benchmark else props.get("level-seed") or None
            scope = f"bench-{args.scenario}-{seed}" if benchmark else world_id
            game = game_type(rcon, settings, server / "world", data_dir, scope,
                             runner=RUNNER if benchmark else args.runner,
                             held_out=benchmark and args.split == "held-out", policy=args.policy)
            try:
                game.run_v1(driver)
            except (OSError, ValueError, RuntimeError):
                game.metrics.result, game.metrics.reason = "aborted", "runtime_error"
                raise
            finally:
                try:
                    if driver:
                        driver.stop()
                finally:
                    write_metrics(data_dir / "rounds.jsonl", game, settings["game"]["win_mode"],
                                  args.split if benchmark else "live", seed,
                                  args.scenario if benchmark else None)
            if benchmark:
                rounds -= 1
                continue
            result = game.metrics.result
            reason = game.metrics.reason.replace("_", " ")
            points = game.metrics.points
            if points:
                rcon.command("scoreboard objectives add mh_points dummy")
                for role, value in points.items():
                    rcon.command(f"scoreboard players add {role.capitalize()} mh_points {value}")
            if game.player not in game.players():
                continue
            score = f" | Hunter +{points['hunter']}, Runner +{points['runner']}" if points else ""
            message = f"[Manhunt] {result.capitalize()} | {reason}{score}. Replay with /trigger mh_replay."
            rcon.command(f"tellraw {game.player} {component(message, 'gold')}")
            lobby.clear_pending_console()
            lobby.prepare_player(game.player)
            print("[LOBBY] R or /trigger mh_replay plays again. Q stops the server.")
            while proc.poll() is None:
                action = lobby.poll_action(game.player)
                if action == "quit":
                    return 0
                if action == "replay":
                    break
                time.sleep(.4)
        if benchmark:
            print(json.dumps(summarize(BENCH / "rounds.jsonl", split=args.split,
                                       scenario=args.scenario, mode=args.win_mode, policy=args.policy), indent=2))
        return 0
    finally:
        if rcon:
            rcon.close()
        if proc:
            stop_server(proc)


def manage_inventory(args):
    settings = load_settings(args.config)
    props = {}
    path = LIVE / "server" / "server.properties"
    for line in path.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if separator and key in {"rcon.port", "rcon.password"}:
            props[key] = value
    if not props.get("rcon.password"):
        raise ValueError("Start a live Manhunt round before inspecting inventory")
    if (args.to or args.drop) and not settings["resources"]["allow_transfers"]:
        raise ValueError("Enable resources.allow_transfers before making an operator inventory change")
    if args.to and None in (args.source_slot, args.dest_slot):
        raise ValueError("Transfer requires --source-slot and --dest-slot")
    if args.drop and (args.player != BOT or args.source_slot is None or args.dest_slot is not None):
        raise ValueError("Drop requires the bot and --source-slot")
    if not (args.to or args.drop) and (args.source_slot is not None or args.dest_slot is not None):
        raise ValueError("Slot arguments require --to or --drop")
    client = RconClient("127.0.0.1", int(props.get("rcon.port", 25575)), props["rcon.password"])
    try:
        bridge = Bridge(client, BOT)
        if args.to:
            result = transfer(bridge, args.player, args.to, args.source_slot, args.dest_slot, args.count)
        elif args.drop:
            result = drop(bridge, args.source_slot, args.count)
        else:
            result = [asdict(stack) for stack in inspect_inventory(bridge, args.player).values()]
        print(json.dumps(result, indent=2))
        return 0
    finally:
        client.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Hunter-only Manhunt v1.2.1 for Minecraft Java 1.21.11")
    sub = parser.add_subparsers(dest="command", required=True)
    live = sub.add_parser("play")
    policies = ("learned", "baseline", "press", "gear")
    live.add_argument("--runner", "--player", dest="runner", help="Minecraft username of the human runner")
    live.add_argument("--win-mode", choices=("hit", "dragon"))
    live.add_argument("--policy", choices=policies, default="learned")
    live.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    live.add_argument("--setup-only", action="store_true")
    bench = sub.add_parser("scenario")
    bench.add_argument("--scenario", choices=SCENARIOS, required=True)
    bench.add_argument("--seed", type=int, required=True)
    bench.add_argument("--rounds", type=int, default=1)
    bench.add_argument("--split", choices=("train", "held-out"), default="held-out")
    bench.add_argument("--seconds", type=int, default=45)
    bench.add_argument("--head-start", type=int, default=3)
    bench.add_argument("--win-mode", choices=("hit", "dragon"), default="hit")
    bench.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    bench.add_argument("--policy", choices=policies, default="learned")
    bench.set_defaults(setup_only=False)
    report = sub.add_parser("report")
    report.add_argument("--file", type=Path, default=BENCH / "rounds.jsonl")
    report.add_argument("--split", choices=("train", "held-out", "live"))
    report.add_argument("--scenario", choices=SCENARIOS)
    report.add_argument("--mode", choices=("hit", "dragon"))
    report.add_argument("--policy", choices=policies)
    inventory = sub.add_parser("inventory", help="Inspect or transfer inventory on the live server")
    inventory.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    inventory.add_argument("--player", default=BOT)
    action = inventory.add_mutually_exclusive_group()
    action.add_argument("--to")
    action.add_argument("--drop", action="store_true")
    inventory.add_argument("--source-slot", type=int)
    inventory.add_argument("--dest-slot", type=int)
    inventory.add_argument("--count", type=int, default=1)
    args = parser.parse_args(argv)
    if args.command == "scenario" and not (1 <= args.rounds <= 100 and 15 <= args.seconds <= 900
            and 0 <= args.head_start <= 60 and -(2**63) <= args.seed < 2**63):
        parser.error("Use 1-100 rounds, 15-900 seconds, 0-60s head start and a signed 64-bit seed")
    try:
        if args.command == "report":
            print(json.dumps(summarize(args.file, split=args.split, scenario=args.scenario,
                                       mode=args.mode, policy=args.policy), indent=2))
            return 0
        if args.command == "inventory":
            return manage_inventory(args)
        return play(args)
    except (SetupError, RconError, OSError, ValueError, RuntimeError) as exc:
        print("[ERROR]", exc, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
