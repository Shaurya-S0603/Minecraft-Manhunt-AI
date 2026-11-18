"""Windows-friendly Python entry point for a single-machine hit-Manhunt test."""
from __future__ import annotations
import argparse
import os
import queue
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from .install import SERVER, SetupError, prepare, ensure_properties
from .rcon import RconClient, RconError
from .match import ManhuntMatch
from .lobby import Lobby
from .results import RoundResult, show_round_result
from .history import MatchHistory


def local_port_open(port: int) -> bool:
    try:
        with socket.create_connection(('127.0.0.1', port),timeout=0.8):
            return True
    except OSError:
        return False


def reset_world():
    import datetime
    import secrets
    import shutil
    if local_port_open(25565) or local_port_open(25575):
        raise SetupError('Minecraft is still running. Close the server before resetting.')
    world = SERVER/'world'
    # Explicitly only work with the known child directory, never arbitrary paths.
    if world.is_symlink() or world.resolve().parent != SERVER.resolve():
        raise SetupError('Unsafe world path; refusing reset')
    if world.exists():
        backups = SERVER.parent/'backups'
        backups.mkdir(parents=True,exist_ok=True)
        suffix = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        target = backups/f'world_{suffix}'
        if target.exists():
            raise SetupError('Backup collision; refusing overwrite')
        shutil.move(str(world),str(target))
        print('[BACKUP] Previous world moved to:',target)
    properties = ensure_properties()
    seed = input('World seed (leave blank for random): ').strip()
    if not seed:
        seed = str(secrets.randbits(63))
    if len(seed) > 80 or any(c in seed for c in '\r\n='):
        raise SetupError('Seed must be 1–80 characters with no newlines or equals signs')
    path = SERVER/'server.properties'
    properties['level-seed']=seed
    path.write_text('# Local Manhunt test server\n'+''.join(f'{k}={v}\n' for k,v in sorted(properties.items())), encoding='utf-8')
    print('[WORLD] Next world will use seed:',seed)
    print('[WORLD] Launch the game to generate it. Backups are never deleted automatically.')


def _console_reader(proc, lines):
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.rstrip()
        lines.put(line)
        if any(w in line.lower() for w in ('done (', 'error', 'failed', 'exception', 'carpet', 'eula')):
            print('[SERVER]',line[-250:])


def start_server(java: str):
    if local_port_open(25565):
        raise SetupError('Port 25565 is already in use. Stop the existing server first.')
    args = [java, '-Xms1024M', '-Xmx3072M', '-jar', 'fabric-server.jar', 'nogui']
    print('[SERVER] Starting Minecraft 1.21.11 + Fabric + Carpet...')
    print('[SERVER] First startup must download official Minecraft files and may take longer.')
    proc = subprocess.Popen(args,cwd=SERVER,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',bufsize=1)
    lines=queue.Queue()
    threading.Thread(target=_console_reader,args=(proc,lines),daemon=True).start()
    return proc,lines


def wait_for_rcon(proc, props, timeout=240):
    start=time.monotonic()
    while time.monotonic()-start<timeout:
        if proc.poll() is not None:
            raise SetupError(f'Server exited with code {proc.returncode}. Check runtime/server-data/logs/latest.log')
        try:
            rcon=RconClient('127.0.0.1',int(props['rcon.port']),props['rcon.password'])
            rcon.connect()
            if rcon.command('list') is not None:
                print('[SERVER] RCON authenticated; server is ready.')
                return rcon
            rcon.close()
        except (OSError,RconError):
            pass
        time.sleep(2)
    raise SetupError('Minecraft server did not become ready. Inspect runtime/server-data/logs/latest.log')


def stop_server(proc):
    if proc.poll() is None:
        print('[SERVER] Saving world and stopping the server...')
        try:
            assert proc.stdin is not None
            proc.stdin.write('stop\n')
            proc.stdin.flush()
            proc.wait(timeout=45)
        except (OSError,subprocess.TimeoutExpired):
            print('[SERVER] Did not stop normally. No automatic world deletion will occur.')


def main(argv=None):
    parser=argparse.ArgumentParser(description='Launch Minecraft 1.21.11 local AI hit-Manhunt')
    parser.add_argument('--role', choices=['hunter','runner'],default='runner',help='Your human role')
    parser.add_argument('--head-start',type=int,default=20,help='Runner head start (seconds)')
    parser.add_argument('--survival-seconds',type=int,default=180,help='Runner survival win timer')
    parser.add_argument('--setup-only',action='store_true',help='Install components, but do not start server')
    parser.add_argument('--reset-world',action='store_true',help='Archive existing world and select seed')
    args=parser.parse_args(argv)
    proc=None
    rcon=None
    try:
        if args.reset_world:
            reset_world()
            return 0
        java=prepare(accept_eula=not args.setup_only)
        if args.setup_only:
            print('[READY] Files installed; run START_AS_RUNNER.bat or START_AS_HUNTER.bat')
            return 0
        props=ensure_properties()
        proc,_=start_server(java)
        rcon=wait_for_rcon(proc, props)
        lobby = Lobby(rcon)
        lobby.setup()
        lobby.start_console()
        role = args.role
        history = MatchHistory(SERVER.parent / 'logs' / 'match_history.jsonl')
        round_number = 0
        while proc.poll() is None:
            round_number += 1
            print(f'\n[ROUND {round_number}] Human role: {role.upper()}; starting a new round.')
            game = ManhuntMatch(rcon, role, args.head_start, args.survival_seconds)
            winner = game.run()
            if winner not in ('hunter', 'runner'):
                print(f'[MATCH] Round ended without a winner: {winner}. Waiting for a player to reconnect.')
                time.sleep(1)
                continue
            result = RoundResult(role, winner, game.player, game.game_duration, game.result_reason or 'hit')
            # The result is announced *after* game.run has stopped bot movement.
            history.record(result)
            lobby.clear_pending_console()
            lobby.prepare_player(game.player)
            show_round_result(rcon, result, history.summary())
            print(f'[ROUND {round_number}] {result.headline} {result.description}')
            choice = lobby.wait_for_next_round(game.player, proc)
            if choice == 'quit':
                break
            if choice == 'switch':
                role = 'hunter' if role == 'runner' else 'runner'
                print('[LOBBY] Switched role to', role.upper())
            else:
                print('[LOBBY] Starting rematch with the same role.')
        return 0
    except (SetupError, RconError, OSError, ValueError, RuntimeError) as err:
        print('\n[ERROR]',err,file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('\n[STOP] Interrupted by user.')
        return 130
    finally:
        if rcon:
            rcon.close()
        if proc:
            stop_server(proc)


if __name__=='__main__':
    sys.exit(main())
