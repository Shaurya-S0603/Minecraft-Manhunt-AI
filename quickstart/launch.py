"""Local server process helpers and a compatibility alias for Hunter play."""
from __future__ import annotations
import queue
import socket
import subprocess
import sys
import threading
import time
from .install import SERVER, SetupError, ensure_properties
from .rcon import RconClient, RconError


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


def start_server(java: str, server=SERVER, *, game_port=25565):
    if local_port_open(game_port):
        raise SetupError(f'Port {game_port} is already in use. Stop the existing server first.')
    args = [java, '-Xms1024M', '-Xmx3072M', '-jar', 'fabric-server.jar', 'nogui']
    print('[SERVER] Starting Minecraft 1.21.11 + Fabric + Carpet...')
    print('[SERVER] First startup must download official Minecraft files and may take longer.')
    proc = subprocess.Popen(args,cwd=server,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',bufsize=1)
    lines=queue.Queue()
    threading.Thread(target=_console_reader,args=(proc,lines),daemon=True).start()
    return proc,lines


def wait_for_rcon(proc, props, timeout=240, *, command_timeout=4.0):
    start=time.monotonic()
    while time.monotonic()-start<timeout:
        if proc.poll() is not None:
            raise SetupError(f'Server exited with code {proc.returncode}. Check runtime/server-data/logs/latest.log')
        try:
            rcon=RconClient('127.0.0.1',int(props['rcon.port']),props['rcon.password'], timeout=command_timeout)
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
    from .hunter_v1.cli import main as hunter_main

    return hunter_main(["play", *(sys.argv[1:] if argv is None else argv)])


if __name__ == "__main__":
    sys.exit(main())
