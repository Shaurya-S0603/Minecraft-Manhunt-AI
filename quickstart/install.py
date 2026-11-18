"""First-run Fabric 1.21.11 server + Carpet installer, no binary redistribution.

Official HTTPS endpoints; mod hashes are checked against Modrinth's metadata.
"""
from __future__ import annotations
import hashlib
import json
import re
import secrets
import shutil
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path

MINECRAFT_VERSION = '1.21.11'
ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / 'runtime' / 'server-data'
FABRIC = 'https://meta.fabricmc.net/v2/versions'
MODRINTH = 'https://api.modrinth.com/v2'
AGENT = 'MinecraftManhunterLocalTest/0.7 (+https://fabricmc.net/)'


class SetupError(RuntimeError):
    pass


def fetch(url: str, max_bytes: int = 40_000_000) -> bytes:
    req = urllib.request.Request(url, headers={'User-Agent':AGENT})
    with urllib.request.urlopen(req, timeout=30) as response:
        data = response.read(max_bytes+1)
        if len(data) > max_bytes:
            raise SetupError('Download exceeded safe size limit')
        return data


def json_get(url: str):
    return json.loads(fetch(url, 2_000_000).decode('utf-8'))


def java_executable() -> str:
    result = shutil.which('java')
    if result is None:
        raise SetupError('Java missing. Install JDK 21 and restart this terminal: https://adoptium.net/temurin/releases/?version=21')
    version = subprocess.run([result, '-version'], capture_output=True, text=True, timeout=12)
    combined = version.stdout + version.stderr
    found = re.search(r'version\s+"(\d+)', combined)
    if not found or int(found.group(1)) < 21:
        raise SetupError('Minecraft 1.21.11 requires Java 21 or newer. Installed Java: ' + combined.split('\n')[0])
    if int(found.group(1)) != 21:
        print('[CHECK] Java 21 is recommended; detected:', combined.split('\n')[0])
    return result


def download_to(url: str, destination: Path, max_bytes: int, sha512: str | None = None):
    print('[DOWNLOAD]', destination.name)
    destination.parent.mkdir(parents=True, exist_ok=True)
    data = fetch(url, max_bytes)
    if sha512 and hashlib.sha512(data).hexdigest().lower() != sha512.lower():
        raise SetupError('File SHA-512 mismatch. Refusing to install: '+destination.name)
    destination.with_suffix(destination.suffix+'.partial').write_bytes(data)
    destination.with_suffix(destination.suffix+'.partial').replace(destination)


def install_fabric(server=None):
    server = SERVER if server is None else server
    target = server / 'fabric-server.jar'
    if target.exists() and target.stat().st_size > 10000:
        print('[READY] Fabric launcher already exists')
        return
    loaders = json_get(f'{FABRIC}/loader/{MINECRAFT_VERSION}')
    stable_loaders = [v['loader']['version'] for v in loaders if v.get('loader',{}).get('stable')]
    if not stable_loaders:
        raise SetupError('No stable Fabric Loader for 1.21.11 found')
    installers = json_get(f'{FABRIC}/installer')
    stable_installers = [v['version'] for v in installers if v.get('stable')]
    if not stable_installers:
        raise SetupError('No stable Fabric installer found')
    url = f'{FABRIC}/loader/{MINECRAFT_VERSION}/{stable_loaders[0]}/{stable_installers[0]}/server/jar'
    download_to(url, target, 15_000_000)
    print('[FABRIC]', stable_loaders[0], 'launcher', stable_installers[0])


def install_mod(project_id: str, label: str, server=None, *, version=None):
    server = SERVER if server is None else server
    mods = server/'mods'
    marker = mods/f'manhunt-{project_id}.install.json'
    if marker.exists():
        try:
            details = json.loads(marker.read_text(encoding='utf-8'))
            if (version is None or details.get('version') == version) and (mods/details['filename']).is_file():
                print('[READY]', label, 'already installed')
                return
        except (ValueError, KeyError, OSError):
            pass
    query = urllib.parse.urlencode({
        'loaders': json.dumps(['fabric']),
        'game_versions': json.dumps([MINECRAFT_VERSION]),
    })
    versions = json_get(f'{MODRINTH}/project/{project_id}/version?{query}')
    releases = [v for v in versions if v.get('version_type') == 'release'
                and (version is None or v.get('version_number') == version)]
    if not releases:
        raise SetupError(f"No release of {label} {version or ''} for Fabric {MINECRAFT_VERSION}")
    best = max(releases, key=lambda item: item['date_published'])
    primary = next((f for f in best['files'] if f.get('primary')), best['files'][0])
    filename = primary['filename']
    if '/' in filename or '\\' in filename or not filename.endswith('.jar'):
        raise SetupError('Untrusted filename in mod metadata')
    file_url = primary['url']
    if not file_url.startswith('https://'):
        raise SetupError('Expected secure mod download URL')
    download_to(file_url, mods/filename, 60_000_000, primary.get('hashes',{}).get('sha512'))
    marker.write_text(json.dumps({'filename':filename,'version':best['version_number']},indent=2), encoding='utf-8')
    print('[MOD]', label, best['version_number'])


def ensure_properties(server=None, *, game_port=25565, rcon_port=25575, overrides=None):
    server = SERVER if server is None else server
    server.mkdir(parents=True, exist_ok=True)
    path = server/'server.properties'
    properties = {}
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            if '=' in line and not line.startswith('#'):
                a,b = line.split('=',1)
                properties[a.strip()] = b.strip()
    if properties.get('level-name','world') not in ('world',):
        raise SetupError('Refusing to modify custom world-level name: use a fresh test-server directory')
    properties.update({
        'server-ip':'127.0.0.1', 'server-port':str(game_port),
        'online-mode':'true', 'white-list':'false',
        'enable-rcon':'true', 'rcon.port':str(rcon_port),
        'max-players':'8', 'motd':'Local Minecraft AI Manhunt test',
        'level-name':'world', 'gamemode':'survival', 'difficulty':'normal',
        'spawn-protection':'0', 'enable-command-block':'false',
        'enforce-secure-profile':'true',
    })
    if overrides:
        properties.update(overrides)
    # Never carry a bundled or user-supplied password into a public config.
    if not properties.get('rcon.password') or properties['rcon.password'] in ('changeme','password'):
        properties['rcon.password'] = secrets.token_urlsafe(32)
    path.write_text('# Generated for localhost-only Minecraft Manhunt. Do not publish RCON credentials.\n'+''.join(f'{k}={v}\n' for k,v in sorted(properties.items())),encoding='utf-8')
    return properties


def eula_agreement(server=None):
    server = SERVER if server is None else server
    target = server/'eula.txt'
    if target.exists() and re.search(r'(?m)^eula=true\s*$',target.read_text(encoding='utf-8')):
        return
    print('\n[MINECRAFT EULA] You must personally review and accept the Minecraft EULA:')
    print('https://www.minecraft.net/en-us/eula')
    reply = input('After reading, type "I AGREE" to accept (anything else cancels): ').strip()
    if reply != 'I AGREE':
        raise SetupError('Minecraft EULA was not accepted. Server launch cancelled.')
    target.write_text('eula=true\n',encoding='ascii')


def prepare(accept_eula: bool = True):
    java = java_executable()
    ensure_properties()
    install_fabric()
    install_mod('carpet','Carpet fake players')
    # Carpet does not require Fabric API. Keep first-run downloads minimal.
    if accept_eula:
        eula_agreement()
    return java
