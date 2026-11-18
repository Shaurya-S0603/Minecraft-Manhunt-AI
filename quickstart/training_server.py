"""Private, isolated Fabric/Carpet arena server for autonomous trial batches.

Not a Manhunt match. Never touches/saves/resets the user's ordinary
runtime/server-data/world; test maps live under runtime/training-server-data.
"""
from __future__ import annotations
import argparse
import secrets
import shutil
import subprocess
import sys
import time
from pathlib import Path

from . import install
from .arena_training import ArenaRunner, built_in_stages, read_stages, write_stage_template, checked
from .observations import parse_player_list, validate_name
from .launch import _console_reader, local_port_open, wait_for_rcon, stop_server
import queue
import threading

TRAIN_SERVER=install.ROOT/'runtime'/'training-server-data'
PORT=25566
RCON_PORT=25576


def training_properties(directory: Path=TRAIN_SERVER) -> dict:
    """Generate dedicated local-only ports/password; never reuse normal RCON."""
    directory.mkdir(parents=True,exist_ok=True)
    path=directory/'server.properties'
    props={}
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                key,value=line.split('=',1)
                props[key]=value.strip()
    if props.get('level-name','world')!='world':
        raise ValueError('Trainer refuses to edit a custom level-name')
    props.update({'server-ip':'127.0.0.1','server-port':str(PORT),
                  'online-mode':'true','white-list':'false','enable-rcon':'true',
                  'rcon.port':str(RCON_PORT),'level-name':'world',
                  'gamemode':'survival','difficulty':'peaceful',
                  'spawn-protection':'0','enable-command-block':'false',
                  'max-players':'4','view-distance':'6','simulation-distance':'6',
                  'motd':'Private autonomous movement-training arena'})
    # Even when a previous configuration was edited, the training server
    # stays on 127.0.0.1 with normal online authentication enabled.
    assert props['server-ip']=='127.0.0.1' and props['online-mode']=='true'
    if not props.get('rcon.password') or props['rcon.password'] in ('password','changeme'):
        props['rcon.password']=secrets.token_urlsafe(32)
    path.write_text('# Local TRAINING server only. NEVER COMMIT.\n'+
                    ''.join(f'{k}={v}\n' for k,v in sorted(props.items())),encoding='utf-8')
    return props


def install_training_server(main: Path=install.SERVER, training: Path=TRAIN_SERVER):
    """Copy *only* reviewed Fabric/Carpet distribution files into training.

    Neither the survival world nor its server.properties is ever copied.
    """
    training.mkdir(parents=True,exist_ok=True)
    source=main/'fabric-server.jar'
    if not source.is_file():
        raise FileNotFoundError('Fabric launcher missing; complete INSTALL_SERVER_ONLY first')
    shutil.copy2(source,training/'fabric-server.jar')
    mods=main/'mods'
    target=training/'mods'
    target.mkdir(parents=True,exist_ok=True)
    if not mods.is_dir():
        raise FileNotFoundError('Carpet mods missing from main server')
    for file in mods.iterdir():
        if file.is_file() and file.suffix=='.jar' and not file.is_symlink():
            shutil.copy2(file,target/file.name)
    original=main/'eula.txt'
    if not original.is_file() or 'eula=true' not in original.read_text(encoding='ascii'):
        raise RuntimeError('Review and accept Minecraft EULA using existing launcher before training')
    (training/'eula.txt').write_text('eula=true\n',encoding='ascii')
    return training_properties(training)


def launch_training_server(java: str, directory: Path=TRAIN_SERVER):
    if local_port_open(PORT) or local_port_open(RCON_PORT):
        raise RuntimeError('Training ports 25566/25576 already occupied. Stop existing trainer.')
    proc=subprocess.Popen([java,'-Xms1024M','-Xmx3072M','-jar','fabric-server.jar','nogui'],
                         cwd=directory,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',bufsize=1)
    lines=queue.Queue()
    threading.Thread(target=_console_reader,args=(proc,lines),daemon=True).start()
    return proc


def _command(rcon, command):
    response=rcon.command(command)
    if any(phrase in response.lower() for phrase in ('unknown command','incorrect argument',
                'could not','failed','unknown or incomplete')):
        raise RuntimeError('Arena builder rejected '+command+': '+response[:140])


def generate_arena(rcon, world_dir: Path, *, overwrite: bool=False):
    """Generate only in a dedicated training world, never an imported map.

    Coordinates around x=0..30, y=204..240, z=0..100 are cleared. This
    operation is explicitly isolated from the human's Manhunt world.
    """
    if world_dir.name!='world' or world_dir.parent.name!='training-server-data':
        raise ValueError('Refusing to generate arena outside dedicated training world')
    marker=world_dir.parent/'.generated_training_arena'
    if (world_dir.parent/'.custom_map_installed').exists():
        raise RuntimeError('Training world marked custom; refusing to overwrite map')
    if marker.exists() and not overwrite:
        return False
    print('[ARENA] Building floating practice lanes in isolated training world...')
    # Minecraft 1.21.11 renamed game rules to namespaced snake_case IDs.
    # Preload a bounded region because off-spawn /fill commands otherwise
    # fail with 'position not loaded' in unattended server-only sessions.
    for command in ('forceload add -16 -16 32 112',
                    'gamerule minecraft:spawn_mobs false',
                    'gamerule minecraft:advance_time false',
                    'gamerule minecraft:advance_weather false',
                    'gamerule minecraft:fall_damage false',
                    'gamerule minecraft:keep_inventory true',
                    'difficulty peaceful','time set day','weather clear',
                    'setworldspawn 1 220 0'):
        _command(rcon,command)
    for z in (0,20,40,80,100):
        for a,b in ((200,217),(218,240)):
            _command(rcon,f'fill -6 {a} {z-6} 30 {b} {z+6} air')
        # Falls terminate on a broad safe shallow water catch basin.
        _command(rcon,f'fill -6 204 {z-6} 30 204 {z+6} stone')
        _command(rcon,f'fill -6 205 {z-6} 30 205 {z+6} water')
    for gap,z in ((1,0),(2,20),(3,40)):
        _command(rcon,f'fill 0 219 {z-2} 5 219 {z+2} stone')
        edge=6+gap
        _command(rcon,f'fill {edge} 219 {z-2} 15 219 {z+2} stone')
    # Swim: a 3-high shallow channel. The top remains open for breathing.
    _command(rcon,'fill 0 215 77 17 215 83 stone')
    _command(rcon,'fill 0 216 77 17 218 83 water')
    # Climb: solid wall east of ladder, small start area, and upper exit.
    _command(rcon,'fill 2 219 98 5 219 102 stone')
    _command(rcon,'fill 6 219 99 7 227 101 stone')
    _command(rcon,'fill 5 220 100 5 226 100 ladder[facing=west]')
    marker.write_text('Generated autonomous practice arena; v0.7.5\n',encoding='ascii')
    print('[ARENA] Generated stages: gap 1,2,3; horizontal swim; ladder ascent.')
    return True


def authenticated_shadow_player(rcon, *, clock=time.monotonic, sleep=time.sleep, timeout=180):
    """Use Carpet's authenticated human->fake-player shadow command.

    This fallback does NOT invent a player profile or turn off online-mode.
    The real Minecraft player joins the isolated server, then Carpet converts
    that already-authenticated player session into a simulated player.
    """
    print('[ARENA] Authenticated shadow mode enabled.')
    print('[ARENA] Join 127.0.0.1:25566 with your legitimate Minecraft account.')
    print('[ARENA] You will disconnect once Carpet transfers control to the AI.')
    deadline=clock()+timeout
    while clock()<deadline:
        names=parse_player_list(rcon.command('list'))
        if len(names)>1:
            raise RuntimeError('Expected exactly one authenticated player for shadow mode; found '+str(len(names)))
        if len(names)==1:
            name=validate_name(names[0])
            response=checked(rcon,f'player {name} shadow')
            # The fake player should remain connected using the same identity.
            sleep(.5)
            if name.casefold() not in {n.casefold() for n in parse_player_list(rcon.command('list'))}:
                raise RuntimeError('Carpet shadow conversion did not retain the fake player; '+response[:140])
            print('[ARENA] Authenticated player was converted to a Carpet fake player; training can start.')
            return name
        sleep(.5)
    raise RuntimeError('No authenticated player joined the training server. No trials were started.')


def main(argv=None):
    parser=argparse.ArgumentParser(description='AUTONOMOUS Minecraft parkour training, no Manhunt match')
    parser.add_argument('--episodes',type=int,default=1000,help='Physical episodes per selected course, default 1000')
    parser.add_argument('--skills',choices=['jump','swim','climb','all'],default='jump')
    parser.add_argument('--config',type=Path,help='Optional custom stage JSON; no custom world bundled')
    parser.add_argument('--interleave',action='store_true',help='Rotate jump/swim/climb stages each round')
    parser.add_argument('--adaptive',action='store_true',help='V4 generation-aware recent-evidence scheduling instead of fixed course repetitions')
    parser.add_argument('--budget',type=int,default=1000,help='Adaptive TOTAL Minecraft attempts (not per course)')
    parser.add_argument('--validation-every',type=int,default=5,help='Reserve every Nth physical trial as held-out validation')
    parser.add_argument('--shadow-authenticated',action='store_true',
                        help='Compatibility flag; training always requires one authenticated shadow player')
    parser.add_argument('--setup-only',action='store_true',help='Prepare isolated server without launching trials')
    parser.add_argument('--serve-only',action='store_true',help='Keep generated training world online for inspection; no trials or block edits')
    args=parser.parse_args(argv)
    if not 1<=args.episodes<=10000:
        parser.error('--episodes must be 1..10000')
    if not 1<=args.budget<=10000 or not 2<=args.validation_every<=20:
        parser.error('--budget must be 1..10000; --validation-every 2..20')
    stage_template=install.ROOT/'training'/'arena_config.example.json'
    write_stage_template(stage_template,built_in_stages())
    stages=read_stages(args.config) if args.config else built_in_stages()
    skills=None if args.skills=='all' else {'sprint_jump' if args.skills=='jump' else args.skills}
    proc=None;rcon=None
    bot_name='ManhuntBot'
    try:
        # First-time downloads/EULA apply to the normal installation only.
        # Actual training world's data/config remains entirely isolated.
        java=install.prepare(accept_eula=True)
        props=install_training_server()
        if args.setup_only:
            print('[ARENA] Isolated training server installed. World untouched.')
            return 0
        proc=launch_training_server(java)
        rcon=wait_for_rcon(proc,props)
        if args.serve_only:
            print('[ARENA] Practice server running at 127.0.0.1:25566; no trials.')
            while proc.poll() is None:
                time.sleep(1)
            raise RuntimeError('Practice server exited unexpectedly')
        if not args.config:
            generate_arena(rcon,TRAIN_SERVER/'world')
        else:
            print('[ARENA] Custom config selected; will NOT generate/overwrite training map.')
        bot_name = authenticated_shadow_player(rcon)
        runner=ArenaRunner(rcon,bot=bot_name)
        summary=(runner.run_adaptive(stages,args.budget,skills,validation_every=args.validation_every)
                 if args.adaptive else runner.run(stages,args.episodes,skills,interleave=args.interleave or args.skills=='all'))
        print('[ARENA] Finished, results:',summary)
        print('[ARENA] Jump trial log:',runner.trainer.log_file)
        print('[ARENA] All episodes:',runner.arena_log)
        print('[ARENA] Trained jump policy:',runner.trainer.root/'policy.json')
        print('[ARENA] Trained swim/climb policy:',runner.trainer.root/'skill_policy.json')
        print('[ARENA] Adaptive curriculum weights:',runner.trainer.root/'curriculum_policy_v3.json')
        from .arena_report import build_report,export_report,OUTPUT
        report=build_report(runner.arena_log,runner.trainer.root/'policy.json',runner.trainer.root/'skill_policy.json')
        for file in export_report(report,OUTPUT):
            print('[REPORT] Wrote:',file)
        return 0
    except (ValueError,RuntimeError,FileNotFoundError,ConnectionError,OSError,install.SetupError) as exc:
        print('[ARENA ERROR]',exc,file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('[ARENA] Interrupted; stopping controls and saving training world.')
        return 130
    finally:
        if rcon is not None:
            try: rcon.command(f'player {bot_name} stop')
            except Exception: pass
            rcon.close()
        if proc is not None:
            stop_server(proc)

if __name__=='__main__':
    raise SystemExit(main())
